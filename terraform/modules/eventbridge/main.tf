variable "project_name" { type = string }

resource "aws_cloudwatch_event_bus" "this" {
  name = "${var.project_name}-bus"
}

output "event_bus_name" { value = aws_cloudwatch_event_bus.this.name }
output "event_bus_arn"  { value = aws_cloudwatch_event_bus.this.arn }
