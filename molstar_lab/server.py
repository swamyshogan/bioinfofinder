"""molstar-lab: a Jupyter-Lab-style local launcher for the Mol* viewer.

Run `molstar-lab` inside any folder; a local server starts, your browser opens
Mol*, and a sidebar lets you browse every file under that folder and load it.
"""

from __future__ import annotations

import argparse
import errno
import gzip
import json
import mimetypes
import os
import re
import shutil
import socket
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__

MOLSTAR_VERSION = os.environ.get("MOLSTAR_LAB_MOLSTAR_VERSION", "5.13.1")
CDN = "https://cdn.jsdelivr.net/npm/molstar@{ver}/build/viewer/{name}"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "molstar-lab"
STATIC_DIR = Path(__file__).parent / "static"

# Extensions Mol* can open (lower-case, without a trailing .gz / .zip).
STRUCTURE_EXT = {
    ".pdb", ".ent", ".cif", ".mmcif", ".bcif", ".pdbqt", ".gro", ".mol", ".mol2",
    ".sdf", ".sd", ".xyz", ".lammpsdata", ".data",
}
TOPOLOGY_EXT = {".psf", ".prmtop", ".parm7", ".top"}
TRAJECTORY_EXT = {".xtc", ".trr", ".dcd", ".nc", ".nctraj", ".lammpstrj"}
VOLUME_EXT = {".ccp4", ".mrc", ".map", ".dsn6", ".brix", ".cube", ".dx", ".dxbin"}
SESSION_EXT = {".molj", ".molx", ".mvsj", ".mvsx"}
ALL_MOL_EXT = STRUCTURE_EXT | TOPOLOGY_EXT | TRAJECTORY_EXT | VOLUME_EXT | SESSION_EXT


def classify(name: str) -> str | None:
    low = name.lower()
    for comp in (".gz", ".zip"):
        if low.endswith(comp):
            low = low[: -len(comp)]
    ext = os.path.splitext(low)[1]
    if ext in STRUCTURE_EXT:
        return "structure"
    if ext in TOPOLOGY_EXT:
        return "topology"
    if ext in TRAJECTORY_EXT:
        return "trajectory"
    if ext in VOLUME_EXT:
        return "volume"
    if ext in SESSION_EXT:
        return "session"
    return None


def natural_key(s: str):
    """Sort 'seed-2' before 'seed-10'."""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.split(r"(\d+)", s.lower()) if t]


def ensure_molstar_asset(name: str) -> Path | None:
    """Return a local copy of molstar.js / molstar.css, downloading it once."""
    target = CACHE_DIR / MOLSTAR_VERSION / name
    if target.exists() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    url = CDN.format(ver=MOLSTAR_VERSION, name=name)
    try:
        print(f"[molstar-lab] downloading Mol* {MOLSTAR_VERSION} {name} (first run only)...", file=sys.stderr)
        tmp = target.with_suffix(target.suffix + ".part")
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        tmp.replace(target)
        return target
    except Exception as e:  # offline and not cached
        print(f"[molstar-lab] could not fetch {url}: {e}", file=sys.stderr)
        return None


class LabHandler(BaseHTTPRequestHandler):
    root: Path = Path.cwd()
    show_hidden: bool = False
    server_version = f"molstar-lab/{__version__}"

    # ---- helpers -------------------------------------------------------
    def log_message(self, fmt, *args):  # quiet by default
        if os.environ.get("MOLSTAR_LAB_DEBUG"):
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(obj).encode(), "application/json")

    def _error(self, status: int, msg: str):
        self._json({"error": msg}, status)

    def _resolve(self, rel: str) -> Path | None:
        """Resolve a user-supplied relative path, refusing anything outside root."""
        # Lexical check (rejects `..`) so symlinked data folders still work.
        rel = os.path.normpath(urllib.parse.unquote(rel).lstrip("/"))
        if rel == ".":
            return self.root
        if rel.startswith("..") or os.path.isabs(rel):
            return None
        return self.root / rel

    def _rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    def _serve_file(self, path: Path, ctype: str | None = None, cache: bool = False):
        ctype = ctype or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "max-age=31536000" if cache else "no-store")
        self.end_headers()
        if self.command != "HEAD":
            with open(path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)

    # ---- routes --------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        path = url.path
        try:
            if path in ("/", "/index.html"):
                return self._serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path == "/api/info":
                return self._json({
                    "root": str(self.root), "name": self.root.name or str(self.root),
                    "version": __version__, "molstar": MOLSTAR_VERSION,
                })
            if path == "/api/list":
                return self._list(q.get("path", [""])[0])
            if path == "/api/find":
                return self._find(q.get("q", [""])[0])
            if path.startswith("/files/"):
                return self._file(path[len("/files/"):], raw="raw" in q)
            self._error(404, "not found")
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _static(self, name: str):
        if name in ("molstar.js", "molstar.css"):
            p = ensure_molstar_asset(name)
            if p is None:  # let the browser try the CDN directly
                self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
                self.send_header("Location", CDN.format(ver=MOLSTAR_VERSION, name=name))
                self.end_headers()
                return
            ctype = "text/css" if name.endswith(".css") else "application/javascript"
            return self._serve_file(p, ctype, cache=True)
        p = (STATIC_DIR / name).resolve()
        if STATIC_DIR.resolve() not in p.parents or not p.is_file():
            return self._error(404, "not found")
        return self._serve_file(p)

    def _list(self, rel: str):
        d = self._resolve(rel)
        if d is None or not d.is_dir():
            return self._error(404, f"no such folder: {rel}")
        entries = []
        try:
            it = list(os.scandir(d))
        except PermissionError:
            return self._error(403, "permission denied")
        for e in it:
            if not self.show_hidden and e.name.startswith("."):
                continue
            try:
                is_dir = e.is_dir()
                st = e.stat()
            except OSError:
                continue
            entries.append({
                "name": e.name,
                "path": self._rel(Path(e.path)),
                "dir": is_dir,
                "size": None if is_dir else st.st_size,
                "mtime": st.st_mtime,
                "kind": None if is_dir else classify(e.name),
            })
        entries.sort(key=lambda x: (not x["dir"], natural_key(x["name"])))
        self._json({"path": "" if d == self.root else self._rel(d), "entries": entries})

    def _find(self, query: str, limit: int = 3000):
        query = query.lower()
        out = []
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=True):
            if not self.show_hidden:
                dirnames[:] = [n for n in dirnames if not n.startswith(".")]
            dirnames[:] = [n for n in dirnames if n not in ("node_modules", "__pycache__")]
            for fn in filenames:
                kind = classify(fn)
                if not kind or (not self.show_hidden and fn.startswith(".")):
                    continue
                full = Path(dirpath) / fn
                rel = full.relative_to(self.root).as_posix()
                if query and query not in rel.lower():
                    continue
                try:
                    st = full.stat()
                except OSError:
                    continue
                out.append({"name": fn, "path": rel, "dir": False, "size": st.st_size,
                            "mtime": st.st_mtime, "kind": kind})
                if len(out) >= limit:
                    return self._json({"entries": out, "truncated": True})
        out.sort(key=lambda x: natural_key(x["path"]))
        self._json({"entries": out, "truncated": False})

    def _file(self, rel: str, raw: bool = False):
        p = self._resolve(rel)
        if p is None or not p.is_file():
            return self._error(404, f"no such file: {rel}")
        # Decompress .gz on the fly so every Mol* loader can read it.
        if p.name.lower().endswith(".gz") and not raw:
            with gzip.open(p, "rb") as f:
                data = f.read()
            return self._send(200, data, "application/octet-stream")
        return self._serve_file(p, "application/octet-stream")


def find_port(host: str, start: int, tries: int = 50) -> int:
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError as e:
                if e.errno != errno.EADDRINUSE:
                    raise
    raise SystemExit(f"no free port in {start}-{start + tries}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="molstar-lab",
        description="Open Mol* in your browser with a file browser rooted at a local folder (like `jupyter lab`).",
    )
    ap.add_argument("target", nargs="?", default=".", help="folder to serve, or a structure file to open (default: .)")
    ap.add_argument("-p", "--port", type=int, default=8890, help="port to try first (default 8890)")
    ap.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1 = this machine only)")
    ap.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    ap.add_argument("--hidden", action="store_true", help="show dotfiles / hidden folders")
    ap.add_argument("--version", action="version", version=f"molstar-lab {__version__} (Mol* {MOLSTAR_VERSION})")
    args = ap.parse_args(argv)

    target = Path(args.target).expanduser().resolve()
    if not target.exists():
        raise SystemExit(f"molstar-lab: {target} does not exist")
    open_rel = None
    if target.is_file():
        root = target.parent
        open_rel = target.name
    else:
        root = target

    LabHandler.root = root
    LabHandler.show_hidden = args.hidden

    # Warm the Mol* cache in the background so the first page load is fast.
    threading.Thread(target=lambda: [ensure_molstar_asset(n) for n in ("molstar.js", "molstar.css")],
                     daemon=True).start()

    port = find_port(args.host, args.port)
    httpd = ThreadingHTTPServer((args.host, port), LabHandler)
    shown_host = "localhost" if args.host in ("127.0.0.1", "0.0.0.0", "::") else args.host
    url = f"http://{shown_host}:{port}/"
    if open_rel:
        url += "?open=" + urllib.parse.quote(open_rel)

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"[molstar-lab] WARNING: listening on {args.host}; anyone who can reach this port can read files under {root}",
              file=sys.stderr)
    print(f"\n  Mol* Lab {__version__}  ·  Mol* {MOLSTAR_VERSION}")
    print(f"  Serving  {root}")
    print(f"  Open     {url}\n")
    print("  Press Ctrl+C to stop.\n")

    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[molstar-lab] shutting down.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
