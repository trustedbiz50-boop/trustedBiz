"""
integrations.py — sign-in with Google/GitHub, and deploy from GitHub/GitLab
════════════════════════════════════════════════════════════════════════════
  • Sign in with Google or GitHub (OAuth 2.0 authorization-code flow).
  • Connect a GitHub or GitLab account, pick a repository, deploy it, and
    redeploy automatically on every push (webhook).
  • Public repositories can be deployed from a URL with no login at all.

Everything the repo contains goes through hosting.prepare_upload(), so a Git
deploy obeys exactly the same rules as a ZIP upload (static site, or a Python/
Node app that is stored until app hosting launches).

Environment variables (a provider with no keys simply doesn't show up):
    APP_BASE_URL            https://trustedbiz.co.ug
    GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
    GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET
    GITLAB_CLIENT_ID / GITLAB_CLIENT_SECRET   (GITLAB_BASE for self-hosted)
    TOKEN_KEY               optional; encrypts stored Git tokens (defaults to SECRET_KEY)

Callback URL to register with every provider:  {APP_BASE_URL}/oauth/<provider>/callback
"""
import os
import re
import json
import hmac
import base64
import hashlib
import secrets
import threading
from urllib.parse import urlencode, quote

import requests as _requests
from flask import request, redirect, session, flash, render_template, jsonify
from werkzeug.security import generate_password_hash

import hosting
import secrets_box

_deps = None
_app = None


class OAuthError(Exception):
    """Something we can explain to the user (shown as a flash message)."""


def _env(name, default=""):
    return (os.environ.get(name) or default).strip()


def base_url():
    return _env("APP_BASE_URL", "https://trustedbiz.co.ug").rstrip("/")


def _http(method, url, **kw):
    """The ONLY place that touches the network, so tests can replace it."""
    kw.setdefault("timeout", (5, 30))
    return _requests.request(method, url, **kw)


def safe_next(n):
    n = (n or "").strip()
    if n.startswith("/") and not n.startswith("//") and "\\" not in n and "\n" not in n and "\r" not in n:
        return n
    return "/dashboard"


# ══════════════════════════════════════════════════════════════════════════════
# TOKEN ENCRYPTION (shared helper, see secrets_box.py)
# ══════════════════════════════════════════════════════════════════════════════
def encrypt_token(token):
    try:
        return secrets_box.encrypt(token)
    except secrets_box.SecretsError as e:
        raise OAuthError(str(e))


def decrypt_token(blob):
    return secrets_box.decrypt(blob)


# ══════════════════════════════════════════════════════════════════════════════
# PROVIDERS
# ══════════════════════════════════════════════════════════════════════════════
class Provider:
    name = ""
    label = ""
    can_signin = False
    can_git = False
    auth_url = ""
    token_url = ""
    signin_scope = ""

    # keys
    def client_id(self):
        return _env(self.name.upper() + "_CLIENT_ID")

    def client_secret(self):
        return _env(self.name.upper() + "_CLIENT_SECRET")

    def configured(self):
        return bool(self.client_id() and self.client_secret())

    def redirect_uri(self):
        return f"{base_url()}/oauth/{self.name}/callback"

    def authorize_url(self, state, scope, extra=None):
        params = {"client_id": self.client_id(), "redirect_uri": self.redirect_uri(), "response_type": "code",
                  "scope": scope, "state": state}
        params.update(extra or {})
        return f"{self.auth_url}?{urlencode(params)}"

    def exchange(self, code):
        raise NotImplementedError

    def identity(self, token):
        raise NotImplementedError

    def account_label(self, token):
        return ""

    # git (override where supported)
    def list_repos(self, token):
        raise OAuthError(f"{self.label} repositories are not supported.")

    def default_branch(self, token, repo, repo_id):
        raise NotImplementedError

    def archive_url(self, repo, repo_id, ref):
        raise NotImplementedError

    def auth_headers(self, token):
        return {"Authorization": f"Bearer {token}"} if token else {}

    def create_hook(self, token, repo, repo_id, branch, url, secret):
        return None

    def delete_hook(self, token, repo, repo_id, hook_id):
        return None

    def verify_hook(self, headers, body, secret):
        return False

    def hook_event_ok(self, headers):
        return True

    def parse_push(self, payload):
        return None, None


def _check(r, what):
    if r.status_code >= 400:
        raise OAuthError(f"{what} failed ({r.status_code}).")
    return r


class Google(Provider):
    name = "google"
    label = "Google"
    can_signin = True
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    signin_scope = "openid email profile"

    def authorize_url(self, state, scope, extra=None):
        return super().authorize_url(state, scope, {"prompt": "select_account", **(extra or {})})

    def exchange(self, code):
        r = _check(_http("POST", self.token_url, data={
            "code": code, "client_id": self.client_id(), "client_secret": self.client_secret(),
            "redirect_uri": self.redirect_uri(), "grant_type": "authorization_code"}), "Google sign-in")
        tok = (r.json() or {}).get("access_token")
        if not tok:
            raise OAuthError("Google did not return an access token.")
        return tok

    def identity(self, token):
        r = _check(_http("GET", "https://openidconnect.googleapis.com/v1/userinfo",
                         headers={"Authorization": f"Bearer {token}"}), "Google profile")
        j = r.json() or {}
        return {"id": str(j.get("sub") or ""), "email": (j.get("email") or "").lower(),
                "email_verified": bool(j.get("email_verified")), "name": j.get("name") or ""}


class GitHub(Provider):
    name = "github"
    label = "GitHub"
    can_signin = True
    can_git = True
    auth_url = "https://github.com/login/oauth/authorize"
    token_url = "https://github.com/login/oauth/access_token"
    signin_scope = "read:user user:email"
    api = "https://api.github.com"

    def _h(self, token):
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    def exchange(self, code):
        r = _check(_http("POST", self.token_url, headers={"Accept": "application/json"}, data={
            "client_id": self.client_id(), "client_secret": self.client_secret(),
            "code": code, "redirect_uri": self.redirect_uri()}), "GitHub sign-in")
        j = r.json() or {}
        if not j.get("access_token"):
            raise OAuthError("GitHub did not return an access token" + (f" ({j.get('error')})." if j.get("error") else "."))
        return j["access_token"]

    def identity(self, token):
        u = _check(_http("GET", f"{self.api}/user", headers=self._h(token)), "GitHub profile").json() or {}
        emails = _check(_http("GET", f"{self.api}/user/emails", headers=self._h(token)), "GitHub email").json() or []
        primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
        any_verified = next((e for e in emails if e.get("verified")), None)
        pick = primary or any_verified
        return {"id": str(u.get("id") or ""), "email": ((pick or {}).get("email") or "").lower(),
                "email_verified": bool(pick), "name": u.get("name") or u.get("login") or ""}

    def account_label(self, token):
        try:
            return (_http("GET", f"{self.api}/user", headers=self._h(token)).json() or {}).get("login", "")
        except Exception:
            return ""

    def list_repos(self, token):
        r = _check(_http("GET", f"{self.api}/user/repos", headers=self._h(token), params={
            "per_page": 100, "sort": "pushed", "affiliation": "owner,collaborator,organization_member"}), "Listing repositories")
        return [{"repo": x["full_name"], "repo_id": str(x["id"]), "default_branch": x.get("default_branch") or "main",
                 "private": bool(x.get("private"))} for x in (r.json() or [])]

    def default_branch(self, token, repo, repo_id):
        r = _check(_http("GET", f"{self.api}/repos/{repo}", headers=self._h(token)), "Reading repository")
        return (r.json() or {}).get("default_branch") or "main"

    def archive_url(self, repo, repo_id, ref):
        return f"{self.api}/repos/{repo}/zipball/{quote(ref, safe='')}"

    def auth_headers(self, token):
        return self._h(token)

    def create_hook(self, token, repo, repo_id, branch, url, secret):
        r = _check(_http("POST", f"{self.api}/repos/{repo}/hooks", headers=self._h(token), json={
            "name": "web", "active": True, "events": ["push"],
            "config": {"url": url, "content_type": "json", "secret": secret, "insecure_ssl": "0"}}), "Creating webhook")
        return str((r.json() or {}).get("id") or "")

    def delete_hook(self, token, repo, repo_id, hook_id):
        _http("DELETE", f"{self.api}/repos/{repo}/hooks/{hook_id}", headers=self._h(token))

    def verify_hook(self, headers, body, secret):
        sig = headers.get("X-Hub-Signature-256", "")
        want = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return bool(sig) and hmac.compare_digest(sig, want)

    def hook_event_ok(self, headers):
        return headers.get("X-GitHub-Event") == "push"

    def parse_push(self, payload):
        ref = payload.get("ref") or ""
        return (ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else None), payload.get("after")


class GitLab(Provider):
    name = "gitlab"
    label = "GitLab"
    can_git = True
    signin_scope = "api"

    @property
    def base(self):
        return _env("GITLAB_BASE", "https://gitlab.com").rstrip("/")

    @property
    def auth_url(self):
        return f"{self.base}/oauth/authorize"

    @property
    def token_url(self):
        return f"{self.base}/oauth/token"

    def exchange(self, code):
        r = _check(_http("POST", self.token_url, data={
            "client_id": self.client_id(), "client_secret": self.client_secret(), "code": code,
            "grant_type": "authorization_code", "redirect_uri": self.redirect_uri()}), "GitLab sign-in")
        j = r.json() or {}
        if not j.get("access_token"):
            raise OAuthError("GitLab did not return an access token.")
        return j["access_token"]

    def account_label(self, token):
        try:
            return (_http("GET", f"{self.base}/api/v4/user", headers=self.auth_headers(token)).json() or {}).get("username", "")
        except Exception:
            return ""

    def list_repos(self, token):
        r = _check(_http("GET", f"{self.base}/api/v4/projects", headers=self.auth_headers(token), params={
            "membership": "true", "simple": "true", "per_page": 100, "order_by": "last_activity_at"}), "Listing projects")
        return [{"repo": x["path_with_namespace"], "repo_id": str(x["id"]), "default_branch": x.get("default_branch") or "main",
                 "private": x.get("visibility") != "public"} for x in (r.json() or [])]

    def _pid(self, repo, repo_id):
        return repo_id or quote(repo, safe="")

    def default_branch(self, token, repo, repo_id):
        r = _check(_http("GET", f"{self.base}/api/v4/projects/{self._pid(repo, repo_id)}", headers=self.auth_headers(token)), "Reading project")
        return (r.json() or {}).get("default_branch") or "main"

    def archive_url(self, repo, repo_id, ref):
        return f"{self.base}/api/v4/projects/{self._pid(repo, repo_id)}/repository/archive.zip?sha={quote(ref, safe='')}"

    def create_hook(self, token, repo, repo_id, branch, url, secret):
        r = _check(_http("POST", f"{self.base}/api/v4/projects/{self._pid(repo, repo_id)}/hooks", headers=self.auth_headers(token), data={
            "url": url, "token": secret, "push_events": "true", "enable_ssl_verification": "true"}), "Creating webhook")
        return str((r.json() or {}).get("id") or "")

    def delete_hook(self, token, repo, repo_id, hook_id):
        _http("DELETE", f"{self.base}/api/v4/projects/{self._pid(repo, repo_id)}/hooks/{hook_id}", headers=self.auth_headers(token))

    def verify_hook(self, headers, body, secret):
        got = headers.get("X-Gitlab-Token", "")
        return bool(got) and hmac.compare_digest(got, secret)

    def hook_event_ok(self, headers):
        return headers.get("X-Gitlab-Event") == "Push Hook"

    def parse_push(self, payload):
        ref = payload.get("ref") or ""
        return (ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else None), payload.get("checkout_sha") or payload.get("after")


PROVIDERS = {p.name: p for p in (Google(), GitHub(), GitLab())}


def enabled():
    return {name: p.configured() for name, p in PROVIDERS.items()}


# ══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD (size-capped)
# ══════════════════════════════════════════════════════════════════════════════
def download_repo(prov, token, repo, repo_id, ref):
    r = _http("GET", prov.archive_url(repo, repo_id, ref), headers=prov.auth_headers(token), stream=True, allow_redirects=True)
    if r.status_code == 404:
        raise hosting.UploadError("Repository, branch or access not found. For a private repository, connect your account first.")
    if r.status_code in (401, 403):
        raise hosting.UploadError(f"{prov.label} refused access. Reconnect your account and try again.")
    if r.status_code >= 400:
        raise hosting.UploadError(f"{prov.label} returned an error ({r.status_code}).")
    buf = bytearray()
    for chunk in r.iter_content(65536):
        buf.extend(chunk)
        if len(buf) > hosting.MAX_STATIC_ZIP_BYTES:
            raise hosting.UploadError("This repository is over 8 MB as a ZIP. Remove large media files and try again.")
    return bytes(buf)


# ══════════════════════════════════════════════════════════════════════════════
# SCHEMA
# ══════════════════════════════════════════════════════════════════════════════
def ensure_schema():
    d = _deps
    pg = d["USE_POSTGRES"]
    pk = "SERIAL PRIMARY KEY" if pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ts = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if pg else "DATETIME DEFAULT CURRENT_TIMESTAMP"
    stmts = [
        f"CREATE TABLE IF NOT EXISTS oauth_identities (id {pk}, user_id INTEGER, provider TEXT, provider_user_id TEXT, email TEXT, created_at {ts}, UNIQUE(provider, provider_user_id))",
        f"CREATE TABLE IF NOT EXISTS git_connections (id {pk}, user_id INTEGER, provider TEXT, token_enc TEXT, account TEXT, created_at {ts}, UNIQUE(user_id, provider))",
        f"CREATE TABLE IF NOT EXISTS git_links (id {pk}, business_id INTEGER UNIQUE, user_id INTEGER, provider TEXT, repo TEXT, repo_id TEXT, branch TEXT, hook_id TEXT, hook_secret TEXT, last_commit TEXT, last_deploy_at TEXT, last_status TEXT, last_message TEXT, root_dir TEXT, auto_deploy INTEGER DEFAULT 1, deploy_token TEXT)",
    ]
    try:
        for s in stmts:
            d["db_execute"](s)
        cols = {r["column_name"] for r in d["db_fetchall"]("SELECT column_name FROM information_schema.columns WHERE table_name='git_links'")} if pg \
            else {r[1] for r in d["db_fetchall"]("PRAGMA table_info(git_links)")}
        for col, ddl in (("root_dir", "TEXT"), ("auto_deploy", "INTEGER DEFAULT 1"), ("deploy_token", "TEXT")):
            if col not in cols:
                d["db_execute"](f"ALTER TABLE git_links ADD COLUMN {col} {ddl}")
        return True
    except Exception as e:
        print(f"[integrations] ensure_schema: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# DB HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _one(sql, params=()):
    r = _deps["db_fetchone"](_deps["q"](sql), params)
    return dict(r) if r else None


def _all(sql, params=()):
    return [dict(r) for r in _deps["db_fetchall"](_deps["q"](sql), params)]


def _exec(sql, params=()):
    return _deps["db_execute"](_deps["q"](sql), params)


def _connection_token(user_id, provider):
    row = _one("SELECT token_enc FROM git_connections WHERE user_id=? AND provider=?", (user_id, provider))
    return decrypt_token(row["token_enc"]) if row else None


def _link(biz_id):
    return _one("SELECT * FROM git_links WHERE business_id=?", (biz_id,))


def _repo_url(provider, repo):
    if provider == "github":
        return f"https://github.com/{repo}"
    if provider == "gitlab":
        return f"{PROVIDERS['gitlab'].base}/{repo}"
    return ""


def _ensure_deploy_token(link):
    if not link.get("deploy_token"):
        tok = secrets.token_urlsafe(24)
        _exec("UPDATE git_links SET deploy_token=? WHERE business_id=?", (tok, link["business_id"]))
        link["deploy_token"] = tok
    return link["deploy_token"]


def git_info(biz_id):
    try:
        l = _link(biz_id)
    except Exception:
        return None
    if not l:
        return None
    tok = _ensure_deploy_token(l)
    return {"provider": PROVIDERS[l["provider"]].label if l["provider"] in PROVIDERS else l["provider"], "provider_key": l["provider"],
            "repo": l["repo"], "repo_url": _repo_url(l["provider"], l["repo"]), "branch": l["branch"], "root_dir": l.get("root_dir") or "",
            "commit": (l.get("last_commit") or "")[:7], "auto_deploy": bool(l.get("auto_deploy", 1)), "hook_active": bool(l.get("hook_id")),
            "last_deploy_at": l.get("last_deploy_at") or "", "last_status": l.get("last_status") or "",
            "last_message": l.get("last_message") or "", "deploy_hook_url": f"{base_url()}/hooks/deploy/{tok}"}


def remove_link(biz_id):
    """Best-effort: remove the webhook, then the link row. Runs when a project is deleted."""
    l = _link(biz_id)
    if not l:
        return
    try:
        if l.get("hook_id"):
            tok = _connection_token(l["user_id"], l["provider"])
            if tok:
                PROVIDERS[l["provider"]].delete_hook(tok, l["repo"], l["repo_id"], l["hook_id"])
    except Exception as e:
        print(f"[integrations] delete hook: {e}")
    _exec("DELETE FROM git_links WHERE business_id=?", (biz_id,))


# ══════════════════════════════════════════════════════════════════════════════
# DEPLOY FROM A LINK
# ══════════════════════════════════════════════════════════════════════════════
def _stamp(biz_id, status, message, commit=None):
    from datetime import datetime
    _exec("UPDATE git_links SET last_status=?, last_message=?, last_deploy_at=?, last_commit=COALESCE(?, last_commit) WHERE business_id=?",
          (status, (message or "")[:200], datetime.utcnow().isoformat(timespec="seconds"), commit, biz_id))


def deploy_link(biz_id, commit=None, reason="manual"):
    """Download the linked repo and update the project. Returns (ok, message). Never raises."""
    link = _link(biz_id)
    if not link:
        return False, "This project is not connected to a repository."
    prov = PROVIDERS.get(link["provider"])
    try:
        token = _connection_token(link["user_id"], link["provider"])
        ref = commit or link["branch"]
        raw = download_repo(prov, token, link["repo"], link["repo_id"], ref)
        prep = hosting.prepare_upload(raw, "repo.zip", subdir=hosting.clean_subdir(link.get("root_dir")))
        short = (commit or "")[:7]
        res = hosting.update_project(biz_id, link["user_id"], prep,
                                     note=f'deployed from {prov.label} {link["repo"]}@{link["branch"]}' + (f" ({short})" if short else "") + f", {reason}")
        _stamp(biz_id, "ok", "deployed", commit)
        _notify(biz_id, link, True, "deployed", reason)
        return True, "Deployed."
    except hosting.UploadError as e:
        _stamp(biz_id, "failed", str(e))
        try:
            _deps["log_deploy_event"](biz_id, link["user_id"], "deploy_failed", f"Git deploy failed: {e}", "failed")
        except Exception:
            pass
        _notify(biz_id, link, False, str(e), reason)
        return False, str(e)
    except Exception as e:
        print(f"[integrations] deploy_link error: {e}")
        _stamp(biz_id, "failed", "unexpected error")
        return False, "Something went wrong while deploying from Git. Your site was not changed."


def _notify(biz_id, link, ok, detail, reason):
    """Email the owner about a Git deploy, following the project's notification setting."""
    try:
        b = _one("SELECT name, notify_deploys, owner_id FROM business WHERE id=?", (biz_id,))
        mode = (b or {}).get("notify_deploys") or "failed"
        if not b or mode == "none" or (mode == "failed" and ok):
            return
        u = _one("SELECT email FROM users WHERE id=?", (b["owner_id"],))
        send = _deps.get("send_email")
        if u and send:
            subject = f'Deploy {"succeeded" if ok else "failed"}: {b["name"]}'
            send(u["email"], subject, f'<p>{b["name"]}: {detail}</p><p><a href="{base_url()}/hosting/site/{biz_id}">Open project</a></p>')
    except Exception as e:
        print(f"[integrations] notify: {e}")


def _run_async(fn, *args):
    if _app is not None and _app.config.get("TESTING"):
        return fn(*args)
    t = threading.Thread(target=fn, args=args, daemon=True)
    t.start()


# ══════════════════════════════════════════════════════════════════════════════
# SIGN-IN: find or create the TrustedBiz user
# ══════════════════════════════════════════════════════════════════════════════
def _login_user(user):
    if user.get("two_factor_enabled"):
        session["pending_login_user_id"] = user["id"]
        return redirect("/login/verify-2fa")
    session.permanent = True
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return None


def resolve_user(provider, ident):
    """Returns (user_dict, created_bool). Raises OAuthError."""
    d = _deps
    if not ident.get("id"):
        raise OAuthError(f"{PROVIDERS[provider].label} did not return an account id.")
    row = _one("SELECT user_id FROM oauth_identities WHERE provider=? AND provider_user_id=?", (provider, ident["id"]))
    if row:
        user = _one("SELECT * FROM users WHERE id=?", (row["user_id"],))
        if user:
            return user, False
    if not ident.get("email") or not ident.get("email_verified"):
        raise OAuthError(f"{PROVIDERS[provider].label} did not share a verified email address, so we can't create your account. Use email sign-up instead.")
    created = False
    user = _one("SELECT * FROM users WHERE email=?", (ident["email"],))
    if not user:
        name = (ident.get("name") or ident["email"].split("@")[0])[:100]
        uid = d["db_insert"](d["q"]("INSERT INTO users (name,email,password) VALUES (?,?,?)"),
                             (name, ident["email"], generate_password_hash(secrets.token_urlsafe(32))))
        user = _one("SELECT * FROM users WHERE id=?", (uid,))
        created = True
    _exec("INSERT INTO oauth_identities (user_id, provider, provider_user_id, email) VALUES (?,?,?,?)",
          (user["id"], provider, ident["id"], ident["email"]))
    return user, created


# ══════════════════════════════════════════════════════════════════════════════
# GIT URL PARSING (public repositories)
# ══════════════════════════════════════════════════════════════════════════════
_RE_GH = re.compile(r"^https?://(?:www\.)?github\.com/([\w.\-]+)/([\w.\-]+?)(?:\.git)?(?:/tree/([^\s?#]+))?/?$")
_RE_GL = re.compile(r"^https?://(?:www\.)?gitlab\.com/((?:[\w.\-]+/)+[\w.\-]+?)(?:\.git)?(?:/-/tree/([^\s?#]+))?/?$")


def parse_repo_url(url):
    """Returns (provider_name, repo, branch_or_None) or None."""
    url = (url or "").strip()
    m = _RE_GH.match(url)
    if m:
        return "github", f"{m.group(1)}/{m.group(2)}", m.group(3)
    m = _RE_GL.match(url)
    if m:
        return "gitlab", m.group(1), m.group(2)
    return None


def create_from_repo(user, prov, repo, repo_id, branch, name, token, want_hook):
    raw = download_repo(prov, token, repo, repo_id, branch)
    prep = hosting.prepare_upload(raw, "repo.zip")
    res = hosting.create_project(user, name, "Git", "", "#2b7a78", "", prep, f"from {prov.label} {repo}@{branch}")
    biz_id = res["biz_id"]
    secret = secrets.token_hex(24)
    hook_id = None
    hook_note = ""
    if want_hook and token:
        try:
            hook_id = prov.create_hook(token, repo, repo_id, branch, f"{base_url()}/hooks/{prov.name}/{biz_id}", secret)
        except Exception as e:
            print(f"[integrations] hook create: {e}")
            hook_note = " Automatic deploys on push could not be set up, but you can redeploy from the project page."
    _exec("INSERT INTO git_links (business_id, user_id, provider, repo, repo_id, branch, hook_id, hook_secret, last_status, last_message) VALUES (?,?,?,?,?,?,?,?,?,?)",
          (biz_id, user["id"], prov.name, repo, repo_id, branch, hook_id, secret, "ok", "first deploy"))
    res["message"] += (" Every push to " + branch + " now redeploys it." if hook_id else "") + hook_note
    return res



def deploy_public(user, url, name=""):
    """Create a project from a public GitHub/GitLab URL. Raises UploadError/OAuthError."""
    hosting.check_free_slot(user["id"])
    parsed = parse_repo_url(url)
    if not parsed:
        raise OAuthError("Paste a GitHub or GitLab repository link, like https://github.com/you/your-site")
    provider, repo, branch = parsed
    prov = PROVIDERS[provider]
    if not branch:
        branch = prov.default_branch(None, repo, None)
    return create_from_repo(user, prov, repo, None, branch, (name or repo.split("/")[-1]).strip(), None, want_hook=False)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════
def init_integrations(app, deps):
    global _deps, _app
    _deps, _app = deps, app
    secrets_box.configure(app.secret_key)
    login_required = deps["login_required"]
    ensure_schema()
    hosting.git_info = git_info
    hosting.on_delete.append(remove_link)
    app.jinja_env.globals["oauth_enabled"] = enabled

    def _fail(msg, to="/login"):
        flash(msg, "error")
        return redirect(to)

    # ── start a sign-in ──────────────────────────────────────────────────────
    @app.route("/auth/<provider>")
    def oauth_signin(provider):
        prov = PROVIDERS.get(provider)
        if not prov or not prov.can_signin or not prov.configured():
            return _fail("That sign-in option isn't available.")
        state = secrets.token_urlsafe(24)
        session["oauth"] = {"state": state, "purpose": "signin", "provider": provider, "next": safe_next(request.args.get("next"))}
        return redirect(prov.authorize_url(state, prov.signin_scope))

    # ── start connecting a Git account ───────────────────────────────────────
    @app.route("/connect/<provider>")
    @login_required
    def oauth_connect(provider):
        prov = PROVIDERS.get(provider)
        if not prov or not prov.can_git or not prov.configured():
            return _fail("That Git provider isn't available.", "/git/import")
        state = secrets.token_urlsafe(24)
        session["oauth"] = {"state": state, "purpose": "connect", "provider": provider, "next": "/git/import"}
        if provider == "github":
            scope = "repo" if request.args.get("private") == "1" else "public_repo"
        else:
            scope = prov.signin_scope
        return redirect(prov.authorize_url(state, scope))

    # ── the one callback for both purposes ───────────────────────────────────
    @app.route("/oauth/<provider>/callback")
    def oauth_callback(provider):
        prov = PROVIDERS.get(provider)
        data = session.pop("oauth", None)
        if not prov or not data or data.get("provider") != provider:
            return _fail("That sign-in link expired. Please try again.")
        if not hmac.compare_digest(str(data.get("state", "")), str(request.args.get("state", ""))):
            return _fail("Sign-in could not be verified. Please try again.")
        if request.args.get("error"):
            return _fail("Sign-in was cancelled.", "/git/import" if data["purpose"] == "connect" else "/login")
        code = request.args.get("code", "")
        if not code:
            return _fail("No authorisation code was returned.")
        try:
            token = prov.exchange(code)
            if data["purpose"] == "signin":
                ident = prov.identity(token)
                user, created = resolve_user(provider, ident)
                if created:
                    try:
                        deps["email_welcome"](user["name"], user["email"])
                    except Exception as e:
                        print(f"[integrations] welcome email: {e}")
                resp = _login_user(user)
                if resp is not None:
                    return resp
                if created:
                    flash(f"Welcome {user['name']}! Deploy your first site to get started.", "success")
                return redirect(data.get("next") or "/dashboard")
            # connect
            if "user_id" not in session:
                return _fail("Please log in first.")
            _exec("DELETE FROM git_connections WHERE user_id=? AND provider=?", (session["user_id"], provider))
            _exec("INSERT INTO git_connections (user_id, provider, token_enc, account) VALUES (?,?,?,?)",
                  (session["user_id"], provider, encrypt_token(token), prov.account_label(token)))
            flash(f"{prov.label} connected.", "success")
            return redirect("/git/import")
        except OAuthError as e:
            return _fail(str(e), "/git/import" if data["purpose"] == "connect" else "/login")
        except Exception as e:
            print(f"[integrations] callback error: {e}")
            return _fail("Something went wrong signing you in. Please try again.",
                         "/git/import" if data["purpose"] == "connect" else "/login")

    @app.route("/connect/<provider>/disconnect", methods=["POST"])
    @login_required
    def oauth_disconnect(provider):
        if provider in PROVIDERS and PROVIDERS[provider].can_git:
            _exec("DELETE FROM git_connections WHERE user_id=? AND provider=?", (session["user_id"], provider))
            flash(f"{PROVIDERS[provider].label} disconnected. Projects stay live, but automatic deploys from private repositories stop.", "success")
        return redirect("/git/import")

    # ── import page ──────────────────────────────────────────────────────────
    @app.route("/git/import")
    @login_required
    def git_import():
        uid = session["user_id"]
        sections = []
        for name, prov in PROVIDERS.items():
            if not prov.can_git:
                continue
            sec = {"name": name, "label": prov.label, "configured": prov.configured(), "connected": False, "account": "", "repos": [], "error": ""}
            if prov.configured():
                row = _one("SELECT token_enc, account FROM git_connections WHERE user_id=? AND provider=?", (uid, name))
                if row:
                    sec["connected"], sec["account"] = True, row.get("account") or ""
                    tok = decrypt_token(row["token_enc"])
                    if tok:
                        try:
                            sec["repos"] = prov.list_repos(tok)
                        except OAuthError as e:
                            sec["error"] = str(e)
                    else:
                        sec["error"] = "Your saved connection can't be read any more. Reconnect."
            sections.append(sec)
        free_used = hosting.count_free_projects(uid)
        return render_template("git_import.html", sections=sections, current_user=deps["get_current_user"](),
                               free_full=free_used >= hosting.FREE_MAX_PROJECTS)

    # ── deploy a repo you picked ─────────────────────────────────────────────
    @app.route("/git/deploy", methods=["POST"])
    @login_required
    def git_deploy():
        user = dict(deps["get_current_user"]())
        provider = request.form.get("provider", "")
        prov = PROVIDERS.get(provider)
        if not prov or not prov.can_git:
            return _fail("Unknown Git provider.", "/git/import")
        pick = request.form.get("repo", "")
        try:
            repo_id, repo, default_branch = pick.split("::", 2)
        except ValueError:
            return _fail("Pick a repository.", "/git/import")
        branch = (request.form.get("branch") or "").strip() or default_branch
        name = (request.form.get("name") or repo.split("/")[-1]).strip()
        token = _connection_token(user["id"], provider)
        if not token:
            return _fail(f"Connect {prov.label} first.", "/git/import")
        try:
            hosting.check_free_slot(user["id"])
            res = create_from_repo(user, prov, repo, repo_id, branch, name, token, want_hook=True)
        except hosting.UploadError as e:
            return _fail(str(e), "/git/import")
        except OAuthError as e:
            return _fail(str(e), "/git/import")
        flash(res["message"], "success")
        if res.get("warnings"):
            flash("Heads up: " + " · ".join(res["warnings"][:4]), "success")
        return redirect(f"/hosting/site/{res['biz_id']}")

    # ── deploy a public repo from a URL (no login with the provider) ─────────
    @app.route("/git/deploy-public", methods=["POST"])
    @login_required
    def git_deploy_public():
        user = dict(deps["get_current_user"]())
        try:
            res = deploy_public(user, request.form.get("url", ""), request.form.get("name", ""))
        except (hosting.UploadError, OAuthError) as e:
            return _fail(str(e), "/git/import")
        flash(res["message"], "success")
        if res.get("warnings"):
            flash("Heads up: " + " · ".join(res["warnings"][:4]), "success")
        return redirect(f"/hosting/site/{res['biz_id']}")

    # ── Git settings for a project (branch, root directory, auto-deploy) ─────
    @app.route("/git/settings/<int:biz_id>", methods=["POST"])
    @login_required
    def git_settings(biz_id):
        row = _one("SELECT id FROM business WHERE id=? AND owner_id=?", (biz_id, session["user_id"]))
        link = _link(biz_id) if row else None
        if not link:
            return _fail("Not found.", "/dashboard")
        back = f"/hosting/site/{biz_id}?tab=settings#build"
        branch = (request.form.get("branch") or link["branch"]).strip()
        if not re.match(r"^[\w.\-/]{1,100}$", branch):
            return _fail("That branch name isn't valid.", back)
        try:
            root = hosting.clean_subdir(request.form.get("root_dir"))
        except hosting.UploadError as e:
            return _fail(str(e), back)
        auto = 1 if request.form.get("auto_deploy") == "on" else 0
        _exec("UPDATE git_links SET branch=?, root_dir=?, auto_deploy=? WHERE business_id=?", (branch, root, auto, biz_id))
        flash("Build settings saved. They apply to the next deploy.", "success")
        return redirect(back)

    @app.route("/git/hook/regenerate/<int:biz_id>", methods=["POST"])
    @login_required
    def git_hook_regenerate(biz_id):
        row = _one("SELECT id FROM business WHERE id=? AND owner_id=?", (biz_id, session["user_id"]))
        if not row or not _link(biz_id):
            return _fail("Not found.", "/dashboard")
        _exec("UPDATE git_links SET deploy_token=? WHERE business_id=?", (secrets.token_urlsafe(24), biz_id))
        flash("New deploy hook URL created. The old one no longer works.", "success")
        return redirect(f"/hosting/site/{biz_id}?tab=settings#build")

    @app.route("/hooks/deploy/<token>", methods=["POST", "GET"])
    def deploy_hook(token):
        """A private URL that redeploys the linked repository (like Render's deploy hook)."""
        if not re.match(r"^[A-Za-z0-9_\-]{20,64}$", token or ""):
            return "not found", 404
        link = _one("SELECT business_id FROM git_links WHERE deploy_token=?", (token,))
        if not link:
            return "not found", 404
        _run_async(deploy_link, link["business_id"], None, "deploy hook")
        return "deploy queued", 202

    # ── redeploy by hand ─────────────────────────────────────────────────────
    @app.route("/git/redeploy/<int:biz_id>", methods=["POST"])
    @login_required
    def git_redeploy(biz_id):
        row = _one("SELECT id FROM business WHERE id=? AND owner_id=?", (biz_id, session["user_id"]))
        if not row:
            return _fail("Not found.", "/dashboard#sites")
        ok, msg = deploy_link(biz_id, reason="manual redeploy")
        flash(("✅ " if ok else "") + msg, "success" if ok else "error")
        return redirect(f"/hosting/site/{biz_id}?tab=events")

    # ── webhook receiver ─────────────────────────────────────────────────────
    @app.route("/hooks/<provider>/<int:biz_id>", methods=["POST"])
    def git_webhook(provider, biz_id):
        prov = PROVIDERS.get(provider)
        link = _link(biz_id)
        if not prov or not link or link["provider"] != provider or not link.get("hook_secret"):
            return "not found", 404
        body = request.get_data()
        if not prov.verify_hook(request.headers, body, link["hook_secret"]):
            return "bad signature", 401
        if request.headers.get("X-GitHub-Event") == "ping":
            return "pong", 200
        if not link.get("auto_deploy", 1):
            return "ignored (auto-deploy is off)", 202
        if not prov.hook_event_ok(request.headers):
            return "ignored", 202
        branch, commit = prov.parse_push(request.get_json(silent=True) or {})
        if branch != link["branch"]:
            return "ignored (other branch)", 202
        if commit and commit == link.get("last_commit"):
            return "ignored (already deployed)", 202
        _run_async(deploy_link, biz_id, commit, "push")
        return "queued", 202
