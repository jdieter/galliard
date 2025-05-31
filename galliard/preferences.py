#!/usr/bin/env python3

import gi

from galliard.widgets.async_ui_helper import AsyncUIHelper

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402


class PreferencesWindow(Gtk.Window):
    """Preferences window for Galliard"""

    def __init__(self, app, config):
        super().__init__(title="Preferences")

        self.app = app
        self.config = config

        # Set up window
        self.set_default_size(500, 500)
        self.set_modal(True)
        self.set_transient_for(app.props.active_window)

        # Main container
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(self.main_box)

        # Notebook for pages
        self.notebook = Gtk.Notebook()
        self.notebook.set_vexpand(True)
        self.main_box.append(self.notebook)

        # Create pages
        self.create_connection_page()
        self.create_interface_page()

        # Add button box at the bottom
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_margin_top(12)
        button_box.set_margin_bottom(12)
        button_box.set_margin_start(12)
        button_box.set_margin_end(12)
        button_box.set_halign(Gtk.Align.END)

        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda btn: self.close())
        button_box.append(close_button)

        self.main_box.append(button_box)

    def create_connection_page(self):
        """Create MPD connection settings page"""
        # Create page
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_start(24)
        page.set_margin_end(24)
        page.set_margin_top(24)
        page.set_margin_bottom(24)

        # Add page to notebook with icon
        page_icon = Gtk.Image.new_from_icon_name("network-server-symbolic")
        self.notebook.append_page(
            page, Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        )
        tab_label = self.notebook.get_tab_label(page)
        tab_label.append(page_icon)
        tab_label.append(Gtk.Label(label="Connection"))

        # MPD Server Group
        group_frame = Gtk.Frame()
        group_frame.set_margin_bottom(18)
        group_label = Gtk.Label()
        group_label.set_markup("<b>MPD Server</b>")
        group_label.set_halign(Gtk.Align.START)
        group_label.set_margin_bottom(6)

        page.append(group_label)
        page.append(group_frame)

        group_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        group_box.set_margin_start(12)
        group_box.set_margin_end(12)
        group_box.set_margin_top(12)
        group_box.set_margin_bottom(12)
        group_frame.set_child(group_box)

        # Host entry
        host_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        host_label = Gtk.Label(label="Host")
        host_label.set_xalign(0)
        host_label.set_hexpand(True)
        host_entry = Gtk.Entry()
        host_entry.set_text(self.config.get("mpd.host", "localhost"))
        host_entry.connect("changed", self.on_host_changed)
        host_box.append(host_label)
        host_box.append(host_entry)
        group_box.append(host_box)

        # Port entry
        port_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        port_label = Gtk.Label(label="Port")
        port_label.set_xalign(0)
        port_label.set_hexpand(True)
        port_adj = Gtk.Adjustment(
            value=self.config.get("mpd.port", 6600),
            lower=1,
            upper=65535,
            step_increment=1,
        )
        port_spin = Gtk.SpinButton(adjustment=port_adj, digits=0)
        port_spin.connect("value-changed", self.on_port_changed)
        port_box.append(port_label)
        port_box.append(port_spin)
        group_box.append(port_box)

        # Password entry
        password_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        password_label = Gtk.Label(label="Password")
        password_label.set_xalign(0)
        password_label.set_hexpand(True)
        password_entry = Gtk.PasswordEntry()
        password = self.config.get("mpd.password", "")
        if password:
            password_entry.set_text(password)
        password_entry.connect("changed", self.on_password_changed)
        password_box.append(password_label)
        password_box.append(password_entry)
        group_box.append(password_box)

        # Connection timeout
        timeout_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        timeout_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        timeout_label = Gtk.Label(label="Connection Timeout")
        timeout_label.set_xalign(0)
        timeout_subtitle = Gtk.Label(label="Seconds to wait before timeout")
        timeout_subtitle.set_xalign(0)
        timeout_subtitle.add_css_class("dim-label")
        timeout_subtitle.add_css_class("caption")
        timeout_vbox.append(timeout_label)
        timeout_vbox.append(timeout_subtitle)
        timeout_vbox.set_hexpand(True)

        timeout_adj = Gtk.Adjustment(
            value=self.config.get("mpd.timeout", 10),
            lower=1,
            upper=60,
            step_increment=1,
        )
        timeout_spin = Gtk.SpinButton(adjustment=timeout_adj, digits=0)
        timeout_spin.connect("value-changed", self.on_timeout_changed)
        timeout_box.append(timeout_vbox)
        timeout_box.append(timeout_spin)
        group_box.append(timeout_box)

        # Auto-connect
        auto_connect_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        auto_connect_label = Gtk.Label(label="Auto-connect on startup")
        auto_connect_label.set_xalign(0)
        auto_connect_label.set_hexpand(True)
        auto_connect_switch = Gtk.Switch()
        auto_connect_switch.set_active(self.config.get("auto_connect", True))
        auto_connect_switch.set_valign(Gtk.Align.CENTER)
        auto_connect_switch.connect("notify::active", self.on_auto_connect_changed)
        auto_connect_box.append(auto_connect_label)
        auto_connect_box.append(auto_connect_switch)
        group_box.append(auto_connect_box)

        # Add Snapcast Group after the MPD Server Group
        snapcast_label = Gtk.Label()
        snapcast_label.set_markup("<b>Snapcast Integration</b>")
        snapcast_label.set_halign(Gtk.Align.START)
        snapcast_label.set_margin_bottom(6)
        snapcast_label.set_margin_top(12)

        snapcast_frame = Gtk.Frame()
        snapcast_frame.set_margin_bottom(18)

        page.append(snapcast_label)
        page.append(snapcast_frame)

        snapcast_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        snapcast_box.set_margin_start(12)
        snapcast_box.set_margin_end(12)
        snapcast_box.set_margin_top(12)
        snapcast_box.set_margin_bottom(12)
        snapcast_frame.set_child(snapcast_box)

        # Volume control method
        volume_method_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        volume_method_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        volume_method_label = Gtk.Label(label="Volume Control")
        volume_method_label.set_xalign(0)
        volume_method_subtitle = Gtk.Label(
            label="Method used to control playback volume"
        )
        volume_method_subtitle.set_xalign(0)
        volume_method_subtitle.add_css_class("dim-label")
        volume_method_subtitle.add_css_class("caption")
        volume_method_vbox.append(volume_method_label)
        volume_method_vbox.append(volume_method_subtitle)
        volume_method_vbox.set_hexpand(True)

        # Create dropdown for volume control method
        self.volume_method_dropdown = Gtk.DropDown.new_from_strings(["MPD", "Snapcast"])

        current_method = self.config.get("volume.method", "mpd").lower()
        if current_method == "snapcast":
            self.volume_method_dropdown.set_selected(1)
        else:  # mpd
            self.volume_method_dropdown.set_selected(0)

        self.volume_method_dropdown.connect(
            "notify::selected", self.on_volume_method_changed
        )
        volume_method_box.append(volume_method_vbox)
        volume_method_box.append(self.volume_method_dropdown)
        snapcast_box.append(volume_method_box)

        # Snapcast server settings
        snapcast_server_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=12
        )
        snapcast_server_label = Gtk.Label(label="Snapcast Server")
        snapcast_server_label.set_xalign(0)
        snapcast_server_label.set_hexpand(True)
        snapcast_server_entry = Gtk.Entry()
        snapcast_server_entry.set_text(self.config.get("snapcast.host", "localhost"))
        snapcast_server_entry.connect("changed", self.on_snapcast_host_changed)
        snapcast_server_box.append(snapcast_server_label)
        snapcast_server_box.append(snapcast_server_entry)
        snapcast_box.append(snapcast_server_box)

        # Snapcast port
        snapcast_port_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        snapcast_port_label = Gtk.Label(label="Snapcast Port")
        snapcast_port_label.set_xalign(0)
        snapcast_port_label.set_hexpand(True)
        snapcast_port_adj = Gtk.Adjustment(
            value=self.config.get("snapcast.port", 1780),
            lower=1,
            upper=65535,
            step_increment=1,
        )
        snapcast_port_spin = Gtk.SpinButton(adjustment=snapcast_port_adj, digits=0)
        snapcast_port_spin.connect("value-changed", self.on_snapcast_port_changed)
        snapcast_port_box.append(snapcast_port_label)
        snapcast_port_box.append(snapcast_port_spin)
        snapcast_box.append(snapcast_port_box)

        # Snapcast client selection
        client_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        client_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        client_label = Gtk.Label(label="Snapcast Client")
        client_label.set_xalign(0)
        client_subtitle = Gtk.Label(label="Select which client's volume to control")
        client_subtitle.set_xalign(0)
        client_subtitle.add_css_class("dim-label")
        client_subtitle.add_css_class("caption")
        client_vbox.append(client_label)
        client_vbox.append(client_subtitle)
        client_vbox.set_hexpand(True)

        # Create dropdown for Snapcast client selection
        self.client_dropdown = Gtk.DropDown.new_from_strings(["Loading..."])
        self.update_snapcast_client_list()

        # Create a string list model with available clients
        # client_names = [
        #     client["name"] for client in self.app.mpd_client.snapcast_clients
        # ] or ["No clients found"]
        # self.client_dropdown = Gtk.DropDown.new_from_strings(client_names)

        # Set selected client if it exists
        # selected_client_id = self.config.get("snapcast.client_id", "")
        # for i, client in enumerate(self.app.mpd_client.snapcast_clients):
        #    if client["id"] == selected_client_id:
        #        self.client_dropdown.set_selected(i)
        #        break

        self.client_dropdown_handler_id = self.client_dropdown.connect(
            "notify::selected", self.on_snapcast_client_changed
        )

        # Add refresh button
        refresh_button = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_button.set_tooltip_text("Refresh client list")
        refresh_button.connect("clicked", self.on_refresh_snapcast_clients)

        client_box.append(client_vbox)
        client_box.append(self.client_dropdown)
        client_box.append(refresh_button)
        snapcast_box.append(client_box)

        # Set sensitivity of Snapcast controls based on current method
        is_snapcast = current_method == "snapcast"
        snapcast_server_entry.set_sensitive(is_snapcast)
        snapcast_port_spin.set_sensitive(is_snapcast)
        self.client_dropdown.set_sensitive(is_snapcast)
        refresh_button.set_sensitive(is_snapcast)

    def create_interface_page(self):
        """Create interface settings page"""
        # Create page
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_start(24)
        page.set_margin_end(24)
        page.set_margin_top(24)
        page.set_margin_bottom(24)

        # Add page to notebook with icon
        page_icon = Gtk.Image.new_from_icon_name(
            "preferences-desktop-appearance-symbolic"
        )
        self.notebook.append_page(
            page, Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        )
        tab_label = self.notebook.get_tab_label(page)
        tab_label.append(page_icon)
        tab_label.append(Gtk.Label(label="Interface"))

        # Appearance Group
        group_label = Gtk.Label()
        group_label.set_markup("<b>Appearance</b>")
        group_label.set_halign(Gtk.Align.START)
        group_label.set_margin_bottom(6)

        group_frame = Gtk.Frame()
        group_frame.set_margin_bottom(18)

        page.append(group_label)
        page.append(group_frame)

        group_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        group_box.set_margin_start(12)
        group_box.set_margin_end(12)
        group_box.set_margin_top(12)
        group_box.set_margin_bottom(12)
        group_frame.set_child(group_box)

        # Theme
        theme_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        theme_label = Gtk.Label(label="Theme")
        theme_label.set_xalign(0)
        theme_label.set_hexpand(True)

        theme_dropdown = Gtk.DropDown.new_from_strings(["System", "Light", "Dark"])

        current_theme = self.config.get("ui.theme", "system").lower()
        if current_theme == "light":
            theme_dropdown.set_selected(1)
        elif current_theme == "dark":
            theme_dropdown.set_selected(2)
        else:  # system
            theme_dropdown.set_selected(0)

        theme_dropdown.connect("notify::selected", self.on_theme_changed)
        theme_box.append(theme_label)
        theme_box.append(theme_dropdown)
        group_box.append(theme_box)

        # Show album art
        album_art_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        album_art_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        album_art_label = Gtk.Label(label="Show album art")
        album_art_label.set_xalign(0)
        album_art_subtitle = Gtk.Label(label="Display album covers if available")
        album_art_subtitle.set_xalign(0)
        album_art_subtitle.add_css_class("dim-label")
        album_art_subtitle.add_css_class("caption")
        album_art_vbox.append(album_art_label)
        album_art_vbox.append(album_art_subtitle)
        album_art_vbox.set_hexpand(True)

        album_art_switch = Gtk.Switch()
        album_art_switch.set_active(self.config.get("ui.show_album_art", True))
        album_art_switch.set_valign(Gtk.Align.CENTER)
        album_art_switch.connect("notify::active", self.on_album_art_changed)
        album_art_box.append(album_art_vbox)
        album_art_box.append(album_art_switch)
        group_box.append(album_art_box)

        # Notification Group
        notif_label = Gtk.Label()
        notif_label.set_markup("<b>Notifications</b>")
        notif_label.set_halign(Gtk.Align.START)
        notif_label.set_margin_bottom(6)
        notif_label.set_margin_top(12)

        notif_frame = Gtk.Frame()
        notif_frame.set_margin_bottom(18)

        page.append(notif_label)
        page.append(notif_frame)

        notif_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        notif_box.set_margin_start(12)
        notif_box.set_margin_end(12)
        notif_box.set_margin_top(12)
        notif_box.set_margin_bottom(12)
        notif_frame.set_child(notif_box)

        # Show notifications
        notifications_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        notifications_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        notifications_label = Gtk.Label(label="Show notifications")
        notifications_label.set_xalign(0)
        notifications_subtitle = Gtk.Label(
            label="Display notifications when songs change"
        )
        notifications_subtitle.set_xalign(0)
        notifications_subtitle.add_css_class("dim-label")
        notifications_subtitle.add_css_class("caption")
        notifications_vbox.append(notifications_label)
        notifications_vbox.append(notifications_subtitle)
        notifications_vbox.set_hexpand(True)

        notifications_switch = Gtk.Switch()
        notifications_switch.set_active(self.config.get("ui.show_notifications", True))
        notifications_switch.set_valign(Gtk.Align.CENTER)
        notifications_switch.connect("notify::active", self.on_notifications_changed)
        notifications_box.append(notifications_vbox)
        notifications_box.append(notifications_switch)
        notif_box.append(notifications_box)

        # Minimize to tray
        tray_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        tray_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        tray_label = Gtk.Label(label="Minimize to system tray")
        tray_label.set_xalign(0)
        tray_subtitle = Gtk.Label(label="Keep app running in system tray when closed")
        tray_subtitle.set_xalign(0)
        tray_subtitle.add_css_class("dim-label")
        tray_subtitle.add_css_class("caption")
        tray_vbox.append(tray_label)
        tray_vbox.append(tray_subtitle)
        tray_vbox.set_hexpand(True)

        tray_switch = Gtk.Switch()
        tray_switch.set_active(self.config.get("ui.minimize_to_tray", True))
        tray_switch.set_valign(Gtk.Align.CENTER)
        tray_switch.connect("notify::active", self.on_tray_changed)
        tray_box.append(tray_vbox)
        tray_box.append(tray_switch)
        notif_box.append(tray_box)

    # Connection settings handlers

    def on_host_changed(self, entry):
        """Handle host change"""
        self.config.set("mpd.host", entry.get_text())

    def on_port_changed(self, spin_button):
        """Handle port change"""
        self.config.set("mpd.port", int(spin_button.get_value()))

    def on_password_changed(self, entry):
        """Handle password change"""
        self.config.set("mpd.password", entry.get_text())

    def on_timeout_changed(self, spin_button):
        """Handle timeout change"""
        self.config.set("mpd.timeout", int(spin_button.get_value()))

    def on_auto_connect_changed(self, switch, pspec):
        """Handle auto-connect change"""
        self.config.set("auto_connect", switch.get_active())

    # Interface settings handlers

    def on_theme_changed(self, dropdown, pspec):
        """Handle theme change"""
        themes = ["system", "light", "dark"]
        selected = dropdown.get_selected()
        if selected < len(themes):
            self.config.set("ui.theme", themes[selected])

            # Apply theme - use GTK settings instead of Adw
            settings = Gtk.Settings.get_default()
            if themes[selected] == "light":
                settings.set_property("gtk-application-prefer-dark-theme", False)
            elif themes[selected] == "dark":
                settings.set_property("gtk-application-prefer-dark-theme", True)
            else:
                # Use system default - this is a bit trickier without Adw
                # For simplicity we'll default to light mode
                settings.set_property("gtk-application-prefer-dark-theme", False)

    def on_album_art_changed(self, switch, pspec):
        """Handle album art change"""
        self.config.set("ui.show_album_art", switch.get_active())

    def on_notifications_changed(self, switch, pspec):
        """Handle notifications change"""
        self.config.set("ui.show_notifications", switch.get_active())

    def on_tray_changed(self, switch, pspec):
        """Handle tray change"""
        self.config.set("ui.minimize_to_tray", switch.get_active())

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
            self.client_dropdown.disconnect(self.client_dropdown_handler_id)

            # Update dropdown with new client list
            client_names = [
                client["name"] for client in self.app.mpd_client.snapcast_clients
            ] or ["No clients found"]
            # Create a new string list model
            string_list = Gtk.StringList()
            for name in client_names:
                string_list.append(name)
            self.client_dropdown.set_model(string_list)

            # Set selected client if it exists
            selected_client_id = self.config.get("snapcast.client_id", "")
            for i, client in enumerate(self.app.mpd_client.snapcast_clients):
                if client["id"] == selected_client_id:
                    self.client_dropdown.set_selected(i)
                    break
            self.client_dropdown_handler_id = self.client_dropdown.connect(
                "notify::selected", self.on_snapcast_client_changed
            )
            return

        GLib.idle_add(update_client_dropdown)

    def on_refresh_snapcast_clients(self, button):
        """Handle refresh button click for Snapcast clients"""
        self.update_snapcast_client_list()

    def on_volume_method_changed(self, dropdown, pspec):
        """Handle volume control method change"""
        methods = ["mpd", "snapcast"]
        selected = dropdown.get_selected()
        if selected < len(methods):
            method = methods[selected]
            self.config.set("volume.method", method)

            # Enable/disable Snapcast settings based on selection
            is_snapcast = method == "snapcast"

            # Get the snapcast_box (parent of dropdown's parent)
            snapcast_box = dropdown.get_parent().get_parent()

            # Skip the first child (volume method box itself)
            child = snapcast_box.get_first_child().get_next_sibling()

            # Enable/disable all remaining Snapcast-specific settings
            while child:
                child.set_sensitive(is_snapcast)
                child = child.get_next_sibling()

    def on_snapcast_host_changed(self, entry):
        """Handle Snapcast host change"""
        self.config.set("snapcast.host", entry.get_text())

    def on_snapcast_port_changed(self, spin_button):
        """Handle Snapcast port change"""
        self.config.set("snapcast.port", int(spin_button.get_value()))

    def on_snapcast_client_changed(self, dropdown, pspec):
        """Handle Snapcast client selection change"""
        selected = dropdown.props.selected_item.get_string()
        print(f"!!!!!!!!! Selected Snapcast client: {selected}")
        for client in self.app.mpd_client.snapcast_clients:
            if client["name"] == selected:
                print(f"Setting Snapcast client ID to: {client['id']}")
                self.config.set("snapcast.client_id", client["id"])
                AsyncUIHelper.run_async_operation(
                    self.app.mpd_client._select_snapcast_client
                )
                return
