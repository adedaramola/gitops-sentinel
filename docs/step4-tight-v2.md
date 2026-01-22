# Step 4 Tightening v2

This version adds:
- Enriched incident bundling:
  - Optional Prometheus snapshot queries via `PROMETHEUS_QUERY_URL`
  - Optional EKS Kubernetes API read-only enrichment (events + deployment status)
- LLM agent improvements:
  - Fetches allowed-actions contract from the repo
  - Uses Bedrock (default) or OpenAI (optional) to select an action
  - Applies one of the supported playbook-style changes and opens a PR
- Verification improvements:
  - Verifier queries Prometheus for a recovery condition and emits a verified/failed event
  - Optional Slack notification
- GitHub merge signal:
  - Workflow posts `RemediationApplied` event to EventBridge on push to main by extracting the incident id from commit message
