import streamlit as st
import subprocess
import json
import os
import re
import time
import shlex

st.set_page_config(
    page_title="DevOps Pilot",
    page_icon="🚀",
    layout="centered",
)

if "deploy_status" not in st.session_state:
    st.session_state.deploy_status = None
if "deploy_outputs" not in st.session_state:
    st.session_state.deploy_outputs = None

TEMPLATES = {
    "staging": {
        "instance_type": "t3.small",
        "ebs_size": 30,
        "desc": "Lightweight, cost-optimized environment for testing.",
    },
    "production": {
        "instance_type": "t3.medium",
        "ebs_size": 50,
        "desc": "Production with larger EBS, restricted SSH, and data retention.",
    },
}

TERRAFORM_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "terraform")
)


def sanitize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", name.lower().strip())


def run_terraform(
    action: str, customer: str, env: str, root_domain: str, az: str
) -> subprocess.CompletedProcess:
    is_placeholder_domain = any(
        d in root_domain.lower() for d in ["example.com", "demo.local", "test.local", "localhost"]
    )
    create_dns = "false" if is_placeholder_domain else "true"

    cmd = [
        "terraform",
        action,
        "-auto-approve",
        f"-var=customer={shlex.quote(customer)}",
        f"-var=environment={shlex.quote(env)}",
        f"-var=root_domain={shlex.quote(root_domain)}",
        f"-var=availability_zone={shlex.quote(az)}",
        f"-var=create_dns_resources={create_dns}",
    ]

    env_overrides = {**os.environ, "TF_IN_AUTOMATION": "1"}

    return subprocess.run(
        cmd,
        cwd=TERRAFORM_DIR,
        capture_output=True,
        text=True,
        env=env_overrides,
    )


def parse_terraform_outputs(stdout: str) -> dict:
    outputs = {}
    for line in stdout.splitlines():
        m = re.match(r"^(\w+)\s*=\s*(.+)$", line.strip())
        if m:
            val = m.group(2).strip().strip('"')
            outputs[m.group(1)] = val
    return outputs


# --- UI ---
st.title("🚀 DevOps Pilot")
st.markdown("Provision a fully isolated customer environment on AWS.")

terraform_available = os.path.isfile(os.path.join(TERRAFORM_DIR, "main.tf"))

if not terraform_available:
    st.error(f"Terraform configuration not found at {TERRAFORM_DIR}")
    st.stop()

with st.form("deploy_form"):
    col1, col2 = st.columns(2)

    with col1:
        customer = st.text_input(
            "Customer Name",
            placeholder="e.g. acme-corp",
            help="Lowercase alphanumeric with hyphens. Used as DNS prefix.",
        )

    with col2:
        template = st.selectbox(
            "Template",
            options=list(TEMPLATES.keys()),
            format_func=lambda t: f"{t.title()} ({TEMPLATES[t]['instance_type']})",
        )

    st.info(TEMPLATES[template]["desc"])

    col3, col4 = st.columns(2)

    with col3:
        root_domain = st.text_input(
            "Root Domain",
            value="demo.example.com",
            help="Route53 hosted zone must exist for this domain.",
        )

    with col4:
        availability_zone = st.text_input(
            "Availability Zone",
            value="us-east-1a",
        )

    action = st.selectbox(
        "Action",
        options=["apply", "destroy"],
        format_func=lambda a: { "apply": "Deploy 🚀", "destroy": "Destroy 🗑️" }[a],
    )

    submitted = st.form_submit_button(
        "Deploy" if action == "apply" else "Destroy",
        type="primary" if action == "apply" else "secondary",
        use_container_width=True,
    )

    if action == "destroy":
        st.warning("⚠️ This will destroy all infrastructure for this customer.")

# --- Deployment logic ---
if submitted:
    if not customer:
        st.error("Customer name is required.")
        st.stop()

    customer_clean = sanitize_name(customer)
    if customer_clean != customer:
        st.warning(f"Sanitized customer name to: **{customer_clean}**")
        customer = customer_clean

    if not root_domain:
        st.error("Root domain is required.")
        st.stop()

    deploy_url = f"https://{customer}.{root_domain}"
    st.subheader(f"Target: {deploy_url}")

    status_placeholder = st.empty()
    log_placeholder = st.empty()
    output_placeholder = st.empty()

    with status_placeholder.status(
        f"Running `terraform {action}`...", expanded=True
    ) as status:
        st.write(f"**Customer:** {customer}")
        st.write(f"**Template:** {template}")
        st.write(f"**Domain:** {root_domain}")
        st.write(f"**AZ:** {availability_zone}")
        st.write(f"**Action:** {action}")

        start = time.time()
        result = run_terraform(action, customer, template, root_domain, availability_zone)
        elapsed = time.time() - start

        if result.stdout:
            with log_placeholder.container():
                st.text_area("Terraform stdout", result.stdout, height=200)

        if result.returncode == 0:
            status.update(
                label=f"✅ Terraform {action} succeeded ({elapsed:.0f}s)",
                state="complete",
            )

            st.balloons()

            if action == "apply":
                outputs = parse_terraform_outputs(result.stdout)
                st.session_state.deploy_outputs = outputs

                output_placeholder.subheader("Deployment Outputs")
                output_placeholder.json(outputs)

                st.success(
                    f"### Deployment Complete\n\n"
                    f"👉 **URL:** [{deploy_url}]({deploy_url})\n\n"
                    f"**ALB DNS:** `{outputs.get('alb_dns_name', 'N/A')}`\n"
                    f"**Instance ID:** `{outputs.get('instance_id', 'N/A')}`\n"
                    f"**Elastic IP:** `{outputs.get('elastic_ip', 'N/A')}`\n"
                    f"**EBS Volume:** `{outputs.get('ebs_volume_id', 'N/A')}`\n"
                    f"**Duration:** {elapsed:.0f}s"
                )
            else:
                st.success("Infrastructure destroyed successfully.")
        else:
            status.update(
                label=f"❌ Terraform {action} failed ({elapsed:.0f}s)",
                state="error",
            )
            output_placeholder.error("Terraform Error Log")
            output_placeholder.code(result.stderr, language="text")

            st.session_state.deploy_status = "failed"

st.markdown("---")
st.markdown(
    "**Prerequisites:** AWS credentials configured via environment variables "
    "or `~/.aws/credentials`, and Terraform installed."
)
