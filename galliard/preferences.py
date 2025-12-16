#!/usr/bin/env python3

import logging
import gi

from galliard.widgets.async_ui_helper import AsyncUIHelper

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Adw  # noqa: E402


class PreferencesWindow(Adw.PreferencesWindow):
    """Preferences window for Galliard"""

    def __init__(self, app, config):
        super().__init__(title="Preferences")

        self.app = app
        self.config = config

        # Set up window
        self.set_default_size(500, 700)
        self.set_modal(True)
        self.set_transient_for(app.props.active_window)

        # Create pages
        self.create_connection_page()
        self.create_interface_page()

    def create_connection_page(self):
        """Create MPD connection settings page"""
        # Create page
        page = Adw.PreferencesPage(
            title="Connection",
            icon_name="network-server-symbolic"
        )
        self.add(page)

        # MPD Server Group
        mpd_group = Adw.PreferencesGroup(title="MPD Server")
        page.add(mpd_group)

        # Host entry
        host_row = Adw.EntryRow(
            title="Host",
            text=self.config.get("mpd.host", "localhost")
        )
        host_row.connect("changed", self.on_host_changed)
        mpd_group.add(host_row)

        # Port entry
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

        # Password entry
        password_row = Adw.PasswordEntryRow(
            title="Password",
            text=self.config.get("mpd.password", "")
        )
        password_row.connect("changed", self.on_password_changed)
        mpd_group.add(password_row)

        # Connection timeout
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

        # Auto-connect
        auto_connect_row = Adw.SwitchRow(
            title="Auto-connect on startup",
            active=self.config.get("auto_connect", True)
        )
        auto_connect_row.connect("notify::active", self.on_auto_connect_changed)
        mpd_group.add(auto_connect_row)

        # Snapcast Group
        snapcast_group = Adw.PreferencesGroup(title="Snapcast Integration")
        page.add(snapcast_group)

        # Volume control method
        volume_method_row = Adw.ComboRow(
            title="Volume Control",
            subtitle="Method used to control playback volume",
            model=Gtk.StringList.new(["MPD", "Snapcast"])
        )

        if self.app.mpd_client.supports_snapcast():
            current_method = self.config.get("volume.method", "mpd").lower()
            if current_method == "snapcast":
                volume_method_row.set_selected(1)
            else:  # mpd
                volume_method_row.set_selected(0)
        else:
            volume_method_row.set_selected(0)

        volume_method_row.connect("notify::selected", self.on_volume_method_changed)
        snapcast_group.add(volume_method_row)

        # Snapcast server settings
        snapcast_server_row = Adw.EntryRow(
            title="Snapcast Server",
            text=self.config.get("snapcast.host", "localhost")
        )
        snapcast_server_row.connect("changed", self.on_snapcast_host_changed)
        snapcast_group.add(snapcast_server_row)

        # Snapcast port
        snapcast_port_row = Adw.SpinRow(
            title="Snapcast Port",
            adjustment=Gtk.Adjustment(
                value=self.config.get("snapcast.port", 1780),
                lower=1,
                upper=65535,
                step_increment=1
            ),
            digits=0
        )
        snapcast_port_row.connect("changed", self.on_snapcast_port_changed)
        snapcast_group.add(snapcast_port_row)

        # Snapcast client selection
        self.client_row = Adw.ComboRow(
            title="Snapcast Client",
            subtitle="Select which client's volume to control",
            model=Gtk.StringList.new([""])
        )

        # Add refresh button to the client row
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

        # Store references to Snapcast-specific rows for sensitivity control
        self.snapcast_rows = [snapcast_server_row, snapcast_port_row, self.client_row]

        if self.app.mpd_client.supports_snapcast():
            logging.debug("Snapcast support is available.")
            # Set sensitivity of Snapcast controls based on current method
            current_method = self.config.get("volume.method", "mpd").lower()
            is_snapcast = current_method == "snapcast"
            for row in self.snapcast_rows:
                row.set_sensitive(is_snapcast)
        else:
            logging.info("Snapcast support is NOT available. Disabling Snapcast settings.")
            for row in self.snapcast_rows:
                row.set_sensitive(False)

    def create_interface_page(self):
        """Create interface settings page"""
        # Create page
        page = Adw.PreferencesPage(
            title="Interface",
            icon_name="preferences-desktop-appearance-symbolic"
        )
        self.add(page)

        # Appearance Group
        appearance_group = Adw.PreferencesGroup(title="Appearance")
        page.add(appearance_group)

        # Theme
        theme_row = Adw.ComboRow(
            title="Theme",
            model=Gtk.StringList.new(["System", "Light", "Dark"])
        )

        current_theme = self.config.get("ui.theme", "system").lower()
        if current_theme == "light":
            theme_row.set_selected(1)
        elif current_theme == "dark":
            theme_row.set_selected(2)
        else:  # system
            theme_row.set_selected(0)

        theme_row.connect("notify::selected", self.on_theme_changed)
        appearance_group.add(theme_row)

        # Notification Group
        notification_group = Adw.PreferencesGroup(title="Notifications")
        page.add(notification_group)

        # Show notifications
        notifications_row = Adw.SwitchRow(
            title="Show notifications",
            subtitle="Display notifications when songs change",
            active=self.config.get("ui.show_notifications", True)
        )
        notifications_row.connect("notify::active", self.on_notifications_changed)
        notification_group.add(notifications_row)

        # Minimize to tray
        tray_row = Adw.SwitchRow(
            title="Minimize to system tray",
            subtitle="Keep app running in system tray when closed",
            active=self.config.get("ui.minimize_to_tray", True)
        )
        tray_row.connect("notify::active", self.on_tray_changed)
        notification_group.add(tray_row)

    # Connection settings handlers

    def on_host_changed(self, entry_row):
        """Handle host change"""
        self.config.set("mpd.host", entry_row.get_text())

    def on_port_changed(self, spin_row):
        """Handle port change"""
        self.config.set("mpd.port", int(spin_row.get_value()))

    def on_password_changed(self, entry_row):
        """Handle password change"""
        self.config.set("mpd.password", entry_row.get_text())

    def on_timeout_changed(self, spin_row):
        """Handle timeout change"""
        self.config.set("mpd.timeout", int(spin_row.get_value()))

    def on_auto_connect_changed(self, switch_row, pspec):
        """Handle auto-connect change"""
        self.config.set("auto_connect", switch_row.get_active())

    # Interface settings handlers

    def on_theme_changed(self, combo_row, pspec):
        """Handle theme change"""
        themes = ["system", "light", "dark"]
        selected = combo_row.get_selected()
        if selected < len(themes):
            self.config.set("ui.theme", themes[selected])

            # Apply theme using Adwaita StyleManager
            style_manager = Adw.StyleManager.get_default()
            if themes[selected] == "light":
                style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            elif themes[selected] == "dark":
                style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            else:  # system
                style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

    def on_notifications_changed(self, switch_row, pspec):
        """Handle notifications change"""
        self.config.set("ui.show_notifications", switch_row.get_active())

    def on_tray_changed(self, switch_row, pspec):
        """Handle tray change"""
        self.config.set("ui.minimize_to_tray", switch_row.get_active())

    def update_snapcast_client_list(self):
        """Update the list of available Snapcast clients"""
        # This function will request client list from MPDConn
        host = self.config.get("snapcast.host", "localhost")
        port = self.config.get("snapcast.port", 1705)

        AsyncUIHelper.run_async_operation(
            self.app.mpd_client.async_get_snapcast_clients,
            self._handle_snapcast_client_update,
            host,
            port,
        )

    def _handle_snapcast_client_update(self, result):
        """Handle the updated list of Snapcast clients"""
        if not result:
            return

        # Use GLib.idle_add to ensure thread safety when updating UI
        def update_client_dropdown():
            self.client_row.disconnect(self.client_dropdown_handler_id)

            # Update combo row with new client list
            client_names = [
                client["name"] for client in self.app.mpd_client.snapcast_clients
            ] or ["No clients found"]

            # Create a new string list model
            string_list = Gtk.StringList()
            for name in client_names:
                string_list.append(name)
            self.client_row.set_model(string_list)

            # Set selected client if it exists
            selected_client_id = self.config.get("snapcast.client_id", "")
            for i, client in enumerate(self.app.mpd_client.snapcast_clients):
                if client["id"] == selected_client_id:
                    self.client_row.set_selected(i)
                    break

            self.client_dropdown_handler_id = self.client_row.connect(
                "notify::selected", self.on_snapcast_client_changed
            )
            return

        GLib.idle_add(update_client_dropdown)

    def on_refresh_snapcast_clients(self, button):
        """Handle refresh button click for Snapcast clients"""
        self.update_snapcast_client_list()

    def on_volume_method_changed(self, combo_row, pspec):
        """Handle volume control method change"""
        methods = ["mpd", "snapcast"]
        selected = combo_row.get_selected()
        if selected < len(methods):
            method = methods[selected]
            self.config.set("volume.method", method)

            # Enable/disable Snapcast settings based on selection
            is_snapcast = method == "snapcast"

            # Update client model
            if is_snapcast:
                string_list = Gtk.StringList.new(["Loading..."])
            else:
                string_list = Gtk.StringList.new([""])
            self.client_row.set_model(string_list)

            # Enable/disable all Snapcast-specific settings
            for row in self.snapcast_rows:
                row.set_sensitive(is_snapcast)

    def on_snapcast_host_changed(self, entry_row):
        """Handle Snapcast host change"""
        self.config.set("snapcast.host", entry_row.get_text())

    def on_snapcast_port_changed(self, spin_row):
        """Handle Snapcast port change"""
        self.config.set("snapcast.port", int(spin_row.get_value()))

    def on_snapcast_client_changed(self, combo_row, pspec):
        """Handle Snapcast client selection change"""
        selected_item = combo_row.get_selected_item()
        if selected_item:
            selected = selected_item.get_string()
            for client in self.app.mpd_client.snapcast_clients:
                if client["name"] == selected:
                    logging.debug(f"Setting Snapcast client ID to: {client['id']}")
                    self.config.set("snapcast.client_id", client["id"])
                    AsyncUIHelper.run_async_operation(
                        self.app.mpd_client._select_snapcast_client
                    )
                    return
