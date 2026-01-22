# Amazon Managed Service for Prometheus (AMP) Guidance (POC)

This repo supports querying a Prometheus HTTP API endpoint via `prometheus_query_url`.

For AMP:
- Your `prometheus_query_url` should be your AMP query endpoint.
- Access requires SigV4 signing. This POC currently assumes the endpoint is reachable without extra auth.
- For a production AMP integration, add SigV4 signing (AWS requests auth) to the `_prom_query()` functions.

Practical approach:
1. Start with in-cluster Prometheus (kube-prometheus-stack) and port-forwarded/proxied query URL.
2. Migrate to AMP later with SigV4 signing.
