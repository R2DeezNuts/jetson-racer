#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../../.."
source ./socket_vision/conexion/scripts/load_global_env.sh
export PYTHONPATH="$PWD:${PYTHONPATH:-}"

# Ensure remote control server is up before opening interactive control.
./socket_vision/conexion/scripts/start_remote_control_server.sh >/dev/null

ready=0
for _ in {1..60}; do
  if "${PYTHON_BIN}" - << 'PY'
import socket
from socket_vision.config_loader import load_runtime_config
cfg = load_runtime_config(config_dir="socket_vision")
host = cfg["network"].get("jetson_control_ip", "192.168.1.34")
port = int(cfg["control"].get("port", 5060))
s = socket.socket()
s.settimeout(0.5)
try:
    s.connect((host, port))
except Exception:
    raise SystemExit(1)
finally:
    s.close()
PY
  then
    ready=1
    break
  fi
  sleep 0.5
done

if [[ "$ready" -ne 1 ]]; then
  echo "[control] no se pudo levantar el servidor remoto en Jetson (puerto control cerrado)." >&2
  exit 1
fi

"${PYTHON_BIN}" -m socket_vision.control.laptop_control_client --config-dir socket_vision "$@"
