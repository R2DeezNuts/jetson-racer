#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$(dirname "$0")/load_global_env.sh"
JETSON_HOST="${JETSON_HOST:-jetson@192.168.1.34}"
SSH_KEY="${SSH_KEY:-${SSH_KEY_GLOBAL:-$HOME/.ssh/id_ed25519_jetson}}"
REMOTE_DIR="${REMOTE_DIR:-${REMOTE_DIR_GLOBAL:-~/socket_vision_project}}"
REMOTE_LOG="${REMOTE_LOG:-/tmp/socket_vision_sender.log}"
REMOTE_CONTROL_LOG="${REMOTE_CONTROL_LOG:-/tmp/socket_vision_control_server.log}"
RECEIVER_ARGS="${RECEIVER_ARGS:-}"

export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}"
SSH_OPTS=(-o BatchMode=yes)
if [[ -f "${SSH_KEY}" ]]; then
  SSH_OPTS+=(-i "${SSH_KEY}" -o IdentitiesOnly=yes)
else
  echo "[launcher] warning: SSH_KEY not found (${SSH_KEY}), using default ssh identities."
fi
CLEANED_UP=0

cleanup() {
  if [[ "${CLEANED_UP}" -eq 1 ]]; then
    return
  fi
  CLEANED_UP=1
  echo "[launcher] stopping remote sender..."
  ssh -n "${SSH_OPTS[@]}" -o ConnectTimeout=5 "${JETSON_HOST}" \
    "pkill -f '[s]ocket_vision.jetson.sender' || true; pkill -f '[s]ocket_vision/jetson/sender.py' || true" >/dev/null 2>&1 || true
  echo "[launcher] stopping remote control server..."
  ssh -n "${SSH_OPTS[@]}" -o ConnectTimeout=5 "${JETSON_HOST}" \
    "pkill -f '[s]ocket_vision.jetson.control_server' || true; pkill -f '[s]ocket_vision/jetson/control_server.py' || true" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "[launcher] stopping stale remote processes on ${JETSON_HOST} ..."
ssh -n "${SSH_OPTS[@]}" "${JETSON_HOST}" \
  "pkill -f '[s]ocket_vision.jetson.sender' || true; \
   pkill -f '[s]ocket_vision.jetson.control_server' || true; \
   pkill -f '[s]ocket_vision/jetson/sender.py' || true; \
   pkill -f '[s]ocket_vision/jetson/control_server.py' || true" >/dev/null 2>&1 || true

echo "[launcher] starting sender on ${JETSON_HOST} ..."
ssh -f -n "${SSH_OPTS[@]}" "${JETSON_HOST}" "
  cd ${REMOTE_DIR} && \
  export PYTHONPATH=\$PWD && \
  nohup ${REMOTE_PYTHON_BIN} -u -m socket_vision.jetson.sender --config-dir socket_vision > ${REMOTE_LOG} 2>&1 < /dev/null &
"

echo "[launcher] sender started. remote log: ${REMOTE_LOG}"
echo "[launcher] starting remote control server on ${JETSON_HOST} ..."
ssh -f -n "${SSH_OPTS[@]}" "${JETSON_HOST}" "
  cd ${REMOTE_DIR} && \
  export PYTHONPATH=\$PWD && \
  nohup ${REMOTE_PYTHON_BIN} -u -m socket_vision.jetson.control_server --config-dir socket_vision > ${REMOTE_CONTROL_LOG} 2>&1 < /dev/null &
"
echo "[launcher] control server started. remote log: ${REMOTE_CONTROL_LOG}"
echo "[launcher] waiting for remote control port 5060 ..."
READY=0
for _ in {1..60}; do
  if ssh -n "${SSH_OPTS[@]}" "${JETSON_HOST}" "ss -ltn | grep -q ':5060 '" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 0.5
done
if [[ "${READY}" -ne 1 ]]; then
  echo "[launcher] warning: control server port 5060 not ready yet; receiver will continue and retry." >&2
fi
echo "[launcher] starting local receiver..."
"${PYTHON_BIN}" -u -m socket_vision.conexion.receiver --config-dir socket_vision ${RECEIVER_ARGS}
