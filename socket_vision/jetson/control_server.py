import argparse
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict

from socket_vision.config_loader import load_runtime_config
from socket_vision.control.protocol import recv_json_line, send_json_line


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class CarController:
    def __init__(self, cfg: Dict, dry_run: bool = False):
        self.dry_run = dry_run
        self.car = None
        self.lock = threading.Lock()
        self.ctrl = cfg["control"]
        if not self.dry_run:
            from jetracer.nvidia_racecar import NvidiaRacecar

            self.car = NvidiaRacecar()
            steering_gain = float(self.ctrl.get("steering_gain", 1.0))
            steering_offset = float(self.ctrl.get("steering_offset", 0.0))
            if hasattr(self.car, "steering_gain"):
                self.car.steering_gain = steering_gain
            if hasattr(self.car, "steering_offset"):
                self.car.steering_offset = steering_offset
            self.car.steering = 0.0
            self.car.throttle = 0.0
            print(f"[control] steering calibration gain={steering_gain:.3f} offset={steering_offset:.3f}")

    def apply(self, steering: float, throttle: float):
        with self.lock:
            if self.dry_run:
                print(f"[control] DRY steering={steering:.3f} throttle={throttle:.3f}")
                return
            steering_cmd = float(_clamp(steering, -1.0, 1.0))
            throttle_cmd = float(_clamp(throttle, -1.0, 1.0))

            # jetracer maps steering with: servo = steering * steering_gain + steering_offset.
            # Keep the final servo command inside [-1, 1] to avoid runtime ValueError.
            gain = float(getattr(self.car, "steering_gain", 1.0))
            offset = float(getattr(self.car, "steering_offset", 0.0))
            servo_cmd = (steering_cmd * gain) + offset
            if servo_cmd > 1.0 or servo_cmd < -1.0:
                if abs(gain) > 1e-6:
                    steering_hi = (1.0 - offset) / gain
                    steering_lo = (-1.0 - offset) / gain
                    steering_min = min(steering_lo, steering_hi)
                    steering_max = max(steering_lo, steering_hi)
                    steering_cmd = float(_clamp(steering_cmd, steering_min, steering_max))
                else:
                    steering_cmd = 0.0

            self.car.steering = steering_cmd
            self.car.throttle = throttle_cmd

    def stop(self):
        self.apply(0.0, 0.0)


def play_sound(sound_file: Path):
    if not sound_file.exists():
        return
    cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(sound_file)]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


class CommandArbiter:
    def __init__(self, car: CarController, cfg: Dict):
        self.car = car
        self.cfg = cfg
        self.ctrl = cfg["control"]
        self.lock = threading.Lock()
        self.manual_override_until = 0.0
        self.auto_last_ts = 0.0
        self.last_mode = "idle"
        self.last_reason = "startup"

    def _play_manual_sound(self, cmd: str):
        sounds = self.ctrl.get("sound_map", {})
        sound_dir = Path(self.ctrl.get("sound_dir", "socket_vision/control/assets/sounds"))
        sound_file = sounds.get(cmd)
        if sound_file:
            play_sound(sound_dir / sound_file)

    def apply_manual(self, cmd: str):
        f_th = float(self.ctrl.get("forward_throttle", 0.26))
        t_th = float(self.ctrl.get("turn_throttle", 0.20))
        t_st = float(self.ctrl.get("turn_steering", 0.58))
        r_th = float(self.ctrl.get("reverse_throttle", -0.18))
        steering_sign = self.steering_sign()
        manual_override_sec = float(self.ctrl.get("manual_override_sec", 1.8))
        manual_stop_override_sec = float(self.ctrl.get("manual_stop_override_sec", 3.0))

        if cmd == "forward":
            steering = 0.0
            throttle = f_th
        elif cmd == "left":
            steering = -t_st * steering_sign
            throttle = t_th
        elif cmd == "right":
            steering = t_st * steering_sign
            throttle = t_th
        elif cmd == "backward":
            steering = 0.0
            throttle = r_th
        elif cmd == "stop":
            steering = 0.0
            throttle = 0.0
        else:
            raise ValueError(f"Unknown command: {cmd}")

        with self.lock:
            self.car.apply(steering, throttle)
            hold = manual_stop_override_sec if cmd == "stop" else manual_override_sec
            self.manual_override_until = time.monotonic() + hold
            self.last_mode = "manual"
            self.last_reason = cmd
            self._play_manual_sound(cmd)
            return {"ok": True, "cmd": cmd, "applied": True, "mode": "manual", "reason": cmd}

    def apply_auto(self, req: Dict):
        now = time.monotonic()
        with self.lock:
            if now < self.manual_override_until:
                return {
                    "ok": True,
                    "cmd": "auto_drive",
                    "applied": False,
                    "mode": "manual_override",
                    "reason": "manual_override_active",
                }

            steering = _clamp(float(req.get("steering", 0.0)) * self.steering_sign(), -1.0, 1.0)
            throttle = _clamp(float(req.get("throttle", 0.0)), -1.0, 1.0)
            self.car.apply(steering, throttle)
            self.auto_last_ts = time.monotonic()
            self.last_mode = str(req.get("mode", "auto"))
            self.last_reason = str(req.get("reason", "auto"))
            return {
                "ok": True,
                "cmd": "auto_drive",
                "applied": True,
                "mode": self.last_mode,
                "reason": self.last_reason,
            }

    def steering_sign(self) -> float:
        sign = float(self.ctrl.get("steering_sign", 1.0))
        return -1.0 if sign < 0 else 1.0

    def watchdog_loop(self):
        timeout = float(self.ctrl.get("autonomy_command_timeout_sec", 1.0))
        while True:
            time.sleep(0.1)
            with self.lock:
                if self.last_mode not in ("idle", "manual", "timeout_stop") and self.auto_last_ts > 0.0:
                    if (time.monotonic() - self.auto_last_ts) > timeout:
                        self.car.stop()
                        self.last_mode = "timeout_stop"
                        self.last_reason = "autonomy_timeout"


def handle_client(conn: socket.socket, addr, arbiter: CommandArbiter):
    print(f"[control] client connected: {addr}")
    try:
        while True:
            req = recv_json_line(conn)
            cmd = str(req.get("cmd", "")).strip().lower()
            if cmd in {"forward", "left", "right", "backward", "stop"}:
                res = arbiter.apply_manual(cmd)
            elif cmd == "auto_drive":
                res = arbiter.apply_auto(req)
            elif cmd == "ping":
                res = {"ok": True, "cmd": "ping", "applied": True}
            else:
                raise ValueError(f"Unknown command: {cmd}")
            res["ts"] = time.time()
            send_json_line(conn, res)
    except ConnectionError:
        pass
    except Exception as exc:
        print(f"[control] client/session error from {addr}: {exc}")
        try:
            send_json_line(conn, {"ok": False, "error": str(exc), "ts": time.time()})
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    p = argparse.ArgumentParser(description="Jetson car control server")
    p.add_argument("--config", default=None, help="Legacy single config file")
    p.add_argument("--config-dir", default="socket_vision")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    cfg = load_runtime_config(config_path=args.config, config_dir=args.config_dir)
    ctrl = cfg["control"]
    host = ctrl.get("listen_ip", "0.0.0.0")
    port = int(ctrl.get("port", 5060))

    car = CarController(cfg, dry_run=bool(args.dry_run))
    arbiter = CommandArbiter(car, cfg)

    watchdog = threading.Thread(target=arbiter.watchdog_loop, daemon=True)
    watchdog.start()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    print(f"[control] listening on {host}:{port}")

    try:
        while True:
            conn, addr = server.accept()
            conn.settimeout(float(ctrl.get("socket_timeout_sec", 120)))
            thread = threading.Thread(target=handle_client, args=(conn, addr, arbiter), daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print("[control] interrupted")
    finally:
        try:
            car.stop()
        except Exception:
            pass
        server.close()


if __name__ == "__main__":
    main()
