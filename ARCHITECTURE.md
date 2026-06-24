# Architecture

```
                          INTERNET
                             |
                    +--------+--------+
                    |                 |
               HTTPS :443         HTTP :80
                    |                 |
                    |        +--------+
                    |        |
             +------v--------v------+
             |   Route53 (ALIAS A)  |
             |   customer.domain    |
             +---------+-----------+
                       |
             +---------v-----------+
             |   ACM Certificate   |
             |   DNS-validated     |
             |   *.domain.com      |
             +---------+-----------+
                       |
             +---------v-----------+
             |   ALB SG            |
             |   Port 80 (0.0.0.0) |
             |   Port 443 (0.0.0.0)|
             +---------+-----------+
                       |
             +---------v-----------+
             |   ALB (Application  |
             |   Load Balancer)    |
             |                     |
             |   HTTP :80          |
             |     -> 301 redirect |
             |     -> HTTPS :443   |
             |   HTTPS :443        |
             |     -> forward TG   |
             +---------+-----------+
                       |
             +---------v-----------+
             |   Target Group      |
             |   Port 80, HTTP     |
             |   /health check     |
             +---------+-----------+
                       |
             +---------v-----------+
             |   EC2 SG            |
             |   Port 22 (SSH)     |
             |   Port 80 (ALB only)|
             |   Port 8080 (app)   |
             +---------+-----------+
                       |
             +---------v-----------+
             |   EC2 Instance      |
             |   Amazon Linux 2023 |
             |   t3.small/medium   |
             |   IMDSv2 enforced   |
             |   IAM instance prof |
             +---------+-----------+
                       |
             +---------v-----------+
             |   Docker Compose    |
             |   (3 containers)    |
             |                     |
             |  +----------------+ |
             |  | frontend       | |
             |  | nginx:alpine   | |
             |  | Port 80        | |
             |  | /api/ -> backend| |
             |  +-------+--------+ |
             |          |          |
             |  +-------v--------+ |
             |  | backend        | |
             |  | nginx:alpine   | |
             |  | Port 8080      | |
             |  | /health 200    | |
             |  +-------+--------+ |
             |          |          |
             |  +-------v--------+ |
             |  | postgres:16    | |
             |  | pg_isready     | |
             |  +----------------+ |
             +---------+-----------+
                       |
             +---------v-----------+
             |   EBS Volume (gp3)  |
             |   Encrypted         |
             |   /dev/sdf          |
             |   Mount: /mnt/data  |
             +---------------------+
```

## Data Flow

```
                    REQUEST FLOW
  ====================================

  1. User → https://customer.example.com
  2. Route53 resolves ALIAS → ALB DNS name
  3. ALB terminates TLS using ACM certificate
  4. ALB forwards HTTP to Target Group (EC2:80)
  5. EC2 SG allows only ALB SG on port 80
  6. Docker frontend (nginx:80) serves static content
  7. /api/* proxied to backend container (nginx:8080)
  8. Backend communicates with PostgreSQL (Docker network)
  9. PostgreSQL stores data on persistent EBS volume
```

## Components

| Component | Type | Purpose |
|-----------|------|---------|
| Route53 | DNS | Custom domain resolution, cert validation |
| ACM | TLS | Free SSL/TLS certificate, auto-renewed |
| ALB | Load Balancer | TLS termination, HTTP->HTTPS redirect, traffic distribution |
| Target Group | Routing | Health checks, forwards to EC2 instance port 80 |
| Security Groups | Firewall | ALB SG: 80/443; EC2 SG: 22, 80(ALB only), 8080 |
| EC2 | Compute | Amazon Linux 2023, Docker host |
| IAM | Access | SSM agent, EBS attach/detach, scoped to AZ |
| EBS | Storage | 30-50GB gp3, encrypted, persistent data |
| Docker Compose | Orchestration | Frontend, Backend, PostgreSQL containers |
| EIP | Management | Elastic IP for SSH/administration |

## Security Boundaries

| Layer | Control |
|-------|---------|
| TLS | ACM cert via DNS validation, TLS 1.3 ready |
| Network | EC2 SG allows port 80 only from ALB SG |
| IAM | SSM agent + EBS attach/detach scoped to AZ+account |
| Instance Metadata | IMDSv2 enforced (`http_tokens = "required"`) |
| Storage | EBS encrypted at rest (`encrypted = true`) |
| Application | Structured JSON logging, health check endpoints |
| Destruction | Production volumes protected (`skip_destroy = true`) |
