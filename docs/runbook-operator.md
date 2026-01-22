# Operator Runbook (POC)

## Deploy
1. `cd terraform && terraform init && terraform apply`
2. Record outputs:
   - `webhook_url`
   - `incident_bucket_name`
   - `event_bus_name`
   - `incident_table_name`

## Configure Argo CD Applications
Update repoURL in:
- `gitops/argocd/application-staging.yaml`
- `gitops/argocd/application-prod.yaml`

Apply:
```bash
kubectl apply -n argocd -f gitops/argocd/application-staging.yaml
kubectl apply -n argocd -f gitops/argocd/application-prod.yaml
```

## Configure Alertmanager webhook
See `docs/alertmanager-webhook.md` and set:
- receiver webhook URL = Terraform `webhook_url`

## Validate the loop
- Trigger a test alert (or reduce thresholds)
- Confirm:
  - Bundler writes `s3://<bucket>/incidents/inc-...json`
  - Agent opens a PR
  - CI passes
  - Merge PR
  - Argo syncs
  - Verifier posts result + (optional) revert PR on failure

## Common failure modes
- Agent can't open PR → check GitHub token secret format and permissions
- Verifier can't query Prometheus → set `prometheus_query_url` and ensure network reachability
- Gatekeeper rejects change → expected; adjust playbook within allowed-actions bounds
