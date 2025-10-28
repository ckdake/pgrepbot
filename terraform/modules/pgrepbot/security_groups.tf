# Security group rule to allow existing ALB to reach ECS service
resource "aws_security_group_rule" "alb_to_ecs" {
  type                     = "egress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs_service.id
  security_group_id        = var.existing_alb_security_group_id
  description              = "Allow ALB to reach ${local.name_prefix} ECS service"
}

# ECS Service Security Group
resource "aws_security_group" "ecs_service" {
  name_prefix = "${local.name_prefix}-ecs-"
  vpc_id      = var.vpc_id
  description = "Security group for ${local.name_prefix} ECS service"

  tags = merge(local.tags, {
    Name = "${local.name_prefix}-ecs-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# ECS ingress rule - HTTP from existing ALB
resource "aws_security_group_rule" "ecs_ingress_alb" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  source_security_group_id = var.existing_alb_security_group_id
  security_group_id        = aws_security_group.ecs_service.id
  description              = "HTTP from existing ALB"
}

# ECS egress rule - all outbound traffic
resource "aws_security_group_rule" "ecs_egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.ecs_service.id
  description       = "All outbound traffic"
}

# ECS egress rules - connection to allowed security groups
resource "aws_security_group_rule" "ecs_egress_to_allowed_sgs" {
  for_each = toset(var.allowed_egress_security_groups)

  type                     = "egress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  source_security_group_id = each.value
  security_group_id        = aws_security_group.ecs_service.id
  description              = "Connection to security group ${each.value}"
}

# Redis Security Group
resource "aws_security_group" "redis" {
  name_prefix = "${local.name_prefix}-redis-"
  vpc_id      = var.vpc_id
  description = "Security group for ${local.name_prefix} Redis cluster"

  tags = merge(local.tags, {
    Name = "${local.name_prefix}-redis-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# Redis ingress rule - Redis port from ECS service
resource "aws_security_group_rule" "redis_ingress_ecs" {
  type                     = "ingress"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs_service.id
  security_group_id        = aws_security_group.redis.id
  description              = "Redis from ECS service"
}