import boto3
import time
import json


def _get_session(region="us-east-1"):
    return boto3.Session(region_name=region)


def _get_ec2(region="us-east-1"):
    return _get_session(region).client("ec2")


def _get_elbv2(region="us-east-1"):
    return _get_session(region).client("elbv2")


def _get_ssm(region="us-east-1"):
    return _get_session(region).client("ssm")


def _get_route53(region="us-east-1"):
    return _get_session(region).client("route53")


def _get_sts(region="us-east-1"):
    return _get_session(region).client("sts")


def resolve_region():
    try:
        return boto3.Session().region_name or "us-east-1"
    except Exception:
        return "us-east-1"


def check_ec2_instance(instance_id, region=None):
    region = region or resolve_region()
    if not instance_id or instance_id == "N/A":
        return {"status": "unknown", "detail": "No instance ID provided"}
    try:
        ec2 = _get_ec2(region)
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]
        state = instance["State"]["Name"]
        return {
            "status": "healthy" if state == "running" else "unhealthy",
            "detail": f"State: {state}",
            "instance_type": instance.get("InstanceType", "unknown"),
            "public_ip": instance.get("PublicIpAddress", "N/A"),
            "private_ip": instance.get("PrivateIpAddress", "N/A"),
            "az": instance.get("Placement", {}).get("AvailabilityZone", "N/A"),
            "launch_time": str(instance.get("LaunchTime", "N/A")),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def check_alb_by_name(alb_name, region=None):
    region = region or resolve_region()
    if not alb_name:
        return {"status": "unknown", "detail": "No ALB name provided"}
    try:
        elbv2 = _get_elbv2(region)
        response = elbv2.describe_load_balancers(Names=[alb_name])
        lb = response["LoadBalancers"][0]
        state_code = lb["State"]["Code"]
        listeners = []
        try:
            listener_response = elbv2.describe_listeners(LoadBalancerArn=lb["LoadBalancerArn"])
            for lis in listener_response["Listeners"]:
                listeners.append({
                    "protocol": lis["Protocol"],
                    "port": lis["Port"],
                })
        except Exception:
            listeners = []
        return {
            "status": "healthy" if state_code == "active" else "unhealthy",
            "detail": f"State: {state_code}",
            "name": lb["LoadBalancerName"],
            "dns_name": lb["DNSName"],
            "arn": lb["LoadBalancerArn"],
            "type": lb["LoadBalancerType"],
            "vpc": lb["VpcId"],
            "listeners": listeners,
            "listener_count": len(listeners),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def check_alb(alb_dns_name, alb_name=None, region=None):
    region = region or resolve_region()

    if alb_name:
        result = check_alb_by_name(alb_name, region)
        if result["status"] != "error":
            return result

    if not alb_dns_name or alb_dns_name == "N/A":
        return {"status": "unknown", "detail": "No ALB DNS or name provided"}
    try:
        elbv2 = _get_elbv2(region)
        paginator = elbv2.get_paginator("describe_load_balancers")
        for page in paginator.paginate():
            for lb in page["LoadBalancers"]:
                if lb["DNSName"] == alb_dns_name:
                    listeners = []
                    try:
                        lr = elbv2.describe_listeners(LoadBalancerArn=lb["LoadBalancerArn"])
                        for lis in lr["Listeners"]:
                            listeners.append({
                                "protocol": lis["Protocol"],
                                "port": lis["Port"],
                            })
                    except Exception:
                        pass
                    return {
                        "status": "healthy" if lb["State"]["Code"] == "active" else "unhealthy",
                        "detail": f"State: {lb['State']['Code']}",
                        "name": lb["LoadBalancerName"],
                        "dns_name": lb["DNSName"],
                        "arn": lb["LoadBalancerArn"],
                        "type": lb["LoadBalancerType"],
                        "listeners": listeners,
                        "listener_count": len(listeners),
                    }
        return {"status": "unknown", "detail": "ALB not found by DNS or name"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def check_target_group(target_group_arn, region=None):
    region = region or resolve_region()
    if not target_group_arn or target_group_arn == "N/A":
        return {"status": "unknown", "detail": "No target group ARN provided"}
    try:
        elbv2 = _get_elbv2(region)
        tg_response = elbv2.describe_target_groups(TargetGroupArns=[target_group_arn])
        tg = tg_response["TargetGroups"][0]

        health_response = elbv2.describe_target_health(TargetGroupArn=target_group_arn)
        descriptions = health_response["TargetHealthDescriptions"]

        healthy_count = sum(
            1 for d in descriptions if d["TargetHealth"]["State"] == "healthy"
        )
        unhealthy_count = sum(
            1 for d in descriptions if d["TargetHealth"]["State"] != "healthy"
        )
        states = [d["TargetHealth"]["State"] for d in descriptions]

        registered = []
        for d in descriptions:
            registered.append({
                "id": d["Target"]["Id"],
                "port": d["Target"]["Port"],
                "state": d["TargetHealth"]["State"],
            })

        total = len(descriptions)
        all_healthy = healthy_count == total and total > 0

        return {
            "status": "healthy" if all_healthy else "unhealthy",
            "detail": f"Healthy: {healthy_count}/{total}" if total > 0 else "No targets",
            "healthy_count": healthy_count,
            "unhealthy_count": unhealthy_count,
            "total_targets": total,
            "states": states,
            "registered_targets": registered,
            "health_check_path": tg.get("HealthCheck", {}).get("Path", "N/A"),
            "health_check_port": tg.get("HealthCheck", {}).get("Port", "N/A"),
            "health_check_protocol": tg.get("HealthCheck", {}).get("Protocol", "N/A"),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def check_route53_record(domain, record_name, region="us-east-1"):
    if not domain or domain == "N/A":
        return {"status": "unknown", "detail": "No domain provided"}
    try:
        route53 = boto3.client("route53", region_name="us-east-1")
        paginator = route53.get_paginator("list_hosted_zones")
        for page in paginator.paginate():
            for zone in page["HostedZones"]:
                zone_domain = zone["Name"].rstrip(".")
                if domain.rstrip(".").endswith("." + zone_domain) or domain.rstrip(".") == zone_domain:
                    zone_id = zone["Id"].split("/")[-1]
                    try:
                        record_sets = route53.list_resource_record_sets(
                            HostedZoneId=zone["Id"],
                            StartRecordName=record_name,
                            StartRecordType="A",
                            MaxItems="1",
                        )
                        for rs in record_sets["ResourceRecordSets"]:
                            if rs["Name"].rstrip(".") == record_name.rstrip("."):
                                alias = rs.get("AliasTarget", {})
                                return {
                                    "status": "active",
                                    "detail": f"Record found: {rs['Name']}",
                                    "type": rs["Type"],
                                    "alias_target": alias.get("DNSName", "N/A"),
                                    "zone_id": zone_id,
                                    "zone_name": zone_domain,
                                }
                        return {
                            "status": "warning",
                            "detail": f"Record {record_name} not found in zone {zone_domain}",
                            "zone_id": zone_id,
                            "zone_name": zone_domain,
                        }
                    except Exception as e:
                        return {"status": "error", "detail": str(e)}
        return {"status": "warning", "detail": f"No hosted zone found for {domain}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def check_containers_ssm(instance_id, region=None):
    region = region or resolve_region()
    if not instance_id or instance_id == "N/A":
        return {"status": "unknown", "detail": "No instance ID provided"}
    try:
        ssm = _get_ssm(region)
        commands = [
            "echo '=== DOCKER PS ===",
            "docker compose ps --format json 2>/dev/null || docker ps --format json 2>/dev/null || echo '{}'",
            "echo '=== FRONTEND HEALTH ===",
            "curl -sf http://localhost/health 2>/dev/null || echo 'unreachable'",
            "echo '=== BACKEND HEALTH ===",
            "curl -sf http://localhost:8080/health 2>/dev/null || echo 'unreachable'",
            "echo '=== DOCKER COMPOSE CONFIG ===",
            "docker compose ls 2>/dev/null || echo 'compose ls failed'",
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
            try:
                output = ssm.get_command_invocation(
                    CommandId=command_id, InstanceId=instance_id,
                )
                if output["Status"] in ("Success", "Failed", "TimedOut"):
                    stdout = output.get("StandardOutputContent", "")
                    stderr = output.get("StandardErrorContent", "")
                    lines = stdout.strip().split("\n")
                    frontend_status = "unknown"
                    backend_status = "unknown"
                    containers = []
                    capture_section = None
                    for line in lines:
                        line = line.strip()
                        if line == "=== FRONTEND HEALTH ===":
                            capture_section = "frontend"
                            continue
                        elif line == "=== BACKEND HEALTH ===":
                            capture_section = "backend"
                            continue
                        elif line == "=== DOCKER PS ===":
                            capture_section = "docker"
                            continue
                        if capture_section == "frontend":
                            frontend_status = "healthy" if line == "healthy" else "unhealthy"
                        elif capture_section == "backend":
                            backend_status = "healthy" if line == "healthy" else "unhealthy"
                        elif capture_section == "docker" and line.startswith("{"):
                            try:
                                containers.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
                    all_healthy = frontend_status == "healthy" and backend_status == "healthy"
                    return {
                        "status": "healthy" if all_healthy else "unhealthy",
                        "frontend": frontend_status,
                        "backend": backend_status,
                        "container_count": len(containers),
                        "detail": f"Frontend: {frontend_status}, Backend: {backend_status}",
                    }
            except Exception:
                pass
            time.sleep(5)
        return {"status": "unknown", "detail": "SSM command timed out"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def get_full_status(instance_id, alb_dns, target_group_arn, alb_name=None,
                    domain=None, record_name=None, region=None):
    region = region or resolve_region()
    results = {}
    results["ec2"] = check_ec2_instance(instance_id, region)
    results["alb"] = check_alb(alb_dns, alb_name, region)
    results["target_group"] = check_target_group(target_group_arn, region)
    results["route53"] = check_route53_record(domain, record_name, region)
    results["containers"] = check_containers_ssm(instance_id, region)

    all_healthy = all(
        v.get("status") == "healthy" for v in results.values()
    )
    any_warning = any(
        v.get("status") == "warning" for v in results.values()
    )
    if all_healthy:
        results["overall"] = "healthy"
    elif any_warning:
        results["overall"] = "warning"
    else:
        results["overall"] = "degraded"
    return results
