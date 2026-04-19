"""PreferencesWindow construction + handler side-effects on Config."""

from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.gtk


@pytest.fixture(autouse=True)
def _no_async_dispatch(monkeypatch):
    """Prevent the preferences window from queueing Snapcast fetches."""
    from galliard.utils.async_task_queue import AsyncUIHelper

    monkeypatch.setattr(
        AsyncUIHelper, "run_async_operation",
        staticmethod(lambda *a, **kw: None),
    )


@pytest.fixture
def prefs(gtk_app):
    """Instantiate the PreferencesWindow bound to the session app."""
    from galliard.preferences import PreferencesWindow

    return PreferencesWindow(gtk_app, gtk_app.mpd_conn.config)


def _make_notify_pspec(name: str):
    """A dummy pspec argument accepted by the ``notify::`` handlers."""
    return MagicMock(name=f"pspec<{name}>")


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_window_title(self, prefs):
        assert prefs.get_title() == "Preferences"

    def test_client_row_present_after_construction(self, prefs):
        assert prefs.client_row is not None

    def test_snapcast_rows_collected(self, prefs):
        # Three rows managed as a group for sensitivity toggling.
        assert len(prefs.snapcast_rows) == 3


# ---------------------------------------------------------------------------
# MPD server row handlers
# ---------------------------------------------------------------------------

class TestConnectionHandlers:
    def test_host_change_persists(self, prefs, gtk_app):
        entry = MagicMock()
        entry.get_text.return_value = "mpd.example.com"
        prefs.on_host_changed(entry)
        assert gtk_app.mpd_conn.config.get("mpd.host") == "mpd.example.com"

    def test_port_change_persists(self, prefs, gtk_app):
        spin = MagicMock()
        spin.get_value.return_value = 6601.0
        prefs.on_port_changed(spin)
        assert gtk_app.mpd_conn.config.get("mpd.port") == 6601

    def test_password_change_persists(self, prefs, gtk_app):
        entry = MagicMock()
        entry.get_text.return_value = "secret"
        prefs.on_password_changed(entry)
        assert gtk_app.mpd_conn.config.get("mpd.password") == "secret"

    def test_timeout_change_persists(self, prefs, gtk_app):
        spin = MagicMock()
        spin.get_value.return_value = 15.0
        prefs.on_timeout_changed(spin)
        assert gtk_app.mpd_conn.config.get("mpd.timeout") == 15

    def test_auto_connect_toggle_persists(self, prefs, gtk_app):
        switch = MagicMock()
        switch.get_active.return_value = False
        prefs.on_auto_connect_changed(switch, _make_notify_pspec("active"))
        assert gtk_app.mpd_conn.config.get("auto_connect") is False


# ---------------------------------------------------------------------------
# Interface-page handlers
# ---------------------------------------------------------------------------

class TestInterfaceHandlers:
    def test_theme_changed_dark(self, prefs, gtk_app):
        combo = MagicMock()
        combo.get_selected.return_value = 2  # "Dark"
        prefs.on_theme_changed(combo, _make_notify_pspec("selected"))
        assert gtk_app.mpd_conn.config.get("ui.theme") == "dark"

    def test_theme_changed_light(self, prefs, gtk_app):
        combo = MagicMock()
        combo.get_selected.return_value = 1  # "Light"
        prefs.on_theme_changed(combo, _make_notify_pspec("selected"))
        assert gtk_app.mpd_conn.config.get("ui.theme") == "light"

    def test_theme_changed_system(self, prefs, gtk_app):
        combo = MagicMock()
        combo.get_selected.return_value = 0  # "System"
        prefs.on_theme_changed(combo, _make_notify_pspec("selected"))
        assert gtk_app.mpd_conn.config.get("ui.theme") == "system"

    def test_theme_out_of_range_is_ignored(self, prefs, gtk_app):
        """Selecting beyond the theme list leaves config untouched."""
        gtk_app.mpd_conn.config.set("ui.theme", "system")
        combo = MagicMock()
        combo.get_selected.return_value = 99
        prefs.on_theme_changed(combo, _make_notify_pspec("selected"))
        assert gtk_app.mpd_conn.config.get("ui.theme") == "system"

    def test_notifications_toggle_persists(self, prefs, gtk_app):
        switch = MagicMock()
        switch.get_active.return_value = False
        prefs.on_notifications_changed(switch, _make_notify_pspec("active"))
        assert gtk_app.mpd_conn.config.get("ui.show_notifications") is False

    def test_tray_toggle_persists(self, prefs, gtk_app):
        switch = MagicMock()
        switch.get_active.return_value = False
        prefs.on_tray_changed(switch, _make_notify_pspec("active"))
        assert gtk_app.mpd_conn.config.get("ui.minimize_to_tray") is False


# ---------------------------------------------------------------------------
# Snapcast handlers
# ---------------------------------------------------------------------------

class TestSnapcastHandlers:
    def test_volume_method_snapcast_toggles_row_sensitivity(self, prefs):
        combo = MagicMock()
        combo.get_selected.return_value = 1  # "Snapcast"
        prefs.on_volume_method_changed(combo, _make_notify_pspec("selected"))
        for row in prefs.snapcast_rows:
            assert row.get_sensitive() is True

    def test_volume_method_mpd_disables_snapcast_rows(self, prefs):
        # First flip on so the assertion below is testing a change.
        for row in prefs.snapcast_rows:
            row.set_sensitive(True)
        combo = MagicMock()
        combo.get_selected.return_value = 0  # "MPD"
        prefs.on_volume_method_changed(combo, _make_notify_pspec("selected"))
        for row in prefs.snapcast_rows:
            assert row.get_sensitive() is False

    def test_volume_method_persists_choice(self, prefs, gtk_app):
        combo = MagicMock()
        combo.get_selected.return_value = 1
        prefs.on_volume_method_changed(combo, _make_notify_pspec("selected"))
        assert gtk_app.mpd_conn.config.get("volume.method") == "snapcast"

    def test_snapcast_host_persists(self, prefs, gtk_app):
        entry = MagicMock()
        entry.get_text.return_value = "snap.example.com"
        prefs.on_snapcast_host_changed(entry)
        assert gtk_app.mpd_conn.config.get("snapcast.host") == "snap.example.com"

    def test_snapcast_port_persists(self, prefs, gtk_app):
        spin = MagicMock()
        spin.get_value.return_value = 1705.0
        prefs.on_snapcast_port_changed(spin)
        assert gtk_app.mpd_conn.config.get("snapcast.port") == 1705

    def test_snapcast_client_changed_persists_id(
        self, prefs, gtk_app, monkeypatch
    ):
        gtk_app.mpd_conn.snapcast.clients = [
            {"id": "client-a", "name": "Living Room", "connected": True, "volume": 50},
            {"id": "client-b", "name": "Kitchen", "connected": True, "volume": 30},
        ]
        combo = MagicMock()
        selected_item = MagicMock()
        selected_item.get_string.return_value = "Kitchen"
        combo.get_selected_item.return_value = selected_item

        prefs.on_snapcast_client_changed(combo, _make_notify_pspec("selected"))
        assert gtk_app.mpd_conn.config.get("snapcast.client_id") == "client-b"

    def test_snapcast_client_changed_noop_when_nothing_selected(
        self, prefs, gtk_app
    ):
        gtk_app.mpd_conn.config.set("snapcast.client_id", "existing")
        combo = MagicMock()
        combo.get_selected_item.return_value = None
        prefs.on_snapcast_client_changed(combo, _make_notify_pspec("selected"))
        assert gtk_app.mpd_conn.config.get("snapcast.client_id") == "existing"


# ---------------------------------------------------------------------------
# Snapcast client-list refresh
# ---------------------------------------------------------------------------

class TestSnapcastClientRefresh:
    def test_empty_result_skips_update(self, prefs, gtk_app):
        """An empty result from get_clients leaves the combo untouched."""
        original_model = prefs.client_row.get_model()
        prefs._handle_snapcast_client_update(None)
        assert prefs.client_row.get_model() is original_model

    def test_populates_model_from_snapcast_clients(self, prefs, gtk_app):
        gtk_app.mpd_conn.snapcast.clients = [
            {"id": "client-a", "name": "Living Room", "connected": True, "volume": 50},
            {"id": "client-b", "name": "Kitchen", "connected": True, "volume": 30},
        ]
        prefs._handle_snapcast_client_update(True)

        model = prefs.client_row.get_model()
        names = [model.get_string(i) for i in range(model.get_n_items())]
        assert names == ["Living Room", "Kitchen"]

    def test_empty_clients_fallback_label(self, prefs, gtk_app):
        gtk_app.mpd_conn.snapcast.clients = []
        prefs._handle_snapcast_client_update(True)
        model = prefs.client_row.get_model()
        names = [model.get_string(i) for i in range(model.get_n_items())]
        assert names == ["No clients found"]

    def test_preselects_configured_client(self, prefs, gtk_app):
        gtk_app.mpd_conn.config.set("snapcast.client_id", "client-b")
        gtk_app.mpd_conn.snapcast.clients = [
            {"id": "client-a", "name": "Living Room", "connected": True, "volume": 50},
            {"id": "client-b", "name": "Kitchen", "connected": True, "volume": 30},
        ]
        prefs._handle_snapcast_client_update(True)
        assert prefs.client_row.get_selected() == 1

    def test_refresh_button_triggers_update_no_crash(self, prefs):
        """The refresh-clients button routes through the async helper (stubbed)."""
        prefs.on_refresh_snapcast_clients(MagicMock())
        # Stubbed AsyncUIHelper means no actual IO; success is no exception.
