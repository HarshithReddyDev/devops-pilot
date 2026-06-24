# Monthly Cost Estimate

All prices in USD, based on `us-east-1` (N. Virginia) as of June 2026.

---

## Staging (`t3.small` + 30GB gp3)

| Resource | Spec | Monthly |
|----------|------|---------|
| **EC2** | t3.small (2 vCPU, 2 GiB), Linux, on-demand | $20.52 |
| **EBS root** | 20 GB gp3 | $1.60 |
| **EBS data** | 30 GB gp3 | $2.40 |
| **ALB** | Application Load Balancer | $16.43 |
| **ALB LCU** | 1 LCU (light traffic) | $5.85 |
| **EIP** | Elastic IP (associated) | $0.00 |
| **ACM** | Public certificate | $0.00 |
| **Route53** | 1 hosted zone + 5 records | $0.50 |
| **NAT Gateway** | *(none — instance has public IP)* | $0.00 |
| **Data transfer** | ~50 GB out | $4.50 |

### Staging Total: **~$52/mo**

---

## Production (`t3.medium` + 50GB gp3)

| Resource | Spec | Monthly |
|----------|------|---------|
| **EC2** | t3.medium (2 vCPU, 4 GiB), Linux, on-demand | $41.04 |
| **EBS root** | 30 GB gp3 | $2.40 |
| **EBS data** | 50 GB gp3 | $4.00 |
| **ALB** | Application Load Balancer | $16.43 |
| **ALB LCU** | 2 LCU (moderate traffic) | $11.70 |
| **EIP** | Elastic IP (associated) | $0.00 |
| **ACM** | Public certificate | $0.00 |
| **Route53** | 1 hosted zone + 5 records | $0.50 |
| **NAT Gateway** | *(none — instance has public IP)* | $0.00 |
| **Data transfer** | ~200 GB out | $18.00 |

### Production Total: **~$94/mo**

---

## Cost Breakdown Notes

| Component | Notes |
|-----------|-------|
| **EC2** | On-demand pricing. Savings: ~40% with 1-yr reserved, ~60% with 3-yr. |
| **EBS gp3** | $0.08/GB-mo. Baseline 3000 IOPS + 125 MB/s free. |
| **ALB** | $0.0225/hr + $0.008/LCU-hr. 1 LCU = 25 new connections/s, 3000 active, 1 MB throughput. |
| **EIP** | Free when associated to running instance. ~$0.005/hr if unused. |
| **ACM** | Free. Auto-renewed. |
| **Route53** | $0.50/zone for first 25 zones. $0.40/million queries. |
| **Data transfer** | First 100 GB/mo = $0.09/GB. Next 100 GB = $0.085/GB. |

---

## Optimization Options

| Action | Savings | Staging | Production |
|--------|---------|---------|------------|
| t3.small → t3.nano (staging only) | -$15/mo | $37/mo | — |
| 1-yr reserved instance | -40% EC2 | $44/mo | $78/mo |
| 3-yr reserved instance | -60% EC2 | $40/mo | $69/mo |
| Remove EIP (use ALB only) | $0 | $52/mo | $94/mo |
| Staging on t4g (ARM, Graviton) | -20% | $42/mo | — |

---

## One-Time Costs

| Resource | Cost |
|----------|------|
| ACM certificate | $0 |
| Route53 zone creation | $0 |
| EBS snapshot (first full) | ~$3 (30GB) / ~$5 (50GB) |
