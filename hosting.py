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
import secrets_box
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
    ("renew_by",     "TEXT"),                  # free plan: YYYY-MM-DD, renewed by opening the dashboard
    ("renew_notified", "TEXT"),
    ("upgrade_requested_at", "TEXT"),
    ("upgrade_phone", "TEXT"),
    ("upgrade_period", "TEXT"),
    ("maintenance_on", "INTEGER DEFAULT 0"),
    ("maintenance_url", "TEXT"),
    ("owner_paused", "INTEGER DEFAULT 0"),
    ("notify_deploys", "TEXT DEFAULT 'failed'"),   # all | failed | none
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
        pk = "SERIAL PRIMARY KEY" if d["USE_POSTGRES"] else "INTEGER PRIMARY KEY AUTOINCREMENT"
        ts = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if d["USE_POSTGRES"] else "DATETIME DEFAULT CURRENT_TIMESTAMP"
        d["db_execute"](f"CREATE TABLE IF NOT EXISTS env_vars (id {pk}, business_id INTEGER, name TEXT, value_enc TEXT, created_at {ts}, UNIQUE(business_id, name))")
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

    def __init__(self, raw, subdir=None):
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
        if subdir:
            sd = subdir.strip("/")
            members = [(n[len(sd) + 1:], i) for n, i in members if n.startswith(sd + "/")]
            if not members:
                raise UploadError(f'The root directory "{sd}" was not found in the repository.')
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


# ── PLANS ────────────────────────────────────────────────────────────────────
FREE_MAX_PROJECTS     = 1     # free projects per user
FREE_RENEW_DAYS       = 90    # opening the dashboard renews every free project
FREE_APP_SLEEP_MINUTES = 20   # apps only; enforced by the runner once servers exist
RENEW_REMINDER_DAYS   = 7


def plan_limits(row):
    """What a project's plan allows. The runner (when it exists) must read
    sleep_after_minutes and persistent_storage from here."""
    paid = bool((row or {}).get("is_premium"))
    return {
        "plan": "paid" if paid else "free",
        "custom_domain": paid,
        "always_on": paid,
        "sleep_after_minutes": None if paid else FREE_APP_SLEEP_MINUTES,
        "persistent_storage": paid,
        "renew_every_days": None if paid else FREE_RENEW_DAYS,
    }


def clean_phone(raw):
    """Digits only; 9-15 long, else None."""
    digits = re.sub(r"\D", "", raw or "")
    return digits if 9 <= len(digits) <= 15 else None


# Set by integrations.py: git_info(biz_id) -> dict or None. Used by the Manage page.
git_info = lambda biz_id: None
# Callables run before a project is deleted (e.g. to remove its Git webhook).
on_delete = []


def _today():
    from datetime import date
    return date.today()


def _renew_date():
    from datetime import timedelta
    return (_today() + timedelta(days=FREE_RENEW_DAYS)).isoformat()


def is_paused(row):
    """A live free project whose renewal date has passed. Paid projects and
    legacy projects with no renewal date never pause."""
    if not row or row.get("status") != "approved":
        return False
    if row.get("owner_paused"):
        return True
    if row.get("is_premium"):
        return False
    rb = str(row.get("renew_by") or "")[:10]
    return bool(rb) and rb < _today().isoformat()


def count_free_projects(user_id):
    d = _deps
    r = d["db_fetchone"](d["q"]("SELECT COUNT(*) AS c FROM business WHERE owner_id=? AND COALESCE(is_premium,0)=0 AND status IN ('approved','draft','paused')"), (user_id,))
    return int(dict(r)["c"]) if r else 0


def check_free_slot(user_id):
    """Raises UploadError if this user already has their free project. Call it BEFORE
    downloading or parsing anything, so an over-limit request costs us nothing."""
    if count_free_projects(user_id) >= FREE_MAX_PROJECTS:
        raise UploadError(f"The Free plan includes {FREE_MAX_PROJECTS} project. Upgrade it to Paid or delete it to add another.")


def renew_free_projects(user_id):
    """Called whenever the owner opens the dashboard. Keeps every free project live
    for another FREE_RENEW_DAYS. Does not touch suspended (unpaid) sites."""
    d = _deps
    try:
        d["db_execute"](d["q"]("UPDATE business SET renew_by=?, renew_notified=NULL WHERE owner_id=? AND COALESCE(is_premium,0)=0 AND status='approved'"),
                        (_renew_date(), user_id))
    except Exception as e:
        print(f"[hosting] renew_free_projects: {e}")   # columns not created yet


def free_tier_job():
    """Run from the admin payment check. Reminds owners whose free project will pause
    soon (or just paused). At most one reminder per project per 7 days."""
    from datetime import timedelta
    d = _deps
    soon = (_today() + timedelta(days=RENEW_REMINDER_DAYS)).isoformat()
    week_ago = (_today() - timedelta(days=7)).isoformat()
    rows = d["db_fetchall"](d["q"]("SELECT id, name, slug, owner_id, renew_by, renew_notified FROM business WHERE COALESCE(is_premium,0)=0 AND status='approved' AND renew_by IS NOT NULL AND renew_by <= ?"), (soon,))
    sent = 0
    for r in rows:
        r = dict(r)
        if r.get("renew_notified") and str(r["renew_notified"])[:10] > week_ago:
            continue
        paused = str(r["renew_by"])[:10] < _today().isoformat()
        msg = (f'"{r["name"]}" is paused. Open your TrustedBiz dashboard to bring it back.' if paused
               else f'"{r["name"]}" will pause on {str(r["renew_by"])[:10]}. Open your TrustedBiz dashboard before then to keep it live.')
        if r.get("owner_id"):
            d["db_insert"](d["q"]("INSERT INTO notifications (user_id,message) VALUES (?,?)"), (r["owner_id"], msg))
            try:
                u = d["db_fetchone"](d["q"]("SELECT email, name FROM users WHERE id=?"), (r["owner_id"],))
                if u and d.get("send_email"):
                    d["send_email"](dict(u)["email"], "Keep your TrustedBiz project live", f"<p>{msg}</p><p><a href='https://trustedbiz.co.ug/dashboard'>Open your dashboard</a></p>")
            except Exception as e:
                print(f"[hosting] reminder email: {e}")
        d["db_execute"](d["q"]("UPDATE business SET renew_notified=? WHERE id=?"), (_today().isoformat(), r["id"]))
        sent += 1
    return sent


# ── ENVIRONMENT VARIABLES (stored encrypted; used by the app runner later) ───
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
MAX_ENV_VARS = 50


def env_names(biz_id):
    d = _deps
    return [dict(r)["name"] for r in d["db_fetchall"](d["q"]("SELECT name FROM env_vars WHERE business_id=? ORDER BY name"), (biz_id,))]


def env_set(biz_id, name, value):
    d = _deps
    name = (name or "").strip()
    if not _ENV_NAME.match(name):
        raise UploadError("Variable names use letters, numbers and underscores, and can't start with a number.")
    if len(value or "") > 4000:
        raise UploadError("A value can be at most 4,000 characters.")
    exists = d["db_fetchone"](d["q"]("SELECT id FROM env_vars WHERE business_id=? AND name=?"), (biz_id, name))
    if not exists and len(env_names(biz_id)) >= MAX_ENV_VARS:
        raise UploadError(f"At most {MAX_ENV_VARS} variables per project.")
    try:
        blob = secrets_box.encrypt(value or "")
    except secrets_box.SecretsError as e:
        raise UploadError(str(e))
    if exists:
        d["db_execute"](d["q"]("UPDATE env_vars SET value_enc=? WHERE business_id=? AND name=?"), (blob, biz_id, name))
    else:
        d["db_execute"](d["q"]("INSERT INTO env_vars (business_id, name, value_enc) VALUES (?,?,?)"), (biz_id, name, blob))


def env_delete(biz_id, name):
    d = _deps
    d["db_execute"](d["q"]("DELETE FROM env_vars WHERE business_id=? AND name=?"), (biz_id, name))


def env_values(biz_id):
    """Decrypted {NAME: value}. For the app runner only. Never render these in a page."""
    d = _deps
    out = {}
    for r in d["db_fetchall"](d["q"]("SELECT name, value_enc FROM env_vars WHERE business_id=?"), (biz_id,)):
        r = dict(r)
        v = secrets_box.decrypt(r["value_enc"])
        if v is not None:
            out[r["name"]] = v
    return out


def fmt_dt(v):
    """'Nov 13, 2026 at 8:36 AM' in East Africa Time (UTC+3) from a DB timestamp."""
    from datetime import datetime, timedelta
    if not v:
        return ""
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.replace("Z", "").split(".")[0].replace("T", " "))
        except ValueError:
            return v[:16]
    try:
        v = v + timedelta(hours=3)
        return v.strftime("%b %-d, %Y at %-I:%M %p")
    except Exception:
        return str(v)[:16]


# ── PREPARE (parse + validate, no database writes) ───────────────────────────
def clean_subdir(raw):
    """Validates a repository root directory; returns '' or a safe relative path."""
    sd = (raw or "").strip().strip("/")
    if not sd:
        return ""
    if len(sd) > 100 or ".." in sd.split("/") or not re.match(r"^[\w.\-/]+$", sd):
        raise UploadError("Root directory can only contain letters, numbers, dots, dashes and slashes.")
    return sd


def prepare_upload(raw, filename, subdir=None):
    """Turns uploaded/downloaded bytes into a Prepared dict, or raises UploadError.
    Used by the upload form and by Git deploys, so both obey the same rules."""
    low = (filename or "").lower()
    if not raw:
        raise UploadError("That file is empty.")
    if len(raw) > MAX_STATIC_ZIP_BYTES:
        raise UploadError("That is over 8 MB. Remove big media files and try again.")
    warnings, config = [], {}
    if low.endswith(".html"):
        html = raw.decode("utf-8", errors="replace")
        if len(html) < 20:
            raise UploadError("That HTML file looks too short to be a real page.")
        return {"kind": "static", "pages": {"index": html}, "order": ["index"], "labels": {"index": "Home"},
                "warnings": [], "config": {}, "runtime": "static", "raw": raw, "filename": filename}
    if not low.endswith(".zip"):
        raise UploadError("Please upload a .zip or a single .html file.")
    p = Project(raw, subdir=subdir)
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
    out = {"kind": kind, "warnings": warnings, "config": config, "runtime": det["runtime"], "raw": raw, "filename": filename,
           "pages": None, "order": None, "labels": None}
    if kind == "static":
        out["pages"], out["order"], out["labels"], bw, _stats = build_static_site(p, det["root"])
        out["warnings"] += bw
    else:
        config["detected_start"] = config.get("start") or _procfile_start(p)
        if len(raw) > MAX_APP_BUNDLE_BYTES:
            raise UploadError("App bundles are limited to 5 MB for now. Remove virtual environments, node_modules and media files.")
    return out


# ── CREATE / UPDATE ──────────────────────────────────────────────────────────
def create_project(user, name, category, whatsapp, brand_color, description, prep, source_note="uploaded"):
    """Creates a new FREE project from a Prepared upload. Returns result dict. Raises UploadError."""
    d = _deps
    name = (name or "").strip()[:100]
    if not name:
        raise UploadError("Project name is required.")
    check_free_slot(user["id"])
    kind = prep["kind"]
    slug = d["make_slug"](name)
    renew = _renew_date()
    if kind == "static":
        blob = d["_encode_site"](prep["pages"], prep["order"], prep["labels"])
        biz_id = d["db_insert"](
            d["q"]("INSERT INTO business (name, category, whatsapp, description, brand_color, slug, owner_id, status, plan, is_premium, generated_html) VALUES (?,?,?,?,?,?,?,?,?,?,?)"),
            (name, category, whatsapp, description, brand_color, slug, user["id"], "approved", "free", 0, blob))
        d["db_execute"](d["q"]("UPDATE business SET app_kind='static', app_status='none', app_runtime='static', renew_by=? WHERE id=?"), (renew, biz_id))
        d["snapshot_site_html"](biz_id, blob)
        try:
            d["ping_google"](slug)
        except Exception:
            pass
        d["log_deploy_event"](biz_id, user["id"], "deploy", f'"{name}" deployed as a static site ({len(prep["pages"])} page{"s" if len(prep["pages"]) != 1 else ""}), {source_note}', "ok")
        msg = f'🚀 "{name}" is LIVE at {slug}.trustedbiz.co.ug ({len(prep["pages"])} page{"s" if len(prep["pages"]) != 1 else ""}) on the Free plan.'
    else:
        biz_id = d["db_insert"](
            d["q"]("INSERT INTO business (name, category, whatsapp, description, brand_color, slug, owner_id, status, plan, is_premium) VALUES (?,?,?,?,?,?,?,?,?,?)"),
            (name, category, whatsapp, description, brand_color, slug, user["id"], "approved", "free", 0))
        d["db_execute"](d["q"]("UPDATE business SET app_kind=?, app_status='waiting_for_server', app_runtime=?, app_config=?, renew_by=? WHERE id=?"),
                        (kind, prep["runtime"], json.dumps(prep["config"]), renew, biz_id))
        _store_bundle(biz_id, prep["filename"] or "app.zip", prep["raw"])
        d["log_deploy_event"](biz_id, user["id"], "app_upload", f'"{name}" ({kind} app) stored, {source_note}. Waiting for app servers to launch.', "pending")
        msg = f'📦 Your {"Python" if kind == "python" else "Node"} app "{name}" is uploaded and stored safely. App hosting launches soon, and it will go live automatically then.'
    return {"ok": True, "biz_id": biz_id, "kind": kind, "warnings": prep["warnings"], "slug": slug, "message": msg}


def update_project(biz_id, user_id, prep, note="redeployed"):
    """Replaces the content of an existing project with a Prepared upload."""
    d = _deps
    row = d["db_fetchone"](d["q"]("SELECT * FROM business WHERE id=?"), (biz_id,))
    if not row:
        raise UploadError("Project not found.")
    row = dict(row)
    kind = prep["kind"]
    old_kind = row.get("app_kind") or "none"
    is_app_row = old_kind in APP_KINDS
    if kind == "static" and is_app_row or kind in APP_KINDS and not is_app_row and old_kind in ("static",):
        raise UploadError("This repository changed type (static site vs app). Create a new project for it.")
    if kind == "static":
        blob = d["_encode_site"](prep["pages"], prep["order"], prep["labels"])
        d["save_site_html"](biz_id, blob)
        d["log_deploy_event"](biz_id, user_id, "deploy", f'"{row["name"]}" {note} ({len(prep["pages"])} page{"s" if len(prep["pages"]) != 1 else ""})', "ok")
    else:
        _store_bundle(biz_id, prep["filename"] or "app.zip", prep["raw"])
        d["db_execute"](d["q"]("UPDATE business SET app_config=?, app_runtime=? WHERE id=?"), (json.dumps(prep["config"]), prep["runtime"], biz_id))
        d["log_deploy_event"](biz_id, user_id, "app_upload", f'"{row["name"]}" {note}. New bundle stored.', "pending" if not _live(row) else "ok")
    return {"ok": True, "biz_id": biz_id, "kind": kind, "warnings": prep["warnings"]}


# ── FORM ENTRY POINT ─────────────────────────────────────────────────────────
def deploy_project(user, name, category, whatsapp, brand_color, description, upload):
    """Handle an uploaded .zip or .html. Returns {ok, message, biz_id, kind, warnings}. Never raises."""
    try:
        if not (name or "").strip():
            raise UploadError("Project name is required.")
        check_free_slot(user["id"])
        filename = (upload.filename or "").strip()
        raw = upload.read(MAX_STATIC_ZIP_BYTES + 1)
        prep = prepare_upload(raw, filename)
        return create_project(user, name, category, whatsapp, brand_color, description, prep, "uploaded")
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

_PAUSED_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><meta name="robots" content="noindex">
<title>{{ name }} is paused</title>
<style>
:root{--bg:#f5f8f8;--surface:#fff;--border:#d8e4e4;--text:#0d1c1c;--mid:#43605f;--brand:#2b7a78;}
@media (prefers-color-scheme: dark){:root{--bg:#0d1412;--surface:#141d1b;--border:#233230;--text:#eef5f4;--mid:#a9c4c1;}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,'Segoe UI',sans-serif;padding:24px}
.card{max-width:460px;background:var(--surface);border:1px solid var(--border);padding:32px 28px;text-align:center}
h1{font-size:22px;margin:0 0 10px}p{color:var(--mid);line-height:1.6;font-size:14.5px;margin:0 0 10px}a{color:var(--brand)}
</style></head><body><div class="card">
<h1>{{ name }} is paused</h1>
{% if owner %}<p>This project is paused. Open your dashboard: free projects come straight back, and projects you paused yourself can be resumed from Settings.</p>
<p><a href="/dashboard">Open dashboard</a></p>
{% else %}<p>This site is paused by its owner and will be back soon.</p>{% endif %}
<p style="font-size:12px;margin-top:18px">Hosted on <a href="https://trustedbiz.co.ug">TrustedBiz</a></p>
</div></body></html>"""


_MAINT_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><meta name="robots" content="noindex">
<title>{{ name }} is under maintenance</title>
<style>
:root{--bg:#f5f8f8;--surface:#fff;--border:#d8e4e4;--text:#0d1c1c;--mid:#43605f;--brand:#2b7a78;}
@media (prefers-color-scheme: dark){:root{--bg:#0d1412;--surface:#141d1b;--border:#233230;--text:#eef5f4;--mid:#a9c4c1;}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,'Segoe UI',sans-serif;padding:24px}
.card{max-width:460px;background:var(--surface);border:1px solid var(--border);padding:32px 28px;text-align:center}
h1{font-size:22px;margin:0 0 10px}p{color:var(--mid);line-height:1.6;font-size:14.5px;margin:0 0 10px}a{color:var(--brand)}
</style></head><body><div class="card">
<h1>Down for maintenance</h1>
<p>{{ name }} is being updated and will be back shortly.</p>
{% if owner %}<p><a href="/hosting/site/{{ biz_id }}?tab=settings">Maintenance mode is on. Turn it off in Settings.</a></p>{% endif %}
<p style="font-size:12px;margin-top:18px">Hosted on <a href="https://trustedbiz.co.ug">TrustedBiz</a></p>
</div></body></html>"""


def maintenance_response(row):
    """Paid feature. None when maintenance is off or the viewer is an admin."""
    if not row or not row.get("maintenance_on") or session.get("admin_auth"):
        return None
    url = (row.get("maintenance_url") or "").strip()
    if re.match(r"^https?://[^\s]+$", url):
        return redirect(url, code=302)
    html = render_template_string(_MAINT_PAGE, name=row.get("name") or "This site", owner=_is_owner_or_admin(row), biz_id=row.get("id"))
    resp = Response(html, status=503, mimetype="text/html")
    resp.headers["Retry-After"] = "600"
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


def _paused_response(row):
    html = render_template_string(_PAUSED_PAGE, name=row.get("name") or "This site", owner=_is_owner_or_admin(row))
    resp = Response(html, status=503, mimetype="text/html")
    resp.headers["Retry-After"] = "86400"
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


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
        row = d["db_fetchone"](d["q"]("SELECT id, name, slug, status, owner_id, is_premium, renew_by, owner_paused, maintenance_on, maintenance_url, app_kind, app_status, app_upstream FROM business WHERE slug=?"), (slug,))
    except Exception:
        return None   # columns not created yet: behave like before
    return dict(row) if row else None


def _live(row):
    return (APP_HOSTING_ENABLED and row.get("app_status") == "running" and _valid_upstream(row.get("app_upstream")))


def subdomain_app_response(slug):
    """Called by app.py for every <slug>.trustedbiz.co.ug request. Returns a
    Response for app sites, or None so normal static handling continues."""
    row = _row_for_slug(slug)
    if not row:
        return None
    if is_paused(row) and not session.get("admin_auth"):
        return _paused_response(row)
    m = maintenance_response(row)
    if m is not None:
        return m
    if (row.get("app_kind") or "none") not in APP_KINDS:
        return None
    if row.get("status") != "approved" and not _is_owner_or_admin(row):
        return None
    if _live(row):
        return _proxy(row["app_upstream"], request.path)
    return _waiting_response(row)


def app_gate_response(bd):
    """Called inside site() (the /site/<slug> route). None = carry on as normal."""
    if is_paused(bd) and not session.get("admin_auth"):
        return _paused_response(bd)
    m = maintenance_response(bd)
    if m is not None:
        return m
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
    ("Free plan", "live", "1 project, yourname.trustedbiz.co.ug, renews when you open your dashboard (every 90 days)."),
    ("Paid plan", "live", "Custom domain, always on, no renewal needed. UGX 15,000 a month."),
    ("Deploy from GitHub and GitLab", "live", "Connect an account, pick a repo, and every push deploys. Public repos need no login."),
    ("Sign in with Google or GitHub", "live", "One click sign-in on the login page."),
    ("Custom domains (Paid)", "live", "Request a domain from your dashboard and follow the DNS steps."),
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


_ADMIN = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>App hosting | Admin</title><style>{{ style|safe }}</style></head><body>
<header><a class="logo" href="/">Trusted<span>Biz</span></a><a class="btn" href="/admin">← Admin</a></header>
<div class="wrap"><h1>App hosting</h1>
<p>App hosting switch: <span class="tag {{ 'live' if enabled else 'soon' }}">{{ 'ON' if enabled else 'OFF (set APP_HOSTING_ENABLED=true on Render when the server is ready)' }}</span></p>
{% if msg %}<div class="card">{{ msg }}</div>{% endif %}
<h2>Upgrade requests</h2>
{% for u in upgrades %}<div class="card"><b>{{ u.name }}</b> · {{ u.slug }}.trustedbiz.co.ug · {{ u.upgrade_period or 'monthly' }} · phone {{ u.upgrade_phone }}
<form method="POST" action="/admin/hosting/upgrade/{{ u.id }}" style="margin-top:8px"><button class="btn solid" type="submit">Mark paid and switch to Paid</button></form></div>
{% else %}<p>No pending upgrade requests.</p>{% endfor %}
<h2>Apps</h2>
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

    def _owned(biz_id):
        row = fetchone(q("SELECT * FROM business WHERE id=?"), (biz_id,))
        if not row:
            return None
        row = dict(row)
        if row.get("owner_id") == session.get("user_id") or session.get("admin_auth"):
            return row
        return None

    @app.route("/hosting/upgrade/<int:biz_id>", methods=["POST"])
    @login_required
    def hosting_upgrade(biz_id):
        b = _owned(biz_id)
        if not b:
            flash("Not found.", "error")
            return redirect("/dashboard#sites")
        if b.get("is_premium"):
            flash("This project is already on the Paid plan.", "success")
            return redirect(f"/hosting/site/{biz_id}")
        phone = clean_phone(request.form.get("phone"))
        period = "yearly" if request.form.get("period") == "yearly" else "monthly"
        if not phone:
            flash("Enter the mobile money number you will pay from.", "error")
            return redirect(f"/hosting/site/{biz_id}")
        execute(q("UPDATE business SET upgrade_requested_at=?, upgrade_phone=?, upgrade_period=? WHERE id=?"),
                (_today().isoformat(), phone, period, biz_id))
        deps["log_deploy_event"](biz_id, session.get("user_id"), "upgrade_requested", f'Upgrade to Paid requested ({period})', "pending")
        try:
            if deps.get("send_email") and deps.get("ADMIN_EMAIL"):
                deps["send_email"](deps["ADMIN_EMAIL"], "Upgrade request", f'<p>{b["name"]} ({b["slug"]}) asked to upgrade, {period}, phone {phone}.</p>')
        except Exception as e:
            print(f"[hosting] admin email: {e}")
        flash("Upgrade requested. Pay on WhatsApp and we will switch it on.", "success")
        return redirect(f"/hosting/site/{biz_id}")

    @app.route("/hosting/delete/<int:biz_id>", methods=["POST"])
    @login_required
    def hosting_delete(biz_id):
        b = _owned(biz_id)
        if not b:
            flash("Not found.", "error")
            return redirect("/dashboard#sites")
        for fn in on_delete:
            try:
                fn(biz_id)
            except Exception as e:
                print(f"[hosting] on_delete hook: {e}")
        for table in ("deploy_events", "site_backups", "app_bundles", "reviews", "branches"):
            try:
                execute(q(f"DELETE FROM {table} WHERE business_id=?"), (biz_id,))
            except Exception:
                pass
        execute(q("DELETE FROM business WHERE id=?"), (biz_id,))
        deps["log_deploy_event"](None, session.get("user_id"), "delete", f'Deleted "{b["name"]}"', "ok")
        flash(f'"{b["name"]}" was deleted.', "success")
        return redirect("/dashboard#sites")

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
            return redirect(f"/hosting/site/{biz_id}?tab=events#snapshots")
        deps["save_site_html"](biz_id, dict(snap)["html_snapshot"])
        deps["log_deploy_event"](biz_id, session.get("user_id"), "rollback", f'"{b["name"]}" restored to an earlier snapshot', "ok")
        flash("Restored. Your site is now showing the earlier version.", "success")
        return redirect(f"/hosting/site/{biz_id}?tab=events#snapshots")

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
        ups = [_dot(dict(r)) for r in fetchall(q("SELECT id, name, slug, upgrade_period, upgrade_phone FROM business WHERE upgrade_requested_at IS NOT NULL AND COALESCE(is_premium,0)=0 ORDER BY id DESC"))]
        return render_template_string(_ADMIN, style=_STYLE, enabled=APP_HOSTING_ENABLED, apps=_admin_apps(), upgrades=ups,
                                      statuses=APP_STATUSES, msg=request.args.get("msg"))

    @app.route("/admin/hosting/upgrade/<int:biz_id>", methods=["POST"])
    @admin_required
    def admin_hosting_upgrade(biz_id):
        b = fetchone(q("SELECT id, name, owner_id FROM business WHERE id=?"), (biz_id,))
        if not b:
            return redirect("/admin/hosting?msg=Not+found")
        # Same fields the existing admin "mark hosting paid" action sets.
        execute(q("UPDATE business SET plan='hosted', is_premium=1, last_payment_date=CURRENT_DATE, renew_by=NULL, upgrade_requested_at=NULL WHERE id=?"), (biz_id,))
        b = dict(b)
        if b.get("owner_id"):
            deps["db_insert"](q("INSERT INTO notifications (user_id,message) VALUES (?,?)"), (b["owner_id"], f'Payment confirmed. "{b["name"]}" is now on the Paid plan.'))
        deps["log_deploy_event"](biz_id, None, "upgrade", "Switched to Paid plan", "ok")
        return redirect("/admin/hosting?msg=Switched+to+Paid")

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
