import boto3
import time
import json


def _get_ec2_client(region="us-east-1"):
    return boto3.client("ec2", region_name=region)


def _get_elbv2_client(region="us-east-1"):
    return boto3.client("elbv2", region_name=region)


def _get_ssm_client(region="us-east-1"):
    return boto3.client("ssm", region_name=region)


def check_ec2_instance(instance_id, region="us-east-1"):
    if not instance_id:
        return {"status": "unknown", "detail": "No instance ID provided"}
    try:
        ec2 = _get_ec2_client(region)
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]
        state = instance["State"]["Name"]
        return {
            "status": "healthy" if state == "running" else "unhealthy",
            "detail": f"State: {state}",
            "instance_type": instance.get("InstanceType", "unknown"),
            "public_ip": instance.get("PublicIpAddress", "N/A"),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def check_alb(alb_dns_name, region="us-east-1"):
    if not alb_dns_name:
        return {"status": "unknown", "detail": "No ALB DNS provided"}
    try:
        elbv2 = _get_elbv2_client(region)
        paginator = elbv2.get_paginator("describe_load_balancers")
        for page in paginator.paginate():
            for lb in page["LoadBalancers"]:
                if lb["DNSName"] == alb_dns_name:
                    return {
                        "status": "healthy" if lb["State"]["Code"] == "active" else "unhealthy",
                        "detail": f"State: {lb['State']['Code']}",
                        "dns_name": lb["DNSName"],
                    }
        return {"status": "unknown", "detail": "ALB not found"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def check_target_group(target_group_arn, region="us-east-1"):
    if not target_group_arn:
        return {"status": "unknown", "detail": "No target group ARN provided"}
    try:
        elbv2 = _get_elbv2_client(region)
        response = elbv2.describe_target_health(TargetGroupArn=target_group_arn)
        descriptions = response["TargetHealthDescriptions"]
        if not descriptions:
            return {"status": "unknown", "detail": "No targets registered"}
        all_healthy = all(
            d["TargetHealth"]["State"] == "healthy" for d in descriptions
        )
        states = [d["TargetHealth"]["State"] for d in descriptions]
        return {
            "status": "healthy" if all_healthy else "unhealthy",
            "detail": f"States: {', '.join(states)}",
            "target_count": len(descriptions),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def check_containers_ssm(instance_id, region="us-east-1"):
    if not instance_id:
        return {"status": "unknown", "detail": "No instance ID provided"}
    try:
        ssm = _get_ssm_client(region)
        commands = [
            "docker compose ps --format json 2>/dev/null || echo '{}'",
            "curl -sf http://localhost/health 2>/dev/null || echo 'unreachable'",
            "curl -sf http://localhost:8080/health 2>/dev/null || echo 'unreachable'",
        ]
        combined_cmd = "; ".join(commands)
        response = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [combined_cmd]},
            TimeoutSeconds=30,
        )
        command_id = response["Command"]["CommandId"]
        time.sleep(5)
        for _ in range(6):
            output = ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=instance_id,
            )
            if output["Status"] in ("Success", "Failed", "TimedOut"):
                stdout = output.get("StandardOutputContent", "")
                stderr = output.get("StandardErrorContent", "")
                lines = stdout.strip().split("\n")
                frontend_status = "unknown"
                backend_status = "unknown"
                containers = []
                for line in lines:
                    if line == "healthy":
                        if frontend_status == "unknown":
                            frontend_status = "healthy"
                        else:
                            backend_status = "healthy"
                    elif line == "unreachable":
                        if frontend_status == "unknown":
                            frontend_status = "unhealthy"
                        else:
                            backend_status = "unhealthy"
                    elif line.startswith("{"):
                        try:
                            containers.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
                all_healthy = (
                    frontend_status == "healthy" and backend_status == "healthy"
                )
                return {
                    "status": "healthy" if all_healthy else "unhealthy",
                    "frontend": frontend_status,
                    "backend": backend_status,
                    "containers": len(containers),
                    "detail": f"Frontend: {frontend_status}, Backend: {backend_status}",
                }
            time.sleep(5)
        return {"status": "unknown", "detail": "SSM command timed out"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def get_full_status(instance_id, alb_dns, target_group_arn, region="us-east-1"):
    results = {}
    results["ec2"] = check_ec2_instance(instance_id, region)
    results["alb"] = check_alb(alb_dns, region)
    results["target_group"] = check_target_group(target_group_arn, region)
    results["containers"] = check_containers_ssm(instance_id, region)
    all_healthy = all(
        v.get("status") == "healthy" for v in results.values()
    )
    results["overall"] = "healthy" if all_healthy else "degraded"
    return results
