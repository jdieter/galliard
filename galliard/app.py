#!/usr/bin/env python3

import logging
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gio  # noqa: E402
from galliard.mpd_conn import MPDConn  # noqa: E402
from galliard.config import Config  # noqa: E402
from galliard.preferences import PreferencesWindow  # noqa: E402
from galliard.window import MainWindow  # noqa: E402
from galliard.notifications import NotificationManager  # noqa: E402

logging.basicConfig(level=logging.DEBUG)

# System tray and media-keys bindings are both optional; the app runs
# without either if the system libraries aren't available.
try:
    from galliard.system_tray import (
        SystemTrayIcon,
        APPINDICATOR_AVAILABLE,
    )  # noqa: E402
except ImportError:
    SystemTrayIcon = None
    APPINDICATOR_AVAILABLE = False

try:
    from galliard.media_keys import MediaKeysManager, MEDIA_KEYS_AVAILABLE  # noqa: E402
except ImportError:
    MediaKeysManager = None
    MEDIA_KEYS_AVAILABLE = False


class Galliard(Adw.Application):
    """Top-level Adw.Application for the Galliard MPD client."""

    def __init__(self):
        """Construct the application, load config, and wire up signals."""
        super().__init__(
            application_id="net.jdieter.galliard", flags=Gio.ApplicationFlags.FLAGS_NONE
        )

        self.config = Config()
        self.config.load()

        self.mpd_conn = MPDConn(self.config)

        self.notification_manager = None
        self.system_tray_icon = None
        self.media_keys_manager = None

        self.connect("activate", self.on_activate)
        self.connect("shutdown", self.on_shutdown)

        self.create_actions()

    def create_actions(self):
        """Register app-level Gio actions and their keyboard accelerators."""
        actions = [
            ("quit", self.on_quit),
            ("preferences", self.on_preferences),
            ("about", self.on_about),
            ("connect", self.on_connect),
            ("disconnect", self.on_disconnect),
        ]

        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        self.set_accels_for_action("app.quit", ["<primary>q"])
        self.set_accels_for_action("app.preferences", ["<primary>comma"])

    def on_activate(self, app):
        """Initialise singleton services, present the window, and auto-connect."""
        if not self.notification_manager:
            self.notification_manager = NotificationManager(
                self, self.config, self.mpd_conn
            )

        # Only build the tray icon when there's actually a backend for it --
        # otherwise on_close_request would minimise to an invisible tray.
        if (
            SystemTrayIcon
            and APPINDICATOR_AVAILABLE
            and not self.system_tray_icon
            and self.config.get("ui.minimize_to_tray", True)
        ):
            self.system_tray_icon = SystemTrayIcon(self, self.config, self.mpd_conn)

        if MediaKeysManager and not self.media_keys_manager:
            self.media_keys_manager = MediaKeysManager(self, self.mpd_conn)

        window = self.props.active_window
        if window is None:
            window = MainWindow(application=self, mpd_conn=self.mpd_conn)
        window.present()

        if self.config.get("auto_connect", True):
            self.mpd_conn.connect_to_server()

    def on_shutdown(self, app):
        """Tear down MPD connection and release external integrations."""
        if self.mpd_conn.is_connected():
            self.disconnect_mpd()

        if self.notification_manager:
            self.notification_manager.cleanup()
        if self.system_tray_icon:
            self.system_tray_icon.cleanup()
        if self.media_keys_manager:
            self.media_keys_manager.release()

    def do_activate(self):
        """No-op; activation is handled via the ``activate`` signal."""
        pass

    def on_quit(self, action, param):
        """Quit the application."""
        self.quit()

    def on_preferences(self, action, param):
        """Open the preferences window."""
        prefs = PreferencesWindow(self, self.config)
        prefs.present()

    def on_about(self, action, param):
        """Open the about dialog."""
        about = Adw.AboutWindow(
            transient_for=self.props.active_window,
            application_name="Galliard",
            application_icon="net.jdieter.galliard",
            developer_name="Jonathan Dieter",
            version="0.1.0",
            developers=["Jonathan Dieter <jonathan@dieter.ie>"],
            copyright="© 2025 Jonathan Dieter",
            license_type=Gtk.License.MIT_X11,
            website="https://github.com/jdieter/galliard",
            issue_url="https://github.com/jdieter/galliard/issues",
        )
        about.present()

    def on_connect(self, action, param):
        """Action handler: connect to the configured MPD server."""
        self.mpd_conn.connect_to_server()

    def on_disconnect(self, action, param):
        """Action handler: disconnect from the MPD server."""
        self.disconnect_mpd()

    def disconnect_mpd(self):
        """Disconnect from the MPD server."""
        self.mpd_conn.disconnect_from_server()
