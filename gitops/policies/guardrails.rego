package guardrails

default allow = false

# Placeholder: implement constraints aligned to allowed-actions.yaml
allow {
  input.kind == "Deployment"
}
