"""Combine workflow processing."""

import asyncio
import logging
from pathlib import Path
from shutil import copy
from nicegui import ui
from .. import helpers

log = logging.getLogger(__name__)


@helpers.track_subprocess_cleanup
async def process_combine(output_widget, progress_widget, args, spectronaut_cmd, spectronaut_key):
    """Run Combine workflow"""
    if not args['datafiles']:
        ui.notify('No files to process', type='negative')
        return

    if args['output_directory'] == '':
        ui.notify('Output directory not specified', type='negative')
        return
    
    if not Path(args['output_directory']).exists():
        Path(args['output_directory']).mkdir(parents=True)

    if args['experiment_name'] == '':
        args['experiment_name'] = Path(args['datafiles'][0]['name']).stem

    params_folder = Path(args['output_directory']).joinpath('params')
    params_folder.mkdir(parents=True, exist_ok=True)

    # Make a snapshot of the parameters files in the output directory to ensure reproducibility
    for property_key in ['properties_file', 'fasta_file', 'report_file', 'mod_repository', 'enzyme_database']:
        if args[property_key] != '' and Path(args[property_key]).exists():
            new_path = Path(params_folder).joinpath(Path(args[property_key]).name)
            copy(Path(args[property_key]), new_path)
            args[property_key] = new_path

    output_widget.clear()

    if not helpers.validate_filetable(args['datafiles'], 'sne'):
        log.error('Invalid file table: Mixed or unsupported file types.')
        return

    args.pop('protocol')
    
    try:
        args_list = await asyncio.to_thread(helpers.get_full_args, args, file_arg='-sne')
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
    log.info(f'Combining {total} files')
    success = True
    result = await helpers.run_cmd(spectronaut_cmd + args_list, log)
    success = success and result
    if result:
        log.info('Spectronaut exited successfully')
    else:
        log.error('Processing failed, see detailed log')
    
    log.info('Deactivating Spectronaut')
    result = await helpers.run_cmd(spectronaut_cmd + ['deactivate'], log)
    if result:
        log.info('Spectronaut deactivated')
    else:
        log.error('Cannot deactivate Spectronaut, see detailed log')
    
    return success
