variable "application" {
  type        = string
  description = "Name of the application, used as AWS tag"
  default     = "postgres-replication-manager"
}

variable "environment" {
  type        = string
  description = "Name of the environment, used as AWS tag"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "region" {
  type        = string
  description = "AWS region to deploy resources in"
  default     = null
}

variable "vpc_id" {
  type        = string
  description = "VPC ID to deploy resources into"
}

variable "private_subnet_name_filter" {
  type        = string
  description = "Name filter for private subnets (subnets ending with this will be used)"
  default     = "*-private"
}

variable "public_subnet_name_filter" {
  type        = string
  description = "Name filter for public subnets (subnets ending with this will be used)"
  default     = "*-public"
}



variable "allowed_egress_security_groups" {
  type        = list(string)
  description = "List of security group IDs the application is allowed to connect to"
  default     = []
}

variable "container_image" {
  type        = string
  description = "Docker image for the application"
  default     = "postgres-replication-manager:latest"
}

variable "container_registry_arn" {
  type        = string
  description = "ARN of the container registry (ECR repository) for IAM permissions"
  default     = null
}

variable "database_secret_arns" {
  type        = list(string)
  description = "List of AWS Secrets Manager ARNs containing PostgreSQL credentials in RDS format"
  default     = []
}

variable "kms_key_arn" {
  type        = string
  description = "KMS key ARN for decrypting secrets (if using customer-managed keys)"
  default     = null
}

variable "container_cpu" {
  type        = number
  description = "CPU units for the container (1024 = 1 vCPU)"
  default     = 512
}

variable "container_memory" {
  type        = number
  description = "Memory for the container in MB"
  default     = 1024
}

variable "desired_count" {
  type        = number
  description = "Desired number of ECS tasks"
  default     = 2
}

variable "enable_auto_scaling" {
  type        = bool
  description = "Enable ECS auto scaling"
  default     = true
}

variable "min_capacity" {
  type        = number
  description = "Minimum number of ECS tasks"
  default     = 1
}

variable "max_capacity" {
  type        = number
  description = "Maximum number of ECS tasks"
  default     = 10
}

variable "redis_node_type" {
  type        = string
  description = "ElastiCache Redis node type"
  default     = "cache.t3.micro"
}

variable "redis_num_cache_nodes" {
  type        = number
  description = "Number of Redis cache nodes"
  default     = 1
}



variable "domain_name" {
  type        = string
  description = "Full domain name for the application (e.g., pgrepbot.example.io)"
}

variable "existing_alb_arn" {
  type        = string
  description = "ARN of existing Application Load Balancer to use"
}

variable "existing_alb_listener_arn" {
  type        = string
  description = "ARN of existing HTTPS listener (443) on the ALB"
}

variable "existing_alb_security_group_id" {
  type        = string
  description = "Security group ID of the existing ALB"
}

variable "enable_deletion_protection" {
  type        = bool
  description = "Enable deletion protection for critical resources"
  default     = true
}

variable "backup_retention_days" {
  type        = number
  description = "Number of days to retain backups"
  default     = 7
}



variable "auth_key" {
  type        = string
  description = "Authentication key for development/testing (use AWS Secrets Manager in production)"
  default     = null
  sensitive   = true
}

