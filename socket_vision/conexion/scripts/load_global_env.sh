#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
GLOBAL_CFG="${ROOT_DIR}/socket_vision/global_config.json"

# Local runtime Python (laptop). Override with PYTHON_BIN if needed.
export PYTHON_BIN="${PYTHON_BIN:-$HOME/venvs/vision/bin/python}"
# Remote runtime Python (Jetson). Override with REMOTE_PYTHON_BIN if needed.
export REMOTE_PYTHON_BIN="${REMOTE_PYTHON_BIN:-python3}"

if [[ ! -f "${GLOBAL_CFG}" ]]; then
  return 0 2>/dev/null || exit 0
fi

readarray -t _SV_GLOBAL < <("${PYTHON_BIN}" - "${GLOBAL_CFG}" <<'PY'
import json
import os
import pathlib
import sys

p = pathlib.Path(sys.argv[1])
cfg = json.loads(p.read_text(encoding="utf-8"))
net = cfg.get("network", {})
ssh = cfg.get("ssh", {})

jetson_ip = str(net.get("jetson_ip", "")).strip()
jetson_ctrl_ip = str(net.get("jetson_control_ip", jetson_ip)).strip()
jetson_user = str(ssh.get("jetson_user", "jetson")).strip() or "jetson"
jetson_host = str(ssh.get("jetson_host", jetson_ip)).strip()
ssh_key = os.path.expanduser(str(ssh.get("ssh_key", "")).strip())
remote_dir = str(ssh.get("remote_dir", "~/socket_vision_project")).strip() or "~/socket_vision_project"

if not jetson_host:
    jetson_host = jetson_ip

if "@" in jetson_host:
    jetson_host_user = jetson_host
else:
    jetson_host_user = f"{jetson_user}@{jetson_host}"

print(f"JETSON_IP={jetson_ip}")
print(f"JETSON_CONTROL_IP={jetson_ctrl_ip}")
print(f"JETSON_USER={jetson_user}")
print(f"JETSON_HOST={jetson_host_user}")
print(f"SSH_KEY_GLOBAL={ssh_key}")
print(f"REMOTE_DIR_GLOBAL={remote_dir}")
PY
)

for kv in "${_SV_GLOBAL[@]}"; do
  export "$kv"
done
