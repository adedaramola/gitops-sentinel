# GitOps Sentinel — Operator Runbook

## Deploy
```bash
cd terraform && terraform init && terraform apply -var-file=terraform.tfvars
```

Record outputs:
- `webhook_url` — configure in Alertmanager receiver
- `signals_bucket_name` — S3 bucket for signal bundles
- `event_bus_name` — EventBridge custom bus
- `signals_table_name` — DynamoDB dedup table

## Configure Argo CD Applications
Update `repoURL` in:
- `gitops/argocd/application-staging.yaml`
- `gitops/argocd/application-prod.yaml`

```bash
kubectl apply -n argocd -f gitops/argocd/application-staging.yaml
kubectl apply -n argocd -f gitops/argocd/application-prod.yaml
```

## Configure Alertmanager webhook
See `docs/alertmanager-webhook.md` and set:
- receiver webhook URL = Terraform `webhook_url` output

## Validate the full loop
1. Trigger a test alert (or lower thresholds temporarily)
2. Confirm:
   - Signal Collector writes `s3://<bucket>/incidents/inc-*.json`
   - Decision Engine (or Sentinel Pipeline) opens a GitHub PR
   - CI passes on the PR
   - Merge PR → Argo CD syncs cluster
   - Outcome Validator queries Prometheus and emits `OutcomeValidated`
   - DynamoDB Audit Log has entries for `action_dispatched` and `outcome_validated`

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Decision Engine can't open PR | GitHub token secret wrong format or missing permissions | Check secret JSON: `{ "token": "ghp_..." }`, ensure `contents:write` + `pull_requests:write` |
| Outcome Validator skips Prometheus check | `PROMETHEUS_QUERY_URL` not set | Set `prometheus_query_url` in tfvars and redeploy |
| Gatekeeper rejects change | Action outside `allowed-actions.yaml` bounds | Expected — add action to the allowed list if intentional |
| Signal dedup suppressing alerts | DynamoDB TTL not expired (30-min window) | Wait for TTL or manually delete the dedup record |
| Step Functions pipeline stuck | Agent Lambda timeout | Check X-Ray trace for which state timed out; increase timeout or check Bedrock throttling |
