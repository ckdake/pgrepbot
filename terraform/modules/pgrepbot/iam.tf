# ECS Task Execution Role
resource "aws_iam_role" "ecs_task_execution_role" {
  name_prefix        = "${local.name_prefix}-ecs-execution-"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_execution_role.json

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_role" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Additional permissions for Secrets Manager and ECR
resource "aws_iam_role_policy" "ecs_task_execution_additional" {
  name_prefix = "${local.name_prefix}-ecs-execution-additional-"
  role        = aws_iam_role.ecs_task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = concat(
          [
            "arn:aws:secretsmanager:${local.region}:${data.aws_caller_identity.current.account_id}:secret:${local.name_prefix}/*"
          ],
          var.database_secret_arns
        )
      }
    ], var.container_registry_arn != null ? [
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = [var.container_registry_arn]
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        Resource = ["*"]
      }
    ] : [], var.kms_key_arn != null ? [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = [var.kms_key_arn]
      }
    ] : [])
  })
}

# ECS Task Role (for application permissions)
resource "aws_iam_role" "ecs_task_role" {
  name_prefix        = "${local.name_prefix}-ecs-task-"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_role.json

  tags = local.tags
}

resource "aws_iam_role_policy" "app_permissions" {
  name_prefix = "${local.name_prefix}-app-permissions-"
  role        = aws_iam_role.ecs_task_role.id
  policy      = data.aws_iam_policy_document.app_permissions.json
}

# Auto Scaling Role
resource "aws_iam_role" "ecs_autoscale_role" {
  count = var.enable_auto_scaling ? 1 : 0

  name_prefix = "${local.name_prefix}-ecs-autoscale-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "application-autoscaling.amazonaws.com"
        }
      }
    ]
  })

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "ecs_autoscale_role" {
  count = var.enable_auto_scaling ? 1 : 0

  role       = aws_iam_role.ecs_autoscale_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSServiceRolePolicy"
}