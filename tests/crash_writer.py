"""Test-only launcher for otherwise unreachable publication stages.

Imports the installed package. This file is never in the wheel and exposes no
fault flags or environment switches in the actual CLI.
"""
import os
import signal
import stat
import sys
from unittest.mock import patch
import uuid

from orion_handoff import cli, store

stage, selected_store = sys.argv[1:]
sys.argv = ["orion-handoff", "--store", selected_store, "--json", "record", "--input", "-"]
link, unlink, sync, create, record = (store.os.link, store.os.unlink, store.os.fsync,
                                   store.create_file, store.Store.record)
original_uuid = store.uuid.uuid4


def identifier():
    return uuid.UUID(stage.split(":", 1)[1]) if stage.startswith("collision:") else original_uuid()


def kill():
    os.kill(os.getpid(), signal.SIGKILL)


def interrupt_link(*args, **kwargs):
    if stage == "after_file_sync":
        kill()
    result = link(*args, **kwargs)
    if stage == "link_error_after_commit":
        raise OSError("synthetic failure after link committed")
    if stage == "after_link":
        kill()
    return result


def interrupt_unlink(*args, **kwargs):
    if stage == "after_directory_sync":
        kill()
    return unlink(*args, **kwargs)


def interrupt_sync(fd):
    if stage == "sync_error" and stat.S_ISDIR(os.fstat(fd).st_mode):
        raise OSError("synthetic directory fsync failure")
    return sync(fd)


def interrupt_create(directory, name, content):
    if stage == "partial_write" and name.startswith(".pending-"):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
        os.write(fd, content[:len(content) // 2])
        kill()
    return create(directory, name, content)


def interrupt_ack(self, value):
    result = record(self, value)
    if stage == "before_ack":
        kill()
    return result


with patch.object(store.os, "link", interrupt_link), \
        patch.object(store.os, "unlink", interrupt_unlink), \
        patch.object(store.os, "fsync", interrupt_sync), \
        patch.object(store, "create_file", interrupt_create), \
        patch.object(store.Store, "record", interrupt_ack), \
        patch.object(store.uuid, "uuid4", identifier):
    raise SystemExit(cli.main())
