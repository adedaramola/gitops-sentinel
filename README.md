# GitOps Sentinel

> **Confidence-gated autonomous remediation for Kubernetes — no human in the loop unless the system isn't sure.**

GitOps Sentinel is a production-grade AIOps platform that intercepts infrastructure anomalies, routes them through a multi-agent reasoning pipeline, and takes action only when confidence justifies it. Every remediation is a Git commit — the cluster never changes outside of a reviewed pull request or a high-confidence auto-apply.

---

## Why GitOps Sentinel?

Traditional alerting pipelines page humans for every incident. GitOps Sentinel asks: *what if the system could reason about the incident itself and decide whether a human is needed?*

The answer is a **confidence-gated routing engine**:

| Confidence | Risk level | Action |
|---|---|---|
| ≥ 80 | low | Auto-apply: merge the PR automatically |
| 40 – 79 | any | Open PR: engineer reviews before merge |
| < 40 | any | Escalate: page on-call, no automated change |

This means routine, well-understood incidents (pod OOMKilled, replica drift, known bad image tag) resolve in seconds. Novel, high-risk situations escalate immediately — before anything touches the cluster.

---

## Architecture

```
Alertmanager / CloudWatch
        │
        ▼
  API Gateway (HMAC-validated webhook)
        │
        ▼
  Signal Collector Lambda          ◄── dedup via DynamoDB conditional write
        │  emits: SignalBundled / SentinelPipelineTriggered
        ▼
  EventBridge (custom bus + 7-day archive)
        │
        ├──► Decision Engine Lambda        (single-agent path, feature-flag off)
        │
        └──► Step Functions: Sentinel Pipeline  (multi-agent path, feature-flag on)
                │
                ├── Classifier Agent     → severity class, blast radius, priority
                ├── Root Cause Agent     → root cause, contributing factors, confidence
                ├── Action Planner Agent → action from allowed-actions.yaml, alternatives
                ├── Confidence Scorer    → deterministic score, route decision
                └── RouteByConfidence ──► auto_apply | open_pr | escalate
                                              │
                                              ▼
                                    GitHub PR (GitOps write path)
                                              │
                                              ▼
                                    Argo CD syncs cluster
                                              │
                                              ▼
                              Outcome Validator Lambda
                                    (Prometheus health check)
                                              │
                                    emits: OutcomeValidated / OutcomeFailed
                                              │
                                    ► auto-revert PR if OutcomeFailed
```

---

## Components

### Lambda Functions

| Function | Role |
|---|---|
| `signal_collector` | Ingests Alertmanager webhooks, deduplicates via DynamoDB, bundles signal context (Prometheus metrics + k8s events) into S3, emits to EventBridge |
| `decision_engine` | Single-agent coordinator: reads the signal bundle, queries the LLM for a remediation plan, opens a GitHub PR |
| `outcome_validator` | Post-remediation health check: queries Prometheus, emits `OutcomeValidated` or `OutcomeFailed`, triggers auto-revert if needed |
| `classifier_agent` | Multi-agent: classifies severity, incident type, blast radius |
| `root_cause_agent` | Multi-agent: LLM root cause analysis with diagnosis confidence score |
| `action_planner_agent` | Multi-agent: proposes action from `allowed-actions.yaml`, with alternatives |
| `confidence_scorer` | Multi-agent: pure deterministic scoring — no LLM, no latency, no cost |

### Infrastructure Modules

| Module | Purpose |
|---|---|
| `eventbridge` | Custom event bus + 7-day archive for replay |
| `eventbridge_rules` | Rules with DLQ, retry policies, and dead-letter config |
| `step_functions` | Sentinel Pipeline state machine (Standard Workflow) |
| `dynamodb_incidents` | Dedup table + audit trail (TTL-based) |
| `s3_incidents` | Signal bundle storage |
| `apigw_webhook` | HTTP API Gateway → Signal Collector |
| `iam` | Per-function scoped roles, X-Ray permissions |
| `argocd` | GitOps controller (Helm) |
| `observability` | Prometheus + Grafana (Helm) |
| `gatekeeper` | OPA policy enforcement (Helm) |

---

## Signal Flow

1. **Alertmanager** fires a webhook → API Gateway validates HMAC secret
2. **Signal Collector** deduplicates (DynamoDB conditional write), enriches with Prometheus metrics and k8s events, stores bundle in S3, emits `SignalBundled` or `SentinelPipelineTriggered` to EventBridge
3. **Sentinel Pipeline** (Step Functions) runs: Classifier → Root Cause → Action Planner → Confidence Scorer → RouteByConfidence
4. **GitHub PR** is opened (or auto-merged) with the proposed change to the GitOps manifest
5. **Argo CD** detects the merged commit and syncs the cluster
6. **Outcome Validator** queries Prometheus 5 minutes post-remediation and emits the outcome event
7. If validation fails, the validator opens a **revert PR** automatically

---

## EventBridge Event Types

| Event | Emitted by | Triggers |
|---|---|---|
| `SignalBundled` | Signal Collector | Decision Engine (single-agent path) |
| `SentinelPipelineTriggered` | Signal Collector | Step Functions (multi-agent path) |
| `ActionDispatched` | Decision Engine | Outcome Validator |
| `OutcomeValidated` | Outcome Validator | — (terminal success) |
| `OutcomeFailed` | Outcome Validator | — (auto-revert initiated) |

---

## Configuration

Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars` and fill in:

```hcl
github_owner            = "your-org"
github_repo             = "your-gitops-repo"
github_token_secret_arn = "arn:aws:secretsmanager:..."

# Optional
prometheus_query_url = "https://prom.example.com"
slack_webhook_url    = "https://hooks.slack.com/..."
webhook_secret       = ""   # generate: openssl rand -hex 32
enable_multi_agent   = true # set false for single-agent mode
model_provider       = "bedrock"  # or "openai"
```

---

## Local Development

```bash
# Install dev dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r lambdas/requirements-dev.txt

# Run tests
cd lambdas && pytest tests/ -v

# Lint
cd lambdas && flake8 . --max-line-length=120

# Terraform
cd terraform
terraform init
terraform validate
terraform plan -var-file=terraform.tfvars
```

---

## Deploying

```bash
cd terraform
terraform init
terraform apply -var-file=terraform.tfvars
```

The `webhook_url` output is the endpoint to configure in Alertmanager's `receivers`.

---

## Cost Estimate

| Component | ~Monthly (us-east-1) |
|---|---|
| EKS cluster (1.32, 2× t2.medium) | ~$140 |
| Lambda invocations | < $5 |
| EventBridge + Step Functions | < $5 |
| DynamoDB + S3 | < $3 |
| API Gateway | < $2 |
| **Total** | **~$155–$178** |

---

## Project Structure

```
.
├── lambdas/
│   ├── signal_collector/       # Webhook ingestion + signal bundling
│   ├── decision_engine/        # Single-agent remediation coordinator
│   ├── outcome_validator/      # Post-remediation health check
│   ├── classifier_agent/       # Multi-agent: incident classification
│   ├── root_cause_agent/       # Multi-agent: root cause analysis
│   ├── action_planner/         # Multi-agent: remediation planning
│   ├── confidence_scorer/      # Multi-agent: deterministic scoring
│   └── tests/                  # Unit tests (33 tests, 100% pass)
├── terraform/
│   ├── main.tf                 # Root module
│   ├── variables.tf
│   ├── outputs.tf
│   └── modules/                # 12+ custom Terraform modules
├── Makefile                    # install / test / lint / tf-* targets
└── docs/                       # Architecture diagrams, runbooks
```

---

## License

MIT
