import asyncio
import logging
from pathlib import Path
from tempfile import mkdtemp
from shutil import copy
from typing import List
from nicegui import app, ui
from starlette.formparsers import MultiPartParser
from .config import load_config
from . import helpers
from .widgets import LocalPicker

# large file upload support
MultiPartParser.spool_max_size = 1024 * 1024 * 100  # 100 MB

# --- Global constants ---
global_temp_directory = mkdtemp()
_config = None

#logging setup
class LogElementHandler(logging.Handler):
    """A logging handler that emits messages to a log element."""

    level_format = {
        logging.DEBUG: 'text-grey',
        logging.INFO: 'text-green',
        logging.WARNING: 'text-orange',
        logging.ERROR: 'text-red',
        logging.CRITICAL: 'text-red font-bold'
    }

    def __init__(self, element: ui.log, level: int = logging.NOTSET) -> None:
        self.element = element
        super().__init__(level)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            splits = [msg[i:i+160] for i in range(0, len(msg), 160)]
            self.element.push(f'{"\n".join(splits)}', classes=self.level_format.get(record.levelno, ''))
            # after pushing a message, instruct the browser to scroll the log area to the bottom
            try:
                #some JS madness
                ui.run_javascript("(function(){el = document.getElementById('terminal_log');\
                                  if(!el) return;\
                                  sc = el.querySelector('.q-scrollarea__content') || el.querySelector('pre') || el;\
                                  sc.scrollTop = sc.scrollHeight;})()")
            except Exception:
                # ignore JS invocation errors
                pass
        except Exception:
            self.handleError(record)

log = logging.getLogger()
logging.basicConfig(format='%(asctime)s [%(name)s] %(levelname)s: %(message)s', level=logging.DEBUG,
                    datefmt='%Y-%m-%d %H:%M:%S')

# Load configuration from file or use defaults
_config = load_config()
SPECTRONAUT = _config['spectronaut_command']
DEFAULT_DIR = _config['default_dir']
SPECTRONAUT_KEY = _config['spectronaut_key']
PORT = _config['port']

def check_type(path: Path) -> str:
    if path.is_dir() and path.suffix.lower() == '.d':
        return 'Bruker D'
    elif path.is_dir():
        return 'Folder'
    elif path.is_file() and path.suffix.lower() == '.raw':
        return 'Thermo Raw'
    elif path.is_file() and ''.join(path.suffixes[-2:]).lower() == '.d.zip':
        return 'Bruker D Zip'
    else:
        return 'File'

def add_to_datafiles(paths: List[str], datafiles, table):
    added = 0
    if len(paths) > 0:
        paths.sort(key=lambda r: Path(r).name or r)

    for p in paths:
        if any(d['path'] == p for d in datafiles):
            continue
        path_obj = Path(p)
        datafiles.append({
            'name': path_obj.name or str(path_obj),
            'type': check_type(path_obj),
            'path': str(path_obj),
            'replicate': '',
            'condition': '',
            'fraction': '',
            'reference': False,
        })
        added += 1
    
    try:
        table.options['rowData'] = datafiles
    except Exception:
        pass
    table.update()
    ui.notify(f'Added {added} items', type='positive')

def open_file_picker(field, extension: str = ''):
    def _on_select(paths: List[str]):
        if not paths:
            ui.notify('Nothing selected', type='negative')
            return
        path_obj = Path(paths[0])
        if not path_obj.is_file():
                ui.notify('Selected path is not a file', type='negative')
                return
        field.value = str(path_obj)
    
    picker = LocalPicker(directory=DEFAULT_DIR, multiple=False, show_files=True,
                            default_selection=extension, on_select=_on_select)
    try:
        picker.open()
    except Exception:
        pass

def open_dirw_picker(field):
    def _on_select(paths: List[str]):
        if not paths:
            ui.notify('Nothing selected', type='negative')
            return
        try:
            path_obj = Path(paths[0])
            if not path_obj.is_dir():
                ui.notify('Selected path is not a directory', type='negative')
                return
            path_obj.joinpath('test_permission.tmp').touch()
            path_obj.joinpath('test_permission.tmp').unlink()
        except PermissionError:
            ui.notify('Permission error accessing selected path', type='negative')
            return
        field.value = paths[0]

    picker = LocalPicker(directory=DEFAULT_DIR, multiple=False, show_files=False,
                            on_select=_on_select)
    try:
        picker.open()
    except Exception:
        pass

def handle_upload(field):
    """Open a dialog with an upload control, save the uploaded file to a temp
    directory and set the input `field.value` to the saved path.
    """
    dlg = ui.dialog()
    with dlg:
        async def _on_upload(e):
            file = getattr(e, 'file', None)
            if not file:
                ui.notify('No file received', type='negative')
                return
            filename = getattr(file, 'name', None)
            if not filename:
                ui.notify('Cannot determine filename', type='negative')
                return
            
            save_path = Path(global_temp_directory).joinpath(filename)
            try:
                await file.save(save_path)
            except Exception as exc:
                ui.notify(f'Error saving uploaded file: {exc}', type='negative')
                return
            field.value = str(save_path)
            dlg.close()

        ui.upload(label='Select a file', auto_upload=True, max_files=1, on_upload=_on_upload)

    dlg.open()

@helpers.track_subprocess_cleanup
async def process_direct(output_widget, progress_widget, args) -> bool:
    """Run DirectDIA workflow"""
    if not args['datafiles']:
        ui.notify('No files to process', type='negative')
        return

    if args['output_directory'] == '':
        ui.notify('Output directory not specified', type='negative')
        return 
    
    if not Path(args['output_directory']).exists():
        Path(args['output_directory']).mkdir(parents=True, exist_ok=True)

    if args['properties_file'] == '':
        ui.notify('Properties file not specified', type='negative')
        return
    
    if args['fasta_file'] == '':
        ui.notify('FASTA file not specified', type='negative')
        return
    
    if args['experiment_name'] == '':
        args['experiment_name'] = Path(args['datafiles'][0]['name']).stem

    data_folder = Path(args['output_directory']).joinpath('data')
    data_folder.mkdir(parents=True, exist_ok=True)
    params_folder = Path(args['output_directory']).joinpath('params')
    params_folder.mkdir(parents=True, exist_ok=True)

    if Path(args['properties_file']).exists():
        new_path = Path(params_folder).joinpath(Path(args['properties_file']).name)
        copy(Path(args['properties_file']), new_path)
        args['properties_file'] = new_path
    
    if Path(args['fasta_file']).exists():
        new_path = Path(params_folder).joinpath(Path(args['fasta_file']).name)
        copy(Path(args['fasta_file']), new_path)
        args['fasta_file'] = new_path

    if args['go_file'] != '' and Path(args['go_file']).exists():
        new_path = Path(params_folder).joinpath(Path(args['go_file']).name)
        copy(Path(args['go_file']), new_path)
        args['go_file'] = new_path  

    if args['report_file'] != '' and Path(args['report_file']).exists():
        new_path = Path(params_folder).joinpath(Path(args['report_file']).name)
        copy(Path(args['report_file']), new_path)
        args['report_file'] = new_path  
    
    if args['mod_repository'] != '' and Path(args['mod_repository']).exists():
        new_path = Path(params_folder).joinpath(Path(args['mod_repository']).name)
        copy(Path(args['mod_repository']), new_path)
        args['mod_repository'] = new_path
    
    if args['enzyme_database'] != '' and Path(args['enzyme_database']).exists():
        new_path = Path(params_folder).joinpath(Path(args['enzyme_database']).name)
        copy(Path(args['enzyme_database']), new_path)
        args['enzyme_database'] = new_path

    output_widget.clear()

    if not helpers.validate_filetable(args['datafiles']):
        log.error('Invalid file table: Mixed or unsupported file types.')
        return

    try:
        ui.notify('Preparing data files...', type='info')
        await helpers.prepare_datafiles_async(args['datafiles'], data_folder, log, progress_widget)
    except asyncio.CancelledError:
        log.warning('Processing cancelled by user')
        return
    except Exception as e:
        log.error(f'Error preparing data files: {e}')
        return

    try:
        condition_file = Path(params_folder).joinpath(f'{args["experiment_name"]}_condition.tsv')
        ui.notify('Creating condition file...')
        await asyncio.to_thread(helpers.write_conditon_file, args['datafiles'], str(condition_file), log)
        args['condition_file'] = condition_file
        log.debug(f'Wrote condition file to: {condition_file}')
    except Exception as e:
        log.error(f'Error writing condition file: {e}')
        return

    try:
        args_list = await asyncio.to_thread(helpers.get_full_args, args)
        log.debug(f'Got full arguments: {len(args_list)} included')
    except Exception as e:
        log.error(f'Cannot get arguments: {e}')
        return
    
    log.info('Activating Spectronaut')
    result = await helpers.run_cmd(SPECTRONAUT + ['activate', SPECTRONAUT_KEY], log)
    if result:
        log.info('Spectronaut activated successfully')
    else:
        log.error('Cannot activate Spectronaut, see detailed log')
        return

    success = True
    log.info('Launching Spectronaut')
    result = await helpers.run_cmd(SPECTRONAUT + args_list, log)
    success = success and result
    if result:
        log.info('Spectronaut exited successfully')
    else:
        log.error('Processing failed, see detailed log')
    
    log.info('Deactivating Spectronaut')
    result = await helpers.run_cmd(SPECTRONAUT + ['deactivate'], log)
    if result:
        log.info('Spectronaut deactivated')
    else:
        log.error('Cannot deactivate Spectronaut, see detailed log')
    
    return success

@helpers.track_subprocess_cleanup
async def process_convert(output_widget, progress_widget, args):
    """Run Convert workflow"""
    if not args['datafiles']:
        ui.notify('No files to process', type='negative')
        return

    if args['output_directory'] == '':
        ui.notify('Output directory not specified', type='negative')
        return
    
    if not Path(args['output_directory']).exists():
        Path(args['output_directory']).mkdir(parents=True)

    data_folder = Path(args['output_directory']).joinpath('data')
    data_folder.mkdir(parents=True, exist_ok=True)
    params_folder = Path(args['output_directory']).joinpath('params')
    params_folder.mkdir(parents=True, exist_ok=True)

    if args['properties_file'] != '' and Path(args['properties_file']).exists():
        new_path = Path(params_folder).joinpath(Path(args['properties_file']).name)
        copy(Path(args['properties_file']), new_path)
        args['properties_file'] = new_path
    
    output_widget.clear()

    try:
        ui.notify('Preparing data files...', type='info')
        await helpers.prepare_datafiles_async(args['datafiles'], data_folder, log, progress_widget)
    except asyncio.CancelledError:
        log.warning('Processing cancelled by user')
        return
    except Exception as e:
        log.error(f'Error preparing data files: {e}')
        return
    
    args.pop('protocol')
    
    try:
        args_list = await asyncio.to_thread(helpers.get_args, args)
        log.debug(f'Got base arguments: {len(args_list)} included')
    except Exception as e:
        log.error(f'Cannot get arguments: {e}')
        return

    log.info('Activating Spectronaut')
    result = await helpers.run_cmd(SPECTRONAUT + ['activate', SPECTRONAUT_KEY], log)
    if result:
        log.info('Spectronaut activated successfully')
    else:
        log.error('Cannot activate Spectronaut, see detailed log')
        return

    total = len(args['datafiles'])
    log.info(f'Converting {total} files')
    progress_widget.visible = True
    progress_widget.value = 0
    success = True
    for i in range(total):
        file_path = Path(args['datafiles'][i]['path'])
        result = await helpers.run_cmd(SPECTRONAUT + ['convert', '-i', file_path] + args_list, log)
        success = success and result
        if result:
            log.info(f'[{i + 1}|{total}] Converted successfully')
        else:
            log.error('Processing failed, see detailed log')
        
        progress_widget.value = (i + 1) / total
    
    progress_widget.visible = False
    
    log.info('Deactivating Spectronaut')
    result = await helpers.run_cmd(SPECTRONAUT + ['deactivate'], log)
    if result:
        log.info('Spectronaut deactivated')
    else:
        log.error('Cannot deactivate Spectronaut, see detailed log')
    
    return success

# --- UI LAYER ---
columnDefs = [
    {'headerName': 'Name', 'field': 'name', 'align': 'left', 'filter': 'agTextColumnFilter'},
    {'headerName': 'Type', 'field': 'type', 'align': 'left', 'filter': 'agTextColumnFilter'},
    {'headerName': 'Absolute Path', 'field': 'path', 'align': 'left', 'hide': True},
    {'headerName': 'Reference', 'field': 'reference', 'align': 'center', 'editable': True,
     'cellRenderer': 'agCheckboxCellRenderer'},
    {'headerName': 'Condition', 'field': 'condition', 'align': 'center', 'editable': True},
    {'headerName': 'Replicate', 'field': 'replicate', 'align': 'center', 'editable': True},
    {'headerName': 'Fraction', 'field': 'fraction', 'align': 'center', 'editable': True},
]

#root element
def root():
    button_style = 'px-4 py-2 rounded-md bg-blue-500 text-white hover:bg-blue-700 transition-colors text-lg font-semibold'
    with ui.row().classes('w-full q-pa-md bg-blue-100 gap-4 items-center'):
        ui.label('Spectronaut UCloud GUI').classes('text-xl font-bold')
        with ui.row().classes('gap-2'):
            ui.link('Info', '/').classes(button_style)
            ui.link('Convert', '/convert').classes(button_style)
            ui.link('Combine', '/combine').classes(button_style)
            ui.link('DirectDIA', '/direct').classes(button_style)
            ui.link('DIA', '/dia').classes(button_style)
        ui.space()
        ui.button('Close', icon='power_settings_new', on_click=lambda: app.shutdown())

    ui.sub_pages({'/': info_page,
                  '/convert': convert_page,
                  '/combine': combine_page,
                  '/direct': directdia_page,
                  '/dia': dia_page}).classes('w-full')

def info_page():
    """Info page - starting page."""
    ui.markdown('''
    ## Spectronaut UCloud GUI

    This application helps you to setup the search using Spectronaut in UCloud 
    environment.
                
    Use the navigation bar at the top to switch between different functionalities.
                
    Each page has parameter tabs where you can select processing parameters, input files,
    and their metadata.
    
    Click "Start Processing" on the  the selected items.

    Processing log will be displayed in the Output tab.
    ''').classes('q-pa-md')

def convert_page():
    """Convert workflow page."""

    datafiles: List[dict] = []
    table = None
    running_task = {'task': None}

    with ui.tabs().classes('w-full') as tabs:
        param_tab = ui.tab('Parameters')
        output_tab = ui.tab('Output')

    with ui.tab_panels(tabs, value=param_tab).classes('w-full'):
        with ui.tab_panel(param_tab):
            def open_D_picker():
                picker = LocalPicker(directory=DEFAULT_DIR, multiple=True, show_files=False,
                                    on_select=lambda paths: add_to_datafiles(paths, datafiles, table))
                try:
                    picker.open()
                except Exception:
                    pass

            def open_raw_picker():
                picker = LocalPicker(directory=DEFAULT_DIR, multiple=True, show_files=True,
                                    default_selection='.raw', on_select=lambda paths: add_to_datafiles(paths, datafiles, table))
                try:
                    picker.open()
                except Exception:
                    pass
            
            def open_Dzip_picker():
                picker = LocalPicker(directory=DEFAULT_DIR, multiple=True, show_files=True,
                                    default_selection='.d.zip', on_select=lambda paths: add_to_datafiles(paths, datafiles, table))
                try:
                    picker.open()
                except Exception:
                    pass

            async def _delete_selected(*_):
                """Delete selected rows from the datafiles list and update the table."""
                rows = None
                try:
                    rows = await table.get_selected_rows()
                except Exception:
                    rows = None

                targets = set()
                if rows:
                    for r in rows:
                        if isinstance(r, dict) and r.get('path'):
                            targets.add(r.get('path'))

                if not targets:
                    ui.notify('No rows selected', type='negative')
                    return

                initial_count = len(datafiles)
                datafiles[:] = [d for d in datafiles if d.get('path') not in targets]

                try:
                    table.options['rowData'] = datafiles
                except Exception:
                    pass
                table.update()
                deleted_count = initial_count - len(datafiles)
                ui.notify(f'Deleted {deleted_count} items', type='positive')
            
            async def _clear_table(*_):
                """Clear all entries from the datafiles list and update the table."""
                if not datafiles:
                    ui.notify('Data table is already empty', type='warning')
                    return
                datafiles.clear()
                try:
                    table.options['rowData'] = datafiles
                except Exception:
                    pass
                table.update()
                ui.notify('Cleared all items from the data table', type='positive')

            columnDefsNew = [e.copy() for e in columnDefs]
            for c_def in columnDefsNew[3:]:
                c_def['hide'] = True
            
            with ui.row().classes('q-pa-md gap-4'):
                ui.button('Add Bruker D', icon='add', on_click=open_D_picker)
                ui.button('Add Thermo Raw', icon='add', on_click=open_raw_picker)
                ui.button('Add zipped Bruker D', icon='add', on_click=open_Dzip_picker)

            with ui.row().classes('w-full q-pa-md gap-2'):
                table = ui.aggrid({'columnDefs': columnDefsNew, 'rowData': datafiles,
                                        'rowSelection': {'mode': 'multiRow'}}).classes('h-128')
                
                ui.button('Delete selected', on_click=_delete_selected).tooltip('Delete selected entries from the data table')
                ui.button('Clear all', on_click=_clear_table).tooltip('Clear all entries from the data table')
            
            with ui.row().classes('w-full q-pa-md gap-2 items-center'):
                prop_input = ui.input(label='Settings file', placeholder='Enter settings file path here').classes('grow')
                ui.button('Select', icon='file_open', on_click=lambda _: open_file_picker(prop_input, '.prop|.txt|.json'))
                ui.button('Upload', icon='file_upload', on_click=lambda _: handle_upload(prop_input))
                
            with ui.row().classes('w-full q-pa-md gap-2 items-center'):
                output_dir = ui.input(label='Output Directory', placeholder='Enter output directory here').classes('grow')
                ui.button('Select', icon='folder_open', on_click=lambda _: open_dirw_picker(output_dir))
            
            with ui.expansion('Advanced options').classes('w-full'):
                with ui.row().classes('w-full q-pa-md gap-2 items-center'):
                    temp_dir = ui.input(label='Temp Directory', placeholder='Enter temporary directory here or leave empty for default one').classes('grow')
                    ui.button('Select', icon='folder_open', on_click=lambda _: open_dirw_picker(temp_dir))

                with ui.row().classes('w-full q-pa-md gap-2 items-center'):
                    mark_verbose = ui.checkbox('Verbose output')
                    mark_segment = ui.checkbox('Segmented dia-PASEF (beta)')
                    mark_error = ui.checkbox('Terminate on error')

            with ui.row().classes('q-pa-md'):        
                start_button = ui.button('Start Processing', color='primary')
                # Run the processing coroutine inside the UI slot so it can safely
                # perform UI updates (avoids "slot stack is empty" runtime error).
                async def _on_start_click(*_):
                    args = {
                        'protocol': 'convert',
                        'properties_file': prop_input.value,
                        'output_directory': output_dir.value,
                        'temp_directory': temp_dir.value,
                        'verbose': mark_verbose.value,
                        'segmented': mark_segment.value,
                        'error_term': mark_error.value,
                        'datafiles': datafiles,
                    }

                    tabs.set_value('Output')
                    start_button.disable()
                    abort_button.enable()
                    ok.visible = False
                    not_ok.visible = False

                    # Create and store the task so it can be cancelled
                    running_task['task'] = asyncio.current_task()
                    try:
                        rc = await process_convert(terminal_output, progress, args)
                        if rc:
                            ok.visible = True
                            not_ok.visible = False
                        else:
                            ok.visible = False
                            not_ok.visible = True
                    except asyncio.CancelledError:
                        log.warning('Processing aborted by user')
                        ok.visible = False
                        not_ok.visible = True
                    finally:
                        running_task['task'] = None
                        start_button.enable()
                        abort_button.disable()
                        if terminate.value:
                            app.shutdown()

                start_button.on('click', _on_start_click)

        with ui.tab_panel(output_tab):
            ui.label('Console Output').classes('text-lg font-bold q-mt-lg')
            terminal_output = ui.log().props('id="terminal_log"').classes('w-full font-mono h-128')
            progress = ui.linear_progress(show_value=False).classes('w-full')
            progress.visible = False
            with ui.row().classes('w-full q-pa-md gap-2 items-center') as ok:
                ui.icon('check_circle', color='green').classes('text-5xl')
                ui.label('Success').classes('text-green text-xl')
            with ui.row().classes('w-full q-pa-md gap-2 items-center') as not_ok:
                ui.icon('error', color='red').classes('text-5xl')
                ui.label('Error').classes('text-red text-xl')
            ok.visible = False
            not_ok.visible = False

            with ui.row().classes('w-full q-pa-md gap-2'):
                abort_button = ui.button('Abort', color='negative', icon='stop')
                abort_button.disable()
                terminate = ui.checkbox('Terminate the app when processing is done')
                terminate.value = False
                
                async def _on_abort_click(*_):
                    if running_task['task'] is not None:
                        running_task['task'].cancel()
                        ui.notify('Aborting...', type='warning')
                    else:
                        ui.notify('No processing running', type='info')
                
                abort_button.on('click', _on_abort_click)
                        
            console = LogElementHandler(terminal_output)
            console.setLevel(logging.INFO)
            log.addHandler(console)
            ui.context.client.on_disconnect(lambda: log.removeHandler(console))

def combine_page():
    """Combine workflow page."""
    ui.label('Coming soon').classes('q-pa-md')

def directdia_page():
    """DirectDIA workflow page."""
    
    datafiles: List[dict] = []
    table = None
    running_task = {'task': None}  # Store the currently running coroutine task

    with ui.tabs().classes('w-full') as tabs:
        param_tab = ui.tab('Parameters')
        output_tab = ui.tab('Output')

    with ui.tab_panels(tabs, value=param_tab).classes('w-full'):
        with ui.tab_panel(param_tab):
            def open_D_picker():
                picker = LocalPicker(directory=DEFAULT_DIR, multiple=True, show_files=False,
                                    on_select=lambda paths: add_to_datafiles(paths, datafiles, table))
                try:
                    picker.open()
                except Exception:
                    pass

            def open_raw_picker():
                picker = LocalPicker(directory=DEFAULT_DIR, multiple=True, show_files=True,
                                    default_selection='.raw', on_select=lambda paths: add_to_datafiles(paths, datafiles, table))
                try:
                    picker.open()
                except Exception:
                    pass
            
            def open_Dzip_picker():
                picker = LocalPicker(directory=DEFAULT_DIR, multiple=True, show_files=True,
                                    default_selection='.d.zip', on_select=lambda paths: add_to_datafiles(paths, datafiles, table))
                try:
                    picker.open()
                except Exception:
                    pass
            
            def _on_cell_value_changed(event):
                """Update internal datafiles when a cell is edited in the grid."""
                data = None
                try:
                    data = event.args['data']
                except Exception:
                    ui.notify('Error extracting data from event', type='negative')

                if not data:
                    return
                
                column = event.args['colId']
                for d in datafiles:
                    if d.get('path') == data.get('path'):
                        if column in data:
                            d[column] = data[column]
                        break

            async def _open_condition_dialog(*_):
                await _apply_value_to_selected('condition', 'Condition', 'Condition to apply')
            
            async def _open_fraction_dialog(*_):
                await _apply_value_to_selected('fraction', 'Fraction', 'Fraction to apply')
            
            async def _assign_replicates(*_):
                """Assign replicate numbers (1,2,3,...) to rows with the same condition and fraction."""
                groups = {(d['condition'], d['fraction']): 1 for d in datafiles}
                for d in datafiles:
                    entry = groups.get((d['condition'], d['fraction']), None)
                    if entry is not None:
                        d['replicate'] = str(entry)
                        groups[(d['condition'], d['fraction'])] += 1

                try:
                    table.options['rowData'] = datafiles
                except Exception:
                    pass
                table.update()
                ui.notify(f'Assigned replicates to {len(groups)} groups', type='positive')
            
            async def _apply_value_to_selected(column: str, title: str, placeholder: str):
                """Open a small dialog to enter a string and apply it to the selected rows."""
                rows = None
                try:
                    rows = await table.get_selected_rows()
                except Exception:
                    rows = None

                targets = set()
                if rows:
                    for r in rows:
                        if isinstance(r, dict) and r.get('path'):
                            targets.add(r.get('path'))

                if not targets:
                    ui.notify('No rows selected', type='negative')
                    return

                with ui.dialog() as dlg, ui.card().classes('q-pa-md'):
                    async def _on_confirm(*_):
                        val = input_widget.value
                        if not val:
                            ui.notify(f'Enter a {title} value first', type='warning')
                            return
                        
                        for d in datafiles:
                            if d.get('path') in targets:
                                d[column] = val

                        try:
                            table.options['rowData'] = datafiles
                        except Exception:
                            pass
                        table.update()
                        ui.notify(f'Applied {title} "{val}" to {len(targets)} rows', type='positive')
                        dlg.close()

                    with ui.row().classes('q-pa-sm gap-2'):
                        ui.label(f'Select {title} to apply').classes('text-lg')
                        input_widget = ui.input('', placeholder=placeholder).classes('w-full')
                    with ui.row().classes('justify-end gap-2 q-mt-md'):
                        ui.button('Confirm', on_click=_on_confirm)
                        ui.button('Cancel', on_click=dlg.close)

                dlg.open()

            async def _delete_selected(*_):
                """Delete selected rows from the datafiles list and update the table."""
                rows = None
                try:
                    rows = await table.get_selected_rows()
                except Exception:
                    rows = None

                targets = set()
                if rows:
                    for r in rows:
                        if isinstance(r, dict) and r.get('path'):
                            targets.add(r.get('path'))

                if not targets:
                    ui.notify('No rows selected', type='negative')
                    return

                initial_count = len(datafiles)
                datafiles[:] = [d for d in datafiles if d.get('path') not in targets]

                try:
                    table.options['rowData'] = datafiles
                except Exception:
                    pass
                table.update()
                deleted_count = initial_count - len(datafiles)
                ui.notify(f'Deleted {deleted_count} items', type='positive')
            
            async def _clear_table(*_):
                """Clear all entries from the datafiles list and update the table."""
                if not datafiles:
                    ui.notify('Data table is already empty', type='warning')
                    return
                datafiles.clear()
                try:
                    table.options['rowData'] = datafiles
                except Exception:
                    pass
                table.update()
                ui.notify('Cleared all items from the data table', type='positive')

            with ui.row().classes('q-pa-md gap-4'):
                ui.button('Add Bruker D', icon='add', on_click=open_D_picker)
                ui.button('Add Thermo Raw', icon='add', on_click=open_raw_picker)
                ui.button('Add zipped Bruker D', icon='add', on_click=open_Dzip_picker)

            with ui.row().classes('w-full q-pa-md gap-2'):
                table = ui.aggrid({'columnDefs': columnDefs, 'rowData': datafiles,
                                    'rowSelection': {'mode': 'multiRow'}}).classes('h-128')

                table.on('cellValueChanged', _on_cell_value_changed)

                ui.button('Apply condition to selected', on_click=_open_condition_dialog).tooltip('Set the same condition value to all selected rows')
                ui.button('Apply fraction to selected', on_click=_open_fraction_dialog).tooltip('Set the same fraction value to all selected rows')
                ui.button('Assign replicates', on_click=_assign_replicates).tooltip('Assign consequentive replicate numbers to the rows with the same fraction and condition')
                ui.button('Delete selected', on_click=_delete_selected).tooltip('Delete selected entries from the data table')
                ui.button('Clear all', on_click=_clear_table).tooltip('Clear all entries from the data table')
                
            with ui.row().classes('w-full q-pa-md gap-2'):
                exp_name = ui.input(label='Experiment Name', placeholder='Enter experiment name here').classes('w-full')

            with ui.row().classes('w-full q-pa-md gap-2 items-center'):
                prop_input = ui.input(label='Properties file', placeholder='Enter properties file path here').classes('grow')
                ui.button('Select', icon='file_open', on_click=lambda _: open_file_picker(prop_input, '.prop|.txt|.json'))
                ui.button('Upload', icon='file_upload', on_click=lambda _: handle_upload(prop_input))
                
            with ui.row().classes('w-full q-pa-md gap-2 items-center'):
                rs_input = ui.input(label='Report schema', placeholder='Enter report schema path here').classes('grow')
                ui.button('Select', icon='file_open', on_click=lambda _: open_file_picker(rs_input, '.rs'))
                ui.button('Upload', icon='file_upload', on_click=lambda _: handle_upload(rs_input))

            with ui.row().classes('w-full q-pa-md gap-2 items-center'):
                fasta_input = ui.input(label='FASTA file', placeholder='Enter FASTA file path here').classes('grow')
                ui.button('Select', icon='file_open', on_click=lambda _: open_file_picker(fasta_input, '.fasta|.bgsfasta'))
                ui.button('Upload', icon='file_upload', on_click=lambda _: handle_upload(fasta_input))
                
            with ui.row().classes('w-full q-pa-md gap-2 items-center'):
                go_input = ui.input(label='GO file', placeholder='Enter GO file path here').classes('grow')
                ui.button('Select', icon='file_open', on_click=lambda _: open_file_picker(go_input, '.goannotation|.goa'))
                ui.button('Upload', icon='file_upload', on_click=lambda _: handle_upload(go_input))

            with ui.row().classes('w-full q-pa-md gap-2 items-center'):
                output_dir = ui.input(label='Output Directory', placeholder='Enter output directory here').classes('grow')
                ui.button('Select', icon='folder_open', on_click=lambda _: open_dirw_picker(output_dir))

            with ui.row().classes('w-full q-pa-md gap-2 items-center'):
                temp_dir = ui.input(label='Temp Directory', placeholder='Enter temporary directory here or leave empty for default one').classes('grow')
                ui.button('Select', icon='folder_open', on_click=lambda _: open_dirw_picker(temp_dir))

            with ui.expansion('Advanced options').classes('w-full'):
                with ui.row().classes('w-full q-pa-md gap-2 items-center'):
                    modrep_input = ui.input(label='Custom modification repository', placeholder='Enter file path here').classes('grow')
                    ui.button('Select', icon='file_open', on_click=lambda _: open_file_picker(modrep_input, ''))
                    ui.button('Upload', icon='file_upload', on_click=lambda _: handle_upload(modrep_input))
                with ui.row().classes('w-full q-pa-md gap-2 items-center'):
                    enzdb_input = ui.input(label='Custom enzyme DB', placeholder='Enter file path here').classes('grow')
                    ui.button('Select', icon='file_open', on_click=lambda _: open_file_picker(enzdb_input, '.enzdb'))
                    ui.button('Upload', icon='file_upload', on_click=lambda _: handle_upload(enzdb_input))
                with ui.row().classes('w-full q-pa-md gap-2 items-center'):
                    mark_verbose = ui.checkbox('Verbose output')
                    mark_segment = ui.checkbox('Segmented dia-PASEF (beta)')
                    mark_parquet = ui.checkbox('Parquet output')
                    mark_error = ui.checkbox('Terminate on error')

            with ui.row().classes('q-pa-md'):
                start_button = ui.button('Start Processing', color='primary')

                async def _on_start_click(*_):
                    args = {
                        'protocol': 'direct',
                        'experiment_name': exp_name.value,
                        'properties_file': prop_input.value,
                        'fasta_file': fasta_input.value,
                        'go_file': go_input.value,
                        'report_file': rs_input.value,
                        'output_directory': output_dir.value,
                        'temp_directory': temp_dir.value,
                        'verbose': mark_verbose.value,
                        'parquet': mark_parquet.value,
                        'segmented': mark_segment,
                        'error_term': mark_error.value,
                        'mod_repository': modrep_input.value,
                        'enzyme_database': enzdb_input.value,
                        'datafiles': datafiles,
                    }

                    tabs.set_value('Output')
                    ok.visible = False
                    not_ok.visible = False
                    start_button.disable()
                    abort_button.enable()
                    
                    # Create and store the task so it can be cancelled
                    running_task['task'] = asyncio.current_task()
                    try:
                        rc = await process_direct(terminal_output, progress, args)
                        if rc:
                            ok.visible = True
                            not_ok.visible = False
                        else:
                            ok.visible = False
                            not_ok.visible = True
                    except asyncio.CancelledError:
                        log.warning('Processing aborted by user')
                        ok.visible = False
                        not_ok.visible = True
                    finally:
                        running_task['task'] = None
                        start_button.enable()
                        abort_button.disable()
                        if terminate.value:
                            app.shutdown()

                start_button.on('click', _on_start_click)

        with ui.tab_panel(output_tab):
            ui.label('Console Output').classes('text-lg font-bold q-mt-lg')
            terminal_output = ui.log(max_lines=256).props('id="terminal_log"').classes('w-full font-mono h-128')
            progress = ui.linear_progress(show_value=False).classes('w-full')
            progress.visible = False
            
            with ui.row().classes('w-full q-pa-md gap-2'):
                abort_button = ui.button('Abort', color='negative', icon='stop')
                abort_button.disable()
                terminate = ui.checkbox('Terminate the app when processing is done')
                terminate.value = False
                
                async def _on_abort_click(*_):
                    if running_task['task'] is not None:
                        running_task['task'].cancel()
                        ui.notify('Aborting...', type='warning')
                    else:
                        ui.notify('No processing running', type='info')
                
                abort_button.on('click', _on_abort_click)
            
            with ui.row().classes('w-full q-pa-md gap-2 items-center') as ok:
                ui.icon('check_circle', color='green').classes('text-5xl')
                ui.label('Success').classes('text-green text-xl')
            with ui.row().classes('w-full q-pa-md gap-2 items-center') as not_ok:
                ui.icon('error', color='red').classes('text-5xl')
                ui.label('Error').classes('text-red text-xl')
            ok.visible = False
            not_ok.visible = False
            
            console = LogElementHandler(terminal_output)
            console.setLevel(logging.INFO)
            log.addHandler(console)
            ui.context.client.on_disconnect(lambda: log.removeHandler(console))

def dia_page():
    """DIA workflow page."""
    ui.label('Coming soon!').classes('q-pa-md')

def main():
    """Main entry point."""
    if SPECTRONAUT_KEY is None:
        log.error('Cannot find license key')
        exit(1)

    ui.run(root, title='Spectronaut UCloud GUI', port=PORT, reload=False)

if __name__ in {"__main__", "__mp_main__"}:
    main()
