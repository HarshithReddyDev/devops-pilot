# DevOps Pilot — 5-Minute Walkthrough

## Prerequisites

- AWS credentials configured (env vars or `~/.aws/credentials`)
- Terraform installed
- A Route53 hosted zone (e.g. `demo.example.com`)
- Python 3.10+ with Streamlit (`pip install streamlit`)

---

## Step 1: Deploy via Dashboard (2 min)

```bash
cd dashboard
streamlit run app.py
```

1. Enter **Customer Name**: `acme`
2. Select **Template**: `Staging`
3. Enter **Root Domain**: your real domain (e.g. `demo.example.com`)
4. Enter **Availability Zone**: `us-east-1a`
5. Click **Deploy**

Watch the real-time log stream. Deployment takes ~3 minutes.

---

## Step 2: Verify Deployment (1 min)

When complete, the dashboard shows:

| Output | Value |
|--------|-------|
| ALB DNS | `testco-alb-123456.us-east-1.elb.amazonaws.com` |
| Elastic IP | `54.123.45.67` |
| Instance ID | `i-0abc123def456` |
| EBS Volume | `vol-0abc123def456` |

**Check health:**

```bash
curl -I https://acme.demo.example.com
# HTTP/1.1 200 OK

curl https://acme.demo.example.com/api/health
# {"customer":"acme","environment":"staging","status":"healthy"}
```

---

## Step 3: SSH into Instance (30s)

```bash
ssh -i your-key.pem ec2-user@<elastic-ip>
```

Verify the stack:

```bash
docker compose ps
# NAME                   STATUS         PORTS
# acme-staging-postgres  Up (healthy)   5432/tcp
# acme-staging-backend   Up (healthy)   80/tcp
# acme-staging-frontend  Up (healthy)   0.0.0.0:80->80/tcp

docker compose logs --tail=10 <service>
```

---

## Step 4: Destroy (1 min)

Back in the dashboard:

1. Select **Action**: `Destroy`
2. Click **Destroy**

Or via CLI:

```bash
cd ../terraform
terraform destroy -var="customer=acme" -var="environment=staging" \
  -var="root_domain=demo.example.com" -var="availability_zone=us-east-1a"
```

---

## Key Facts for Ofir

| Question | Answer |
|----------|--------|
| **Architecture** | ALB → EC2 (Docker Compose) → Postgres on EBS |
| **TLS** | ACM cert via DNS validation, auto-renewed |
| **Storage** | 30GB gp3 EBS (staging) / 50GB gp3 EBS (production), encrypted |
| **IAM** | Minimal scope: SSM agent + EBS attach/detach (scoped to AZ) |
| **User Data** | Retry-wrapped, idempotent, pinned Docker Compose v2.32.0 |
| **Dashboard** | Streamlit, runs `terraform apply/destroy -auto-approve` |
| **Estimated cost** | ~$52/mo staging, ~$94/mo production |
