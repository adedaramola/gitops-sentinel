# Cost Estimate (POC)

> Costs vary heavily by region, cluster size, and usage. This is a rough POC guide.

## Major drivers
- EKS: control plane hourly + worker nodes
- NAT Gateway (if enabled): hourly + data processing
- Lambda: invocations + duration
- EventBridge: events
- DynamoDB: on-demand reads/writes
- S3: storage + PUT/GET requests
- CloudWatch logs

## Tips to keep costs low
- Use small node groups (t3.large or smaller if possible)
- Keep NAT traffic minimal; consider public nodes for POC (tradeoff)
- Set log retention to 7 days
- Tear down after demo: `terraform destroy`
