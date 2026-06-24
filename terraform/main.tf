terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_vpc" "default" {
  default = true
}

# --- ERROR 2 FIX: Deterministic subnet selection ---

data "aws_subnets" "all_default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

data "aws_subnets" "default_in_az" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "availability-zone"
    values = [var.availability_zone]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

data "aws_subnet" "default" {
  id = one(data.aws_subnets.default_in_az.ids)
}

# --- ERROR 1 FIX: Route53 conditional ---

data "aws_route53_zone" "this" {
  count        = var.create_dns_resources ? 1 : 0
  name         = var.root_domain
  private_zone = false
}

locals {
  common_tags = {
    Project     = "DevOpsPilot"
    Customer    = var.customer
    Environment = var.environment
    ManagedBy   = "Terraform"
  }

  customer_domain = "${var.customer}.${var.root_domain}"

  ebs_device_name = "/dev/sdf"
}

# --- ACM Certificate (only with DNS) ---

resource "aws_acm_certificate" "this" {
  count = var.create_dns_resources ? 1 : 0

  domain_name       = local.customer_domain
  validation_method = "DNS"

  subject_alternative_names = ["*.${var.root_domain}"]

  lifecycle {
    create_before_destroy = true
  }

  tags = local.common_tags
}

resource "aws_route53_record" "cert_validation" {
  count = var.create_dns_resources ? length(aws_acm_certificate.this[0].domain_validation_options) : 0

  zone_id = data.aws_route53_zone.this[0].zone_id
  name    = aws_acm_certificate.this[0].domain_validation_options[count.index].resource_record_name
  type    = aws_acm_certificate.this[0].domain_validation_options[count.index].resource_record_type
  records = [aws_acm_certificate.this[0].domain_validation_options[count.index].resource_record_value]
  ttl     = 60
}

resource "aws_acm_certificate_validation" "this" {
  count = var.create_dns_resources ? 1 : 0

  certificate_arn         = aws_acm_certificate.this[0].arn
  validation_record_fqdns = aws_route53_record.cert_validation[*].fqdn
}

# --- ALB Security Group ---

resource "aws_security_group" "alb" {
  name        = "${var.customer}-${var.environment}-alb-sg"
  description = "Security group for ALB (${var.customer} ${var.environment})"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.customer}-${var.environment}-alb-sg"
  })
}

module "networking" {
  source = "./modules/networking"

  customer              = var.customer
  environment           = var.environment
  vpc_id                = data.aws_vpc.default.id
  app_port              = var.app_port
  ssh_cidr_blocks       = var.ssh_cidr_blocks
  alb_security_group_id = aws_security_group.alb.id
  tags                  = local.common_tags
}

module "compute" {
  source = "./modules/ec2-compute"

  customer           = var.customer
  environment        = var.environment
  instance_type      = var.environment == "production" ? "t3.medium" : "t3.small"
  subnet_id          = data.aws_subnet.default.id
  security_group_ids = [module.networking.security_group_id]
  availability_zone  = var.availability_zone
  ebs_volume_size    = var.environment == "production" ? 50 : 30
  root_volume_size   = var.environment == "production" ? 30 : 20
  ebs_device_name    = local.ebs_device_name
  app_port           = var.app_port
  customer_domain    = local.customer_domain
  tags               = local.common_tags
}

resource "aws_eip" "this" {
  domain   = "vpc"
  instance = module.compute.instance_id

  tags = merge(local.common_tags, {
    Name = "${var.customer}-${var.environment}-eip"
  })
}

# --- ALB ---

resource "aws_lb_target_group" "this" {
  name        = "${var.customer}-${var.environment}-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "instance"

  health_check {
    enabled             = true
    path                = "/health"
    port                = "80"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  tags = local.common_tags
}

resource "aws_lb_target_group_attachment" "this" {
  target_group_arn = aws_lb_target_group.this.arn
  target_id        = module.compute.instance_id
  port             = 80
}

resource "aws_lb" "this" {
  name               = "${var.customer}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.all_default.ids

  enable_deletion_protection = var.environment == "production"

  tags = merge(local.common_tags, {
    Name = "${var.customer}-${var.environment}-alb"
  })
}

# HTTP listener: redirect to HTTPS (when DNS enabled) or forward (when DNS disabled)
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  dynamic "default_action" {
    for_each = var.create_dns_resources ? [1] : []
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }

  dynamic "default_action" {
    for_each = var.create_dns_resources ? [] : [1]
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.this.arn
    }
  }
}

resource "aws_lb_listener" "https" {
  count = var.create_dns_resources ? 1 : 0

  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.this[0].arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }
}

# --- Route53 A record (ALIAS to ALB, only with DNS) ---

resource "aws_route53_record" "this" {
  count = var.create_dns_resources ? 1 : 0

  zone_id = data.aws_route53_zone.this[0].zone_id
  name    = local.customer_domain
  type    = "A"

  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}
