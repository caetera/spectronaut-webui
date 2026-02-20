"""DirectDIA workflow processing."""

import asyncio
import logging
from pathlib import Path
from shutil import copy
from nicegui import ui
from .. import helpers

log = logging.getLogger(__name__)


@helpers.track_subprocess_cleanup
async def process_direct(output_widget, progress_widget, args, spectronaut_cmd, spectronaut_key) -> bool|None:
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

    # Make a snapshot of the parameters files in the output directory to ensure reproducibility
    for property_key in ['properties_file', 'fasta_file', 'go_file', 'report_file', 'mod_repository', 'enzyme_database']:
        if args[property_key] != '' and Path(args[property_key]).exists():
            new_path = Path(params_folder).joinpath(Path(args[property_key]).name)
            copy(Path(args[property_key]), new_path)
            args[property_key] = new_path
        
    output_widget.clear()

    if not helpers.validate_filetable(args['datafiles'], 'raw'):
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
        args_list = await asyncio.to_thread(helpers.get_full_args, args, file_arg='-r')
        log.debug(f'Got full arguments: {len(args_list)} included')
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

    success = True
    log.info('Launching Spectronaut')
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
