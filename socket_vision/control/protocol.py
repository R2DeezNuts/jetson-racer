import json
import socket
from typing import Dict


def send_json_line(sock: socket.socket, payload: Dict) -> None:
    sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))


def recv_json_line(sock: socket.socket) -> Dict:
    data = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("socket closed")
        if chunk == b"\n":
            break
        data.extend(chunk)
    return json.loads(data.decode("utf-8"))
