# AI-Powered GitOps Self-Healing Infrastructure (POC)

This repository is a proof-of-concept platform demonstrating how **LLM agents + GitOps** can be combined to build **self-healing infrastructure**.

## What this is
A reference POC where an AI agent:
1. Consumes incident context (metrics/logs/events)
2. Performs reasoning and remediation planning
3. Proposes changes only through Git pull requests
4. GitOps controllers reconcile approved changes
5. Observability verifies recovery

## Core principles
- Git is the single source of truth  
- The AI never touches production directly  
- All changes go through policy, CI, and reconciliation  
- Autonomy is bounded and auditable  

## High-level workflow
Detect → Context Build → Reason → Plan → PR → Validate → Reconcile → Verify → Learn

## Intended stack
- Kubernetes (EKS or local)
- Argo CD or Flux
- Prometheus + logs
- Python LLM agent
- GitHub Actions CI

## Folder intent
- docs/ → Architecture, runbooks, and threat model
- agent/ → LLM agent (future step)
- gitops/ → Declarative infrastructure and apps
- incidents/ → Test incident bundles

## Status
Step 3 of a staged build:
✔ Architecture  
✔ Reference design  
✔ Repo blueprint  
⬜ AWS-native implementation  
⬜ Portfolio project packaging
