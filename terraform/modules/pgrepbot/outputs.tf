output "application_url" {
  description = "URL to access the application"
  value       = "https://${var.domain_name}"
}

output "target_group_arn" {
  description = "ARN of the target group"
  value       = aws_lb_target_group.app.arn
}

output "listener_rule_arn" {
  description = "ARN of the listener rule"
  value       = aws_lb_listener_rule.app.arn
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "Name of the ECS service"
  value       = aws_ecs_service.app.name
}

output "redis_endpoint" {
  description = "Redis primary endpoint"
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "redis_port" {
  description = "Redis port"
  value       = aws_elasticache_replication_group.redis.port
}

output "route53_record_fqdn" {
  description = "FQDN of the Route 53 record"
  value       = aws_route53_record.app.fqdn
}

output "security_group_ecs_id" {
  description = "ID of the ECS service security group"
  value       = aws_security_group.ecs_service.id
}

output "security_group_redis_id" {
  description = "ID of the Redis security group"
  value       = aws_security_group.redis.id
}

output "secrets_manager_auth_key_arn" {
  description = "ARN of the auth key secret (if created)"
  value       = var.auth_key != null ? aws_secretsmanager_secret.auth_key[0].arn : null
}

output "database_secret_arns" {
  description = "ARNs of the database secrets provided to the application"
  value       = var.database_secret_arns
}

output "cloudwatch_log_group_app" {
  description = "CloudWatch log group for the application"
  value       = aws_cloudwatch_log_group.app.name
}

output "iam_role_ecs_task_arn" {
  description = "ARN of the ECS task role"
  value       = aws_iam_role.ecs_task_role.arn
}

output "iam_role_ecs_execution_arn" {
  description = "ARN of the ECS task execution role"
  value       = aws_iam_role.ecs_task_execution_role.arn
}

output "private_subnet_ids" {
  description = "Private subnet IDs discovered by the module"
  value       = local.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Public subnet IDs discovered by the module"
  value       = local.public_subnet_ids
}

# Useful for connecting external databases
output "database_connection_security_group_rules" {
  description = "Security group rules to allow the application to connect to databases"
  value = {
    postgresql = {
      type                     = "ingress"
      from_port               = 5432
      to_port                 = 5432
      protocol                = "tcp"
      source_security_group_id = aws_security_group.ecs_service.id
    }
    mysql = {
      type                     = "ingress"
      from_port               = 3306
      to_port                 = 3306
      protocol                = "tcp"
      source_security_group_id = aws_security_group.ecs_service.id
    }
  }
}