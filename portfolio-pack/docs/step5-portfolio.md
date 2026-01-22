# Step 5 — Turn This Into a Portfolio Project (AI / Platform / DevOps)

This pack helps you present the project as a **credible, interview-ready portfolio artifact**: clear story, measurable outcomes, demo plan, and role-aligned talking points.

---

## 1) Portfolio framing (what you built)

**Project title:** AI-Powered GitOps Self-Healing Platform (AWS-native POC)

**One-liner:**  
A safe-by-default, AWS-native “self-healing” platform that converts production alerts into constrained GitOps pull requests, enforces guardrails with CI + Gatekeeper, and verifies recovery with PromQL—optionally auto-reverting via a rollback PR.

**Problem it solves:**  
- Alert fatigue and slow MTTR  
- Manual, error-prone remediations  
- Lack of guardrails when automation is introduced

**Why it’s unique:**  
- “AI doesn’t touch the cluster” — AI proposes **PRs only**  
- Hard constraints (allowed-actions + Gatekeeper + CI)  
- Verification loop (PromQL) + optional auto-revert PR  
- Dedup/correlation to prevent alert storms

---

## 2) What to showcase (features that land well in interviews)

### A) Safe autonomy model
- Agent can only choose actions from `gitops/policies/allowed-actions.yaml`
- All changes go through PR review + checks
- Gatekeeper enforces maximum bounds at admission time

### B) Closed-loop operation
- Alert → Bundle → PR → Merge → Reconcile → Verify
- Emits events to EventBridge at each stage for auditability

### C) Reliability patterns
- Dedup via DynamoDB TTL window
- Auto-revert PR on verification failure
- Minimal blast radius via overlays (staging vs prod)

### D) AWS-native architecture
- EKS, EventBridge, Lambda, DynamoDB, S3, API Gateway
- Optional Bedrock/OpenAI reasoning component

---

## 3) Repo structure (recommended for the public portfolio repo)

```
.
├─ README.md
├─ docs/
│  ├─ architecture.md
│  ├─ runbook.md
│  ├─ demo.md
│  ├─ security.md
│  ├─ decisions.md
│  ├─ cost-estimate.md
├─ terraform/
├─ gitops/
├─ lambdas/
└─ .github/workflows/
```

---

## 4) README outline (what recruiters and interviewers want)

### Must-have sections
- What it does (1–2 paragraphs)
- Architecture diagram (image + link to draw.io)
- End-to-end flow
- Guardrails / safety model
- Quickstart (terraform + demo steps)
- Demo video link (later)
- Tradeoffs & future work
- Cost notes + teardown instructions

---

## 5) Demo plan (10–12 minutes, interview-friendly)

### Setup
- `terraform apply` already done
- Argo CD app is synced
- Prometheus + Alertmanager installed
- (Optional) Slack webhook configured

### Live demo steps
1. Show Grafana dashboard / alert rules
2. Trigger alert (or reduce threshold)
3. Show S3 incident bundle JSON (enriched context)
4. Show GitHub PR opened by the agent
5. Show CI checks passing (kustomize build + policy check)
6. Merge PR → show Argo CD syncing to EKS
7. Show verifier output (Verified/Failed) + Slack update
8. (If failed) show auto-revert PR created

### Narration line that hits
“AI recommends a *bounded* remediation via PR; the platform enforces guardrails and verifies recovery.”

---

## 6) Metrics and success criteria (what you can claim)

Even as a POC, you can demonstrate:
- Reduced time-to-remediation (manual vs automated PR creation)
- Safety: 0 direct writes from AI to cluster
- Policy compliance rate (CI + Gatekeeper rejects out-of-policy)
- Dedup effectiveness (suppressed repeated alerts within TTL)

Add a small table in README with example runs:
- Alert fired at T0
- PR opened at T0+X seconds
- Merge at T0+Y
- Recovery verified at T0+Z

---

## 7) Resume bullets (choose based on role)

### AI Engineer / AI Platform
- Built an AI-driven incident response agent that converts alerts into constrained GitOps PRs using Bedrock/OpenAI prompts and policy-bound action selection.
- Designed guardrail system (allowed-actions contract + CI validation + Gatekeeper) to enforce safe autonomous changes and prevent unsafe remediations.
- Implemented closed-loop verification using PromQL and automated rollback via revert PRs when recovery conditions fail.

### Platform / SRE / DevOps
- Architected AWS-native self-healing infrastructure on EKS with EventBridge orchestration, Lambda remediation pipeline, S3 evidence bundling, and DynamoDB incident deduplication.
- Automated GitOps remediation workflow using Argo CD, Kustomize overlays, and GitHub Actions with policy checks to ensure repeatable, auditable operations.
- Reduced MTTR by automating incident triage → remediation → verification while maintaining change control via PR approvals and cluster admission constraints.

---

## 8) STAR stories (ready-to-tell in interviews)

### Story 1: Safety-by-default autonomy
- **S:** Team fears “AI running wild” in prod.
- **T:** Add AI without increasing risk.
- **A:** PR-only changes, allowed-actions contract, CI + Gatekeeper, staged rollouts.
- **R:** Demonstrated autonomous remediation with guardrails and audit trail; no direct cluster writes.

### Story 2: Verification and rollback
- **S:** Automated fixes can make incidents worse.
- **T:** Ensure “trust but verify.”
- **A:** Verifier queries PromQL; on failure opens revert PR; Slack notifications.
- **R:** Reduced risk of runaway automation; deterministic rollback path.

---

## 9) What to record for a demo video (2–4 minutes)
- Architecture slide (30s)
- Alert triggers → incident bundle (30s)
- PR opened → checks (45s)
- Merge → Argo sync (30s)
- Verifier status + revert PR (45s)

---

## 10) Future roadmap (credible next steps)
- AMP integration with SigV4 signing
- GitHub App installation token flow (no PAT)
- Multi-alert correlation graph
- Argo Rollouts (canary) + progressive remediation
- Fine-grained Gatekeeper policies derived from allowed-actions
