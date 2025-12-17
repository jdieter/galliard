"""GLib utility functions for Galliard."""

import logging
from gi.repository import GLib

def idle_add_once(callback, *args, **kwargs):
    """
    Add a callback to be called during idle time, guaranteed to run only once.

    This wraps GLib.idle_add with a helper function that always returns False,
    ensuring the callback is removed after a single execution.

    Args:
        callback: The function to call during idle time
        *args: Positional arguments to pass to the callback
        **kwargs: Keyword arguments to pass to the callback

    Returns:
        The ID of the event source (same as GLib.idle_add)
    """
    def _wrapper():
        callback(*args, **kwargs)
        return GLib.SOURCE_REMOVE

    return GLib.idle_add(_wrapper)
