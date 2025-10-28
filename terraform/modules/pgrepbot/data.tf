data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_vpc" "selected" {
  id = var.vpc_id
}

data "aws_route53_zone" "domain" {
  name         = replace(var.domain_name, "/^[^.]+\\./", "")
  private_zone = false
}

data "aws_lb" "existing" {
  arn = var.existing_alb_arn
}

data "aws_lb_listener" "existing_https" {
  arn = var.existing_alb_listener_arn
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }

  filter {
    name   = "tag:Name"
    values = [var.private_subnet_name_filter]
  }
}

data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }

  filter {
    name   = "tag:Name"
    values = [var.public_subnet_name_filter]
  }
}

data "aws_subnet" "private" {
  for_each = toset(data.aws_subnets.private.ids)
  id       = each.value
}

data "aws_subnet" "public" {
  for_each = toset(data.aws_subnets.public.ids)
  id       = each.value
}

# ECS task execution role policy
data "aws_iam_policy_document" "ecs_task_execution_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ECS task role policy
data "aws_iam_policy_document" "ecs_task_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Application permissions policy
data "aws_iam_policy_document" "app_permissions" {
  # Secrets Manager permissions for app-managed secrets
  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = [
      "arn:aws:secretsmanager:${local.region}:${data.aws_caller_identity.current.account_id}:secret:${local.name_prefix}/*"
    ]
  }

  # Secrets Manager permissions for database secrets
  dynamic "statement" {
    for_each = length(var.database_secret_arns) > 0 ? [1] : []
    content {
      effect = "Allow"
      actions = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ]
      resources = var.database_secret_arns
    }
  }

  # KMS permissions for secret decryption
  dynamic "statement" {
    for_each = var.kms_key_arn != null ? [1] : []
    content {
      effect = "Allow"
      actions = [
        "kms:Decrypt",
        "kms:DescribeKey"
      ]
      resources = [var.kms_key_arn]
    }
  }

  # RDS permissions for discovery and IAM auth
  statement {
    effect = "Allow"
    actions = [
      "rds:DescribeDBInstances",
      "rds:DescribeDBClusters",
      "rds:DescribeDBSubnetGroups",
      "rds:ListTagsForResource"
    ]
    resources = ["*"]
  }

  # RDS IAM authentication
  statement {
    effect = "Allow"
    actions = [
      "rds-db:connect"
    ]
    resources = [
      "arn:aws:rds-db:${local.region}:${data.aws_caller_identity.current.account_id}:dbuser:*/${local.name_prefix}-*"
    ]
  }

  # ElastiCache permissions
  statement {
    effect = "Allow"
    actions = [
      "elasticache:DescribeCacheClusters",
      "elasticache:DescribeReplicationGroups",
      "elasticache:DescribeCacheSubnetGroups"
    ]
    resources = ["*"]
  }

  # CloudWatch Logs permissions
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams"
    ]
    resources = [
      "arn:aws:logs:${local.region}:${data.aws_caller_identity.current.account_id}:log-group:/ecs/${local.name_prefix}*"
    ]
  }
}