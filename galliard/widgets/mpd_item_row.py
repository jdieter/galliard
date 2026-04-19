"""Shared factory scaffolding for compact tree-view rows.

The artists, files, and search-results views all render a compact row
consisting of an expander, a 20x20 image, and a label, with optional
right-click context menu and (for artists) a play button. This module
builds the box + widgets once so each view's ``_item_setup`` collapses
to a single call.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


def build_compact_tree_row(
    list_item,
    *,
    on_expand=None,
    on_context=None,
    on_play=None,
):
    """Populate ``list_item`` with the compact-tree row scaffold.

    Attaches the box as ``list_item``'s child and stashes the
    key widgets as attributes on ``list_item``:

      - ``list_item.expander``: initially hidden; the bind callback is
        responsible for making it visible on expandable rows and setting
        the pan-{end,down}-symbolic icon.
      - ``list_item.image``: 20x20 icon / album-art holder.
      - ``list_item.label``: stretched to fill horizontal space.
      - ``list_item.play_button``: present only when ``on_play`` is given;
        initially hidden, bind callback makes it visible on rows where it
        applies.

    Handlers are connected with ``(handler, list_item)`` signatures so
    view methods can look up the current item via ``list_item.get_item()``
    / ``list_item.tree_list_row.get_item()``.
    """
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    box.set_margin_start(0)
    box.set_margin_end(0)
    box.set_margin_top(0)
    box.set_margin_bottom(0)

    expander = Gtk.Button.new_from_icon_name("pan-end-symbolic")
    expander.add_css_class("flat")
    expander.set_visible(False)
    expander.set_name("compact-expander")
    box.append(expander)

    image = Gtk.Image()
    image.set_size_request(20, 20)
    image.add_css_class("compact")
    box.append(image)

    label = Gtk.Label()
    label.set_halign(Gtk.Align.START)
    label.set_hexpand(True)
    label.add_css_class("compact")
    box.append(label)

    list_item.expander = expander
    list_item.image = image
    list_item.label = label

    if on_play is not None:
        play_button = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
        play_button.add_css_class("flat")
        play_button.set_tooltip_text("Play")
        play_button.set_visible(False)
        play_button.connect("clicked", on_play, list_item)
        box.append(play_button)
        list_item.play_button = play_button

    if on_expand is not None:
        expander.connect("clicked", on_expand, list_item)

    if on_context is not None:
        gesture = Gtk.GestureClick.new()
        gesture.set_button(3)  # Right mouse button
        gesture.connect("pressed", on_context, list_item)
        box.add_controller(gesture)

    list_item.set_child(box)
