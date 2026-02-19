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

    if args['properties_file'] != '' and Path(args['properties_file']).exists():
        new_path = Path(params_folder).joinpath(Path(args['properties_file']).name)
        copy(Path(args['properties_file']), new_path)
        args['properties_file'] = new_path
    
    if args['fasta_file'] != '' and Path(args['fasta_file']).exists():
        new_path = Path(params_folder).joinpath(Path(args['fasta_file']).name)
        copy(Path(args['fasta_file']), new_path)
        args['fasta_file'] = new_path

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
