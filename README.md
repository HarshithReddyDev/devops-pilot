# DevOps Pilot

Automated AWS infrastructure deployment with Terraform, Docker Compose, and ALB — a complete DevOps submission for the Ofir assignment.

## Overview

This project provisions a production-ready AWS environment using Infrastructure-as-Code. A single `terraform apply` creates an end-to-end stack: DNS (Route53), TLS (ACM), load balancing (ALB), compute (EC2), container orchestration (Docker Compose), and persistent storage (EBS). A Streamlit dashboard enables self-service deployments.

## Architecture

```
Internet → Route53 → ACM → ALB → EC2 → Docker → Postgres(EBS)
```

| Component | Role |
|-----------|------|
| **VPC** | Default VPC, public subnets across all AZs |
| **Route53** | ALIAS A record to ALB DNS name, DNS validation records for ACM |
| **ACM** | TLS certificate for `customer.domain` + `*.domain`, auto-renewed |
| **ALB** | Application Load Balancer — terminates TLS, HTTP→HTTPS redirect, forwards to target group |
| **Target Group** | Health checks on `/health`, routes to EC2 instance port 80 |
| **Security Groups** | ALB SG (80/443 from internet), EC2 SG (80 from ALB only, 22/8080 restricted) |
| **EC2** | Amazon Linux 2023, IMDSv2, CloudWatch monitoring |
| **IAM Role** | SSM managed instance + EBS attach/detach (scoped to AZ + account) |
| **EBS** | gp3 encrypted volume (30GB staging / 50GB production) |
| **Docker Compose** | Three containers: frontend (nginx:80), backend (nginx:8080), PostgreSQL 16 |

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full ASCII diagram.

## Automated Deployment Flow

```
  1. terraform apply
  2. AWS provisions: VPC subnets, SG, IAM role, EBS, EC2
  3. EC2 boots with user_data.sh bootstrap script
  4. Bootstrap installs Docker CE + Docker Compose v2
  5. EBS volume formatted (xfs) and mounted at /mnt/data
  6. docker-compose.yml and nginx configs written
  7. Nginx configs validated with nginx -t
  8. Docker Compose starts frontend, backend, postgres
  9. Health checks verify /health on both containers
  10. ALB Target Group detects healthy instance
  11. ALB begins serving traffic at https://customer.domain
```

## Project Structure

```
devops-pilot/
├── terraform/                      # Infrastructure-as-Code (Terraform)
│   ├── main.tf                     # Root module: provider, data sources, ACM, ALB, Route53
│   ├── variables.tf                # Input variables with validation
│   ├── outputs.tf                  # Deployment outputs
│   ├── modules/
│   │   ├── ec2-compute/            # EC2 instance, EBS volume, IAM role/policy
│   │   │   └── templates/
│   │   │       └── user_data.sh    # Bootstrap script (Docker, compose, nginx)
│   │   └── networking/             # Security group, ALB ingress rule
│   └── environments/
│       ├── staging/                # t3.small, 30GB EBS, open SSH
│       └── production/            # t3.medium, 50GB EBS, restricted SSH
├── docker/                         # Local Docker Compose development
│   ├── compose.yml                 # Three-service stack
│   ├── frontend/                   # Frontend nginx Dockerfile
│   └── backend/                    # Backend nginx Dockerfile
├── dashboard/                      # Streamlit self-service UI
│   ├── app.py                      # Deploy/destroy dashboard
│   └── requirements.txt            # Python dependencies
├── docs/
│   ├── architecture.md             # Architecture diagram
│   └── workflow.md                 # Deployment workflow
├── ARCHITECTURE.md                 # ASCII architecture diagram
├── COST_ESTIMATE.md                # Monthly cost breakdown
├── DEMO.md                         # 5-minute walkthrough
└── README.md                       # This file
```

## Prerequisites

- **Terraform** >= 1.0 ([install](https://developer.hashicorp.com/terraform/downloads))
- **AWS account** with credentials configured (env vars or `~/.aws/credentials`)
- **Route53 hosted zone** for your domain (e.g. `example.com`)
- **Docker** for local testing ([install](https://docs.docker.com/engine/install/))
- **Python** >= 3.9 for the Streamlit dashboard

## Deployment Instructions

```bash
cd terraform

# 1. Initialize Terraform
terraform init

# 2. Validate configuration
terraform validate

# 3. Review the plan
terraform plan -var-file=environments/staging/terraform.tfvars

# 4. Deploy (with a real domain)
terraform apply -var="customer=acme" -var="environment=staging" \
  -var="root_domain=example.com" -var="availability_zone=us-east-1a"

# Or deploy without a domain (HTTP only, ALB DNS name)
terraform apply -var="customer=acme" -var="environment=staging" \
  -var="root_domain=demo.example.com" -var="availability_zone=us-east-1a" \
  -var="create_dns_resources=false"
```

### Streamlit Dashboard

```bash
cd dashboard
pip install -r requirements.txt
streamlit run app.py
```

Open the URL shown in the terminal, enter customer details, select a template, and click **Deploy**.

## Verification

After deployment completes, verify the infrastructure:

```bash
# Check EC2 instance is running
aws ec2 describe-instances --filters "Name=tag:Customer,Values=acme"

# SSH into the instance (uses Elastic IP)
ssh -i your-key.pem ec2-user@<elastic-ip>

# Verify Docker containers inside the instance
docker ps
# CONTAINER ID   IMAGE                PORTS
# abc123         nginx:alpine         0.0.0.0:80->80/tcp
# def456         nginx:alpine         0.0.0.0:8080->80/tcp
# ghi789         postgres:16-alpine   5432/tcp

# Test health endpoints locally
curl -s http://localhost/health
# healthy

curl -s http://localhost:8080/health
# healthy

# Verify via ALB (get ALB DNS from terraform outputs)
curl -s http://<alb-dns>/health
# healthy

# Verify via custom domain (if DNS enabled)
curl -s https://acme.example.com/health
# healthy
```

### ALB Target Group Health

```bash
# Check target group health via AWS CLI
aws elbv2 describe-target-health \
  --target-group-arn $(terraform output -raw alb_target_group_arn)
# TargetHealth.State: healthy
```

## Demo Instructions (For Reviewers)

### 60-Second Demo

```bash
# 1. Validate
cd terraform && terraform validate

# 2. Plan
terraform plan -var="customer=demo" -var="environment=staging" \
  -var="root_domain=demo.example.com" -var="availability_zone=us-east-1a" \
  -var="create_dns_resources=false"

# 3. Apply
terraform apply -var="customer=demo" -var="environment=staging" \
  -var="root_domain=demo.example.com" -var="availability_zone=us-east-1a" \
  -var="create_dns_resources=false" -auto-approve

# 4. Check outputs
terraform output website_url
# http://demo-alb-123456.us-east-1.elb.amazonaws.com

terraform output alb_dns_name
# demo-alb-123456.us-east-1.elb.amazonaws.com

# 5. Verify ALB serves traffic
curl -s http://$(terraform output -raw alb_dns_name)/health
# healthy

# 6. SSH into EC2
ssh -i your-key.pem ec2-user@$(terraform output -raw elastic_ip)

# 7. Inside EC2 - check bootstrap log
sudo cat /var/log/bootstrap.log | tail -20

# 8. Inside EC2 - check containers
docker compose ps

# 9. Clean up
terraform destroy -var="customer=demo" -var="environment=staging" \
  -var="root_domain=demo.example.com" -var="availability_zone=us-east-1a" \
  -var="create_dns_resources=false" -auto-approve
```

### Expected Outputs

| Check | Expected Result |
|-------|----------------|
| `terraform validate` | `Success! The configuration is valid.` |
| `terraform plan` | `Plan: 15 to add, 0 to change, 0 to destroy.` |
| `terraform apply` | `Apply complete! Resources: 15 added.` |
| `docker ps` | 3 containers running (postgres, backend, frontend) |
| `curl localhost/health` | `healthy` |
| `curl <alb-dns>/health` | `healthy` |
| ALB Target Group | `State: healthy` |

## Clean Up

```bash
cd terraform
terraform destroy -var="customer=acme" -var="environment=staging" \
  -var="root_domain=example.com" -var="availability_zone=us-east-1a"
```

Or use the Streamlit dashboard with the **Destroy** action.

## Environments

| Property | Staging | Production |
|----------|---------|------------|
| Instance | t3.small (2 vCPU, 2 GiB) | t3.medium (2 vCPU, 4 GiB) |
| Root volume | 20 GB gp3 | 30 GB gp3 |
| Data volume | 30 GB gp3 | 50 GB gp3 |
| SSH access | 0.0.0.0/0 | Restricted CIDRs |
| ALB deletion protection | Off | On |
| EBS skip_destroy | false | true |
| Monthly cost | ~$52 | ~$94 |
