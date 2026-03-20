output "event_bus_name" { value = module.eventing.event_bus_name }
output "signals_bucket_name" { value = module.signals_bucket.bucket_name }
output "signal_collector_lambda" { value = module.signal_collector_lambda.lambda_name }
output "decision_engine_lambda" { value = module.decision_engine_lambda.lambda_name }
output "outcome_validator_lambda" { value = module.outcome_validator_lambda.lambda_name }

output "cluster_name" { value = module.eks.cluster_name }
output "cluster_endpoint" { value = module.eks.cluster_endpoint }

output "signals_table_name" { value = module.signals_table.table_name }
