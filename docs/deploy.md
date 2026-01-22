# Deploy (Option B Tightened)

## Prereqs
- Terraform >= 1.6
- AWS credentials configured
- GitHub repo created (this repo)
- A GitHub token stored in Secrets Manager as JSON: `{ "token": "ghp_..." }`

## Steps
1. Create `terraform/terraform.tfvars` from `terraform/terraform.tfvars.example` with:
   - github_owner, github_repo, github_token_secret_arn
   - aws_region, cluster_name (optional)
2. Run:
   ```bash
   cd terraform
   terraform init
   terraform apply
   ```
3. Install Argo CD Applications:
   - Update repoURL in `gitops/argocd/application-staging.yaml` and `application-prod.yaml`
   - Apply them:
     ```bash
     kubectl apply -n argocd -f gitops/argocd/application-staging.yaml
     kubectl apply -n argocd -f gitops/argocd/application-prod.yaml
     ```
4. Configure Alertmanager webhook using `webhook_url` output (see `docs/alertmanager-webhook.md`)
5. Trigger an alert; verify:
   - S3 incident bundle is created
   - GitHub PR is opened by the Agent Lambda


## Optional: Prometheus query URL
Set `prometheus_query_url` in `terraform.tfvars` if you have a reachable Prometheus query endpoint.

## GitHub Actions -> AWS (for verifier trigger)
To emit `RemediationApplied` events on merge, set these GitHub repo secrets:
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY
- AWS_REGION

The workflow `Notify Remediation Applied` extracts the incident id from the merge commit message and puts an EventBridge event that triggers the verifier.


## Apply GitOps policies
This repo includes Gatekeeper constraints and the allowed-actions contract under `gitops/policies/`.
Both staging and prod cluster kustomizations include `../../policies`.
