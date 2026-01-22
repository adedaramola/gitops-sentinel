# Step 4 — Final (AWS-Native Option B POC)

This repository implements an AWS-native AI-powered GitOps **self-healing** proof of concept with:

- **EKS** (apps runtime)
- **kube-prometheus-stack** (Prometheus + Alertmanager)
- **Argo CD** (GitOps reconciliation)
- **EventBridge** (incident/event routing)
- **Lambda** (Bundler → Agent → Verifier)
- **Bedrock/OpenAI** (optional, constrained reasoning)
- **Gatekeeper** (admission control guardrails)
- **DynamoDB** (incident dedup/correlation)
- **S3** (incident bundles / evidence)

## End-to-end flow
1. **Alert fires** (Alertmanager)
2. Alert webhook → **API Gateway** `POST /webhook`
3. Bundler Lambda enriches context (Prometheus snapshots + optional k8s read-only) and writes **incident bundle** to S3
4. Bundler emits `IncidentBundleCreated` on **EventBridge**
5. Agent Lambda reads incident bundle + allowed-actions contract → selects a safe remediation → opens **GitHub PR**
6. GitHub Actions validates manifests/policies
7. Merge PR → Argo CD reconciles changes to EKS
8. GitHub Action emits `RemediationApplied` event to EventBridge
9. Verifier Lambda checks recovery via PromQL:
   - emits `RemediationVerified` or `RemediationFailed`
   - optional Slack notify
   - optional **auto-revert PR** on failure

## What’s intentionally POC-grade
- Prometheus query auth is simplified (production AMP requires SigV4 signing)
- Agent uses lightweight playbooks (extendable)
- API Gateway auth is not enforced by default (add WAF/JWT/API key in prod)

## Where to look
- `terraform/` — deploy infra
- `lambdas/` — bundler/agent/verifier
- `gitops/` — kustomize base/overlays, policies, Argo apps
- `.github/workflows/` — CI + remediation applied notifier

