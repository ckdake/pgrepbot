locals {
  # Use provided region or current region
  region = var.region != null ? var.region : data.aws_region.current.name

  # Standard tags applied to all resources
  tags = {
    Application = var.application
    Environment = var.environment
    ManagedBy   = "terraform"
    Repository  = "postgres-replication-manager"
  }

  # Resource naming
  name_prefix = "${var.application}-${var.environment}"

  # Subnet IDs from data sources
  private_subnet_ids = data.aws_subnets.private.ids
  public_subnet_ids  = data.aws_subnets.public.ids

  # Container environment variables
  container_environment = [
    {
      name  = "AWS_DEFAULT_REGION"
      value = local.region
    },
    {
      name  = "REDIS_HOST"
      value = aws_elasticache_replication_group.redis.primary_endpoint_address
    },
    {
      name  = "REDIS_PORT"
      value = tostring(aws_elasticache_replication_group.redis.port)
    },
    {
      name  = "REDIS_URL"
      value = "redis://${aws_elasticache_replication_group.redis.primary_endpoint_address}:${aws_elasticache_replication_group.redis.port}"
    }
  ]

  # Container secrets from AWS Secrets Manager
  container_secrets = concat(
    var.auth_key != null ? [
      {
        name      = "AUTH_KEY"
        valueFrom = aws_secretsmanager_secret.auth_key[0].arn
      }
    ] : [],
    # Add database secrets as environment variables for bootstrap
    [
      for i, secret_arn in var.database_secret_arns : {
        name      = "DATABASE_SECRET_${i + 1}"
        valueFrom = secret_arn
      }
    ]
  )

  # Health check configuration
  health_check = {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    path                = "/health"
    matcher             = "200"
    protocol            = "HTTP"
    port                = "traffic-port"
  }
}