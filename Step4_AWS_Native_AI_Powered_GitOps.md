# Step 4 – AWS-Native AI-Powered GitOps Self-Healing Platform

## Overview
This document defines the AWS-native implementation of the AI-powered GitOps self-healing infrastructure platform.

It translates the reference architecture into deployable AWS services using:

- Amazon EKS
- Prometheus + Alertmanager
- Argo CD
- EventBridge
- AWS Lambda
- Amazon Bedrock or OpenAI
- Terraform
- S3, IAM, Secrets Manager

The goal is to build a **closed-loop operational system** where alerts automatically trigger AI-driven remediation proposals through GitOps.

---

## Core Event Flow

1. Alert fires in Prometheus / Alertmanager  
2. Alert webhook sent to API Gateway or EventBridge  
3. EventBridge routes event to Incident Bundler Lambda  
4. Bundler enriches context and writes incident bundle to S3  
5. EventBridge triggers LLM Agent Lambda  
6. Agent reasons over incident and opens GitHub Pull Request  
7. GitHub Actions validates manifests and policies  
8. Argo CD reconciles approved change to EKS  
9. Verifier Lambda checks recovery metrics  
10. Status posted to Slack/SNS and stored for learning  

---

## AWS Architecture Components

### Compute and Runtime
- Amazon EKS (applications, Kubernetes control plane)
- Managed node groups or Karpenter
- Argo CD deployed via Helm

### Observability
- kube-prometheus-stack (Prometheus, Alertmanager, Grafana)
- Kubernetes events API
- Optional: AWS Managed Grafana

### Intelligence Layer
- AWS Lambda (Python)
- Amazon Bedrock (Claude/Llama/Titan) or OpenAI
- Tool-restricted operational agent

### Control Plane
- GitHub repository
- GitHub App for PR access
- GitHub Actions CI pipelines
- Argo CD reconciliation

### Eventing and Orchestration
- Amazon EventBridge custom event bus
- API Gateway (optional webhook intake)
- Step Functions (optional future state orchestration)

### Data and Evidence
- Amazon S3 (incident bundles, logs, evidence)
- DynamoDB (optional incident index)

### Governance and Security
- IAM least privilege roles
- OPA Gatekeeper on EKS
- GitHub branch protection
- Secrets Manager for API keys

---

## Lambda Responsibilities

### Incident Bundler Lambda
- Consumes Alertmanager payloads
- Queries Prometheus for snapshots
- Pulls Kubernetes events
- Collects recent deployment data
- Writes immutable incident bundle to S3

### LLM Agent Lambda
- Loads incident bundle
- Enforces allowed-actions contract
- Invokes Bedrock or OpenAI
- Generates remediation plan
- Applies patch to GitOps repo
- Opens Pull Request with explanation

### Verifier Lambda
- Waits defined stabilization window
- Runs PromQL queries
- Confirms recovery
- Posts result to Slack/SNS
- Closes incident lifecycle

---

## Guardrails

- Git-only write access
- No EKS write permissions for AI
- OPA/Gatekeeper admission controls
- CI validation before merge
- Environment promotion rules
- Risk-based autonomy levels

---

## Terraform Module Layout

terraform/
  main.tf
  providers.tf
  variables.tf
  outputs.tf

  modules/
    eks/
    argocd/
    observability/
    gatekeeper/
    eventbridge/
    s3_incidents/
    iam/
    secrets/
    lambda_incident_bundler/
    lambda_llm_agent/
    lambda_verifier/

---

## Supported Remediations (POC Scope)

- Deployment rollback
- Replica scaling
- Resource tuning
- Rollout restarts
- Config repair
- Dependency throttling

---

## Autonomy Maturity Model

Level 0 – PR only, human merges  
Level 1 – Auto-merge low-risk in staging  
Level 2 – Guarded auto-merge in prod  
Level 3 – Predictive self-healing  

---

## Success Metrics

- Mean time to detect
- Mean time to resolve
- Auto-remediation rate
- Incident recurrence
- Change failure rate
- On-call pages per week

---

## Outcome

This AWS-native implementation creates a production-aligned foundation for autonomous operations, where Git remains the execution engine, AI becomes the reasoning engine, and AWS provides the secure event-driven control fabric.
