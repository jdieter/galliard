#!/usr/bin/env python3

import logging
import gi

from galliard.mpd_snapcast import DEFAULT_CONTROL_PORT as DEFAULT_SNAPCAST_PORT
from galliard.utils.async_task_queue import AsyncUIHelper

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Adw  # noqa: E402


class PreferencesWindow(Adw.PreferencesDialog):
    """Adwaita preferences dialog for MPD / Snapcast / interface settings."""

    def __init__(self, app, config):
        """Build the preferences pages from the current ``config`` state."""
        super().__init__(title="Preferences")

        self.app = app
        self.config = config

        self.set_content_width(500)
        self.set_content_height(700)

        self.create_connection_page()
        self.create_interface_page()

    def create_connection_page(self):
        """Build the Connection page: MPD server + Snapcast integration."""
        page = Adw.PreferencesPage(
            title="Connection",
            icon_name="network-server-symbolic"
        )
        self.add(page)

        mpd_group = Adw.PreferencesGroup(title="MPD Server")
        page.add(mpd_group)

        host_row = Adw.EntryRow(
            title="Host",
            text=self.config.get("mpd.host", "localhost")
        )
        host_row.connect("changed", self.on_host_changed)
        mpd_group.add(host_row)

        port_row = Adw.SpinRow(
            title="Port",
            adjustment=Gtk.Adjustment(
                value=self.config.get("mpd.port", 6600),
                lower=1,
                upper=65535,
                step_increment=1
            ),
            digits=0
        )
        port_row.connect("changed", self.on_port_changed)
        mpd_group.add(port_row)

        password_row = Adw.PasswordEntryRow(
            title="Password",
            text=self.config.get("mpd.password", "")
        )
        password_row.connect("changed", self.on_password_changed)
        mpd_group.add(password_row)

        timeout_row = Adw.SpinRow(
            title="Connection Timeout",
            subtitle="Seconds to wait before timeout",
            adjustment=Gtk.Adjustment(
                value=self.config.get("mpd.timeout", 10),
                lower=1,
                upper=60,
                step_increment=1
            ),
            digits=0
        )
        timeout_row.connect("changed", self.on_timeout_changed)
        mpd_group.add(timeout_row)

        auto_connect_row = Adw.SwitchRow(
            title="Auto-connect on startup",
            active=self.config.get("auto_connect", True)
        )
        auto_connect_row.connect("notify::active", self.on_auto_connect_changed)
        mpd_group.add(auto_connect_row)

        snapcast_group = Adw.PreferencesGroup(title="Snapcast Integration")
        page.add(snapcast_group)

        volume_method_row = Adw.ComboRow(
            title="Volume Control",
            subtitle="Method used to control playback volume",
            model=Gtk.StringList.new(["MPD", "Snapcast"])
        )

        if self.app.mpd_conn.supports_snapcast():
            current_method = self.config.get("volume.method", "mpd").lower()
            if current_method == "snapcast":
                volume_method_row.set_selected(1)
            else:
                volume_method_row.set_selected(0)
        else:
            volume_method_row.set_selected(0)

        volume_method_row.connect("notify::selected", self.on_volume_method_changed)
        snapcast_group.add(volume_method_row)

        snapcast_server_row = Adw.EntryRow(
            title="Snapcast Server",
            text=self.config.get("snapcast.host", "localhost")
        )
        snapcast_server_row.connect("changed", self.on_snapcast_host_changed)
        snapcast_group.add(snapcast_server_row)

        snapcast_port_row = Adw.SpinRow(
            title="Snapcast Port",
            adjustment=Gtk.Adjustment(
                value=self.config.get("snapcast.port", DEFAULT_SNAPCAST_PORT),
                lower=1,
                upper=65535,
                step_increment=1
            ),
            digits=0
        )
        snapcast_port_row.connect("changed", self.on_snapcast_port_changed)
        snapcast_group.add(snapcast_port_row)

        self.client_row = Adw.ComboRow(
            title="Snapcast Client",
            subtitle="Select which client's volume to control",
            model=Gtk.StringList.new([""])
        )

        refresh_button = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_button.set_tooltip_text("Refresh client list")
        refresh_button.set_valign(Gtk.Align.CENTER)
        refresh_button.add_css_class("flat")
        refresh_button.connect("clicked", self.on_refresh_snapcast_clients)
        self.client_row.add_suffix(refresh_button)

        self.update_snapcast_client_list()

        self.client_dropdown_handler_id = self.client_row.connect(
            "notify::selected", self.on_snapcast_client_changed
        )
        snapcast_group.add(self.client_row)

        # Kept as a list so the volume-method toggle can grey them out
        # wholesale when the user picks MPD-native volume.
        self.snapcast_rows = [snapcast_server_row, snapcast_port_row, self.client_row]

        if self.app.mpd_conn.supports_snapcast():
            logging.debug("Snapcast support is available.")
            current_method = self.config.get("volume.method", "mpd").lower()
            is_snapcast = current_method == "snapcast"
            for row in self.snapcast_rows:
                row.set_sensitive(is_snapcast)
        else:
            logging.info("Snapcast support is NOT available. Disabling Snapcast settings.")
            for row in self.snapcast_rows:
                row.set_sensitive(False)

    def create_interface_page(self):
        """Build the Interface page: theme + notification preferences."""
        page = Adw.PreferencesPage(
            title="Interface",
            icon_name="preferences-desktop-appearance-symbolic"
        )
        self.add(page)

        appearance_group = Adw.PreferencesGroup(title="Appearance")
        page.add(appearance_group)

        theme_row = Adw.ComboRow(
            title="Theme",
            model=Gtk.StringList.new(["System", "Light", "Dark"])
        )

        current_theme = self.config.get("ui.theme", "system").lower()
        if current_theme == "light":
            theme_row.set_selected(1)
        elif current_theme == "dark":
            theme_row.set_selected(2)
        else:
            theme_row.set_selected(0)

        theme_row.connect("notify::selected", self.on_theme_changed)
        appearance_group.add(theme_row)

        notification_group = Adw.PreferencesGroup(title="Notifications")
        page.add(notification_group)

        notifications_row = Adw.SwitchRow(
            title="Show notifications",
            subtitle="Display notifications when songs change",
            active=self.config.get("ui.show_notifications", True)
        )
        notifications_row.connect("notify::active", self.on_notifications_changed)
        notification_group.add(notifications_row)

        tray_row = Adw.SwitchRow(
            title="Minimize to system tray",
            subtitle="Keep app running in system tray when closed",
            active=self.config.get("ui.minimize_to_tray", True)
        )
        tray_row.connect("notify::active", self.on_tray_changed)
        notification_group.add(tray_row)

    def on_host_changed(self, entry_row):
        """Persist a new MPD host to config."""
        self.config.set("mpd.host", entry_row.get_text())

    def on_port_changed(self, spin_row):
        """Persist a new MPD port to config."""
        self.config.set("mpd.port", int(spin_row.get_value()))

    def on_password_changed(self, entry_row):
        """Persist a new MPD password to config."""
        self.config.set("mpd.password", entry_row.get_text())

    def on_timeout_changed(self, spin_row):
        """Persist a new MPD connection timeout (seconds) to config."""
        self.config.set("mpd.timeout", int(spin_row.get_value()))

    def on_auto_connect_changed(self, switch_row, pspec):
        """Persist the auto-connect-on-startup toggle to config."""
        self.config.set("auto_connect", switch_row.get_active())

    def on_theme_changed(self, combo_row, pspec):
        """Persist the theme choice and apply it to Adwaita immediately."""
        themes = ["system", "light", "dark"]
        selected = combo_row.get_selected()
        if selected < len(themes):
            self.config.set("ui.theme", themes[selected])

            style_manager = Adw.StyleManager.get_default()
            if themes[selected] == "light":
                style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            elif themes[selected] == "dark":
                style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            else:
                style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

    def on_notifications_changed(self, switch_row, pspec):
        """Persist the show-notifications toggle to config."""
        self.config.set("ui.show_notifications", switch_row.get_active())

    def on_tray_changed(self, switch_row, pspec):
        """Persist the minimize-to-tray toggle to config."""
        self.config.set("ui.minimize_to_tray", switch_row.get_active())

    def update_snapcast_client_list(self):
        """Ask MPDConn.snapcast for the current client list asynchronously."""
        host = self.config.get("snapcast.host", "localhost")
        port = self.config.get("snapcast.port", DEFAULT_SNAPCAST_PORT)

        AsyncUIHelper.run_async_operation(
            self.app.mpd_conn.snapcast.get_clients,
            self._handle_snapcast_client_update,
            host,
            port,
        )

    def _handle_snapcast_client_update(self, result):
        """Repopulate the client combo row from the freshly-fetched list.

        Runs as an AsyncUIHelper callback, which is already dispatched on
        the GLib main loop, so no further idle_add_once wrapping is needed.
        """
        if not result:
            return

        self.client_row.disconnect(self.client_dropdown_handler_id)

        client_names = [
            client["name"] for client in self.app.mpd_conn.snapcast.clients
        ] or ["No clients found"]

        string_list = Gtk.StringList()
        for name in client_names:
            string_list.append(name)
        self.client_row.set_model(string_list)

        selected_client_id = self.config.get("snapcast.client_id", "")
        for i, client in enumerate(self.app.mpd_conn.snapcast.clients):
            if client["id"] == selected_client_id:
                self.client_row.set_selected(i)
                break

        self.client_dropdown_handler_id = self.client_row.connect(
            "notify::selected", self.on_snapcast_client_changed
        )

    def on_refresh_snapcast_clients(self, button):
        """Manual refresh button: re-fetch the Snapcast client list."""
        self.update_snapcast_client_list()

    def on_volume_method_changed(self, combo_row, pspec):
        """Toggle Snapcast volume control: persist choice, enable/disable rows."""
        methods = ["mpd", "snapcast"]
        selected = combo_row.get_selected()
        if selected < len(methods):
            method = methods[selected]
            self.config.set("volume.method", method)

            is_snapcast = method == "snapcast"

            if is_snapcast:
                string_list = Gtk.StringList.new(["Loading..."])
            else:
                string_list = Gtk.StringList.new([""])
            self.client_row.set_model(string_list)

            for row in self.snapcast_rows:
                row.set_sensitive(is_snapcast)

    def on_snapcast_host_changed(self, entry_row):
        """Persist a new Snapcast host to config."""
        self.config.set("snapcast.host", entry_row.get_text())

    def on_snapcast_port_changed(self, spin_row):
        """Persist a new Snapcast port to config."""
        self.config.set("snapcast.port", int(spin_row.get_value()))

    def on_snapcast_client_changed(self, combo_row, pspec):
        """Persist the selected Snapcast client and re-select it on the server."""
        selected_item = combo_row.get_selected_item()
        if selected_item:
            selected = selected_item.get_string()
            for client in self.app.mpd_conn.snapcast.clients:
                if client["name"] == selected:
                    logging.debug(f"Setting Snapcast client ID to: {client['id']}")
                    self.config.set("snapcast.client_id", client["id"])
                    AsyncUIHelper.run_async_operation(
                        self.app.mpd_conn.snapcast.select_client
                    )
                    return
