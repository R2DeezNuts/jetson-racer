#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
SYNC_CMD="./socket_vision/conexion/scripts/sync_to_jetson.sh"
VISION_CMD="./socket_vision/conexion/scripts/launch_all_from_laptop.sh"
CONTROL_CMD="./socket_vision/conexion/scripts/run_control_client.sh"
SESSION_DIR="/tmp/socket_vision_session_$$"

find_terminal() {
  if command -v gnome-terminal >/dev/null 2>&1; then
    echo "gnome-terminal"
    return
  fi
  if command -v x-terminal-emulator >/dev/null 2>&1; then
    echo "x-terminal-emulator"
    return
  fi
  if command -v konsole >/dev/null 2>&1; then
    echo "konsole"
    return
  fi
  if command -v xfce4-terminal >/dev/null 2>&1; then
    echo "xfce4-terminal"
    return
  fi
  if command -v xterm >/dev/null 2>&1; then
    echo "xterm"
    return
  fi
  return 1
}

open_terminal() {
  local terminal="$1"
  local title="$2"
  local command="$3"
  local wrapped="cd '${ROOT_DIR}' && SESSION_DIR='${SESSION_DIR}' TERMINAL_CMD=\"${command}\" ./socket_vision/conexion/scripts/session_terminal.sh; exec bash"

  case "${terminal}" in
    gnome-terminal)
      gnome-terminal --title="${title}" -- bash -lc "${wrapped}"
      ;;
    x-terminal-emulator)
      x-terminal-emulator -T "${title}" -e bash -lc "${wrapped}"
      ;;
    konsole)
      konsole --new-tab -p tabtitle="${title}" -e bash -lc "${wrapped}"
      ;;
    xfce4-terminal)
      xfce4-terminal --title="${title}" --command="bash -lc \"${wrapped}\""
      ;;
    xterm)
      xterm -T "${title}" -e bash -lc "${wrapped}"
      ;;
    *)
      echo "[main] no supported terminal emulator found." >&2
      exit 1
      ;;
  esac
}

TERMINAL="$(find_terminal)" || {
  echo "[main] no supported terminal emulator found (tried gnome-terminal, x-terminal-emulator, konsole, xfce4-terminal, xterm)." >&2
  exit 1
}

cd "${ROOT_DIR}"
echo "[main] syncing project to Jetson..."
"${SYNC_CMD}"
mkdir -p "${SESSION_DIR}"
printf '2\n' > "${SESSION_DIR}/count"

open_terminal "${TERMINAL}" "Socket Vision - Vision" "${VISION_CMD}"
sleep 1
open_terminal "${TERMINAL}" "Socket Vision - Control" "${CONTROL_CMD}"

echo "[main] synced project and launched vision and control terminals using ${TERMINAL}."
echo "[main] remote cleanup will run automatically when the last session terminal closes."
