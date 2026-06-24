output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.this.id
}

output "instance_public_ip" {
  description = "Public IP address of the EC2 instance"
  value       = aws_instance.this.public_ip
}

output "instance_private_ip" {
  description = "Private IP address of the EC2 instance"
  value       = aws_instance.this.private_ip
}

output "instance_az" {
  description = "Availability zone of the EC2 instance"
  value       = aws_instance.this.availability_zone
}

output "iam_role_name" {
  description = "IAM role name attached to the instance profile"
  value       = aws_iam_role.this.name
}

output "iam_role_arn" {
  description = "IAM role ARN"
  value       = aws_iam_role.this.arn
}

output "ebs_volume_id" {
  description = "EBS volume ID for persistent data"
  value       = aws_ebs_volume.data.id
}

output "ami_id" {
  description = "AMI ID used for the EC2 instance"
  value       = data.aws_ami.amazon_linux_2023.id
}
