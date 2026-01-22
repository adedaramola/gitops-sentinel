# AWS-Native AI-Powered GitOps Self-Healing Platform (Option B POC)

This repository is a **complete POC blueprint** for an AI-powered GitOps self-healing loop on AWS:

**EKS + Prometheus/Alertmanager + EventBridge + Lambda (Bundler/Agent/Verifier) + GitHub PRs + Argo CD reconcile + Guardrails**

## What you get
- Terraform skeleton to deploy:
  - EKS (placeholder module)
  - Argo CD (Helm)
  - kube-prometheus-stack (Helm)
  - OPA Gatekeeper (Helm)
  - EventBridge bus + rules
  - S3 incident bundle bucket
  - Lambda functions (Bundler, Agent, Verifier)
  - Secrets Manager wiring
  - IAM least-privilege roles
- GitOps repo structure (Kustomize) + demo service
- Sample Prometheus alert rules
- GitHub Actions validation workflow
- Allowed-actions contract + policy placeholders

## Safety model
- The AI agent **never writes to EKS**.
- The agent **only proposes changes via GitHub PR**.
- CI + Gatekeeper enforce constraints before changes reach the cluster.

## Quickstart (conceptual)
1. Deploy infra with Terraform (see `terraform/`)
2. Install Argo CD and point it at `gitops/clusters/staging`
3. Deploy Prometheus/Alertmanager + alert rules
4. Configure Alertmanager webhook → API Gateway (or direct) → EventBridge
5. Trigger an alert; verify:
   - Bundler writes `s3://<bucket>/incidents/<id>.json`
   - Agent opens GitHub PR
   - CI validates
   - Merge → Argo CD syncs
   - Verifier confirms recovery and posts notification

## Next
This is a scaffold intended to be customized for your AWS accounts, repos, and security requirements.
