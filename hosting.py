"""
hosting.py — TrustedBiz hosting layer
═════════════════════════════════════
What this file does:

  1. Static hosting from a ZIP (or one .html file): detects what was uploaded,
     inlines local CSS/JS/images so the site can live in the database, and
     publishes it as a normal multi-page TrustedBiz site.
  2. Python / Node app uploads: detected, validated and STORED SAFELY, but not
     run yet. They get the status "waiting_for_server" and visitors see an
     honest "coming online soon" page (HTTP 503), never a crash.
  3. The switch for later: set APP_HOSTING_ENABLED=true once a server exists.
     An admin then marks an app "running" with its upstream URL and TrustedBiz
     reverse-proxies the app's subdomain to it. The only piece that is NOT
     here is the thing that actually starts each customer's process on your
     server — see register_runner() below for exactly where that plugs in.
  4. Manage page, rollback to a previous snapshot, a docs page, a public
     capabilities endpoint, and a small admin screen for apps.

Wiring (app.py does this at the bottom):  hosting.init_hosting(app, deps)
"""
import os
import io
import re
import json
import base64
import hashlib
import zipfile
import mimetypes
import posixpath
from html import escape
from urllib.parse import unquote

import requests as _requests
from flask import (request, jsonify, redirect, flash, session, Response,
                   render_template_string)

try:
    import yaml
except ImportError:  # requirements.txt lists pyyaml; fail soft if it's missing
    yaml = None

# ── SWITCH + LIMITS ──────────────────────────────────────────────────────────
# Master switch. While false (default) no customer code ever runs.
APP_HOSTING_ENABLED = os.environ.get("APP_HOSTING_ENABLED", "false").strip().lower() in ("1", "true", "yes")

MAX_STATIC_ZIP_BYTES  = 8 * 1024 * 1024     # upload cap for any ZIP
MAX_APP_BUNDLE_BYTES  = 5 * 1024 * 1024     # stored app bundles (kept in DB for now)
MAX_UNZIPPED_BYTES    = 40 * 1024 * 1024    # zip-bomb guard (declared + actual)
MAX_FILES             = 600
MAX_INLINE_ASSET      = 400 * 1024          # one asset embedded into a page
MAX_INLINE_TOTAL      = 3 * 1024 * 1024     # all embedded assets, whole site
MAX_PAGES             = 40
MAX_SINGLE_HTML       = 1_500_000

APP_KINDS = ("python", "node")

# Statuses an app can have. Only the admin screen (or a registered runner) can
# move an app to "running", and only while APP_HOSTING_ENABLED is true.
APP_STATUSES = ("waiting_for_server", "running", "stopped", "failed")

_deps = None       # filled in by init_hosting()
_runner = None     # filled in by register_runner()


class UploadError(Exception):
    """A problem with the upload that we can explain to the user."""


class AppRuntimeUnavailable(Exception):
    """Raised when something tries to run an app while hosting is off."""


# ══════════════════════════════════════════════════════════════════════════════
# RUNNER HOOK — this is the one piece that needs a real server
# ══════════════════════════════════════════════════════════════════════════════
def register_runner(fn):
    """Plug in whatever starts customer apps on your server.

    fn(biz: dict, bundle_zip_bytes: bytes, config: dict) -> str
        Must start the app and return its upstream URL, e.g. "http://10.0.0.5:9001".
        TrustedBiz then marks the app running and reverse-proxies to that URL.

    Until a runner is registered, an admin can do the same thing by hand on
    /admin/hosting: deploy the bundle to the server yourself, then paste its URL.
    IMPORTANT before turning this on for strangers' code: run each app in its own
    container/user with CPU, memory, disk and network limits.
    """
    global _runner
    _runner = fn


def start_app(biz_id):
    if not APP_HOSTING_ENABLED:
        raise AppRuntimeUnavailable("App hosting is not enabled yet (APP_HOSTING_ENABLED is off).")
    if _runner is None:
        raise AppRuntimeUnavailable("No runner is registered yet. Use /admin/hosting to attach an upstream by hand.")
    d = _deps
    biz = d["db_fetchone"](d["q"]("SELECT * FROM business WHERE id=?"), (biz_id,))
    if not biz:
        raise AppRuntimeUnavailable("Site not found.")
    biz = dict(biz)
    bundle = load_bundle(biz_id)
    if bundle is None:
        raise AppRuntimeUnavailable("No stored bundle for this app.")
    config = _json_or_empty(biz.get("app_config"))
    upstream = _runner(biz, bundle, config)
    _set_app_state(biz_id, "running", upstream)
    return upstream


# ══════════════════════════════════════════════════════════════════════════════
# SCHEMA
# ══════════════════════════════════════════════════════════════════════════════
_NEW_COLUMNS = [
    ("app_kind",     "TEXT DEFAULT 'none'"),   # none | static | python | node
    ("app_status",   "TEXT DEFAULT 'none'"),   # none | waiting_for_server | running | stopped | failed
    ("app_runtime",  "TEXT"),
    ("app_config",   "TEXT"),                  # JSON: parsed trustedbiz.yaml + detected start command
    ("app_upstream", "TEXT"),
]


def _business_columns():
    d = _deps
    if d["USE_POSTGRES"]:
        rows = d["db_fetchall"]("SELECT column_name FROM information_schema.columns WHERE table_name='business'")
        return {r["column_name"] for r in rows}
    rows = d["db_fetchall"]("PRAGMA table_info(business)")
    return {r[1] for r in rows}


def ensure_schema():
    """Idempotent. Safe to call on every boot and from /admin/migrate-db."""
    d = _deps
    try:
        have = _business_columns()
        for col, ddl in _NEW_COLUMNS:
            if col not in have:
                d["db_execute"](f"ALTER TABLE business ADD COLUMN {col} {ddl}")
        if d["USE_POSTGRES"]:
            d["db_execute"]("CREATE TABLE IF NOT EXISTS app_bundles (id SERIAL PRIMARY KEY, business_id INTEGER, filename TEXT, size INTEGER, sha256 TEXT, data_b64 TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        else:
            d["db_execute"]("CREATE TABLE IF NOT EXISTS app_bundles (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, filename TEXT, size INTEGER, sha256 TEXT, data_b64 TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        return True
    except Exception as e:
        print(f"[hosting] ensure_schema error: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# ZIP READING (safe)
# ══════════════════════════════════════════════════════════════════════════════
def _read_member(zf, info, limit):
    with zf.open(info) as fh:
        data = fh.read(limit + 1)
    if len(data) > limit:
        raise UploadError(f"“{info.filename}” is larger than the allowed size.")
    return data


class Project:
    """A cleaned view of an uploaded ZIP: safe paths, one top folder stripped."""

    def __init__(self, raw):
        try:
            self.zf = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile:
            raise UploadError("That file is not a valid ZIP archive.")
        members, total = [], 0
        for info in self.zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            parts = name.split("/")
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in parts:
                raise UploadError("The ZIP contains an unsafe file path, so it was rejected.")
            if (parts[0] == "__MACOSX" or parts[-1] in (".DS_Store", "Thumbs.db")
                    or parts[-1].startswith("._") or ".git" in parts or "node_modules" in parts
                    or "__pycache__" in parts):
                continue
            total += info.file_size
            if total > MAX_UNZIPPED_BYTES:
                raise UploadError("The ZIP expands to more than 40 MB, which is over the limit.")
            members.append((name, info))
        if not members:
            raise UploadError("The ZIP is empty.")
        if len(members) > MAX_FILES:
            raise UploadError(f"The ZIP has {len(members)} files; the limit is {MAX_FILES}.")
        # GitHub-style ZIPs wrap everything in one folder — strip it.
        firsts = {n.split("/")[0] for n, _ in members}
        if len(firsts) == 1 and all("/" in n for n, _ in members):
            cut = len(next(iter(firsts))) + 1
            members = [(n[cut:], i) for n, i in members]
        self.files = {n: i for n, i in members}
        self.names = list(self.files)
        self._cache = {}

    def has(self, path):
        return path in self.files

    def read(self, path, limit=MAX_UNZIPPED_BYTES):
        if path not in self._cache:
            self._cache[path] = _read_member(self.zf, self.files[path], limit)
        return self._cache[path]

    def text(self, path, limit=2_000_000):
        return self.read(path, limit).decode("utf-8", errors="replace")


# ══════════════════════════════════════════════════════════════════════════════
# DETECTION
# ══════════════════════════════════════════════════════════════════════════════
_BUILT_DIRS = ("dist", "build", "public", "docs", "out", "_site")


def _static_root(p):
    """Folder that holds the deployable index.html, or None."""
    if p.has("index.html"):
        return ""
    for d in _BUILT_DIRS:
        if p.has(f"{d}/index.html"):
            return d + "/"
    return None


def detect_project(p):
    """Returns dict(kind, root, runtime, notes). kind is one of
    static | python | node | needs_build | unknown."""
    py_markers = [n for n in ("requirements.txt", "pyproject.toml", "Pipfile", "wsgi.py", "manage.py") if p.has(n)]
    py_entry = [n for n in ("app.py", "main.py", "server.py", "wsgi.py", "manage.py") if p.has(n)]
    if py_markers or py_entry:
        return {"kind": "python", "root": "", "runtime": "python"}

    if p.has("package.json"):
        try:
            pkg = json.loads(p.text("package.json"))
        except Exception:
            pkg = {}
        scripts = pkg.get("scripts") or {}
        deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
        server_like = any(k in deps for k in ("express", "fastify", "koa", "hapi", "@nestjs/core", "next"))
        if "start" in scripts and (server_like or not _static_root(p)):
            return {"kind": "node", "root": "", "runtime": "node"}
        root = _static_root(p)
        if root == "" and "build" in scripts and re.search(r'src\s*=\s*["\'](?:\./|/)?src/', p.text("index.html", 200_000), re.I):
            root = None   # unbuilt Vite/React source: index.html loads /src/..., so it would be blank
        if root is not None:
            return {"kind": "static", "root": root, "runtime": "static"}
        if "build" in scripts:
            return {"kind": "needs_build", "root": "", "runtime": "node"}
        if p.has("server.js") or p.has("index.js"):
            return {"kind": "node", "root": "", "runtime": "node"}

    root = _static_root(p)
    if root is not None:
        return {"kind": "static", "root": root, "runtime": "static"}
    if any(n.lower().endswith(".html") for n in p.names):
        return {"kind": "unknown", "root": "", "runtime": None,
                "hint": "I found HTML files but no index.html at the top of the ZIP."}
    return {"kind": "unknown", "root": "", "runtime": None}


# ── trustedbiz.yaml ──────────────────────────────────────────────────────────
_YAML_KEYS = {"name", "type", "runtime", "build", "start", "env"}


def parse_config(p):
    """Reads trustedbiz.yaml / .yml if present. Returns (config_dict, warnings)."""
    warnings, cfg = [], {}
    path = next((n for n in ("trustedbiz.yaml", "trustedbiz.yml") if p.has(n)), None)
    if not path:
        return cfg, warnings
    if yaml is None:
        return cfg, ["trustedbiz.yaml was found but the server can't read YAML yet (pyyaml missing)."]
    try:
        data = yaml.safe_load(p.text(path, 20_000)) or {}
    except Exception:
        return cfg, ["trustedbiz.yaml could not be parsed, so it was ignored."]
    if not isinstance(data, dict):
        return cfg, ["trustedbiz.yaml must be a key: value file, so it was ignored."]
    for k, v in data.items():
        if k not in _YAML_KEYS:
            warnings.append(f"trustedbiz.yaml: unknown key “{str(k)[:30]}” ignored.")
            continue
        if k == "env":
            if isinstance(v, dict):
                warnings.append("trustedbiz.yaml: list env variable NAMES only. Never put secret values in this file. env was ignored.")
                continue
            if isinstance(v, list):
                names = [str(x)[:60] for x in v if re.match(r"^[A-Z_][A-Z0-9_]*$", str(x))]
                cfg["env"] = names[:50]
            continue
        if isinstance(v, (str, int, float)):
            cfg[k] = str(v)[:200]
    return cfg, warnings


def _procfile_start(p):
    if p.has("Procfile"):
        for line in p.text("Procfile", 5000).splitlines():
            if line.lower().startswith("web:"):
                return line.split(":", 1)[1].strip()[:200]
    return None


# ══════════════════════════════════════════════════════════════════════════════
# STATIC SITE BUILD (inlining)
# ══════════════════════════════════════════════════════════════════════════════
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.\-]*:|//|#)", re.I)
_TAG_ATTR = lambda name: re.compile(r"""\b%s\s*=\s*(["'])(.*?)\1""" % name, re.I | re.S)
_RE_LINK   = re.compile(r"<link\b[^>]*>", re.I)
_RE_SCRIPT = re.compile(r"<script\b([^>]*?)\bsrc\s*=\s*([\"'])(.*?)\2([^>]*)>\s*</script>", re.I | re.S)
_RE_MEDIA  = re.compile(r"(<(?:img|source|video|audio|input)\b[^>]*?\b(?:src|poster)\s*=\s*)([\"'])(.*?)\2", re.I | re.S)
_RE_HREF   = re.compile(r"""(<a\b[^>]*?\bhref\s*=\s*)(["'])(.*?)\2""", re.I | re.S)
_RE_CSSURL = re.compile(r"""url\(\s*(["']?)(.*?)\1\s*\)""", re.I)


class _Inliner:
    def __init__(self, project, root):
        self.p, self.root = project, root
        self.budget = MAX_INLINE_TOTAL
        self.warnings = set()
        self.inlined = 0

    def resolve(self, ref, base_dir=""):
        ref = (ref or "").strip()
        if not ref or _EXTERNAL.match(ref):
            return None
        ref = unquote(ref.split("#")[0].split("?")[0])
        if ref.startswith("/"):
            path = posixpath.normpath(self.root + ref.lstrip("/"))
        else:
            path = posixpath.normpath(posixpath.join(self.root + base_dir, ref))
        if path.startswith("..") or not self.p.has(path):
            return None
        return path

    def data_uri(self, path, allowed_prefixes=("image/", "font/", "application/font", "application/x-font")):
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if path.lower().endswith((".woff", ".woff2", ".ttf", ".otf")):
            mime = "font/" + path.rsplit(".", 1)[1].lower()
        if not mime.startswith(allowed_prefixes):
            self.warnings.add(f"“{path}” was not embedded (type not supported for embedding).")
            return None
        size = self.p.files[path].file_size
        if size > MAX_INLINE_ASSET:
            self.warnings.add(f"“{path}” is over {MAX_INLINE_ASSET // 1024} KB so it was not embedded. Host big images elsewhere (e.g. Cloudinary) and link them.")
            return None
        if size > self.budget:
            self.warnings.add(f"“{path}” was not embedded: the site's total embedded-file budget is used up.")
            return None
        data = self.p.read(path, MAX_INLINE_ASSET)
        self.budget -= len(data)
        self.inlined += 1
        return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")

    def css(self, text, css_dir):
        def repl(m):
            quote, ref = m.group(1), m.group(2)
            target = self.resolve(ref, css_dir)
            if target:
                uri = self.data_uri(target)
                if uri:
                    return f'url("{uri}")'
            return m.group(0)
        return _RE_CSSURL.sub(repl, text)

    def page(self, html):
        # 1. stylesheets
        def link_repl(m):
            tag = m.group(0)
            rel = _TAG_ATTR("rel").search(tag)
            href = _TAG_ATTR("href").search(tag)
            if not rel or not href:
                return tag
            rels = rel.group(2).lower().split()
            target = self.resolve(href.group(2))
            if not target:
                return tag
            if "stylesheet" in rels:
                css = self.p.text(target)
                if len(css) > self.budget:
                    self.warnings.add(f"“{target}” was not embedded: embedded-file budget used up.")
                    return tag
                self.budget -= len(css)
                self.inlined += 1
                css = self.css(css, posixpath.dirname(target[len(self.root):]))
                media = _TAG_ATTR("media").search(tag)
                media_attr = f' media="{escape(media.group(2))}"' if media else ""
                return f"<style{media_attr}>\n{css}\n</style>"
            if "icon" in rels or "shortcut" in rels:
                uri = self.data_uri(target)
                if uri:
                    return tag.replace(href.group(0), f'href="{uri}"')
            return tag
        html = _RE_LINK.sub(link_repl, html)

        # 2. scripts
        def script_repl(m):
            before, _, src, after = m.group(1), m.group(2), m.group(3), m.group(4)
            target = self.resolve(src)
            if not target:
                return m.group(0)
            js = self.p.text(target)
            if len(js) > self.budget:
                self.warnings.add(f"“{target}” was not embedded: embedded-file budget used up.")
                return m.group(0)
            self.budget -= len(js)
            self.inlined += 1
            js = js.replace("</script", "<\\/script")
            attrs = re.sub(r"\s+(?:defer|async)\b", "", (before + after))
            return f"<script{attrs}>\n{js}\n</script>"
        html = _RE_SCRIPT.sub(script_repl, html)

        # 3. images (and other src/poster media)
        def media_repl(m):
            prefix, quote, ref = m.group(1), m.group(2), m.group(3)
            target = self.resolve(ref)
            if not target:
                return m.group(0)
            uri = self.data_uri(target, allowed_prefixes=("image/",))
            if not uri:
                return m.group(0)
            return f"{prefix}{quote}{uri}{quote}"
        html = _RE_MEDIA.sub(media_repl, html)

        # 4. links between pages: about.html -> about
        def href_repl(m):
            prefix, quote, ref = m.group(1), m.group(2), m.group(3)
            if _EXTERNAL.match(ref.strip()) and not ref.strip().startswith("#"):
                return m.group(0)
            if ref.strip().startswith("#"):
                return m.group(0)
            core, sep, tail = re.match(r"^([^#?]*)([#?].*)?$", ref.strip()).group(1), "", (re.match(r"^([^#?]*)([#?].*)?$", ref.strip()).group(2) or "")
            if core.lower().endswith(".html"):
                slug = _slug(posixpath.basename(core)[:-5])
                if "/" in core.strip("./"):
                    self.warnings.add(f"Link “{core}” points into a sub-folder; sub-folder pages are not supported yet.")
                    return m.group(0)
                return f"{prefix}{quote}{slug}{tail}{quote}"
            return m.group(0)
        html = _RE_HREF.sub(href_repl, html)
        return html


def _slug(stem):
    s = re.sub(r"[^a-z0-9\-]+", "-", stem.lower()).strip("-")
    return s or "page"


def build_static_site(p, root):
    """Returns (pages, order, labels, warnings, stats)."""
    inl = _Inliner(p, root)
    top_html = [n for n in p.names
                if n.startswith(root) and n.lower().endswith(".html")
                and "/" not in n[len(root):] and n[len(root):].lower() != "404.html"]
    nested = [n for n in p.names if n.startswith(root) and n.lower().endswith(".html") and "/" in n[len(root):]]
    if not top_html:
        raise UploadError("No index.html found at the top of the site.")
    if len(top_html) > MAX_PAGES:
        raise UploadError(f"A site can have at most {MAX_PAGES} pages.")

    pages, labels, taken = {}, {}, set()
    for n in sorted(top_html, key=lambda x: (x[len(root):].lower() != "index.html", x.lower())):
        stem = n[len(root):-5]
        slug = _slug(stem)
        base, i = slug, 2
        while slug in taken:
            slug = f"{base}-{i}"; i += 1
        taken.add(slug)
        raw = p.text(n, MAX_SINGLE_HTML)
        pages[slug] = inl.page(raw)
        title = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
        labels[slug] = "Home" if slug == "index" else (
            re.sub(r"\s+", " ", title.group(1)).strip()[:40] if title and title.group(1).strip() else slug.replace("-", " ").title())
    if "index" not in pages:
        raise UploadError("No index.html found at the top of the site.")
    order = ["index"] + [s for s in pages if s != "index"]
    warnings = sorted(inl.warnings)
    if nested:
        warnings.append(f"{len(nested)} page(s) in sub-folders were skipped. For now only top-level pages are published.")
    stats = {"pages": len(pages), "embedded_files": inl.inlined}
    return pages, order, labels, warnings, stats


# ══════════════════════════════════════════════════════════════════════════════
# DEPLOY ENTRY POINT (called from app.py's /deploy route)
# ══════════════════════════════════════════════════════════════════════════════
def _json_or_empty(s):
    try:
        v = json.loads(s) if s else {}
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _set_app_state(biz_id, status, upstream=None):
    d = _deps
    d["db_execute"](d["q"]("UPDATE business SET app_status=?, app_upstream=? WHERE id=?"), (status, upstream, biz_id))


def _store_bundle(biz_id, filename, raw):
    d = _deps
    d["db_execute"](d["q"]("DELETE FROM app_bundles WHERE business_id=?"), (biz_id,))
    d["db_insert"](d["q"]("INSERT INTO app_bundles (business_id, filename, size, sha256, data_b64) VALUES (?,?,?,?,?)"),
                   (biz_id, filename[:200], len(raw), hashlib.sha256(raw).hexdigest(), base64.b64encode(raw).decode("ascii")))


def load_bundle(biz_id):
    d = _deps
    row = d["db_fetchone"](d["q"]("SELECT data_b64 FROM app_bundles WHERE business_id=? ORDER BY id DESC"), (biz_id,))
    if not row:
        return None
    row = dict(row)
    return base64.b64decode(row["data_b64"]) if row.get("data_b64") else None


def clean_phone(raw):
    """Digits only; 9-15 long, else None."""
    digits = re.sub(r"\D", "", raw or "")
    return digits if 9 <= len(digits) <= 15 else None


def start_trial(biz_id, phone):
    """Starts the free-trial clock the billing job already understands
    (is_premium + free_trial_end + payment_phone). Same fields go-live sets."""
    from datetime import date, timedelta
    d = _deps
    trial_end = (date.today() + timedelta(days=d["HOSTING_TRIAL_DAYS"])).isoformat()
    d["db_execute"](d["q"]("UPDATE business SET is_premium=1, free_trial_end=?, payment_phone=? WHERE id=?"),
                    (trial_end, phone, biz_id))
    return trial_end


def deploy_project(user, name, category, whatsapp, brand_color, description, upload, phone=None):
    """Handle an uploaded .zip or .html. Returns dict:
    {ok, message, biz_id, kind, warnings}. Never raises UploadError."""
    d = _deps
    try:
        filename = (upload.filename or "").strip()
        low = filename.lower()
        if not (low.endswith(".zip") or low.endswith(".html")):
            raise UploadError("Please upload a .zip or a single .html file.")
        raw = upload.read(MAX_STATIC_ZIP_BYTES + 1)
        if len(raw) > MAX_STATIC_ZIP_BYTES:
            raise UploadError("That file is over 8 MB. Remove big media files and try again.")
        if not raw:
            raise UploadError("That file is empty.")
        if not name:
            raise UploadError("Site name is required.")

        warnings, config, kind, pages, order, labels = [], {}, "static", None, None, None

        if low.endswith(".html"):
            html = raw.decode("utf-8", errors="replace")
            if len(html) < 20:
                raise UploadError("That HTML file looks too short to be a real page.")
            pages, order, labels = {"index": html}, ["index"], {"index": "Home"}
        else:
            p = Project(raw)
            det = detect_project(p)
            kind = det["kind"]
            if kind == "needs_build":
                raise UploadError("This looks like a project that must be built first (it has a build script but no built folder). "
                                  "Run the build locally and upload the dist/ or build/ folder as the ZIP instead.")
            if kind == "unknown":
                raise UploadError((det.get("hint") or "I couldn't tell what this ZIP is.") +
                                  " A static site needs index.html at the top; a Python app needs requirements.txt or app.py; a Node app needs package.json with a start script.")
            config, cw = parse_config(p)
            warnings += cw
            if kind == "static":
                pages, order, labels, bw, stats = build_static_site(p, det["root"])
                warnings += bw
            else:
                config["detected_start"] = config.get("start") or _procfile_start(p)
                if len(raw) > MAX_APP_BUNDLE_BYTES:
                    raise UploadError("App bundles are limited to 5 MB for now. Remove virtual environments, node_modules and media files.")

        slug = d["make_slug"](name)
        if kind == "static":
            phone = clean_phone(phone)
            if not phone:
                raise UploadError("Enter your mobile money number (MTN or Airtel) so we can bill you after the free trial.")
            html_blob = d["_encode_site"](pages, order, labels)
            biz_id = d["db_insert"](
                d["q"]("INSERT INTO business (name, category, whatsapp, description, brand_color, slug, owner_id, status, plan, is_premium, generated_html) VALUES (?,?,?,?,?,?,?,?,?,?,?)"),
                (name, category, whatsapp, description, brand_color, slug, user["id"], "approved", "free", 0, html_blob))
            d["db_execute"](d["q"]("UPDATE business SET app_kind='static', app_status='none', app_runtime='static' WHERE id=?"), (biz_id,))
            start_trial(biz_id, phone)
            d["snapshot_site_html"](biz_id, html_blob)
            try:
                d["ping_google"](slug)
            except Exception:
                pass
            d["log_deploy_event"](biz_id, user["id"], "deploy", f'"{name}" deployed as a static site ({len(pages)} page(s)). {d["HOSTING_TRIAL_DAYS"]}-day free trial started', "ok")
            return {"ok": True, "biz_id": biz_id, "kind": "static", "warnings": warnings, "slug": slug,
                    "message": f'🚀 "{name}" is LIVE at {slug}.trustedbiz.co.ug ({len(pages)} page{"s" if len(pages) != 1 else ""}). Your {d["HOSTING_TRIAL_DAYS"]}-day free trial has started.'}

        # python / node: store it, don't run it
        biz_id = d["db_insert"](
            d["q"]("INSERT INTO business (name, category, whatsapp, description, brand_color, slug, owner_id, status, plan, is_premium) VALUES (?,?,?,?,?,?,?,?,?,?)"),
            (name, category, whatsapp, description, brand_color, slug, user["id"], "approved", "free", 0))
        d["db_execute"](d["q"]("UPDATE business SET app_kind=?, app_status='waiting_for_server', app_runtime=?, app_config=? WHERE id=?"),
                        (kind, det["runtime"], json.dumps(config), biz_id))
        _store_bundle(biz_id, filename, raw)
        d["log_deploy_event"](biz_id, user["id"], "app_upload",
                              f'"{name}" ({kind} app) uploaded and stored. Waiting for app servers to launch.', "pending")
        label = "Python" if kind == "python" else "Node"
        return {"ok": True, "biz_id": biz_id, "kind": kind, "warnings": warnings, "slug": slug,
                "message": f'📦 Your {label} app "{name}" is uploaded and stored safely. App hosting launches soon, and it will go live automatically then.'}
    except UploadError as e:
        return {"ok": False, "message": str(e), "warnings": [], "kind": None, "biz_id": None}
    except Exception as e:
        print(f"[hosting] deploy_project error: {e}")
        return {"ok": False, "message": "Something went wrong while deploying. Nothing was published.", "warnings": [], "kind": None, "biz_id": None}


# ══════════════════════════════════════════════════════════════════════════════
# SERVING: gate, waiting page, reverse proxy
# ══════════════════════════════════════════════════════════════════════════════
_WAIT_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><meta name="robots" content="noindex">
<title>{{ name }} — coming online soon</title>
<style>
:root{--bg:#f5f8f8;--surface:#fff;--border:#d8e4e4;--text:#0d1c1c;--mid:#43605f;--brand:#2b7a78;}
@media (prefers-color-scheme: dark){:root{--bg:#0d1412;--surface:#141d1b;--border:#233230;--text:#eef5f4;--mid:#a9c4c1;}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,'Segoe UI',sans-serif;padding:24px}
.card{max-width:460px;background:var(--surface);border:1px solid var(--border);padding:32px 28px;text-align:center}
h1{font-size:22px;margin:0 0 10px}p{color:var(--mid);line-height:1.6;font-size:14.5px;margin:0 0 10px}
.badge{display:inline-block;font:600 11px ui-monospace,monospace;letter-spacing:.5px;text-transform:uppercase;color:var(--brand);border:1px solid var(--brand);padding:3px 8px;margin-bottom:16px}
a{color:var(--brand)}
</style></head><body><div class="card">
<span class="badge">Coming online soon</span>
<h1>{{ name }}</h1>
{% if owner %}
<p>Your {{ kind }} app is uploaded and stored safely on TrustedBiz. App hosting is not switched on yet, so it can't serve visitors for now.</p>
<p>It will go live on its own address when app servers launch. <a href="/hosting/site/{{ biz_id }}">Manage this app</a></p>
{% else %}
<p>This app is being set up and isn't available yet. Please check back soon.</p>
{% endif %}
<p style="font-size:12px;margin-top:18px">Hosted on <a href="https://trustedbiz.co.ug">TrustedBiz</a></p>
</div></body></html>"""

_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
        "transfer-encoding", "upgrade", "host", "content-length", "content-encoding"}


def _is_owner_or_admin(row):
    return bool(session.get("admin_auth")) or (bool(session.get("user_id")) and row.get("owner_id") == session.get("user_id"))


def _waiting_response(row):
    html = render_template_string(_WAIT_PAGE, name=row.get("name") or "App", kind=("Python" if row.get("app_kind") == "python" else "Node"),
                                  owner=_is_owner_or_admin(row), biz_id=row.get("id"))
    resp = Response(html, status=503, mimetype="text/html")
    resp.headers["Retry-After"] = "3600"
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


def _valid_upstream(u):
    return bool(u) and re.match(r"^https?://[^\s/]+", u) is not None


def _proxy(upstream, path):
    url = upstream.rstrip("/") + "/" + path.lstrip("/")
    if request.query_string:
        url += "?" + request.query_string.decode("utf-8", errors="replace")
    headers = {k: v for k, v in request.headers if k.lower() not in _HOP}
    headers["X-Forwarded-Host"] = request.host
    headers["X-Forwarded-Proto"] = request.headers.get("X-Forwarded-Proto", request.scheme)
    headers["X-Forwarded-For"] = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    try:
        r = _requests.request(request.method, url, data=request.get_data(), headers=headers,
                              allow_redirects=False, timeout=(5, 60))
    except _requests.RequestException:
        return Response("This app isn't responding right now. Please try again in a moment.", status=502, mimetype="text/plain")
    resp = Response(r.content, status=r.status_code)
    for k, v in r.headers.items():
        if k.lower() not in _HOP and k.lower() != "set-cookie":
            resp.headers[k] = v
    try:
        for c in r.raw.headers.getlist("Set-Cookie"):
            resp.headers.add("Set-Cookie", c)
    except Exception:
        pass
    return resp


def _row_for_slug(slug):
    d = _deps
    if not d:
        return None
    try:
        row = d["db_fetchone"](d["q"]("SELECT id, name, slug, status, owner_id, app_kind, app_status, app_upstream FROM business WHERE slug=?"), (slug,))
    except Exception:
        return None   # columns not created yet: behave like before
    return dict(row) if row else None


def _live(row):
    return (APP_HOSTING_ENABLED and row.get("app_status") == "running" and _valid_upstream(row.get("app_upstream")))


def subdomain_app_response(slug):
    """Called by app.py for every <slug>.trustedbiz.co.ug request. Returns a
    Response for app sites, or None so normal static handling continues."""
    row = _row_for_slug(slug)
    if not row or (row.get("app_kind") or "none") not in APP_KINDS:
        return None
    if row.get("status") != "approved" and not _is_owner_or_admin(row):
        return None
    if _live(row):
        return _proxy(row["app_upstream"], request.path)
    return _waiting_response(row)


def app_gate_response(bd):
    """Called inside site() (the /site/<slug> route). None = carry on as normal."""
    if (bd.get("app_kind") or "none") not in APP_KINDS:
        return None
    if _live(bd):
        return redirect(f"https://{bd.get('slug')}.trustedbiz.co.ug", code=302)
    return _waiting_response(bd)


# ══════════════════════════════════════════════════════════════════════════════
# PAGES: capabilities, docs, manage, admin
# ══════════════════════════════════════════════════════════════════════════════
_STYLE = """
:root{--brand:#2b7a78;--bg:#f5f8f8;--surface:#fff;--border:#d8e4e4;--text:#0d1c1c;--mid:#43605f;--dim:#6f8c8b;--font:'DM Sans',system-ui,sans-serif;--mono:'DM Mono',ui-monospace,monospace;}
@media (prefers-color-scheme: dark){:root{--bg:#0d1412;--surface:#141d1b;--border:#233230;--text:#eef5f4;--mid:#a9c4c1;--dim:#7d9a97;}}
*{box-sizing:border-box;margin:0;padding:0}body{font-family:var(--font);background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased;line-height:1.55}
a{color:var(--brand);text-decoration:none}header{border-bottom:1px solid var(--border);padding:0 20px;height:56px;display:flex;justify-content:space-between;align-items:center}
.logo{font-family:var(--mono);font-weight:500;color:var(--text)}.logo span{color:var(--brand)}
.wrap{max-width:820px;margin:0 auto;padding:36px 20px 72px}h1{font-size:26px;font-weight:800;letter-spacing:-.5px;margin-bottom:6px}
h2{font-size:17px;font-weight:700;margin:30px 0 10px}p,li{font-size:14.5px;color:var(--mid)}ul{padding-left:20px}li{margin:4px 0}
.card{background:var(--surface);border:1px solid var(--border);padding:18px 18px;margin:12px 0}
table{width:100%;border-collapse:collapse;font-size:13.5px}td,th{border-bottom:1px solid var(--border);padding:9px 8px;text-align:left;vertical-align:top;color:var(--mid)}th{color:var(--text);font-weight:700}
.tag{display:inline-block;font:600 10.5px var(--mono);letter-spacing:.4px;text-transform:uppercase;padding:2px 7px;border:1px solid var(--border);color:var(--dim)}
.tag.live{color:#16a34a;border-color:rgba(22,163,74,.4)}.tag.soon{color:#b7791f;border-color:rgba(183,121,31,.45)}
code,pre{font-family:var(--mono);font-size:12.5px}pre{background:var(--surface);border:1px solid var(--border);padding:12px;overflow:auto;color:var(--text)}
.btn{display:inline-block;padding:8px 14px;border:1.5px solid var(--border);color:var(--text);font-size:13px;font-weight:600;background:transparent;cursor:pointer;font-family:inherit}
.btn.solid{background:var(--text);color:var(--bg);border-color:var(--text)}input,select{padding:8px 10px;border:1.5px solid var(--border);background:var(--bg);color:var(--text);font-family:inherit;font-size:13px}
.row{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);font-size:13.5px;color:var(--mid)}.row:last-child{border:none}
"""

_FEATURES = [
    # (name, state, note)
    ("Static site hosting (ZIP or single HTML)", "live", "Free subdomain. Local CSS, JS and small images are embedded automatically."),
    ("Multi-page static sites", "live", "Top-level .html pages. Links like about.html are converted for you."),
    ("Custom domains", "live", "Request a domain from your dashboard and follow the DNS steps."),
    ("Deploy history", "live", "Every deploy, edit and rollback is logged."),
    ("Snapshots and one-click rollback", "live", "A snapshot is saved on every change. The last 5 are kept."),
    ("Python / Flask app upload", "soon", "Uploads are accepted and stored now. They start running when app servers launch."),
    ("Node app upload", "soon", "Same as Python: stored now, runs at launch."),
    ("trustedbiz.yaml config", "soon", "Read and validated on upload today. Used to run your app at launch."),
    ("Background workers and scheduled tasks", "soon", "Planned."),
    ("Managed databases (Postgres, Redis)", "soon", "Planned."),
    ("REST API and CLI", "soon", "Planned."),
    ("Autoscaling, preview environments, region choice", "soon", "Planned."),
]


def _caps():
    return {
        "static_hosting": True,
        "app_hosting": {"available": APP_HOSTING_ENABLED, "status": "live" if APP_HOSTING_ENABLED else "coming_soon",
                        "runtimes": ["python", "node"]},
        "limits": {"zip_mb": MAX_STATIC_ZIP_BYTES // (1024 * 1024), "app_bundle_mb": MAX_APP_BUNDLE_BYTES // (1024 * 1024),
                   "max_files": MAX_FILES, "max_pages": MAX_PAGES},
        "features": [{"name": n, "state": s} for n, s, _ in _FEATURES],
    }


_DOCS = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hosting docs | TrustedBiz</title><style>{{ style|safe }}</style></head><body>
<header><a class="logo" href="/">Trusted<span>Biz</span></a><a class="btn" href="/dashboard#sites">Dashboard</a></header>
<div class="wrap">
<h1>Hosting docs</h1><p>Deploy a website or app on TrustedBiz. Pay by MTN or Airtel Money.</p>

<h2>What works today</h2>
<table><tr><th>Feature</th><th>Status</th></tr>
{% for n, s, note in features %}<tr><td><b>{{ n }}</b><br><span style="font-size:12.5px">{{ note }}</span></td>
<td><span class="tag {{ s }}">{{ 'Live' if s == 'live' else 'Coming soon' }}</span></td></tr>{% endfor %}</table>

<h2>Deploy a static site</h2>
<ol style="padding-left:20px"><li>Put <code>index.html</code> at the top of a ZIP, with your other pages next to it.</li>
<li>Dashboard → Projects → Deploy site or app. Enter your mobile money number, choose the ZIP, press Deploy.</li>
<li>Your site goes live at <code>yourname.trustedbiz.co.ug</code>.</li></ol>
<p style="margin-top:8px">Built with React, Vite or similar? Run the build on your computer and zip the <code>dist/</code> or <code>build/</code> folder.</p>

<h2>Limits</h2>
<ul><li>ZIP up to {{ caps.limits.zip_mb }} MB, up to {{ caps.limits.max_files }} files, up to {{ caps.limits.max_pages }} pages.</li>
<li>Each embedded image or font up to 400 KB; 3 MB embedded in total. Bigger media should be hosted elsewhere and linked.</li>
<li>Only top-level pages are published. Pages in sub-folders are skipped for now.</li></ul>

<h2>Python and Node apps</h2>
<p>You can upload them now. TrustedBiz detects the project, checks it, and stores it. Until app servers launch the app's address shows a “coming online soon” page, and it starts serving automatically at launch.</p>
<ul><li><b>Python:</b> include <code>requirements.txt</code> and an entry such as <code>app.py</code>. A <code>Procfile</code> line like <code>web: gunicorn app:app</code> tells us how to start it.</li>
<li><b>Node:</b> include <code>package.json</code> with a <code>start</code> script.</li>
<li>Don't include secrets, <code>.env</code> files, virtual environments or <code>node_modules</code>.</li></ul>

<h2>trustedbiz.yaml (optional)</h2>
<pre>name: my-app
type: web
runtime: python
build: pip install -r requirements.txt
start: gunicorn app:app
env:
  - DATABASE_URL
  - SECRET_KEY</pre>
<p><code>env</code> lists variable <b>names</b> only. Never put secret values in this file.</p>

<h2>Pricing and billing</h2>
<p>The first {{ trial }} days are free. After that a site costs UGX {{ monthly }} per month or UGX {{ yearly }} per year, paid with MTN or Airtel Money. Python and Node apps are not billed until app hosting launches.</p>

<h2>Rollback</h2>
<p>Open a site's <b>Manage</b> page from your dashboard to restore any of the last 5 snapshots.</p>
</div></body></html>"""


_MANAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ b.name }} | Manage</title><style>{{ style|safe }}</style></head><body>
<header><a class="logo" href="/">Trusted<span>Biz</span></a><a class="btn" href="/dashboard#sites">← Dashboard</a></header>
<div class="wrap">
<h1>{{ b.name }}</h1>
<p>{{ b.slug }}.trustedbiz.co.ug &nbsp;
{% if is_app %}<span class="tag {{ 'live' if live else 'soon' }}">{{ (b.app_kind|capitalize) ~ ' app · ' ~ ('Running' if live else 'Waiting for server') }}</span>
{% else %}<span class="tag live">Static site</span>{% endif %}</p>

{% if is_app %}
<div class="card"><b>About this app</b>
<p style="margin-top:6px">Your app is stored safely{% if bundle %} ({{ bundle.size // 1024 }} KB){% endif %}. App hosting is not switched on yet, so it isn't serving visitors. It will start automatically when app servers launch.</p>
{% if cfg %}<ul style="margin-top:8px">
{% if cfg.get('detected_start') %}<li>Start command: <code>{{ cfg.get('detected_start') }}</code></li>{% endif %}
{% if cfg.get('build') %}<li>Build command: <code>{{ cfg.get('build') }}</code></li>{% endif %}
{% if cfg.get('env') %}<li>Environment variables: <code>{{ cfg.get('env')|join(', ') }}</code></li>{% endif %}</ul>{% endif %}
<p style="margin-top:8px">To update it, deploy a new ZIP from your dashboard.</p></div>
{% else %}
<div class="card"><b>Snapshots</b>
<p style="margin:4px 0 8px">Restore an earlier version of this site. The last 5 are kept.</p>
{% for s in backups %}<div class="row"><span>{{ s.created_at }} · {{ (s.size // 1024) }} KB{% if loop.first %} · latest{% endif %}</span>
{% if not loop.first %}<form method="POST" action="/hosting/rollback/{{ b.id }}/{{ s.id }}" onsubmit="return confirm('Restore this version? Your current version stays in snapshots.')"><button class="btn" type="submit">Restore</button></form>{% endif %}</div>
{% else %}<p>No snapshots yet.</p>{% endfor %}</div>
{% endif %}

<div class="card"><b>Deploy history</b>
{% for e in events %}<div class="row"><span>{{ e.message }}</span><span class="tag">{{ e.status }}</span></div>
{% else %}<p style="margin-top:6px">Nothing yet.</p>{% endfor %}</div>
<p style="margin-top:18px"><a href="/docs">Hosting docs</a></p>
</div></body></html>"""


_ADMIN = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>App hosting | Admin</title><style>{{ style|safe }}</style></head><body>
<header><a class="logo" href="/">Trusted<span>Biz</span></a><a class="btn" href="/admin">← Admin</a></header>
<div class="wrap"><h1>App hosting</h1>
<p>App hosting switch: <span class="tag {{ 'live' if enabled else 'soon' }}">{{ 'ON' if enabled else 'OFF (set APP_HOSTING_ENABLED=true on Render when the server is ready)' }}</span></p>
{% if msg %}<div class="card">{{ msg }}</div>{% endif %}
{% for a in apps %}
<div class="card"><b>{{ a.name }}</b> · {{ a.slug }}.trustedbiz.co.ug · {{ a.app_kind }} · <span class="tag">{{ a.app_status }}</span>
<p style="margin:6px 0">Bundle: {% if a.bundle_size %}{{ a.bundle_size // 1024 }} KB · <a href="/admin/hosting/{{ a.id }}/bundle.zip">download</a>{% else %}none{% endif %}
{% if a.start %} · start: <code>{{ a.start }}</code>{% endif %}</p>
<form method="POST" action="/admin/hosting/{{ a.id }}" style="display:flex;gap:8px;flex-wrap:wrap">
<select name="app_status">{% for s in statuses %}<option value="{{ s }}" {{ 'selected' if s == a.app_status else '' }}>{{ s }}</option>{% endfor %}</select>
<input name="app_upstream" value="{{ a.app_upstream or '' }}" placeholder="http://server:port" style="flex:1;min-width:200px">
<button class="btn solid" type="submit">Save</button></form></div>
{% else %}<p style="margin-top:14px">No Python or Node apps uploaded yet.</p>{% endfor %}
</div></body></html>"""


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════
def init_hosting(app, deps):
    global _deps
    _deps = deps
    login_required = deps["login_required"]
    admin_required = deps["admin_required"]
    q, fetchone, fetchall, execute = deps["q"], deps["db_fetchone"], deps["db_fetchall"], deps["db_execute"]

    ensure_schema()
    # Templates ask this instead of trusting the raw DB status: an app only counts
    # as live while the master switch is on AND it has a valid upstream.
    app.jinja_env.globals["app_live"] = lambda b: bool(b) and _live(dict(b))

    @app.route("/api/hosting/capabilities")
    def hosting_capabilities():
        return jsonify(_caps())

    @app.route("/docs")
    def hosting_docs():
        return render_template_string(_DOCS, style=_STYLE, features=_FEATURES, caps=_dot(_caps()),
                                      trial=deps["HOSTING_TRIAL_DAYS"], monthly="{:,}".format(deps["HOSTING_FEE_MONTHLY"]), yearly="{:,}".format(deps["HOSTING_FEE_YEARLY"]))

    def _owned(biz_id):
        row = fetchone(q("SELECT * FROM business WHERE id=?"), (biz_id,))
        if not row:
            return None
        row = dict(row)
        if row.get("owner_id") == session.get("user_id") or session.get("admin_auth"):
            return row
        return None

    @app.route("/hosting/site/<int:biz_id>")
    @login_required
    def hosting_manage(biz_id):
        b = _owned(biz_id)
        if not b:
            flash("Not found.")
            return redirect("/dashboard#sites")
        is_app = (b.get("app_kind") or "none") in APP_KINDS
        events = [dict(e) for e in fetchall(q("SELECT message, status FROM deploy_events WHERE business_id=? ORDER BY id DESC LIMIT 15"), (biz_id,))]
        backups = []
        for s in fetchall(q("SELECT id, created_at, html_snapshot FROM site_backups WHERE business_id=? ORDER BY id DESC LIMIT 5"), (biz_id,)):
            s = dict(s)
            backups.append({"id": s["id"], "created_at": str(s["created_at"])[:16], "size": len(s.get("html_snapshot") or "")})
        bundle = None
        if is_app:
            r = fetchone(q("SELECT size FROM app_bundles WHERE business_id=? ORDER BY id DESC"), (biz_id,))
            bundle = dict(r) if r else None
        return render_template_string(_MANAGE, style=_STYLE, b=_dot(b), is_app=is_app, live=_live(b), events=_dot_list(events),
                                      backups=_dot_list(backups), bundle=_dot(bundle) if bundle else None,
                                      cfg=_json_or_empty(b.get("app_config")))

    @app.route("/hosting/rollback/<int:biz_id>/<int:backup_id>", methods=["POST"])
    @login_required
    def hosting_rollback(biz_id, backup_id):
        b = _owned(biz_id)
        if not b:
            flash("Not found.")
            return redirect("/dashboard#sites")
        snap = fetchone(q("SELECT id, html_snapshot FROM site_backups WHERE id=? AND business_id=?"), (backup_id, biz_id))
        if not snap or not dict(snap).get("html_snapshot"):
            flash("That snapshot no longer exists.", "error")
            return redirect(f"/hosting/site/{biz_id}")
        deps["save_site_html"](biz_id, dict(snap)["html_snapshot"])
        deps["log_deploy_event"](biz_id, session.get("user_id"), "rollback", f'"{b["name"]}" restored to an earlier snapshot', "ok")
        flash("Restored. Your site is now showing the earlier version.", "success")
        return redirect(f"/hosting/site/{biz_id}")

    # ── admin ────────────────────────────────────────────────────────────────
    def _admin_apps():
        rows = fetchall(q("SELECT id, name, slug, app_kind, app_status, app_upstream, app_config FROM business WHERE app_kind IN ('python','node') ORDER BY id DESC"))
        out = []
        for r in rows:
            r = dict(r)
            br = fetchone(q("SELECT size FROM app_bundles WHERE business_id=? ORDER BY id DESC"), (r["id"],))
            r["bundle_size"] = dict(br)["size"] if br else 0
            r["start"] = _json_or_empty(r.get("app_config")).get("detected_start")
            out.append(_dot(r))
        return out

    @app.route("/admin/hosting")
    @admin_required
    def admin_hosting():
        return render_template_string(_ADMIN, style=_STYLE, enabled=APP_HOSTING_ENABLED, apps=_admin_apps(),
                                      statuses=APP_STATUSES, msg=request.args.get("msg"))

    @app.route("/admin/hosting/<int:biz_id>", methods=["POST"])
    @admin_required
    def admin_hosting_set(biz_id):
        status = request.form.get("app_status", "")
        upstream = (request.form.get("app_upstream") or "").strip() or None
        if status not in APP_STATUSES:
            return redirect("/admin/hosting?msg=Invalid+status")
        if status == "running":
            if not APP_HOSTING_ENABLED:
                return redirect("/admin/hosting?msg=Turn+on+APP_HOSTING_ENABLED+first")
            if not _valid_upstream(upstream):
                return redirect("/admin/hosting?msg=Running+needs+an+upstream+URL+starting+with+http")
        _set_app_state(biz_id, status, upstream)
        deps["log_deploy_event"](biz_id, None, "app_status", f"App status set to {status}", "ok")
        return redirect("/admin/hosting?msg=Saved")

    @app.route("/admin/hosting/<int:biz_id>/bundle.zip")
    @admin_required
    def admin_hosting_bundle(biz_id):
        raw = load_bundle(biz_id)
        if raw is None:
            return "No bundle", 404
        return Response(raw, mimetype="application/zip",
                        headers={"Content-Disposition": f"attachment; filename=app-{biz_id}.zip"})


# tiny helpers so Jinja can use dot access on dicts safely
class _D(dict):
    __getattr__ = dict.get


def _dot(d):
    if isinstance(d, dict):
        return _D({k: _dot(v) if isinstance(v, dict) else v for k, v in d.items()})
    return d


def _dot_list(items):
    return [_dot(i) for i in items]
