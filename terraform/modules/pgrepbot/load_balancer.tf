# Target Group for the application
resource "aws_lb_target_group" "app" {
  name        = "${local.name_prefix}-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  # Health check configuration
  health_check {
    enabled             = local.health_check.enabled
    healthy_threshold   = local.health_check.healthy_threshold
    unhealthy_threshold = local.health_check.unhealthy_threshold
    timeout             = local.health_check.timeout
    interval            = local.health_check.interval
    path                = local.health_check.path
    matcher             = local.health_check.matcher
    protocol            = local.health_check.protocol
    port                = local.health_check.port
  }

  # Deregistration delay
  deregistration_delay = 30

  # Stickiness (disabled for stateless app)
  stickiness {
    type            = "lb_cookie"
    cookie_duration = 1
    enabled         = false
  }

  tags = local.tags

  lifecycle {
    create_before_destroy = true
  }
}

# Listener Rule for the existing HTTPS listener
resource "aws_lb_listener_rule" "app" {
  listener_arn = var.existing_alb_listener_arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }

  condition {
    host_header {
      values = [var.domain_name]
    }
  }

  tags = local.tags
}

# Route 53 Record pointing to the existing ALB
resource "aws_route53_record" "app" {
  zone_id = data.aws_route53_zone.domain.zone_id
  name    = var.domain_name
  type    = "CNAME"
  ttl     = 300
  records = [data.aws_lb.existing.dns_name]
}