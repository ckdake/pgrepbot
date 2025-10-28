# PostgreSQL Replication Manager - Terraform Module

This Terraform module deploys the PostgreSQL Replication Manager to AWS using ECS Fargate, Application Load Balancer, and ElastiCache Redis.

## Architecture

The module creates:

- **ECS Fargate Cluster**: Runs the application containers
- **Application Load Balancer**: Provides HTTPS termination and load balancing
- **ElastiCache Redis**: Caches configuration and metrics
- **Security Groups**: Network security with least privilege access
- **IAM Roles**: Service roles with minimal required permissions
- **Secrets Manager**: Secure storage for authentication keys and database credentials
- **CloudWatch Logs**: Centralized logging for monitoring and debugging

## Quick Start

### Prerequisites

1. AWS CLI configured with appropriate permissions
2. Terraform >= 1.0 installed
3. A VPC with public and private subnets named with "-public" and "-private" suffixes
4. Container image pushed to ECR
5. (Optional) RDS-managed secrets for database credentials
6. (Optional) ACM certificate for HTTPS
7. (Optional) Route 53 hosted zone for custom domain

### Subnet Discovery

The module automatically discovers subnets by name pattern:
- Private subnets: Names ending with "-private" 
- Public subnets: Names ending with "-public"

### Basic Usage

```hcl
module "postgres_replication_manager" {
  source = "./terraform/modules/pgrepbot"

  # Required variables
  application = "postgres-replication-manager"
  environment = "prod"
  vpc_id      = "vpc-12345678"

  # Container registry for ECR permissions
  container_registry_arn = "arn:aws:ecr:us-east-1:123456789012:repository/postgres-replication-manager"

  # Optional: Custom domain and HTTPS
  domain_name     = "replication.example.com"
  certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012"

  # Optional: Database secrets for bootstrap
  database_secret_arns = [
    "arn:aws:secretsmanager:us-east-1:123456789012:secret:rds-db-credentials/cluster-ABC123/postgres-AbCdEf"
  ]

  # Optional: Development auth key
  auth_key = "your-secure-auth-key-here"

  # Optional: Resource sizing
  container_cpu    = 1024
  container_memory = 2048
  desired_count    = 2

  # Optional: Redis configuration
  redis_node_type       = "cache.t3.small"
  redis_num_cache_nodes = 2

  # Optional: Security
  allowed_ingress_cidr_blocks = ["10.0.0.0/8", "172.16.0.0/12"]
}
```

### Development Environment

```hcl
module "postgres_replication_manager_dev" {
  source = "./terraform/modules/pgrepbot"

  application = "postgres-replication-manager"
  environment = "dev"
  
  vpc_id             = "vpc-12345678"
  private_subnet_ids = ["subnet-12345678", "subnet-87654321"]
  public_subnet_ids  = ["subnet-abcdef12", "subnet-21fedcba"]

  # Development settings
  container_cpu             = 256
  container_memory          = 512
  desired_count            = 1
  enable_auto_scaling      = false
  enable_deletion_protection = false
  
  # Allow broader access for development
  allowed_ingress_cidr_blocks = ["0.0.0.0/0"]
  
  # Development auth key
  auth_key = "dev-auth-key-12345"
}
```

### Production Environment

```hcl
module "postgres_replication_manager_prod" {
  source = "./terraform/modules/pgrepbot"

  application = "postgres-replication-manager"
  environment = "prod"
  
  vpc_id             = "vpc-12345678"
  private_subnet_ids = ["subnet-12345678", "subnet-87654321"]
  public_subnet_ids  = ["subnet-abcdef12", "subnet-21fedcba"]

  # Production domain and HTTPS
  domain_name     = "replication.example.com"
  certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012"

  # Production sizing
  container_cpu    = 1024
  container_memory = 2048
  desired_count    = 3
  min_capacity     = 2
  max_capacity     = 10

  # Production Redis
  redis_node_type         = "cache.r6g.large"
  redis_num_cache_nodes   = 3
  enable_redis_encryption = true

  # Security
  enable_deletion_protection = true
  allowed_ingress_cidr_blocks = ["10.0.0.0/8"]
  
  # Use Secrets Manager for auth (don't specify auth_key)
  # Configure authentication through AWS Secrets Manager instead
}
```



## Connecting to Databases

The module automatically handles security group connectivity. Simply specify your database security groups in `allowed_egress_security_groups` and the module creates all necessary rules:

```hcl
module "postgres_replication_manager" {
  source = "./terraform/modules/pgrepbot"
  
  # ... other variables ...
  
  # Automatically creates egress rules to these security groups
  allowed_egress_security_groups = [
    "sg-database123",  # Your RDS cluster security group
    "sg-replica456"    # Your replica security group
  ]
}
```

No additional security group rules needed - the module handles everything automatically.

## Database Credentials

### Using RDS-Managed Secrets

The recommended approach is to use RDS-managed secrets that are automatically created when you enable Secrets Manager integration for your RDS instances. These secrets are in the correct format and are automatically rotated.

Pass the ARNs of these secrets to the module:

```hcl
module "postgres_replication_manager" {
  source = "./terraform/modules/pgrepbot"
  
  # ... other variables ...
  
  # RDS-managed secrets (recommended)
  database_secret_arns = [
    "arn:aws:secretsmanager:us-east-1:123456789012:secret:rds-db-credentials/cluster-ABC123/postgres-AbCdEf",
    "arn:aws:secretsmanager:us-east-1:123456789012:secret:rds-db-credentials/instance-XYZ789/postgres-GhIjKl"
  ]
  
  # If using customer-managed KMS keys
  kms_key_arn = "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012"
}
```

### RDS Secret Format

RDS-managed secrets have the following JSON format:
```json
{
  "username": "postgres",
  "password": "your-password",
  "engine": "postgres",
  "host": "mydb.cluster-xyz.us-east-1.rds.amazonaws.com",
  "port": 5432,
  "dbname": "postgres",
  "dbClusterIdentifier": "mydb-cluster"
}
```

### KMS Permissions

If your secrets are encrypted with customer-managed KMS keys, you may need to update the key policy to allow the ECS task role to decrypt secrets:

```json
{
  "Sid": "AllowECSTaskRoleAccess",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::123456789012:role/postgres-replication-manager-prod-ecs-task-*"
  },
  "Action": [
    "kms:Decrypt",
    "kms:DescribeKey"
  ],
  "Resource": "*"
}
```

## Monitoring and Logging

The module sets up CloudWatch logging for:
- Application logs: `/ecs/${application}-${environment}`
- Redis slow logs: `/aws/elasticache/${application}-${environment}/redis/slow-log`
- ECS Exec logs: `/aws/ecs/${application}-${environment}/exec`

## Security Considerations

1. **Network Security**: The application runs in private subnets with security groups restricting access
2. **Secrets Management**: Use AWS Secrets Manager for production credentials
3. **Encryption**: Redis encryption is always enabled (at rest and in transit)
4. **IAM Roles**: Minimal required permissions following least privilege principle
5. **HTTPS**: Uses existing ALB with HTTPS listener and certificates
6. **Logging**: CloudWatch logs retained for 365 days for compliance and auditing

### Hardcoded Security Defaults

The module enforces secure defaults that cannot be overridden:
- **Redis Encryption**: Always enabled (at rest, in transit, auth token)
- **Log Retention**: Always 365 days for compliance
- **IAM Authentication**: Ready for IAM-based database authentication

## Cost Optimization

For development environments:
- Use smaller instance types (`cache.t3.micro`, `256 CPU/512 MB memory`)
- Disable auto scaling
- Reduce log retention periods
- Use single AZ deployments

For production environments:
- Enable auto scaling to handle traffic spikes
- Use appropriate instance sizes based on load
- Enable multi-AZ for high availability
- Set up proper backup retention

## Troubleshooting

### Common Issues

1. **ECS Tasks Not Starting**: Check CloudWatch logs in `/ecs/${application}-${environment}`
2. **Load Balancer Health Checks Failing**: Verify security group rules and application health endpoint
3. **Redis Connection Issues**: Check security group rules between ECS and ElastiCache
4. **Database Connection Issues**: Verify security group rules and credentials in Secrets Manager

### Debugging

Use ECS Exec to debug running containers:

```bash
aws ecs execute-command \
  --cluster ${cluster_name} \
  --task ${task_arn} \
  --container app \
  --interactive \
  --command "/bin/bash"
```

## License

This module is released under the MIT License. See [LICENSE.md](../../../LICENSE.md) for details.