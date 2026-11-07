# =============================================================================
# URTC-COMMON - tests/test_vision_faults.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Faults and cuts in the thermal vision path, on a simulated camera: the image over CAN (requests 0x254, data 0x255) and the sensor link frames.

The camera here is a simulated node that answers a chunk request with the four frames of eight bytes the specification describes, and the bus is the
``FaultyBus`` of the scenarios (frames lost, repeated, shortened, a silent camera). The reader in this file is the smallest host that can recover from those
faults (ask again for the chunk that did not come, never accept a short or a repeated one as new data); it holds that the protocol CAN be recovered, it is not the
code of a panel. Evidence: simulator. What a real sensor does with its refresh rate and its noise is for a bench.
"""
from __future__ import annotations

import pytest

from urtc_common import bus_scenario as bs
from urtc_common import sensor_frame as sf
from urtc_common import thermal_view as tv


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class SimulatedCamera:
    """A head with the thermal inspection tool: one request, four frames of data."""

    def __init__(self, frame: list[list[float]]) -> None:
        self.chunks = tv.encode_chunks(frame)
        self.queue: list[tuple[int, bytes]] = []
        self.requests: list[int] = []

    def open_channel(self, *a, **k) -> None:
        pass

    def close_channel(self) -> None:
        pass

    def close(self) -> None:
        pass

    def send_frame(self, can_id: int, data: bytes = b"") -> None:
        if can_id != tv.CAN_ID_CALIBRATED_REQUEST or len(data) < 1 or data[0] >= len(self.chunks):
            return   # a request that is not well formed gets no answer
        self.requests.append(data[0])
        chunk = self.chunks[data[0]]
        for part in range(tv.FRAMES_PER_CHUNK):
            self.queue.append((tv.CAN_ID_CALIBRATED_CHUNK, chunk[part * 8:(part + 1) * 8]))

    def read_frame(self, timeout: float = 0.05):
        return self.queue.pop(0) if self.queue else None


def bus_with(faults: list[dict], frame=None, seed: int = 5):
    clock = FakeTime()
    camera = SimulatedCamera(frame or tv.synthetic_frame())
    scenario = bs.from_dict({"format": bs.FORMAT, "name": "vision", "seed": seed, "faults": faults})
    return bs.FaultyBus(camera, scenario, clock=clock.clock, sleep=clock.sleep), camera


def read_chunk(bus, index: int, tries: int = 6) -> bytes | None:
    """One chunk: ask, collect exactly four frames of eight bytes, and ask again if they did not all come."""
    for _ in range(tries):
        bus.send_frame(tv.CAN_ID_CALIBRATED_REQUEST, bytes([index]))
        parts = []
        while True:
            got = bus.read_frame(0.01)
            if got is None:
                break
            if got[0] == tv.CAN_ID_CALIBRATED_CHUNK and len(got[1]) == 8:
                parts.append(got[1])
        if len(parts) == tv.FRAMES_PER_CHUNK:
            return b"".join(parts)
    return None


def read_image(bus, variant: str = "90640", tries: int = 6) -> list[list[float]]:
    chunks = {}
    for index in range(tv.chunk_count(variant)):
        data = read_chunk(bus, index, tries)
        if data is not None:
            chunks[index] = data
    return tv.assemble(chunks, variant)


# ---- the image over a bus with faults ---------------------------------------------------------------------------------------------------
def test_a_clean_bus_gives_back_the_image_of_the_camera_exactly():
    frame = tv.synthetic_frame()
    bus, camera = bus_with([], frame)
    assert read_image(bus) == frame and camera.requests == list(range(48))


def test_lost_frames_are_recovered_by_asking_the_chunk_again():
    frame = tv.synthetic_frame()
    bus, camera = bus_with([{"fault": "drop", "direction": "rx", "per_mille": 120}], frame)
    assert read_image(bus, tries=12) == frame
    assert len(camera.requests) > 48 and bus.stats["drop"] > 0   # some chunks had to be asked for again


def test_a_burst_that_swallows_whole_chunks_is_recovered_too():
    frame = tv.synthetic_frame()
    bus, _ = bus_with([{"fault": "burst_loss", "direction": "rx", "length": 5, "period": 40}], frame)
    assert read_image(bus, tries=12) == frame


def test_a_repeated_frame_is_not_taken_for_new_data():
    frame = tv.synthetic_frame()
    bus, _ = bus_with([{"fault": "duplicate", "direction": "rx", "id": tv.CAN_ID_CALIBRATED_CHUNK, "count": 1}], frame)
    # five frames came for the first chunk: the reader, which wants exactly four, asks again instead of gluing a wrong chunk together
    assert read_image(bus, tries=3) == frame


def test_a_shortened_frame_is_never_glued_into_the_image():
    frame = tv.synthetic_frame()
    bus, _ = bus_with([{"fault": "truncate", "direction": "rx", "id": tv.CAN_ID_CALIBRATED_CHUNK, "dlc": 4, "count": 3}], frame)
    assert read_image(bus, tries=4) == frame


def test_a_silent_camera_gives_an_incomplete_image_that_is_refused_not_painted():
    bus, camera = bus_with([{"fault": "mute", "direction": "tx"}])
    with pytest.raises(tv.ThermalError, match="48 chunk"):
        read_image(bus, tries=2)
    assert camera.requests == []


def test_a_camera_that_dies_half_way_leaves_the_missing_chunks_named():
    bus, _ = bus_with([{"fault": "mute", "direction": "rx", "from": 24 * 4}])     # the answers stop after chunk 23
    with pytest.raises(tv.ThermalError, match="first 24"):
        read_image(bus, tries=2)


def test_a_request_for_a_chunk_that_does_not_exist_gets_no_answer():
    bus, camera = bus_with([])
    bus.send_frame(tv.CAN_ID_CALIBRATED_REQUEST, bytes([48]))
    bus.send_frame(tv.CAN_ID_CALIBRATED_REQUEST, b"")
    assert bus.read_frame(0.01) is None and camera.requests == []


def test_the_small_variant_is_read_with_its_own_twelve_chunks():
    frame = tv.synthetic_frame(16, 12)
    bus, camera = bus_with([], frame)
    assert read_image(bus, "90641") == frame and camera.requests == list(range(12))


# ---- pixels that are not numbers and values out of range -------------------------------------------------------------------------------------
def test_a_burnt_pixel_is_painted_apart_and_does_not_move_the_scale_or_the_statistics():
    frame = tv.synthetic_frame()
    frame[3][4] = float("nan")
    frame[5][6] = float("inf")
    lo, hi = tv.scale_of(frame)
    assert 20 <= lo < hi < 90
    rgb = tv.false_color(frame)
    assert rgb[3][4] == tv.INVALID_COLOR and rgb[5][6] == tv.INVALID_COLOR
    stats = tv.region_stats(frame, 0, 0, 32, 24)
    assert stats is not None and stats.invalid == 2 and stats.pixels == 32 * 24 - 2


def test_a_value_beyond_what_the_wire_holds_is_clamped_not_wrapped():
    frame = [[400.0] * 16, [-400.0] * 16]
    out = tv.assemble(tv.encode_chunks(frame + [[0.0] * 16] * 10), "90641")
    assert out[0][0] == 327.67 and out[1][0] == -327.68   # int16 of hundredths: a hot spot stays hot, a cold one stays cold, nothing wraps to the other side


# ---- the sensor link of the vision head ----------------------------------------------------------------------------------------------------
def scan(stream: bytes):
    """Frames out of a stream the way a receiver must: look for the start byte, try the frame, and on failure move one byte on (never skip a whole candidate)."""
    frames, rejected, pos = [], {}, 0
    while pos < len(stream):
        if stream[pos] != sf.SOF:
            pos += 1
            continue
        status, frame = sf.parse_frame(stream[pos:])
        if status == sf.OK and frame is not None:
            frames.append(frame)
            pos += sf.HEADER_SIZE + len(frame["payload"]) + 1
            continue
        if status == "incomplete":
            break   # the rest waits for more bytes
        rejected[status] = rejected.get(status, 0) + 1
        pos += 1
    return frames, rejected


def stream_of(count: int, sensor: int = sf.SENSOR_ID_THERMAL) -> list[bytes]:
    return [sf.encode_frame(sensor, n, 1000 + n * 100, sf.encode_thermal_payload(2500 + n)) for n in range(count)]


def test_a_stream_with_a_cut_in_the_middle_loses_one_frame_and_resynchronises():
    frames = stream_of(10)
    data = b"".join(frames[:4]) + frames[4][:7] + b"".join(frames[5:])      # the cable flickered inside frame 4
    got, rejected = scan(data)
    assert [f["seq"] for f in got] == [0, 1, 2, 3, 5, 6, 7, 8, 9]
    assert sum(rejected.values()) >= 1


def test_every_single_bit_flip_in_a_frame_is_rejected_and_the_next_frame_survives():
    frames = stream_of(3)
    for bit in range(8 * len(frames[1])):
        damaged = bytearray(frames[1])
        damaged[bit // 8] ^= 1 << (bit % 8)
        got, _ = scan(frames[0] + bytes(damaged) + frames[2])
        seqs = [f["seq"] for f in got]
        assert seqs[0] == 0 and seqs[-1] == 2        # the neighbours always arrive
        assert 1 not in seqs or bytes(damaged)[3] == 1   # the damaged one is never taken for good (unless the flip left the sequence byte untouched and the CRC still held: impossible for one bit)


def test_noise_before_and_between_frames_is_skipped():
    frames = stream_of(4)
    got, _ = scan(b"\x00\x01\x02" + frames[0] + b"\xb6\xb6\xb6" + frames[1] + b"\xff" * 5 + frames[2] + frames[3])
    assert [f["seq"] for f in got] == [0, 1, 2, 3]


def test_a_gap_in_the_sequence_is_visible_to_whoever_watches_for_lost_readings():
    got, _ = scan(b"".join(f for n, f in enumerate(stream_of(12)) if n not in (4, 5, 9)))
    seqs = [f["seq"] for f in got]
    gaps = [(a, b) for a, b in zip(seqs, seqs[1:], strict=False) if (b - a) & 0xFF != 1]
    assert gaps == [(3, 6), (8, 10)]
    assert [(b - a - 1) & 0xFF for a, b in gaps] == [2, 1]


def test_two_sensors_on_one_link_keep_their_own_sequences():
    thermal, trigger = stream_of(5), stream_of(5, sf.SENSOR_ID_RGB_TRIGGER)
    mixed = [x for pair in zip(thermal, trigger, strict=True) for x in pair]
    got, _ = scan(b"".join(mixed))
    by_sensor = {}
    for f in got:
        by_sensor.setdefault(f["sensor_id"], []).append(f["seq"])
    assert by_sensor == {sf.SENSOR_ID_THERMAL: [0, 1, 2, 3, 4], sf.SENSOR_ID_RGB_TRIGGER: [0, 1, 2, 3, 4]}


@pytest.mark.parametrize("centi,status", [(-4001, "temp_out_of_range"), (30001, "temp_out_of_range"), (-4000, "ok"), (30000, "ok")])
def test_a_reading_outside_the_range_of_the_sensor_is_refused_at_the_edge(centi, status):
    assert sf.validate_thermal(sf.encode_thermal_payload(centi))[0] == status


def test_a_frame_of_the_old_layout_is_refused_and_never_read_as_another_number():
    old = bytearray(sf.encode_frame(sf.SENSOR_ID_THERMAL, 1, 5, sf.encode_thermal_payload(2500)))
    old[1] = 1
    assert sf.parse_frame(bytes(old))[0] == "unsupported_version"
