#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/load_global_env.sh"

JETSON_HOST="${JETSON_HOST:-jetson@192.168.1.34}"
SSH_KEY="${SSH_KEY:-${SSH_KEY_GLOBAL:-$HOME/.ssh/id_ed25519_jetson}}"
REMOTE_DIR="${REMOTE_DIR:-${REMOTE_DIR_GLOBAL:-~/socket_vision_project}}"
REMOTE_LOG="${REMOTE_LOG:-/tmp/socket_vision_control_server.log}"

SSH_OPTS=(-o BatchMode=yes)
if [[ -f "${SSH_KEY}" ]]; then
  SSH_OPTS+=(-i "${SSH_KEY}" -o IdentitiesOnly=yes)
fi

if ssh -n "${SSH_OPTS[@]}" "${JETSON_HOST}" "ss -ltn | grep -q ':5060 '" >/dev/null 2>&1; then
  echo "[control] remote server already running on ${JETSON_HOST}. reusing existing process."
  exit 0
fi

ssh -n "${SSH_OPTS[@]}" "${JETSON_HOST}" "pkill -f '[s]ocket_vision.jetson.control_server' || true; pkill -f '[s]ocket_vision/jetson/control_server.py' || true" >/dev/null 2>&1 || true

ssh -f -n "${SSH_OPTS[@]}" "${JETSON_HOST}" "
  cd ${REMOTE_DIR} && \
  export PYTHONPATH=\$PWD && \
  nohup ${REMOTE_PYTHON_BIN} -u -m socket_vision.jetson.control_server --config-dir socket_vision > ${REMOTE_LOG} 2>&1 < /dev/null &
"

# Wait until port is listening (Jetson init can take several seconds).
for _ in {1..60}; do
  if ssh -n "${SSH_OPTS[@]}" "${JETSON_HOST}" "ss -ltn | grep -q ':5060 '" >/dev/null 2>&1; then
    echo "[control] remote server started on ${JETSON_HOST}. log=${REMOTE_LOG}"
    exit 0
  fi
  sleep 0.5
done

echo "[control] failed to start remote server on ${JETSON_HOST}. check ${REMOTE_LOG}" >&2
exit 1
