variable "customer" {
  type = string
}

variable "environment" {
  type = string
}

variable "customer_domain" {
  description = "Full customer domain (e.g. acme.demo.example.com)"
  type        = string
}

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "subnet_id" {
  type = string
}

variable "security_group_ids" {
  type = list(string)
}

variable "key_name" {
  description = "EC2 key pair name for SSH access"
  type        = string
  default     = null
}

variable "availability_zone" {
  type = string
}

variable "root_volume_size" {
  type    = number
  default = 20
}

variable "ebs_volume_size" {
  type    = number
  default = 30
}

variable "ebs_device_name" {
  type    = string
  default = "/dev/sdf"
}

variable "ebs_mount_point" {
  type    = string
  default = "/mnt/data"
}

variable "app_port" {
  type    = number
  default = 8080
}

variable "tags" {
  type    = map(string)
  default = {}
}
