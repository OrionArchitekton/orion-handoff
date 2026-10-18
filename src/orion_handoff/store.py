"""A cooperating, same-host private store with no implicit bootstrap or pointers."""
from contextlib import contextmanager
import hashlib
import errno
import os
import platform
import stat
import sys
import time
import uuid

try:
    import fcntl
except ImportError:
    fcntl = None

from .records import Fault, MAX_BYTES, decode, encode, now, stamp, validate, valid_id, time_value
from .context import assess

DIRECTORY = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
MARKER = {"store_version": 1, "record_version": 1}


def supported():
    if sys.platform != "linux" or platform.machine() != "x86_64" or fcntl is None:
        raise Fault("unsupported_platform", 69)


@contextmanager
def parent(path):
    supported()
    parts = path_parts(path)
    fd = os.open("/", DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd, parts[-1]
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise Fault("store_unsafe", 74) from exc
        raise
    finally:
        os.close(fd)


def path_parts(path):
    if not path or not os.path.isabs(path):
        raise Fault("usage", 2)
    parts = path.split("/")
    if any(part in (".", "..") for part in parts) or not any(parts):
        raise Fault("usage", 2)
    return [part for part in parts if part]


def check(info, directory=False, links=(1,)):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    mode = 0o700 if directory else 0o600
    if (not kind(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != mode
            or (not directory and info.st_nlink not in links)):
        raise Fault("store_unsafe", 74)


def open_file(directory, name, flags=os.O_RDONLY, links=(1,)):
    before = os.stat(name, dir_fd=directory, follow_symlinks=False)
    check(before, links=links)
    fd = os.open(name, flags | NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        after = os.fstat(fd)
        check(after, links=links)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise Fault("store_unsafe", 74)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_file(directory, name, limit=MAX_BYTES, links=(1,)):
    fd = open_file(directory, name, links=links)
    try:
        if os.fstat(fd).st_size > limit:
            raise Fault("limit_exceeded", 74)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise Fault("limit_exceeded", 74)
        return raw
    finally:
        os.close(fd)


@contextmanager
def locked(fd, exclusive):
    deadline = time.monotonic() + 2
    while True:
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise Fault("busy", 73)
            time.sleep(0.01)
    try:
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)


def create_file(directory, name, content):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW, 0o600,
                 dir_fd=directory)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def initialize(path):
    with parent(path) as (parent_fd, leaf):
        try:
            os.mkdir(leaf, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            with Store(path) as existing:
                return False, existing.warnings
        os.chmod(leaf, 0o700, dir_fd=parent_fd, follow_symlinks=False)
        root = os.open(leaf, DIRECTORY, dir_fd=parent_fd)
        try:
            os.fchmod(root, 0o700)
            create_file(root, ".lock", b"")
            lock_fd = open_file(root, ".lock")
            try:
                with locked(lock_fd, True):
                    os.mkdir("records", 0o700, dir_fd=root)
                    os.chmod("records", 0o700, dir_fd=root, follow_symlinks=False)
                    create_file(root, "store.json", encode(MARKER))
                    os.fsync(root)
                    os.fsync(parent_fd)
            finally:
                os.close(lock_fd)
        finally:
            os.close(root)
    return True, []


class Store:
    def __init__(self, path, write=False):
        self.path, self.write = path, write
        self.root = self.lock_fd = self.records_fd = None
        self.lock_context = None
        self.publication_candidate = None
        self.rows = {}
        self.tips = {}
        self.warnings = []

    def __enter__(self):
        try:
            with parent(self.path) as (parent_fd, leaf):
                self.root = os.open(leaf, DIRECTORY, dir_fd=parent_fd)
            check(os.fstat(self.root), directory=True)
            self.lock_fd = open_file(self.root, ".lock")
            self.lock_context = locked(self.lock_fd, self.write)
            self.lock_context.__enter__()
            if os.fstat(self.lock_fd).st_size != 0:
                raise Fault("store_invalid", 74)
            names = set()
            with os.scandir(self.root) as entries:
                for entry in entries:
                    names.add(entry.name)
                    if len(names) > 3 or entry.name not in {"store.json", ".lock", "records"}:
                        raise Fault("store_invalid", 74)
            if len(names) != 3:
                raise Fault("store_incomplete", 74)
            try:
                marker = decode(read_file(self.root, "store.json", 256))
            except Fault as exc:
                if exc.code == "invalid_input":
                    raise Fault("store_invalid", 74) from exc
                raise
            if set(marker) != set(MARKER) or any(type(v) is not int for v in marker.values()):
                raise Fault("store_invalid", 74)
            if marker != MARKER:
                raise Fault("incompatible_version", 74)
            self.records_fd = os.open("records", DIRECTORY, dir_fd=self.root)
            check(os.fstat(self.records_fd), directory=True)
            self._scan()
            return self
        except FileNotFoundError as exc:
            code = "store_missing" if self.root is None else "store_incomplete"
            self.__exit__(*sys.exc_info())
            raise Fault(code, 69 if code == "store_missing" else 74) from exc
        except OSError as exc:
            self.__exit__(*sys.exc_info())
            if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                raise Fault("store_unsafe", 74) from exc
            raise
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def __exit__(self, *exc):
        cleanup_error = None
        if self.lock_context is not None:
            try:
                self.lock_context.__exit__(*exc)
            except Exception as error:
                cleanup_error = error
            finally:
                self.lock_context = None
        for name in ("records_fd", "lock_fd", "root"):
            fd = getattr(self, name)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError as error:
                    cleanup_error = cleanup_error or error
                finally:
                    # Do not retry close: the OS may already have released this fd.
                    setattr(self, name, None)
        # Preserve the original operation fault, particularly commit_unknown.
        if cleanup_error is not None and exc[0] is None:
            if self.publication_candidate is not None:
                raise Fault("commit_unknown", 74,
                            {"candidate_record_id": self.publication_candidate}) from cleanup_error
            raise cleanup_error

    def _scan(self):
        metadata = {}
        with os.scandir(self.records_fd) as entries:
            for entry in entries:
                if len(metadata) >= 1024:
                    raise Fault("limit_exceeded", 74)
                name = entry.name
                record_id = name[9:] if name.startswith(".pending-") else name[:-5]
                if not valid_id(record_id) or not (name.startswith(".pending-") or name.endswith(".json")):
                    raise Fault("store_invalid", 74)
                info = os.stat(name, dir_fd=self.records_fd, follow_symlinks=False)
                check(info, links=(1, 2))
                if info.st_size > MAX_BYTES:
                    raise Fault("limit_exceeded", 74)
                metadata[name] = info
        self.entry_count = len(metadata)
        aggregate = 0
        for name, info in metadata.items():
            pending = name.startswith(".pending-")
            record_id = name[9:] if pending else name[:-5]
            if info.st_nlink == 2:
                partner = record_id + ".json" if pending else ".pending-" + record_id
                other = metadata.get(partner)
                if other is None or (other.st_dev, other.st_ino) != (info.st_dev, info.st_ino):
                    raise Fault("store_unsafe", 74)
            if pending:
                self.warnings = ["pending_files_present"]
            else:
                if len(self.rows) >= 512:
                    raise Fault("limit_exceeded", 74)
                aggregate += info.st_size
                if aggregate > 33554432:
                    raise Fault("limit_exceeded", 74)
                raw = read_file(self.records_fd, name, links=(info.st_nlink,))
                try:
                    row = validate(decode(raw), stored=True)
                except Fault as exc:
                    raise Fault("store_invalid", 74) from exc
                if row["record_id"] != record_id:
                    raise Fault("store_invalid", 74)
                self.rows[row["record_id"]] = row
        self._chains()

    def _chains(self):
        roots, children = {}, {}
        for key, row in self.rows.items():
            previous = row["predecessor"]
            if previous is None:
                if row["task_key"] in roots:
                    raise Fault("store_invalid", 74)
                roots[row["task_key"]] = key
            else:
                parent_row = self.rows.get(previous)
                if (parent_row is None or previous in children
                        or parent_row["task_key"] != row["task_key"]
                        or parent_row["project_key"] != row["project_key"]):
                    raise Fault("store_invalid", 74)
                children[previous] = key
        visited = set()
        for task, root in roots.items():
            current = root
            while True:
                if current in visited:
                    raise Fault("store_invalid", 74)
                visited.add(current)
                if current not in children:
                    break
                current = children[current]
            self.tips[task] = self.rows[current]
        if len(visited) != len(self.rows):
            raise Fault("store_invalid", 74)

    def record(self, value):
        current = self.tips.get(value["task_key"])
        if (value["predecessor"] != (current["record_id"] if current else None)
                or (current and current["project_key"] != value["project_key"])):
            raise Fault("conflict", 73)
        if len(self.rows) >= 512 or self.entry_count + 2 > 1024:
            raise Fault("limit_exceeded", 74)
        for _ in range(3):
            record_id = str(uuid.uuid4())
            row = dict(value, record_id=record_id, created_at=stamp(now()))
            raw = encode(row)
            if len(raw) > MAX_BYTES:
                raise Fault("invalid_input", 65)
            pending = ".pending-" + record_id
            final = record_id + ".json"
            if any(self._exists(name) for name in (pending, final)):
                continue
            publication_attempted = False
            try:
                create_file(self.records_fd, pending, raw)
                publication_attempted = True
                self.publication_candidate = record_id
                os.link(pending, final, src_dir_fd=self.records_fd,
                        dst_dir_fd=self.records_fd, follow_symlinks=False)
                os.fsync(self.records_fd)
                os.unlink(pending, dir_fd=self.records_fd)
                os.fsync(self.records_fd)
                return {"record_id": record_id, "task_key": row["task_key"],
                        "sha256": hashlib.sha256(raw).hexdigest()}
            except Exception as exc:
                if publication_attempted:
                    raise Fault("commit_unknown", 74, {"candidate_record_id": record_id}) from exc
                raise
        raise Fault("id_collision", 73)

    def _exists(self, name):
        try:
            os.stat(name, dir_fd=self.records_fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    def show(self, record_id):
        if record_id not in self.rows:
            raise Fault("not_found", 11)
        row = self.rows[record_id]
        raw = read_file(self.records_fd, record_id + ".json", links=(1, 2))
        recency, acceptance, reasons, _ = assess(row)
        return {"record": row, "current": self.tips[row["task_key"]]["record_id"] == record_id,
                "sha256": hashlib.sha256(raw).hexdigest(), "recency": recency,
                "acceptance": acceptance, "reasons": reasons}

    def list(self, task, limit):
        selected = [r for r in self.rows.values() if task is None or r["task_key"] == task]
        selected.sort(key=lambda r: (time_value(r["created_at"]), r["record_id"]), reverse=True)
        keys = ("record_id", "task_key", "project_key", "title", "status", "created_at")
        rows = [dict({key: r[key] for key in keys},
                     current=self.tips[r["task_key"]]["record_id"] == r["record_id"])
                for r in selected[:limit]]
        return {"records": rows, "returned": len(rows), "matching_total": len(selected),
                "truncated": len(selected) > limit}
