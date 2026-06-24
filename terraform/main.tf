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

locals {
  common_tags = {
    Project     = "DevOpsPilot"
    Customer    = var.customer_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }

  customer_domain = "${var.customer_name}.${var.root_domain}"
  ebs_device_name = "/dev/sdf"
}

# --- ALB Security Group ---

resource "aws_security_group" "alb" {
  name        = "${var.customer_name}-${var.environment}-alb-sg"
  description = "Security group for ALB (${var.customer_name} ${var.environment})"
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
    Name = "${var.customer_name}-${var.environment}-alb-sg"
  })
}

module "networking" {
  source = "./modules/networking"

  customer_name         = var.customer_name
  environment           = var.environment
  vpc_id                = data.aws_vpc.default.id
  app_port              = var.app_port
  ssh_cidr_blocks       = var.ssh_cidr_blocks
  alb_security_group_id = aws_security_group.alb.id
  tags                  = local.common_tags
}

module "compute" {
  source = "./modules/ec2-compute"

  customer_name      = var.customer_name
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
  db_password        = var.db_password
  tags               = local.common_tags
}

resource "aws_eip" "this" {
  domain   = "vpc"
  instance = module.compute.instance_id

  tags = merge(local.common_tags, {
    Name = "${var.customer_name}-${var.environment}-eip"
  })
}

# --- ALB ---

resource "aws_lb_target_group" "this" {
  name        = "${var.customer_name}-${var.environment}-tg"
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
  name               = "${var.customer_name}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.all_default.ids

  enable_deletion_protection = var.environment == "production"

  tags = merge(local.common_tags, {
    Name = "${var.customer_name}-${var.environment}-alb"
  })
}

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
