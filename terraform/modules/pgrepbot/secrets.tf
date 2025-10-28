# Auth Key Secret (if provided)
resource "aws_secretsmanager_secret" "auth_key" {
  count = var.auth_key != null ? 1 : 0

  name_prefix             = "${local.name_prefix}-auth-key-"
  description             = "Authentication key for ${local.name_prefix}"
  recovery_window_in_days = var.enable_deletion_protection ? 30 : 0

  tags = local.tags
}

resource "aws_secretsmanager_secret_version" "auth_key" {
  count = var.auth_key != null ? 1 : 0

  secret_id     = aws_secretsmanager_secret.auth_key[0].id
  secret_string = var.auth_key
}

# Note: Database credentials are provided via var.database_secret_arns
# These should be existing secrets in RDS format containing PostgreSQL credentials
# The application will bootstrap these secrets into Redis on startup

# Additional application-specific secrets can be added here as needed