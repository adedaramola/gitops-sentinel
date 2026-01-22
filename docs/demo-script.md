# Demo Script (Step 4)

## Goal
Show an end-to-end autonomous remediation loop **without** giving the agent direct cluster write access.

## 5-minute narrative
1. Show dashboards/alerts (Prometheus/Grafana)
2. Show API Gateway webhook endpoint (Terraform output)
3. Trigger a simulated alert
4. Open S3 incident bundle and show enriched context
5. Show GitHub PR created by agent (explain guardrails + allowed-actions)
6. Merge PR → Argo CD sync to EKS
7. Verifier checks PromQL and posts status (and revert PR on failure)

## Talking points
- GitOps is the execution engine; agent is the reasoning engine
- Gatekeeper + CI = hard safety rails
- DynamoDB dedup prevents alert storms
- Rollback is automated via revert PR, not imperative cluster writes
