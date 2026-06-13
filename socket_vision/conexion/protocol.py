import socket
import struct
import time
from typing import Dict, Optional, Tuple

HEADER_LEN = 4
TS_LEN = 8


def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Socket closed while receiving data")
        data.extend(chunk)
    return bytes(data)


def send_frame(sock: socket.socket, jpeg_bytes: bytes, timestamp_ns: int) -> None:
    payload = struct.pack("!Q", timestamp_ns) + jpeg_bytes
    header = struct.pack("!I", len(payload))
    sock.sendall(header + payload)


def recv_frame(sock: socket.socket) -> Tuple[int, bytes]:
    header = recv_exact(sock, HEADER_LEN)
    payload_len = struct.unpack("!I", header)[0]
    if payload_len < TS_LEN:
        raise ValueError(f"Invalid payload length: {payload_len}")
    payload = recv_exact(sock, payload_len)
    timestamp_ns = struct.unpack("!Q", payload[:TS_LEN])[0]
    return timestamp_ns, payload[TS_LEN:]


# UDP video framing.
UDP_MAGIC = b"SV"
UDP_VER = 1
UDP_HDR_FMT = "!2sBIQHH"
UDP_HDR_LEN = struct.calcsize(UDP_HDR_FMT)


def _is_newer_u32(a: int, b: Optional[int]) -> bool:
    if b is None:
        return True
    if a == b:
        return False
    return ((a - b) & 0xFFFFFFFF) < 0x80000000


def send_frame_udp(
    sock: socket.socket,
    addr: Tuple[str, int],
    jpeg_bytes: bytes,
    timestamp_ns: int,
    frame_id: int,
    max_datagram_bytes: int = 1200,
) -> int:
    if max_datagram_bytes <= UDP_HDR_LEN + 16:
        raise ValueError("max_datagram_bytes too small")
    chunk_size = max_datagram_bytes - UDP_HDR_LEN
    total_chunks = max(1, (len(jpeg_bytes) + chunk_size - 1) // chunk_size)
    if total_chunks > 65535:
        raise ValueError("frame too large for UDP chunk format")
    sent = 0
    for idx in range(total_chunks):
        start = idx * chunk_size
        end = start + chunk_size
        payload = jpeg_bytes[start:end]
        hdr = struct.pack(
            UDP_HDR_FMT,
            UDP_MAGIC,
            UDP_VER,
            frame_id & 0xFFFFFFFF,
            int(timestamp_ns),
            total_chunks,
            idx,
        )
        sock.sendto(hdr + payload, addr)
        sent += 1
    return sent


class UdpFrameAssembler:
    def __init__(self, max_inflight_frames: int = 8):
        self.max_inflight_frames = max(2, int(max_inflight_frames))
        self.frames: Dict[int, Dict] = {}
        self.latest_complete: Optional[Tuple[int, bytes]] = None
        self.latest_complete_id: Optional[int] = None

    def _trim_inflight(self):
        if len(self.frames) <= self.max_inflight_frames:
            return
        # Drop oldest ids first.
        ids = sorted(self.frames.keys())
        for fid in ids[: max(0, len(ids) - self.max_inflight_frames)]:
            self.frames.pop(fid, None)

    def feed_packet(self, packet: bytes) -> Optional[Tuple[int, bytes]]:
        if len(packet) < UDP_HDR_LEN:
            return None
        magic, ver, frame_id, ts_ns, total_chunks, chunk_idx = struct.unpack(UDP_HDR_FMT, packet[:UDP_HDR_LEN])
        if magic != UDP_MAGIC or ver != UDP_VER:
            return None
        if total_chunks <= 0 or chunk_idx >= total_chunks:
            return None
        payload = packet[UDP_HDR_LEN:]
        st = self.frames.get(frame_id)
        if st is None:
            st = {
                "ts": ts_ns,
                "total": int(total_chunks),
                "parts": {},
                "created_ns": time.time_ns(),
            }
            self.frames[frame_id] = st
            self._trim_inflight()
        if st["total"] != int(total_chunks):
            # Corrupted/mixed frame id, reset this frame id bucket.
            st = {
                "ts": ts_ns,
                "total": int(total_chunks),
                "parts": {},
                "created_ns": time.time_ns(),
            }
            self.frames[frame_id] = st
        st["parts"][int(chunk_idx)] = payload
        if len(st["parts"]) == st["total"]:
            jpeg = b"".join(st["parts"][i] for i in range(st["total"]))
            self.frames.pop(frame_id, None)
            if _is_newer_u32(frame_id, self.latest_complete_id):
                self.latest_complete = (int(st["ts"]), jpeg)
                self.latest_complete_id = frame_id
            return int(st["ts"]), jpeg
        return None

    def pop_latest_complete(self) -> Optional[Tuple[int, bytes]]:
        out = self.latest_complete
        self.latest_complete = None
        return out
