output "customer_name" {
  description = "Customer name used for this deployment"
  value       = var.customer_name
}

output "environment" {
  description = "Deployment environment (staging/production)"
  value       = var.environment
}

output "customer_url" {
  description = "Customer-facing URL"
  value       = var.create_dns_resources ? "https://${local.customer_domain}" : "http://${aws_lb.this.dns_name}"
}

output "website_url" {
  description = "Legacy alias for customer_url"
  value       = var.create_dns_resources ? "https://${local.customer_domain}" : "http://${aws_lb.this.dns_name}"
}

output "alb_dns_name" {
  description = "ALB DNS name for the customer deployment"
  value       = aws_lb.this.dns_name
}

output "alb_zone_id" {
  description = "ALB canonical hosted zone ID"
  value       = aws_lb.this.zone_id
}

output "acm_certificate_arn" {
  description = "ACM certificate ARN"
  value       = try(aws_acm_certificate.this[0].arn, null)
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = module.compute.instance_id
}

output "instance_public_ip" {
  description = "Public IP address"
  value       = module.compute.instance_public_ip
}

output "instance_private_ip" {
  description = "Private IP address"
  value       = module.compute.instance_private_ip
}

output "elastic_ip" {
  description = "Elastic IP address assigned to the instance"
  value       = aws_eip.this.public_ip
}

output "elastic_ip_id" {
  description = "Elastic IP allocation ID"
  value       = aws_eip.this.id
}

output "route53_fqdn" {
  description = "Route53 FQDN for the customer deployment"
  value       = try(aws_route53_record.this[0].fqdn, null)
}

output "iam_role_name" {
  description = "IAM role name attached to EC2"
  value       = module.compute.iam_role_name
}

output "iam_role_arn" {
  description = "IAM role ARN"
  value       = module.compute.iam_role_arn
}

output "ebs_volume_id" {
  description = "EBS volume ID for persistent data"
  value       = module.compute.ebs_volume_id
}

output "security_group_id" {
  description = "Security group ID"
  value       = module.networking.security_group_id
}

output "security_group_name" {
  description = "Security group name"
  value       = module.networking.security_group_name
}

output "alb_security_group_id" {
  description = "ALB security group ID"
  value       = aws_security_group.alb.id
}

output "availability_zone" {
  description = "Availability zone where resources are deployed"
  value       = module.compute.instance_az
}

output "ami_id" {
  description = "AMI ID used"
  value       = module.compute.ami_id
}

output "alb_target_group_arn" {
  description = "ALB target group ARN"
  value       = aws_lb_target_group.this.arn
}
