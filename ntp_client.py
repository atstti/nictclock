"""Small SNTP client: RFC 5905 four-timestamp calculation and validation."""

import math
import socket
import struct
import time
import threading
from concurrent.futures import Future, TimeoutError as FutureTimeout
from dataclasses import dataclass

EPOCH = 2208988800
ERA = 2**32


class NTPError(Exception):
    pass


class RateLimitError(NTPError):
    pass


_resolver_lock = threading.Lock()
_resolver_future = None
_resolver_host = None


def resolve(server, timeout):
    # One outstanding daemon resolver bounds both wait time and resource use.
    global _resolver_future, _resolver_host
    with _resolver_lock:
        if _resolver_future is None or _resolver_future.done():
            future = Future()
            _resolver_future, _resolver_host = future, server

            def run():
                try:
                    future.set_result(
                        socket.getaddrinfo(server, 123, type=socket.SOCK_DGRAM)
                    )
                except Exception as exc:
                    future.set_exception(exc)

            threading.Thread(target=run, daemon=True, name="NTP-DNS").start()
        elif _resolver_host != server:
            raise NTPError("DNS解決待ちです。しばらくして再試行します")
        future = _resolver_future
    try:
        return future.result(timeout=timeout)
    except FutureTimeout as exc:
        raise NTPError("DNS解決がタイムアウトしました") from exc


@dataclass(frozen=True)
class Sample:
    utc: float
    monotonic_ns: int
    offset: float
    rtt: float
    server: str


def encode_timestamp(unix):
    value = unix + EPOCH
    seconds = math.floor(value)
    return struct.pack("!II", seconds % ERA, int((value - seconds) * ERA))


def decode_timestamp(raw, reference):
    seconds, fraction = struct.unpack("!II", raw)
    value = seconds + fraction / ERA - EPOCH
    return value + round((reference - value) / ERA) * ERA


def parse_response(data, origin, t1, t4, mono, server):
    if len(data) < 48:
        raise NTPError("NTP応答が短すぎます")
    leap, version, mode = data[0] >> 6, (data[0] >> 3) & 7, data[0] & 7
    if mode != 4 or version not in (3, 4) or leap == 3:
        raise NTPError("NTP応答が無効、またはサーバーが未同期です")
    if data[1] == 0:
        raise RateLimitError("サーバーが要求を制限しています（KoD）")
    if not 1 <= data[1] <= 15 or data[24:32] != origin:
        raise NTPError("NTP階層または送信元タイムスタンプが不正です")
    if data[32:40] == bytes(8) or data[40:48] == bytes(8):
        raise NTPError("サーバー時刻が空です")
    t2 = decode_timestamp(data[32:40], t4)
    t3 = decode_timestamp(data[40:48], t4)
    delay = (t4 - t1) - (t3 - t2)
    if t3 < t2 or delay < -0.002 or delay > 10:
        raise NTPError("NTP応答の遅延が不正です")
    offset = ((t2 - t1) + (t3 - t4)) / 2
    return Sample(t4 + offset, mono, offset, max(0, delay), server)


def query(server="ntp.nict.jp", timeout=3.0):
    # DNS and sockets run only in the background worker. Connected UDP filters peers.
    try:
        deadline = time.monotonic() + timeout
        addresses = resolve(server, timeout)
        last = None
        for family, kind, proto, _, address in addresses[:4]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                with socket.socket(family, kind, proto) as sock:
                    sock.settimeout(remaining)
                    sock.connect(address)
                    t1, m1 = time.time(), time.monotonic_ns()
                    origin = encode_timestamp(t1)
                    packet = bytes([0x23, 0, 6, 236]) + bytes(36) + origin
                    sock.send(packet)
                    data = sock.recv(4096)
                    m4 = time.monotonic_ns()
                    # Derive destination timestamp from monotonic elapsed time.
                    t4 = t1 + (m4 - m1) / 1e9
                    return parse_response(data, origin, t1, t4, m4, server)
            except OSError as exc:
                last = exc
        raise last or TimeoutError()
    except socket.gaierror as exc:
        raise NTPError("DNS解決に失敗しました。接続を確認してください") from exc
    except OSError as exc:
        raise NTPError(
            "時刻を取得できません。接続またはUDP 123を確認してください"
        ) from exc
