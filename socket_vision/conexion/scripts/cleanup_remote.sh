#!/usr/bin/env bash
set -euo pipefail

JETSON_HOST="${JETSON_HOST:-jetson@192.168.1.34}"
SSH_KEY="${SSH_KEY:-${SSH_KEY_GLOBAL:-$HOME/.ssh/id_ed25519_jetson}}"

SSH_OPTS=(-o BatchMode=yes)
if [[ -f "${SSH_KEY}" ]]; then
  SSH_OPTS+=(-i "${SSH_KEY}" -o IdentitiesOnly=yes)
fi

ssh -n "${SSH_OPTS[@]}" "${JETSON_HOST}" "
  pkill -f '[s]ocket_vision.jetson.sender' || true
  pkill -f '[s]ocket_vision.jetson.control_server' || true
  pkill -f '[s]ocket_vision/jetson/sender.py' || true
  pkill -f '[s]ocket_vision/jetson/control_server.py' || true
" >/dev/null 2>&1 || true

echo "[cleanup] remote sender and control server stopped."
