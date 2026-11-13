import socket
from dataclasses import replace
from unittest.mock import patch
import pytest
from config import Config, load, save
from ntp_client import (
    encode_timestamp,
    parse_response,
    decode_timestamp,
    NTPError,
    query,
    Sample,
)
from time_service import TimeService, hand_angles


def response(t1, t2, t3):
    packet = bytearray(48)
    packet[0] = 0x24
    packet[1] = 1
    packet[24:32] = encode_timestamp(t1)
    packet[32:40] = encode_timestamp(t2)
    packet[40:48] = encode_timestamp(t3)
    return packet


def test_four_timestamp_calculation():
    t = 1700000000
    result = parse_response(
        response(t, t + 0.03, t + 0.04), encode_timestamp(t), t, t + 0.05, 100, "test"
    )
    assert result.offset == pytest.approx(0.01, abs=1e-6)
    assert result.rtt == pytest.approx(0.04, abs=1e-6)
    assert result.utc == pytest.approx(t + 0.06, abs=1e-6)


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.__setitem__(0, 0xE4),
        lambda p: p.__setitem__(0, 0x23),
        lambda p: p.__setitem__(1, 0),
        lambda p: p.__setitem__(1, 16),
        lambda p: p.__setitem__(24, 1),
        lambda p: p.__setitem__(slice(32, 40), bytes(8)),
    ],
)
def test_invalid_packets(change):
    t = 1700000000
    packet = response(t, t + 0.01, t + 0.02)
    change(packet)
    with pytest.raises(NTPError):
        parse_response(packet, encode_timestamp(t), t, t + 0.05, 100, "test")


def test_short_packet():
    with pytest.raises(NTPError):
        parse_response(b"", b"", 0, 0, 0, "test")


def test_era_rollover():
    t = 2200000000.125
    assert decode_timestamp(encode_timestamp(t), t) == t


def test_monotonic_and_failed_sync_fallback():
    mono = [1000000000]
    wall = [1700000000]
    service = TimeService(lambda: wall[0], lambda: mono[0])
    wall[0] += 3600
    mono[0] += 500000000
    assert service.now() == 1700000000.5
    with patch("ntp_client.socket.getaddrinfo", side_effect=socket.gaierror()):
        with pytest.raises(NTPError):
            query()
    assert service.now() == 1700000000.5
    assert service.sample is None
    service.synchronize(Sample(1800000000, mono[0], 0.01, 0.02, "test"))
    mono[0] += 2000000000
    assert service.now() == 1800000002
    assert service.age() == 2


@pytest.mark.parametrize("hour", [0, 12, 24])
def test_noon_midnight(hour):
    assert hand_angles(hour, 0, 0) == (0, 0, 0)
    before = hand_angles(hour + 11, 59, 59, 999000)
    assert before[0] > 359.99 and before[1] > 359.99


def test_sweep():
    a = hand_angles(3, 4, 5, 125000)
    b = hand_angles(3, 4, 5, 126000)
    assert a[2] == 30.75
    assert all(y > x for x, y in zip(a, b))
    assert hand_angles(3, 4, 5, 999000, False)[2] == 30


def test_config_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    cfg = replace(
        Config(), theme="Dark", transparent=True, timezone="UTC", milliseconds=True
    )
    save(cfg, path)
    assert load(path) == cfg
    path.write_text("{invalid")
    assert load(path) == Config()
    path.write_text('{"interval": 0}')
    assert load(path) == Config()


def test_mock_udp_query():
    from unittest.mock import MagicMock

    fake = MagicMock()
    fake.__enter__.return_value = fake
    t = 1700000000
    fake.recv.return_value = bytes(response(t, t + 0.03, t + 0.04))
    with (
        patch(
            "ntp_client.resolve",
            return_value=[
                (socket.AF_INET, socket.SOCK_DGRAM, 17, "", ("127.0.0.1", 123))
            ],
        ),
        patch("ntp_client.socket.socket", return_value=fake),
        patch("ntp_client.time.time", return_value=t),
        patch("ntp_client.time.monotonic_ns", side_effect=[1000000000, 1050000000]),
    ):
        result = query("mock")
    assert result.offset == pytest.approx(0.01, abs=1e-6)
    assert fake.send.call_args.args[0][0] == 0x23
    assert len(fake.send.call_args.args[0]) == 48
    fake.connect.assert_called_once_with(("127.0.0.1", 123))


def test_invalid_config_types(tmp_path):
    path = tmp_path / "settings.json"
    for content in (
        '{"server": 123}',
        '{"seconds": "yes"}',
        '{"timezone": "Missing/Zone"}',
        "[]",
    ):
        path.write_text(content)
        assert load(path) == Config()
