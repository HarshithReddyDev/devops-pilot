import streamlit as st
import os
import time
import re
import json

from validators import (
    validate_customer_name,
    sanitize_customer_name,
    check_aws_credentials,
    check_terraform_version,
    has_route53_zone,
)
from terraform_runner import (
    run_terraform,
    run_terraform_init,
    run_terraform_plan,
    run_terraform_fmt_check,
    run_terraform_validate,
    get_terraform_outputs,
    get_output_value,
    list_workspaces,
    get_current_workspace,
    TERRAFORM_DIR,
)
from aws_status import get_full_status, resolve_region

st.set_page_config(
    page_title="DevOps Pilot",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session State ──────────────────────────────────────────────
if "deploying" not in st.session_state:
    st.session_state.deploying = False
if "destroying" not in st.session_state:
    st.session_state.destroying = False
if "log_lines" not in st.session_state:
    st.session_state.log_lines = []
if "last_deploy_result" not in st.session_state:
    st.session_state.last_deploy_result = None
if "selected_workspace" not in st.session_state:
    st.session_state.selected_workspace = None
if "refresh_workspaces" not in st.session_state:
    st.session_state.refresh_workspaces = 0
if "status_results" not in st.session_state:
    st.session_state.status_results = None
if "validation_results" not in st.session_state:
    st.session_state.validation_results = None
if "plan_output" not in st.session_state:
    st.session_state.plan_output = None

# ── Constants ──────────────────────────────────────────────────
TEMPLATES = {
    "staging": {
        "instance_type": "t3.small",
        "ebs_size": 30,
        "desc": "Lightweight, cost-optimized environment. t3.small, 30GB EBS.",
    },
    "production": {
        "instance_type": "t3.medium",
        "ebs_size": 50,
        "desc": "Production with larger EBS, restricted SSH, data retention. t3.medium, 50GB EBS.",
    },
}

CUSTOM_CSS = """
<style>
    /* ── Global ── */
    .stApp { background: #0e1117; }
    .main > div { padding: 1rem 2rem; }
    h1, h2, h3 { letter-spacing: -0.02em; }
    .stTabs [data-baseweb="tab-list"] { gap: 0; }
    .stTabs [data-baseweb="tab"] { height: auto; padding: 0.5rem 1rem; }

    /* ── Hero ── */
    .hero {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        border: 1px solid #1a3a5c;
        border-radius: 16px;
        padding: 2rem 2.5rem;
        margin-bottom: 2rem;
    }
    .hero h1 { color: #fff; margin: 0; font-size: 2.2rem; }
    .hero p { color: #8899aa; margin: 0.3rem 0 0 0; font-size: 1rem; }

    /* ── Stat cards in hero ── */
    .stat-box {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 10px;
        padding: 0.8rem 1rem;
        text-align: center;
    }
    .stat-box .num { font-size: 1.6rem; font-weight: 700; color: #fff; }
    .stat-box .lab { font-size: 0.75rem; color: #8899aa; text-transform: uppercase; letter-spacing: 0.05em; }

    /* ── Status badge ── */
    .badge {
        display: inline-block; padding: 0.2rem 0.6rem; border-radius: 999px;
        font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
    }
    .badge-green  { background: #2ecc7118; color: #2ecc71; border: 1px solid #2ecc7130; }
    .badge-yellow { background: #f39c1218; color: #f39c12; border: 1px solid #f39c1230; }
    .badge-red    { background: #e74c3c18; color: #e74c3c; border: 1px solid #e74c3c30; }
    .badge-gray   { background: #95a5a618; color: #95a5a6; border: 1px solid #95a5a630; }

    /* ── Status card ── */
    .s-card {
        border-radius: 12px; padding: 1.2rem; text-align: center;
        transition: transform 0.15s;
    }
    .s-card:hover { transform: translateY(-2px); }
    .s-card .icon { font-size: 2rem; }
    .s-card .label { font-size: 0.8rem; color: #8899aa; margin: 0.3rem 0; }
    .s-card .value { font-size: 1.1rem; font-weight: 700; }
    .s-card .meta  { font-size: 0.7rem; color: #667788; margin-top: 0.3rem; }
</style>
"""


def badge_html(status):
    cls = {"healthy": "badge-green", "warning": "badge-yellow",
           "unhealthy": "badge-red", "unknown": "badge-gray",
           "active": "badge-green", "degraded": "badge-yellow",
           "error": "badge-red", "missing": "badge-red",
           "configured": "badge-green", "installed": "badge-green"}
    return f'<span class="badge badge-{cls.get(status, "gray")}">{status}</span>'


def status_card(label, icon, status, detail="", extra=""):
    color_map = {"healthy": "#2ecc71", "warning": "#f39c12",
                 "unhealthy": "#e74c3c", "unknown": "#95a5a6",
                 "active": "#2ecc71", "degraded": "#f39c12",
                 "error": "#e74c3c"}
    c = color_map.get(status, "#95a5a6")
    st.markdown(f"""
    <div class="s-card" style="background:{c}08;border:1px solid {c}30;">
        <div class="icon">{icon}</div>
        <div class="label">{label}</div>
        <div class="value" style="color:{c}">{badge_html(status)}</div>
        <div class="meta">{detail}</div>
        {extra}
    </div>
    """, unsafe_allow_html=True)


def metric_card(label, value):
    st.markdown(f"""
    <div class="stat-box">
        <div class="num">{value}</div>
        <div class="lab">{label}</div>
    </div>
    """, unsafe_allow_html=True)


def format_seconds(s):
    m, s = divmod(int(s), 60)
    return f"{m}m {s}s" if m else f"{s}s"


# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    tf_ok = os.path.isfile(os.path.join(TERRAFORM_DIR, "main.tf"))
    aws_info = check_aws_credentials()
    tf_info = check_terraform_version()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Terraform**  ")
        if tf_info.get("status") == "installed":
            st.markdown(badge_html("installed"), unsafe_allow_html=True)
            st.caption(tf_info.get("version", "").split("v")[-1].split(" ")[0] if "v" in tf_info.get("version", "") else "ok")
        else:
            st.markdown(badge_html("missing"), unsafe_allow_html=True)

    with col2:
        st.markdown(f"**AWS Creds**  ")
        st.markdown(badge_html(aws_info.get("status", "missing")), unsafe_allow_html=True)
        if aws_info.get("status") == "configured":
            acc = aws_info.get("account_id", "")
            st.caption(acc)

    if not tf_ok:
        st.error(f"Terraform dir not found")
        st.stop()

    st.divider()
    st.markdown("### 🆕 New Deployment")

    customer_input = st.text_input(
        "Customer Name",
        placeholder="e.g. ibm, nike, acme",
        help="Lowercase alphanumeric with hyphens.",
    )

    env_input = st.selectbox(
        "Environment",
        options=list(TEMPLATES.keys()),
        format_func=lambda t: f"{t.title()} ({TEMPLATES[t]['instance_type']})",
    )
    st.caption(TEMPLATES[env_input]["desc"])

    domain_input = st.text_input("Root Domain", value="demo.example.com")
    az_input = st.text_input("Availability Zone", value="us-east-1a")

    # Validation badges
    if customer_input:
        valid_n, msg_n = validate_customer_name(customer_input)
        st.markdown(f"**Name:** {badge_html('healthy' if valid_n else 'unhealthy')} {msg_n if not valid_n else ''}", unsafe_allow_html=True)

    is_placeholder = domain_input.strip().lower() in ["example.com", "demo.local", "test.local", "localhost", "test.com"]
    if not is_placeholder and domain_input:
        zone_found, zone_id = has_route53_zone(domain_input)
        st.markdown(f"**Route53 Zone:** {badge_html('healthy' if zone_found else 'warning')}", unsafe_allow_html=True)
        if zone_found:
            st.caption(f"Zone: {zone_id.split('/')[-1] if zone_id else ''}")
        else:
            st.caption("DNS resources disabled (ALB URL only)")

    st.divider()
    deploy_disabled = st.session_state.deploying or st.session_state.destroying

    col_a, col_b = st.columns(2)
    with col_a:
        deploy_btn = st.button(
            "🚀 Deploy", type="primary", use_container_width=True,
            disabled=deploy_disabled,
        )
    with col_b:
        if st.session_state.last_deploy_result:
            destroy_btn = st.button(
                "🗑️ Destroy", type="secondary", use_container_width=True,
                disabled=deploy_disabled,
            )
        else:
            destroy_btn = False

    st.divider()
    st.markdown("### 📋 Validation")
    if st.button("Run Terraform Validate", use_container_width=True):
        with st.spinner("Running validation..."):
            fmt_res = run_terraform_fmt_check()
            val_res = run_terraform_validate()
            st.session_state.validation_results = {"fmt": fmt_res, "validate": val_res}

    if st.session_state.validation_results:
        v = st.session_state.validation_results
        f_pass = v["fmt"]["passed"]
        val_pass = v["validate"]["passed"]
        st.markdown(f"**fmt:** {badge_html('healthy' if f_pass else 'unhealthy')}", unsafe_allow_html=True)
        st.markdown(f"**validate:** {badge_html('healthy' if val_pass else 'unhealthy')}", unsafe_allow_html=True)
        if not f_pass:
            with st.expander("fmt errors"):
                st.code(v["fmt"]["output"])
        if not val_pass:
            with st.expander("validate errors"):
                st.code(v["validate"]["output"])


# ── Hero Header ────────────────────────────────────────────────
workspace_list = list_workspaces(active_only=True)
active_count = len([w for w in workspace_list if w["name"] != "default"])
aws_region = resolve_region()
domain = domain_input if "domain_input" in dir() else "demo.example.com"

col_hero, col_stats = st.columns([2, 1])
with col_hero:
    st.markdown(f"""<div class="hero">
        <h1>🚀 DevOps Pilot</h1>
        <p>Provision &amp; manage customer-specific environments on AWS</p>
    </div>""", unsafe_allow_html=True)

with col_stats:
    st.markdown("<div style='display:flex;gap:0.5rem;'>", unsafe_allow_html=True)
    cc = st.columns(4)
    with cc[0]:
        metric_card("Active Deployments", active_count)
    with cc[1]:
        metric_card("Environments", "2")
    with cc[2]:
        metric_card("Region", aws_region.replace("us-east-1", "us-east-1")[:9])
    with cc[3]:
        current_ws = get_current_workspace()
        metric_card("Workspace", current_ws[:10])
    st.markdown("</div>", unsafe_allow_html=True)

# ── Inject CSS ─────────────────────────────────────────────────
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ── Tabs ───────────────────────────────────────────────────────
tab_deploy, tab_deployments, tab_status, tab_logs = st.tabs(
    ["🚀 Deploy", "📋 Deployments", "✅ Status", "📄 Logs"]
)

# ── TAB: Deploy ────────────────────────────────────────────────
with tab_deploy:
    if deploy_btn:
        valid, result = validate_customer_name(customer_input or "")
        if not valid:
            st.error(result)
        else:
            customer_name = result
            env = env_input
            st.session_state.deploying = True
            st.session_state.log_lines = []
            st.session_state.last_deploy_result = None
            st.session_state.plan_output = None

            with st.status("🚀 Deploying...", expanded=True) as status:
                st.write(f"**Customer:** {customer_name}")
                st.write(f"**Environment:** {env}")
                st.write(f"**Domain:** {domain_input}")
                st.write(f"**AZ:** {az_input}")
                log_placeholder = st.empty()
                accumulated = ""

                start_t = time.time()
                for stream, line in run_terraform(
                    "apply", customer_name, env, domain_input, az_input,
                ):
                    if stream in ("stdout", "stderr"):
                        accumulated += line + "\n"
                        st.session_state.log_lines.append(line)
                        log_placeholder.code(accumulated, language="text", line_numbers=True)
                    elif stream == "exit_code":
                        elapsed = time.time() - start_t
                        if line == 0:
                            status.update(label=f"✅ Deployed {customer_name}-{env} ({format_seconds(elapsed)})", state="complete")
                            st.balloons()
                            wo = _build_workspace_name(customer_name, env)
                            outputs = get_terraform_outputs(wo)
                            st.session_state.last_deploy_result = {
                                "workspace": wo,
                                "customer": customer_name,
                                "environment": env,
                                "outputs": outputs,
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            }
                            st.session_state.refresh_workspaces += 1
                        else:
                            status.update(label=f"❌ Deploy failed ({format_seconds(elapsed)})", state="error")
                    elif stream == "log":
                        pass

            st.session_state.deploying = False

    if destroy_btn and st.session_state.last_deploy_result:
        last = st.session_state.last_deploy_result
        cn = last["customer"]
        ev = last["environment"]
        st.session_state.destroying = True

        with st.status(f"🗑️ Destroying {cn}-{ev}...", expanded=True) as status:
            log_placeholder = st.empty()
            accumulated = ""
            start_t = time.time()
            for stream, line in run_terraform("destroy", cn, ev, domain_input, az_input):
                if stream in ("stdout", "stderr"):
                    accumulated += line + "\n"
                    st.session_state.log_lines.append(line)
                    log_placeholder.code(accumulated, language="text", line_numbers=True)
                elif stream == "exit_code":
                    elapsed = time.time() - start_t
                    if line == 0:
                        status.update(label=f"✅ Destroyed {cn}-{ev} ({format_seconds(elapsed)})", state="complete")
                        st.session_state.last_deploy_result = None
                        st.session_state.refresh_workspaces += 1
                    else:
                        status.update(label=f"❌ Destroy failed ({format_seconds(elapsed)})", state="error")
        st.session_state.destroying = False

    if st.session_state.last_deploy_result:
        st.divider()
        last = st.session_state.last_deploy_result
        outs = last.get("outputs", {})
        st.subheader(f"📊 Last Deployment: {last['customer']}-{last['environment']}")
        st.caption(f"at {last['timestamp']}")

        url = get_output_value(outs, "customer_url") or "N/A"
        st.markdown(f"**Customer URL:** [{url}]({url})")

        row = st.columns(4)
        with row[0]:
            st.metric("Instance ID", get_output_value(outs, "instance_id") or "N/A")
        with row[1]:
            st.metric("ALB DNS", get_output_value(outs, "alb_dns_name") or "N/A")
        with row[2]:
            st.metric("Elastic IP", get_output_value(outs, "elastic_ip") or "N/A")
        with row[3]:
            st.metric("EBS Volume", get_output_value(outs, "ebs_volume_id") or "N/A")

        with st.expander("All Outputs (JSON)"):
            st.json(outs)
            cb = st.button("📋 Copy JSON", key="copy_outputs")
            if cb:
                st.code(json.dumps(outs, indent=2), language="json")
                st.info("Copied! (select all + copy)")

# ── TAB: Deployments ───────────────────────────────────────────
with tab_deployments:
    ws_list = list_workspaces(active_only=True)
    non_default = [w for w in ws_list if w["name"] != "default"]

    if not non_default:
        st.info("No active deployments. Use the Deploy tab to create one.")
    else:
        st.subheader(f"Active Deployments ({len(non_default)})")
        data = []
        for w in non_default:
            outs = get_terraform_outputs(w["name"])
            cn = get_output_value(outs, "customer_name") or w["name"].split("-")[0]
            ev = get_output_value(outs, "environment") or w["name"].split("-")[-1]
            url = get_output_value(outs, "customer_url") or "N/A"
            inst = get_output_value(outs, "instance_id") or "N/A"
            alb = get_output_value(outs, "alb_dns_name") or "N/A"
            eip = get_output_value(outs, "elastic_ip") or "N/A"
            data.append({
                "workspace": w["name"],
                "customer": cn,
                "environment": ev,
                "url": url,
                "instance": inst,
                "alb_dns": alb,
                "eip": eip,
                "current": w["current"],
            })

        st.dataframe(
            [
                {
                    "Customer": d["customer"],
                    "Environment": d["environment"],
                    "URL": d["url"],
                    "Instance": d["instance"],
                    "ALB DNS": d["alb_dns"],
                    "EIP": d["eip"],
                    "Active": "✅" if d["current"] else "",
                }
                for d in data
            ],
            use_container_width=True,
            column_config={
                "URL": st.column_config.TextColumn(width="large"),
            },
        )

        st.divider()
        st.subheader("Actions")
        col_sel, col_act = st.columns([3, 1])
        with col_sel:
            ws_names = [d["workspace"] for d in data]
            sel = st.selectbox("Select Deployment", ws_names)
        with col_act:
            st.write("")
            st.write("")
            if st.button("🔍 View Status", use_container_width=True):
                st.session_state.selected_workspace = sel
                st.session_state.status_results = None

            if st.button("🗑️ Destroy Selected", use_container_width=True, type="secondary"):
                parts = sel.split("-")
                if len(parts) >= 2:
                    cn_d = "-".join(parts[:-1])
                    ev_d = parts[-1]
                    st.session_state.destroying = True
                    with st.status(f"🗑️ Destroying {sel}...", expanded=True) as status:
                        lp = st.empty()
                        acc = ""
                        for s, line in run_terraform("destroy", cn_d, ev_d, domain_input, az_input):
                            if s in ("stdout", "stderr"):
                                acc += line + "\n"
                                st.session_state.log_lines.append(line)
                                lp.code(acc, language="text", line_numbers=True)
                            elif s == "exit_code":
                                if line == 0:
                                    status.update(label=f"✅ Destroyed {sel}", state="complete")
                                    st.session_state.refresh_workspaces += 1
                                    st.rerun()
                                else:
                                    status.update(label=f"❌ Destroy failed", state="error")
                    st.session_state.destroying = False

# ── TAB: Status ────────────────────────────────────────────────
with tab_status:
    ws_list_st = list_workspaces(active_only=True)
    non_default_st = [w for w in ws_list_st if w["name"] != "default"]

    if not non_default_st:
        st.info("No deployments to check. Deploy a customer first.")
    else:
        current_sel = st.session_state.selected_workspace
        if not current_sel or current_sel not in [w["name"] for w in non_default_st]:
            current_sel = non_default_st[0]["name"]
            st.session_state.selected_workspace = current_sel

        ws_names_st = [w["name"] for w in non_default_st]
        sel_st = st.selectbox("Select Deployment to Check", ws_names_st,
                              index=ws_names_st.index(current_sel) if current_sel in ws_names_st else 0)

        if sel_st != st.session_state.selected_workspace:
            st.session_state.selected_workspace = sel_st
            st.session_state.status_results = None

        if st.button("🔄 Refresh Status", use_container_width=True):
            st.session_state.status_results = None

        outs_st = get_terraform_outputs(sel_st)
        instance_id_st = get_output_value(outs_st, "instance_id") or ""
        alb_dns_st = get_output_value(outs_st, "alb_dns_name") or ""
        tg_arn_st = get_output_value(outs_st, "alb_target_group_arn") or ""
        customer_name_st = get_output_value(outs_st, "customer_name") or sel_st.split("-")[0]
        env_st = get_output_value(outs_st, "environment") or sel_st.split("-")[-1]
        domain_st = get_output_value(outs_st, "root_domain") or domain_input
        record_name_st = f"{customer_name_st}.{domain_st}" if domain_st else ""

        st.caption(f"Checking: **{sel_st}** | Instance: {instance_id_st} | ALB: {alb_dns_st[:30]}...")

        if st.session_state.status_results is None:
            with st.spinner("Running health checks..."):
                alb_name_st = f"{customer_name_st}-{env_st}-alb"
                results_st = get_full_status(
                    instance_id=instance_id_st,
                    alb_dns=alb_dns_st,
                    target_group_arn=tg_arn_st,
                    alb_name=alb_name_st,
                    domain=domain_st,
                    record_name=record_name_st,
                )
                st.session_state.status_results = results_st

        results_st = st.session_state.status_results
        if results_st:
            overall = results_st.get("overall", "unknown")
            ov_color = {"healthy": "#2ecc71", "warning": "#f39c12", "degraded": "#e74c3c", "unknown": "#95a5a6"}
            st.markdown(f"""
            <div style="background:{ov_color.get(overall,'#95a5a6')}10;
                        border:2px solid {ov_color.get(overall,'#95a5a6')};
                        border-radius:12px;padding:1.2rem;text-align:center;margin-bottom:1.5rem;">
                <span style="font-size:1.1rem;font-weight:600;">
                    Overall: <span style="color:{ov_color.get(overall,'#95a5a6')}">{overall.upper()}</span>
                </span>
                <span style="margin-left:1rem;">{badge_html(overall)}</span>
            </div>
            """, unsafe_allow_html=True)

            r1 = st.columns(5)
            cards = [
                ("EC2 Instance", results_st.get("ec2", {}), "🖥️"),
                ("ALB", results_st.get("alb", {}), "⚖️"),
                ("Target Group", results_st.get("target_group", {}), "🎯"),
                ("Route53", results_st.get("route53", {}), "🌐"),
                ("Containers", results_st.get("containers", {}), "🐳"),
            ]
            for i, (label, data, icon) in enumerate(cards):
                with r1[i]:
                    detail = data.get("detail", "")
                    extra = ""
                    if label == "Target Group" and data.get("healthy_count") is not None:
                        extra = f"<div class='meta'>{data['healthy_count']} healthy / {data.get('unhealthy_count',0)} unhealthy</div>"
                    if label == "ALB" and data.get("listeners"):
                        lis_str = ", ".join([f"{l['protocol']}:{l['port']}" for l in data["listeners"]])
                        extra = f"<div class='meta'>{lis_str}</div>"
                    if label == "Route53" and data.get("zone_name"):
                        extra = f"<div class='meta'>Zone: {data['zone_name']}</div>"
                    status_card(label, icon, data.get("status", "unknown"), detail, extra)

            with st.expander("Detailed Status Data"):
                st.json(results_st)
                # Transform JSON for display
                display_data = {}
                for k, v in results_st.items():
                    display_data[k] = {kk: vv for kk, vv in v.items() if kk not in ('registered_targets',)}
                st.json(display_data)

# ── TAB: Logs ──────────────────────────────────────────────────
with tab_logs:
    st.subheader("📄 Deployment Logs")
    if st.session_state.log_lines:
        log_text = "\n".join(st.session_state.log_lines)
        search_term = st.text_input("🔍 Search logs", placeholder="Search...")
        if search_term:
            filtered = [l for l in st.session_state.log_lines if search_term.lower() in l.lower()]
            display_text = "\n".join(filtered)
            st.caption(f"Showing {len(filtered)} of {len(st.session_state.log_lines)} lines")
        else:
            display_text = log_text
            st.caption(f"{len(st.session_state.log_lines)} lines")

        st.code(display_text, language="text", line_numbers=True)

        col_cl, col_dl = st.columns(2)
        with col_cl:
            if st.button("📋 Copy All Logs", use_container_width=True):
                st.code(log_text, language="text")
                st.info("Select all + copy")
        with col_dl:
            st.download_button(
                "⬇️ Download Logs",
                data=log_text,
                file_name=f"devops-pilot-logs-{int(time.time())}.txt",
                mime="text/plain",
                use_container_width=True,
            )
    else:
        st.info("No logs yet. Run a deploy or destroy to see logs here.")

    if st.button("🗑️ Clear Logs"):
        st.session_state.log_lines = []
        st.rerun()


# ── Helper ─────────────────────────────────────────────────────
def _build_workspace_name(customer_name, environment):
    return f"{customer_name}-{environment}"
