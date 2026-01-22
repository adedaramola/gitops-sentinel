# Terraform Notes (Tightened)

This version includes deploy-ready VPC + EKS using registry modules:
- terraform-aws-modules/vpc/aws
- terraform-aws-modules/eks/aws

It also wires the Kubernetes and Helm providers using EKS outputs, and installs:
- Argo CD
- kube-prometheus-stack
- Gatekeeper

Additionally:
- API Gateway HTTP API exposes `/webhook` to receive Alertmanager POSTs
- Lambda permissions allow API GW and EventBridge to invoke lambdas
- The Agent Lambda includes a working GitHub PR creation path (branch + commit + PR) that patches staging replicas

## GitHub token secret format
Store JSON in Secrets Manager:
```json
{ "token": "ghp_..." }
```

## Important
- For production, replace token with a GitHub App installation token flow.
- Add branch protection and required checks before allowing auto-merge.
