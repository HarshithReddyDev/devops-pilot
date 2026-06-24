# Architecture Diagram

```mermaid
graph TB
    subgraph "AWS Cloud"
        subgraph "DNS & TLS"
            R53[("Route53<br/>ALIAS A Record")]
            ACM[("ACM Certificate<br/>DNS-validated")]
        end

        subgraph "Load Balancing"
            ALB_SG["ALB Security Group<br/>Port 80, 443 from Internet"]
            ALB["Application Load Balancer<br/>HTTP:80 -> 301 HTTPS<br/>HTTPS:443 -> Target Group"]
            TG["Target Group<br/>HTTP:80 -> EC2<br/>Health: GET /health"]
        end

        subgraph "Compute & Storage"
            EC2_SG["EC2 Security Group<br/>Port 22 (SSH)<br/>Port 80 (ALB only)"]
            EC2["EC2 Instance<br/>Amazon Linux 2023<br/>t3.small / t3.medium"]
            IAM["IAM Role<br/>SSM + EBS management"]
            EBS["EBS Volume gp3<br/>30-50 GB encrypted<br/>Mount: /mnt/data"]
            EIP["Elastic IP"]
        end

        subgraph "Docker Compose Stack"
            FE["frontend<br/>nginx:alpine<br/>Port 80"]
            BE["backend<br/>nginx:alpine<br/>Port 8080"]
            PG[("postgres<br/>PostgreSQL 16<br/>Port 5432")]
        end

        Internet -->|"HTTPS :443"| R53
        R53 --> ALB
        ALB_SG --> ALB
        ALB -->|"HTTP :80"| TG
        TG -->|"/health check"| EC2
        EC2_SG --> EC2
        IAM --> EC2
        EC2 --- EIP
        EC2 --> EBS
        EC2 --> FE
        FE -->|"/api/*"| BE
        BE --> PG
        PG --> EBS
    end

    style R53 fill:#1abc9c,color:#fff
    style ACM fill:#16a085,color:#fff
    style ALB fill:#3498db,color:#fff
    style TG fill:#2980b9,color:#fff
    style EC2 fill:#9b59b6,color:#fff
    style IAM fill:#8e44ad,color:#fff
    style EBS fill:#f39c12,color:#fff
    style FE fill:#e74c3c,color:#fff
    style BE fill:#e67e22,color:#fff
    style PG fill:#2ecc71,color:#fff
```

## Data Flow

```
  1. User --> https://customer.domain.com
  2. Route53 ALIAS resolves to ALB DNS
  3. ALB terminates TLS (ACM cert)
  4. ALB forwards to Target Group (EC2:80)
  5. EC2 SG allows only ALB on port 80
  6. Docker frontend serves /, proxies /api to backend
  7. Backend communicates with PostgreSQL
  8. Postgres persists data to EBS volume
```

## Security Boundaries

| Layer | Controls |
|-------|----------|
| Network | SG restricts SSH, HTTP from ALB only |
| Host | IMDSv2 required, SSH key auth |
| IAM | Instance role with minimal SSM + EBS manage |
| Data | EBS encrypted at rest |
| Application | Containers run as non-root, health checks |
