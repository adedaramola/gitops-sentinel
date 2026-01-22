output "event_bus_name" { value = module.eventing.event_bus_name }
output "incident_bucket_name" { value = module.incidents_bucket.bucket_name }
output "bundler_lambda_name" { value = module.bundler_lambda.lambda_name }
output "agent_lambda_name" { value = module.agent_lambda.lambda_name }
output "verifier_lambda_name" { value = module.verifier_lambda.lambda_name }

output "cluster_name" { value = module.eks.cluster_name }
output "cluster_endpoint" { value = module.eks.cluster_endpoint }

output "incident_table_name" { value = module.incidents_table.table_name }
