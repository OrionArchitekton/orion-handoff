"""Test-only installed CLI launcher: synthetic cleanup acknowledgement failures."""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

from orion_handoff import cli, store
from orion_handoff.records import Fault

mode, selected_store, audit_path = sys.argv[1:]
sys.argv = ['orion-handoff', '--store', selected_store, '--json', 'record', '--input', '-']
original_exit, original_close = store.Store.__exit__, os.close
original_unlock, original_record = store.fcntl.flock, store.Store.record
descriptors = {}
exiting = False


def exit_store(self, *exc):
    global exiting
    descriptors.update({name: getattr(self, name) for name in ('records_fd', 'lock_fd', 'root')})
    exiting = True
    return original_exit(self, *exc)


def unlock(fd, flags):
    result = original_unlock(fd, flags)
    if flags == store.fcntl.LOCK_UN and mode in ('unlock', 'precommit', 'fault', 'unknown'):
        raise OSError('synthetic unlock acknowledgement failure')
    return result


def close(fd):
    result = original_close(fd)
    if exiting and fd == descriptors.get(mode):
        raise OSError('synthetic close acknowledgement failure')
    return result


def record(self, value):
    if mode == 'precommit':
        raise OSError('synthetic precommit failure')
    if mode == 'fault':
        raise Fault('busy', 73)
    result = original_record(self, value)
    if mode == 'unknown':
        raise Fault('commit_unknown', 74, {'candidate_record_id': result['record_id']})
    return result


with patch.object(store.Store, '__exit__', exit_store), \
        patch.object(store.os, 'close', close), \
        patch.object(store.fcntl, 'flock', unlock), \
        patch.object(store.Store, 'record', record):
    status = cli.main()
closed = {}
for name, fd in descriptors.items():
    try:
        os.fstat(fd)
        closed[name] = False
    except OSError:
        closed[name] = True
Path(audit_path).write_text(json.dumps(closed))
raise SystemExit(status)
