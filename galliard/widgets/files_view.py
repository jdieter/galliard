import logging

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, Gio  # noqa: E402

from galliard.models import FileItem  # noqa: E402
from galliard.utils.sorting import get_sort_key  # noqa: E402
from galliard.utils.album_art import get_album_art_as_pixbuf  # noqa: E402
from galliard.utils.async_task_queue import AsyncUIHelper  # noqa: E402
from galliard.utils.context_menu import ContextMenu  # noqa: E402
from galliard.utils.glib import idle_add_once  # noqa: E402
from galliard.utils.gtk_styling import apply_compact_tree_css  # noqa: E402
from galliard.widgets.mpd_item_row import build_compact_tree_row  # noqa: E402


class FilesView(Gtk.ScrolledWindow):
    """Filesystem-style tree of the MPD music directory."""

    def __init__(self, mpd_client):
        """Build the tree and schedule loading the root directory."""
        super().__init__()
        self.mpd_client = mpd_client
        self._current_hovered_image = None
        self.last_preview_popover = None

        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.create_ui()

        # Wait for the UI to finish construction before the first fetch.
        AsyncUIHelper.run_glib_idle_async(self.load_root_directory)

    def create_ui(self):
        """Build the tree model, column view, and compact-row CSS."""
        self.files_store = Gio.ListStore.new(FileItem)

        # Lazy child model: directories only fetch contents on expansion.
        self.tree_model = Gtk.TreeListModel.new(
            self.files_store,
            False,  # passthrough
            False,  # autoexpand
            self._create_file_children_model,
        )

        self.selection = Gtk.SingleSelection.new(self.tree_model)

        self.files_tree = Gtk.ColumnView.new(self.selection)
        self.files_tree.set_show_column_separators(False)
        self.files_tree.set_show_row_separators(False)

        factory = Gtk.SignalListItemFactory.new()
        factory.connect("setup", self._file_item_setup)
        factory.connect("bind", self._file_item_bind)
        factory.connect("unbind", self._file_item_unbind)

        column = Gtk.ColumnViewColumn.new("Files", factory)
        column.set_expand(True)
        self.files_tree.append_column(column)

        # One-column view: no need to show the column header.
        table_header = self.files_tree.get_first_child()
        if table_header:
            table_header.set_visible(False)

        self.selection.connect("selection-changed", self._on_file_selection_changed)

        self.set_child(self.files_tree)

        self.files_tree.set_name("files-tree")
        apply_compact_tree_css("files-tree")

    def _file_item_setup(self, factory, list_item):
        """Populate the row scaffold shared with the artists/search views."""
        build_compact_tree_row(
            list_item,
            on_expand=self._on_expander_clicked,
            on_context=self._on_file_item_right_click,
        )

    def _file_item_bind(self, factory, list_item):
        """Populate a scaffolded row from the FileItem at its position."""
        tree_list_row = list_item.get_item()
        file_item = tree_list_row.get_item()

        if not file_item:
            return

        # Manual indentation -- the ColumnView row isn't a TreeExpander, so
        # we draw our own depth spacing on the margin.
        depth = tree_list_row.get_depth()
        indent_pixels = depth * 24

        if file_item.is_directory:
            list_item.expander.set_margin_start(indent_pixels)
            list_item.expander.set_visible(True)

            is_expanded = tree_list_row.get_expanded()
            icon_name = "pan-down-symbolic" if is_expanded else "pan-end-symbolic"
            list_item.expander.set_icon_name(icon_name)
            list_item.image.set_margin_start(0)
        else:
            list_item.expander.set_visible(False)
            # Shift the icon over by expander-width so files align with their
            # parent directory's label.
            list_item.image.set_margin_start(indent_pixels + 26)

        if file_item.pixbuf:
            list_item.image.set_from_pixbuf(file_item.pixbuf)
            # Hover-preview controller only attached when real art is present.
            motion_controller = Gtk.EventControllerMotion.new()
            motion_controller.connect("motion", self._on_tree_motion)
            motion_controller.connect("leave", self._on_tree_leave)
            list_item.image.add_controller(motion_controller)
        else:
            list_item.image.set_from_icon_name(file_item.icon_name)

        list_item.label.set_text(file_item.name)

        list_item.tree_list_row = tree_list_row
        file_item.list_item = list_item

    def _file_item_unbind(self, factory, list_item):
        """Clear the stashed tree_list_row so recycled rows don't leak state."""
        list_item.tree_list_row = None

    def _create_file_children_model(self, file_item):
        """Build the child Gio.ListStore for a directory FileItem.

        On first expansion a loading placeholder is shown while the real
        contents fetch asynchronously; :meth:`_update_children` swaps the
        placeholder out once the fetch returns.
        """
        if not file_item.is_directory:
            return None

        child_store = Gio.ListStore.new(FileItem)

        if not file_item.children_loaded:
            AsyncUIHelper.run_async_operation(
                self.load_directory_contents,
                lambda result: self._update_children(file_item, result, child_store),
                file_item.path,
            )

            loading_item = FileItem(
                name="Loading...",
                path="",
                icon_name="content-loading-symbolic",
                is_directory=False,
                pixbuf=None,
            )
            child_store.append(loading_item)
        else:
            for child in file_item.children:
                child_store.append(child)

        return child_store

    def _update_children(self, parent_item, children, child_store):
        """Replace ``parent_item``'s loading placeholder with the real children."""
        parent_item.children = children
        parent_item.children_loaded = True

        child_store.remove_all()

        for child in parent_item.children:
            child_store.append(child)

        idle_add_once(self.files_tree.queue_draw)

    async def _get_directory_contents(self, directory):
        """Return ``(dir_paths, file_paths)`` for an MPD directory, each sorted."""
        dir_contents = await self.mpd_client.async_list_directory(directory)

        dir_paths = []
        file_paths = []

        for item in dir_contents:
            if "directory" in item:
                dir_paths.append(item["directory"])
            elif "file" in item:
                file_paths.append(item["file"])

        dir_paths.sort(
            key=lambda path: get_sort_key(path.split("/")[-1] if "/" in path else path)
        )
        file_paths.sort(
            key=lambda path: get_sort_key(path.split("/")[-1] if "/" in path else path)
        )
        return dir_paths, file_paths

    def _is_music_file(self, file_path):
        """True if ``file_path`` has a recognised audio extension."""
        if any(
            file_path.lower().endswith(ext)
            for ext in [".mp3", ".flac", ".ogg", ".wav", ".aac", ".m4a"]
        ):
            return True
        return False

    async def load_directory_contents(self, directory):
        """Return FileItems for ``directory`` -- directories first, then files.

        Queues a background task per subdirectory to fetch a representative
        cover image; those fill in later via :meth:`_update_item_art`.
        """
        items = []

        try:
            dir_paths, file_paths = await self._get_directory_contents(directory)

            for dir_path in dir_paths:
                dir_name = dir_path.split("/")[-1] if "/" in dir_path else dir_path
                file_item = FileItem(
                    name=dir_name,
                    path=dir_path,
                    icon_name="folder-symbolic",
                    is_directory=True,
                    pixbuf=None,
                )
                items.append(file_item)

                AsyncUIHelper.run_async_operation(
                    self._load_directory_art,
                    lambda result, item=file_item: self._update_item_art(item, result),
                    dir_path,
                    task_priority=110,
                )

            for file_path in file_paths:
                if self._is_music_file(file_path):
                    file_name = (
                        file_path.split("/")[-1] if "/" in file_path else file_path
                    )
                    file_item = FileItem(
                        name=file_name,
                        path=file_path,
                        icon_name="audio-x-generic-symbolic",
                        is_directory=False,
                        pixbuf=None,
                    )
                    items.append(file_item)

        except Exception as e:
            logging.error("Error loading directory %s: %s", directory, e)
            # Surface the error as a row so the UI isn't silently empty.
            items.append(
                FileItem(
                    name=f"Error: {str(e)}",
                    path="",
                    icon_name="dialog-error-symbolic",
                    is_directory=False,
                    pixbuf=None,
                )
            )

        return items

    async def _load_directory_art(self, dir_path):
        """Return cover-art pixbuf for a directory using its first music file."""
        try:
            dir_contents = await self.mpd_client.async_list_directory(dir_path)
            audio_file = next(
                (
                    item["file"]
                    for item in dir_contents
                    if "file" in item and self._is_music_file(item["file"])
                ),
                None,
            )

            if audio_file:
                try:
                    return await get_album_art_as_pixbuf(
                        self.mpd_client, audio_file, 200
                    )
                except Exception as e:
                    logging.error("Error getting album art for %s: %s", audio_file, e)
        except Exception as e:
            logging.error("Error loading art for directory %s: %s", dir_path, e)

        return None

    def _update_item_art(self, file_item, pixbuf):
        """Back-fill fetched cover art onto a directory row."""
        if pixbuf and file_item.list_item is not None:
            file_item.pixbuf = pixbuf
            file_item.icon_name = None
            file_item.list_item.image.set_from_pixbuf(pixbuf)
            file_item.list_item.image.pixbuf_data = pixbuf

            # Hover-preview only makes sense once real art is present.
            motion_controller = Gtk.EventControllerMotion.new()
            motion_controller.connect("motion", self._on_tree_motion)
            motion_controller.connect("leave", self._on_tree_leave)
            file_item.list_item.image.add_controller(motion_controller)

            idle_add_once(self.files_tree.queue_draw)

    def _on_expander_clicked(self, button, list_item):
        """Toggle row expansion and swap the chevron icon."""
        tree_list_row = list_item.tree_list_row
        if tree_list_row:
            is_expanded = tree_list_row.get_expanded()

            if not is_expanded:
                # TreeListModel's create_func will kick off the directory
                # fetch on the first expansion automatically.
                tree_list_row.set_expanded(True)
                button.set_icon_name("pan-down-symbolic")
            else:
                tree_list_row.set_expanded(False)
                button.set_icon_name("pan-end-symbolic")

    def _on_file_selection_changed(self, selection, position, n_items):
        """Selecting a file row appends it to the playlist and plays it."""
        selected = selection.get_selected_item()
        if not selected:
            return

        file_item = selected.get_item()
        if not file_item:
            return

        if not file_item.is_directory:
            self.mpd_client.add_to_playlist(file_item.path)
            playlist = self.mpd_client.get_current_playlist()
            if playlist:
                # Play the song just appended (last item in the playlist).
                self.mpd_client.client.play(len(playlist) - 1)

    async def load_root_directory(self):
        """Populate ``self.files_store`` with the MPD library root."""
        logging.debug("Loading root directory...")

        if not self.mpd_client.is_connected():
            logging.debug("MPD client not connected")
            return False

        try:
            self.files_store.remove_all()

            items = await self.load_directory_contents("")
            logging.debug("Loaded %d items from root directory", len(items))

            for item in items:
                self.files_store.append(item)

            idle_add_once(self.files_tree.queue_draw)

        except Exception as e:
            logging.error("Error loading root directory: %s", e)

        return False

    def _on_tree_motion(self, controller, x, y):
        """Show the hover-preview popover when the cursor is over album art."""
        image = controller.get_widget()

        if hasattr(image, "pixbuf_data") and image.pixbuf_data:
            widget_position = image.translate_coordinates(self.files_tree, x, y)

            if not widget_position:
                return

            tree_x, tree_y = widget_position

            if self._current_hovered_image != image:
                self._current_hovered_image = image

            self._show_preview(image.pixbuf_data, tree_x, tree_y)

    def _on_tree_leave(self, controller):
        """Hide the hover-preview popover once the cursor leaves the art."""
        image = controller.get_widget()
        if image == self._current_hovered_image:
            self._hide_preview()

    def _show_preview(self, pixbuf, x, y):
        """Pop up a 150x150 preview of ``pixbuf`` near (x, y)."""
        if not self.last_preview_popover:
            self.last_preview_popover = Gtk.Popover()
            self.last_preview_popover.set_autohide(True)

            self.preview_image = Gtk.Image()
            self.preview_image.set_size_request(150, 150)

            self.last_preview_popover.set_child(self.preview_image)
            self.last_preview_popover.set_parent(self.files_tree)

        self.preview_image.set_from_pixbuf(pixbuf)

        # Offset from the cursor so the popover doesn't sit on top of the
        # row being hovered.
        rect = Gdk.Rectangle()
        rect.x = int(x) + 20
        rect.y = int(y)
        rect.width = 1
        rect.height = 1

        self.last_preview_popover.set_pointing_to(rect)
        self.last_preview_popover.popup()

    def _hide_preview(self):
        """Dismiss the hover-preview popover."""
        self._current_hovered_image = None
        if self.last_preview_popover:
            self.last_preview_popover.popdown()

    def _on_file_item_right_click(self, gesture, n_press, x, y, list_item):
        """Show an Append / Replace menu for the right-clicked file or directory."""
        tree_list_row = list_item.tree_list_row
        if not tree_list_row:
            return

        file_item = tree_list_row.get_item()
        if not file_item:
            return

        menu_items = [
            {
                "label": "Append",
                "action": "append",
                "callback": lambda: self._on_context_menu_action(
                    file_item, replace=False
                ),
            },
            {
                "label": "Replace",
                "action": "replace",
                "callback": lambda: self._on_context_menu_action(
                    file_item, replace=True
                ),
            },
        ]
        ContextMenu.create_menu_with_actions(
            list_item.get_child(), menu_items, "row", x, y,
        )

    def _on_context_menu_action(self, file_item, replace):
        """Dispatch the chosen Append/Replace action to :meth:`add_path_to_playlist`."""
        AsyncUIHelper.run_async_operation(
            self.add_path_to_playlist, None, file_item, replace
        )

    async def add_path_to_playlist(self, file_item, replace=False):
        """Append or replace the playlist with one song or a whole directory."""
        try:
            if replace:
                await self.mpd_client.async_clear_playlist()

            if file_item.is_directory:
                paths = await self._add_directory_to_playlist(file_item.path)
            else:
                paths = [file_item.path]

            await self.mpd_client.async_add_songs_to_playlist(paths)
            if replace:
                await self.mpd_client.async_play(0)
        except Exception as e:
            logging.error("Error adding to playlist %s: %s", file_item.path, e)

    async def _add_directory_to_playlist(self, directory_path):
        """Return every music file path under ``directory_path``, recursing subdirs first."""
        songs = []

        dir_paths, file_paths = await self._get_directory_contents(directory_path)

        # Subdirectories first so numbered-disc folders end up in order.
        for subdir in dir_paths:
            songs.extend(await self._add_directory_to_playlist(subdir))

        songs.extend(file_paths)

        return songs

    def refresh(self):
        """Re-fetch and redisplay the filesystem tree from the root."""
        AsyncUIHelper.run_async_operation(self.load_root_directory, None)
