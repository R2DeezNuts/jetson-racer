import argparse
import socket
import sys
import time
from pathlib import Path

from socket_vision.config_loader import load_runtime_config
from socket_vision.control.protocol import recv_json_line, send_json_line


def send_cmd(sock: socket.socket, cmd: str, expect_response: bool = True):
    send_json_line(sock, {"cmd": cmd})
    if not expect_response:
        return
    res = recv_json_line(sock)
    if not res.get("ok"):
        raise RuntimeError(res)


def interactive_line(sock: socket.socket):
    print("Control interactivo (linea): w=forward, a=left, d=right, s=backward, espacio=stop, q=quit")
    while True:
        raw = input("> ").strip().lower()
        if raw in ("w", "forward"):
            cmd = "forward"
        elif raw in ("a", "left"):
            cmd = "left"
        elif raw in ("d", "right"):
            cmd = "right"
        elif raw in ("s", "back", "backward", "reverse"):
            cmd = "backward"
        elif raw in ("", "stop", " "):
            cmd = "stop"
        elif raw in ("q", "quit", "exit"):
            try:
                send_cmd(sock, "stop", expect_response=False)
            except Exception:
                pass
            print("bye")
            return
        else:
            print("comando no valido")
            continue

        send_cmd(sock, cmd, expect_response=False)
        print(f"sent: {cmd}")


def interactive_keys(sock: socket.socket):
    import select
    import termios
    import tty

    if not sys.stdin.isatty():
        interactive_line(sock)
        return

    print("Control teclado directo: w/a/d mover, s atras, espacio stop, q salir")
    print("El teclado tiene prioridad temporal sobre el auto-centrado.")
    print("No hace falta pulsar Enter.")

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 0.2)
            if not r:
                continue
            ch = sys.stdin.read(1).lower()

            if ch == "w":
                send_cmd(sock, "forward", expect_response=False)
                print("sent: forward")
            elif ch == "a":
                send_cmd(sock, "left", expect_response=False)
                print("sent: left")
            elif ch == "d":
                send_cmd(sock, "right", expect_response=False)
                print("sent: right")
            elif ch == "s":
                send_cmd(sock, "backward", expect_response=False)
                print("sent: backward")
            elif ch == " ":
                send_cmd(sock, "stop", expect_response=False)
                print("sent: stop")
            elif ch == "q":
                try:
                    send_cmd(sock, "stop", expect_response=False)
                except Exception:
                    pass
                print("bye")
                return
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def main():
    p = argparse.ArgumentParser(description="Laptop client for Jetson car control")
    p.add_argument("--config", default=None, help="Legacy single config file")
    p.add_argument("--config-dir", default="socket_vision")
    p.add_argument("--cmd", choices=["forward", "left", "right", "backward", "stop"], default=None)
    p.add_argument("--duration", type=float, default=0.0)
    args = p.parse_args()

    cfg = load_runtime_config(config_path=args.config, config_dir=args.config_dir)
    host = cfg["network"].get("jetson_control_ip", "192.168.1.43")
    port = int(cfg["control"].get("port", 5060))

    with socket.create_connection((host, port), timeout=4) as sock:
        sock.settimeout(8)
        print(f"connected to {host}:{port}")

        if args.cmd:
            send_cmd(sock, args.cmd, expect_response=False)
            if args.duration > 0 and args.cmd != "stop":
                time.sleep(args.duration)
                # Best-effort safety stop: do not block terminal if ACK is delayed.
                send_cmd(sock, "stop", expect_response=False)
            return

        interactive_keys(sock)


if __name__ == "__main__":
    main()
