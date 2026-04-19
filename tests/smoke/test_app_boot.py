"""End-to-end Gtk smoke: can the app + main window be constructed?

Nothing is realised or presented -- we just build the widget tree and
poke a couple of MPDConn signal handlers to confirm nothing raises.
Skips when Gtk4 / libadwaita aren't available via the ``gtk`` marker.
"""

import pytest


pytestmark = pytest.mark.gtk


async def test_app_and_window_construct(gtk_app):
    """Instantiate MainWindow with the fake MPD backend and read its widgets."""
    from galliard.window import MainWindow

    window = MainWindow(application=gtk_app, mpd_conn=gtk_app.mpd_conn)
    assert window.get_title() == "Galliard"
    assert window.header_bar is not None
    assert window.player_controls is not None
    assert window.content_navigation is not None
    # Four top-level pages: library / playlists / now_playing / search.
    assert set(window.pages.keys()) == {
        "library",
        "playlists",
        "now_playing",
        "search",
    }


async def test_connected_signal_updates_header_status(gtk_app):
    """Emitting ``connected`` flips the header-bar subtitle to "Connected"."""
    from galliard.window import MainWindow

    window = MainWindow(application=gtk_app, mpd_conn=gtk_app.mpd_conn)
    gtk_app.mpd_conn.emit("connected")
    # The header bar's status is updated synchronously through the
    # signal chain.
    assert "Connected" in window.header_bar.current_subtitle


async def test_song_changed_signal_updates_header_subtitle(gtk_app):
    """After a song-changed emission the header subtitle shows title - artist."""
    from galliard.models import Song
    from galliard.window import MainWindow

    window = MainWindow(application=gtk_app, mpd_conn=gtk_app.mpd_conn)

    gtk_app.mpd_conn.connected = True
    gtk_app.mpd_conn.current_song = Song(
        title="Clocks", artist="Coldplay", file="a.mp3"
    )
    gtk_app.mpd_conn.emit("song-changed")
    assert window.header_bar.current_subtitle == "Clocks - Coldplay"
