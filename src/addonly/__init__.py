"""addonly: put a file into a folder that you only ever add to.

  addonly put SRC DIR [--name NAME] [--zip-check] [--max-member BYTES] [--deny-ext .exe,.pkl]
  addonly check-zip ZIP [--max-member BYTES] [--deny-ext .exe,.pkl] [--version-file VERSION]

put copies SRC into DIR by exclusive create only. It never overwrites, renames, truncates or removes
anything. It refuses a DIR that is missing, a link, or under a link, and a target name that exists in any
form (file, folder, dangling link). It lists DIR with sha256 before and after; the two listings must differ
by exactly the one added file.

Exit codes: 0 done, 1 unexpected error, 2 input refused (bad zip), 3 target exists or DIR refused,
4 the listing of DIR changed by more than the added file.
"""
import argparse
import hashlib
import os
import re
import sys
import zipfile

__version__ = "0.1.0"
DENY_EXT = (".exe", ".dll", ".pkl", ".pickle")
MAX_MEMBER = 10 * 1024 * 1024


class Refused(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def listing(d):
    """{relative path: sha256} of every regular file under d; links are listed by their target text."""
    out = {}
    for root, dirs, files in os.walk(d):
        for n in files + [x for x in dirs if os.path.islink(os.path.join(root, x))]:
            p = os.path.join(root, n)
            rel = os.path.relpath(p, d)
            out[rel] = "link:" + os.readlink(p) if os.path.islink(p) else sha256(p) if os.path.isfile(p) else "other"
    return out


def check_zip(path, max_member=MAX_MEMBER, deny_ext=DENY_EXT, version_file=None):
    """Return the version text (or "") of a zip that passes: opens, every CRC matches, no member over
    max_member bytes, no member with a denied extension or an absolute or .. path. Raises Refused(2)."""
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as e:
        raise Refused(2, f"zip does not open: {e}")
    with z:
        try:
            bad = z.testzip()
        except (zipfile.BadZipFile, OSError, EOFError) as e:
            raise Refused(2, f"zip test failed: {e}")
        if bad:
            raise Refused(2, f"zip test failed at {bad}")
        for i in z.infolist():
            n = i.filename
            if n.startswith("/") or ".." in n.split("/"):
                raise Refused(2, f"member path leaves the zip root: {n}")
            if i.file_size > max_member:
                raise Refused(2, f"member over {max_member} bytes: {n}")
            if n.lower().endswith(tuple(deny_ext)):
                raise Refused(2, f"member with a denied extension: {n}")
        if not version_file:
            return ""
        names = z.namelist()
        tops = sorted({n.split("/")[0] for n in names if "/" in n})
        found = next((c for c in [version_file] + [t + "/" + version_file for t in tops] if c in names), None)
        if not found:
            raise Refused(2, f"no {version_file} at the zip root or in a top folder")
        ver = z.read(found).decode("utf-8", "replace").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", ver):
        raise Refused(2, f"{version_file} is not a plain version: {ver[:40]!r}")
    return ver


def put(src, d, name=None):
    """Copy src into d as name (default: basename of src). Returns the target path. Raises Refused."""
    if not os.path.isfile(src):
        raise Refused(2, f"source is not a file: {src}")
    if os.path.islink(d) or not os.path.isdir(d) or os.path.realpath(d) != os.path.abspath(d):
        raise Refused(3, f"folder {d!r} is missing, not a folder, or a link or under a link")
    name = name or os.path.basename(src)
    if not name or "/" in name or name in (".", ".."):
        raise Refused(2, f"bad target name: {name!r}")
    target = os.path.join(d, name)
    if os.path.lexists(target):
        raise Refused(3, f"target exists (file, folder or link): {target}")
    before = listing(d)
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    except FileExistsError:
        raise Refused(3, f"target exists (file, folder or link): {target}")
    with open(src, "rb") as s, os.fdopen(fd, "wb") as t:
        for b in iter(lambda: s.read(1 << 20), b""):
            t.write(b)
    after = listing(d)
    changed = {k for k, v in after.items() if before.get(k) != v} | (before.keys() - after.keys())
    if changed != {name} or after[name] != sha256(src):
        raise Refused(4, f"listing of {d} changed by more than the added file: {sorted(changed)[:5]}")
    return target


def _ext(s):
    return tuple(x if x.startswith(".") else "." + x for x in s.lower().split(",") if x)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="addonly", description="Put a file into a folder you only ever add to.")
    ap.add_argument("--version", action="version", version="addonly " + __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("put", "check-zip"):
        p = sub.add_parser(n)
        if n == "put":
            p.add_argument("src")
            p.add_argument("dir")
            p.add_argument("--name", help="target file name (default: the source's name)")
            p.add_argument("--zip-check", action="store_true", help="refuse a zip that fails check-zip")
        else:
            p.add_argument("zip")
            p.add_argument("--version-file", help="require this file at the zip root or in a top folder; print its text")
        p.add_argument("--max-member", type=int, default=MAX_MEMBER, help="largest member in bytes (default 10 MiB)")
        p.add_argument("--deny-ext", default=",".join(DENY_EXT), help="comma list of member extensions to refuse")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "check-zip":
            ver = check_zip(a.zip, a.max_member, _ext(a.deny_ext), a.version_file)
            print(f"ok {sha256(a.zip)} {a.zip}" + (f" version {ver}" if ver else ""))
            return 0
        if a.zip_check:
            check_zip(a.src, a.max_member, _ext(a.deny_ext))
        t = put(a.src, a.dir, a.name)
        print(f"added {sha256(t)} {t}")
        return 0
    except Refused as e:
        print(f"addonly: refused: {e}", file=sys.stderr)
        return e.code
    except Exception as e:  # one line, never a traceback
        print(f"addonly: failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
