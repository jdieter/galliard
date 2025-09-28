import gi
from typing import Dict, Any, Optional

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


class DataMixin:
    """Mixin class that provides data storage capability to GTK widgets"""

    def __init__(self, data: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(**kwargs)
        # Create a copy to avoid mutable default argument issues
        self._data: Dict[str, Any] = data.copy() if data else {}

    @property
    def data(self) -> Dict[str, Any]:
        """Get the data dictionary"""
        return self._data

    @data.setter
    def data(self, value: Dict[str, Any]) -> None:
        """Set the data dictionary"""
        self._data = value.copy() if value else {}


class Widget(DataMixin, Gtk.Widget):
    """Custom Widget that can hold additional data"""

    def __init__(self, data: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(data=data, **kwargs)


class ListBoxRow(DataMixin, Gtk.ListBoxRow):
    """Custom ListBoxRow that can hold additional data"""

    def __init__(self, data: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(data=data, **kwargs)


class ListBox(DataMixin, Gtk.ListBox):
    """Custom ListBox that can hold additional data"""

    def __init__(self, data: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(data=data, **kwargs)

    def get_first_child(self) -> Widget | None:
        return super().get_first_child()

    def get_selected_rows(self) -> list[ListBoxRow]:
        return self.get_selected_rows()

    def select_row(self, row: ListBoxRow | Widget | None = None) -> None:
        return super().select_row(row)

    def get_row_at_index(self, index_: int) -> ListBoxRow | None:
        return super().get_row_at_index(index_)

    def is_selected(self, row: ListBoxRow) -> bool:
        selected_rows = self.get_selected_rows()
        return row in selected_rows


class Button(DataMixin, Gtk.Button):
    """Custom Button that can hold additional data"""

    def __init__(self, data: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(data=data, **kwargs)


class Label(DataMixin, Gtk.Label):
    """Custom Label that can hold additional data"""

    def __init__(self, data: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(data=data, **kwargs)
