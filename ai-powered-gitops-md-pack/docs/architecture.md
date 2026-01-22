# Architecture Overview

## Layers

### 1. Observability Layer
Collects and normalizes:
- Metrics
- Logs
- Traces
- Kubernetes events
- Cloud alerts

Outputs structured **incident bundles** for the AI agent.

---

### 2. LLM Agent Layer
Responsible for:
- Context aggregation
- Signal correlation
- Root cause hypothesis generation
- Risk classification
- Remediation planning

The agent:
- Has read-only access to telemetry and cluster state
- Has write access only to Git
- Cannot mutate infrastructure directly

---

### 3. GitOps Control Plane
- Git repositories store desired state
- CI validates all changes
- Argo CD or Flux reconciles clusters

Guarantees:
- Drift correction
- Full audit trail
- Safe rollbacks

---

### 4. Runtime Systems
- Kubernetes clusters
- Microservices
- Cloud infrastructure

---

### 5. Governance & Safety Layer
- RBAC and least privilege
- Policy-as-code (OPA/Gatekeeper)
- Security scanning
- Environment promotion
- Human approval workflows

---

## Design philosophy
Git is the execution engine.
AI is the reasoning engine.
Policies are the guardrails.
