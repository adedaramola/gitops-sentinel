# Step 4 Tightening v3

Adds production-aligned behavior on top of v2:

## 1) Dedup / correlation
- Bundler computes a `dedup_key = sha256(service|env|alertname)`
- Writes a DynamoDB record with TTL (default 30 minutes)
- Suppresses duplicate incidents in the window

## 2) Gatekeeper policy aligned to allowed-actions
- Adds ConstraintTemplate + Constraint to enforce:
  - max replicas (10)
  - max CPU limit (2000m)
  - max memory limit (2048Mi)

Files:
- gitops/policies/gatekeeper/constrainttemplate-deployment-bounds.yaml
- gitops/policies/gatekeeper/constraint-deployment-bounds.yaml

## 3) Automated rollback on verification failure
- Verifier checks recovery via PromQL
- If failed, it searches for the AI PR associated with the incident id
- Opens a **revert PR** that restores changed files back to the base branch state
- Optional Slack notification includes the revert PR URL

## 4) CI policy check
- Adds GitHub Actions workflow enforcing basic bounds derived from allowed-actions.yaml
