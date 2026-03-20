import base64
import hashlib
import hmac
import json
import logging
import os
import time

import boto3
import botocore.session
from botocore.signers import RequestSigner
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Structured JSON logger ────────────────────────────────────────────────────
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)
if not LOG.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(_h)


def _log(level: str, msg: str, **ctx):
    LOG.log(getattr(logging, level.upper()), json.dumps({"level": level.upper(), "msg": msg, **ctx}))


# ── HTTP session with retries ─────────────────────────────────────────────────
def _make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s

_SESSION = _make_session()

# ── AWS clients ───────────────────────────────────────────────────────────────
s3 = boto3.client("s3")
events = boto3.client("events")
eks = boto3.client("eks")
ddb = boto3.client("dynamodb")

# ── Config from environment ───────────────────────────────────────────────────
INCIDENT_BUCKET = os.environ["INCIDENT_BUCKET"]
EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
CLUSTER_NAME = os.environ.get("CLUSTER_NAME", "")
PROM_URL = os.environ.get("PROMETHEUS_QUERY_URL", "")
ENABLE_K8S = os.environ.get("ENABLE_K8S_READONLY", "true").lower() == "true"
INCIDENTS_TABLE_NAME = os.environ.get("INCIDENTS_TABLE_NAME", "")
DEDUP_TTL_SECONDS = int(os.environ.get("DEDUP_TTL_SECONDS", "1800"))
ENABLE_AMP = os.environ.get("ENABLE_AMP", "false").lower() == "true"
WEBHOOK_SECRET       = os.environ.get("WEBHOOK_SECRET", "")
# When True, emits MultiAgentIncidentCreated instead of IncidentBundleCreated,
# routing the incident into the Step Functions multi-agent pipeline.
ENABLE_MULTI_AGENT   = os.environ.get("ENABLE_MULTI_AGENT", "false").lower() == "true"


def _now():
    return int(time.time())


def _emit(detail_type, detail):
    events.put_events(Entries=[{
        "EventBusName": EVENT_BUS_NAME,
        "Source": "ai.gitops",
        "DetailType": detail_type,
        "Detail": json.dumps(detail),
    }])


def _dedup_key(service: str, env: str, alertname: str) -> str:
    raw = f"{service}|{env}|{alertname}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _dedup_check_and_write(dedup_key: str):
    """Returns (is_new, existing_incident_id_or_none). Uses conditional put with TTL."""
    if not INCIDENTS_TABLE_NAME:
        return True, None
    now = _now()
    try:
        ddb.put_item(
            TableName=INCIDENTS_TABLE_NAME,
            Item={
                "dedup_key": {"S": dedup_key},
                "created_at": {"N": str(now)},
                "ttl": {"N": str(now + DEDUP_TTL_SECONDS)},
            },
            ConditionExpression="attribute_not_exists(dedup_key)",
        )
        return True, None
    except ddb.exceptions.ConditionalCheckFailedException:
        return False, None
    except Exception as exc:
        _log("warning", "dedup_write_failed", error=str(exc))
        return True, None  # fail open: process the incident


def _prom_query(q: str):
    if not PROM_URL:
        return {"skipped": True, "reason": "PROMETHEUS_QUERY_URL not set"}
    try:
        url = f"{PROM_URL.rstrip('/')}/api/v1/query"
        r = _SESSION.get(url, params={"query": q}, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        return {"error": str(exc)}


def _eks_token(cluster_name: str) -> str:
    session = botocore.session.get_session()
    creds = session.get_credentials().get_frozen_credentials()
    signer = RequestSigner(
        service_id="sts",
        region_name=AWS_REGION,
        service_name="sts",
        signing_version="v4",
        credentials=creds,
        event_emitter=session.get_component("event_emitter"),
    )
    params = {
        "method": "GET",
        "url": f"https://sts.{AWS_REGION}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15",
        "body": {},
        "headers": {"x-k8s-aws-id": cluster_name},
        "context": {},
    }
    signed = signer.generate_presigned_url(params, expires_in=60, operation_name="")
    return "k8s-aws-v1." + base64.urlsafe_b64encode(signed.encode("utf-8")).decode("utf-8").rstrip("=")


def _k8s_api(cluster_name: str):
    desc = eks.describe_cluster(name=cluster_name)["cluster"]
    endpoint = desc["endpoint"]
    ca = base64.b64decode(desc["certificateAuthority"]["data"])
    return endpoint, ca


def _k8s_get(endpoint: str, token: str, path: str, ca_path: str):
    url = endpoint.rstrip("/") + path
    r = _SESSION.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10, verify=ca_path)
    r.raise_for_status()
    return r.json()


def handler(event, context):
    # ── Webhook secret validation ─────────────────────────────────────────────
    if WEBHOOK_SECRET:
        incoming = (event.get("headers") or {}).get("x-webhook-secret", "")
        if not hmac.compare_digest(incoming, WEBHOOK_SECRET):
            _log("warning", "webhook_auth_failed")
            return {"statusCode": 401, "body": json.dumps({"error": "unauthorized"})}

    incident_id = f"inc-{_now()}-{context.aws_request_id[:8]}"
    _log("info", "incident_received", incident_id=incident_id)

    raw = event
    if "requestContext" in event and "body" in event:  # API Gateway HTTP API proxy
        body = event.get("body") or "{}"
        try:
            raw = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            raw = {"body_raw": body}

    labels = {}
    annotations = {}
    try:
        if isinstance(raw, dict) and raw.get("alerts"):
            labels = raw["alerts"][0].get("labels", {}) or {}
            annotations = raw["alerts"][0].get("annotations", {}) or {}
    except (KeyError, IndexError, TypeError) as exc:
        _log("warning", "alert_parse_failed", error=str(exc))

    alertname = labels.get("alertname", "unknown")
    service = labels.get("service", "unknown")
    env = labels.get("env", labels.get("environment", "unknown"))
    severity = labels.get("severity", "unknown")

    # ── Dedup / correlation guard ─────────────────────────────────────────────
    dk = _dedup_key(service, env, alertname)
    is_new, _ = _dedup_check_and_write(dk)
    if not is_new:
        _log("info", "dedup_suppressed", dedup_key=dk, service=service, alertname=alertname)
        return {"statusCode": 202, "body": json.dumps({"message": "dedup_suppressed", "dedup_key": dk})}

    # ── Prometheus enrichment ─────────────────────────────────────────────────
    prom_snapshots = {
        "error_rate_5xx": _prom_query(
            f'sum(rate(http_requests_total{{service="{service}",status=~"5.."}}[5m]))'
        ),
        "cpu_usage_demo_ns": _prom_query(
            'sum(rate(container_cpu_usage_seconds_total{namespace="demo"}[5m]))'
        ),
        "mem_working_set_demo_ns": _prom_query(
            'sum(container_memory_working_set_bytes{namespace="demo"})'
        ),
    }

    # ── Kubernetes enrichment ─────────────────────────────────────────────────
    k8s = {"skipped": True}
    if ENABLE_K8S and CLUSTER_NAME:
        try:
            endpoint, ca = _k8s_api(CLUSTER_NAME)
            ca_path = f"/tmp/{incident_id}-ca.crt"
            with open(ca_path, "wb") as f:
                f.write(ca)
            token = _eks_token(CLUSTER_NAME)
            k8s_events = _k8s_get(endpoint, token, "/api/v1/namespaces/demo/events?limit=20", ca_path)
            dep = _k8s_get(
                endpoint, token,
                "/apis/apps/v1/namespaces/demo/deployments/demo-service",
                ca_path,
            )
            k8s = {
                "cluster": CLUSTER_NAME,
                "events": k8s_events,
                "deployment": {
                    "name": dep.get("metadata", {}).get("name"),
                    "replicas": dep.get("spec", {}).get("replicas"),
                    "availableReplicas": dep.get("status", {}).get("availableReplicas"),
                    "unavailableReplicas": dep.get("status", {}).get("unavailableReplicas"),
                    "image": (
                        dep.get("spec", {})
                        .get("template", {})
                        .get("spec", {})
                        .get("containers", [{}])[0]
                        .get("image")
                    ),
                },
            }
        except Exception as exc:
            _log("warning", "k8s_enrichment_failed", error=str(exc), cluster=CLUSTER_NAME)
            k8s = {"error": str(exc), "cluster": CLUSTER_NAME}

    bundle = {
        "incident_id": incident_id,
        "dedup_key": dk,
        "received_at": _now(),
        "service": service,
        "env": env,
        "severity": severity,
        "labels": labels,
        "annotations": annotations,
        "prometheus": prom_snapshots,
        "kubernetes": k8s,
        "raw_event": raw,
        "constraints": {"allowed_actions_ref": "gitops/policies/allowed-actions.yaml"},
    }

    key = f"incidents/{incident_id}.json"
    s3.put_object(
        Bucket=INCIDENT_BUCKET,
        Key=key,
        Body=json.dumps(bundle, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    _log("info", "bundle_stored", incident_id=incident_id, s3_key=key)

    event_type = "MultiAgentIncidentCreated" if ENABLE_MULTI_AGENT else "IncidentBundleCreated"
    _emit(event_type, {
        "incident_id": incident_id,
        "s3_bucket": INCIDENT_BUCKET,
        "s3_key": key,
        "service": service,
        "env": env,
    })
    _log("info", "event_emitted", event_type=event_type, incident_id=incident_id)
    return {"statusCode": 200, "body": json.dumps({"incident_id": incident_id, "s3_key": key})}
