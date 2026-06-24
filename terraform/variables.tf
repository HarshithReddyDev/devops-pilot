variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "customer_name" {
  description = "Customer name (lowercase alphanumeric with hyphens, used as DNS prefix and resource naming)"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.customer_name))
    error_message = "Customer name must be lowercase alphanumeric with hyphens."
  }
}

variable "environment" {
  description = "Deployment environment"
  type        = string

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Environment must be 'staging' or 'production'."
  }
}

variable "root_domain" {
  description = "Root DNS domain (e.g. demo.example.com). A Route53 hosted zone must exist for this domain when create_dns_resources is true."
  type        = string
}

variable "availability_zone" {
  description = "Availability zone for EC2 and EBS (e.g. us-east-1a)"
  type        = string
}

variable "create_dns_resources" {
  description = "Create Route53, ACM, and HTTPS resources. Set false for testing without a real domain."
  type        = bool
  default     = true
}

variable "app_port" {
  description = "Internal application port exposed by the backend container"
  type        = number
  default     = 8080
}

variable "ssh_cidr_blocks" {
  description = "CIDR blocks allowed for SSH access"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "db_password" {
  description = "PostgreSQL password. If empty, a random password is generated during bootstrap."
  type        = string
  default     = ""
  sensitive   = true
}
