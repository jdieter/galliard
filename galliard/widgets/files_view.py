import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, Gio  # noqa: E402

from galliard.models import FileItem  # noqa: E402
from galliard.utils.sorting import get_sort_key  # noqa: E402
from galliard.utils.album_art import get_album_art_as_pixbuf  # noqa: E402
from galliard.widgets.async_ui_helper import AsyncUIHelper  # noqa: E402
from galliard.utils.context_menu import ContextMenu  # noqa: E402
from galliard.utils.glib import idle_add_once  # noqa: E402


class FilesView(Gtk.ScrolledWindow):
    """Files tree view for the library"""

    def __init__(self, mpd_client):
        super().__init__()
        self.mpd_client = mpd_client
        self._current_hovered_image = None
        self.last_preview_popover = None

        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Create UI elements
        self.create_ui()

        # Load root items on idle to ensure UI is constructed first
        AsyncUIHelper.run_glib_idle_async(self.load_root_directory)

    def create_ui(self):
        """Create the file browser UI"""
        # Create a list store for our tree items
        self.files_store = Gio.ListStore.new(FileItem)

        # Create tree list model to handle the hierarchy
        self.tree_model = Gtk.TreeListModel.new(
            self.files_store,
            False,  # Passthrough
            False,  # Set autoexpand to False to prevent automatic expansion
            self._create_file_children_model,
        )

        # Create selection model
        self.selection = Gtk.SingleSelection.new(self.tree_model)

        # Create column view
        self.files_tree = Gtk.ColumnView.new(self.selection)
        self.files_tree.set_show_column_separators(False)
        self.files_tree.set_show_row_separators(False)

        # Create factory for file items
        factory = Gtk.SignalListItemFactory.new()
        factory.connect("setup", self._file_item_setup)
        factory.connect("bind", self._file_item_bind)
        factory.connect("unbind", self._file_item_unbind)

        # Create column for files
        column = Gtk.ColumnViewColumn.new("Files", factory)
        column.set_expand(True)
        self.files_tree.append_column(column)

        # Hide the table header
        table_header = self.files_tree.get_first_child()
        if table_header:
            table_header.set_visible(False)

        # Connect signals for handling selection and expansion
        self.selection.connect("selection-changed", self._on_file_selection_changed)

        # Add the tree to the scrolled window
        self.set_child(self.files_tree)

        # Apply CSS for compact rows
        self._apply_css()

    def _apply_css(self):
        """Apply CSS styling to make the tree more compact"""
        # First, make sure the files_tree has a name so we can target it with CSS
        self.files_tree.set_name("files-tree")

        # Create a CSS provider
        css_provider = Gtk.CssProvider()

        # Define the CSS to reduce row height
        css = b"""
        #files-tree {
            /* Reduce the overall padding in the tree */
            padding: 0;
        }

        #files-tree row {
            /* Reduce the vertical padding for each row */
            padding-top: 0px;
            padding-bottom: 0px;
            min-height: 20px; /* Adjust this value to get the desired row height */
        }

        #files-tree cell {
            /* Reduce the vertical padding for each row */
            padding-top: 1px;
            padding-bottom: 1px;
            min-height: 20px; /* Adjust this value to get the desired row height */
        }

        .compact {
            padding-top: 0;
            padding-bottom: 0;
            margin-top: 0;
            margin-bottom: 0;
        }

        #compact-expander {
            /* Make expander button more compact */
            padding-top: 0;
            padding-bottom: 0;
            min-height: 16px;
            min-width: 16px;
        }

        #compact-expander image {
            /* Make the icon inside the button smaller */
            -gtk-icon-size: 12px;
        }
        """

        # Load the CSS
        css_provider.load_from_data(css)

        # Add the CSS provider to the display
        if display := Gdk.Display.get_default():
            Gtk.StyleContext.add_provider_for_display(
                display,
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def _file_item_setup(self, factory, list_item):
        """Setup function for file items"""
        # Create box for the row
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box.set_margin_start(0)
        box.set_margin_end(0)
        box.set_margin_top(0)
        box.set_margin_bottom(0)

        # Expander widget for directories
        expander = Gtk.Button.new_from_icon_name("pan-end-symbolic")
        expander.add_css_class("flat")
        expander.set_visible(False)  # Initially hidden
        expander.set_name("compact-expander")
        box.append(expander)

        # Image for icon or album art
        image = Gtk.Image()
        image.set_size_request(20, 20)
        image.add_css_class("compact")
        box.append(image)

        # Label for file name
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        label.add_css_class("compact")
        box.append(label)

        # Store widgets in list item
        list_item.set_child(box)

        # Store references to widgets for later access
        list_item.image = image
        list_item.label = label
        list_item.expander = expander

        # Connect expander button signal
        expander.connect("clicked", self._on_expander_clicked, list_item)

        # Add context menu support
        gesture_click = Gtk.GestureClick.new()
        gesture_click.set_button(3)  # Right mouse button
        gesture_click.connect("pressed", self._on_file_item_right_click, list_item)
        box.add_controller(gesture_click)

    def _file_item_bind(self, factory, list_item):
        """Bind file item data to widgets"""
        # Get the tree list row
        tree_list_row = list_item.get_item()

        # Get the actual item (FileItem) from the row
        file_item = tree_list_row.get_item()

        if not file_item:
            return

        # Calculate indentation based on depth level
        depth = tree_list_row.get_depth()
        indent_pixels = depth * 24  # 24 pixels per level

        if file_item.is_directory:
            # Set margin_start to handle indentation
            list_item.expander.set_margin_start(indent_pixels)

            # Show/hide expander for directories
            list_item.expander.set_visible(True)

            # Update expander icon based on expanded state
            if file_item.is_directory:
                is_expanded = tree_list_row.get_expanded()
                icon_name = "pan-down-symbolic" if is_expanded else "pan-end-symbolic"
                list_item.expander.set_icon_name(icon_name)
            list_item.image.set_margin_start(0)
        else:
            list_item.expander.set_visible(False)
            list_item.image.set_margin_start(indent_pixels + 26)

        # Handle icon or pixbuf
        if file_item.pixbuf:
            list_item.image.set_from_pixbuf(file_item.pixbuf)
            # Add motion controller for hover effects on album art
            motion_controller = Gtk.EventControllerMotion.new()
            motion_controller.connect("motion", self._on_tree_motion)
            motion_controller.connect("leave", self._on_tree_leave)
            list_item.image.add_controller(motion_controller)
        else:
            list_item.image.set_from_icon_name(file_item.icon_name)

        # Set the label text
        list_item.label.set_text(file_item.name)

        # Store the row for later access
        list_item.tree_list_row = tree_list_row
        file_item.list_item = list_item

    def _file_item_unbind(self, factory, list_item):
        """Clean up when item is unbound"""
        list_item.tree_list_row = None

    def _create_file_children_model(self, file_item):
        """Create model for child items"""
        if not file_item.is_directory:
            return None

        # Create a list store for children
        child_store = Gio.ListStore.new(FileItem)

        if not file_item.children_loaded:
            # Load actual children asynchronously
            AsyncUIHelper.run_async_operation(
                self.load_directory_contents,
                lambda result: self._update_children(file_item, result, child_store),
                file_item.path,
            )

            # Add loading placeholder
            loading_item = FileItem(
                name="Loading...",
                path="",
                icon_name="content-loading-symbolic",
                is_directory=False,
                pixbuf=None,
            )
            child_store.append(loading_item)
        else:
            # Add existing children
            for child in file_item.children:
                child_store.append(child)

        return child_store


    def _update_children(self, parent_item, children, child_store):
        """Update directory with loaded children"""
        parent_item.children = children
        parent_item.children_loaded = True

        # Update the store directly (remove loading placeholder)
        child_store.remove_all()

        # Add all children
        for child in parent_item.children:
            child_store.append(child)

        idle_add_once(self.files_tree.queue_draw)

    async def _get_directory_contents(self, directory):
        dir_contents = await self.mpd_client.async_list_directory(directory)

        # Process directories first, then files
        dir_paths = []
        file_paths = []

        for item in dir_contents:
            if "directory" in item:
                dir_paths.append(item["directory"])
            elif "file" in item:
                file_paths.append(item["file"])

        # Sort items alphabetically
        dir_paths.sort(
            key=lambda path: get_sort_key(path.split("/")[-1] if "/" in path else path)
        )
        file_paths.sort(
            key=lambda path: get_sort_key(path.split("/")[-1] if "/" in path else path)
        )
        return dir_paths, file_paths

    def _is_music_file(self, file_path):
        if any(
            file_path.lower().endswith(ext)
            for ext in [".mp3", ".flac", ".ogg", ".wav", ".aac", ".m4a"]
        ):
            return True
        return False

    async def load_directory_contents(self, directory):
        """Load directory contents and return list of FileItem objects"""
        items = []

        try:
            dir_paths, file_paths = await self._get_directory_contents(directory)

            # Create FileItems for directories
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

                # Try to load album art asynchronously
                AsyncUIHelper.run_async_operation(
                    self._load_directory_art,
                    lambda result, item=file_item: self._update_item_art(item, result),
                    dir_path,
                    task_priority=110,  # Lower priority for album art loading
                )

            # Create FileItems for files
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
            print(f"Error loading directory {directory}: {e}")
            # Add error item
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
        """Load album art for a directory"""
        try:
            dir_contents = await self.mpd_client.async_list_directory(dir_path)
            # Find first audio file in directory
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
                    print(f"Error getting album art for {audio_file}: {e}")
        except Exception as e:
            print(f"Error loading art for directory {dir_path}: {e}")

        return None

    def _update_item_art(self, file_item, pixbuf):
        """Update file item with album art"""
        if pixbuf and file_item.list_item is not None:
            file_item.pixbuf = pixbuf
            file_item.icon_name = None
            file_item.list_item.image.set_from_pixbuf(pixbuf)
            file_item.list_item.image.pixbuf_data = pixbuf

            # Create a motion controller for the image
            motion_controller = Gtk.EventControllerMotion.new()
            motion_controller.connect("motion", self._on_tree_motion)
            motion_controller.connect("leave", self._on_tree_leave)
            file_item.list_item.image.add_controller(motion_controller)

            # Notify model that item has changed
            idle_add_once(self.files_tree.queue_draw)

    def _on_expander_clicked(self, button, list_item):
        """Handle expander button click"""
        tree_list_row = list_item.tree_list_row
        if tree_list_row:
            # Toggle expanded state
            is_expanded = tree_list_row.get_expanded()

            # Only expand if not already expanded
            if not is_expanded:
                # If children aren't loaded yet, we need to load them
                file_item = tree_list_row.get_item()
                if not file_item.children_loaded:
                    # Show loading indicator
                    tree_list_row.set_expanded(True)
                    # Update button icon immediately for better UX
                    button.set_icon_name("pan-down-symbolic")
                    # The children will be loaded by the _create_file_children_model
                else:
                    tree_list_row.set_expanded(True)
                    button.set_icon_name("pan-down-symbolic")
            else:
                # Collapse the row
                tree_list_row.set_expanded(False)
                button.set_icon_name("pan-end-symbolic")

    def _on_file_selection_changed(self, selection, position, n_items):
        """Handle file selection"""
        selected = selection.get_selected_item()
        if not selected:
            return

        file_item = selected.get_item()
        if not file_item:
            return

        if not file_item.is_directory:
            # It's a file - play it
            self.mpd_client.add_to_playlist(file_item.path)
            # Get updated playlist
            playlist = self.mpd_client.get_current_playlist()
            # Play the song that was just added (last in playlist)
            if playlist:
                self.mpd_client.client.play(len(playlist) - 1)

    async def load_root_directory(self):
        """Load the root directory"""
        print("Loading root directory...")

        if not self.mpd_client.is_connected():
            print("MPD client not connected")
            return False

        try:
            # Clear current items
            self.files_store.remove_all()

            # Load directory contents
            items = await self.load_directory_contents("")
            print(f"Loaded {len(items)} items from root directory")

            # Add items to store
            for item in items:
                self.files_store.append(item)

            idle_add_once(self.files_tree.queue_draw)

        except Exception as e:
            print(f"Error loading root directory: {e}")

        return False

    def _on_tree_motion(self, controller, x, y):
        """Handle mouse motion over tree to detect hovering over album art"""
        # Get the widget from the controller
        image = controller.get_widget()

        # Only process images with album art
        if hasattr(image, "pixbuf_data") and image.pixbuf_data:
            # Convert widget coordinates to window coordinates
            widget_position = image.translate_coordinates(self.files_tree, x, y)

            if not widget_position:
                return

            tree_x, tree_y = widget_position

            # Track which image we're hovering over
            if self._current_hovered_image != image:
                self._current_hovered_image = image

            # Show the preview
            self._show_preview(image.pixbuf_data, tree_x, tree_y)

    def _on_tree_leave(self, controller):
        """Handle mouse leaving the tree view"""
        image = controller.get_widget()
        if image == self._current_hovered_image:
            self._hide_preview()

    def _show_preview(self, pixbuf, x, y):
        """Show a preview of the album art at the cursor position"""
        # Create popover if it doesn't exist
        if not self.last_preview_popover:
            self.last_preview_popover = Gtk.Popover()
            self.last_preview_popover.set_autohide(True)

            # Create an image widget for the preview
            self.preview_image = Gtk.Image()
            self.preview_image.set_size_request(150, 150)

            # Add the image to the popover
            self.last_preview_popover.set_child(self.preview_image)
            self.last_preview_popover.set_parent(self.files_tree)

        # Set the pixbuf to the image widget
        self.preview_image.set_from_pixbuf(pixbuf)

        # Position the popover near the cursor but offset to prevent it from hiding the cell
        rect = Gdk.Rectangle()
        rect.x = int(x) + 20  # Offset from cursor
        rect.y = int(y)
        rect.width = 1
        rect.height = 1

        self.last_preview_popover.set_pointing_to(rect)
        self.last_preview_popover.popup()

    def _hide_preview(self):
        """Hide the album art preview popover"""
        self._current_hovered_image = None
        if self.last_preview_popover:
            self.last_preview_popover.popdown()

    def _on_file_item_right_click(self, gesture, n_press, x, y, list_item):
        """Handle right-click on file items"""
        tree_list_row = list_item.tree_list_row
        if not tree_list_row:
            return

        file_item = tree_list_row.get_item()
        if not file_item or not file_item.is_directory:
            return

        # Create menu items
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
            list_item.get_child(),  # Parent widget
            menu_items,  # Menu items
            "row",  # Action group name
            x,  # X position
            y,  # Y position
        )

    def _on_context_menu_action(self, file_item, replace):
        """Handle context menu actions"""
        # Launch appropriate async operation based on the selection
        AsyncUIHelper.run_async_operation(
            self.add_path_to_playlist, None, file_item.path, replace
        )

    async def add_path_to_playlist(self, file_path, replace=False):
        """Add a single file to the playlist"""
        try:
            # Clear playlist if replacing
            if replace:
                await self.mpd_client.async_clear_playlist()

            paths = await self._add_directory_to_playlist(file_path)
            await self.mpd_client.async_add_songs_to_playlist(paths)
            if replace:
                await self.mpd_client.async_play(0)
        except Exception as e:
            print(f"Error adding file to playlist {file_path}: {e}")

    async def _add_directory_to_playlist(self, directory_path):
        """Add all music files from a directory to the playlist in order"""
        songs = []

        # Get all subdirectories (albums) and files
        dir_paths, file_paths = await self._get_directory_contents(directory_path)

        # Add songs from any subdirectories first
        for subdir in dir_paths:
            songs.extend(await self._add_directory_to_playlist(subdir))

        # Get detailed information for each file to sort by track number
        songs.extend(file_paths)

        return songs

    def refresh(self):
        """Refresh the file view"""
        AsyncUIHelper.run_async_operation(self.load_root_directory, None)
