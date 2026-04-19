"""Verify MPDConn._emit_status_changes hits every signal correctly.

We stand up an MPDConn with a fake client and a recording ``emit``
replacement, then feed successive status snapshots and assert the
right signals fire with the right args.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def recording_mpd_conn(mpd_conn, monkeypatch):
    """MPDConn with ``emit`` recording all invocations + synchronous idle_add."""
    import galliard.mpd_conn as mpd_conn_module

    calls = []

    def record(signal, *args):
        calls.append((signal, args))

    mpd_conn.emit = record

    # idle_add_once defers emission to the GLib main loop; run it inline
    # so assertions see the signal immediately.
    def sync_idle(fn, *args, **kwargs):
        fn(*args, **kwargs)
        return 0

    monkeypatch.setattr(mpd_conn_module, "idle_add_once", sync_idle)

    mpd_conn.recorded = calls
    return mpd_conn


def _signals(conn, name):
    """Return just the ``args`` tuples emitted for ``name``."""
    return [args for signal, args in conn.recorded if signal == name]


class TestScalarFields:
    def test_volume_emits_int(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"volume": "50"})
        assert _signals(recording_mpd_conn, "volume-changed") == [(50,)]

    def test_no_emit_when_unchanged(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"volume": "50"})
        recording_mpd_conn.recorded.clear()
        recording_mpd_conn._emit_status_changes({"volume": "50"})
        assert _signals(recording_mpd_conn, "volume-changed") == []

    def test_emit_on_volume_change(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"volume": "50"})
        recording_mpd_conn._emit_status_changes({"volume": "60"})
        assert _signals(recording_mpd_conn, "volume-changed") == [(50,), (60,)]

    def test_state_emits_string(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"state": "play"})
        assert _signals(recording_mpd_conn, "playback-status-changed") == [("play",)]

    def test_random_coerces_zero_one_to_bool(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"random": "1"})
        assert _signals(recording_mpd_conn, "random-changed") == [(True,)]
        recording_mpd_conn._emit_status_changes({"random": "0"})
        assert _signals(recording_mpd_conn, "random-changed")[-1] == (False,)

    def test_consume_coerces(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"consume": "1"})
        assert _signals(recording_mpd_conn, "consume-changed") == [(True,)]

    def test_bitrate_emits_int(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"bitrate": "320"})
        assert _signals(recording_mpd_conn, "bitrate-changed") == [(320,)]

    def test_coerce_failure_swallowed(self, recording_mpd_conn):
        # ``int("nope")`` raises; no volume-changed should fire.
        recording_mpd_conn._emit_status_changes({"volume": "nope"})
        assert _signals(recording_mpd_conn, "volume-changed") == []


class TestElapsed:
    def test_first_time_emits(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"elapsed": "12.3"})
        assert _signals(recording_mpd_conn, "elapsed-changed") == [(12.3,)]

    def test_small_change_suppressed(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"elapsed": "10.0"})
        recording_mpd_conn.recorded.clear()
        recording_mpd_conn._emit_status_changes({"elapsed": "10.4"})
        assert _signals(recording_mpd_conn, "elapsed-changed") == []

    def test_big_change_emits(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"elapsed": "10.0"})
        recording_mpd_conn.recorded.clear()
        recording_mpd_conn._emit_status_changes({"elapsed": "10.6"})
        assert _signals(recording_mpd_conn, "elapsed-changed") == [(10.6,)]


class TestRepeatSingle:
    def test_repeat_change_emits_composite(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"repeat": "1", "single": "0"})
        assert _signals(recording_mpd_conn, "repeat-changed") == [(True, False)]

    def test_single_change_also_fires_composite(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"repeat": "1", "single": "0"})
        recording_mpd_conn.recorded.clear()
        recording_mpd_conn._emit_status_changes({"repeat": "1", "single": "1"})
        assert _signals(recording_mpd_conn, "repeat-changed") == [(True, True)]

    def test_neither_changed_no_emit(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"repeat": "1", "single": "0"})
        recording_mpd_conn.recorded.clear()
        recording_mpd_conn._emit_status_changes({"repeat": "1", "single": "0"})
        assert _signals(recording_mpd_conn, "repeat-changed") == []


class TestAudio:
    def test_audio_format_parses(self, recording_mpd_conn):
        recording_mpd_conn._emit_status_changes({"audio": "44100:16:2"})
        assert _signals(recording_mpd_conn, "audio-changed") == [
            ("44100:16:2", 44100, 16)
        ]

    def test_garbled_audio_is_ignored(self, recording_mpd_conn):
        # int("not-a-number") raises -> signal suppressed, no crash.
        recording_mpd_conn._emit_status_changes({"audio": "garbage"})
        assert _signals(recording_mpd_conn, "audio-changed") == []

    def test_two_part_audio_still_emits(self, recording_mpd_conn):
        # Only rate + bits are required; channels missing is tolerated.
        recording_mpd_conn._emit_status_changes({"audio": "48000:24"})
        assert _signals(recording_mpd_conn, "audio-changed") == [
            ("48000:24", 48000, 24)
        ]


def test_prev_status_is_updated(recording_mpd_conn):
    """After processing, ``prev_status`` mirrors the snapshot."""
    snapshot = {"volume": "50", "state": "play"}
    recording_mpd_conn._emit_status_changes(snapshot)
    assert recording_mpd_conn.prev_status == snapshot
