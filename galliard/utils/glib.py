"""GLib utility functions for Galliard."""

from gi.repository import GLib

def idle_add_once(callback, *args, **kwargs):
    """Schedule ``callback(*args, **kwargs)`` to run once on the GLib main loop.

    A thin wrapper over ``GLib.idle_add`` that returns ``SOURCE_REMOVE`` so
    the callback isn't kept on the idle queue.
    """
    def _wrapper():
        callback(*args, **kwargs)
        return GLib.SOURCE_REMOVE

    return GLib.idle_add(_wrapper)
