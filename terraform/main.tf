# Root module wires all components together.

locals {
  name = var.project_name
}

########################
# VPC + EKS (deploy-ready)
########################
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${local.name}-vpc"
  cidr = var.vpc_cidr

  azs             = slice(data.aws_availability_zones.available.names, 0, var.az_count)
  private_subnets = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 4, i + 8)]

  enable_nat_gateway = true
  single_nat_gateway = true

  tags = {
    Project = local.name
  }
}

data "aws_availability_zones" "available" {}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.29"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  enable_cluster_creator_admin_permissions = true
  cluster_endpoint_public_access           = true


  eks_managed_node_groups = {
    default = {
      instance_types = ["t2.medium"]
      min_size       = 2
      max_size       = 4
      desired_size   = 2
    }
  }

  tags = {
    Project = local.name
  }
}

########################
# GitOps & Observability (Helm)
########################
module "argocd" {
  source       = "./modules/argocd"
  project_name = local.name
}

module "observability" {
  source       = "./modules/observability"
  project_name = local.name
}

module "gatekeeper" {
  source       = "./modules/gatekeeper"
  project_name = local.name
}

########################
# Eventing + Incident store
########################
module "eventing" {
  source       = "./modules/eventbridge"
  project_name = local.name
}

module "incidents_bucket" {
  source       = "./modules/s3_incidents"
  project_name = local.name
}

module "iam" {
  source              = "./modules/iam"
  project_name        = local.name
  incident_bucket_arn = module.incidents_bucket.bucket_arn
  event_bus_arn       = module.eventing.event_bus_arn
}

module "bundler_lambda" {
  source                         = "./modules/lambda_incident_bundler"
  project_name                   = local.name
  incident_bucket_name           = module.incidents_bucket.bucket_name
  event_bus_name                 = module.eventing.event_bus_name
  role_arn                       = module.iam.bundler_role_arn
  aws_region                     = var.aws_region
  cluster_name                   = var.cluster_name
  prometheus_query_url           = var.prometheus_query_url
  enable_k8s_readonly_enrichment = var.enable_k8s_readonly_enrichment
  incidents_table_name           = module.incidents_table.table_name
}

module "agent_lambda" {
  source                  = "./modules/lambda_llm_agent"
  project_name            = local.name
  role_arn                = module.iam.agent_role_arn
  github_owner            = var.github_owner
  github_repo             = var.github_repo
  github_token_secret_arn = var.github_token_secret_arn
  model_provider          = var.model_provider
  aws_region              = var.aws_region
  cluster_name            = var.cluster_name
  prometheus_query_url    = var.prometheus_query_url
}

module "verifier_lambda" {
  source                  = "./modules/lambda_verifier"
  project_name            = local.name
  role_arn                = module.iam.verifier_role_arn
  aws_region              = var.aws_region
  cluster_name            = var.cluster_name
  prometheus_query_url    = var.prometheus_query_url
  slack_webhook_url       = var.slack_webhook_url
  event_bus_name          = module.eventing.event_bus_name
  github_owner            = var.github_owner
  github_repo             = var.github_repo
  github_token_secret_arn = var.github_token_secret_arn
}

module "rules" {
  source         = "./modules/eventbridge_rules"
  project_name   = local.name
  event_bus_name = module.eventing.event_bus_name

  bundler_lambda_arn  = module.bundler_lambda.lambda_arn
  agent_lambda_arn    = module.agent_lambda.lambda_arn
  verifier_lambda_arn = module.verifier_lambda.lambda_arn
}

########################
# Permissions: allow EventBridge -> Lambda invoke
########################
resource "aws_lambda_permission" "eventbridge_invoke_bundler" {
  statement_id  = "AllowExecutionFromEventBridgeBundler"
  action        = "lambda:InvokeFunction"
  function_name = module.bundler_lambda.lambda_name
  principal     = "events.amazonaws.com"
  source_arn    = module.rules.alert_in_rule_arn
}

resource "aws_lambda_permission" "eventbridge_invoke_agent" {
  statement_id  = "AllowExecutionFromEventBridgeAgent"
  action        = "lambda:InvokeFunction"
  function_name = module.agent_lambda.lambda_name
  principal     = "events.amazonaws.com"
  source_arn    = module.rules.bundle_created_rule_arn
}

resource "aws_lambda_permission" "eventbridge_invoke_verifier" {
  statement_id  = "AllowExecutionFromEventBridgeVerifier"
  action        = "lambda:InvokeFunction"
  function_name = module.verifier_lambda.lambda_name
  principal     = "events.amazonaws.com"
  source_arn    = module.rules.verify_rule_arn
}

########################
# API Gateway (Webhook intake) -> Bundler Lambda
########################
module "webhook" {
  source              = "./modules/apigw_webhook"
  count               = var.enable_api_gateway ? 1 : 0
  project_name        = local.name
  bundler_lambda_arn  = module.bundler_lambda.lambda_arn
  bundler_lambda_name = module.bundler_lambda.lambda_name
}

output "webhook_url" {
  value       = var.enable_api_gateway ? module.webhook[0].webhook_url : null
  description = "Send Alertmanager webhooks here (POST)."
}


module "incidents_table" {
  source       = "./modules/dynamodb_incidents"
  project_name = local.name
}
