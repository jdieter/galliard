import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk  # noqa: E402


class ContextMenu:
    """Build and show right-click context menus consistently across the app."""

    @staticmethod
    def create_menu_with_actions(
        parent_widget,
        menu_items,
        action_group_name="ctx",
        position_x=None,
        position_y=None,
    ):
        """Build a Gio-action-backed popover menu and pop it up at (x, y).

        Each entry in ``menu_items`` is either ``None`` for a separator or a
        dict ``{"label", "action", "callback", optional "action_param", optional
        "param_type"}``. Position defaults to the pointer location.
        """
        menu = Gio.Menu()

        # A fresh action group per context menu so callbacks don't leak.
        action_group = Gio.SimpleActionGroup()
        parent_widget.insert_action_group(action_group_name, action_group)

        for item in menu_items:
            if item is None:
                menu.append_section(None, Gio.Menu())
                continue

            action_name = item["action"]
            full_action_name = f"{action_group_name}.{action_name}"

            if "action_param" in item:
                param_type = item.get("param_type", "s")
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
                action = Gio.SimpleAction.new(action_name, None)
                action.connect("activate", lambda *args, cb=item["callback"]: cb())
                menu.append(item["label"], full_action_name)

            action_group.add_action(action)

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_has_arrow(False)
        popover.set_parent(parent_widget)

        if position_x is not None and position_y is not None:
            rect = Gdk.Rectangle()
            rect.x = position_x
            rect.y = position_y
            rect.width = 1
            rect.height = 1
            popover.set_pointing_to(rect)

        popover.popup()
        return popover
