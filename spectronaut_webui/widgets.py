import asyncio
import re
from nicegui import ui, events
from pathlib import Path
from typing import List, Set

class LocalPicker(ui.dialog):
    def __init__(self, directory: str = '~', *, 
                 multiple: bool = False, 
                 show_files: bool = True, 
                 on_select=None,
                 default_selection: str = ''):
        super().__init__()
        self.path = Path(directory).expanduser()
        self.multiple = multiple
        self.show_files = show_files
        self.on_select = on_select
        # default_selection: empty string means no filter
        self.current_filter = default_selection if default_selection else ''
        #multiple patterns
        if self.current_filter.find('|') != -1:
            pattern_str = '|'.join([f'{re.escape(p.strip())}' for p in self.current_filter.split('|')])
            self.regex_filter = re.compile(f'(.+)?({pattern_str})(.+)?', re.IGNORECASE)
        else:
            self.regex_filter = re.compile(f'(.+)?{re.escape(self.current_filter)}(.+)?', re.IGNORECASE)\
                  if self.current_filter else re.compile(r'.+?')
        
        # Track shift key state via a UI-level event
        self.shift_is_held = False
        
        self.selected: Set[str] = set() # Store as strings for JSON safety
        self.items: List[Path] = []
        self.last_clicked_index: int = None

        with self, ui.card().classes('w-[800px] h-[700px] column no-wrap'):
            # Detect Shift key globally while dialog is open
            ui.keyboard(on_key=self._handle_key)

            # Header: title, path display and controls
            ui.label('File/Folder Selector').classes('text-h6')
            ui.label('Hold SHIFT to select/unselect ranges').classes('text-caption text-blue')

            with ui.row().classes('w-full items-center gap-2'):
                # path_input lets the user type a path;
                self.path_input = ui.input(label='Path', value=str(self.path)).classes('grow text-xs text-grey-6 truncate')\
                    .on('keydown.enter', lambda e: self._set_path(self.path_input.value))
                ui.button('Create new', icon='create_new_folder', on_click=self._create_new_dir).props('icon')
                
            # Filter and show-files controls
            with ui.row().classes('items-center q-mt-sm gap-2'):
                ui.label('Filter:').classes('text-sm')
                # free-text filter where user can enter extension or pattern (e.g. .csv)
                self.filter_input = ui.input(value='' if self.current_filter == 'All Files' else self.current_filter,
                                             placeholder='any part of name').classes('w-1/3')\
                                                .on('keydown.enter', lambda e: self._set_filter(self.filter_input.value))
                self.show_files_checkbox = ui.checkbox('Show files', value=self.show_files,
                                                      on_change=lambda e: self._set_show_files(e.value))

            with ui.scroll_area().classes('col grow border rounded q-mt-sm'):
                self.list_container = ui.list().props('dense separtor')
                self.update_list()

            # Footer: selection count, quick actions and confirm/cancel
            with ui.row().classes('w-full justify-between mt-4 items-center'):
                ui.label().bind_text_from(self, 'selected', backward=lambda s: f'{len(s)} selected')
                with ui.row():
                    ui.button('Select All', on_click=self._select_all).props('flat')
                    ui.button('Clear', on_click=self._clear_selection).props('flat')
                    ui.button('Cancel', on_click=self.close).props('flat')
                    ui.button('Confirm', on_click=self._handle_confirm).props('primary')

    def _handle_key(self, e: events.KeyEventArguments):
        """Track shift key globally."""
        if e.key.shift:
            self.shift_is_held = e.action.keydown

    def _set_filter(self, value: str):
        """Set current filter (e.g. '.csv' or substring) and refresh list."""
        v = (value or '').strip()
        # empty string means no filter
        self.current_filter = v

        if self.current_filter.find('|') != -1:
            pattern_str = '|'.join([f'{re.escape(p.strip())}' for p in self.current_filter.split('|')])
            self.regex_filter = re.compile(f'(.+)?({pattern_str})(.+)?', re.IGNORECASE)
        else:
            self.regex_filter = re.compile(f'(.+)?{re.escape(self.current_filter)}(.+)?', re.IGNORECASE)\
                 if self.current_filter else re.compile(r'.+?')

        self.update_list()

    def _create_new_dir(self):
        """Ask for a directory name, create it inside the current path and navigate into it."""
        with ui.dialog() as dlg, ui.card().classes('q-pa-md'):
            ui.label('Create new directory').classes('text-lg q-mb-sm')
            name_input = ui.input(label='Directory name', placeholder='Enter new directory name').classes('w-full')

            def _on_create(*_):
                name = (name_input.value or '').strip()
                if not name:
                    ui.notify('Please enter a directory name', type='warning')
                    return
                new_path = self.path.joinpath(name)
                try:
                    new_path.mkdir(parents=False, exist_ok=False)
                except FileExistsError:
                    ui.notify('Directory already exists', type='negative')
                    return
                except Exception as e:
                    ui.notify(f'Error creating directory: {e}', type='negative')
                    return

                # refresh list to show contents of new directory
                self.update_list()
                dlg.close()

            with ui.row().classes('justify-end gap-2 q-mt-md'):
                ui.button('Create', on_click=_on_create)
                ui.button('Cancel', on_click=dlg.close)

        dlg.open()

    def _set_show_files(self, value: bool):
        self.show_files = bool(value)
        self.update_list()

    def _select_all(self):
        for p in self.items:
            self.selected.add(str(p))
        self._refresh_UI()

    def _clear_selection(self):
        self.selected.clear()
        self._refresh_UI()

    def _checkbox_toggled(self, index: int, checked: bool):
        """Handle checkbox toggles. Support shift-range selection when appropriate."""
        if self.multiple and self.shift_is_held and self.last_clicked_index is not None:
            start, end = sorted([self.last_clicked_index, index])
            if checked:
                for i in range(start, end + 1):
                    self.selected.add(str(self.items[i]))
            else:
                for i in range(start, end + 1):
                    self.selected.discard(str(self.items[i]))
        else:
            p_str = str(self.items[index])
            if checked:
                self.selected.add(p_str)
            else:
                self.selected.discard(p_str)
        self.last_clicked_index = index
        self._refresh_UI()

    def _label_clicked(self, index: int):
        """Clicking the label opens folders; files are not navigated by label click.

        Selection is done via the checkbox, not by clicking the label.
        """
        path = self.items[index]
        if path.is_dir():
            self.path = path
            self.path_input.value = str(self.path)
            self.last_clicked_index = None
            self.update_list()

    def update_list(self):
        # Non-blocking update: show loading indicator and spawn async worker
        self.list_container.clear()
        with self.list_container:
            with ui.row().classes('items-center justify-center q-pa-md'):
                # spinner: shows while items are being collected
                try:
                    ui.spinner()
                except Exception:
                    # fallback: simple label if spinner not available
                    ui.label('Loading...')

        # schedule the async update (collect files in a thread, then rebuild UI)
        try:
            asyncio.create_task(self._update_list_async())
        except RuntimeError:
            # no running event loop — fallback to synchronous update
            self._update_list_sync()
        
    def _refresh_UI(self):
        self.list_container.clear()
        with self.list_container:
            # Go Up item
            with ui.item(on_click=lambda: self._item_clicked(self.path.parent)).props('clickable'):
                with ui.item_section().props('avatar'):
                    ui.icon('arrow_upward')
                ui.label('..')

            for index, p in enumerate(self.items):
                p_str = str(p)
                is_selected = p_str in self.selected

                # Build item row: checkbox side for selection, icon, and clickable label for folders
                with ui.item().classes('bg-blue-100' if is_selected else ''):
                    # side: selection checkbox (separate selection control)
                    with ui.item_section().props('side'):
                        ui.checkbox(value=is_selected, on_change=lambda e, i=index: self._checkbox_toggled(i, e.value))

                    # avatar: folder/file icon
                    with ui.item_section().props('avatar'):
                        ui.icon('folder' if p.is_dir() else 'insert_drive_file',
                                color='orange' if p.is_dir() else 'blue-grey')

                    # main label: clicking it opens folders; files do not navigate
                    with ui.item_section():
                        # use a flat button for the label so we can attach a click handler
                        ui.button(p.name, on_click=lambda e, i=index: self._label_clicked(i)).props('flat').classes('text-sm text-left')

    def _collect_raw_items(self) -> List[Path]:
        raw_items: List[Path] = []
        for item in self.path.iterdir():
            try:
                item.is_dir()  # attempt to access to trigger PermissionError if any
                raw_items.append(item)
            except PermissionError:
                print("PermissionError accessing item:", item)
                # skip this item
        return raw_items
    
    def _passes_filter(self, p: Path) -> bool:
            if p.is_dir():
                return True
            elif p.is_file():
                if not self.current_filter:
                    return True if self.show_files else False
                name = p.name.lower()
                if self.regex_filter.match(name):
                    return True
            return False

    def _update_list_sync(self):
        # Synchronous fallback (same logic as the async variant)
        raw_items = self._collect_raw_items()
        self.items = [p for p in sorted(raw_items, key=lambda p: (not p.is_dir(), p.name.lower())) if self._passes_filter(p)]
        self._refresh_UI()

    async def _update_list_async(self):
        # allow the loading UI to render
        await asyncio.sleep(0)
        # collect items in a thread to avoid blocking the event loop
        try:
            raw_items = await asyncio.to_thread(self._collect_raw_items)
        except Exception as e:
            print('Error collecting items:', e)
            raw_items = []

        self.items = [p for p in sorted(raw_items, key=lambda p: (not p.is_dir(), p.name.lower())) if self._passes_filter(p)]
        self._refresh_UI()

    def _item_clicked(self, path: Path):
        self.path = path
        self.path_input.value = str(self.path)
        self.last_clicked_index = None
        self.update_list()

    def _handle_confirm(self):
        if not self.multiple and len(self.selected) > 1:
            # In single-selection mode, only keep the first selected item
            ui.notification('Please select only one item', color='red')
            return
        if self.on_select:
            self.on_select(list(self.selected))
        self.close()
    
    def _set_path(self, value: str):
        """Set path from user-edited input and refresh list."""
        p = Path(value).expanduser()
        if p.exists() and p.is_dir():
            self.path = p
            self.last_clicked_index = None
            self.update_list()
        else:
            self.list_container.clear()
            with self.list_container:
                ui.label('Invalid path').classes('text-red')
                