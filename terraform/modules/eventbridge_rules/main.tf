variable "project_name" { type = string }
variable "event_bus_name" { type = string }
variable "bundler_lambda_arn" { type = string }
variable "agent_lambda_arn" { type = string }
variable "verifier_lambda_arn" { type = string }

# Rule 1: inbound alert -> bundler
resource "aws_cloudwatch_event_rule" "alert_in" {
  name           = "${var.project_name}-alert-in"
  event_bus_name = var.event_bus_name
  event_pattern  = jsonencode({
    "source": ["prometheus.alertmanager", "ai.gitops.webhook", "ai.gitops.test"]
  })
}

resource "aws_cloudwatch_event_target" "alert_to_bundler" {
  rule           = aws_cloudwatch_event_rule.alert_in.name
  event_bus_name = var.event_bus_name
  arn            = var.bundler_lambda_arn
}

# Rule 2: bundle created -> agent
resource "aws_cloudwatch_event_rule" "bundle_created" {
  name           = "${var.project_name}-bundle-created"
  event_bus_name = var.event_bus_name
  event_pattern  = jsonencode({
    "source": ["ai.gitops"],
    "detail-type": ["IncidentBundleCreated"]
  })
}

resource "aws_cloudwatch_event_target" "bundle_to_agent" {
  rule           = aws_cloudwatch_event_rule.bundle_created.name
  event_bus_name = var.event_bus_name
  arn            = var.agent_lambda_arn
}

# Rule 3: (optional) PR merged / sync done -> verifier (placeholder)
resource "aws_cloudwatch_event_rule" "verify" {
  name           = "${var.project_name}-verify"
  event_bus_name = var.event_bus_name
  event_pattern  = jsonencode({
    "source": ["ai.gitops"],
    "detail-type": ["RemediationApplied"]
  })
}

resource "aws_cloudwatch_event_target" "verify_to_lambda" {
  rule           = aws_cloudwatch_event_rule.verify.name
  event_bus_name = var.event_bus_name
  arn            = var.verifier_lambda_arn
}


output "alert_in_rule_arn" { value = aws_cloudwatch_event_rule.alert_in.arn }
output "bundle_created_rule_arn" { value = aws_cloudwatch_event_rule.bundle_created.arn }
output "verify_rule_arn" { value = aws_cloudwatch_event_rule.verify.arn }
