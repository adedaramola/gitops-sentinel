# Lambdas

## incident_bundler
- Receives Alertmanager webhook payload (via API Gateway)
- Deduplicates incidents (DynamoDB TTL window)
- Collects context:
  - Prometheus snapshot queries (optional)
  - Kubernetes events/deployment status (optional, read-only)
- Writes incident bundle to S3
- Emits EventBridge `IncidentBundleCreated`

## llm_agent
- Reads incident bundle from S3
- Loads allowed-actions contract from repo
- Chooses a remediation (Bedrock by default; OpenAI optional)
- Applies a small, bounded patch to GitOps repo and opens a PR

## verifier
- Triggered by `RemediationApplied` event
- Checks recovery via PromQL
- Emits Verified/Failed
- Optional Slack notify
- Optional auto-revert PR on failure
