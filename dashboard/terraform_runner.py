import subprocess
import os
import re
import json
import threading
from queue import Queue, Empty

TERRAFORM_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "terraform")
)


def _stream_output(proc, queue):
    try:
        for line in iter(proc.stdout.readline, ""):
            queue.put(("stdout", line.rstrip()))
    except ValueError:
        pass
    try:
        for line in iter(proc.stderr.readline, ""):
            queue.put(("stderr", line.rstrip()))
    except ValueError:
        pass
    proc.stdout.close()
    proc.stderr.close()
    queue.put(("done", None))


def _is_placeholder_domain(domain):
    exact_placeholders = ["example.com", "demo.local", "test.local", "localhost", "test.com"]
    return domain.strip().lower() in exact_placeholders


def _build_workspace_name(customer_name, environment):
    return f"{customer_name}-{environment}"


def _select_workspace(workspace, log_callback=None):
    try:
        list_result = subprocess.run(
            ["terraform", "workspace", "list"],
            cwd=TERRAFORM_DIR,
            capture_output=True,
            text=True,
            env={**os.environ, "TF_IN_AUTOMATION": "1"},
        )
        existing = list_result.stdout
        current = None
        for line in existing.splitlines():
            stripped = line.strip()
            if stripped.startswith("* "):
                current = stripped[2:]
            if stripped.lstrip("* ") == workspace:
                current = stripped.lstrip("* ")

        if current == workspace:
            return True
        if workspace in existing:
            result = subprocess.run(
                ["terraform", "workspace", "select", workspace],
                cwd=TERRAFORM_DIR,
                capture_output=True, text=True,
                env={**os.environ, "TF_IN_AUTOMATION": "1"},
            )
            if result.returncode != 0:
                return False
            return True
        result = subprocess.run(
            ["terraform", "workspace", "new", workspace],
            cwd=TERRAFORM_DIR,
            capture_output=True, text=True,
            env={**os.environ, "TF_IN_AUTOMATION": "1"},
        )
        return result.returncode == 0
    except Exception:
        return False


def run_terraform_init():
    proc = subprocess.Popen(
        ["terraform", "init"],
        cwd=TERRAFORM_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True, bufsize=1,
        env={**os.environ, "TF_IN_AUTOMATION": "1"},
    )
    for line in iter(proc.stdout.readline, ""):
        yield "stdout", line.rstrip()
    for line in iter(proc.stderr.readline, ""):
        yield "stderr", line.rstrip()
    proc.stdout.close()
    proc.stderr.close()
    proc.wait()
    yield "exit_code", proc.returncode


def run_terraform_plan(customer_name, environment, root_domain, az):
    workspace = _build_workspace_name(customer_name, environment)
    if not _select_workspace(workspace):
        yield "stderr", f"Failed to select/create workspace: {workspace}"
        yield "exit_code", 1
        return

    create_dns = "false" if _is_placeholder_domain(root_domain) else "true"
    cmd = [
        "terraform", "plan",
        f"-var=customer_name={customer_name}",
        f"-var=environment={environment}",
        f"-var=root_domain={root_domain}",
        f"-var=availability_zone={az}",
        f"-var=create_dns_resources={create_dns}",
    ]
    proc = subprocess.Popen(
        cmd, cwd=TERRAFORM_DIR,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
        env={**os.environ, "TF_IN_AUTOMATION": "1"},
    )
    for line in iter(proc.stdout.readline, ""):
        yield "stdout", line.rstrip()
    for line in iter(proc.stderr.readline, ""):
        yield "stderr", line.rstrip()
    proc.stdout.close(); proc.stderr.close()
    proc.wait()
    yield "exit_code", proc.returncode


def run_terraform(action, customer_name, environment, root_domain, az):
    workspace = _build_workspace_name(customer_name, environment)
    if not _select_workspace(workspace):
        yield "stderr", f"Failed to select/create workspace: {workspace}"
        yield "exit_code", 1
        yield "log", ""
        return

    create_dns = "false" if _is_placeholder_domain(root_domain) else "true"
    cmd = [
        "terraform", action, "-auto-approve",
        f"-var=customer_name={customer_name}",
        f"-var=environment={environment}",
        f"-var=root_domain={root_domain}",
        f"-var=availability_zone={az}",
        f"-var=create_dns_resources={create_dns}",
    ]
    env_overrides = {**os.environ, "TF_IN_AUTOMATION": "1"}
    proc = subprocess.Popen(
        cmd, cwd=TERRAFORM_DIR,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, env=env_overrides,
    )
    queue = Queue()
    thread = threading.Thread(target=_stream_output, args=(proc, queue))
    thread.daemon = True
    thread.start()

    log_lines = []
    while True:
        try:
            stream, line = queue.get(timeout=0.1)
            if stream == "done":
                break
            log_lines.append(line)
            yield stream, line
        except Empty:
            if proc.poll() is not None:
                break
    proc.wait()
    yield "exit_code", proc.returncode
    yield "log", "\n".join(log_lines)


def get_terraform_outputs(workspace=None):
    if workspace:
        subprocess.run(
            ["terraform", "workspace", "select", workspace],
            cwd=TERRAFORM_DIR, capture_output=True, text=True,
            env={**os.environ, "TF_IN_AUTOMATION": "1"},
        )
    try:
        result = subprocess.run(
            ["terraform", "output", "-json"],
            cwd=TERRAFORM_DIR,
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "TF_IN_AUTOMATION": "1"},
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return {}


def get_output_value(outputs_json, key):
    if key in outputs_json:
        val = outputs_json[key]
        if isinstance(val, dict) and "value" in val:
            return val["value"]
        return val
    return None


def list_workspaces(active_only=False):
    try:
        result = subprocess.run(
            ["terraform", "workspace", "list"],
            cwd=TERRAFORM_DIR,
            capture_output=True, text=True,
            env={**os.environ, "TF_IN_AUTOMATION": "1"},
        )
        if result.returncode != 0:
            return []
        workspaces = []
        current_workspace = None
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("* "):
                current_workspace = stripped[2:]
                workspaces.append({"name": current_workspace, "current": True})
            elif stripped:
                workspaces.append({"name": stripped, "current": False})
        if active_only:
            workspaces = [w for w in workspaces if w["name"] != "default"]
        return workspaces
    except Exception:
        return []


def get_current_workspace():
    try:
        result = subprocess.run(
            ["terraform", "workspace", "show"],
            cwd=TERRAFORM_DIR,
            capture_output=True, text=True,
            env={**os.environ, "TF_IN_AUTOMATION": "1"},
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "default"


def run_terraform_fmt_check():
    try:
        result = subprocess.run(
            ["terraform", "fmt", "-check", "-recursive"],
            cwd=TERRAFORM_DIR,
            capture_output=True, text=True,
            env={**os.environ, "TF_IN_AUTOMATION": "1"},
        )
        return {
            "passed": result.returncode == 0,
            "output": result.stdout if result.returncode != 0 else "All files formatted correctly.",
            "returncode": result.returncode,
        }
    except Exception as e:
        return {"passed": False, "output": str(e), "returncode": -1}


def run_terraform_validate():
    try:
        result = subprocess.run(
            ["terraform", "validate"],
            cwd=TERRAFORM_DIR,
            capture_output=True, text=True,
            env={**os.environ, "TF_IN_AUTOMATION": "1"},
        )
        return {
            "passed": result.returncode == 0,
            "output": result.stdout + result.stderr,
            "returncode": result.returncode,
        }
    except Exception as e:
        return {"passed": False, "output": str(e), "returncode": -1}
