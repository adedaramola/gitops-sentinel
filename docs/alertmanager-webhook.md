# Alertmanager Webhook Setup

Point Alertmanager to the Terraform output `webhook_url`.

Example (values.yaml for kube-prometheus-stack):
```yaml
alertmanager:
  config:
    receivers:
      - name: ai-webhook
        webhook_configs:
          - url: "<WEBHOOK_URL_FROM_TERRAFORM>"
            send_resolved: true
    route:
      receiver: ai-webhook
```

The webhook sends JSON to the Bundler Lambda. The bundler writes an incident bundle to S3 and emits an EventBridge event that triggers the Agent Lambda.
