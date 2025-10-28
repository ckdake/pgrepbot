# ElastiCache Subnet Group
resource "aws_elasticache_subnet_group" "redis" {
  name       = "${local.name_prefix}-redis-subnet-group"
  subnet_ids = local.private_subnet_ids

  tags = local.tags
}

# ElastiCache Parameter Group
resource "aws_elasticache_parameter_group" "redis" {
  family = "redis7.x"
  name   = "${local.name_prefix}-redis-params"

  # Optimize for application caching
  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru"
  }

  tags = local.tags
}

# ElastiCache Replication Group
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id         = "${local.name_prefix}-redis"
  description                  = "Redis cluster for ${local.name_prefix}"
  
  # Node configuration
  node_type                    = var.redis_node_type
  port                         = 6379
  parameter_group_name         = aws_elasticache_parameter_group.redis.name
  
  # Cluster configuration
  num_cache_clusters           = var.redis_num_cache_nodes
  
  # Network configuration
  subnet_group_name            = aws_elasticache_subnet_group.redis.name
  security_group_ids           = [aws_security_group.redis.id]
  
  # Security configuration - always encrypted
  at_rest_encryption_enabled   = true
  transit_encryption_enabled   = true
  auth_token_enabled          = true
  
  # Backup configuration
  snapshot_retention_limit     = var.backup_retention_days
  snapshot_window             = "03:00-05:00"
  maintenance_window          = "sun:05:00-sun:07:00"
  
  # Auto failover (requires at least 2 nodes)
  automatic_failover_enabled   = var.redis_num_cache_nodes > 1
  multi_az_enabled            = var.redis_num_cache_nodes > 1
  
  # Engine configuration
  engine_version              = "7.0"
  
  # Logging
  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.redis_slow.name
    destination_type = "cloudwatch-logs"
    log_format       = "text"
    log_type         = "slow-log"
  }

  tags = local.tags

  depends_on = [
    aws_cloudwatch_log_group.redis_slow
  ]
}

# CloudWatch Log Group for Redis
resource "aws_cloudwatch_log_group" "redis_slow" {
  name              = "/aws/elasticache/${local.name_prefix}/redis/slow-log"
  retention_in_days = 365

  tags = local.tags
}