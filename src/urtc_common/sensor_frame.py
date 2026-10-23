"""The frame of the sensor link of the vision head (URTC-VISION-TOOL) and the thermal reading it carries.

The frame, byte by byte::

    SOF 0xB6 | VERSION | SENSOR_ID | SEQ | TIMESTAMP_MS (4 bytes, big-endian) | LEN | PAYLOAD (0..16) | CRC-8

The CRC-8 (polynomial 0x07) covers everything from the start byte through the last payload byte. A thermal reading
is a signed 16-bit number in hundredths of a degree Celsius, big-endian like every multi-byte value of the URTC bus,
and must lie between -40.00 and 300.00 degrees. Version 2 is the big-endian layout; version 1 (little-endian) is not
accepted, so a frame of the old layout is refused as an unsupported version instead of being read as a different number.

The vectors in ``conformance/sensor_vectors.json`` are checked against the C code of the vision head and against this
module, so the two cannot drift apart unnoticed.

Standard library only. Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
"""
from __future__ import annotations

SOF = 0xB6
VERSION = 2
MAX_PAYLOAD = 16
SENSOR_ID_THERMAL = 0x01
SENSOR_ID_RGB_TRIGGER = 0x02
MIN_TEMP_CENTIDEGREES_C = -4000
MAX_TEMP_CENTIDEGREES_C = 30000
HEADER_SIZE = 9  # SOF, version, sensor id, sequence, timestamp (4), length

OK = "ok"
FRAME_STATUSES = ("incomplete", "bad_sof", "unsupported_version", "length_out_of_range", "crc_mismatch")
READING_STATUSES = ("wrong_payload_len", "temp_out_of_range")


def crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def encode_frame(sensor_id: int, seq: int, timestamp_ms: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload too long")
    body = bytes([SOF, VERSION, sensor_id & 0xFF, seq & 0xFF]) + (timestamp_ms & 0xFFFFFFFF).to_bytes(4, "big") + bytes([len(payload)]) + bytes(payload)
    return body + bytes([crc8(body)])


def parse_frame(buf: bytes) -> tuple[str, dict | None]:
    """(status, frame): the frame is a dict with sensor_id, seq, timestamp_ms and payload when the status is ``ok``."""
    if len(buf) < HEADER_SIZE + 1:
        return "incomplete", None
    if buf[0] != SOF:
        return "bad_sof", None
    if buf[1] != VERSION:
        return "unsupported_version", None
    length = buf[8]
    if length > MAX_PAYLOAD:
        return "length_out_of_range", None
    total = HEADER_SIZE + length + 1
    if len(buf) < total:
        return "incomplete", None
    if crc8(buf[:HEADER_SIZE + length]) != buf[HEADER_SIZE + length]:
        return "crc_mismatch", None
    return OK, {"sensor_id": buf[2], "seq": buf[3], "timestamp_ms": int.from_bytes(buf[4:8], "big"),
                "payload": bytes(buf[HEADER_SIZE:HEADER_SIZE + length])}


def encode_thermal_payload(centidegrees_c: int) -> bytes:
    return int(centidegrees_c).to_bytes(2, "big", signed=True)


def validate_thermal(payload: bytes) -> tuple[str, int | None]:
    """(status, centidegrees) of a thermal payload; the number is None unless the status is ``ok``."""
    if len(payload) != 2:
        return "wrong_payload_len", None
    value = int.from_bytes(payload, "big", signed=True)
    if value < MIN_TEMP_CENTIDEGREES_C or value > MAX_TEMP_CENTIDEGREES_C:
        return "temp_out_of_range", None
    return OK, value
