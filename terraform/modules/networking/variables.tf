variable "customer_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "app_port" {
  type    = number
  default = 8080
}

variable "ssh_cidr_blocks" {
  type    = list(string)
  default = ["0.0.0.0/0"]
}

variable "alb_security_group_id" {
  description = "Security group ID of the ALB to allow HTTP traffic from"
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
