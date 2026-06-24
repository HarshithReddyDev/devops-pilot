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
    for line in iter(proc.stdout.readline, ""):
        queue.put(("stdout", line.rstrip()))
    for line in iter(proc.stderr.readline, ""):
        queue.put(("stderr", line.rstrip()))
    proc.stdout.close()
    proc.stderr.close()
    queue.put(("done", None))


def _is_placeholder_domain(domain):
    placeholders = [
        "example.com",
        "demo.local",
        "test.local",
        "localhost",
        "test.com",
    ]
    return any(d in domain.lower() for d in placeholders)


def run_terraform(action, customer_name, environment, root_domain, az):
    create_dns = "false" if _is_placeholder_domain(root_domain) else "true"

    cmd = [
        "terraform",
        action,
        "-auto-approve",
        f"-var=customer_name={customer_name}",
        f"-var=environment={environment}",
        f"-var=root_domain={root_domain}",
        f"-var=availability_zone={az}",
        f"-var=create_dns_resources={create_dns}",
    ]

    env_overrides = {**os.environ, "TF_IN_AUTOMATION": "1"}

    proc = subprocess.Popen(
        cmd,
        cwd=TERRAFORM_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env_overrides,
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


def parse_outputs(log_text):
    outputs = {}
    for line in log_text.splitlines():
        m = re.match(r"^(\w+)\s*=\s*(.+)$", line.strip())
        if m:
            val = m.group(2).strip().strip('"')
            outputs[m.group(1)] = val
    return outputs


def get_terraform_outputs():
    try:
        result = subprocess.run(
            ["terraform", "output", "-json"],
            cwd=TERRAFORM_DIR,
            capture_output=True,
            text=True,
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
