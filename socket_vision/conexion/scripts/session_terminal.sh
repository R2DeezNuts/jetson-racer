#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
SESSION_DIR="${SESSION_DIR:?SESSION_DIR is required}"
TERMINAL_CMD="${TERMINAL_CMD:?TERMINAL_CMD is required}"

cleanup_session() {
  local count_file="${SESSION_DIR}/count"
  local lock_dir="${SESSION_DIR}/lock"

  mkdir "${lock_dir}" 2>/dev/null || true
  if [[ -f "${count_file}" ]]; then
    local count
    count="$(cat "${count_file}")"
    if [[ "${count}" =~ ^[0-9]+$ ]] && [[ "${count}" -gt 0 ]]; then
      count="$((count - 1))"
      printf '%s\n' "${count}" > "${count_file}"
      if [[ "${count}" -eq 0 ]]; then
        "${ROOT_DIR}/socket_vision/conexion/scripts/cleanup_remote.sh"
        rm -rf "${SESSION_DIR}"
      fi
    fi
  fi
  rmdir "${lock_dir}" 2>/dev/null || true
}

trap cleanup_session EXIT INT TERM

cd "${ROOT_DIR}"
eval "${TERMINAL_CMD}"
