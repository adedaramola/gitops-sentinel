import json, os, time, hashlib
import boto3
import requests
import base64

s3 = boto3.client("s3")
events = boto3.client("events")
eks = boto3.client("eks")
ddb = boto3.client("dynamodb")

INCIDENT_BUCKET = os.environ["INCIDENT_BUCKET"]
EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
CLUSTER_NAME = os.environ.get("CLUSTER_NAME", "")
PROM_URL = os.environ.get("PROMETHEUS_QUERY_URL", "")
ENABLE_K8S = os.environ.get("ENABLE_K8S_READONLY", "true").lower() == "true"

# Dedup/correlation
INCIDENTS_TABLE_NAME = os.environ.get("INCIDENTS_TABLE_NAME", "")
DEDUP_TTL_SECONDS = int(os.environ.get("DEDUP_TTL_SECONDS", "1800"))  # 30m window

# AMP optional (SigV4). If ENABLE_AMP=true, PROM_URL should be the AMP query endpoint.
ENABLE_AMP = os.environ.get("ENABLE_AMP", "false").lower() == "true"

def _now():
    return int(time.time())

def _emit(detail_type, detail):
    events.put_events(Entries=[{
        "EventBusName": EVENT_BUS_NAME,
        "Source": "gitops.sentinel",
        "DetailType": detail_type,
        "Detail": json.dumps(detail)
    }])

def _dedup_key(service: str, env: str, alertname: str):
    raw = f"{service}|{env}|{alertname}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _dedup_check_and_write(dedup_key: str):
    """
    Returns (is_new, existing_incident_id_or_none)
    Uses conditional put to create a record with TTL.
    """
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
            ConditionExpression="attribute_not_exists(dedup_key)"
        )
        return True, None
    except Exception:
        # already exists in window
        return False, None

def _prom_query(q: str):
    if not PROM_URL:
        return {"skipped": True, "reason": "PROMETHEUS_QUERY_URL not set"}
    try:
        url = f"{PROM_URL.rstrip('/')}/api/v1/query"
        r = requests.get(url, params={"query": q}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def _eks_token(cluster_name: str) -> str:
    import botocore.session
    from botocore.signers import RequestSigner
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
    token = "k8s-aws-v1." + base64.urlsafe_b64encode(signed.encode("utf-8")).decode("utf-8").rstrip("=")
    return token

def _k8s_api(cluster_name: str):
    desc = eks.describe_cluster(name=cluster_name)["cluster"]
    endpoint = desc["endpoint"]
    ca = base64.b64decode(desc["certificateAuthority"]["data"])
    return endpoint, ca

def _k8s_get(endpoint: str, token: str, path: str, ca_path: str):
    url = endpoint.rstrip("/") + path
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10, verify=ca_path)
    r.raise_for_status()
    return r.json()

def handler(event, context):
    incident_id = f"inc-{_now()}-{context.aws_request_id[:8]}"

    raw = event
    if "requestContext" in event and "body" in event:  # API Gateway HTTP API proxy
        body = event.get("body") or "{}"
        try:
            raw = json.loads(body)
        except Exception:
            raw = {"body_raw": body}

    labels = {}
    annotations = {}
    try:
        if isinstance(raw, dict) and raw.get("alerts"):
            labels = raw["alerts"][0].get("labels", {}) or {}
            annotations = raw["alerts"][0].get("annotations", {}) or {}
    except Exception:
        pass

    alertname = labels.get("alertname", "unknown")
    service = labels.get("service", "unknown")
    namespace = labels.get("namespace", labels.get("env", "unknown"))
    env = labels.get("env", labels.get("environment", "unknown"))
    severity = labels.get("severity", "unknown")

    # Dedup/correlation guard
    dk = _dedup_key(service, env, alertname)
    is_new, _ = _dedup_check_and_write(dk)
    if not is_new:
        return {"statusCode": 202, "body": json.dumps({"message": "dedup_suppressed", "dedup_key": dk})}

    prom_snapshots = {
        "error_rate_5xx": _prom_query(f'sum(rate(http_requests_total{{service="{service}",status=~"5.."}}[5m]))'),
        "cpu_usage": _prom_query(f'sum(rate(container_cpu_usage_seconds_total{{namespace="{namespace}",pod=~"{service}.*"}}[5m]))'),
        "mem_working_set": _prom_query(f'sum(container_memory_working_set_bytes{{namespace="{namespace}",pod=~"{service}.*"}})'),
    }

    k8s = {"skipped": True}
    if ENABLE_K8S and CLUSTER_NAME:
        try:
            endpoint, ca = _k8s_api(CLUSTER_NAME)
            ca_path = f"/tmp/{incident_id}-ca.crt"
            with open(ca_path, "wb") as f:
                f.write(ca)
            token = _eks_token(CLUSTER_NAME)
            k8s_events = _k8s_get(endpoint, token, f"/api/v1/namespaces/{namespace}/events?limit=20", ca_path)
            dep = _k8s_get(endpoint, token, f"/apis/apps/v1/namespaces/{namespace}/deployments/{service}", ca_path)
            k8s = {
                "cluster": CLUSTER_NAME,
                "events": k8s_events,
                "deployment": {
                    "name": dep.get("metadata", {}).get("name"),
                    "replicas": dep.get("spec", {}).get("replicas"),
                    "availableReplicas": dep.get("status", {}).get("availableReplicas"),
                    "unavailableReplicas": dep.get("status", {}).get("unavailableReplicas"),
                    "image": dep.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [{}])[0].get("image"),
                }
            }
        except Exception as e:
            k8s = {"error": str(e), "cluster": CLUSTER_NAME}

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
        "constraints": {"allowed_actions_ref": "gitops/policies/allowed-actions.yaml"}
    }

    key = f"incidents/{incident_id}.json"
    s3.put_object(
        Bucket=INCIDENT_BUCKET,
        Key=key,
        Body=json.dumps(bundle, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    _emit("SignalBundled", {"incident_id": incident_id, "s3_bucket": INCIDENT_BUCKET, "s3_key": key, "service": service, "env": env})
    return {"statusCode": 200, "body": json.dumps({"incident_id": incident_id, "s3_key": key})}
