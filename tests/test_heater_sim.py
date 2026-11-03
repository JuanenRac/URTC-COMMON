# =============================================================================
# URTC-COMMON - tests/test_heater_sim.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The simulated soldering iron: the plant, the loop, the watchdog and the telemetry frames of the virtual board."""
from __future__ import annotations

import json

from urtc_common import protocol
from urtc_common.heater_sim import CONFIG_PATH, SolderingIronModel, load_config
from urtc_common.virtual_board import VirtualBoard


def _temps(frames):
    return [int.from_bytes(d, "big") for i, d in frames if i == protocol.CAN_ID_SOLDER_TELEMETRY]


def test_config_file_holds_every_parameter():
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config = load_config()
    assert all(k in data for k in config)


def test_override_wins_over_file():
    assert load_config(kp=9.0)["kp"] == 9.0


def test_no_setpoint_stays_at_ambient():
    model = SolderingIronModel()
    model.advance(5.0)
    assert abs(model.temperature_c - model.config["ambient_c"]) < 1e-6


def test_reaches_setpoint_and_holds():
    model = SolderingIronModel()
    for _ in range(300):   # refresh the setpoint like the host does, 30 s of simulated time
        model.set_target(320)
        model.advance(0.1)
    assert abs(model.temperature_c - 320) < 3.0
    assert model.peak_c < 320 + 20   # limited overshoot


def test_duty_is_clamped():
    model = SolderingIronModel()
    model.set_target(400)
    model.advance(0.05)
    assert 0.0 <= model.duty <= 1.0
    assert model.duty == 1.0   # far from the target: full power


def test_watchdog_drops_target_and_cools():
    model = SolderingIronModel()
    for _ in range(200):
        model.set_target(300)
        model.advance(0.1)
    hot = model.temperature_c
    model.advance(60.0)   # no refresh
    assert model.setpoint_c == 0
    assert model.duty == 0.0
    assert model.temperature_c < hot - 100


def test_setpoint_is_clamped_to_the_maximum():
    model = SolderingIronModel()
    model.set_target(5000)
    assert model.setpoint_c == model.config["max_temperature_c"]


def test_telemetry_period():
    model = SolderingIronModel()
    model.set_target(200)
    frames = model.advance(1.5)
    assert len(frames) == 10   # 1500 ms / 150 ms


def test_board_without_setpoint_sends_nothing():
    board = VirtualBoard()
    assert board.advance(2.0) == []


def test_board_runs_the_loop_from_the_setpoint_frame():
    board = VirtualBoard(tool_id=protocol.TOOL_SOLDERING_IRON)
    temps = []
    for _ in range(300):
        assert board.handle(*protocol.encode_solder_setpoint(280)) == []
        temps += _temps(board.advance(0.1))
    assert temps and temps == sorted(temps) or temps[-1] > temps[0]
    assert abs(temps[-1] - 280) <= 3


def test_board_of_another_tool_ignores_the_setpoint():
    board = VirtualBoard(tool_id=protocol.TOOL_HOT_AIR if hasattr(protocol, "TOOL_HOT_AIR") else 1)
    board.handle(*protocol.encode_solder_setpoint(280))
    assert board.advance(1.0) == []


def test_board_with_a_system_error_does_not_heat():
    board = VirtualBoard(tool_id=protocol.TOOL_SOLDERING_IRON, system_error=True)
    board.handle(*protocol.encode_solder_setpoint(280))
    assert board.advance(1.0) == []


def test_server_sends_the_telemetry_in_real_time():
    from test_virtual_board import SERIAL_MODULE   # the same TCP serial stand-in the other server tests use
    from urtc_common import transports
    from urtc_common.virtual_board import VirtualBoardServer
    import time

    fast = {"heat_capacity_j_per_k": 0.05, "telemetry_period_ms": 60}   # a tiny iron so a fraction of a second is enough
    board = VirtualBoard(tool_id=protocol.TOOL_SOLDERING_IRON, heater_config=fast)
    with VirtualBoardServer(board=board) as server:
        port = transports.SLCAN(server.url, serial_module=SERIAL_MODULE, settle_seconds=0)
        try:
            port.open_channel()
            seen = []
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and len(seen) < 3:
                port.send_frame(*protocol.encode_solder_setpoint(150))
                frame = port.read_frame(0.05)
                if frame is not None and frame[0] == protocol.CAN_ID_SOLDER_TELEMETRY:
                    seen.append(int.from_bytes(frame[1], "big"))
        finally:
            port.close()
    assert len(seen) >= 3
    assert seen[-1] >= seen[0]


def test_a_board_in_its_bootloader_does_not_heat():
    board = VirtualBoard(tool_id=protocol.TOOL_SOLDERING_IRON)
    board.handle(*protocol.encode_solder_setpoint(250))
    board.enter_bootloader()
    assert board.heater is None
    assert board.advance(1.0) == []
