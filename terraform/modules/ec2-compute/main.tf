data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }
}

# --- IAM ---

resource "aws_iam_role" "this" {
  name = "${var.customer}-${var.environment}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "ebs_manage" {
  name = "${var.customer}-${var.environment}-ebs-manage"
  role = aws_iam_role.this.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EBSDescribe"
        Effect = "Allow"
        Action = [
          "ec2:DescribeVolumes",
          "ec2:DescribeVolumeStatus",
        ]
        Resource = "*"
      },
      {
        Sid    = "EBSAttachDetach"
        Effect = "Allow"
        Action = [
          "ec2:AttachVolume",
          "ec2:DetachVolume",
        ]
        Resource = "arn:aws:ec2:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:volume/*"
        Condition = {
          StringEquals = {
            "ec2:AvailabilityZone" = var.availability_zone
          }
        }
      },
      {
        Sid      = "EC2DescribeSelf"
        Effect   = "Allow"
        Action   = "ec2:DescribeInstances"
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_instance_profile" "this" {
  name = "${var.customer}-${var.environment}-instance-profile"
  role = aws_iam_role.this.name

  tags = var.tags
}

# --- EBS ---

resource "aws_ebs_volume" "data" {
  availability_zone = var.availability_zone
  size              = var.ebs_volume_size
  type              = "gp3"
  encrypted         = true

  tags = merge(var.tags, {
    Name     = "${var.customer}-${var.environment}-data"
    Snapshot = "true"
  })
}

resource "aws_volume_attachment" "data" {
  device_name  = var.ebs_device_name
  volume_id    = aws_ebs_volume.data.id
  instance_id  = aws_instance.this.id
  skip_destroy = var.environment == "production"

  stop_instance_before_detaching = true
}

# --- EC2 ---

resource "aws_instance" "this" {
  ami                         = data.aws_ami.amazon_linux_2023.id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = var.security_group_ids
  iam_instance_profile        = aws_iam_instance_profile.this.name
  key_name                    = var.key_name
  user_data_base64            = base64encode(local.user_data)
  user_data_replace_on_change = true

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  monitoring = true

  tags = merge(var.tags, {
    Name = "${var.customer}-${var.environment}-app"
  })

  depends_on = [aws_iam_role_policy.ebs_manage]
}

# --- Data sources for IAM ---

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

# --- User data template ---

locals {
  user_data = templatefile("${path.module}/templates/user_data.sh", {
    customer        = var.customer
    environment     = var.environment
    ebs_device_name = var.ebs_device_name
    ebs_mount_point = var.ebs_mount_point
    app_port        = var.app_port
    customer_domain = var.customer_domain
  })
}
