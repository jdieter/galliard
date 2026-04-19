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

# Try to import system tray support
try:
    from galliard.system_tray import (
        SystemTrayIcon,
        APPINDICATOR_AVAILABLE,
    )  # noqa: E402
except ImportError:
    SystemTrayIcon = None
    APPINDICATOR_AVAILABLE = False

# Try to import media keys support
try:
    from galliard.media_keys import MediaKeysManager, MEDIA_KEYS_AVAILABLE  # noqa: E402
except ImportError:
    MediaKeysManager = None
    MEDIA_KEYS_AVAILABLE = False


class Galliard(Adw.Application):
    """Main application class for Galliard"""

    def __init__(self):
        super().__init__(
            application_id="net.jdieter.galliard", flags=Gio.ApplicationFlags.FLAGS_NONE
        )

        # Load configuration
        self.config = Config()
        self.config.load()

        # Initialize MPD client
        self.mpd_conn = MPDConn(self.config)

        # Initialize notification manager, system tray icon and media keys
        self.notification_manager = None
        self.system_tray_icon = None
        self.media_keys_manager = None

        # Connect signals
        self.connect("activate", self.on_activate)
        self.connect("shutdown", self.on_shutdown)

        # Set up actions
        self.create_actions()

    def create_actions(self):
        """Create application actions"""
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

        # Add keyboard shortcuts
        self.set_accels_for_action("app.quit", ["<primary>q"])
        self.set_accels_for_action("app.preferences", ["<primary>comma"])

    def on_activate(self, app):
        """Handle application activation"""
        # Initialize notification manager and system tray
        if not self.notification_manager:
            self.notification_manager = NotificationManager(
                self, self.config, self.mpd_conn
            )

        if (
            SystemTrayIcon
            and APPINDICATOR_AVAILABLE
            and not self.system_tray_icon
            and self.config.get("ui.minimize_to_tray", True)
        ):
            self.system_tray_icon = SystemTrayIcon(self, self.config, self.mpd_conn)

        # Initialize media keys support
        if MediaKeysManager and not self.media_keys_manager:
            self.media_keys_manager = MediaKeysManager(self, self.mpd_conn)

        # Get the active window or create one if necessary
        window = self.props.active_window
        if window is None:
            window = MainWindow(application=self, mpd_conn=self.mpd_conn)

        # Present the window to the user
        window.present()

        # Auto-connect to MPD server if configured
        if self.config.get("auto_connect", True):
            self.mpd_conn.connect_to_server()

    def on_shutdown(self, app):
        """Handle application shutdown"""
        # Disconnect from MPD
        if self.mpd_conn.is_connected():
            self.disconnect_mpd()

        # Clean up notification manager
        if self.notification_manager:
            self.notification_manager.cleanup()

        # Clean up system tray icon
        if self.system_tray_icon:
            self.system_tray_icon.cleanup()

        # Clean up media keys
        if self.media_keys_manager:
            self.media_keys_manager.release()

    def do_activate(self):
        """Default activation handler (called before on_activate)"""
        pass  # We use the on_activate handler instead

    def on_quit(self, action, param):
        """Quit the application"""
        self.quit()

    def on_preferences(self, action, param):
        """Show preferences dialog"""
        prefs = PreferencesWindow(self, self.config)
        prefs.present()

    def on_about(self, action, param):
        """Show about dialog"""
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
        """Connect to MPD server"""
        self.mpd_conn.connect_to_server()

    def on_disconnect(self, action, param):
        """Disconnect from MPD server"""
        self.disconnect_mpd()

    def disconnect_mpd(self):
        """Safely disconnect from MPD server with proper asyncio handling"""
        self.mpd_conn.disconnect_from_server()
