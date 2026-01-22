variable "project_name" { type = string }
variable "incident_bucket_arn" { type = string }
variable "event_bus_arn" { type = string }

data "aws_iam_policy_document" "assume_lambda" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
  type        = "Service"
  identifiers = ["lambda.amazonaws.com"]
}
  }
}

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

resource "aws_iam_role_policy_attachment" "basic" {
  for_each = {
    bundler  = aws_iam_role.bundler.name
    agent    = aws_iam_role.agent.name
    verifier = aws_iam_role.verifier.name
  }
  role       = each.value
  policy_arn  = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Minimal inline policies. Tighten per your environment.
resource "aws_iam_role_policy" "bundler_inline" {
  name = "${var.project_name}-bundler-inline"
  role = aws_iam_role.bundler.id
  policy = jsonencode({
    Version="2012-10-17",
    Statement=[
      { Effect="Allow", Action=["s3:PutObject","s3:PutObjectAcl"], Resource=["${var.incident_bucket_arn}/*"] },
      { Effect="Allow", Action=["events:PutEvents"], Resource=[var.event_bus_arn] }
    ]
  })
}

resource "aws_iam_role_policy" "agent_inline" {
  name = "${var.project_name}-agent-inline"
  role = aws_iam_role.agent.id
  policy = jsonencode({
    Version="2012-10-17",
    Statement=[
      { Effect="Allow", Action=["s3:GetObject"], Resource=["${var.incident_bucket_arn}/*"] },
      { Effect="Allow", Action=["secretsmanager:GetSecretValue"], Resource=["*"] }
    ]
  })
}

resource "aws_iam_role_policy" "verifier_inline" {
  name = "${var.project_name}-verifier-inline"
  role = aws_iam_role.verifier.id
  policy = jsonencode({
    Version="2012-10-17",
    Statement=[
      { Effect="Allow", Action=["events:PutEvents"], Resource=[var.event_bus_arn] }
    ]
  })
}

output "bundler_role_arn"  { value = aws_iam_role.bundler.arn }
output "agent_role_arn"    { value = aws_iam_role.agent.arn }
output "verifier_role_arn" { value = aws_iam_role.verifier.arn }
