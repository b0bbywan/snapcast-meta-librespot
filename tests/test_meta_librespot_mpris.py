import pytest

pytest.importorskip("dbus_fast")

from test_meta_librespot import TRACK_EVENT  # noqa: E402

import meta_librespot_mpris  # noqa: E402
from meta_librespot import Player  # noqa: E402
from meta_librespot_mpris import NO_TRACK, PlayerInterface, mpris_metadata, track_path  # noqa: E402


def plain(metadata: dict) -> dict:
    return {k: (v.signature, v.value) for k, v in metadata.items()}


# --- metadata mapping --------------------------------------------------
def test_no_track_metadata():
    assert plain(mpris_metadata(None)) == {"mpris:trackid": ("o", NO_TRACK)}


def test_track_metadata_mapping():
    player = Player()
    player.handle_event(TRACK_EVENT)
    assert plain(mpris_metadata(player.properties["metadata"])) == {
        "mpris:trackid": ("o", "/org/mpris/MediaPlayer2/Track/spotify_track_abc"),
        "mpris:length": ("x", 232_500_000),
        "mpris:artUrl": ("s", "https://i.example/640"),
        "xesam:title": ("s", "Le tourbillon"),
        "xesam:url": ("s", "spotify:track:abc"),
        "xesam:artist": ("as", ["Artist A", "Artist B"]),
        "xesam:album": ("s", "Some Album"),
        "xesam:albumArtist": ("as", ["Artist A"]),
        "xesam:trackNumber": ("i", 3),
        "xesam:discNumber": ("i", 1),
    }


def test_track_path_is_a_valid_object_path():
    assert track_path("spotify:episode:a-b.c") == "/org/mpris/MediaPlayer2/Track/spotify_episode_a_b_c"


# --- PlayerInterface ---------------------------------------------------
@pytest.fixture
def view(monkeypatch):
    player = Player()
    view = PlayerInterface(player)
    view.changes = []
    view.seeks = []
    monkeypatch.setattr(view, "emit_properties_changed", view.changes.append)
    monkeypatch.setattr(view, "Seeked", view.seeks.append)
    view.player = player
    return view


def feed(view, event: dict) -> None:
    view.player.handle_event(event)
    view.sync(event["PLAYER_EVENT"])


def test_sync_emits_only_what_changed(view):
    feed(view, TRACK_EVENT)
    feed(view, {"PLAYER_EVENT": "playing", "POSITION_MS": "0"})
    feed(view, {"PLAYER_EVENT": "volume_changed", "VOLUME": "32768"})
    assert [sorted(c) for c in view.changes] == [["Metadata"], ["PlaybackStatus"], ["Volume"]]
    assert view.changes[1] == {"PlaybackStatus": "Playing"}
    assert view.changes[2] == {"Volume": 0.5}


def test_preload_emits_nothing(view):
    feed(view, TRACK_EVENT)
    view.changes.clear()
    feed(view, {"PLAYER_EVENT": "preloading", "TRACK_ID": "next"})
    assert view.changes == []


def test_seek_emits_seeked_not_properties_changed(view):
    feed(view, {"PLAYER_EVENT": "paused", "POSITION_MS": "1000"})
    view.changes.clear()
    feed(view, {"PLAYER_EVENT": "seeked", "POSITION_MS": "60000"})
    assert view.changes == []
    assert view.seeks == [60_000_000]


def test_position_runs_only_while_playing(view, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(meta_librespot_mpris.time, "monotonic", lambda: now[0])
    feed(view, TRACK_EVENT)
    feed(view, {"PLAYER_EVENT": "playing", "POSITION_MS": "10000"})
    now[0] += 5
    assert view._position_us() == 15_000_000
    feed(view, {"PLAYER_EVENT": "paused", "POSITION_MS": "15000"})
    now[0] += 60
    assert view._position_us() == 15_000_000


def test_position_is_capped_at_track_duration(view, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(meta_librespot_mpris.time, "monotonic", lambda: now[0])
    feed(view, TRACK_EVENT)
    feed(view, {"PLAYER_EVENT": "playing", "POSITION_MS": "230000"})
    now[0] += 3600
    assert view._position_us() == 232_500_000
