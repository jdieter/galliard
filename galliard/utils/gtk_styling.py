"""Shared GTK CSS helpers."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402


_applied_tree_names: set[str] = set()


def apply_compact_tree_css(widget_name: str) -> None:
    """Install compact-row CSS for a tree/list view identified by ``widget_name``.

    The caller is responsible for assigning the name to the widget
    (``widget.set_name(widget_name)``). Repeated calls with the same name are
    no-ops to avoid stacking identical providers on the default display, which
    GTK does not deduplicate.
    """
    if widget_name in _applied_tree_names:
        return

    display = Gdk.Display.get_default()
    if display is None:
        return

    css = f"""
    #{widget_name} {{
        padding: 0;
    }}
    #{widget_name} row {{
        padding-top: 0px;
        padding-bottom: 0px;
        min-height: 20px;
    }}
    #{widget_name} cell {{
        padding-top: 1px;
        padding-bottom: 1px;
        min-height: 20px;
    }}
    .compact {{
        padding-top: 0;
        padding-bottom: 0;
        margin-top: 0;
        margin-bottom: 0;
    }}
    #compact-expander {{
        padding-top: 0;
        padding-bottom: 0;
        min-height: 16px;
        min-width: 16px;
    }}
    #compact-expander image {{
        -gtk-icon-size: 12px;
    }}
    """

    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode())
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _applied_tree_names.add(widget_name)
