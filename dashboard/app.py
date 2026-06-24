import streamlit as st
import os
import time
import threading

from validators import validate_customer_name, sanitize_customer_name
from terraform_runner import run_terraform, parse_outputs, get_terraform_outputs, get_output_value
from aws_status import get_full_status

st.set_page_config(
    page_title="DevOps Pilot Deployment Dashboard",
    page_icon="🚀",
    layout="wide",
)

if "deploy_status" not in st.session_state:
    st.session_state.deploy_status = None
if "deploy_outputs" not in st.session_state:
    st.session_state.deploy_outputs = {}
if "log_lines" not in st.session_state:
    st.session_state.log_lines = []
if "deploying" not in st.session_state:
    st.session_state.deploying = False
if "destroying" not in st.session_state:
    st.session_state.destroying = False
if "status_results" not in st.session_state:
    st.session_state.status_results = None

TEMPLATES = {
    "staging": {
        "instance_type": "t3.small",
        "ebs_size": 30,
        "desc": "Lightweight, cost-optimized environment for testing. t3.small, 30GB EBS.",
    },
    "production": {
        "instance_type": "t3.medium",
        "ebs_size": 50,
        "desc": "Production with larger EBS, restricted SSH, and data retention. t3.medium, 50GB EBS.",
    },
}

TERRAFORM_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "terraform")
)


def render_status_card(label, status_data, icon):
    status = status_data.get("status", "unknown")
    detail = status_data.get("detail", "")
    color_map = {
        "healthy": "#2ecc71",
        "unhealthy": "#e74c3c",
        "error": "#e67e22",
        "unknown": "#95a5a6",
        "degraded": "#f39c12",
    }
    bg_color = color_map.get(status, "#95a5a6")
    st.markdown(
        f"""
        <div style="
            background: {bg_color}15;
            border: 1px solid {bg_color}40;
            border-radius: 10px;
            padding: 1rem;
            text-align: center;
        ">
            <div style="font-size: 2rem;">{icon}</div>
            <div style="font-weight: 600; margin: 0.5rem 0;">{label}</div>
            <div style="
                display: inline-block;
                background: {bg_color};
                color: white;
                padding: 0.15rem 0.75rem;
                border-radius: 999px;
                font-size: 0.8rem;
                font-weight: 500;
            ">{status.upper()}</div>
            <div style="font-size: 0.75rem; color: #666; margin-top: 0.5rem;">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.title("🚀 DevOps Pilot Deployment Dashboard")
st.markdown("Provision and manage customer-specific environments on AWS.")

st.sidebar.header("Configuration")
terraform_available = os.path.isfile(os.path.join(TERRAFORM_DIR, "main.tf"))
if not terraform_available:
    st.sidebar.error(f"Terraform config not found at {TERRAFORM_DIR}")
    st.stop()
else:
    st.sidebar.success("Terraform configuration found")

customer_input = st.sidebar.text_input(
    "Customer Name",
    placeholder="e.g. ibm, nike, acme",
    help="Lowercase alphanumeric with hyphens. Used for resource naming and DNS.",
)

env_input = st.sidebar.selectbox(
    "Environment",
    options=list(TEMPLATES.keys()),
    format_func=lambda t: f"{t.title()} ({TEMPLATES[t]['instance_type']})",
)

st.sidebar.info(TEMPLATES[env_input]["desc"])

domain_input = st.sidebar.text_input(
    "Root Domain",
    value="demo.example.com",
    help="Route53 hosted zone must exist. Use example.com for testing (DNS disabled).",
)

az_input = st.sidebar.text_input(
    "Availability Zone",
    value="us-east-1a",
)

col1, col2 = st.sidebar.columns(2)
deploy_disabled = st.session_state.deploying or st.session_state.destroying
destroy_disabled = st.session_state.deploying or st.session_state.destroying or not st.session_state.deploy_outputs

with col1:
    deploy_clicked = st.button(
        "🚀 Deploy",
        type="primary",
        use_container_width=True,
        disabled=deploy_disabled,
    )

with col2:
    destroy_clicked = st.button(
        "🗑️ Destroy",
        type="secondary",
        use_container_width=True,
        disabled=destroy_disabled,
    )

if destroy_clicked and st.session_state.deploy_outputs:
    st.session_state.destroying = True
    customer_name = st.session_state.deploy_outputs.get("customer_name", "")
    env = st.session_state.deploy_outputs.get("environment", env_input)
    domain = domain_input
    az = az_input
    if not customer_name:
        customer_name = sanitize_customer_name(customer_input or "customer")
else:
    customer_name = ""

# ========== MAIN PANEL ==========

log_tab, outputs_tab, status_tab = st.tabs(["📋 Deployment Logs", "📊 Deployment Outputs", "✅ Status Dashboard"])

with log_tab:
    log_container = st.container()
    log_area = st.empty()

with outputs_tab:
    outputs_container = st.container()

with status_tab:
    status_container = st.container()

# ========== DEPLOY LOGIC ==========

if deploy_clicked or destroy_clicked:
    if deploy_clicked:
        is_valid, result = validate_customer_name(customer_input or "")
        if not is_valid:
            st.sidebar.error(result)
            st.stop()
        customer_name = result
        env = env_input
        action = "apply"
        st.session_state.deploying = True
        st.session_state.deploy_status = "deploying"
    else:
        action = "destroy"
        st.session_state.destroying = True
        st.session_state.deploy_status = "destroying"

    st.session_state.log_lines = []
    customer_url = f"https://{customer_name}.{domain_input}"

    with log_tab:
        log_area.markdown("### Deployment Log")
        log_placeholder = st.empty()

    with outputs_tab:
        outputs_placeholder = st.empty()

    accumulated_log = ""

    progress_bar = st.progress(0, text=f"Running terraform {action}...")

    for stream, line in run_terraform(
        action=action,
        customer_name=customer_name,
        environment=env,
        root_domain=domain_input,
        az=az_input,
    ):
        if stream == "stdout":
            accumulated_log += line + "\n"
            st.session_state.log_lines.append(line)
            log_placeholder.code(accumulated_log, language="text")
        elif stream == "stderr":
            accumulated_log += line + "\n"
            st.session_state.log_lines.append(line)
            log_placeholder.code(accumulated_log, language="text")
        elif stream == "exit_code":
            exit_code = line
            if exit_code == 0:
                progress_bar.progress(100, text=f"Terraform {action} completed successfully!")
                if action == "apply":
                    st.session_state.deploy_status = "deployed"
                    outputs_text = ""
                    for l in st.session_state.log_lines:
                        outputs_text += l + "\n"
                    parsed = parse_outputs(outputs_text)
                    st.session_state.deploy_outputs = parsed

                    with outputs_tab:
                        outputs_placeholder.empty()
                        with outputs_placeholder.container():
                            st.success(f"### ✅ Deployment Complete")
                            st.metric("Environment Name", f"{customer_name}-{env}")
                            st.metric("Customer URL", customer_url)
                            st.metric("EC2 Instance ID", parsed.get("instance_id", "N/A"))
                            st.metric("ALB DNS Name", parsed.get("alb_dns_name", "N/A"))
                            st.metric("Elastic IP", parsed.get("elastic_ip", "N/A"))
                            st.metric("EBS Volume ID", parsed.get("ebs_volume_id", "N/A"))
                            st.metric("Security Group", parsed.get("security_group_name", "N/A"))
                            st.json(parsed)
                else:
                    st.session_state.deploy_status = "destroyed"
                    st.session_state.deploy_outputs = {}
                    with outputs_tab:
                        outputs_placeholder.success("### ✅ Infrastructure Destroyed Successfully")
            else:
                progress_bar.progress(100, text=f"Terraform {action} failed!")
                st.session_state.deploy_status = "failed"
                with outputs_tab:
                    outputs_placeholder.error("### ❌ Deployment Failed")
                    outputs_placeholder.code(accumulated_log, language="text")

        elif stream == "log":
            pass

    st.session_state.deploying = False
    st.session_state.destroying = False

    if action == "apply" and st.session_state.deploy_status == "deployed":
        st.balloons()

# ========== STATUS CHECKS ==========

if st.session_state.deploy_status == "deployed" and st.session_state.deploy_outputs:
    with status_tab:
        status_placeholder = st.empty()
        if st.button("🔄 Refresh Status", key="refresh_status"):
            st.session_state.status_results = None

        if st.session_state.status_results is None:
            with st.spinner("Running post-deployment health checks..."):
                outputs = st.session_state.deploy_outputs
                instance_id = outputs.get("instance_id", "")
                alb_dns = outputs.get("alb_dns_name", "")
                tg_arn = outputs.get("alb_target_group_arn", "")
                results = get_full_status(instance_id, alb_dns, tg_arn)
                st.session_state.status_results = results

        results = st.session_state.status_results
        if results:
            overall = results.get("overall", "unknown")
            overall_color = "#2ecc71" if overall == "healthy" else "#f39c12"
            st.markdown(
                f"""
                <div style="
                    background: {overall_color}15;
                    border: 2px solid {overall_color};
                    border-radius: 10px;
                    padding: 1.5rem;
                    text-align: center;
                    margin-bottom: 1.5rem;
                ">
                    <div style="font-size: 1.25rem; font-weight: 600;">
                        Overall Status: <span style="color: {overall_color};">{overall.upper()}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            cols = st.columns(4)
            with cols[0]:
                render_status_card("EC2 Instance", results.get("ec2", {}), "🖥️")
            with cols[1]:
                render_status_card("ALB", results.get("alb", {}), "⚖️")
            with cols[2]:
                render_status_card("Target Group", results.get("target_group", {}), "🎯")
            with cols[3]:
                render_status_card("Containers", results.get("containers", {}), "🐳")

# ========== DEPLOYMENT OUTPUTS (PERSISTENT) ==========

if st.session_state.deploy_outputs:
    with outputs_tab:
        outputs_container.empty()
        with outputs_container.container():
            parsed = st.session_state.deploy_outputs
            st.subheader("📊 Deployment Outputs")
            cust = parsed.get("customer_name", "N/A")
            env = parsed.get("environment", "N/A")
            url = parsed.get("customer_url", "N/A")
            st.markdown(f"**Customer:** {cust}")
            st.markdown(f"**Environment:** {env}")
            st.markdown(f"**URL:** [{url}]({url})")
            st.divider()
            cols = st.columns(2)
            with cols[0]:
                st.metric("Instance ID", parsed.get("instance_id", "N/A"))
                st.metric("Instance Public IP", parsed.get("instance_public_ip", "N/A"))
                st.metric("Instance Private IP", parsed.get("instance_private_ip", "N/A"))
                st.metric("Elastic IP", parsed.get("elastic_ip", "N/A"))
            with cols[1]:
                st.metric("ALB DNS", parsed.get("alb_dns_name", "N/A"))
                st.metric("ALB Zone ID", parsed.get("alb_zone_id", "N/A"))
                st.metric("EBS Volume ID", parsed.get("ebs_volume_id", "N/A"))
                st.metric("Security Group", parsed.get("security_group_name", "N/A"))
            st.divider()
            st.json(parsed)

# ========== RECENT LOGS (PERSISTENT) ==========

if st.session_state.log_lines:
    with log_tab:
        log_area.code("\n".join(st.session_state.log_lines), language="text")

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Prerequisites:** AWS credentials configured, Terraform installed, "
    "and a Route53 hosted zone for custom domains."
)
