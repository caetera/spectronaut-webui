"""Convert workflow processing."""

import asyncio
import logging
from pathlib import Path
from shutil import copy
from nicegui import ui
from .. import helpers

log = logging.getLogger(__name__)


@helpers.track_subprocess_cleanup
async def process_convert(output_widget, progress_widget, args, spectronaut_cmd, spectronaut_key):
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

    # Make a snapshot of the parameters files in the output directory to ensure reproducibility
    for property_key in ['properties_file']:
        if args[property_key] != '' and Path(args[property_key]).exists():
            new_path = Path(params_folder).joinpath(Path(args[property_key]).name)
            copy(Path(args[property_key]), new_path)
            args[property_key] = new_path
    
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
    result = await helpers.run_cmd(spectronaut_cmd + ['activate', spectronaut_key], log)
    if result:
        log.info('Spectronaut activated successfully')
    else:
        log.error('Cannot activate Spectronaut, see detailed log')
        return
    
    global_args = helpers.get_global_args(args)
    if global_args:
        log.info('Executing global arguments')
        log.debug(f'Global arguments: {global_args}')
        result = await helpers.run_cmd(spectronaut_cmd + global_args, log)
        if result:
            log.info('Global arguments set successfully')
        else:
            log.error('Cannot execute global arguments, see detailed log')
            return

    total = len(args['datafiles'])
    log.info(f'Converting {total} files')
    progress_widget.visible = True
    progress_widget.value = 0
    success = True
    for i in range(total):
        file_path = Path(args['datafiles'][i]['path'])
        result = await helpers.run_cmd(spectronaut_cmd + ['convert', '-i', file_path] + args_list, log)
        success = success and result
        if result:
            log.info(f'[{i + 1}|{total}] Converted successfully')
        else:
            log.error('Processing failed, see detailed log')
        
        progress_widget.value = (i + 1) / total
    
    progress_widget.visible = False
    
    log.info('Deactivating Spectronaut')
    result = await helpers.run_cmd(spectronaut_cmd + ['deactivate'], log)
    if result:
        log.info('Spectronaut deactivated')
    else:
        log.error('Cannot deactivate Spectronaut, see detailed log')
    
    return success
