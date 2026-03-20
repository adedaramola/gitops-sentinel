variable "project_name"         { type = string }
variable "event_bus_name"        { type = string }
variable "bundler_lambda_arn"    { type = string }
variable "agent_lambda_arn"      { type = string }
variable "verifier_lambda_arn"   { type = string }
variable "sfn_arn"               { type = string }
variable "events_sfn_role_arn"   { type = string }

# ── Dead Letter Queue ─────────────────────────────────────────────────────────
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project_name}-eventbridge-dlq"
  message_retention_seconds = 1209600 # 14 days
  tags                      = { Project = var.project_name }
}

resource "aws_sqs_queue_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.dlq.arn
    }]
  })
}

# ── Rule 1: inbound alert -> bundler ─────────────────────────────────────────
resource "aws_cloudwatch_event_rule" "alert_in" {
  name           = "${var.project_name}-alert-in"
  event_bus_name = var.event_bus_name
  event_pattern = jsonencode({
    "source" : ["prometheus.alertmanager", "ai.gitops.webhook", "ai.gitops.test"]
  })
}

resource "aws_cloudwatch_event_target" "alert_to_bundler" {
  rule           = aws_cloudwatch_event_rule.alert_in.name
  event_bus_name = var.event_bus_name
  arn            = var.bundler_lambda_arn

  retry_policy {
    maximum_retry_attempts       = 2
    maximum_event_age_in_seconds = 3600
  }

  dead_letter_config {
    arn = aws_sqs_queue.dlq.arn
  }
}

# ── Rule 2: bundle created -> agent ──────────────────────────────────────────
resource "aws_cloudwatch_event_rule" "bundle_created" {
  name           = "${var.project_name}-bundle-created"
  event_bus_name = var.event_bus_name
  event_pattern = jsonencode({
    "source" : ["ai.gitops"],
    "detail-type" : ["IncidentBundleCreated"]
  })
}

resource "aws_cloudwatch_event_target" "bundle_to_agent" {
  rule           = aws_cloudwatch_event_rule.bundle_created.name
  event_bus_name = var.event_bus_name
  arn            = var.agent_lambda_arn

  retry_policy {
    maximum_retry_attempts       = 2
    maximum_event_age_in_seconds = 3600
  }

  dead_letter_config {
    arn = aws_sqs_queue.dlq.arn
  }
}

# ── Rule 3: remediation applied -> verifier ───────────────────────────────────
resource "aws_cloudwatch_event_rule" "verify" {
  name           = "${var.project_name}-verify"
  event_bus_name = var.event_bus_name
  event_pattern = jsonencode({
    "source" : ["ai.gitops"],
    "detail-type" : ["RemediationApplied"]
  })
}

resource "aws_cloudwatch_event_target" "verify_to_lambda" {
  rule           = aws_cloudwatch_event_rule.verify.name
  event_bus_name = var.event_bus_name
  arn            = var.verifier_lambda_arn

  retry_policy {
    maximum_retry_attempts       = 2
    maximum_event_age_in_seconds = 3600
  }

  dead_letter_config {
    arn = aws_sqs_queue.dlq.arn
  }
}

# ── Rule 4: multi-agent bundle created -> Step Functions ─────────────────────
resource "aws_cloudwatch_event_rule" "multi_agent" {
  name           = "${var.project_name}-multi-agent"
  event_bus_name = var.event_bus_name
  event_pattern = jsonencode({
    "source" : ["ai.gitops"],
    "detail-type" : ["MultiAgentIncidentCreated"]
  })
}

resource "aws_cloudwatch_event_target" "multi_agent_to_sfn" {
  rule           = aws_cloudwatch_event_rule.multi_agent.name
  event_bus_name = var.event_bus_name
  arn            = var.sfn_arn
  role_arn       = var.events_sfn_role_arn

  retry_policy {
    maximum_retry_attempts       = 2
    maximum_event_age_in_seconds = 3600
  }

  dead_letter_config {
    arn = aws_sqs_queue.dlq.arn
  }
}

output "alert_in_rule_arn"       { value = aws_cloudwatch_event_rule.alert_in.arn }
output "bundle_created_rule_arn"  { value = aws_cloudwatch_event_rule.bundle_created.arn }
output "verify_rule_arn"          { value = aws_cloudwatch_event_rule.verify.arn }
output "multi_agent_rule_arn"     { value = aws_cloudwatch_event_rule.multi_agent.arn }
output "dlq_arn"                  { value = aws_sqs_queue.dlq.arn }
output "dlq_url"                  { value = aws_sqs_queue.dlq.id }
