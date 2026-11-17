"""
console.py — the TrustedBiz dashboard
═════════════════════════════════════
Projects list, project page (Events / Logs / Environment / Settings), account and
billing, new-project page, and the public status page. Business logic lives in
hosting.py and integrations.py; this file is the screens and their form actions.
"""
import re
import time

from flask import render_template, request, redirect, session, flash, jsonify

import hosting
import integrations

_STARTED = time.time()
_deps = None

TABS = ("events", "logs", "env", "settings")


def _q(sql, params=()):
    return _deps["db_fetchone"](_deps["q"](sql), params)


def _qa(sql, params=()):
    return _deps["db_fetchall"](_deps["q"](sql), params)


def _x(sql, params=()):
    return _deps["db_execute"](_deps["q"](sql), params)


def _is_app(row):
    return (row.get("app_kind") or "none") in hosting.APP_KINDS


def status_for(row):
    """(label, css class) for the badge shown on the dashboard and project page."""
    if row.get("status") == "suspended":
        return {"label": "Suspended", "cls": "bad"}
    if row.get("status") != "approved":
        return {"label": "Draft", "cls": ""}
    if row.get("owner_paused") or hosting.is_paused(row):
        return {"label": "Paused", "cls": "warn"}
    if row.get("maintenance_on"):
        return {"label": "Maintenance", "cls": "warn"}
    if _is_app(row):
        return ({"label": "Live", "cls": "ok"} if hosting._live(row) else {"label": "Waiting for server", "cls": "warn"})
    return {"label": "Live", "cls": "ok"}


def kind_label(row):
    k = row.get("app_kind") or "none"
    return {"python": "Python app", "node": "Node app"}.get(k, "Static site")


def _month_day(iso):
    from datetime import date
    try:
        d = date.fromisoformat(str(iso)[:10])
        return d.strftime("%b %-d, %Y")
    except Exception:
        return str(iso)[:10]


def _short_url(slug):
    return f"{slug}.trustedbiz.co.ug"


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
def dashboard_view():
    d = _deps
    uid = session["user_id"]
    hosting.renew_free_projects(uid)               # opening the dashboard keeps free projects live
    rows = [dict(r) for r in _qa("SELECT * FROM business WHERE owner_id=? ORDER BY id DESC", (uid,))]
    projects, free_count = [], 0
    for r in rows:
        link = None
        try:
            link = _q("SELECT repo FROM git_links WHERE business_id=?", (r["id"],))
        except Exception:
            pass
        last = _q("SELECT created_at FROM deploy_events WHERE business_id=? ORDER BY id DESC LIMIT 1", (r["id"],))
        paid = bool(r.get("is_premium"))
        free_count += 0 if paid or r.get("status") != "approved" else 1
        projects.append({
            "id": r["id"], "name": r["name"], "icon": (r["name"] or "?")[:2].upper(),
            "kind_label": kind_label(r), "url_short": _short_url(r["slug"]),
            "repo": dict(link)["repo"] if link else "", "plan": "Paid" if paid else "Free",
            "status": status_for(r), "updated": hosting.fmt_dt(dict(last)["created_at"]) if last else "",
        })
    notices = []
    try:
        for n in _qa("SELECT id, message FROM notifications WHERE user_id=? AND COALESCE(seen,0)=0 ORDER BY id DESC LIMIT 5", (uid,)):
            n = dict(n)
            # Renewal reminders are stale the moment the dashboard opens, so don't show them.
            if "will pause" not in n["message"] and "is paused" not in n["message"]:
                notices.append(n["message"])
        _x("UPDATE notifications SET seen=1 WHERE user_id=?", (uid,))
    except Exception as e:
        print(f"[console] notifications: {e}")
    paid_count = sum(1 for p in projects if p["plan"] == "Paid")
    return render_template("dashboard.html", projects=projects, notices=notices, current_user=d["get_current_user"](),
                           free_count=free_count, free_until=_month_day(hosting._renew_date()) if free_count else "",
                           paid_count=paid_count, admin_whatsapp=d["ADMIN_WHATSAPP"])


# ══════════════════════════════════════════════════════════════════════════════
def init_console(app, deps):
    global _deps
    _deps = deps
    login_required = deps["login_required"]

    def _owned(biz_id):
        r = _q("SELECT * FROM business WHERE id=? AND owner_id=?", (biz_id, session.get("user_id")))
        return dict(r) if r else None

    def _back(biz_id, tab="settings", anchor=""):
        return redirect(f"/hosting/site/{biz_id}?tab={tab}" + (f"#{anchor}" if anchor else ""))

    def _gone():
        flash("Not found.", "error")
        return redirect("/dashboard")

    # ── project page ─────────────────────────────────────────────────────────
    @app.route("/hosting/site/<int:biz_id>")
    @login_required
    def project_page(biz_id):
        b = _owned(biz_id)
        if not b:
            return _gone()
        is_app = _is_app(b)
        tab = request.args.get("tab", "events")
        if tab not in TABS or (tab in ("logs", "env") and not is_app):
            tab = "events"
        events = [{"message": e["message"], "status": e["status"], "when": hosting.fmt_dt(e["created_at"])}
                  for e in map(dict, _qa("SELECT message, status, created_at FROM deploy_events WHERE business_id=? ORDER BY id DESC LIMIT 40", (biz_id,)))]
        backups = []
        for s in _qa("SELECT id, created_at, html_snapshot FROM site_backups WHERE business_id=? ORDER BY id DESC LIMIT 5", (biz_id,)):
            s = dict(s)
            backups.append({"id": s["id"], "created_at": hosting.fmt_dt(s["created_at"]), "size": len(s.get("html_snapshot") or "")})
        bundle = None
        if is_app:
            r = _q("SELECT size FROM app_bundles WHERE business_id=? ORDER BY id DESC", (biz_id,))
            bundle = dict(r) if r else None
        from urllib.parse import quote
        wa_text = quote(f'Hi TrustedBiz, I want to upgrade "{b.get("name")}" ({b.get("slug")}.trustedbiz.co.ug) to the Paid plan.')
        return render_template(
            "project.html", b=b, is_app=is_app, live=hosting._live(b), limits=hosting.plan_limits(b), kind_label=kind_label(b),
            status=status_for(b), git=hosting.git_info(biz_id), events=events, backups=backups, bundle=bundle,
            env_names=hosting.env_names(biz_id) if is_app else [], cfg=hosting._json_or_empty(b.get("app_config")),
            tab=tab, url=f"https://{b['slug']}.trustedbiz.co.ug", wa_link=f'https://wa.me/{deps["ADMIN_WHATSAPP"]}?text={wa_text}',
            monthly="{:,}".format(deps["HOSTING_FEE_MONTHLY"]), yearly="{:,}".format(deps["HOSTING_FEE_YEARLY"]),
            domain={"name": b.get("custom_domain"), "status": b.get("domain_status")},
            paused_owner=bool(b.get("owner_paused")), maint_on=bool(b.get("maintenance_on")),
            current_user=deps["get_current_user"](), paid_count=1 if b.get("is_premium") else 0)

    # ── settings actions ─────────────────────────────────────────────────────
    @app.route("/hosting/rename/<int:biz_id>", methods=["POST"])
    @login_required
    def project_rename(biz_id):
        b = _owned(biz_id)
        if not b:
            return _gone()
        name = (request.form.get("name") or "").strip()[:100]
        if not name:
            flash("A project needs a name.", "error")
        else:
            _x("UPDATE business SET name=? WHERE id=?", (name, biz_id))
            flash("Name saved.", "success")
        return _back(biz_id, "settings", "general")

    @app.route("/hosting/maintenance/<int:biz_id>", methods=["POST"])
    @login_required
    def project_maintenance(biz_id):
        b = _owned(biz_id)
        if not b:
            return _gone()
        if not b.get("is_premium"):
            flash("Maintenance mode is part of the Paid plan.", "error")
            return _back(biz_id, "settings", "plan")
        url = (request.form.get("url") or "").strip()
        if url and not re.match(r"^https?://[^\s]+$", url):
            flash("The maintenance page must be a full link starting with https://", "error")
            return _back(biz_id, "settings", "maintenance")
        on = 1 if request.form.get("on") == "on" else 0
        _x("UPDATE business SET maintenance_on=?, maintenance_url=? WHERE id=?", (on, url or None, biz_id))
        deps["log_deploy_event"](biz_id, session["user_id"], "maintenance", "Maintenance mode " + ("turned on" if on else "turned off"), "ok")
        flash("Maintenance mode " + ("is on. Visitors now see the maintenance page." if on else "is off."), "success")
        return _back(biz_id, "settings", "maintenance")

    @app.route("/hosting/pause/<int:biz_id>", methods=["POST"])
    @login_required
    def project_pause(biz_id):
        b = _owned(biz_id)
        if not b:
            return _gone()
        new = 0 if b.get("owner_paused") else 1
        _x("UPDATE business SET owner_paused=? WHERE id=?", (new, biz_id))
        deps["log_deploy_event"](biz_id, session["user_id"], "pause", "Project paused by you" if new else "Project resumed", "ok")
        flash("Project paused. Visitors see a paused page." if new else "Project resumed.", "success")
        return _back(biz_id, "settings", "danger")

    @app.route("/hosting/notify/<int:biz_id>", methods=["POST"])
    @login_required
    def project_notify(biz_id):
        if not _owned(biz_id):
            return _gone()
        mode = request.form.get("mode")
        if mode in ("all", "failed", "none"):
            _x("UPDATE business SET notify_deploys=? WHERE id=?", (mode, biz_id))
            flash("Notification setting saved.", "success")
        return _back(biz_id, "settings", "notifications")

    @app.route("/hosting/env/<int:biz_id>", methods=["POST"])
    @login_required
    def project_env_set(biz_id):
        b = _owned(biz_id)
        if not b or not _is_app(b):
            return _gone()
        try:
            hosting.env_set(biz_id, request.form.get("name"), request.form.get("value", ""))
            flash(f'{request.form.get("name", "").strip()} saved.', "success")
        except hosting.UploadError as e:
            flash(str(e), "error")
        return _back(biz_id, "env")

    @app.route("/hosting/env/<int:biz_id>/delete", methods=["POST"])
    @login_required
    def project_env_delete(biz_id):
        b = _owned(biz_id)
        if not b or not _is_app(b):
            return _gone()
        hosting.env_delete(biz_id, (request.form.get("name") or "").strip())
        flash("Variable deleted.", "success")
        return _back(biz_id, "env")

    @app.route("/hosting/domain/remove/<int:biz_id>", methods=["POST"])
    @login_required
    def project_domain_remove(biz_id):
        b = _owned(biz_id)
        if not b:
            return _gone()
        _x("UPDATE business SET custom_domain=NULL, domain_status=NULL WHERE id=?", (biz_id,))
        deps["log_deploy_event"](biz_id, session["user_id"], "domain_removed", f'Custom domain "{b.get("custom_domain")}" removed', "ok")
        flash("Domain removed.", "success")
        return _back(biz_id, "settings", "domains")

    @app.route("/hosting/upload/<int:biz_id>", methods=["POST"])
    @login_required
    def project_upload(biz_id):
        b = _owned(biz_id)
        if not b:
            return _gone()
        f = request.files.get("project_file")
        if not f or not f.filename:
            flash("Choose a ZIP or HTML file.", "error")
            return _back(biz_id, "settings", "update")
        try:
            raw = f.read(hosting.MAX_STATIC_ZIP_BYTES + 1)
            prep = hosting.prepare_upload(raw, f.filename)
            res = hosting.update_project(biz_id, session["user_id"], prep, note="updated from an upload")
            flash("✅ Deployed.", "success")
            if res.get("warnings"):
                flash("Heads up: " + " · ".join(res["warnings"][:4]), "success")
        except hosting.UploadError as e:
            flash(str(e), "error")
        except Exception as e:
            print(f"[console] upload error: {e}")
            flash("Something went wrong. Your project was not changed.", "error")
        return _back(biz_id, "events")

    # ── new project ──────────────────────────────────────────────────────────
    @app.route("/new")
    @login_required
    def new_project():
        free_full = hosting.count_free_projects(session["user_id"]) >= hosting.FREE_MAX_PROJECTS
        return render_template("new_project.html", current_user=deps["get_current_user"](), free_full=free_full, paid_count=0)

    # ── account + billing ────────────────────────────────────────────────────
    @app.route("/account")
    @login_required
    def account_page():
        uid = session["user_id"]
        user = deps["get_current_user"]()
        billing = []
        for r in map(dict, _qa("SELECT * FROM business WHERE owner_id=? ORDER BY id DESC", (uid,))):
            paid = bool(r.get("is_premium"))
            if r.get("status") == "suspended":
                note = "Suspended (unpaid)"
            elif paid:
                note = "Active"
            else:
                note = "Stays live while you open the dashboard"
            billing.append({"id": r["id"], "name": r["name"], "plan": "Paid" if paid else "Free", "note": note,
                            "last_payment": _month_day(r["last_payment_date"]) if r.get("last_payment_date") else ""})
        identities = [{"label": integrations.PROVIDERS[i["provider"]].label if i["provider"] in integrations.PROVIDERS else i["provider"], "email": i.get("email") or ""}
                      for i in map(dict, _qa("SELECT provider, email FROM oauth_identities WHERE user_id=?", (uid,)))]
        gits = []
        for key, prov in integrations.PROVIDERS.items():
            if not prov.can_git:
                continue
            row = _q("SELECT account FROM git_connections WHERE user_id=? AND provider=?", (uid, key))
            gits.append({"key": key, "label": prov.label, "configured": prov.configured(), "connected": bool(row), "account": dict(row)["account"] if row else ""})
        return render_template("account.html", current_user=user, billing=billing, identities=identities, gits=gits,
                               two_factor=bool(dict(user).get("two_factor_enabled")), paid_count=sum(1 for b in billing if b["plan"] == "Paid"),
                               monthly="{:,}".format(deps["HOSTING_FEE_MONTHLY"]), yearly="{:,}".format(deps["HOSTING_FEE_YEARLY"]),
                               admin_whatsapp=deps["ADMIN_WHATSAPP"])

    @app.route("/account/name", methods=["POST"])
    @login_required
    def account_name():
        name = (request.form.get("name") or "").strip()[:100]
        if name:
            _x("UPDATE users SET name=? WHERE id=?", (name, session["user_id"]))
            session["user_name"] = name
            flash("Name saved.", "success")
        return redirect("/account#profile")

    # ── public status page ───────────────────────────────────────────────────
    def _components():
        comps = []
        try:
            _q("SELECT 1 AS ok")
            db_ok = True
        except Exception:
            db_ok = False
        comps.append({"name": "Website and dashboard", "detail": "The TrustedBiz site and your dashboard.", "state": "Operational" if db_ok else "Down", "cls": "ok" if db_ok else "bad"})
        comps.append({"name": "Static site hosting", "detail": "Serving your sites on their addresses.", "state": "Operational" if db_ok else "Down", "cls": "ok" if db_ok else "bad"})
        gits = [p.label for p in integrations.PROVIDERS.values() if p.can_git and p.configured()]
        comps.append({"name": "Git deploys", "detail": ("Available: " + ", ".join(gits)) if gits else "No Git provider is set up on this server yet.",
                      "state": "Operational" if gits else "Not set up", "cls": "ok" if gits else ""})
        signins = [p.label for p in integrations.PROVIDERS.values() if p.can_signin and p.configured()]
        comps.append({"name": "Sign in with Google or GitHub", "detail": ("Available: " + ", ".join(signins)) if signins else "Not set up yet. Email sign-in works.",
                      "state": "Operational" if signins else "Not set up", "cls": "ok" if signins else ""})
        comps.append({"name": "App hosting (Python and Node)", "detail": "Uploads are stored safely until app hosting launches." if not hosting.APP_HOSTING_ENABLED else "Running apps and serving their addresses.",
                      "state": "Operational" if hosting.APP_HOSTING_ENABLED else "Not launched yet", "cls": "ok" if hosting.APP_HOSTING_ENABLED else "warn"})
        return comps, db_ok

    def _uptime():
        s = int(time.time() - _STARTED)
        d, s = divmod(s, 86400)
        h, s = divmod(s, 3600)
        m = s // 60
        return (f"{d}d " if d else "") + f"{h}h {m}m"

    @app.route("/status")
    def status_page():
        comps, ok = _components()
        return render_template("status.html", components=comps, overall_ok=ok, uptime=_uptime(),
                               current_user=deps["get_current_user"](), admin_whatsapp=deps["ADMIN_WHATSAPP"])

    @app.route("/status.json")
    def status_json():
        comps, ok = _components()
        return jsonify({"ok": ok, "components": [{"name": c["name"], "state": c["state"]} for c in comps]})
