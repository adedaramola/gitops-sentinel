# GitOps Sentinel — Mid-Level Developer Implementation Guide

This guide assumes you are comfortable with AWS, Kubernetes, Python, and Terraform. Steps are concise — the focus is on architecture decisions, customisation points, and production considerations rather than hand-holding through CLI basics.

---

## System Design

### Signal Flow

```
Alertmanager
    │  POST /webhook (HMAC-signed)
    ▼
API Gateway (HTTP API)
    │
    ▼
Signal Collector Lambda
    ├── HMAC validation (X-Webhook-Secret header)
    ├── DynamoDB conditional write (dedup — 30-min TTL window)
    ├── Prometheus snapshot queries (optional enrichment)
    ├── EKS read-only k8s events (optional enrichment)
    ├── S3 PUT  →  incidents/<incident_id>.json
    └── EventBridge PUT
            ├── SignalBundled         →  Decision Engine Lambda (single-agent path)
            └── SentinelPipelineTriggered  →  Step Functions (multi-agent path)

Decision Engine Lambda (single-agent)
    ├── Reads signal bundle from S3
    ├── Fetches allowed-actions.yaml from GitHub
    ├── Calls Bedrock (Claude Haiku) or falls back to heuristic
    ├── Checks for existing PR (idempotency)
    ├── Opens GitHub PR with patch
    └── Writes action_dispatched record to DynamoDB Audit Log

Step Functions — Sentinel Pipeline (multi-agent)
    ├── ClassifierAgent   →  severity, blast radius, key signals
    ├── RootCauseAgent    →  LLM root cause + confidence score (0–100)
    ├── ActionPlanner     →  proposed action + alternatives
    ├── ConfidenceScorer  →  deterministic scoring + penalty model
    └── RouteByConfidence
            ├── ≥80 + low risk  →  auto_apply  (merge PR automatically)
            ├── 40–79           →  open_pr     (human review)
            └── <40             →  escalate    (PagerDuty / Slack)

GitHub Actions (on PR merge to main)
    └── notify-action-dispatched.yaml
            └── EventBridge PUT ActionDispatched

Outcome Validator Lambda
    ├── PromQL query  →  error rate < 20% threshold?
    ├── OutcomeValidated  →  success path
    └── OutcomeFailed     →  opens revert PR automatically
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| GitOps as execution engine | No agent ever writes directly to the cluster. All changes are auditable, reversible Git commits |
| Confidence-gated routing | System knows when it is certain enough to act autonomously vs when to ask a human |
| DynamoDB dedup | Prevents alert storms from triggering N identical remediations for the same incident |
| Heuristic fallback | If Bedrock is unavailable or returns an invalid response, a deterministic fallback runs — the system degrades gracefully |
| GitHub App token cache | Token refreshed every 5 minutes via Secrets Manager — avoids per-invocation API calls |
| Separate IAM roles per Lambda | Least-privilege; each function only has the permissions it needs |

---

## Repository Layout

```
.
├── lambdas/
│   ├── signal_collector/app.py      # Webhook receiver, dedup, enrichment
│   ├── decision_engine/app.py       # LLM plan + PR creation
│   ├── outcome_validator/app.py     # PromQL check + revert PR
│   ├── classifier_agent/app.py      # Step Functions: incident classification
│   ├── root_cause_agent/app.py      # Step Functions: LLM root cause
│   ├── action_planner/app.py        # Step Functions: action proposal
│   ├── confidence_scorer/app.py     # Step Functions: deterministic scoring
│   ├── requirements.txt
│   └── tests/                       # 33 unit tests, full stub isolation
│
├── terraform/
│   ├── main.tf                      # Root module — wires everything together
│   ├── variables.tf
│   ├── outputs.tf
│   ├── terraform.tfvars.example
│   └── modules/
│       ├── lambda_signal_collector/
│       ├── lambda_decision_engine/
│       ├── lambda_outcome_validator/
│       ├── lambda_classifier_agent/
│       ├── lambda_root_cause_agent/
│       ├── lambda_action_planner/
│       ├── lambda_confidence_scorer/
│       ├── dynamodb_audit_log/
│       ├── dynamodb_incidents/
│       ├── eventbridge/
│       ├── eventbridge_rules/
│       ├── iam/                     # All Lambda + SFN roles in one module
│       ├── step_functions/
│       ├── apigw_webhook/
│       ├── s3_incidents/
│       ├── argocd/
│       ├── gatekeeper/
│       └── observability/
│
├── gitops/
│   ├── apps/demo-service/
│   │   ├── base/                    # deployment.yaml, service.yaml
│   │   └── overlays/{staging,prod}/ # kustomize patches
│   ├── clusters/{staging,prod}/     # top-level kustomizations
│   ├── policies/
│   │   ├── allowed-actions.yaml     # contract read by Decision Engine
│   │   └── gatekeeper/              # OPA ConstraintTemplate + Constraint
│   └── argocd/
│       ├── application-staging.yaml
│       └── application-prod.yaml
│
└── .github/workflows/
    ├── validate-pr.yaml             # kustomize build + pytest on PRs
    ├── policy-check.yaml            # enforce allowed-actions bounds
    └── notify-action-dispatched.yaml # fires ActionDispatched to EventBridge on merge
```

---

## Prerequisites

- AWS CLI v2, configured with sufficient IAM permissions
- Terraform >= 1.5
- kubectl >= 1.28, Helm >= 3.12
- Argo CD CLI (`brew install argocd`)
- GitHub CLI (`brew install gh`)
- Python 3.11
- Helm repos added:
  ```bash
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
  helm repo update
  ```

---

## Deployment

### 1. Fork the repo

Fork `adedaramola/gitops-sentinel` to your GitHub account. The Decision Engine writes PRs to this repo — it must be yours.

Update Argo CD app manifests:
```bash
sed -i '' 's|adedaramola/gitops-sentinel|YOUR_USERNAME/gitops-sentinel|g' \
  gitops/argocd/application-staging.yaml \
  gitops/argocd/application-prod.yaml
git add gitops/argocd/ && git commit -m "configure argocd repo url" && git push
```

### 2. Create GitHub PAT

Classic PAT with `repo` scope. Store in Secrets Manager:

```bash
aws secretsmanager create-secret \
  --name "gitops-sentinel/github-token" \
  --secret-string '{"token":"ghp_YOUR_TOKEN"}' \
  --region us-east-1
```

Note the returned ARN.

### 3. Bundle Lambda dependencies

Terraform archives each Lambda's `src/` directory as-is. Dependencies must be co-located:

```bash
for mod in lambda_signal_collector lambda_decision_engine lambda_outcome_validator; do
  pip install requests PyYAML --quiet --target "terraform/modules/$mod/src/"
done
```

> **Production note:** Replace this with a proper build pipeline — a `null_resource` with `local-exec` in each Terraform module, or a Lambda Layer for shared deps. The manual install approach works for development but is fragile in CI.

### 4. Create `terraform/terraform.tfvars`

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```

Minimum required values:

```hcl
aws_region              = "us-east-1"
project_name            = "gitops-sentinel"
cluster_name            = "gitops-sentinel-cluster"
github_owner            = "YOUR_USERNAME"
github_repo             = "gitops-sentinel"
github_token_secret_arn = "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:gitops-sentinel/github-token-xxxxxx"
model_provider          = "bedrock"
vpc_cidr                = "10.20.0.0/16"
az_count                = 2
webhook_secret          = "$(openssl rand -hex 32)"  # replace with actual value
enable_multi_agent      = true
```

### 5. Deploy

```bash
cd terraform
terraform init
terraform apply -auto-approve
```

EKS provisioning takes ~10 minutes. On completion you'll have the `webhook_url` and all other outputs.

**Known issue:** Helm installs (Argo CD, Gatekeeper, observability) may fail on the first apply because the Kubernetes API is not yet reachable when Terraform's Helm provider initialises. Fix:

```bash
aws eks update-kubeconfig --name gitops-sentinel-cluster --region us-east-1
terraform apply -auto-approve   # second run succeeds
```

### 6. Configure Argo CD

```bash
# Get admin password
kubectl get secret argocd-initial-admin-secret -n argocd \
  -o jsonpath="{.data.password}" | base64 -d

# Port-forward and login
kubectl port-forward svc/argo-cd-argocd-server -n argocd 8080:443 &
argocd login localhost:8080 --username admin --password <PASSWORD> --insecure

# Register repo (public repo — no credentials needed)
argocd repo add https://github.com/YOUR_USERNAME/gitops-sentinel.git --insecure

# Create namespace and apply apps
kubectl create namespace demo

# Apply ConstraintTemplate before Constraint (Gatekeeper CRD ordering)
argocd app sync demo-staging \
  --resource templates.gatekeeper.sh:ConstraintTemplate:k8sdeploymentbounds

argocd app sync demo-staging
argocd app sync demo-prod
```

### 7. GitHub Actions secrets

In your repo → Settings → Secrets → Actions, add:

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | Your AWS key |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret |
| `AWS_REGION` | `us-east-1` |
| `AWS_EVENT_BUS_NAME` | `gitops-sentinel-bus` |

---

## Testing the Pipeline

### Fire a test alert

```bash
WEBHOOK_URL="<from terraform output>"
SECRET="<webhook_secret from tfvars>"

curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: $SECRET" \
  -d '{
    "receiver":"sentinel-webhook","status":"firing",
    "alerts":[{
      "status":"firing",
      "labels":{"alertname":"HighErrorRate","severity":"critical",
                "service":"demo-service","namespace":"demo","env":"staging"},
      "annotations":{"summary":"High error rate on demo-service"},
      "startsAt":"2026-01-01T00:00:00Z","endsAt":"0001-01-01T00:00:00Z",
      "generatorURL":"http://prometheus:9090/graph"
    }],
    "groupLabels":{"alertname":"HighErrorRate"},
    "commonLabels":{"alertname":"HighErrorRate","severity":"critical",
                    "service":"demo-service","env":"staging"},
    "commonAnnotations":{"summary":"High error rate on demo-service"},
    "externalURL":"http://alertmanager:9093","version":"4",
    "groupKey":"{}/{alertname=~\"HighErrorRate\"}:{alertname=\"HighErrorRate\"}"
  }' | jq .
```

**Important:** Always include `"env":"staging"` in the alert labels. The Decision Engine uses this to build the correct kustomize overlay path (`gitops/apps/demo-service/overlays/{env}/kustomization.yaml`). Without it the path becomes `overlays/unknown/` which does not exist.

### Observe each stage

```bash
# Signal Collector
aws logs tail /aws/lambda/gitops-sentinel-signal-collector --since 5m --format short

# Decision Engine
aws logs tail /aws/lambda/gitops-sentinel-decision-engine --since 5m --format short

# PRs opened
gh pr list --repo YOUR_USERNAME/gitops-sentinel --state open

# After merging PR — replica count
kubectl get deployment demo-service -n demo -o jsonpath='{.spec.replicas}'

# Outcome Validator
aws logs tail /aws/lambda/gitops-sentinel-outcome-validator --since 10m --format short

# DynamoDB Audit Log
aws dynamodb scan \
  --table-name gitops-sentinel-decision-audit \
  --query "Items[*].[incident_id.S, stage.S, action.S]" \
  --output table
```

### Dedup behaviour

The Signal Collector uses a DynamoDB conditional write keyed on a SHA-256 hash of `(alertname, service, labels)`. Identical alerts within 30 minutes return HTTP 202 without creating a new signal bundle. To test a new incident, change the `startsAt` timestamp.

---

## Customisation

### Adding a new allowed action

Edit `gitops/policies/allowed-actions.yaml`:

```yaml
allowed_actions:
  - action: my_new_action
    constraints:
      some_param: some_value
```

Then implement the action handler in `lambdas/decision_engine/app.py` inside the `handler()` function and update the heuristic fallback in `_choose_action_heuristic()`.

The `policy-check.yaml` GitHub Actions workflow enforces bounds — extend it if your new action has numeric constraints that should be validated at PR time.

### Changing the AI model

In `terraform.tfvars`:

```hcl
model_provider = "openai"   # or "bedrock"
```

For OpenAI, also add:
```hcl
openai_secret_arn = "arn:aws:secretsmanager:..."  # {"api_key":"sk-..."}
```

The Decision Engine tries Bedrock/OpenAI first and falls back to the heuristic if either fails or returns an unparseable response.

### Connecting real Prometheus

```hcl
# terraform.tfvars
prometheus_query_url = "http://your-prometheus:9090"
```

The Signal Collector queries:
- `rate(http_requests_total{status=~"5.."}[5m])` — error rate
- `rate(container_cpu_usage_seconds_total{namespace="demo"}[5m])` — CPU
- `container_memory_working_set_bytes{namespace="demo"}` — memory

The Outcome Validator queries the same error rate metric post-remediation and validates it drops below 20%.

For Amazon Managed Prometheus (AMP), see `docs/amp-guidance.md` — SigV4 signing is required.

### Enabling the multi-agent pipeline

The Step Functions pipeline runs in parallel with the single-agent path when `ENABLE_MULTI_AGENT=true` is set on the Signal Collector Lambda (controlled by `enable_multi_agent = true` in tfvars).

**Confidence scoring model:**
```
base_score = diagnosis_confidence  (0–100, from RootCauseAgent)

Penalties applied:
  severity == critical    →  -10
  blast_radius == high    →  -15
  action == scale_replicas → -5   (low risk, small penalty)
  action == rollback_image → -10  (medium risk)
  action == restart_rollout → -5

final_score = base_score - sum(penalties)

Routes:
  final_score >= 80 AND risk == low  →  auto_apply
  final_score >= 40                  →  open_pr
  final_score < 40                   →  escalate
```

To test `auto_apply` routing, set a high `diagnosis_confidence` in a mock Step Functions execution or trigger with a low-severity alert.

---

## IAM Reference

Each Lambda has its own role (`${project_name}-{component}`) with a minimum-privilege inline policy:

| Lambda | Key permissions |
|---|---|
| Signal Collector | `s3:PutObject`, `events:PutEvents`, `dynamodb:PutItem/GetItem`, `eks:DescribeCluster` |
| Decision Engine | `s3:GetObject`, `secretsmanager:GetSecretValue`, `bedrock:InvokeModel`, `dynamodb:PutItem/UpdateItem` |
| Outcome Validator | `events:PutEvents`, `secretsmanager:GetSecretValue`, `dynamodb:PutItem/UpdateItem` |
| Agent Lambdas | `s3:GetObject`, `bedrock:InvokeModel`, `secretsmanager:GetSecretValue` |

> **Production hardening:** Resource ARNs are currently `*` for DynamoDB and Bedrock. Tighten to specific table ARNs and model ARNs. Add `aws:SourceArn` conditions on EventBridge → Lambda invoke permissions. See `docs/security-hardening.md` for the full checklist.

---

## CI/CD Workflows

| Workflow | Trigger | What it does |
|---|---|---|
| `validate-pr.yaml` | PR touching `gitops/**`, `lambdas/**`, `terraform/**` | `kustomize build` both clusters + `pytest tests/ -v` |
| `policy-check.yaml` | PR touching `gitops/**` | Validates replica count in kustomize overlay doesn't exceed `allowed-actions.yaml` max |
| `notify-action-dispatched.yaml` | Push to `main` with `gitops/**` changes | Extracts `inc-*` from commit message, fires `ActionDispatched` to EventBridge |

The `notify-action-dispatched.yaml` workflow bridges GitHub (where the PR merge happens) back to AWS EventBridge to trigger the Outcome Validator. This is the link that closes the feedback loop.

---

## Observability

- **CloudWatch Logs** — all Lambda functions log structured JSON (`{"event": "...", "incident_id": "..."}`)
- **X-Ray tracing** — enabled on all Lambda functions; trace the full execution path in the AWS Console
- **DynamoDB Audit Log** — `gitops-sentinel-decision-audit` table; every decision stored with 90-day TTL
- **EventBridge DLQ** — failed EventBridge deliveries land in an SQS dead letter queue (`gitops-sentinel-eventbridge-dlq`) with 14-day retention
- **Step Functions console** — visual execution graph for the multi-agent pipeline

---

## Known Limitations and Production Gaps

| Gap | Impact | Recommended fix |
|---|---|---|
| Lambda dependencies installed manually into `src/` | Fragile in CI — any `terraform apply` from a clean checkout will fail | Replace with `null_resource` + `local-exec` pip install, or a Lambda Layer |
| IAM resource ARNs use `*` for DynamoDB and Bedrock | Over-permissive | Tighten to specific ARNs in the IAM module |
| `prometheus_query_url` is empty by default | Outcome Validator skips recovery check, always marks `OutcomeValidated` | Connect real Prometheus or AMP |
| Gatekeeper ConstraintTemplate must be synced before Constraint | Manual step required on fresh Argo CD setup | Add Argo CD sync waves via `argocd.argoproj.io/sync-wave` annotations |
| No Alertmanager integration test | You have to fire test alerts manually | Add a `make test-alert` Makefile target or a test receiver in Alertmanager config |
| GitHub PAT is a long-lived credential | Security risk | Migrate to GitHub App installation token flow (token cache already implemented in Decision Engine) |
| Lambda token cache (5-min TTL) not invalidated when Secrets Manager is updated | After rotating a PAT, the Lambda serves stale credentials for up to 5 minutes | Force a cold start immediately by updating any env var: `aws lambda update-function-configuration --function-name gitops-sentinel-decision-engine --environment "$(aws lambda get-function-configuration --function-name gitops-sentinel-decision-engine --query 'Environment' --output json \| python3 -c "import json,sys,time; e=json.load(sys.stdin); e['Variables']['CACHE_BUST']=str(time.time()); print(json.dumps(e))")"` |
| Terraform `archive_file` data source does not reliably detect changes to `src/` directory contents | `terraform apply` reports `0 changes` after adding pip deps — Lambda runs stale code | Re-upload manually: `cd terraform/modules/lambda_{name}/src && zip -r /tmp/fn.zip . && aws lambda update-function-code --function-name gitops-sentinel-{name} --zip-file fileb:///tmp/fn.zip`. Long-term fix: use `null_resource` with `local-exec` and a `triggers` hash of the src directory |
| `allowed-actions.yaml` must not be listed in `gitops/policies/kustomization.yaml` as a resource | It is a Lambda config file, not a Kubernetes manifest — kustomize will reject it with `missing Resource metadata` | Only Gatekeeper manifests belong in that kustomization's `resources:` list. `allowed-actions.yaml` is fetched directly from GitHub by the Decision Engine at runtime via the GitHub Contents API |

---

## Tear Down

```bash
cd terraform && terraform destroy -auto-approve

# Secrets Manager is not managed by Terraform — delete manually
aws secretsmanager delete-secret \
  --secret-id "gitops-sentinel/github-token" \
  --force-delete-without-recovery
```

If `terraform destroy` fails on the EKS node group (common when Kubernetes resources are still present), delete the Argo CD apps first:

```bash
argocd app delete demo-staging --cascade
argocd app delete demo-prod --cascade
kubectl delete namespace demo
terraform destroy -auto-approve
```
