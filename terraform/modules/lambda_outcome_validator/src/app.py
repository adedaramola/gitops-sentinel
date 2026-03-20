import json, os, time, re, base64
import boto3
import requests

events = boto3.client("events")
secrets = boto3.client("secretsmanager")

EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME", "")
PROM_URL = os.environ.get("PROMETHEUS_QUERY_URL", "")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

# GitHub for rollback PR
GITHUB_API = "https://api.github.com"
GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN_SECRET_ARN = os.environ.get("GITHUB_APP_TOKEN_SECRET_ARN", "")

AUTO_REVERT_ON_FAIL = os.environ.get("AUTO_REVERT_ON_FAIL", "true").lower() == "true"

def _get_secret_json(arn: str) -> dict:
    sec = secrets.get_secret_value(SecretId=arn)
    payload = sec.get("SecretString") or "{}"
    return json.loads(payload)

def _gh_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def _gh(method, path, token, **kwargs):
    url = f"{GITHUB_API}{path}"
    r = requests.request(method, url, headers=_gh_headers(token), timeout=30, **kwargs)
    if r.status_code >= 400:
        raise RuntimeError(f"GitHub API error {r.status_code}: {r.text}")
    return r.json() if r.text else {}

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

def _emit(detail_type, detail):
    if not EVENT_BUS_NAME:
        return
    events.put_events(Entries=[{
        "EventBusName": EVENT_BUS_NAME,
        "Source": "gitops.sentinel",
        "DetailType": detail_type,
        "Detail": json.dumps(detail)
    }])

def _slack(msg: str):
    if not SLACK_WEBHOOK_URL:
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, timeout=10).raise_for_status()
    except Exception:
        pass

def _extract_incident_id(detail: dict):
    return detail.get("incident_id") or detail.get("inc") or "unknown"

def _find_ai_pr_for_incident(token: str, incident_id: str):
    # Search PRs by incident id in title/body
    q = f'repo:{GITHUB_OWNER}/{GITHUB_REPO} "{incident_id}" in:title type:pr'
    res = _gh("GET", "/search/issues", token, params={"q": q})
    items = res.get("items", [])
    if not items:
        return None
    # choose most recent
    items.sort(key=lambda x: x.get("created_at",""), reverse=True)
    return items[0]

def _get_pr_files(token: str, pr_number: int):
    files = []
    page = 1
    while True:
        res = requests.get(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls/{pr_number}/files",
                           headers=_gh_headers(token), params={"per_page": 100, "page": page}, timeout=30)
        res.raise_for_status()
        batch = res.json()
        if not batch:
            break
        files.extend(batch)
        page += 1
    return files

def _get_ref_sha(token: str, ref: str):
    data = _gh("GET", f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/ref/{ref}", token)
    return data["object"]["sha"]

def _create_branch(token: str, branch: str, base_sha: str):
    return _gh("POST", f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/refs", token, json={
        "ref": f"refs/heads/{branch}",
        "sha": base_sha
    })

def _get_file(token: str, path: str, ref: str):
    return _gh("GET", f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}", token, params={"ref": ref})

def _put_file(token: str, path: str, message: str, content_bytes: bytes, sha: str, branch: str):
    return _gh("PUT", f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}", token, json={
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
        "sha": sha,
        "branch": branch
    })

def _open_pr(token: str, title: str, body: str, head: str, base: str):
    return _gh("POST", f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls", token, json={
        "title": title,
        "body": body,
        "head": head,
        "base": base
    })

def _auto_revert(token: str, incident_id: str):
    pr_item = _find_ai_pr_for_incident(token, incident_id)
    if not pr_item:
        return {"skipped": True, "reason": "no_pr_found"}

    pr_number = pr_item["number"]
    pr = _gh("GET", f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls/{pr_number}", token)
    base_branch = pr["base"]["ref"]
    base_sha = _get_ref_sha(token, f"heads/{base_branch}")

    branch = f"ai/revert-{incident_id}"
    try:
        _create_branch(token, branch, base_sha)
    except Exception:
        pass

    files = _get_pr_files(token, pr_number)
    changed_paths = [f["filename"] for f in files if f.get("status") in ("modified","added","removed")]

    # Restore each file to the content from base branch (current base branch state).
    restored = []
    for path in changed_paths:
        try:
            base_obj = _get_file(token, path, base_branch)
            base_content = base64.b64decode(base_obj["content"])
            # Get current sha in branch (might not exist if file was added)
            try:
                cur_obj = _get_file(token, path, branch)
                cur_sha = cur_obj["sha"]
            except Exception:
                # If file was added in AI PR, deleting would be ideal; POC: overwrite with base if exists
                cur_sha = None

            if cur_sha:
                _put_file(token, path, f"[AI] revert {incident_id}: restore {path}", base_content, cur_sha, branch)
            else:
                # create file with base content
                _gh("PUT", f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}", token, json={
                    "message": f"[AI] revert {incident_id}: restore {path}",
                    "content": base64.b64encode(base_content).decode("utf-8"),
                    "branch": branch
                })
            restored.append(path)
        except Exception:
            continue

    title = f"[AI] Revert remediation for {incident_id}"
    body = f"""Verifier detected remediation failure for `{incident_id}`.

This PR restores files changed by the AI remediation PR #{pr_number} back to `{base_branch}` state.

Restored paths:
- """ + "\n- ".join(restored)

    revert_pr = _open_pr(token, title, body, head=branch, base=base_branch)
    return {"revert_pr_url": revert_pr.get("html_url"), "revert_pr_number": revert_pr.get("number"), "restored": restored}

def handler(event, context):
    detail = event.get("detail", {}) if isinstance(event, dict) else {}
    incident_id = _extract_incident_id(detail)
    service = detail.get("service", "demo-service")

    err = _prom_query(f'sum(rate(http_requests_total{{service="{service}",status=~"5.."}}[5m]))')
    recovered = False
    try:
        res = (err.get("data") or {}).get("result") or []
        if res and "value" in res[0]:
            val = float(res[0]["value"][1])
            recovered = val < 0.2
        else:
            recovered = False
    except Exception:
        recovered = False

    status = "OutcomeValidated" if recovered else "OutcomeFailed"

    revert_result = None
    if (not recovered) and AUTO_REVERT_ON_FAIL and GITHUB_OWNER and GITHUB_REPO and GITHUB_TOKEN_SECRET_ARN:
        try:
            token = _get_secret_json(GITHUB_TOKEN_SECRET_ARN)["token"]
            revert_result = _auto_revert(token, incident_id)
        except Exception as e:
            revert_result = {"error": str(e)}

    payload = {"incident_id": incident_id, "service": service, "recovered": recovered, "prometheus": err, "revert": revert_result}
    _emit(status, payload)

    msg = f"[AI-GitOps] {status} incident={incident_id} service={service} recovered={recovered}"
    if revert_result and revert_result.get("revert_pr_url"):
        msg += f" | Revert PR: {revert_result['revert_pr_url']}"
    _slack(msg)

    return {"statusCode": 200, "body": json.dumps(payload)}
