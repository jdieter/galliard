import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk  # noqa: E402


class ContextMenu:
    """Utility class to create and show context menus consistently across the application"""

    @staticmethod
    def create_menu_with_actions(
        parent_widget,
        menu_items,
        action_group_name="ctx",
        position_x=None,
        position_y=None,
    ):
        """
        Create and show a context menu using Gio actions (preferred GTK4 approach)

        Args:
            parent_widget: The widget the context menu is associated with
            menu_items: List of dict with keys 'label', 'action', 'callback', and optional
                        'action_param'
            action_group_name: Name for the action group to be used (default: "ctx")
            position_x: Optional X position for the menu (default: None - use pointer position)
            position_y: Optional Y position for the menu (default: None - use pointer position)

        Returns:
            The popover menu object
        """
        # Create a menu model
        menu = Gio.Menu()

        # Create action group for this context menu
        action_group = Gio.SimpleActionGroup()
        parent_widget.insert_action_group(action_group_name, action_group)

        # Add menu items and their associated actions
        for item in menu_items:
            if item is None:
                # Add separator (section break)
                menu.append_section(None, Gio.Menu())
                continue

            action_name = item["action"]
            full_action_name = f"{action_group_name}.{action_name}"

            # Create the action
            if "action_param" in item:
                # Action with parameter
                param_type = item.get("param_type", "s")  # Default to string
                action = Gio.SimpleAction.new(
                    action_name, GLib.VariantType.new(param_type)
                )
                action.connect(
                    "activate",
                    lambda act, param, cb=item["callback"]: cb(param.get_string()),
                )
                menu.append(
                    item["label"], f"{full_action_name}::'{item['action_param']}'"
                )
            else:
                # Simple action without parameter
                action = Gio.SimpleAction.new(action_name, None)
                action.connect("activate", lambda *args, cb=item["callback"]: cb())
                menu.append(item["label"], full_action_name)

            # Add the action to our group
            action_group.add_action(action)

        # Create the popover menu from model
        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_has_arrow(False)
        popover.set_parent(parent_widget)

        # Set position if provided
        if position_x is not None and position_y is not None:
            rect = Gdk.Rectangle()
            rect.x = position_x
            rect.y = position_y
            rect.width = 1
            rect.height = 1
            popover.set_pointing_to(rect)

        # Show the menu
        popover.popup()

        return popover
