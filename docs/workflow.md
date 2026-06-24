# Deployment Workflow

```
START
  │
  ├─ Admin enters: customer name + template (staging/production)
  │
  ├─ Validate input (alphanumeric, regex)
  │   ├─ Invalid → return to input
  │   └─ Valid → continue
  │
  ├─ Generate terraform.tfvars
  │   Customer, environment, root_domain, availability_zone
  │
  ├─ terraform init
  │
  ├─ terraform plan
  │
  ├─ Confirm deploy?
  │   ├─ Cancel → END
  │   └─ Apply → terraform apply -auto-approve
  │
  ├─ TERRAFORM PROVISIONING
  │   ├─ 1. Security Groups (ALB SG, EC2 SG)
  │   ├─ 2. IAM Role + Policy + Instance Profile
  │   ├─ 3. EBS Volume (gp3, encrypted)
  │   ├─ 4. ALB + Target Group + Listener (HTTP 80/HTTPS 443)
  │   ├─ 5. EC2 Instance + user_data bootstrap
  │   ├─ 6. EBS Attachment
  │   ├─ 7. ACM Certificate + DNS validation records (if enabled)
  │   └─ 8. Route53 ALIAS A record (if enabled)
  │
  ├─ EC2 BOOTSTRAP (user_data.sh)
  │   ├─ 1. Install Docker CE, start daemon
  │   ├─ 2. Install Docker Compose v2.32.0
  │   ├─ 3. Format + mount EBS (/dev/sdf → /mnt/data)
  │   ├─ 4. Write docker-compose.yml + nginx configs
  │   ├─ 5. Validate nginx configs (nginx -t)
  │   └─ 6. docker compose up -d
  │
  ├─ CONTAINER HEALTH
  │   ├─ postgres: pg_isready
  │   ├─ backend: /health on port 8080
  │   └─ frontend: /health on port 80
  │
  ├─ ALB Target Group marks instance healthy
  │
  ├─ OUTPUT
  │   ├─ website_url → https://customer.domain
  │   ├─ alb_dns_name
  │   ├─ elastic_ip
  │   └─ instance_id
  │
  ├─ Streamlit Dashboard shows outputs
  │
  └─ DESTROY?
      ├─ No → Monitor
      └─ Yes → terraform destroy -auto-approve → END
```

## Bootstrap Script Execution

| Step | Description |
|------|-------------|
| 1 | Install Docker CE via yum |
| 2 | Start Docker daemon (`systemctl enable --now docker`) |
| 3 | Install Docker Compose v2.32.0 plugin |
| 4 | Format EBS (`mkfs -t xfs /dev/sdf`) — first boot only |
| 5 | Mount EBS at `/mnt/data` |
| 6 | Persist mount in `/etc/fstab` |
| 7 | Create app directories |
| 8 | Write `docker-compose.yml` and nginx configs |
| 9 | Validate nginx configs |
| 10 | `docker compose up -d` — starts all 3 containers |

## Environment Comparison

| Feature | Staging | Production |
|---------|---------|------------|
| Instance Type | t3.small (2vCPU, 2GiB) | t3.medium (2vCPU, 4GiB) |
| EBS Data Size | 30 GB gp3 | 50 GB gp3 |
| SSH Access | 0.0.0.0/0 | Restricted CIDRs |
| ALB Deletion Protection | Off | On |
| EBS skip_destroy | false | true |
