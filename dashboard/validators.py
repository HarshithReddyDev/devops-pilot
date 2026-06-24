import re
import subprocess
import os


def validate_customer_name(name):
    if not name or not name.strip():
        return False, "Customer name is required."
    name = name.strip()
    if len(name) < 2:
        return False, "Customer name must be at least 2 characters."
    if len(name) > 63:
        return False, "Customer name must be 63 characters or fewer."
    if not re.match(r"^[a-z0-9-]+$", name.lower()):
        return False, (
            "Customer name must contain only lowercase letters, "
            "numbers, and hyphens."
        )
    if name.startswith("-") or name.endswith("-"):
        return False, "Customer name cannot start or end with a hyphen."
    return True, name.lower()


def sanitize_customer_name(name):
    cleaned = re.sub(r"[^a-z0-9-]", "", name.lower().strip())
    cleaned = cleaned.strip("-")
    if not cleaned:
        cleaned = "customer"
    return cleaned


def validate_domain(domain):
    if not domain or not domain.strip():
        return False, "Domain is required."
    domain = domain.strip()
    if len(domain) > 253:
        return False, "Domain is too long (max 253 characters)."
    if not re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", domain):
        return False, (
            "Domain must be a valid domain name (e.g. demo.example.com)."
        )
    return True, domain


def validate_availability_zone(az):
    if not az or not az.strip():
        return False, "Availability zone is required."
    az = az.strip()
    if not re.match(r"^[a-z]{2}-[a-z]+-[0-9][a-z]$", az):
        return False, "Availability zone must be in format like 'us-east-1a'."
    return True, az


def validate_environment(env):
    valid = ["staging", "production"]
    if env not in valid:
        return False, f"Environment must be one of: {', '.join(valid)}"
    return True, env


def check_aws_credentials():
    try:
        import boto3
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        return {
            "status": "configured",
            "account_id": identity["Account"],
            "arn": identity["Arn"],
            "region": boto3.session.Session().region_name or "us-east-1",
        }
    except Exception as e:
        return {"status": "missing", "error": str(e)}


def check_terraform_version():
    try:
        result = subprocess.run(
            ["terraform", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            first_line = result.stdout.strip().split("\n")[0]
            return {"status": "installed", "version": first_line}
        return {"status": "error", "detail": result.stderr}
    except FileNotFoundError:
        return {"status": "missing", "detail": "terraform not found in PATH"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def has_route53_zone(domain, region="us-east-1"):
    try:
        import boto3
        client = boto3.client("route53", region_name=region)
        paginator = client.get_paginator("list_hosted_zones")
        for page in paginator.paginate():
            for zone in page["HostedZones"]:
                if zone["Name"].rstrip(".") == domain.rstrip(".") or \
                   domain.rstrip(".").endswith("." + zone["Name"].rstrip(".")):
                    return True, zone["Id"]
        return False, None
    except Exception:
        return False, None
