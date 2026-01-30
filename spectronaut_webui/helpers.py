import asyncio
import concurrent.futures
import functools
import logging
import multiprocessing
import pandas as pd
import threading
import zipfile
from typing import List, Tuple, Sequence
from pathlib import Path
from asyncio.subprocess import STDOUT, PIPE

# Global registry of active subprocesses for cancellation cleanup
_active_processes = {}
_process_lock = threading.Lock()

def track_subprocess_cleanup(coro_func):
    """Decorator that tracks running subprocesses and kills them on coroutine cancellation.
    
    When the decorated coroutine is cancelled (CancelledError), all spawned subprocesses
    are terminated gracefully first, then killed if necessary.
    
    Usage:
        @track_subprocess_cleanup
        async def my_long_running_function():
            ...
    """
    @functools.wraps(coro_func)
    async def wrapper(*args, **kwargs):
        # Get or create a unique ID for this invocation
        task_id = id(asyncio.current_task())
        _active_processes[task_id] = []
        
        try:
            result = await coro_func(*args, **kwargs)
            return result
        except asyncio.CancelledError:
            # On cancellation, clean up all subprocesses
            await _cleanup_processes(task_id)
            raise
        finally:
            # Clean up the registry
            with _process_lock:
                _active_processes.pop(task_id, None)
    
    return wrapper

async def _cleanup_processes(task_id: int):
    """Terminate all processes associated with a task."""
    with _process_lock:
        processes = _active_processes.get(task_id, [])
    
    if not processes:
        return
    
    logging.getLogger().warning(f'Cleaning up {len(processes)} subprocess(es)')
    
    # First, try to terminate gracefully
    for proc in processes:
        if proc and proc.returncode is None:
            try:
                proc.terminate()
            except Exception:
                pass
    
    # Give them a moment to terminate
    await asyncio.sleep(0.5)
    
    # Then force-kill any that are still running
    for proc in processes:
        if proc and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
    
    # Wait for all processes to finish
    for proc in processes:
        if proc:
            try:
                await proc.wait() if hasattr(proc, 'wait') else None
            except Exception:
                pass

def register_subprocess(process):
    """Register a subprocess with the current task for cleanup on cancellation."""
    task = asyncio.current_task()
    if task is None:
        return
    
    task_id = id(task)
    with _process_lock:
        if task_id in _active_processes:
            _active_processes[task_id].append(process)

def _extract_zip_worker(idx: int, zip_path: Path, extract_path: Path, progress_queue=None):
    """Worker that extracts zip_path into extract_base/name and verifies analysis.tdf exists.

    Returns (idx, success:bool, real_path_str or '', error_message)
    """
    def _try_put(*args):
        if progress_queue is not None:
            try:
                progress_queue.put(*args)
            except Exception:
                pass

    try:
        _try_put(('progress', f'Extracting {str(zip_path)}'))

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        real_path = extract_path.joinpath('analysis.tdf')
        if not real_path.exists():
            _try_put(('done', idx, False, '', f'Missing analysis.tdf after extraction for {str(zip_path)}'))

            return (idx, False, '', f'Missing analysis.tdf after extraction for {str(zip_path)}')
        
        _try_put(('done', idx, True, str(real_path.parent), ''))
        
        return (idx, True, str(real_path.parent), '')
    
    except Exception as e:
        _try_put(('done', idx, False, '', str(e)))
        return (idx, False, '', str(e))

def validate_filetable(filetable: List[dict]) -> bool:
    types = {file['type'] for file in filetable}
    
    if len(types) == 1 and 'Thermo Raw' in types:
        return True
    elif len(types) == 1 and ('Bruker D' in types or 'Bruker D Zip' in types):
        return True
    elif len(types) == 2 and 'Bruker D' in types and 'Bruker D Zip' in types:
        return True
    else:
        return False
    
def write_conditon_file(filetable: List[dict], output_path: str, log: logging.Logger) -> None:
    df = pd.DataFrame(filetable)
    df['#'] = range(1, len(df) + 1)
    df['File Name'] = df['name'].apply(lambda x: Path(x).stem)
    df['fraction'] = df['fraction'].apply(lambda s: 'NA' if s == '' else s)
    df['condition'] = df['condition'].apply(lambda s: 'NA' if s == '' else s)
    #unfilled replicate column, fill like 1, 2, 3, ... for the same condition and fraction
    
    if df['replicate'].astype(str).apply(lambda s: s.strip().lower() in ['', 'none', 'nan']).all():
        df['replicate'] = df.groupby(['fraction', 'condition'])['replicate'].\
            transform(lambda f: range(1, f.shape[0] + 1))
    
    #semifilled replicate column
    if df['replicate'].astype(str).apply(lambda s: s.strip().lower() in ['', 'none', 'nan']).any():
        log.warning('Only some replicates were assigned, check your input')
    
    df.rename(columns={'reference': 'Reference',
                       'name': 'Run Label',
                       'condition': 'Condition',
                       'fraction': 'Fraction',
                       'replicate': 'Replicate'}, inplace=True)
    df['Label'] = df['Condition']
    df.loc[:, ['#', 'Reference', 'Run Label', 'Condition', 'Fraction',
                'Replicate', 'Label', 'File Name']].to_csv(output_path, sep='\t', index=False)

def prepare_datafiles(filetable: List[dict], data_folder: Path, log: logging.Logger, progress, cancel_event: threading.Event = None) -> None:
    """Prepare data files for processing.
    
    Args:
        cancel_event: optional threading.Event to signal cancellation from the main task
    """
    # First, handle Bruker D folders synchronously (quick checks)
    zip_tasks: List[Tuple[int, dict]] = []  # list of (index, filedict) for zip entries
    for idx, file in enumerate(filetable):
        if file['type'] == 'Bruker D':
            real_path = Path(file['path']).joinpath('analysis.tdf')
            if not real_path.exists():
                raise FileNotFoundError(f'Corrupted Bruker D folder: {file["path"]} (missing analysis.tdf)')
            else:
                file['path'] = str(real_path.parent)

        elif file['type'] == 'Bruker D Zip':
            # defer unzipping to parallel workers
            zip_tasks.append((idx, file))
        else:
            # For Thermo Raw files, no action needed
            continue

    if zip_tasks:
        # choose number of workers (max 8 for IO bound tasks)
        max_workers = min(len(zip_tasks), 8)
        log.info(f'Extracting {len(zip_tasks)} Bruker D Zip file(s)')
        log.debug(f'Using {max_workers} workers')

        # Use a Manager queue for streaming progress from workers
        manager = multiprocessing.Manager()
        progress_q = manager.Queue()

        total = len(zip_tasks)
        done_counter = [0]
        errors = []
        progress.visible = True
        progress.value = 0
        
        # Flag to signal early exit on cancellation
        should_exit = [False]

        def _progress_reader():
            # consume progress messages and update filetable/log
            while done_counter[0] < total and not should_exit[0]:
                try:
                    item = progress_q.get(timeout=1)
                except Exception:
                    continue
                if not item:
                    continue
                typ = item[0]
                if typ == 'progress':
                    _, msg = item
                    log.info(msg)
                elif typ == 'done':
                    _, idx, success, real_path, err = item
                    file = filetable[idx]
                    if success:
                        file['path'] = real_path
                        file['name'] = Path(file['name']).stem
                        log.info(f'Extracted {file["name"]} -> {real_path}')
                    else:
                        log.error(f'Failed extracting {file["path"]}: {err}')
                        errors.append((file['path'], err))
                    done_counter[0] += 1
                    progress.value = done_counter[0]/total

        reader_thread = threading.Thread(target=_progress_reader, daemon=True)
        reader_thread.start()

        # Try process pool first, fallback to thread pool
        futures = []
        executor = None
        try:
            executor = concurrent.futures.ProcessPoolExecutor(max_workers=max_workers)
            futures = [executor.submit(_extract_zip_worker, idx, Path(file['path']),
                           Path(data_folder).joinpath(Path(file['name']).stem), progress_q) for idx, file in zip_tasks]
            # Wait for all futures to complete with periodic checks for cancellation
            # Use a timeout loop so we can check cancel_event periodically
            while True:
                done, pending = concurrent.futures.wait(futures, timeout=0.2)
                if not pending:  # All futures completed
                    break
                if cancel_event and cancel_event.is_set():
                    # Cancellation requested: cancel all pending futures
                    log.debug('Cancellation signal received, terminating extraction tasks')
                    for fut in futures:
                        fut.cancel()
                    raise asyncio.CancelledError('Zip extraction cancelled')
        except asyncio.CancelledError:
            # On cancellation, clean up and re-raise
            log.debug('Extraction cancelled, cleaning up executor')
            if executor:
                for fut in futures:
                    fut.cancel()
            raise
        except Exception as e:
            log.debug(f'Process pool extraction failed ({e})')
        finally:
            # Mark that we want to exit, but keep the queue alive for in-flight processes
            should_exit[0] = True
            
            # Cancel only futures that haven't started yet
            # This allows running processes to finish naturally
            if futures:
                for fut in futures:
                    fut.cancel()
            
            # Wait for all futures to complete (both cancelled and running)
            # This ensures all processes finish their work and close queue connections
            if futures:
                try:
                    concurrent.futures.wait(futures, timeout=5)
                except Exception as e:
                    log.debug(f'Error waiting for futures: {e}')
            
            # Now shutdown the executor after all processes have finished
            if executor:
                executor.shutdown(wait=True)
            
            # Give reader thread time to consume remaining messages
            reader_thread.join(timeout=2)
            
            # NOW all processes are dead; safe to shutdown the manager
            try:
                manager.shutdown()
            except Exception as e:
                log.debug(f'Error shutting down manager: {e}')

            progress.visible = False

        if errors:
            raise Exception('Error extracting zip file(s)')

async def prepare_datafiles_async(filetable: List[dict], data_folder: Path, log: logging.Logger, progress) -> None:
    """Async wrapper for prepare_datafiles that allows cancellation.
    
    Runs the synchronous prepare_datafiles in a thread pool so it can be cancelled.
    When cancelled, sets the cancel_event which signals the extraction threads to stop.
    """
    cancel_event = threading.Event()

    try:
        await asyncio.to_thread(prepare_datafiles, filetable, data_folder, log, progress, cancel_event)
    except asyncio.CancelledError:
        log.warning('Zip extraction cancelled by user')
        # Signal the worker thread to stop processing
        cancel_event.set()
        raise
        
def get_args(args: dict) -> Sequence[str]:
    return functools.reduce(lambda i,j: i + j, _parse_args(args), [])

def _parse_args(args: dict) -> Sequence[list]:
    result = []
    if args.get('temp_directory'):
        result.append(['-setTemp', f'{args["temp_directory"]}'])
    if args.get('mod_repository'):
        result.append(['--importModRepository', f'{args["mod_repository"]}'])
    if args.get('enzyme_database'):
        result.append(['--importEnzymeDB', f'{args["enzyme_database"]}'])
    if args.get('protocol'):
        result.append([f'{args["protocol"]}'])
    if args.get('experiment_name'):
        result.append(['-n', f'{args["experiment_name"]}'])
    if args.get('condition_file'):
        result.append(['-con', f'{args["condition_file"]}'])
    if args.get('properties_file'):
        result.append(['-s', f'{args["properties_file"]}'])
    if args.get('report_file'):
        result.append(['-rs', f'{args["report_file"]}'])
    if args.get('fasta_file'):
        result.append(['-fasta', f'{args["fasta_file"]}'])
    if args.get('go_file'):
        result.append(['-go', f'{args["go_file"]}'])
    if args.get('output_directory'):
        result.append(['-o', f'{args["output_directory"]}'])
    if args.get('verbose'):
        result.append(['--verbose'])
    if args.get('parquet'):
        result.append(['--writeParquet'])
    if args.get('error_term'):
        result.append(['--terminateAfterError'])
    if args.get('segmented'):
        result.append(['-segmented'])
    
    return result

def get_full_args(args: dict) -> None:
    args_list = functools.reduce(lambda i,j: i + j, _parse_args(args), [])
    for file in args.get('datafiles'):
        args_list.extend(['-r', f'{file["path"]}'])

    return args_list

async def run_cmd(args: Sequence[str], log: logging.Logger, timeout: float | None = None) -> bool:
    """Run a command asynchronously, streaming stdout/stderr to the logger.

    - args: sequence of command + arguments (same as subprocess.exec args)
    - timeout: optional timeout in seconds for the whole process
    Returns True on exit code 0, False otherwise.
    This implementation handles decode errors, supports cancellation and timeouts,
    and ensures the subprocess is terminated if the coroutine is cancelled.
    """
    log.debug(f'run_cmd {args} (timeout={timeout})')
    try:
        process = await asyncio.create_subprocess_exec(*args, stdout=PIPE, stderr=STDOUT)
        # Register this process for cleanup if the task is cancelled
        register_subprocess(process)
        log.debug(f'Added PID: {process.pid}')

        try:
            # Stream output line-by-line using async for when available
            async def _stream_stdout():
                if process.stdout is None:
                    return
                async for raw_line in process.stdout:
                    try:
                        line = raw_line.decode(errors='replace').rstrip()
                    except Exception:
                        # Safe fallback
                        line = str(raw_line)
                    log.info(line)

            if timeout is not None:
                # run streaming and wait with timeout
                await asyncio.wait_for(_stream_stdout(), timeout=timeout)
                rc = await process.wait()
            else:
                # no timeout: stream until EOF then wait for exit
                await _stream_stdout()
                rc = await process.wait()

            return rc == 0

        except asyncio.TimeoutError:
            log.error(f'Command timed out after {timeout} seconds: {args}')
            try:
                process.kill()
            except Exception:
                pass
            await process.wait()
            return False

        except asyncio.CancelledError:
            # Caller cancelled the coroutine: terminate the subprocess
            try:
                log.debug(f'Killing {process.pid}')
                process.kill()
            except Exception as e:
                log.debug(f'Killing failed for {process.pid}: {e}')
                pass
            await process.wait()
            raise

    except Exception as e:
        log.error(f'Cannot execute command {args}: {e}')
        return False
