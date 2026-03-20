variable "project_name" { type = string }

resource "aws_cloudwatch_event_bus" "this" {
  name = "${var.project_name}-bus"
}

# ── Archive: retain all events for 7 days (enables replay after bug fixes) ───
resource "aws_cloudwatch_event_archive" "this" {
  name             = "${var.project_name}-archive"
  event_source_arn = aws_cloudwatch_event_bus.this.arn
  retention_days   = 7
}

output "event_bus_name"    { value = aws_cloudwatch_event_bus.this.name }
output "event_bus_arn"     { value = aws_cloudwatch_event_bus.this.arn }
output "archive_name"      { value = aws_cloudwatch_event_archive.this.name }
