# GitOps Sentinel — Demo Script

## Goal
Show an end-to-end confidence-gated remediation loop — the system reasons about the incident, scores its confidence, and takes action **without** giving any agent direct cluster write access.

## 5-minute narrative

1. **Show dashboards** — Prometheus/Grafana, highlight a high error rate alert
2. **Show webhook endpoint** — `webhook_url` from Terraform output, point to API Gateway
3. **Trigger a simulated alert** — POST to the webhook (or fire a real Alertmanager alert)
4. **Show Signal Collector output** — open the S3 signal bundle JSON, highlight enriched context (Prometheus metrics, k8s events)
5. **Show Sentinel Pipeline execution** — Step Functions console, each agent state, confidence score output from Confidence Scorer
6. **Show RouteByConfidence decision** — highlight which path was taken (auto_apply / open_pr / escalate) and why
7. **Show GitHub PR** — created by Decision Engine or Action Planner, point to `allowed-actions.yaml` constraints
8. **Merge PR → Argo CD syncs** — show Argo CD UI reconciling the cluster
9. **Show Outcome Validator** — Prometheus health check result, `OutcomeValidated` event, DynamoDB Audit Log entry

## Key talking points
- GitOps is the execution engine; the agent pipeline is the reasoning engine
- **Confidence-gated routing** means the system knows when it's sure enough to act autonomously
- Gatekeeper + CI = hard safety rails — no agent can push a change Gatekeeper rejects
- DynamoDB dedup prevents alert storms from triggering duplicate remediations
- Rollback is automated via revert PR, not imperative cluster writes
- Every decision is recorded in the DynamoDB Audit Log with full traceability
