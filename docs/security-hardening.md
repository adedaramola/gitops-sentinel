# Security Hardening (Recommended for production)

## API Gateway
- Require auth (JWT authorizer or API key)
- Add AWS WAF
- Rate limit / throttling
- Validate payload schema

## GitHub auth
- Replace static PAT with GitHub App installation token flow
- Restrict app permissions to:
  - Contents: write (only necessary paths)
  - Pull requests: write
- Enforce branch protection + required checks

## Network
- Put Lambdas in VPC only if required; otherwise prefer public egress with strict IAM
- If using OpenAI, restrict outbound via NAT + egress firewalling / DNS controls

## Data
- Use KMS CMK for S3 + Secrets Manager
- Lock down S3 bucket policy to lambdas only
- Consider encrypting incident bundles containing sensitive labels

## IAM
- Tighten resource ARNs (Secrets Manager, EventBridge, S3 prefixes)
- Separate roles per lambda (already done) and minimize permissions further
