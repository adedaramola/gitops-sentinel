variable "project_name" { type = string }
variable "role_arn" { type = string }

variable "incident_bucket_name" { type = string }
variable "event_bus_name" { type = string }







variable "aws_region" { type = string }
variable "cluster_name" { type = string }
variable "prometheus_query_url" { type = string }
variable "enable_k8s_readonly_enrichment" { type = bool }
variable "incidents_table_name" { type = string }
data "archive_file" "zip" {
  type        = "zip"
  source_dir  = "${path.module}/src"
  output_path = "${path.module}/function.zip"
}

resource "aws_lambda_function" "this" {
  function_name = "${var.project_name}-lambda_incident_bundler"
  role          = var.role_arn
  runtime       = "python3.11"
  handler       = "app.handler"
  filename      = data.archive_file.zip.output_path
  timeout       = 30

  environment {
    variables = {
      DEDUP_TTL_SECONDS = "1800"
      INCIDENTS_TABLE_NAME = var.incidents_table_name
      INCIDENT_BUCKET = var.incident_bucket_name
      EVENT_BUS_NAME = var.event_bus_name
      CLUSTER_NAME = var.cluster_name
      PROMETHEUS_QUERY_URL = var.prometheus_query_url
      ENABLE_K8S_READONLY = tostring(var.enable_k8s_readonly_enrichment)
    }
  }
}

output "lambda_arn"  { value = aws_lambda_function.this.arn }
output "lambda_name" { value = aws_lambda_function.this.function_name }
