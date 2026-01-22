# Threat Model & Safety Controls

## Key risks
- Hallucinated remediations
- Over-privileged agents
- Cascading failures
- Prompt injection via logs
- Unauthorized infrastructure changes

---

## Mitigations
- Tool-restricted agents
- Git-only write access
- Policy-as-code enforcement
- Schema validation
- CI security scans
- RBAC environment scoping
- Human approval for risky actions

---

## Trust boundaries
- Observability → Agent (read only)
- Agent → Git (write controlled)
- Git → Cluster (via GitOps only)

---

## Security posture
The AI agent is treated as a junior engineer with:
- Limited permissions
- Mandatory reviews
- Continuous auditing
