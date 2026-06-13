#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$(dirname "$0")/load_global_env.sh"
JETSON_HOST="${JETSON_HOST:-jetson@192.168.1.34}"
SSH_KEY="${SSH_KEY:-${SSH_KEY_GLOBAL:-$HOME/.ssh/id_ed25519_jetson}}"
REMOTE_DIR="${REMOTE_DIR:-${REMOTE_DIR_GLOBAL:-~/socket_vision_project}}"

SSH_OPTS=(-o BatchMode=yes)
SCP_OPTS=(-o BatchMode=yes)
if [[ -f "${SSH_KEY}" ]]; then
  SSH_OPTS+=(-i "${SSH_KEY}" -o IdentitiesOnly=yes)
  SCP_OPTS+=(-i "${SSH_KEY}" -o IdentitiesOnly=yes)
fi

STAGE_DIR="$(mktemp -d /tmp/socket_vision_min_sync.XXXXXX)"
cleanup() {
  rm -rf "${STAGE_DIR}"
}
trap cleanup EXIT

mkdir -p "${STAGE_DIR}/socket_vision"

# Paquete base.
cp -f "${ROOT_DIR}/socket_vision/__init__.py" "${STAGE_DIR}/socket_vision/"
cp -f "${ROOT_DIR}/socket_vision/config_loader.py" "${STAGE_DIR}/socket_vision/"
cp -f "${ROOT_DIR}/socket_vision/global_config.json" "${STAGE_DIR}/socket_vision/"

# Runtime Jetson (2 modulos principales).
mkdir -p "${STAGE_DIR}/socket_vision/jetson"
cp -f "${ROOT_DIR}/socket_vision/jetson/__init__.py" "${STAGE_DIR}/socket_vision/jetson/"
cp -f "${ROOT_DIR}/socket_vision/jetson/sender.py" "${STAGE_DIR}/socket_vision/jetson/"
cp -f "${ROOT_DIR}/socket_vision/jetson/control_server.py" "${STAGE_DIR}/socket_vision/jetson/"

# Dependencias directas importadas por sender/control_server.
mkdir -p "${STAGE_DIR}/socket_vision/conexion"
cp -f "${ROOT_DIR}/socket_vision/conexion/__init__.py" "${STAGE_DIR}/socket_vision/conexion/"
cp -f "${ROOT_DIR}/socket_vision/conexion/protocol.py" "${STAGE_DIR}/socket_vision/conexion/"

mkdir -p "${STAGE_DIR}/socket_vision/control"
cp -f "${ROOT_DIR}/socket_vision/control/__init__.py" "${STAGE_DIR}/socket_vision/control/"
cp -f "${ROOT_DIR}/socket_vision/control/protocol.py" "${STAGE_DIR}/socket_vision/control/"

# Config minima consumida por load_runtime_config.
mkdir -p "${STAGE_DIR}/socket_vision/conexion/config"
cp -f "${ROOT_DIR}/socket_vision/conexion/config/default_config.json" "${STAGE_DIR}/socket_vision/conexion/config/"
mkdir -p "${STAGE_DIR}/socket_vision/control/config"
cp -f "${ROOT_DIR}/socket_vision/control/config/default_config.json" "${STAGE_DIR}/socket_vision/control/config/"
mkdir -p "${STAGE_DIR}/socket_vision/vision/config"
cp -f "${ROOT_DIR}/socket_vision/vision/config/default_config.json" "${STAGE_DIR}/socket_vision/vision/config/"

ssh -n "${SSH_OPTS[@]}" "${JETSON_HOST}" "mkdir -p ${REMOTE_DIR} && rm -rf ${REMOTE_DIR}/socket_vision"
scp -r "${SCP_OPTS[@]}" "${STAGE_DIR}/socket_vision" "${JETSON_HOST}:${REMOTE_DIR}/"
echo "[sync] uploaded MINIMAL socket_vision runtime -> ${JETSON_HOST}:${REMOTE_DIR}/socket_vision"
echo "[sync] included: jetson/{sender.py,control_server.py}, protocols, config_loader, and config json files"
