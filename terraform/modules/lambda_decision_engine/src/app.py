import json, os, time, re, base64
import boto3
import requests
import yaml

s3 = boto3.client("s3")
secrets = boto3.client("secretsmanager")
bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))

GITHUB_API = "https://api.github.com"
GITHUB_OWNER = os.environ["GITHUB_OWNER"]
GITHUB_REPO = os.environ["GITHUB_REPO"]
GITHUB_APP_TOKEN_SECRET_ARN = os.environ["GITHUB_APP_TOKEN_SECRET_ARN"]  # store a fine-scoped token JSON: {"token":"..."}
MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "bedrock")  # bedrock|openai
ALLOWED_ACTIONS_PATH = os.environ.get("ALLOWED_ACTIONS_PATH", "gitops/policies/allowed-actions.yaml")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
OPENAI_SECRET_ARN = os.environ.get("OPENAI_SECRET_ARN", "")  # optional: secret json {"api_key":"..."}

def _get_secret_json(arn: str) -> dict:
    sec = secrets.get_secret_value(SecretId=arn)
    payload = sec.get("SecretString") or "{}"
    return json.loads(payload)

def _get_github_token():
    return _get_secret_json(GITHUB_APP_TOKEN_SECRET_ARN)["token"]

def _github_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def _gh(method, path, token, **kwargs):
    url = f"{GITHUB_API}{path}"
    r = requests.request(method, url, headers=_github_headers(token), timeout=30, **kwargs)
    if r.status_code >= 400:
        raise RuntimeError(f"GitHub API error {r.status_code}: {r.text}")
    return r.json() if r.text else {}

def _get_ref_sha(owner, repo, ref, token):
    data = _gh("GET", f"/repos/{owner}/{repo}/git/ref/{ref}", token)
    return data["object"]["sha"]

def _create_branch(owner, repo, branch, base_sha, token):
    return _gh("POST", f"/repos/{owner}/{repo}/git/refs", token, json={
        "ref": f"refs/heads/{branch}",
        "sha": base_sha
    })

def _get_file(owner, repo, path, ref, token):
    return _gh("GET", f"/repos/{owner}/{repo}/contents/{path}", token, params={"ref": ref})

def _put_file(owner, repo, path, message, content_bytes, sha, branch, token):
    return _gh("PUT", f"/repos/{owner}/{repo}/contents/{path}", token, json={
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
        "sha": sha,
        "branch": branch
    })

def _open_pr(owner, repo, title, body, head, base, token):
    return _gh("POST", f"/repos/{owner}/{repo}/pulls", token, json={
        "title": title,
        "body": body,
        "head": head,
        "base": base
    })

def _fetch_allowed_actions(token, ref="main") -> dict:
    obj = _get_file(GITHUB_OWNER, GITHUB_REPO, ALLOWED_ACTIONS_PATH, ref, token)
    data = base64.b64decode(obj["content"]).decode("utf-8")
    return yaml.safe_load(data) or {}

def _choose_action_heuristic(bundle, allowed):
    """
    Safe-by-default heuristic. LLM can override within allowed actions.
    """
    actions = {a["action"]: a.get("constraints", {}) for a in allowed.get("allowed_actions", [])}
    # Very simple: if 5xx error rate snapshot looks high, propose rollback; else scale.
    prom = bundle.get("prometheus", {})
    err = prom.get("error_rate_5xx", {})
    if "result" in (err.get("data") or {}) and "rollback_image" in actions:
        # We'll propose rollback to 'previous' (still constrained in allowed list)
        return {"action": "rollback_image", "target": {"env": bundle.get("env","staging")}, "params": {"tag": "previous"}}
    if "scale_replicas" in actions:
        return {"action": "scale_replicas", "target": {"env": bundle.get("env","staging")}, "params": {"replicas": 3}}
    return {"action": "restart_rollout", "target": {"env": bundle.get("env","staging")}, "params": {}}

def _llm_plan(bundle, allowed):
    """
    Returns a JSON dict with keys: action, target, params, rationale, risk.
    Ensures returned action is one of allowed actions.
    """
    # Keep prompt concise; enforce JSON-only output.
    allowed_actions = [a["action"] for a in allowed.get("allowed_actions", [])]
    prompt = f"""
You are an SRE assistant operating under strict GitOps controls.
You must propose ONE remediation within allowed actions only.

Allowed actions: {allowed_actions}

Incident bundle (JSON):
{json.dumps(bundle)[:6000]}

Respond with valid JSON only:
{{
  "action": "<one of allowed actions>",
  "target": {{"service": "<string>", "env": "<string>"}},
  "params": {{}},
  "risk": "<low|medium|high>",
  "rationale": "<short>"
}}
"""
    try:
        if MODEL_PROVIDER == "openai":
            if not OPENAI_SECRET_ARN:
                raise ValueError("OPENAI_SECRET_ARN not set")
            api_key = _get_secret_json(OPENAI_SECRET_ARN)["api_key"]
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4.1-mini",
                    "messages": [{"role":"user","content":prompt}],
                    "temperature": 0.2
                },
                timeout=30
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
        else:
            # Bedrock generic invoke (model id must be provided via env in production)
            model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 700,
                "temperature": 0.2,
                "messages": [{"role": "user", "content": prompt}]
            })
            resp = bedrock.invoke_model(modelId=model_id, body=body)
            raw = resp["body"].read().decode("utf-8")
            data = json.loads(raw)
            # Claude on bedrock returns content list
            text = ""
            if isinstance(data.get("content"), list) and data["content"]:
                text = data["content"][0].get("text","")
            else:
                text = raw
        plan = json.loads(text)
        if plan.get("action") not in allowed_actions:
            raise ValueError("LLM returned disallowed action")
        return plan
    except Exception:
        # fallback heuristic
        p = _choose_action_heuristic(bundle, allowed)
        p.update({"risk": "low", "rationale": "Fallback heuristic plan."})
        p.setdefault("target", {}).setdefault("service", bundle.get("service","demo-service"))
        p.setdefault("target", {}).setdefault("env", bundle.get("env","staging"))
        return p

def _patch_replicas_kustomize(kustomize_text: str, new_replicas: int) -> str:
    lines = kustomize_text.splitlines()
    out = []
    replaced = False
    for ln in lines:
        if (not replaced) and re.match(r'^\s*value:\s*\d+\s*$', ln):
            out.append(re.sub(r'(\s*value:\s*)\d+', r'\g<1>'+str(new_replicas), ln))
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        raise ValueError("Could not locate replicas value line to patch.")
    return "\n".join(out) + "\n"

def _patch_image_deployment(deploy_yaml: str, new_tag: str) -> str:
    # naive image tag patch; for POC only
    return re.sub(r'(image:\s+\S+?:)([^\s]+)', r'\g<1>'+new_tag, deploy_yaml)

def handler(event, context):
    """
    Triggered by EventBridge on SignalBundled.
    Reads incident bundle from S3, proposes remediation, opens PR.
    """
    detail = event.get("detail", {})
    bucket = detail["s3_bucket"]
    key = detail["s3_key"]
    bundle = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8"))

    token = _get_github_token()
    allowed = _fetch_allowed_actions(token, ref="main")

    plan = _llm_plan(bundle, allowed)
    action = plan["action"]
    env = (plan.get("target") or {}).get("env") or bundle.get("env","staging")
    service = (plan.get("target") or {}).get("service") or bundle.get("service","demo-service")

    branch = f"ai/{bundle['incident_id']}-{action}"
    base_branch = "main"
    pr_title = f"[AI] {bundle['incident_id']}: {action} for {service} ({env})"
    pr_body = f"""## Incident
- Incident ID: `{bundle['incident_id']}`
- Bundle: s3://{bucket}/{key}

## Proposed remediation
- Action: `{action}`
- Target: `{service}` ({env})
- Params: `{json.dumps(plan.get('params',{}))}`
- Risk: `{plan.get('risk','low')}`

## Rationale
{plan.get('rationale','')}

## Guardrails
- Git-only change (no direct cluster writes)
- CI + policy checks required before merge
- Admission control enforced by Gatekeeper (if installed)

## Rollback
Revert this PR.
"""

    base_sha = _get_ref_sha(GITHUB_OWNER, GITHUB_REPO, f"heads/{base_branch}", token)
    try:
        _create_branch(GITHUB_OWNER, GITHUB_REPO, branch, base_sha, token)
    except Exception:
        pass

    changes = []
    if action == "scale_replicas":
        target_path = f"gitops/apps/demo-service/overlays/{env}/kustomization.yaml"
        file_obj = _get_file(GITHUB_OWNER, GITHUB_REPO, target_path, base_branch, token)
        original = base64.b64decode(file_obj["content"]).decode("utf-8")
        replicas = int(plan.get("params", {}).get("replicas", 3))
        patched = _patch_replicas_kustomize(original, replicas).encode("utf-8")
        _put_file(GITHUB_OWNER, GITHUB_REPO, target_path, f"[AI] {bundle['incident_id']}: scale replicas", patched, file_obj["sha"], branch, token)
        changes.append(target_path)

    elif action == "rollback_image":
        # For POC, rollback means set image tag to a known tag in base deployment
        tag = plan.get("params", {}).get("tag", "previous")
        deploy_path = "gitops/apps/demo-service/base/deployment.yaml"
        file_obj = _get_file(GITHUB_OWNER, GITHUB_REPO, deploy_path, base_branch, token)
        original = base64.b64decode(file_obj["content"]).decode("utf-8")
        # keep repo/image the same, only swap tag portion if present
        patched = re.sub(r'(image:\s+[\w\.\-\/]+:)[^\s]+', r'\g<1>'+tag, original).encode("utf-8")
        _put_file(GITHUB_OWNER, GITHUB_REPO, deploy_path, f"[AI] {bundle['incident_id']}: rollback image", patched, file_obj["sha"], branch, token)
        changes.append(deploy_path)

    elif action == "tune_resources":
        # POC: bump memory limit in base deployment (bounded by policy via CI/Gatekeeper in real impl)
        deploy_path = "gitops/apps/demo-service/base/deployment.yaml"
        file_obj = _get_file(GITHUB_OWNER, GITHUB_REPO, deploy_path, base_branch, token)
        original = base64.b64decode(file_obj["content"]).decode("utf-8")
        # naive patch: replace memory limit 512Mi -> 768Mi
        patched = original.replace('memory: "512Mi"', 'memory: "768Mi"').encode("utf-8")
        _put_file(GITHUB_OWNER, GITHUB_REPO, deploy_path, f"[AI] {bundle['incident_id']}: tune resources", patched, file_obj["sha"], branch, token)
        changes.append(deploy_path)

    elif action == "restart_rollout":
        # POC: add an annotation change by touching deployment file
        deploy_path = "gitops/apps/demo-service/base/deployment.yaml"
        file_obj = _get_file(GITHUB_OWNER, GITHUB_REPO, deploy_path, base_branch, token)
        original = base64.b64decode(file_obj["content"]).decode("utf-8")
        stamp = str(int(time.time()))
        if "metadata:" in original and "annotations:" not in original:
            patched = original.replace("metadata:\n", f"metadata:\n  annotations:\n    ai.gitops/restartAt: \"{stamp}\"\n")
        else:
            patched = original + f"\n# ai.gitops/restartAt: {stamp}\n"
        _put_file(GITHUB_OWNER, GITHUB_REPO, deploy_path, f"[AI] {bundle['incident_id']}: restart rollout", patched.encode("utf-8"), file_obj["sha"], branch, token)
        changes.append(deploy_path)

    pr = _open_pr(GITHUB_OWNER, GITHUB_REPO, pr_title, pr_body, head=branch, base=base_branch, token=token)

    return {"statusCode": 200, "body": json.dumps({
        "message": "PR opened",
        "incident_id": bundle["incident_id"],
        "action": action,
        "changed_files": changes,
        "pr_number": pr.get("number"),
        "pr_url": pr.get("html_url")
    })}
