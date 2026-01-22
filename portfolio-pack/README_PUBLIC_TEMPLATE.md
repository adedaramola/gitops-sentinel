# AI-Powered GitOps Self-Healing Platform (AWS-native)

A safe-by-default, AWS-native self-healing POC that turns production alerts into **constrained GitOps pull requests**, enforces guardrails with **CI + Gatekeeper**, and verifies recovery with **PromQL**—optionally opening an **auto-revert PR** on failure.

> **Key principle:** AI never writes directly to the cluster. It proposes PRs only.

## Architecture
![Architecture Diagram](assets/architecture.png)

**Core components**
- EKS + Argo CD (GitOps reconciliation)
- Prometheus/Alertmanager (signals)
- API Gateway → Lambda Bundler (incident context)
- EventBridge (routing)
- Lambda Agent (PR creation; Bedrock/OpenAI optional)
- Lambda Verifier (PromQL check; optional revert PR + Slack)
- DynamoDB (dedup/correlation), S3 (incident bundles)

## End-to-end flow
1) Alert fires → POST /webhook  
2) Bundler enriches + writes S3 bundle → emits `IncidentBundleCreated`  
3) Agent reads bundle + allowed-actions → opens PR  
4) Merge PR → Argo CD applies  
5) Workflow emits `RemediationApplied`  
6) Verifier checks recovery → Verified/Failed (+ optional auto-revert PR)

## Guardrails
- Allowed actions contract: `gitops/policies/allowed-actions.yaml`
- CI checks: kustomize build + policy-check workflow
- Gatekeeper bounds: `gitops/policies/gatekeeper/*`

## Quickstart
1. Create `terraform/terraform.tfvars` from `terraform/terraform.tfvars.example`
2. `cd terraform && terraform init && terraform apply`
3. Update repoURL in `gitops/argocd/application-*.yaml` and apply
4. Configure Alertmanager webhook with Terraform output `webhook_url`
5. Trigger an alert and watch the PR appear

## Demo
See `docs/demo.md` and `docs/runbook.md`.

## Tradeoffs
- POC: Prometheus auth simplified; AMP needs SigV4
- Use GitHub App auth in production (avoid PAT)

## License
MIT
