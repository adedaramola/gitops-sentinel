# Interview Cheat Sheet

## 30-second pitch
I built an AWS-native GitOps self-healing loop that converts alerts into constrained PRs. The AI agent only proposes changes; CI + Gatekeeper enforce guardrails; a verifier checks PromQL recovery and can open an auto-revert PR if the remediation fails.

## Deep dive prompts
- Why PR-only execution is safer than imperative automation
- How allowed-actions + Gatekeeper reduce blast radius
- How verifier prevents “automation making it worse”
- How EventBridge enables auditable, decoupled workflows

## “What would you do next?”
- GitHub App auth flow
- AMP with SigV4
- Correlation graph + dedup improvements
- Canary rollouts + Argo Rollouts integration
