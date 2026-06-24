# DevOps Pilot — Reviewer Walkthrough

## Prerequisites

- AWS credentials configured (env vars or `~/.aws/credentials`)
- Terraform installed
- SSH key pair in AWS (referenced by `key_name` in tfvars)
- Python 3.10+ for Streamlit dashboard (optional)

---

## Step 1: Terraform Init

```bash
cd terraform
terraform init
```

Initializes the AWS provider and modules. Downloads plugins.

```
Initializing the backend...
Initializing provider plugins...
- Finding hashicorp/aws versions matching "~> 5.0"...
- Installing hashicorp/aws v5.100.0...
- Installed hashicorp/aws v5.100.0 (signed by HashiCorp)
Terraform has been successfully initialized!
```

---

## Step 2: Terraform Plan

```bash
terraform plan -var="customer=demo" ^
  -var="environment=staging" ^
  -var="root_domain=demo.example.com" ^
  -var="availability_zone=us-east-1a" ^
  -var="create_dns_resources=false"
```

Review the execution plan. Expected output:

```
Plan: 15 to add, 0 to change, 0 to destroy.
```

With `create_dns_resources=true` (real domain + Route53 zone):

```
Plan: 17 to add, 0 to change, 0 to destroy.
```

![Terraform Apply Success](screenshots/Terraform%20Apply%20Success.png)

---

## Step 3: Terraform Apply

```bash
terraform apply -var="customer=demo" ^
  -var="environment=staging" ^
  -var="root_domain=demo.example.com" ^
  -var="availability_zone=us-east-1a" ^
  -var="create_dns_resources=false" ^
  -auto-approve
```

Deployment takes approximately 3 minutes. On completion:

```
Apply complete! Resources: 15 added, 0 changed, 0 destroyed.

Outputs:

alb_dns_name = "demo-alb-123456.us-east-1.elb.amazonaws.com"
elastic_ip = "54.123.45.67"
instance_id = "i-0abc123def456"
website_url = "http://demo-alb-123456.us-east-1.elb.amazonaws.com"
```

---

## Step 4: Infrastructure Verification

### EC2 Instance

```bash
aws ec2 describe-instances --instance-ids i-0abc123def456 ^
  --query "Reservations[0].Instances[0].State.Name"
# running
```

![EC2 Instance Running](screenshots/EC2%20Instance%20Running.png)

### ALB Configuration

```bash
aws elbv2 describe-load-balancers ^
  --names demo-alb ^
  --query "LoadBalancers[0].DNSName"
# demo-alb-123456.us-east-1.elb.amazonaws.com
```

![Load Balancer](screenshots/Load%20Balancer.png)

### Target Group Health

```bash
aws elbv2 describe-target-health ^
  --target-group-arn $(terraform output -raw alb_target_group_arn) ^
  --query "TargetHealthDescriptions[*].TargetHealth"
# State: healthy
```

![Target Group Healthy](screenshots/Target%20Group%20Healthy.png)

### ALB Health Endpoint

```bash
curl -s http://$(terraform output -raw alb_dns_name)/health
# healthy
```

![Health Endpoint](screenshots/Health%20Endpoint.png)

---

## Step 5: EC2 Verification

### SSM Session Manager

Connect to the EC2 instance via AWS Console > Systems Manager > Session Manager:

```bash
# Or via AWS CLI
aws ssm start-session --target i-0abc123def456
```

![SSM Session Manager](screenshots/SSM%20Session%20Manager.png)

The IAM role includes `AmazonSSMManagedInstanceCore` policy, enabling browser-based shell access.

### Bootstrap Log

```bash
sudo cat /var/log/bootstrap.log
```

Expected output shows all 10 steps completed:

```
[2026-06-24 12:34:56] Step 1: Installing Docker...
[2026-06-24 12:35:10] Step 2: Installed Docker Compose v2.32.0
[2026-06-24 12:35:15] Step 3: Formatted /dev/sdf (first boot)
[2026-06-24 12:35:16] Step 4: Mounted /mnt/data
[2026-06-24 12:35:16] Step 5: Added /etc/fstab entry
[2026-06-24 12:35:17] Step 6: Created app directories
[2026-06-24 12:35:17] Step 7: Wrote configuration files
[2026-06-24 12:35:18] Step 8: nginx config validated successfully
[2026-06-24 12:35:30] Step 9: Docker Compose started
[2026-06-24 12:35:30] Step 10: [SUCCESS] Bootstrap completed successfully
```

![Bootstrap Completion](screenshots/Bootstrap%20Completion.png)

### EBS Volume

```bash
df -h /mnt/data
# Filesystem      Size  Used Avail Use% Mounted on
# /dev/nvme1n1     30G   24K   30G   1% /mnt/data

lsblk
# NAME        MAJ:MIN RM SIZE RO TYPE MOUNTPOINT
# nvme0n1     259:0    0  20G  0 disk /
# nvme1n1     259:1    0  30G  0 disk /mnt/data
```

![EBS Mounted](screenshots/EBS%20Mounted.png)

---

## Step 6: Docker Verification

```bash
docker compose ps
```

Expected output:

```
NAME                    STATUS         PORTS
demo-staging-postgres   Up (healthy)   5432/tcp
demo-staging-backend    Up (healthy)   80/tcp
demo-staging-frontend   Up (healthy)   0.0.0.0:80->80/tcp
```

### Health Endpoints (EC2 Internal)

```bash
curl -s http://localhost/health
# healthy

curl -s http://localhost:8080/health
# healthy
```

![Health Checks Locally](screenshots/Health%20Checks%20Locally.png)

---

## Step 7: Repository Structure

![Repository Structure](screenshots/tree.png)

![EC2 Tree](screenshots/ec2%20tree.png)

---

## Step 8: Clean Up

```bash
terraform destroy -var="customer=demo" ^
  -var="environment=staging" ^
  -var="root_domain=demo.example.com" ^
  -var="availability_zone=us-east-1a" ^
  -var="create_dns_resources=false" ^
  -auto-approve
```

```
Destroy complete! Resources: 15 destroyed.
```

## Verification Checklist

| Step | Verification | Status |
|------|-------------|--------|
| 1 | `terraform validate` returns success | ✓ |
| 2 | `terraform plan` shows 15 to add | ✓ |
| 3 | `terraform apply` completes with 15 added | ✓ |
| 4 | EC2 instance in `running` state | ✓ |
| 5 | ALB DNS name resolves | ✓ |
| 6 | Target group shows `healthy` | ✓ |
| 7 | `curl <alb-dns>/health` returns `healthy` | ✓ |
| 8 | SSM Session Manager connects | ✓ |
| 9 | Bootstrap log shows completion | ✓ |
| 10 | EBS mounted at `/mnt/data` | ✓ |
| 11 | `docker compose ps` shows 3 containers | ✓ |
| 12 | Local health checks pass (port 80 + 8080) | ✓ |
| 13 | `terraform destroy` cleans up all resources | ✓ |

## Key Architecture Facts

| Question | Answer |
|----------|--------|
| **Architecture** | ALB -> EC2 (Docker Compose) -> Postgres on EBS |
| **TLS** | ACM cert via DNS validation, auto-renewed |
| **Load balancing** | HTTP:80 -> 301 HTTPS, HTTPS:443 -> Target Group |
| **Storage** | 30GB gp3 EBS (staging) / 50GB gp3 (prod), encrypted, xfs |
| **IAM** | Minimal scope: SSM agent + EBS attach/detach (scoped to AZ) |
| **User Data** | Retry-wrapped, idempotent, pinned Docker Compose v2.32.0 |
| **Subnet selection** | Deterministic `one()` — validates at plan time |
| **Dashboard** | Streamlit, runs `terraform apply/destroy -auto-approve` |
| **Estimated cost** | ~$52/mo staging, ~$94/mo production |
