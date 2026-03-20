variable "project_name"        { type = string }
variable "incident_bucket_arn" { type = string }
variable "event_bus_arn"        { type = string }

# ── Trust policies ────────────────────────────────────────────────────────────
data "aws_iam_policy_document" "assume_lambda" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "assume_sfn" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "assume_events" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

# ── Existing Lambda roles ─────────────────────────────────────────────────────
resource "aws_iam_role" "bundler" {
  name               = "${var.project_name}-bundler"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json
}

resource "aws_iam_role" "agent" {
  name               = "${var.project_name}-agent"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json
}

resource "aws_iam_role" "verifier" {
  name               = "${var.project_name}-verifier"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json
}

# ── Multi-agent Lambda roles ──────────────────────────────────────────────────
resource "aws_iam_role" "triage_agent" {
  name               = "${var.project_name}-triage-agent"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json
}

resource "aws_iam_role" "diagnosis_agent" {
  name               = "${var.project_name}-diagnosis-agent"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json
}

resource "aws_iam_role" "remediation_agent" {
  name               = "${var.project_name}-remediation-agent"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json
}

resource "aws_iam_role" "risk_agent" {
  name               = "${var.project_name}-risk-agent"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json
}

# ── Step Functions role ───────────────────────────────────────────────────────
resource "aws_iam_role" "sfn" {
  name               = "${var.project_name}-sfn"
  assume_role_policy = data.aws_iam_policy_document.assume_sfn.json
}

# ── EventBridge → Step Functions role ────────────────────────────────────────
resource "aws_iam_role" "events_sfn" {
  name               = "${var.project_name}-events-sfn"
  assume_role_policy = data.aws_iam_policy_document.assume_events.json
}

# ── Attach basic execution + X-Ray to all Lambda roles ───────────────────────
locals {
  lambda_roles = {
    bundler           = aws_iam_role.bundler.name
    agent             = aws_iam_role.agent.name
    verifier          = aws_iam_role.verifier.name
    triage_agent      = aws_iam_role.triage_agent.name
    diagnosis_agent   = aws_iam_role.diagnosis_agent.name
    remediation_agent = aws_iam_role.remediation_agent.name
    risk_agent        = aws_iam_role.risk_agent.name
  }
}

resource "aws_iam_role_policy_attachment" "basic" {
  for_each   = local.lambda_roles
  role       = each.value
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "xray" {
  for_each   = local.lambda_roles
  role       = each.value
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# ── Existing inline policies ──────────────────────────────────────────────────
resource "aws_iam_role_policy" "bundler_inline" {
  name = "${var.project_name}-bundler-inline"
  role = aws_iam_role.bundler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:PutObject", "s3:PutObjectAcl"], Resource = ["${var.incident_bucket_arn}/*"] },
      { Effect = "Allow", Action = ["events:PutEvents"], Resource = [var.event_bus_arn] },
      { Effect = "Allow", Action = ["dynamodb:PutItem", "dynamodb:GetItem"], Resource = ["*"] },
      { Effect = "Allow", Action = ["eks:DescribeCluster"], Resource = ["*"] }
    ]
  })
}

resource "aws_iam_role_policy" "agent_inline" {
  name = "${var.project_name}-agent-inline"
  role = aws_iam_role.agent.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = ["${var.incident_bucket_arn}/*"] },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = ["*"] },
      { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = ["*"] }
    ]
  })
}

resource "aws_iam_role_policy" "verifier_inline" {
  name = "${var.project_name}-verifier-inline"
  role = aws_iam_role.verifier.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["events:PutEvents"], Resource = [var.event_bus_arn] },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = ["*"] }
    ]
  })
}

# ── Multi-agent inline policies ───────────────────────────────────────────────
resource "aws_iam_role_policy" "triage_inline" {
  name = "${var.project_name}-triage-inline"
  role = aws_iam_role.triage_agent.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = ["${var.incident_bucket_arn}/*"] },
      { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = ["*"] },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = ["*"] }
    ]
  })
}

resource "aws_iam_role_policy" "diagnosis_inline" {
  name = "${var.project_name}-diagnosis-inline"
  role = aws_iam_role.diagnosis_agent.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = ["${var.incident_bucket_arn}/*"] },
      { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = ["*"] },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = ["*"] }
    ]
  })
}

resource "aws_iam_role_policy" "remediation_inline" {
  name = "${var.project_name}-remediation-inline"
  role = aws_iam_role.remediation_agent.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = ["${var.incident_bucket_arn}/*"] },
      { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = ["*"] },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = ["*"] }
    ]
  })
}

resource "aws_iam_role_policy" "risk_inline" {
  name = "${var.project_name}-risk-inline"
  role = aws_iam_role.risk_agent.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = ["${var.incident_bucket_arn}/*"] }
    ]
  })
}

# ── Step Functions: invoke all agent Lambdas ──────────────────────────────────
resource "aws_iam_role_policy" "sfn_invoke_lambdas" {
  name = "${var.project_name}-sfn-invoke-lambdas"
  role = aws_iam_role.sfn.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = ["*"] },
      { Effect = "Allow", Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"], Resource = ["*"] }
    ]
  })
}

# ── EventBridge: start Step Functions executions ─────────────────────────────
resource "aws_iam_role_policy" "events_start_sfn" {
  name = "${var.project_name}-events-start-sfn"
  role = aws_iam_role.events_sfn.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["states:StartExecution"], Resource = ["*"] }
    ]
  })
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "bundler_role_arn"           { value = aws_iam_role.bundler.arn }
output "agent_role_arn"             { value = aws_iam_role.agent.arn }
output "verifier_role_arn"          { value = aws_iam_role.verifier.arn }
output "triage_agent_role_arn"      { value = aws_iam_role.triage_agent.arn }
output "diagnosis_agent_role_arn"   { value = aws_iam_role.diagnosis_agent.arn }
output "remediation_agent_role_arn" { value = aws_iam_role.remediation_agent.arn }
output "risk_agent_role_arn"        { value = aws_iam_role.risk_agent.arn }
output "sfn_role_arn"               { value = aws_iam_role.sfn.arn }
output "events_sfn_role_arn"        { value = aws_iam_role.events_sfn.arn }
