variable "project_name" { type = string }

# Immutable decision audit log — every agent decision is written here with its
# confidence score, chosen action, routing outcome, and final validation result.
# TTL is 90 days; archived to S3 via DynamoDB Streams if longer retention needed.

resource "aws_dynamodb_table" "this" {
  name         = "${var.project_name}-decision-audit"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "incident_id"
  range_key    = "event_time"

  attribute {
    name = "incident_id"
    type = "S"
  }

  attribute {
    name = "event_time"
    type = "N"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = { Project = var.project_name }
}

output "table_name" { value = aws_dynamodb_table.this.name }
output "table_arn"  { value = aws_dynamodb_table.this.arn }
