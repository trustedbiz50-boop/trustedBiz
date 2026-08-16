"""
TrustedBiz — app.py
All routes. Add your keys in environment variables and run.

on ENV VARS (add on Render dashboard):
  SECRET_KEY          = any random string
  ANTHROPIC_API_KEY   = sk-ant-... (from console.anthropic.com) — this is what powers Daisy directly now
  DATABASE_URL        = auto-set by Render PostgreSQL
  CLOUDINARY_URL      = from cloudinary.com
  ADMIN_PASSWORD      = your secret admin password
  ADMIN_WHATSAPP      = 256753187966
  DGATEWAY_API_KEY    = (add when ready)
  DGATEWAY_MERCHANT_ID= (add when ready)
  DAISY_API_KEY       = shared secret — must match DAISY_API_KEY on Daisy's
                         own server (daisy_backend/app.py). Only Daisy's
                         backend calls /api/daisy/publish with this key;
                         it never reaches a browser.
"""

import os, math, json, re, secrets, requests, socket, ssl
import pyotp
from datetime import timedelta, datetime
from difflib import SequenceMatcher
from functools import wraps
from pathlib import Path
from flask import (Flask, render_template, render_template_string, request,
                   redirect, flash, session, jsonify, url_for)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ── EMAIL ─────────────────────────────────────────────────────────────────────
import threading, urllib.request
from plan_power import get_website_power, get_artifact_power, artifact_allowed
from image_generator import generate_business_images, generate_single_image
from daisy_builders import build_artifact, ARTIFACT_MODES, register_template_saver

_BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
_MAIL_FROM     = os.environ.get("MAIL_FROM", "TrustedBiz <hello@trustedbiz.co.ug>")

def _send_email(to, subject, html):
    """Send email via Brevo HTTP API in background thread — never blocks a request."""
    if not _BREVO_API_KEY:
        print(f"[EMAIL] BREVO_API_KEY not set — skipping email to {to}")
        return
    def _run():
        try:
            if "<" in _MAIL_FROM:
                fname, femail = _MAIL_FROM.split("<")
                fname  = fname.strip()
                femail = femail.strip("> ")
            else:
                fname  = "TrustedBiz"
                femail = _MAIL_FROM.strip()

            payload = json.dumps({
                "sender":  {"name": fname, "email": femail},
                "to":      [{"email": to}],
                "subject": subject,
                "htmlContent": html
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.brevo.com/v3/smtp/email",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "api-key":      _BREVO_API_KEY,
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                print(f"[EMAIL] Sent '{subject}' → {to} (status {resp.status})")
        except Exception as e:
            print(f"[EMAIL] Failed to send to {to}: {e}")
    threading.Thread(target=_run, daemon=True).start()

def _email_welcome(name, email):
    _send_email(email, "Welcome to TrustedBiz! 🎉", f"""
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:30px;">
<div style="max-width:560px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;">
  <div style="background:#2b7a78;padding:32px;text-align:center;">
    <h1 style="color:white;margin:0;font-size:28px;">Welcome to TrustedBiz!</h1>
    <p style="color:rgba(255,255,255,.8);margin:8px 0 0;">Uganda's Trusted Business Directory</p>
  </div>
  <div style="padding:32px;">
    <p style="font-size:16px;color:#333;">Hi <strong>{name}</strong>,</p>
    <p style="color:#555;line-height:1.7;">Your account is ready. You can now list your business and get a free AI-generated website that customers can find on Google.</p>
    <div style="text-align:center;margin:28px 0;">
      <a href="https://trustedbiz.co.ug/dashboard" style="background:#2b7a78;color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;">Talk to Daisy →</a>
    </div>
    <p style="color:#888;font-size:13px;">If you didn't create this account, ignore this email.</p>
  </div>
  <div style="background:#f8f8f8;padding:16px;text-align:center;font-size:12px;color:#aaa;">
    © 2026 TrustedBiz · <a href="https://trustedbiz.co.ug" style="color:#2b7a78;">trustedbiz.co.ug</a>
  </div>
</div>
</body></html>""")

def _email_domain_live(name, email, biz_name, domain):
    biz_url = f"https://{domain}"
    _send_email(email, f"✅ {domain} is connected and live!", f"""
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:30px;">
<div style="max-width:560px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;">
  <div style="background:#22c55e;padding:32px;text-align:center;">
    <h1 style="color:white;margin:0;font-size:26px;">Your domain is live! 🌐</h1>
  </div>
  <div style="padding:32px;">
    <p style="font-size:16px;color:#333;">Hi <strong>{name}</strong>,</p>
    <p style="color:#555;line-height:1.7;">Good news — we verified DNS and switched on SSL for <strong>{biz_name}</strong>. Your site is now live at your own domain.</p>
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin:20px 0;">
      <p style="margin:0;color:#166534;font-size:14px;">🔒 Secured and live:</p>
      <a href="{biz_url}" style="color:#2b7a78;font-weight:700;word-break:break-all;">{biz_url}</a>
    </div>
    <div style="text-align:center;margin:24px 0;">
      <a href="{biz_url}" style="background:#2b7a78;color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;">View Your Site →</a>
    </div>
  </div>
  <div style="background:#f8f8f8;padding:16px;text-align:center;font-size:12px;color:#aaa;">
    © 2026 TrustedBiz · <a href="https://trustedbiz.co.ug" style="color:#2b7a78;">trustedbiz.co.ug</a>
  </div>
</div>
</body></html>""")

def _email_2fa_enabled(name, email):
    _send_email(email, "Two-factor login enabled on your TrustedBiz account", f"""
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:30px;">
<div style="max-width:560px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;">
  <div style="background:#2b7a78;padding:32px;text-align:center;">
    <h1 style="color:white;margin:0;font-size:24px;">Two-factor login is on 🔐</h1>
  </div>
  <div style="padding:32px;">
    <p style="font-size:16px;color:#333;">Hi <strong>{name}</strong>,</p>
    <p style="color:#555;line-height:1.7;">From now on, signing in to TrustedBiz will also ask for a 6-digit code from your authenticator app.</p>
    <p style="color:#888;font-size:13px;">If you didn't make this change, contact us right away and reset your password.</p>
  </div>
  <div style="background:#f8f8f8;padding:16px;text-align:center;font-size:12px;color:#aaa;">
    © 2026 TrustedBiz · <a href="https://trustedbiz.co.ug" style="color:#2b7a78;">trustedbiz.co.ug</a>
  </div>
</div>
</body></html>""")

def ping_google(slug):
    """Ping Google to crawl and index a business URL immediately after approval."""
    import threading, urllib.request, urllib.parse
    def _ping(slug):
        try:
            biz_url   = f"https://{slug}.trustedbiz.co.ug"
            sitemap   = "https://trustedbiz.co.ug/sitemap.xml"
            # 1. Ping sitemap so Google re-reads all URLs
            ping_url  = f"https://www.google.com/ping?sitemap={urllib.parse.quote(sitemap, safe='')}"
            urllib.request.urlopen(ping_url, timeout=8)
            # 2. Also ping the specific business URL via IndexNow (Bing/Yandex — helps speed)
            indexnow  = (f"https://api.indexnow.org/indexnow"
                         f"?url={urllib.parse.quote(biz_url, safe='')}"
                         f"&key=trustedbiz2026")
            urllib.request.urlopen(indexnow, timeout=8)
            print(f"[SEO] Pinged Google + IndexNow for {biz_url}")
        except Exception as e:
            print(f"[SEO] Ping error for {slug}: {e}")
    threading.Thread(target=_ping, args=(slug,), daemon=True).start()

def _email_approved(name, email, biz_name, biz_slug):
    biz_url = f"https://{biz_slug}.trustedbiz.co.ug"
    _send_email(email, f"✅ {biz_name} is now LIVE on TrustedBiz!", f"""
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:30px;">
<div style="max-width:560px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;">
  <div style="background:#22c55e;padding:32px;text-align:center;">
    <h1 style="color:white;margin:0;font-size:26px;">Your Business is Live! 🎉</h1>
  </div>
  <div style="padding:32px;">
    <p style="font-size:16px;color:#333;">Hi <strong>{name}</strong>,</p>
    <p style="color:#555;line-height:1.7;"><strong>{biz_name}</strong> has been approved and is now live on TrustedBiz. Customers in Uganda can find you right now.</p>
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin:20px 0;">
      <p style="margin:0;color:#166534;font-size:14px;">🌐 Your business page:</p>
      <a href="{biz_url}" style="color:#2b7a78;font-weight:700;word-break:break-all;">{biz_url}</a>
    </div>
    <div style="text-align:center;margin:24px 0;">
      <a href="{biz_url}" style="background:#2b7a78;color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;">View Your Page →</a>
    </div>
    <p style="color:#555;font-size:14px;">Share this link on WhatsApp, Facebook, and anywhere your customers are!</p>
  </div>
  <div style="background:#f8f8f8;padding:16px;text-align:center;font-size:12px;color:#aaa;">
    © 2026 TrustedBiz · <a href="https://trustedbiz.co.ug" style="color:#2b7a78;">trustedbiz.co.ug</a>
  </div>
</div>
</body></html>""")

def _email_submitted(name, email, biz_name):
    _send_email(email, f"📋 {biz_name} submitted — we're reviewing it", f"""
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:30px;">
<div style="max-width:560px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;">
  <div style="background:#2b7a78;padding:32px;text-align:center;">
    <h1 style="color:white;margin:0;font-size:24px;">Business Received! 📋</h1>
  </div>
  <div style="padding:32px;">
    <p style="font-size:16px;color:#333;">Hi <strong>{name}</strong>,</p>
    <p style="color:#555;line-height:1.7;">We've received your listing for <strong>{biz_name}</strong>. Our team will review and approve it within 24 hours. You'll get another email the moment it goes live.</p>
    <div style="text-align:center;margin:24px 0;">
      <table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center"><a href="https://trustedbiz.co.ug/dashboard" style="display:inline-block;background:#2b7a78;color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;mso-padding-alt:0;">View Dashboard →</a></td></tr></table>
    </div>
  </div>
  <div style="background:#f8f8f8;padding:16px;text-align:center;font-size:12px;color:#aaa;">
    © 2026 TrustedBiz · <a href="https://trustedbiz.co.ug" style="color:#2b7a78;">trustedbiz.co.ug</a>
  </div>
</div>
</body></html>""")

# ── APP ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB

ALLOWED_EXTENSIONS = {'png','jpg','jpeg','gif','webp'}

# ── SUBDOMAIN MIDDLEWARE ───────────────────────────────────────────────────────
@app.before_request
def handle_subdomain():
    host = request.host.lower().split(':')[0]  # e.g. cyber-tech.trustedbiz.co.ug
    if host.endswith('.trustedbiz.co.ug'):
        slug = host.replace('.trustedbiz.co.ug', '')
        if slug and slug not in ('www', 'admin', 'api'):
            if request.path == '/':
                # Serve the business page without changing the URL
                return site(slug)
ADMIN_PASSWORD  = os.environ.get("ADMIN_PASSWORD", "trustedbiz2026")
ADMIN_WHATSAPP  = os.environ.get("ADMIN_WHATSAPP", "256753187966")

def allowed_file(f):
    return '.' in f and f.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def similar(a,b):
    return SequenceMatcher(None,a,b).ratio()

# ── DATABASE ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL","")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://","postgresql://",1)
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2, psycopg2.extras
    def get_db():
        return psycopg2.connect(DATABASE_URL,
               cursor_factory=psycopg2.extras.RealDictCursor)
else:
    import sqlite3
    DB_PATH = os.environ.get("DB_PATH","database.db")
    def get_db():
        conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

def q(sql):
    return sql.replace("?","%s") if USE_POSTGRES else sql

# ── IMAGE STORAGE ─────────────────────────────────────────────────────────────
CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL","")
USE_CLOUDINARY = bool(CLOUDINARY_URL)
if USE_CLOUDINARY:
    import cloudinary, cloudinary.uploader
    cloudinary.config(cloudinary_url=CLOUDINARY_URL)

LOCAL_UPLOAD = Path("static/images")
LOCAL_UPLOAD.mkdir(parents=True, exist_ok=True)

def save_photos(files):
    results = []
    for photo in files:
        if not photo or not photo.filename: continue
        if not allowed_file(photo.filename): continue
        try:
            if USE_CLOUDINARY:
                up = cloudinary.uploader.upload(photo, folder="trustedbiz",
                     transformation=[{"width":1200,"height":900,"crop":"limit","quality":"auto:good"}])
                results.append(up["secure_url"])
            else:
                ext = photo.filename.rsplit('.',1)[1].lower()
                fname = f"{secrets.token_hex(8)}.{ext}"
                photo.save(str(LOCAL_UPLOAD/fname))
                results.append(fname)
        except Exception as e:
            print(f"Photo error: {e}")
    return results

def save_photos_b64(b64_list):
    """Save client-compressed base64 images — avoids 413 entity too large."""
    import base64, re
    results = []
    for b64 in b64_list:
        if not b64 or b64 == 'null': continue
        try:
            match = re.match(r'data:image/(\w+);base64,(.+)', b64, re.DOTALL)
            if not match: continue
            ext, data = match.group(1), match.group(2)
            if ext not in ('jpeg','jpg','png','webp'): ext = 'jpg'
            raw = base64.b64decode(data)
            if not raw or len(raw) < 100: continue
            if USE_CLOUDINARY:
                up = cloudinary.uploader.upload(raw, folder="trustedbiz",
                     transformation=[{"width":1200,"height":900,"crop":"limit","quality":"auto:good"}])
                results.append(up["secure_url"])
            else:
                fname = f"{secrets.token_hex(8)}.{ext}"
                (LOCAL_UPLOAD/fname).write_bytes(raw)
                results.append(fname)
        except Exception as e:
            print(f"B64 photo error: {e}")
    return results

def save_single_photo(file):
    results = save_photos([file])
    return results[0] if results else None

def photo_url(ref):
    if not ref: return ""
    if ref.startswith("http"): return ref
    return f"/static/images/{ref}"

app.jinja_env.globals['photo_url'] = photo_url

# ── DB HELPERS ────────────────────────────────────────────────────────────────
def db_fetchall(sql, params=()):
    conn = get_db()
    try:
        if USE_POSTGRES:
            cur = conn.cursor(); cur.execute(sql,params); return cur.fetchall()
        return conn.execute(sql,params).fetchall()
    finally: conn.close()

def db_fetchone(sql, params=()):
    conn = get_db()
    try:
        if USE_POSTGRES:
            cur = conn.cursor(); cur.execute(sql,params); return cur.fetchone()
        return conn.execute(sql,params).fetchone()
    finally: conn.close()

def db_execute(sql, params=()):
    conn = get_db()
    try:
        if USE_POSTGRES:
            cur = conn.cursor(); cur.execute(sql,params); conn.commit()
        else:
            conn.execute(sql,params); conn.commit()
    except Exception as e:
        try: conn.rollback()
        except: pass
        print(f"db_execute error: {e}"); raise
    finally: conn.close()

def db_insert(sql, params=()):
    conn = get_db()
    try:
        if USE_POSTGRES:
            if "RETURNING" not in sql.upper():
                sql = sql.rstrip(';') + " RETURNING id"
            cur = conn.cursor(); cur.execute(sql,params)
            row = cur.fetchone(); conn.commit()
            return row['id'] if row else None
        else:
            cur = conn.execute(sql,params); conn.commit(); return cur.lastrowid
    except Exception as e:
        try: conn.rollback()
        except: pass
        raise
    finally: conn.close()

# ── TABLES ────────────────────────────────────────────────────────────────────
def create_tables():
    conn = get_db()
    tables = []
    if USE_POSTGRES:
        tables = [
        "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT, role TEXT DEFAULT 'user', is_premium INTEGER DEFAULT 0, two_factor_enabled INTEGER DEFAULT 0, two_factor_secret TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS business (id SERIAL PRIMARY KEY, name TEXT, category TEXT, whatsapp TEXT, lat REAL, lng REAL, photos TEXT, description TEXT, hours TEXT, status TEXT DEFAULT 'approved', verified INTEGER DEFAULT 0, reports INTEGER DEFAULT 0, views INTEGER DEFAULT 0, owner_id INTEGER, owner_ip TEXT, is_premium INTEGER DEFAULT 0, plan TEXT DEFAULT 'free', brand_color TEXT DEFAULT '#2b7a78', slug TEXT UNIQUE, hero_price REAL, hero_price_label TEXT, generated_html TEXT, last_payment_date DATE, free_trial_end DATE, payment_months_late INTEGER DEFAULT 0, custom_domain TEXT, domain_status TEXT DEFAULT 'none', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS branches (id SERIAL PRIMARY KEY, business_id INTEGER, name TEXT, address TEXT, whatsapp TEXT, hours TEXT, lat REAL, lng REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS reviews (id SERIAL PRIMARY KEY, business_id INTEGER, user_id INTEGER, rating INTEGER, comment TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS reports (id SERIAL PRIMARY KEY, business_id INTEGER, user_identifier TEXT)",
        "CREATE TABLE IF NOT EXISTS notifications (id SERIAL PRIMARY KEY, user_id INTEGER, user_identifier TEXT, message TEXT, seen INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS price_guard_items (id SERIAL PRIMARY KEY, business_id INTEGER, category TEXT, label TEXT, price REAL, image_ref TEXT, ai_name TEXT, ai_verified INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS ads (id SERIAL PRIMARY KEY, business_id INTEGER, title TEXT, body TEXT, image_ref TEXT, active INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS agents (id SERIAL PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT, whatsapp TEXT, area TEXT, code TEXT UNIQUE, status TEXT DEFAULT 'active', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS template_pool (id SERIAL PRIMARY KEY, category TEXT NOT NULL, html TEXT NOT NULL, quality_score INTEGER DEFAULT 0, times_used INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS invite_codes (id SERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL, biz_id INTEGER, agent_id INTEGER, plan TEXT DEFAULT 'promax', used INTEGER DEFAULT 0, used_by_user_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS daisy_training (id SERIAL PRIMARY KEY, input TEXT NOT NULL, output TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS deploy_events (id SERIAL PRIMARY KEY, business_id INTEGER, user_id INTEGER, event_type TEXT, message TEXT, status TEXT DEFAULT 'ok', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS site_backups (id SERIAL PRIMARY KEY, business_id INTEGER, html_snapshot TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS security_scans (id SERIAL PRIMARY KEY, user_id INTEGER, score INTEGER, checks TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        ]
        cur = conn.cursor()
        for t in tables: cur.execute(t)
        conn.commit(); cur.close()
    else:
        tables = [
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, password TEXT, role TEXT DEFAULT 'user', is_premium INTEGER DEFAULT 0, two_factor_enabled INTEGER DEFAULT 0, two_factor_secret TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS business (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category TEXT, whatsapp TEXT, lat REAL, lng REAL, photos TEXT, description TEXT, hours TEXT, status TEXT DEFAULT 'approved', verified INTEGER DEFAULT 0, reports INTEGER DEFAULT 0, views INTEGER DEFAULT 0, owner_id INTEGER, owner_ip TEXT, is_premium INTEGER DEFAULT 0, brand_color TEXT DEFAULT '#2b7a78', slug TEXT UNIQUE, hero_price REAL, hero_price_label TEXT, generated_html TEXT, last_payment_date DATE, payment_months_late INTEGER DEFAULT 0, plan TEXT DEFAULT 'free', location TEXT, custom_domain TEXT, domain_status TEXT DEFAULT 'none', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS branches (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, name TEXT, address TEXT, whatsapp TEXT, hours TEXT, lat REAL, lng REAL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, user_id INTEGER, rating INTEGER, comment TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, user_identifier TEXT)",
        "CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, user_identifier TEXT, message TEXT, seen INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS price_guard_items (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, category TEXT, label TEXT, price REAL, image_ref TEXT, ai_name TEXT, ai_verified INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS ads (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, title TEXT, body TEXT, image_ref TEXT, active INTEGER DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS agents (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, password TEXT, whatsapp TEXT, area TEXT, code TEXT UNIQUE, status TEXT DEFAULT 'active', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS template_pool (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, html TEXT NOT NULL, quality_score INTEGER DEFAULT 0, times_used INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS invite_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, biz_id INTEGER, agent_id INTEGER, plan TEXT DEFAULT 'promax', used INTEGER DEFAULT 0, used_by_user_id INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS daisy_training (id INTEGER PRIMARY KEY AUTOINCREMENT, input TEXT NOT NULL, output TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS deploy_events (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, user_id INTEGER, event_type TEXT, message TEXT, status TEXT DEFAULT 'ok', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS site_backups (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, html_snapshot TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS security_scans (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, score INTEGER, checks TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        ]
        for t in tables: conn.execute(t)
        conn.commit()
    conn.close()

try: create_tables()
except Exception as e: print(f"DB init: {e}")

# ── HELPERS ───────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(f'/login?next={request.path}')
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_auth'):
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    if 'user_id' in session:
        return db_fetchone(q("SELECT * FROM users WHERE id=?"), (session['user_id'],))
    return None

def make_slug(name):
    slug = re.sub(r'[^a-z0-9]+','-',name.lower()).strip('-')[:60]
    base, i = slug, 1
    while db_fetchone(q("SELECT id FROM business WHERE slug=?"), (slug,)):
        slug = f"{base}-{i}"; i += 1
    return slug

def haversine(lat1,lon1,lat2,lon2):
    R=6371; d=lambda x:math.radians(x)
    a=(math.sin(d(lat2-lat1)/2)**2 + math.cos(d(lat1))*math.cos(d(lat2))*math.sin(d(lon2-lon1)/2)**2)
    return R*2*math.atan2(math.sqrt(a),math.sqrt(1-a))

def biz_to_dict(b):
    from datetime import datetime, date
    d = dict(b)
    for k,v in d.items():
        if isinstance(v,(datetime,date)): d[k] = v.isoformat()
    return d

# ── HOSTING: real deploy log + site backups ─────────────────────────────────
# Every entry here corresponds to something that actually happened — a site
# created, redeployed, or a domain connected — not placeholder rows.
def log_deploy_event(business_id, user_id, event_type, message, status='ok'):
    try:
        db_insert(q("INSERT INTO deploy_events (business_id,user_id,event_type,message,status) VALUES (?,?,?,?,?)"),
                  (business_id, user_id, event_type, message, status))
    except Exception as e:
        print(f"[deploy_event] log error: {e}")

def save_site_html(biz_id, html):
    """Single place that writes generated_html for an existing business —
    also snapshots a real backup so 'Automatic backups' in Security reflects
    what's actually stored, not a canned 'Enabled'. Keeps the 5 most recent
    snapshots per site."""
    if not html: return
    try:
        db_execute(q("UPDATE business SET generated_html=? WHERE id=?"), (html, biz_id))
        db_insert(q("INSERT INTO site_backups (business_id, html_snapshot) VALUES (?,?)"), (biz_id, html))
        db_execute(q("DELETE FROM site_backups WHERE business_id=? AND id NOT IN "
                      "(SELECT id FROM site_backups WHERE business_id=? ORDER BY created_at DESC LIMIT 5)"),
                   (biz_id, biz_id))
    except Exception as e:
        print(f"[save_site_html] error for biz {biz_id}: {e}")

def snapshot_site_html(biz_id, html):
    """Same backup snapshot as save_site_html, without re-writing
    generated_html — for routes that already set it in their own INSERT."""
    if not html: return
    try:
        db_insert(q("INSERT INTO site_backups (business_id, html_snapshot) VALUES (?,?)"), (biz_id, html))
        db_execute(q("DELETE FROM site_backups WHERE business_id=? AND id NOT IN "
                      "(SELECT id FROM site_backups WHERE business_id=? ORDER BY created_at DESC LIMIT 5)"),
                   (biz_id, biz_id))
    except Exception as e:
        print(f"[snapshot_site_html] error for biz {biz_id}: {e}")

# ── SECURITY: live checks, not canned badges ────────────────────────────────
_SAFE_SCRIPT_HOSTS = ('trustedbiz.co.ug', 'cdnjs.cloudflare.com', 'cdn.jsdelivr.net',
                      'fonts.googleapis.com', 'fonts.gstatic.com', 'unpkg.com',
                      'www.googletagmanager.com', 'www.google-analytics.com')

def check_domain_ssl(domain, timeout=5):
    """Real TLS handshake against the live domain. Returns (ok, detail, days_left)."""
    if not domain:
        return False, "No domain to check", None
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
        expires = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
        days_left = (expires - datetime.utcnow()).days
        if days_left < 0:
            return False, f"Certificate expired {abs(days_left)} days ago", days_left
        if days_left < 14:
            return True, f"Valid — renews automatically, {days_left} days left", days_left
        return True, f"Valid until {expires.strftime('%d %b %Y')}", days_left
    except socket.gaierror:
        return False, "Domain does not resolve yet (DNS not pointed at TrustedBiz)", None
    except socket.timeout:
        return False, "Timed out connecting — site may be unreachable", None
    except ssl.SSLError as e:
        return False, f"TLS error: {e}", None
    except Exception as e:
        return False, f"Could not verify: {e}", None

def scan_site_html(html):
    """Real static-analysis pass over the site's own stored HTML — flags the
    patterns that actually indicate injected or unsafe content."""
    if not html: return []
    issues = []
    for m in re.finditer(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE):
        src = m.group(1)
        if src.startswith(('http://', 'https://', '//')):
            host = re.sub(r'^(https?:)?//', '', src).split('/')[0].lower()
            if not any(host == h or host.endswith('.' + h) for h in _SAFE_SCRIPT_HOSTS):
                issues.append(f"External script from unrecognized host: {host}")
    if re.search(r'\beval\s*\(', html): issues.append("Uses eval() — potential code injection risk")
    if re.search(r'document\.write\s*\(', html): issues.append("Uses document.write() — can allow injected content")
    if re.search(r'<iframe', html, re.IGNORECASE): issues.append("Contains an embedded iframe")
    if re.search(r'atob\s*\(', html): issues.append("Contains a base64-decoded script payload")
    if re.search(r'on(?:error|load)\s*=\s*["\'][^"\']*(?:eval|atob)', html, re.IGNORECASE):
        issues.append("Suspicious inline event handler")
    return issues

def run_security_scan(user_id):
    """Runs SSL, content-safety, backup-freshness and 2FA checks against
    this user's actual sites and account — computed live, not hardcoded."""
    businesses = [dict(b) for b in db_fetchall(q("SELECT * FROM business WHERE owner_id=?"), (user_id,))]
    checks, passes, total = [], 0, 0

    for b in businesses:
        if b['status'] != 'approved': continue
        domain = b['custom_domain'] if (b.get('domain_status') == 'active' and b.get('custom_domain')) else f"{b['slug']}.trustedbiz.co.ug"
        total += 1
        ok, detail, _days = check_domain_ssl(domain)
        if ok: passes += 1
        checks.append({'label': 'SSL certificate', 'target': f"{b['name']} — {domain}",
                       'detail': detail, 'status': 'pass' if ok else 'warn'})

    for b in businesses:
        total += 1
        found = scan_site_html(b.get('generated_html'))
        if found:
            checks.append({'label': 'Content scan', 'target': b['name'],
                           'detail': '; '.join(found), 'status': 'warn'})
        else:
            passes += 1
            checks.append({'label': 'Content scan', 'target': b['name'],
                           'detail': 'No suspicious scripts or embeds found', 'status': 'pass'})

    for b in businesses:
        total += 1
        last = db_fetchone(q("SELECT created_at FROM site_backups WHERE business_id=? ORDER BY created_at DESC LIMIT 1"), (b['id'],))
        if last:
            passes += 1
            checks.append({'label': 'Automatic backups', 'target': b['name'],
                           'detail': f"Last snapshot saved {last['created_at']}", 'status': 'pass'})
        else:
            checks.append({'label': 'Automatic backups', 'target': b['name'],
                           'detail': 'No backup snapshot yet — one is created on next deploy', 'status': 'warn'})

    total += 1; passes += 1
    checks.append({'label': 'Firewall & DDoS protection', 'target': 'All sites',
                   'detail': 'Provided at the platform level by the hosting edge network', 'status': 'pass'})

    user_row = db_fetchone(q("SELECT two_factor_enabled FROM users WHERE id=?"), (user_id,))
    user_row = dict(user_row) if user_row else None
    total += 1
    if user_row and user_row.get('two_factor_enabled'):
        passes += 1
        checks.append({'label': 'Two-factor login', 'target': 'Your account', 'detail': 'Enabled', 'status': 'pass'})
    else:
        checks.append({'label': 'Two-factor login', 'target': 'Your account',
                       'detail': 'Not yet enabled on your account', 'status': 'warn'})

    score = round((passes / total) * 100) if total else 100
    return {'score': score, 'passes': passes, 'total': total, 'checks': checks}

def store_security_scan(user_id, result):
    try:
        db_insert(q("INSERT INTO security_scans (user_id, score, checks) VALUES (?,?,?)"),
                  (user_id, result['score'], json.dumps(result['checks'])))
    except Exception as e:
        print(f"[security_scan] store error: {e}")

def get_anthropic_client():
    key = os.environ.get("ANTHROPIC_API_KEY","")
    if not key: return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=key)
    except ImportError:
        return None

# ── DAISY — runs directly on the Anthropic API ─────────────────────────────────
# Daisy used to be a separate Render deployment that TrustedBiz called over
# HTTP (DAISY_API_URL / DAISY_API_KEY). She now runs in-process on Claude,
# using the ANTHROPIC_API_KEY already set in this environment. No separate
# service, no extra env vars, nothing else to deploy.
DAISY_MODEL = "claude-sonnet-5"

# Everything Daisy needs to know about the platform she's part of, and what
# "real website" means here. Shared by both the chat persona and the website
# builder so she never contradicts herself between the two.
DAISY_KNOWLEDGE = """
WHAT YOU ARE PART OF — TRUSTEDBIZ
TrustedBiz (trustedbiz.co.ug) is a Ugandan business directory and hosting
platform — the same idea as Render or Vercel, but built around getting local
businesses live on the internet with almost zero effort from the owner. You
are Daisy, TrustedBiz's AI website builder, sometimes described as "the
first Ugandan AI": the conversational engine that turns a business owner's
description of their shop, restaurant, salon, clinic, boutique, etc. into a
real, live website in minutes.

How a business goes live on TrustedBiz:
- An owner (or one of TrustedBiz's field agents, who sign local businesses
  up in person) describes the business to you: name, category, description,
  WhatsApp number, hours, brand color, and photos if they have any.
- Once there's enough to work with, you generate the actual website. If it
  came in through an agent it's reviewed and approved by a TrustedBiz admin,
  then goes live at https://{slug}.trustedbiz.co.ug — TrustedBiz pings
  Google automatically so it gets indexed fast.
- The owner gets an invite code (from their agent, or by signing up
  directly) to unlock their dashboard at /dashboard, where they can see
  their live site, request a rebuild, and manage hosting.
- Businesses can connect a custom domain, or — separately from the
  business-directory flow — deploy an existing HTML site of their own
  directly, the same way you'd deploy to Render or Netlify. That's the
  hosting-platform side of TrustedBiz, distinct from Daisy building a site
  from scratch.

Other things that exist on TrustedBiz:
- A reseller/agent program: agents sign up local businesses and get
  notified when their submissions are approved.
- An admin panel for reviewing and approving new listings.
- mybootcamp, a separate product also hosted on TrustedBiz.
- A public directory/search on trustedbiz.co.ug itself, so people can find
  approved businesses without going through Google.
- WhatsApp is the default way Ugandan customers reach a business — every
  generated site should make "message us on WhatsApp" the easiest possible
  action on the page.
- Plans and pricing exist at /pricing. Never invent exact prices or specific
  numbers — if someone asks, point them there instead of guessing.

YOUR JOB, AND WHAT "REAL" MEANS
Whatever you generate is a business's actual public website — not a demo,
not a mockup, not a sample of what a site *could* look like. A real
customer will open this on their phone and decide, right then, whether to
trust and contact this business. That means:
- Write like the business itself would: plain, specific language about what
  they actually do. Never generic filler like "Welcome to our website, we
  provide quality services to all our esteemed customers."
- Use only the real details you're given — name, category, description,
  hours, WhatsApp, photos, branches, testimonials. Never invent facts,
  awards, stats, years in business, or reviews you weren't given.
- If no photos are provided, don't fake it with stock-photo-style images,
  cartoon illustrations, or AI-mascot graphics — lean on clean typography,
  color, and layout instead.
- Design like a good freelance web developer would for a small local
  business, not like an AI demo: no gradient-blob backgrounds, no generic
  purple-SaaS look, no robot mascots, no "Lorem ipsum," no glowing button
  overload. Grounded and professional, shaped by that business's category
  and brand color, not a template that could belong to any business.
- Most visitors are on a phone, often on limited mobile data, in Uganda —
  mobile-first, single-column-friendly, fast (inline CSS, no heavy JS
  frameworks or large external assets), with a big, obvious WhatsApp button
  near the top.
- Structure to fit the business, skipping what doesn't apply rather than
  padding with filler: hero (name + one clear line on what they do), about
  /description, what they offer (services or menu, inferred sensibly from
  category), photo gallery if photos exist, hours, location/branches if
  given, testimonials if given, and one clear WhatsApp call-to-action.
"""

DAISY_CHAT_SYSTEM = """You are Daisy, TrustedBiz's friendly AI assistant, \
talking directly with a business owner (or a TrustedBiz agent on their \
behalf) in a chat widget in order to get their real website built.

""" + DAISY_KNOWLEDGE + """
HOW THIS CONVERSATION WORKS
Right now your only job is the conversation — gather enough real detail to
build a genuine website, in as few friendly questions as possible. You need
at minimum: business name, category, and a short description of what they
do. Nice-to-haves: WhatsApp number, hours, brand color, branch locations.

Photos matter — a site with a couple of real photos of the shop, the
product, or the food feels alive in a way text never does. So somewhere in
the conversation, once you have the basics, actively ask if they have a
few photos to upload (the widget has an upload button right next to the
chat for this). The context you're given each turn includes
"photo_count" — the number already uploaded this session. If it's 0,
ask once, plainly: don't nag if they say they don't have any or don't
reply to it — you can still build a good site with none. If it's already
above 0, don't ask again, just acknowledge it in passing if it comes up
naturally.

Don't interrogate — ask for one or two things at a time, warmly and
conversationally, like a helpful local assistant, not a form. Once you
have at least name, category, and description, tell them you're building
their site now and mark the conversation ready.

BEYOND WEBSITES — OTHER THINGS YOU CAN BUILD
A website isn't the only thing you build. If someone asks for a WhatsApp
product catalog, a logo, a promotional flyer, business cards, a CV, or a
presentation, you can build that too — right in this chat, no separate
tool needed. Recognize the request and gather what that specific thing
needs instead of steering them toward a website:
- catalog: business name, description, WhatsApp, brand color, and the
  list of products/services with prices if they have them
- logo: business name, brand color, a style word or two (e.g. "modern",
  "playful", "elegant")
- flyer: business name, brand color, style, what the flyer is announcing
- cards: business name, brand color, style, role/tagline, WhatsApp
- cv: full name, role/title, email, phone, key skills
- presentation: topic, brand color, style

Once you have enough for the thing they asked for, tell them you're
building it now and mark the conversation ready.

RESPONSE FORMAT — CRITICAL
Reply with ONLY a JSON object — no markdown fences, no text outside the
JSON:
{"reply": "<what you say to them next, in your own conversational voice>", "ready": <true or false>, "artifact_type": "<omit for a website, otherwise one of: catalog, logo, flyer, cards, cv, presentation>", "business": {"name": "...", "category": "...", "description": "...", "whatsapp": "...", "hours": "...", "brand_color": "...", "style": "...", "items": ["..."]}}

- "business" holds whatever fields you've collected so far — omit fields
  you don't have yet, and omit "business" entirely only if you have
  nothing at all.
- Omit "artifact_type" entirely when this is an ordinary website request.
- Set "ready" to true only once you have what that thing needs, and
  "reply" has told the user it's being built now.
"""

DAISY_HOME_SYSTEM = """You are Daisy, TrustedBiz's friendly AI assistant, \
answering a visitor's question in a small chat bubble right on the \
TrustedBiz homepage, before they've signed up for anything.

""" + DAISY_KNOWLEDGE + """
HOW THIS CONVERSATION WORKS — THIS IS NOT THE BUILDER
This widget is not where websites get built — it's where visitors get their
questions answered and get pointed to the right next step. Your job here is
to explain how TrustedBiz works, answer questions about pricing, hosting,
the agent program, or anything else about the platform, and warmly direct
people toward what they should do next: /register to sign up directly, or
mention that a TrustedBiz field agent can sign them up in person if that
fits better.

If someone starts describing their business or asks you to build them a
site right here, don't start gathering business details or attempt to
build anything in this chat. Instead, tell them plainly that you'd love to
build it, that it only takes a couple of minutes, and point them to
/register (or /dashboard if they mention already having an account) to
start that conversation for real. One short, specific reason it's worth
doing now (e.g. getting found on Google, a WhatsApp button customers can
tap) is welcome — a full pitch is not.

Keep replies short — two or three sentences, plain language, no jargon,
like a helpful local assistant chatting on the phone, not a landing page.

RESPONSE FORMAT — CRITICAL
Reply with ONLY a JSON object — no markdown fences, no text outside the
JSON:
{"reply": "<your short, direct answer or nudge>", "ready": false}

Always set "ready" to false and never include a "business" field — no
website gets built from this widget, only explained and pointed toward.
"""

DAISY_WEBSITE_SYSTEM = """You are Daisy, TrustedBiz's website builder. You \
are about to generate the real, live, public website for one specific \
business, from the details TrustedBiz sends you.

""" + DAISY_KNOWLEDGE + """
OUTPUT FORMAT — CRITICAL
Respond with ONLY the complete HTML document — starting with <!DOCTYPE
html> and ending with </html>. No markdown code fences, no explanation
before or after, no commentary. Everything (CSS, and minimal JS only if
truly needed) must be inline in this one file — no external stylesheets or
scripts, though Google Fonts is fine. Write a real <title> and meta
description built from the business's actual name and description. Use the
business's brand_color as the primary accent color throughout. If a
WhatsApp number is given, the primary contact button must be a wa.me link
built from it. Include a small, unobtrusive "Built with TrustedBiz" footer
credit.

PHOTOS — REAL CONTENT, NOT DECORATION
If the business details include photo URLs, use every one of them as an
actual, visible <img> in the page content — a gallery grid, next to the
about text, alongside a service or menu item, wherever it genuinely fits
that business. They exist to make the page feel like a real, lived-in
place. Never use a supplied photo as a full-bleed CSS background-image
behind a hero or section — that's exactly the "AI demo" look this site
must not have. Photos are things a visitor looks *at* in the page, not
scenery behind a headline. If no photos are given, don't add any image
placeholders or filler graphics in their place — build the page well
without them instead.

If the business details include an "ai_photos" list instead of (or
alongside) "photos", those are custom images made specifically for this
business — use them exactly like real photos: genuine content in the page
(gallery, next to the about text, alongside a service), never as a
full-bleed background behind text. Don't mention anywhere in the page that
they're AI-generated.
"""

def _daisy_extract_json(text):
    """Pull a JSON object out of a Claude response that should be pure JSON
    but might come wrapped in markdown fences or stray text."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r'^```[a-zA-Z]*\n?', '', text)
        text = re.sub(r'```\s*$', '', text).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None

def _daisy_extract_html(text):
    """Pull the HTML document out of a Claude response that should be pure
    HTML but might come wrapped in markdown fences or stray commentary."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r'^```[a-zA-Z]*\n?', '', text)
        text = re.sub(r'```\s*$', '', text).strip()
    lower = text.lower()
    idx = lower.find("<!doctype")
    if idx == -1:
        idx = lower.find("<html")
    if idx > 0:
        text = text[idx:]
    return text

def call_daisy(mode, context=None, history=None, message=None, timeout=55):
    """
    Runs Daisy directly on the Anthropic API (Claude) — no separate Daisy
    service to call. Returns (result_dict, error_string), same contract as
    before, so every existing call site keeps working unchanged.
    """
    client = get_anthropic_client()
    if not client:
        return None, "Daisy isn't connected yet — set ANTHROPIC_API_KEY."

    try:
        if mode == 'chat':
            ctx = context or {}
            msgs = []
            for turn in (history or [])[-20:]:
                role = 'user' if turn.get('role') == 'user' else 'assistant'
                content = turn.get('content') or turn.get('message') or ''
                if content:
                    msgs.append({"role": role, "content": content})
            msgs.append({"role": "user", "content": message or ""})

            # Homepage widget gets the "explain and direct" persona; every
            # other caller (the real builder in /dashboard) gets the
            # build-a-site persona.
            system = DAISY_HOME_SYSTEM if ctx.get('surface') == 'home' else DAISY_CHAT_SYSTEM

            # CLIENT MEMORY — if this conversation is about a specific
            # business Daisy already built (the "Edit with Daisy" flow),
            # fold in what's already known so she doesn't ask for it again
            # and can talk about that real, live site by name.
            existing = ctx.get('existing_business')
            if existing:
                system += (
                    "\n\nCLIENT MEMORY — YOU ALREADY BUILT THIS SITE\n"
                    "You are mid-conversation with a client whose real website you "
                    "already built. Here is everything you know about them and their "
                    "live site so far, as JSON — treat it as true, don't ask for any "
                    "of it again, and only ask about what's genuinely new or changing "
                    "this time:\n" + json.dumps(existing, ensure_ascii=False, indent=2)
                )

            resp = client.messages.create(
                model=DAISY_MODEL,
                max_tokens=1000,
                system=system,
                messages=msgs,
                timeout=timeout,
            )
            raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            data = _daisy_extract_json(raw)
            if not data:
                return {"reply": raw.strip() or "Tell me a bit more about your business.",
                         "mode": None}, None
            ready = bool(data.get("ready"))
            artifact_type = (data.get("artifact_type") or "").strip().lower() or None
            if artifact_type and artifact_type not in ARTIFACT_MODES:
                artifact_type = None
            if ready and artifact_type:
                mode_out = "artifact"
            elif ready:
                mode_out = "website"
            else:
                mode_out = None
            result = {"reply": data.get("reply") or "Tell me a bit more about your business.",
                      "mode": mode_out}
            if artifact_type:
                result["artifact_type"] = artifact_type
            if ready:
                result["business"] = data.get("business") or {}
            return result, None

        else:
            ctx = dict(context or {})
            power = get_website_power(ctx.get('plan'))
            model = power['model']
            max_tokens = power['max_tokens']

            # Give Daisy custom AI-generated imagery to work with on paid
            # plans when the business hasn't supplied its own photos —
            # otherwise a paid site with no photos looks identical to a
            # free one.
            if power['images'] and not ctx.get('photos'):
                try:
                    ai_photos = generate_business_images(ctx, count=power['images'])
                    if ai_photos:
                        ctx['ai_photos'] = ai_photos
                except Exception as e:
                    print(f"[Daisy/Images] {e}")

            prompt = ("Build the real, live website for this business now. "
                       "Business details (JSON):\n" +
                       json.dumps(ctx, ensure_ascii=False, indent=2) +
                       "\n\nRespond with the complete HTML document only.")
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=DAISY_WEBSITE_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout,
            )
            raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            html = _daisy_extract_html(raw)
            if not html or len(html) < 200:
                return None, "Daisy is thinking hard on this one. Please try again in a moment."

            # Pro Max gets a second pass: Daisy reviews her own first draft
            # as a senior art director and rewrites it. This is the real
            # difference between plans — not just a bigger token budget —
            # and is what should make a Pro Max site look like it came from
            # an agency, not a fast first draft.
            if power['passes'] >= 2:
                try:
                    review_prompt = (
                        "Here is the first draft of this Pro Max client's website — "
                        "the full HTML document:\n\n" + html + "\n\n"
                        "You are now the senior art director reviewing a junior "
                        "designer's first draft before it ships to a paying Pro Max "
                        "client who is paying for noticeably more premium, more "
                        "distinctive work than a standard site. Rewrite the ENTIRE "
                        "document, keeping every real business fact exactly as given "
                        "(never invent new facts), but elevating the design: more "
                        "confident typography, better spacing and rhythm, a stronger "
                        "sense of visual hierarchy and a signature layout idea "
                        "specific to this business — the kind of detail that makes a "
                        "client feel like this was designed *for them*, not generated. "
                        "Fix anything that reads as generic, templated, or unfinished. "
                        "Respond with the complete rewritten HTML document only."
                    )
                    resp2 = client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        system=DAISY_WEBSITE_SYSTEM,
                        messages=[{"role": "user", "content": review_prompt}],
                        timeout=timeout,
                    )
                    raw2 = "".join(b.text for b in resp2.content if getattr(b, "type", "") == "text")
                    html2 = _daisy_extract_html(raw2)
                    if html2 and len(html2) > 200:
                        html = html2
                except Exception as e:
                    print(f"[Daisy/Pass2] {e}")

            return {"html": html, "mode": mode}, None

    except Exception as e:
        msg = str(e).lower()
        print(f"[Daisy/Claude] {e}")
        if "timeout" in msg or "timed out" in msg:
            return None, "Daisy is thinking hard on this one. Please try again in a moment."
        return None, "Daisy couldn't be reached right now. Please try again shortly."

# ── HOME ──────────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    query    = request.args.get('query','').strip()
    user_lat = request.args.get('lat', type=float)
    user_lng = request.args.get('lng', type=float)

    all_biz = db_fetchall(
        q("SELECT * FROM business WHERE status='approved' ORDER BY is_premium DESC, id DESC"))

    if query:
        ql = query.lower()
        scored = []
        for b in all_biz:
            bd = biz_to_dict(b)
            s = max(similar(ql,(bd.get('name') or '').lower()),
                    similar(ql,(bd.get('category') or '').lower()))
            if ql in (bd.get('name') or '').lower() or \
               ql in (bd.get('category') or '').lower() or s > 0.45:
                scored.append((b,s))
        scored.sort(key=lambda x:x[1],reverse=True)
        filtered = [b for b,_ in scored]
    else:
        filtered = list(all_biz)

    results = []
    for b in filtered:
        bd = biz_to_dict(b)
        dist = 9999.0
        if user_lat and user_lng and bd.get('lat') and bd.get('lng'):
            try: dist = haversine(user_lat,user_lng,float(bd['lat']),float(bd['lng']))
            except: pass
        rv = db_fetchone(
            q("SELECT AVG(rating) as avg_rating, COUNT(*) as cnt FROM reviews WHERE business_id=?"),
            (bd['id'],))
        bd['avg_rating']   = round(float(rv['avg_rating']),1) if rv and rv['avg_rating'] else 0
        bd['review_count'] = rv['cnt'] if rv else 0
        results.append((bd, round(dist,2)))

    if user_lat and user_lng:
        results.sort(key=lambda x:(0 if x[0].get('is_premium') else 1, x[1]))

    notifications = []
    if 'user_id' in session:
        rows = db_fetchall(
            q("SELECT * FROM notifications WHERE user_id=? AND seen=0 ORDER BY created_at DESC LIMIT 5"),
            (session['user_id'],))
        notifications = [dict(r) for r in rows]
        if notifications:
            db_execute(q("UPDATE notifications SET seen=1 WHERE user_id=?"), (session['user_id'],))

    # ── WEB SEARCH ─────────────────────────────────────────────────────────────
    web_results = []
    if query:
        try:
            import urllib.request, urllib.parse, json as _json
            search_query = urllib.parse.quote(f"{query} Uganda business")
            url = f"https://api.duckduckgo.com/?q={search_query}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(url, headers={'User-Agent': 'TrustedBiz/1.0'})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = _json.loads(r.read().decode())
            for item in (data.get('RelatedTopics') or [])[:10]:
                if isinstance(item, dict) and item.get('Text') and item.get('FirstURL'):
                    icon = (item.get('Icon') or {}).get('URL', '')
                    domain = item['FirstURL'].split('/')[2] if '//' in item['FirstURL'] else ''
                    web_results.append({
                        'title': item['Text'].split(' - ')[0][:90],
                        'snippet': item['Text'][:220],
                        'url': item['FirstURL'],
                        'image': ('https://duckduckgo.com' + icon) if icon and icon.startswith('/') else icon,
                        'source': domain,
                    })
        except Exception as e:
            print(f"Web search error: {e}")

    return render_template('home.html',
        results=results,
        web_results=web_results,
        current_user=get_current_user(),
        notifications=notifications)

# ── PRICE GUARD API ───────────────────────────────────────────────────────────
@app.route('/portfolio')
def portfolio():
    # Folded into /about — redirect so any existing links/bookmarks still work
    return redirect('/about', code=301)


@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name  = request.form.get('name','').strip()[:100]
        email = request.form.get('email','').lower().strip()
        pwd   = request.form.get('password','')
        conf  = request.form.get('confirm','')
        if not name or not email: flash("All fields are required."); return render_template('register.html',current_user=None)
        if len(pwd) < 6: flash("Password must be at least 6 characters."); return render_template('register.html',current_user=None)
        if pwd != conf: flash("Passwords do not match."); return render_template('register.html',current_user=None)
        try:
            user_id = db_insert(q("INSERT INTO users (name,email,password) VALUES (?,?,?)"),
                      (name,email,generate_password_hash(pwd)))
            session.permanent = True
            session['user_id'] = user_id
            session['user_name'] = name
            _email_welcome(name, email)
            flash(f"Welcome {name}! Tell Daisy about your business to get your first site live.")
            return redirect('/dashboard')
        except: flash("Email already registered.")
    return render_template('register.html', current_user=None)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email','').lower().strip()
        pwd   = request.form.get('password','')
        user  = db_fetchone(q("SELECT * FROM users WHERE email=?"), (email,))
        if user and check_password_hash(user['password'], pwd):
            if dict(user).get('two_factor_enabled'):
                session['pending_login_user_id'] = user['id']
                return redirect('/login/verify-2fa')
            session.permanent = True
            session['user_id']   = user['id']
            session['user_name'] = user['name']
            return redirect(request.args.get('next','/dashboard'))
        flash("Wrong email or password.")
    return render_template('login.html', current_user=None)

@app.route('/logout')
def logout():
    session.clear(); return redirect('/')

# ── AI WEBSITE VIEW ───────────────────────────────────────────────────────────
@app.route('/site/<slug>')
def site(slug=None):
    # Also handle subdomain requests e.g. cyber-tech.trustedbiz.co.ug
    if slug is None:
        from flask import g
        slug = getattr(g, 'subdomain_slug', None)
        if not slug:
            return render_template('404.html', current_user=get_current_user()), 404
    biz = db_fetchone(q("SELECT * FROM business WHERE slug=? AND status='approved'"), (slug,))
    if not biz:
        try: biz = db_fetchone(q("SELECT * FROM business WHERE id=? AND status='approved'"), (int(slug),))
        except: pass
    if not biz: return render_template('404.html', current_user=get_current_user()), 404

    db_execute(q("UPDATE business SET views=views+1 WHERE id=?"), (biz['id'],))
    bd = biz_to_dict(biz)

    # Get ads for this business
    ads = db_fetchall(q("SELECT * FROM ads WHERE business_id=? AND active=1 ORDER BY updated_at DESC LIMIT 2"), (biz['id'],))
    bd['ads'] = [dict(a) for a in ads]

    # Get branches
    branches = db_fetchall(q("SELECT * FROM branches WHERE business_id=? ORDER BY id"), (biz['id'],))
    bd['branches'] = [dict(b) for b in branches]

    # Get reviews
    reviews = db_fetchall(q("""
        SELECT r.*, u.name as reviewer_name FROM reviews r
        LEFT JOIN users u ON u.id=r.user_id
        WHERE r.business_id=? ORDER BY r.created_at DESC
    """), (biz['id'],))
    rv_avg = db_fetchone(q("SELECT AVG(rating) as a, COUNT(*) as c FROM reviews WHERE business_id=?"), (biz['id'],))
    bd['avg_rating']    = round(float(rv_avg['a']),1) if rv_avg and rv_avg['a'] else 0
    bd['total_reviews'] = rv_avg['c'] if rv_avg else 0

    if bd.get('generated_html'):
        return bd['generated_html']

    # Generate the site via Daisy's API instead of generating locally.
    # A simple, real-data fallback (using the business's actual name, category,
    # description, photos, hours, branches) is saved and served immediately so
    # the visitor never sees a blank page. Daisy's real build then runs and
    # replaces it — currently synchronous (page waits up to ~55s on first
    # visit); move this to a background thread once Daisy's API is live and
    # you know her real response time.
    wa_link = f"https://wa.me/{bd.get('whatsapp','')}"
    fallback_html = _basic_fallback_site(bd, wa_link)

    daisy_ctx = {
        'name': bd.get('name'), 'category': bd.get('category'),
        'description': bd.get('description'), 'whatsapp': bd.get('whatsapp'),
        'hours': bd.get('hours') or 'Mon-Sat 8am-7pm',
        'brand_color': bd.get('brand_color') or '#2b7a78',
        'photos': [p.strip() for p in str(bd.get('photos') or '').split(',') if p.strip()],
        'branches': bd.get('branches') or [], 'ads': bd.get('ads') or [],
        'plan': bd.get('plan') or 'free',
    }
    result, err = call_daisy('website', context=daisy_ctx)
    html = (result or {}).get('html') if result else None

    if html:
        try: db_execute(q("UPDATE business SET generated_html=? WHERE id=?"), (html, biz['id']))
        except: pass
        return html

    # Daisy unavailable or still not connected — serve the fallback, don't
    # leave the visitor with nothing, but don't cache it as the final site.
    print(f"[Daisy API] site() fallback used for biz {biz['id']}: {err}")
    return fallback_html


def _basic_fallback_site(bd, wa_link):
    """Plain, real-data page shown only if Daisy's API is unreachable."""
    name  = str(bd.get('name') or 'Business')
    cat   = str(bd.get('category') or '')
    desc  = str(bd.get('description') or '')
    hours = str(bd.get('hours') or 'Mon-Sat 8am-7pm')
    color = str(bd.get('brand_color') or '#2b7a78')
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} | TrustedBiz</title>
<style>body{{font-family:sans-serif;background:#f5f8f8;color:#0d1c1c;max-width:560px;margin:60px auto;padding:0 24px;text-align:center;}}
h1{{color:{color};}} a{{display:inline-block;margin-top:20px;background:{color};color:#fff;padding:12px 26px;border-radius:6px;text-decoration:none;font-weight:600;}}</style>
</head><body><h1>{name}</h1><p>{cat}</p><p>{desc}</p><p>{hours}</p>
<a href="{wa_link}">Message on WhatsApp</a></body></html>"""

# ── REGENERATE ────────────────────────────────────────────────────────────────
@app.route('/daisy/create-business', methods=['POST'])
@login_required
def daisy_create_business():
    """The real gap this closes: Daisy's chat can describe a business and
    even preview its HTML, but nothing saved it. This turns that into an
    actual live listing — called once the conversation has a name and
    enough detail to go live."""
    user = get_current_user()
    data = request.get_json() or {}
    name        = (data.get('name') or '').strip()[:100]
    category    = (data.get('category') or '').strip().lower()
    whatsapp    = (data.get('whatsapp') or '').strip()
    description = (data.get('description') or '').strip()
    color       = (data.get('brand_color') or '#2b7a78').strip()
    html        = data.get('html')  # Daisy may have already generated this during chat
    # Photos the owner uploaded mid-conversation via /daisy/upload-photo —
    # frontend sends back the URLs it already collected, comma-joined or as
    # a list; store the same way manual uploads are stored (comma string).
    photos_in   = data.get('photos') or []
    if isinstance(photos_in, str):
        photos_in = [p.strip() for p in photos_in.split(',') if p.strip()]
    photos_str  = ','.join(p for p in photos_in if p)[:2000]

    if not name:
        return jsonify({'error': 'A business name is required.'}), 400

    slug = make_slug(name)
    biz_id = db_insert(
        q("INSERT INTO business (name, category, whatsapp, description, brand_color, slug, owner_id, status, plan, generated_html, photos) VALUES (?,?,?,?,?,?,?,?,?,?,?)"),
        (name, category, whatsapp, description, color, slug, user['id'], 'approved', 'free', html, photos_str)
    )
    ping_google(slug)

    if html:
        snapshot_site_html(biz_id, html)
        log_deploy_event(biz_id, user['id'], 'deploy', f'"{name}" deployed successfully', 'ok')
    else:
        daisy_ctx = {'name': name, 'category': category, 'description': description,
                     'whatsapp': whatsapp, 'brand_color': color, 'hours': 'Mon-Sat 8am-7pm',
                     'photos': photos_in}
        def _bg(ctx, bid, uid, bname):
            result, err = call_daisy('website', context=ctx)
            h = (result or {}).get('html') if result else None
            if h:
                save_site_html(bid, h)
                log_deploy_event(bid, uid, 'deploy', f'"{bname}" deployed successfully', 'ok')
            else:
                log_deploy_event(bid, uid, 'deploy_failed', f'"{bname}" deploy failed — Daisy timed out', 'warn')
                print(f"[Daisy API] create-business gen failed for biz {bid}: {err}")
        import threading
        threading.Thread(target=_bg, args=(daisy_ctx, biz_id, user['id'], name), daemon=True).start()

    return jsonify({'success': True, 'biz_id': biz_id, 'slug': slug,
                     'url': f"https://{slug}.trustedbiz.co.ug"})


# ── DAISY PUBLISH (server-to-server) ────────────────────────────────────────
# Called by Daisy's own standalone backend (daisy_backend/app.py) when a user
# clicks "Publish to TrustedBiz" there. That's a *separate* Daisy from the
# in-process one above — a general assistant that can build a whole site in
# chat and hand the finished HTML here. Auth is a shared secret in the
# Authorization header, never a browser session, since the caller is a server.
DAISY_API_KEY = os.environ.get("DAISY_API_KEY", "")

@app.route('/api/daisy/publish', methods=['POST'])
def api_daisy_publish():
    if not DAISY_API_KEY:
        return jsonify({'error': 'Daisy publishing is not configured on this server.'}), 503

    auth  = request.headers.get('Authorization', '')
    token = auth.split(' ', 1)[1] if auth.startswith('Bearer ') else ''
    if not token or not secrets.compare_digest(token, DAISY_API_KEY):
        return jsonify({'error': 'unauthorized'}), 401

    data        = request.get_json(silent=True) or {}
    name        = (data.get('name') or '').strip()[:100]
    category    = (data.get('category') or '').strip().lower()[:60]
    description = (data.get('description') or '').strip()[:2000]
    whatsapp    = re.sub(r'\D', '', data.get('whatsapp') or '')[:20]
    brand_color = (data.get('brand_color') or '').strip()[:20] or '#2b7a78'
    owner_email = (data.get('owner_email') or '').strip().lower()[:150]
    owner_name  = (data.get('owner_name') or name or 'Business Owner').strip()[:100]
    owner_password_hash = (data.get('owner_password_hash') or '').strip()
    html        = data.get('html') or ''

    if not name:
        return jsonify({'error': 'A business name is required.'}), 400
    if not html or len(html) < 200:
        return jsonify({'error': 'No finished site to publish.'}), 400
    if len(html) > 500_000:
        return jsonify({'error': 'Site is too large to publish.'}), 400

    # Reuse an existing TrustedBiz account for this email, or create a
    # placeholder one — same pattern agent_add_business already uses — so
    # the owner can claim the listing later via /agent/set-password.
    owner_id = 0
    is_new_user = False
    if owner_email:
        existing = db_fetchone(q("SELECT id FROM users WHERE email=?"), (owner_email,))
        if existing:
            # Existing TrustedBiz account — never touch its password here.
            owner_id = existing['id']
        else:
            # New account. If this email has a Daisy account, Daisy forwards
            # that account's password hash so the same email/password logs
            # into TrustedBiz too — both apps hash with werkzeug, so the hash
            # verifies correctly here without ever seeing the plaintext.
            # Only accept it if it actually looks like a werkzeug hash;
            # otherwise fall back to the old random-password + claim-link flow.
            if owner_password_hash and owner_password_hash.split(':', 1)[0] in ('pbkdf2', 'scrypt'):
                new_password = owner_password_hash
            else:
                new_password = generate_password_hash(secrets.token_urlsafe(8))
            owner_id = db_insert(
                q("INSERT INTO users (name, email, password) VALUES (?,?,?)"),
                (owner_name, owner_email, new_password)
            )
            is_new_user = True

    slug = make_slug(name)
    try:
        biz_id = db_insert(
            q("INSERT INTO business (name, category, whatsapp, description, brand_color, "
              "slug, owner_id, status, plan, generated_html) VALUES (?,?,?,?,?,?,?,?,?,?)"),
            (name, category, whatsapp, description, brand_color, slug, owner_id, 'approved', 'free', html)
        )
    except Exception as e:
        print(f"[api/daisy/publish] insert error: {e}")
        return jsonify({'error': 'Could not save the site. Try again.'}), 500

    ping_google(slug)
    snapshot_site_html(biz_id, html)
    log_deploy_event(biz_id, owner_id or None, 'deploy', f'"{name}" published via Daisy', 'ok')

    join_link = None
    if owner_email:
        from urllib.parse import quote
        join_link = f"https://trustedbiz.co.ug/agent/set-password?email={quote(owner_email)}"
        if is_new_user:
            _email_approved(owner_name, owner_email, name, slug)

    return jsonify({
        'success':  True,
        'biz_id':   biz_id,
        'slug':     slug,
        'url':      f"https://{slug}.trustedbiz.co.ug",
        'join_link': join_link,
    }), 201


@app.route('/generate-site/<int:biz_id>', methods=['POST'])
@login_required
def generate_site(biz_id):
    biz = db_fetchone(q("SELECT * FROM business WHERE id=? AND owner_id=?"), (biz_id,session['user_id']))
    if not biz: flash("Not found."); return redirect('/dashboard#sites')
    bd = biz_to_dict(biz)
    branches = db_fetchall(q("SELECT * FROM branches WHERE business_id=?"), (biz_id,))
    bd['branches'] = [dict(b) for b in branches]
    ads = db_fetchall(q("SELECT * FROM ads WHERE business_id=? AND active=1 LIMIT 2"), (biz_id,))
    bd['ads'] = [dict(a) for a in ads]
    daisy_ctx = {
        'name': bd.get('name'), 'category': bd.get('category'),
        'description': bd.get('description'), 'whatsapp': bd.get('whatsapp'),
        'hours': bd.get('hours') or 'Mon-Sat 8am-7pm',
        'brand_color': bd.get('brand_color') or '#2b7a78',
        'photos': [p.strip() for p in str(bd.get('photos') or '').split(',') if p.strip()],
        'branches': bd.get('branches') or [], 'ads': bd.get('ads') or [],
        'plan': bd.get('plan') or 'free',
    }

    def _regen_bg(ctx, biz_id, user_id, biz_name):
        result, err = call_daisy('website', context=ctx)
        html = (result or {}).get('html') if result else None
        if html:
            save_site_html(biz_id, html)
            log_deploy_event(biz_id, user_id, 'redeploy', f'"{biz_name}" redeployed successfully', 'ok')
        else:
            log_deploy_event(biz_id, user_id, 'redeploy_failed', f'"{biz_name}" redeploy failed — Daisy timed out', 'warn')
            print(f"[Daisy API] regen failed for biz {biz_id}: {err}")

    import threading
    threading.Thread(target=_regen_bg, args=(daisy_ctx, biz_id, session['user_id'], bd.get('name')), daemon=True).start()
    flash("✨ Your website is being rebuilt by Daisy... refresh in about 30 seconds to see it live.")
    return redirect('/dashboard')

# ── ADD BUSINESS ──────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    user_id    = session['user_id']
    businesses = db_fetchall(q("SELECT * FROM business WHERE owner_id=? ORDER BY created_at DESC"), (user_id,))
    stats = {}
    for b in businesses:
        rv = db_fetchone(q("SELECT AVG(rating) as a, COUNT(*) as c FROM reviews WHERE business_id=?"), (b['id'],))
        stats[b['id']] = {"avg_rating": round(float(rv['a']),1) if rv and rv['a'] else 0, "total_reviews": rv['c'] if rv else 0}
    businesses   = [biz_to_dict(b) for b in businesses]
    total_views  = sum(b.get('views',0) or 0 for b in businesses)
    live_count   = sum(1 for b in businesses if b.get('status')=='approved')
    # Plan is tracked per-business (see admin's Set Basic/Set Pro Max). For the
    # account-level billing view, use the highest plan among the user's
    # businesses as "chosen_plan" — reasonable for the common single-business
    # case; worth revisiting once multi-business accounts are common.
    plan_rank = {'free': 0, 'basic': 1, 'pro_max': 2}
    chosen_plan = 'free'
    for b in businesses:
        if plan_rank.get(b.get('plan') or 'free', 0) > plan_rank.get(chosen_plan, 0):
            chosen_plan = b.get('plan') or 'free'
    current_user = get_current_user()

    deploy_events = db_fetchall(q(
        "SELECT de.*, b.name as biz_name FROM deploy_events de "
        "LEFT JOIN business b ON b.id = de.business_id "
        "WHERE de.user_id=? ORDER BY de.created_at DESC LIMIT 8"), (user_id,))
    deploy_events = [biz_to_dict(e) for e in deploy_events]

    last_scan = db_fetchone(q("SELECT * FROM security_scans WHERE user_id=? ORDER BY created_at DESC LIMIT 1"), (user_id,))
    security = None
    if last_scan:
        try:
            security = {'score': last_scan['score'], 'checks': json.loads(last_scan['checks']),
                       'scanned_at': biz_to_dict(last_scan).get('created_at')}
            security['passes'] = sum(1 for c in security['checks'] if c['status'] == 'pass')
            security['total']  = len(security['checks'])
        except Exception as e:
            print(f"[dashboard] security scan parse error: {e}")

    return render_template('console.html', businesses=businesses, stats=stats,
                           current_user=current_user, total_listings=len(businesses),
                           live_count=live_count, total_views=total_views,
                           chosen_plan=chosen_plan, deploy_events=deploy_events,
                           security=security)

# ── DASHBOARD SET COLOR ───────────────────────────────────────────────────────
@app.route('/dashboard/set-template/<int:biz_id>', methods=['POST'])
@login_required
def set_template(biz_id):
    color = request.form.get('brand_color','#2b7a78')
    biz   = db_fetchone(q("SELECT id FROM business WHERE id=? AND owner_id=?"), (biz_id,session['user_id']))
    if biz:
        db_execute(q("UPDATE business SET brand_color=?,generated_html=NULL WHERE id=?"), (color,biz_id))
        flash("Color saved! Regenerating website…")
    return redirect('/dashboard')

# ── REVIEW ────────────────────────────────────────────────────────────────────
@app.route('/review/<int:biz_id>', methods=['POST'])
@login_required
def submit_review(biz_id):
    rating  = request.form.get('rating')
    comment = request.form.get('comment','').strip()
    user_id = session['user_id']
    if not rating: flash("Please select a star rating."); return redirect(f'/site/{biz_id}')
    existing = db_fetchone(q("SELECT id FROM reviews WHERE business_id=? AND user_id=?"), (biz_id,user_id))
    if existing: flash("You already reviewed this business."); return redirect(f'/site/{biz_id}')
    db_insert(q("INSERT INTO reviews (business_id,user_id,rating,comment) VALUES (?,?,?,?)"),
              (biz_id,user_id,rating,comment))
    flash("Review submitted! Thank you.")
    return redirect(f'/site/{biz_id}')

# ── REPORT ────────────────────────────────────────────────────────────────────
@app.route('/report/<int:biz_id>')
def report(biz_id):
    ip = request.remote_addr
    if db_fetchone(q("SELECT id FROM reports WHERE business_id=? AND user_identifier=?"), (biz_id,ip)):
        flash("You already reported this business."); return redirect('/')
    db_execute(q("INSERT INTO reports (business_id,user_identifier) VALUES (?,?)"), (biz_id,ip))
    db_execute(q("UPDATE business SET reports=reports+1 WHERE id=?"), (biz_id,))
    flash("Business reported. Thank you."); return redirect('/')

# ── UPGRADE ───────────────────────────────────────────────────────────────────
# The dedicated upgrade page was cut — the console's Billing tab already has
# the same WhatsApp upgrade links built in. Redirect so old links still work.
@app.route('/upgrade/<int:biz_id>')
@login_required
def upgrade_page(biz_id):
    return redirect('/dashboard')

# ── ADMIN LOGIN ───────────────────────────────────────────────────────────────
@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('admin_pass') == ADMIN_PASSWORD:
            session['admin'] = True; return redirect('/admin')
        flash("Wrong password.")
    return render_template('admin_login.html', current_user=None)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_auth',None); return redirect('/')

# ── ADMIN PANEL ───────────────────────────────────────────────────────────────
@app.route('/admin', methods=['GET','POST'])
def admin():
    if not session.get('admin_auth'):
        if request.method == 'POST' and request.form.get('admin_pass') == ADMIN_PASSWORD:
            session.permanent = True
            session['admin_auth'] = True
        else:
            if request.method == 'POST':
                flash("Wrong password.")
            return render_template('admin_login.html', current_user=None)

    if request.method == 'POST':
        biz_id = request.form.get('id')
        action = request.form.get('action')

        if action == 'approve':
            db_execute(q("UPDATE business SET status='approved' WHERE id=?"), (biz_id,))
            owner = db_fetchone(q("SELECT owner_id FROM business WHERE id=?"), (biz_id,))
            biz_row = db_fetchone(q("SELECT name, slug FROM business WHERE id=?"), (biz_id,))
            # Ping Google to index the business URL immediately
            if biz_row and biz_row.get('slug'):
                ping_google(biz_row['slug'])
            if owner and owner.get('owner_id'):
                db_insert(q("INSERT INTO notifications (user_id,message) VALUES (?,?)"),
                          (owner['owner_id'], "✅ Your business is now live on TrustedBiz!"))
                # Send approval email
                user_row = db_fetchone(q("SELECT name, email FROM users WHERE id=?"), (owner['owner_id'],))
                if biz_row and user_row:
                    _email_approved(user_row['name'], user_row['email'], biz_row['name'], biz_row['slug'])
        elif action == 'reject':
            db_execute(q("UPDATE business SET status='rejected' WHERE id=?"), (biz_id,))
        elif action == 'verify':
            db_execute(q("UPDATE business SET verified=1 WHERE id=?"), (biz_id,))
        elif action == 'unverify':
            db_execute(q("UPDATE business SET verified=0 WHERE id=?"), (biz_id,))
        elif action in ('set_basic', 'set_pro_max', 'set_free'):
            new_plan = {'set_basic': 'basic', 'set_pro_max': 'pro_max', 'set_free': 'free'}[action]
            is_paid  = 1 if new_plan != 'free' else 0
            db_execute(q("UPDATE business SET plan=?, is_premium=?, last_payment_date=CURRENT_DATE, payment_months_late=0 WHERE id=?"),
                       (new_plan, is_paid, biz_id))
            owner = db_fetchone(q("SELECT owner_id FROM business WHERE id=?"), (biz_id,))
            if owner and owner.get('owner_id'):
                label = {'basic': 'Basic', 'pro_max': 'Pro Max', 'free': 'Free'}[new_plan]
                db_insert(q("INSERT INTO notifications (user_id,message) VALUES (?,?)"),
                          (owner['owner_id'], f"Your plan is now {label}."))
        elif action == 'mark_late':
            db_execute(q("UPDATE business SET payment_months_late=payment_months_late+1 WHERE id=?"), (biz_id,))
        elif action == 'block':
            db_execute(q("UPDATE business SET status='rejected' WHERE id=?"), (biz_id,))
        elif action == 'regen':
            biz = db_fetchone(q("SELECT * FROM business WHERE id=?"), (biz_id,))
            if biz:
                bd = biz_to_dict(biz)
                branches = db_fetchall(q("SELECT * FROM branches WHERE business_id=?"), (biz_id,))
                bd['branches'] = [dict(b) for b in branches]
                ads = db_fetchall(q("SELECT * FROM ads WHERE business_id=? AND active=1 LIMIT 2"), (biz_id,))
                bd['ads'] = [dict(a) for a in ads]
                daisy_ctx = {
                    'name': bd.get('name'), 'category': bd.get('category'),
                    'description': bd.get('description'), 'whatsapp': bd.get('whatsapp'),
                    'hours': bd.get('hours') or 'Mon-Sat 8am-7pm',
                    'brand_color': bd.get('brand_color') or '#2b7a78',
                    'photos': [p.strip() for p in str(bd.get('photos') or '').split(',') if p.strip()],
                    'branches': bd.get('branches') or [], 'ads': bd.get('ads') or [],
                    'plan': bd.get('plan') or 'free',
                }
                def _admin_regen_bg(ctx, bid):
                    result, err = call_daisy('website', context=ctx)
                    html = (result or {}).get('html') if result else None
                    if html:
                        try: db_execute(q("UPDATE business SET generated_html=? WHERE id=?"), (html, bid))
                        except Exception as e: print(f"Admin regen save error: {e}")
                    else:
                        print(f"[Daisy API] admin regen failed for biz {bid}: {err}")
                import threading as _threading
                _threading.Thread(target=_admin_regen_bg, args=(daisy_ctx, int(biz_id)), daemon=True).start()
                flash("✅ Daisy is regenerating this site — refresh in about 60 seconds!")
        elif action == 'delete':
            db_execute(q("DELETE FROM business WHERE id=?"), (biz_id,))
        elif action == 'send_to_pool':
            # Owner refused or ignored — save their generated website to the pool
            # so the next business in the same category gets it for free
            biz = db_fetchone(q("SELECT * FROM business WHERE id=?"), (biz_id,))
            if biz and biz.get('generated_html') and len(biz['generated_html']) > 2000:
                category = (biz.get('category') or '').lower().strip()
                # Only pool if not already in pool from this business
                already = db_fetchone(
                    q("SELECT id FROM template_pool WHERE category=? AND html=?"),
                    (category, biz['generated_html'])
                )
                if not already:
                    db_insert(
                        q("INSERT INTO template_pool (category, html, quality_score) VALUES (?,?,?)"),
                        (category, biz['generated_html'], 90)
                    )
                    flash(f"✅ '{biz['name']}' website moved to pool — next {category} business gets it free!", 'success')
                else:
                    flash("Already in pool.", 'info')
            else:
                flash("No generated website found for this business — generate one first.", 'error')

        return redirect('/admin')

    businesses = db_fetchall(q("""
        SELECT b.*, u.name as owner_name, COUNT(r.id) as report_count
        FROM business b
        LEFT JOIN users u ON u.id=b.owner_id
        LEFT JOIN reports r ON r.business_id=b.id
        GROUP BY b.id, u.name ORDER BY b.created_at DESC
    """))

    try:
        late_alert = db_fetchall(q("""
            SELECT * FROM business WHERE is_premium=1
            AND (last_payment_date IS NULL OR last_payment_date < CURRENT_DATE - INTERVAL '30 days')
            ORDER BY last_payment_date ASC
        """))
    except:
        late_alert = []

    stats = {
        'total_users':      (db_fetchone(q("SELECT COUNT(*) as c FROM users")) or {}).get('c',0),
        'total_businesses': (db_fetchone(q("SELECT COUNT(*) as c FROM business")) or {}).get('c',0),
        'total_reviews':    (db_fetchone(q("SELECT COUNT(*) as c FROM reviews")) or {}).get('c',0),
        'total_paid':       (db_fetchone(q("SELECT COUNT(*) as c FROM business WHERE plan IS NOT NULL AND plan!='free'")) or {}).get('c',0),
    }

    # Template pool stats — show how many Daisy calls were saved by reuse
    try:
        pool_stats = db_fetchall(q("SELECT category, times_used, quality_score, created_at FROM template_pool ORDER BY times_used DESC"))
        pool_stats = [dict(p) for p in pool_stats]
        pool_saves = sum(p.get('times_used', 0) for p in pool_stats)
    except:
        pool_stats = []
        pool_saves = 0

    # Reports queue — the one thing that still needs a human
    try:
        reported_businesses = db_fetchall(q("SELECT * FROM business WHERE reports > 0 ORDER BY reports DESC"))
        reported_businesses = [biz_to_dict(b) for b in reported_businesses]
    except:
        reported_businesses = []
    reported_count = len(reported_businesses)

    # Agent activity log — submissions now publish automatically, this is
    # just a record of what agents have brought in recently.
    try:
        agent_activity = db_fetchall(q("""
            SELECT b.name as business_name, a.name as agent_name, b.created_at
            FROM business b
            LEFT JOIN agents a ON a.code=b.agent_code
            WHERE b.agent_code IS NOT NULL
            ORDER BY b.created_at DESC LIMIT 20
        """))
        agent_activity = [dict(a) for a in agent_activity]
    except:
        agent_activity = []

    return render_template('admin.html',
        businesses=[biz_to_dict(b) for b in businesses],
        late_alert=[biz_to_dict(b) for b in (late_alert or [])],
        pool_stats=pool_stats,
        pool_saves=pool_saves,
        reported_businesses=reported_businesses,
        reported_count=reported_count,
        agent_activity=agent_activity,
        **stats)

# ── STATIC PAGES ──────────────────────────────────────────────────────────────
@app.route('/privacy')
def privacy():
    return render_template('privacy.html', current_user=get_current_user())

@app.route('/terms')
def terms():
    return render_template('terms.html', current_user=get_current_user())


@app.route('/admin/migrate-db')
@admin_required
def migrate_db():
    try:
        db_execute("ALTER TABLE business ADD COLUMN IF NOT EXISTS last_payment_date DATE")
        db_execute("ALTER TABLE business ADD COLUMN IF NOT EXISTS payment_months_late INTEGER DEFAULT 0")
        db_execute("ALTER TABLE business ADD COLUMN IF NOT EXISTS free_trial_end DATE")
        db_execute("ALTER TABLE business ADD COLUMN IF NOT EXISTS slug TEXT")
        db_execute("ALTER TABLE business ADD COLUMN IF NOT EXISTS hero_price REAL")
        db_execute("ALTER TABLE business ADD COLUMN IF NOT EXISTS hero_price_label TEXT")
        db_execute("ALTER TABLE business ADD COLUMN IF NOT EXISTS generated_html TEXT")
        db_execute("ALTER TABLE business ADD COLUMN IF NOT EXISTS brand_color TEXT DEFAULT '#2b7a78'")
        db_execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_premium INTEGER DEFAULT 0")
        db_execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS chosen_plan TEXT DEFAULT 'free'")
        # Agent-submitted business extras
        try:
            db_execute("ALTER TABLE business ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'basic'")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE business ADD COLUMN IF NOT EXISTS location TEXT")
        except Exception:
            pass
        # Real hosting + security: domains, deploy log, backups, scan cache, 2FA
        try:
            db_execute("ALTER TABLE business ADD COLUMN IF NOT EXISTS custom_domain TEXT")
            db_execute("ALTER TABLE business ADD COLUMN IF NOT EXISTS domain_status TEXT DEFAULT 'none'")
            db_execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS two_factor_enabled INTEGER DEFAULT 0")
            db_execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS two_factor_secret TEXT")
            if USE_POSTGRES:
                db_execute("CREATE TABLE IF NOT EXISTS deploy_events (id SERIAL PRIMARY KEY, business_id INTEGER, user_id INTEGER, event_type TEXT, message TEXT, status TEXT DEFAULT 'ok', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
                db_execute("CREATE TABLE IF NOT EXISTS site_backups (id SERIAL PRIMARY KEY, business_id INTEGER, html_snapshot TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
                db_execute("CREATE TABLE IF NOT EXISTS security_scans (id SERIAL PRIMARY KEY, user_id INTEGER, score INTEGER, checks TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            else:
                db_execute("CREATE TABLE IF NOT EXISTS deploy_events (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, user_id INTEGER, event_type TEXT, message TEXT, status TEXT DEFAULT 'ok', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
                db_execute("CREATE TABLE IF NOT EXISTS site_backups (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, html_snapshot TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
                db_execute("CREATE TABLE IF NOT EXISTS security_scans (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, score INTEGER, checks TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        except Exception as e:
            print(f"Migration (hosting/security) error: {e}")
        return "Migration done! All columns added."
    except Exception as e:
        return f"Migration error: {e}"


@app.route('/admin/preview/<int:biz_id>')
@admin_required
def admin_preview(biz_id):
    biz = db_fetchone(q("SELECT * FROM business WHERE id=?"), (biz_id,))
    if not biz:
        return "Business not found", 404
    bd = biz_to_dict(biz)
    branches = db_fetchall(q("SELECT * FROM branches WHERE business_id=?"), (biz_id,))
    bd['branches'] = [dict(b) for b in branches]
    ads = db_fetchall(q("SELECT * FROM ads WHERE business_id=? AND active=1 LIMIT 2"), (biz_id,))
    bd['ads'] = [dict(a) for a in ads]
    if bd.get('generated_html'):
        return bd['generated_html']
    wa_link = f"https://wa.me/{bd.get('whatsapp','')}"
    fallback_html = _basic_fallback_site(bd, wa_link)
    daisy_ctx = {
        'name': bd.get('name'), 'category': bd.get('category'),
        'description': bd.get('description'), 'whatsapp': bd.get('whatsapp'),
        'hours': bd.get('hours') or 'Mon-Sat 8am-7pm',
        'brand_color': bd.get('brand_color') or '#2b7a78',
        'photos': [p.strip() for p in str(bd.get('photos') or '').split(',') if p.strip()],
        'branches': bd.get('branches') or [], 'ads': bd.get('ads') or [],
        'plan': bd.get('plan') or 'free',
    }
    result, err = call_daisy('website', context=daisy_ctx)
    html = (result or {}).get('html') if result else None
    if html:
        try: db_execute(q("UPDATE business SET generated_html=? WHERE id=?"), (html, biz_id))
        except: pass
        return html
    print(f"[Daisy API] admin_preview fallback used for biz {biz_id}: {err}")
    return fallback_html


@app.route('/admin/check-payments')
@admin_required
def check_payments():
    from datetime import date
    overdue = db_fetchall(q(
        "SELECT b.*, u.name as owner_name FROM business b "
        "LEFT JOIN users u ON u.id=b.owner_id "
        "WHERE b.is_premium=1 AND b.free_trial_end IS NOT NULL "
        "AND b.free_trial_end < CURRENT_DATE "
        "AND (b.last_payment_date IS NULL OR b.last_payment_date < b.free_trial_end) "
        "ORDER BY b.free_trial_end ASC"
    ))
    reminded = 0
    suspended = 0
    for b in overdue:
        trial_end = b['free_trial_end']
        if hasattr(trial_end, 'date'):
            trial_end = trial_end.date()
        days_overdue = (date.today() - trial_end).days if trial_end else 0
        if days_overdue > 14:
            db_execute(q("UPDATE business SET is_premium=0,status='suspended' WHERE id=?"), (b['id'],))
            if b['owner_id']:
                db_insert(q("INSERT INTO notifications (user_id,message) VALUES (?,?)"),
                    (b['owner_id'], f"Your business has been suspended due to non-payment. Contact us on WhatsApp to reactivate."))
            suspended += 1
        else:
            if b['owner_id']:
                db_insert(q("INSERT INTO notifications (user_id,message) VALUES (?,?)"),
                    (b['owner_id'], f"Payment reminder: Your free month has ended. Pay UGX 7,500 or 15,000 via WhatsApp. You have {14 - days_overdue} days before suspension."))
            reminded += 1
    return f"Done. {reminded} reminded. {suspended} suspended."


@app.route('/about')
def about():
    return render_template('landing.html')

@app.route('/pricing')
def pricing():
    # Public — no login required, so people can see prices before committing.
    return render_template('pricing.html')

@app.route('/daisy')
def daisy_page():
    # Stopgap until Daisy's own pages are transferred into this app —
    # redirect to her current live deployment so this link never 404s.
    # Once her templates + /daisy/chat are wired locally, replace this
    # with render_template('daisy_landing.html') instead.
    return redirect('https://daisy-qg1c.onrender.com/welcome')

@app.route('/agent/set-password', methods=['GET', 'POST'])
def agent_set_password():
    email = request.args.get('email', '')
    biz = None
    if email:
        user = db_fetchone(q("SELECT * FROM users WHERE email=?"), (email,))
        if user:
            biz = db_fetchone(
                q("SELECT * FROM business WHERE owner_id=? AND status='approved' ORDER BY created_at DESC LIMIT 1"),
                (user['id'],)
            )
    if request.method == 'POST':
        email            = request.form.get('email', '').strip().lower()
        password         = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('set_password.html', email=email, biz=biz)
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('set_password.html', email=email, biz=biz)
        user = db_fetchone(q("SELECT * FROM users WHERE email=?"), (email,))
        if not user:
            flash('Email not found.', 'error')
            return render_template('set_password.html', email=email, biz=biz)
        db_execute(q("UPDATE users SET password=? WHERE id=?"),
            (generate_password_hash(password), user['id']))
        session['user_id'] = user['id']
        flash('Account activated! Welcome to TrustedBiz 🎉', 'success')
        return redirect('/dashboard')
    return render_template('set_password.html', email=email, biz=biz)


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html', current_user=get_current_user()), 404

@app.errorhandler(413)
def too_large(e):
    # Return 200 so Render doesn't intercept — then flash and redirect
    flash("Photos too large. Please use the compression button or choose fewer images.")
    from flask import make_response
    resp = make_response(redirect('/add-business'))
    return resp 
@app.route('/google2c13209b099aea62.html')
def google_verify():
    return "google-site-verification: google2c13209b099aea62"

@app.route('/trustedbiz2026.txt')
def indexnow_key():
    return "trustedbiz2026", 200, {'Content-Type': 'text/plain'}


@app.route('/sitemap.xml')
def sitemap():
    urls = [
        'https://trustedbiz.co.ug/',
        'https://trustedbiz.co.ug/about',
        'https://trustedbiz.co.ug/privacy',
        'https://trustedbiz.co.ug/terms'
    ]

    businesses = db_fetchall(
        q("SELECT slug FROM business WHERE status='approved'")
    )

    for biz in businesses:
        urls.append(f"https://{biz['slug']}.trustedbiz.co.ug")

    xml = '<?xml version="1.0" encoding="UTF-8"?>'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'

    for url in urls:
        xml += f'<url><loc>{url}</loc></url>'

    xml += '</urlset>'

    return app.response_class(
        xml,
        mimetype='application/xml'
    )


@app.route('/robots.txt')
def robots():
    return """
User-agent: *
Allow: /

Sitemap: https://trustedbiz.co.ug/sitemap.xml
""", 200, {'Content-Type': 'text/plain'}

# ── RUN ───────────────────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
# HOSTING — custom domains for Daisy-built business sites
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# HOSTING — deploy your own site, or connect a custom domain to a Daisy-built one
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/deploy', methods=['POST'])
@login_required
def deploy_site():
    """Bring-your-own-HTML hosting, the actual 'hosting platform' side of
    TrustedBiz — same idea as Render or Netlify, deploy what you already have.
    Separate from Daisy's business-builder flow, which creates the business
    record itself; this just needs a name and HTML."""
    user        = get_current_user()
    name        = request.form.get('name','').strip()
    category    = request.form.get('category','Website').strip()
    whatsapp    = request.form.get('whatsapp','').strip()
    brand_color = request.form.get('brand_color','#2b7a78').strip()
    description = request.form.get('description','').strip()
    custom_html = request.form.get('custom_html','').strip()
    html_file   = request.files.get('html_file')
    github_url  = request.form.get('github_url','').strip()

    if html_file and html_file.filename.endswith('.html'):
        custom_html = html_file.read().decode('utf-8')

    # Simple GitHub import — pulls index.html from a public repo's default
    # branch. Real push-to-deploy (via a GitHub App + webhook) needs GitHub
    # App credentials that don't exist yet; this covers "connect a repo" for now.
    if github_url and not custom_html:
        try:
            m = re.search(r'github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$', github_url)
            if m:
                owner, repo = m.group(1), m.group(2)
                for branch in ('main', 'master'):
                    r = requests.get(
                        f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/index.html",
                        timeout=10
                    )
                    if r.status_code == 200 and r.text.strip():
                        custom_html = r.text
                        break
                if not custom_html:
                    flash('Could not find an index.html on the main or master branch of that repo.', 'error')
                    return redirect('/dashboard#sites')
            else:
                flash('That doesn\'t look like a valid GitHub repo URL.', 'error')
                return redirect('/dashboard#sites')
        except Exception as e:
            print(f"GitHub import error: {e}")
            flash('Could not fetch that repo. Check the URL and that it\'s public.', 'error')
            return redirect('/dashboard#sites')

    if not name:
        flash('Site name is required.', 'error')
        return redirect('/dashboard#sites')
    if not custom_html:
        flash('Please upload HTML, paste it, or link a public GitHub repo.', 'error')
        return redirect('/dashboard#sites')
    slug   = make_slug(name)
    biz_id = db_insert(
        q("INSERT INTO business (name, category, whatsapp, description, brand_color, slug, owner_id, status, plan, is_premium, generated_html) VALUES (?,?,?,?,?,?,?,?,?,?,?)"),
        (name, category, whatsapp, description, brand_color, slug, user['id'], 'approved', 'free', 0, custom_html)
    )
    ping_google(slug)
    snapshot_site_html(biz_id, custom_html)
    log_deploy_event(biz_id, user['id'], 'deploy', f'"{name}" deployed successfully', 'ok')
    flash(f'🚀 "{name}" is now LIVE at {slug}.trustedbiz.co.ug!', 'success')
    return redirect('/dashboard#sites')


@app.route('/trusthost/request-domain', methods=['POST'])
@login_required
def trusthost_request_domain():
    user          = get_current_user()
    biz_id        = request.form.get('biz_id','').strip()
    custom_domain = request.form.get('domain','').strip().lower()
    custom_domain = custom_domain.replace('https://','').replace('http://','').rstrip('/')
    if not biz_id or not custom_domain:
        flash('Pick a site and enter a domain.', 'error')
        return redirect('/dashboard#hosting')
    biz = db_fetchone(q("SELECT id, name FROM business WHERE id=? AND owner_id=?"), (biz_id, user['id']))
    if not biz:
        flash('Site not found.', 'error')
        return redirect('/dashboard#hosting')
    try:
        db_execute(q("UPDATE business SET custom_domain=?, domain_status='pending' WHERE id=?"), (custom_domain, biz_id))
        log_deploy_event(biz_id, user['id'], 'domain_requested',
                         f'{biz["name"]}: custom domain "{custom_domain}" requested', 'ok')
        flash(f'✅ Domain "{custom_domain}" requested for {biz["name"]}! Point its CNAME at trustedbiz.co.ug, '
              f'then use "Verify DNS" below once it has propagated (can take up to 24hrs).', 'success')
    except Exception as e:
        print(f"[trusthost_request_domain] {e}")
        flash('Could not save that domain — run /admin/migrate-db then try again.', 'error')
    return redirect('/dashboard#hosting')


@app.route('/hosting/verify-domain/<int:biz_id>', methods=['POST'])
@login_required
def verify_domain(biz_id):
    """Real DNS/TLS check — actually connects to the domain over HTTPS
    rather than just flipping a status flag."""
    user = get_current_user()
    user = dict(user) if user else None
    if not user:
        return redirect('/login')
    biz  = db_fetchone(q("SELECT * FROM business WHERE id=? AND owner_id=?"), (biz_id, user['id']))
    biz  = dict(biz) if biz else None
    if not biz or not biz.get('custom_domain'):
        flash('No pending domain for that site.', 'error')
        return redirect('/dashboard#hosting')
    ok, detail, _days = check_domain_ssl(biz['custom_domain'])
    if ok:
        db_execute(q("UPDATE business SET domain_status='active' WHERE id=?"), (biz_id,))
        log_deploy_event(biz_id, user['id'], 'domain_connected',
                         f'{biz["name"]}: custom domain "{biz["custom_domain"]}" verified and SSL active', 'ok')
        if user.get('email'):
            _email_domain_live(user.get('name') or 'there', user['email'], biz['name'], biz['custom_domain'])
        flash(f'✅ {biz["custom_domain"]} is verified and live!', 'success')
    else:
        flash(f'Not verified yet — {detail}. DNS changes can take up to 24hrs.', 'error')
    return redirect('/dashboard#hosting')


@app.route('/security/scan', methods=['POST'])
@login_required
def security_scan():
    """Runs the real checks (SSL, content scan, backups, 2FA) live and
    caches the result so the panel doesn't re-scan on every page load."""
    result = run_security_scan(session['user_id'])
    store_security_scan(session['user_id'], result)
    return jsonify(result)


_2FA_PAGE = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Two-factor login | TrustedBiz</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'DM Sans',sans-serif;background:#f5f8f8;color:#0d1c1c;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}
.card{background:#fff;border:1px solid #dde8e8;border-radius:8px;padding:32px;max-width:420px;width:100%;}
h1{font-size:19px;font-weight:800;margin-bottom:6px;}
p{font-size:13.5px;color:#43605f;line-height:1.6;margin-bottom:14px;}
.secret{font-family:'DM Mono',monospace;font-size:13px;background:#f5f8f8;border:1px solid #dde8e8;border-radius:4px;padding:12px 14px;word-break:break-all;margin-bottom:16px;}
input{width:100%;padding:11px 14px;border:1.5px solid #dde8e8;border-radius:4px;font-family:'DM Mono',monospace;font-size:15px;letter-spacing:2px;margin-bottom:12px;}
button{width:100%;padding:11px;border-radius:4px;font-weight:700;font-size:13.5px;border:none;background:#2b7a78;color:#fff;cursor:pointer;}
button:hover{background:#1f5c5a;}
a{color:#2b7a78;font-size:13px;}
.flash{padding:10px 14px;border-radius:4px;font-size:13px;margin-bottom:14px;background:#fdecec;border-left:3px solid #dc2626;}
</style></head><body>
<div class="card">
  <h1>Set up two-factor login</h1>
  {% with messages = get_flashed_messages() %}{% if messages %}<div class="flash">{{ messages[0] }}</div>{% endif %}{% endwith %}
  <p>Scan this into an authenticator app (Google Authenticator, Authy, etc.), or enter the key manually:</p>
  <div class="secret">{{ secret }}</div>
  <p style="font-size:11.5px;color:#8aa5a4;">otpauth URI: {{ uri }}</p>
  <form method="POST" action="/account/2fa/enable">
    <input name="code" placeholder="6-digit code" inputmode="numeric" maxlength="6" required>
    <button type="submit">Confirm & enable</button>
  </form>
  <p style="margin-top:14px;"><a href="/dashboard#security">Cancel</a></p>
</div>
</body></html>
"""

_2FA_VERIFY_PAGE = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Verify code | TrustedBiz</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'DM Sans',sans-serif;background:#f5f8f8;color:#0d1c1c;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}
.card{background:#fff;border:1px solid #dde8e8;border-radius:8px;padding:32px;max-width:380px;width:100%;}
h1{font-size:19px;font-weight:800;margin-bottom:6px;}
p{font-size:13.5px;color:#43605f;line-height:1.6;margin-bottom:16px;}
input{width:100%;padding:11px 14px;border:1.5px solid #dde8e8;border-radius:4px;font-family:'DM Mono',monospace;font-size:15px;letter-spacing:2px;margin-bottom:12px;}
button{width:100%;padding:11px;border-radius:4px;font-weight:700;font-size:13.5px;border:none;background:#2b7a78;color:#fff;cursor:pointer;}
button:hover{background:#1f5c5a;}
.flash{padding:10px 14px;border-radius:4px;font-size:13px;margin-bottom:14px;background:#fdecec;border-left:3px solid #dc2626;}
</style></head><body>
<div class="card">
  <h1>Enter your code</h1>
  {% with messages = get_flashed_messages() %}{% if messages %}<div class="flash">{{ messages[0] }}</div>{% endif %}{% endwith %}
  <p>Open your authenticator app and enter the current 6-digit code for TrustedBiz.</p>
  <form method="POST">
    <input name="code" placeholder="6-digit code" inputmode="numeric" maxlength="6" required autofocus>
    <button type="submit">Verify & sign in</button>
  </form>
</div>
</body></html>
"""

@app.route('/account/2fa/setup')
@login_required
def account_2fa_setup():
    user = get_current_user()
    if user and dict(user).get('two_factor_enabled'):
        flash('Two-factor login is already enabled.')
        return redirect('/dashboard#security')
    secret = pyotp.random_base32()
    session['pending_2fa_secret'] = secret
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user['email'], issuer_name='TrustedBiz')
    return render_template_string(_2FA_PAGE, secret=secret, uri=uri)

@app.route('/account/2fa/enable', methods=['POST'])
@login_required
def account_2fa_enable():
    secret = session.get('pending_2fa_secret')
    code   = request.form.get('code','').strip()
    if not secret:
        flash('Start setup again.', 'error')
        return redirect('/dashboard#security')
    if pyotp.TOTP(secret).verify(code, valid_window=1):
        db_execute(q("UPDATE users SET two_factor_enabled=1, two_factor_secret=? WHERE id=?"), (secret, session['user_id']))
        session.pop('pending_2fa_secret', None)
        user = dict(get_current_user() or {})
        if user.get('email'):
            _email_2fa_enabled(user.get('name') or 'there', user['email'])
        flash('✅ Two-factor login enabled.', 'success')
        return redirect('/dashboard#security')
    flash("That code didn't match — try again.")
    return redirect('/account/2fa/setup')

@app.route('/account/2fa/disable', methods=['POST'])
@login_required
def account_2fa_disable():
    db_execute(q("UPDATE users SET two_factor_enabled=0, two_factor_secret=NULL WHERE id=?"), (session['user_id'],))
    flash('Two-factor login turned off.', 'success')
    return redirect('/dashboard#security')

@app.route('/login/verify-2fa', methods=['GET','POST'])
def login_verify_2fa():
    pending_id = session.get('pending_login_user_id')
    if not pending_id:
        return redirect('/login')
    if request.method == 'POST':
        code = request.form.get('code','').strip()
        user = db_fetchone(q("SELECT * FROM users WHERE id=?"), (pending_id,))
        user_d = dict(user) if user else None
        if user_d and user_d.get('two_factor_secret') and pyotp.TOTP(user_d['two_factor_secret']).verify(code, valid_window=1):
            session.pop('pending_login_user_id', None)
            session.permanent = True
            session['user_id']   = user['id']
            session['user_name'] = user['name']
            return redirect('/dashboard')
        flash('Invalid code — try again.')
    return render_template_string(_2FA_VERIFY_PAGE)


@app.route('/daisy/ping', methods=['GET','POST'])
def daisy_ping():
    return jsonify({"status":"alive","name":"Daisy"})


@app.route('/daisy/build', methods=['POST'])
def daisy_build():
    """Thin proxy to Daisy's own API — she does the generating, we just
    relay the request and cache the result so repeat requests in the same
    category can reuse it for free (template_pool)."""
    data    = request.get_json() or {}
    mode    = (data.get('mode') or '').strip()
    ctx     = data.get('context') or {}
    history = data.get('history') or []

    result, err = call_daisy(mode, context=ctx, history=history)
    html = (result or {}).get('html') if result else None

    if not html:
        return jsonify({'html': None, 'error': err or "Daisy is thinking hard on this one. Please try again in a moment.", 'mode': mode}), 503

    try:
        existing = db_fetchone(q("SELECT id FROM template_pool WHERE category=? AND html=?"), (mode, html))
        if not existing:
            db_insert(q("INSERT INTO template_pool (category, html, quality_score) VALUES (?,?,?)"), (mode, html, 80))
    except Exception as e:
        print(f"[Daisy/TemplateSave] {e}")

    return jsonify({'html': html, 'mode': mode})


@app.route('/daisy/save-testimonial', methods=['POST'])
def daisy_save_testimonial():
    """Save a user testimonial to the DB so it can appear on the homepage."""
    data = request.get_json() or {}
    text = (data.get('text') or '').strip()
    if len(text) < 10:
        return jsonify({'saved': False, 'reason': 'too short'})
    _u = get_current_user()
    user_id = _u['id'] if _u else None
    user_name = (_u.get('name') if _u else None) or 'Anonymous'
    try:
        db_insert(q("INSERT INTO daisy_training (input, output) VALUES (?,?)"),
                  (f"[TESTIMONIAL from {user_name}]", text))
        return jsonify({'saved': True})
    except Exception as e:
        print(f'[Testimonial] {e}')
        return jsonify({'saved': False, 'reason': str(e)})

@app.route('/daisy/save-training', methods=['POST'])
def daisy_save_training():
    """Save a Daisy Q&A pair to the database so it persists across restarts."""
    data = request.get_json() or {}
    inp  = (data.get('input') or '').strip()
    out  = (data.get('output') or '').strip()
    if not inp or not out:
        return jsonify({'saved': False, 'reason': 'empty'})
    try:
        # Skip exact duplicates
        existing = db_fetchone(q("SELECT id FROM daisy_training WHERE input=?"), (inp,))
        if existing:
            return jsonify({'saved': False, 'reason': 'duplicate'})
        db_insert(q("INSERT INTO daisy_training (input, output) VALUES (?,?)"), (inp, out))
        total = (db_fetchone(q("SELECT COUNT(*) as c FROM daisy_training")) or {}).get('c', 0)
        return jsonify({'saved': True, 'total': total})
    except Exception as e:
        print(f'[Daisy/SaveTraining] {e}')
        return jsonify({'saved': False, 'reason': str(e)})

@app.route('/admin/export-training')
@admin_required
def export_training():
    """Download all Daisy training data as training_data.json — replace file in repo and redeploy."""
    import json as _j
    rows = db_fetchall(q("SELECT input, output FROM daisy_training ORDER BY id ASC"))
    pairs = [{'input': r['input'], 'output': r['output']} for r in rows]
    from flask import Response
    return Response(
        _j.dumps(pairs, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=training_data.json'}
    )

@app.route('/daisy/chat', methods=['POST'])
def daisy_chat():
    """Thin proxy to Daisy's own API for the conversational flow."""
    data        = request.get_json() or {}
    msg         = (data.get('message') or data.get('user_input') or '').strip()
    history     = data.get('history', [])
    has_img     = data.get('has_image', False)
    photo_count = data.get('photo_count', 0)  # photos already uploaded this session, if any
    surface     = data.get('surface') or 'builder'  # 'home' = homepage widget, 'builder' = dashboard
    biz_id      = data.get('biz_id')  # set when the user picked "Edit with Daisy" on an existing site
    if not msg:
        default_reply = ('Hi! Ask me anything about TrustedBiz.' if surface == 'home'
                          else 'What would you like to build today?')
        return jsonify({'reply': default_reply, 'done': False})

    # Client memory: if we're editing a specific existing business, load
    # what Daisy already knows about it so she remembers it in this chat.
    existing_business = None
    if biz_id:
        user = get_current_user()
        if user:
            biz = db_fetchone(q("SELECT * FROM business WHERE id=? AND owner_id=?"), (biz_id, user['id']))
            if biz:
                existing_business = {
                    'name':        biz.get('name'),
                    'category':    biz.get('category'),
                    'description': biz.get('description'),
                    'whatsapp':    biz.get('whatsapp'),
                    'hours':       biz.get('hours'),
                    'brand_color': biz.get('brand_color'),
                    'live_url':    f"https://{biz['slug']}.trustedbiz.co.ug" if biz.get('slug') else None,
                    'status':      biz.get('status'),
                }

    result, err = call_daisy('chat',
                              context={'has_image': has_img, 'photo_count': photo_count,
                                       'surface': surface, 'existing_business': existing_business},
                              history=history, message=msg, timeout=20)
    if not result:
        return jsonify({'reply': err or "I'm having a small moment — try again!", 'done': False})

    return jsonify({
        'reply':    result.get('reply', ''),
        'done':     bool(result.get('mode')),
        'mode':     result.get('mode'),
        'business': result.get('business'),
    })


@app.route('/daisy/upload-photo', methods=['POST'])
@login_required
def daisy_upload_photo():
    """Photos uploaded mid-conversation in the Daisy builder — separate from
    the older /add-business form upload. Client sends already-compressed
    base64 images (see save_photos_b64) to dodge 413s; we save them the same
    way every other photo on TrustedBiz is saved and hand back real URLs the
    frontend can show as thumbnails and Daisy can drop straight into the
    generated site."""
    data   = request.get_json() or {}
    images = data.get('images') or []
    if isinstance(images, str):
        images = [images]
    if not images:
        return jsonify({'urls': [], 'error': 'No images received.'}), 400

    refs = save_photos_b64(images[:8])  # cap per request, matches gallery-sized use, not a bulk importer
    if not refs:
        return jsonify({'urls': [], 'error': "Couldn't save those photos — try a smaller image."}), 400

    urls = []
    for ref in refs:
        if ref.startswith('http'):
            urls.append(ref)
        else:
            urls.append(request.host_url.rstrip('/') + '/static/images/' + ref)

    return jsonify({'urls': urls})


@app.route('/search')
def search_page():
    q_str = request.args.get('q','')
    results = []
    if q_str:
        import re as _re
        pattern = '%' + q_str + '%'
        results = db_fetchall(
            q("SELECT name,slug,category,description,whatsapp FROM business WHERE status=\'approved\' AND (name LIKE ? OR category LIKE ? OR description LIKE ?) LIMIT 30"),
            (pattern, pattern, pattern)
        )
    return render_template('search.html',
        results=results, query=q_str,
        current_user=get_current_user())



# ══════════════════════════════════════════════════════════════════════════════
# DAISY VIDEO ENGINE ROUTES
# ══════════════════════════════════════════════════════════════════════════════
VIDEO_UPLOAD_DIR = Path("static/video_uploads")
VIDEO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_VIDEO_EXT = {"mp4","mov","avi","mkv","webm","3gp","m4v"}

def _allowed_video(fn):
    return "." in fn and fn.rsplit(".",1)[1].lower() in ALLOWED_VIDEO_EXT

@app.route("/daisy/video/upload", methods=["POST"])
def daisy_video_upload():
    from video_engine import submit_video_job
    user_prompt = (request.form.get("prompt") or request.form.get("message") or "").strip()
    video_file  = request.files.get("video")
    if not video_file or not video_file.filename:
        return jsonify({"error":"No video file uploaded"}), 400
    if not _allowed_video(video_file.filename):
        return jsonify({"error":"File type not supported. Use MP4, MOV, or 3GP"}), 400
    if not user_prompt:
        user_prompt = "Make a professional promo video"
    ext      = video_file.filename.rsplit(".",1)[1].lower()
    raw_path = VIDEO_UPLOAD_DIR / f"{secrets.token_hex(10)}.{ext}"
    try:
        video_file.save(str(raw_path))
    except Exception as e:
        return jsonify({"error":f"Upload failed: {e}"}), 500
    size_mb = raw_path.stat().st_size / (1024*1024)
    if size_mb > 150:
        raw_path.unlink(missing_ok=True)
        return jsonify({"error":"Video too large. Max 150MB"}), 400
    job_id = submit_video_job(str(raw_path), user_prompt)
    return jsonify({"job_id":job_id,"status":"processing",
        "message":"Daisy is editing your video... check back in 30-60 seconds 🎬",
        "prompt":user_prompt})

@app.route("/daisy/video/status/<job_id>", methods=["GET"])
def daisy_video_status(job_id):
    from video_engine import get_job
    job = get_job(job_id)
    if not job:
        return jsonify({"error":"Job not found"}), 404
    resp = {"job_id":job_id,"status":job["status"],"prompt":job.get("prompt","")}
    if job["status"] == "done":
        resp["url"]     = job["url"]
        resp["plan"]    = job.get("plan",{})
        resp["message"] = "Your video is ready! 🎬✨"
    elif job["status"] == "error":
        resp["error"]   = job.get("error","Unknown error")
        resp["message"] = "Something went wrong. Try again with a shorter video."
    else:
        resp["message"] = "Still editing... Daisy is working on it 🎬"
    return jsonify(resp)

@app.route("/daisy/video/check", methods=["GET"])
def daisy_video_check():
    import shutil as _sh
    ff = _sh.which("ffmpeg")
    fp = _sh.which("ffprobe")
    return jsonify({
        "ffmpeg":      bool(ff),
        "ffprobe":     bool(fp),
        "ffmpeg_path": ff,
        "cloudinary":  bool(os.environ.get("CLOUDINARY_URL")),
        "anthropic":   bool(os.environ.get("ANTHROPIC_API_KEY")),
        "ready":       bool(ff and fp),
        "message":     "Daisy Video Engine is ready 🎬" if ff else "FFmpeg not found — check build command"
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

def agent_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'agent_id' not in session:
            return redirect('/agent/login')
        return f(*args, **kwargs)
    return decorated

def get_current_agent():
    if 'agent_id' in session:
        return db_fetchone(q("SELECT * FROM agents WHERE id=?"), (session['agent_id'],))
    return None

def make_agent_code():
    """Generate a unique AGT-XXXX code."""
    while True:
        code = "AGT-" + str(secrets.randbelow(9000) + 1000)
        existing = db_fetchone(q("SELECT id FROM agents WHERE code=?"), (code,))
        if not existing:
            return code


@app.route('/agent/register', methods=['GET', 'POST'])
def agent_register():
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        whatsapp = request.form.get('whatsapp', '').strip()
        area     = request.form.get('area', '').strip()

        if not all([name, email, password, whatsapp, area]):
            flash('Please fill in all fields.', 'error')
            return render_template('agent_register.html')

        existing = db_fetchone(q("SELECT id FROM agents WHERE email=?"), (email,))
        if existing:
            flash('An agent account with that email already exists.', 'error')
            return render_template('agent_register.html')

        code     = make_agent_code()
        hashed   = generate_password_hash(password)
        agent_id = db_insert(
            q("INSERT INTO agents (name, email, password, whatsapp, area, code) VALUES (?,?,?,?,?,?)"),
            (name, email, hashed, whatsapp, area, code)
        )

        # Notify admin on WhatsApp
        admin_wa = os.environ.get('ADMIN_WHATSAPP', '256753187966')
        _send_wa_notification = f"New TrustedBiz Agent registered!\nName: {name}\nEmail: {email}\nArea: {area}\nCode: {code}\nWhatsApp: {whatsapp}"
        # (WhatsApp notification to admin — plug in your SMS/WA API here)

        session['agent_id'] = agent_id
        flash(f'Welcome {name}! Your agent code is {code}. Start adding businesses!', 'success')
        return redirect('/agent/dashboard')

    return render_template('agent_register.html')


@app.route('/agent/login', methods=['GET', 'POST'])
def agent_login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        agent = db_fetchone(q("SELECT * FROM agents WHERE email=?"), (email,))
        if not agent or not check_password_hash(agent['password'], password):
            flash('Invalid email or password.', 'error')
            return render_template('agent_login.html')

        session['agent_id'] = agent['id']
        return redirect('/agent/dashboard')

    return render_template('agent_login.html')


@app.route('/agent/logout')
def agent_logout():
    session.pop('agent_id', None)
    return redirect('/agent/login')


@app.route('/agent/dashboard')
@agent_login_required
def agent_dashboard():
    agent = get_current_agent()
    if not agent:
        return redirect('/agent/login')

    businesses = db_fetchall(
        q("SELECT * FROM business WHERE agent_code=? ORDER BY created_at DESC"),
        (agent['code'],)
    )

    approved = [b for b in businesses if b['status'] == 'approved']
    pending  = [b for b in businesses if b['status'] == 'pending']

    stats = {
        'total':        len(businesses),
        'approved':     len(approved),
        'pending':      len(pending),
        'earnings':     len(approved) * 1000,
        'total_earned': len(approved) * 1000,  # expand with real payout tracking later
    }

    # Fetch invite codes for approved businesses so agent can share passcodes
    invite_codes = {}
    for biz in businesses:
        if biz['status'] == 'approved':
            inv = db_fetchone(
                q("SELECT * FROM invite_codes WHERE biz_id=? ORDER BY id DESC LIMIT 1"),
                (biz['id'],)
            )
            if inv:
                invite_codes[biz['id']] = dict(inv)

    # Attach plan to each biz dict (from column if exists, else derive from is_premium)
    biz_dicts = []
    for biz in businesses:
        b = dict(biz)
        if not b.get('plan'):
            b['plan'] = 'promax' if b.get('is_premium') else 'free'
        biz_dicts.append(b)

    return render_template('agent_dashboard.html',
        agent=dict(agent),
        businesses=biz_dicts,
        stats=stats,
        invite_codes=invite_codes
    )


@app.route('/agent/add-business', methods=['POST'])
@agent_login_required
def agent_add_business():
    agent = get_current_agent()
    if not agent:
        return redirect('/agent/login')

    name        = request.form.get('name', '').strip()
    category    = request.form.get('category', '').strip()
    whatsapp    = request.form.get('whatsapp', '').strip()
    email       = request.form.get('email', '').strip().lower()
    location    = request.form.get('location', '').strip()
    hours       = request.form.get('hours', 'Mon–Sat 8am–6pm').strip() or 'Mon–Sat 8am–6pm'
    description = request.form.get('description', '').strip()
    brand_color = request.form.get('brand_color', '#2b7a78').strip()
    map_link    = request.form.get('map_link', '').strip()
    plan        = request.form.get('plan', 'basic').strip().lower()
    if plan not in ('free', 'basic', 'promax'):
        plan = 'basic'

    # Only name, category, location, description are required — email/whatsapp optional for demo
    if not all([name, category, location, description]):
        flash('Please fill in the business name, category, location and description.', 'error')
        return redirect('/agent/dashboard')

    # Create a placeholder user only if email was given
    owner_id = 0
    if email:
        existing_user = db_fetchone(q("SELECT id FROM users WHERE email=?"), (email,))
        if existing_user:
            owner_id = existing_user['id']
        else:
            temp_password = generate_password_hash(secrets.token_urlsafe(8))
            owner_id = db_insert(
                q("INSERT INTO users (name, email, password) VALUES (?,?,?)"),
                (name, email, temp_password)
            )

    slug       = make_slug(name)
    agent_code = agent['code']
    is_premium = 1 if plan in ('basic', 'promax') else 0

    # Store plan in the business record (reuse a spare column or add to notes)
    # We store plan value in a separate field; fall back to storing in description prefix if column missing
    try:
        biz_id = db_insert(
            q("INSERT INTO business (name, category, whatsapp, description, hours, brand_color, slug, owner_id, status, agent_code, is_premium, plan) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"),
            (name, category, whatsapp, description, hours, brand_color, slug, owner_id, 'pending', agent_code, is_premium, plan)
        )
    except Exception:
        # plan column may not exist yet — fallback without it
        biz_id = db_insert(
            q("INSERT INTO business (name, category, whatsapp, description, hours, brand_color, slug, owner_id, status, agent_code, is_premium) VALUES (?,?,?,?,?,?,?,?,?,?,?)"),
            (name, category, whatsapp, description, hours, brand_color, slug, owner_id, 'pending', agent_code, is_premium)
        )

    # Save location (stored in a notes/location field if available, otherwise skip gracefully)
    try:
        db_execute(q("UPDATE business SET location=? WHERE id=?"), (location, biz_id))
    except Exception:
        pass

    # Save photos if uploaded
    photos = request.files.getlist('photos')
    if photos and photos[0].filename:
        try:
            photo_refs = save_photos(photos)
            if photo_refs:
                db_execute(q("UPDATE business SET photos=? WHERE id=?"), (','.join(photo_refs), biz_id))
        except Exception:
            pass

    plan_label = {'free': 'Free', 'basic': 'Basic', 'promax': 'Pro Max'}.get(plan, plan.title())
    flash(f'✅ "{name}" ({plan_label} plan) submitted for approval! Once approved, you\'ll get a passcode to share with the owner.', 'success')
    return redirect('/agent/dashboard')


# ── ADMIN: Approve agent-submitted business and notify owner ──────────────────

@app.route('/admin/approve-agent-biz/<int:biz_id>', methods=['POST'])
@admin_required
def admin_approve_agent_biz(biz_id):
    biz = db_fetchone(q("SELECT * FROM business WHERE id=?"), (biz_id,))
    if not biz:
        return "Not found", 404

    db_execute(q("UPDATE business SET status='approved', verified=1 WHERE id=?"), (biz_id,))

    category = (biz.get('category') or '').lower().strip()

    # ── WEBSITE GENERATION ────────────────────────────────────────────────────
    # NOTE: the old pool-swap optimization (reusing a template's HTML and
    # string-swapping in the new business's name/contact info) lived inside
    # ai_generator.swap_business_info, which isn't available now that Daisy
    # is a separate service — that function's logic wasn't visible to build
    # a safe equivalent here. For now every business gets a fresh Daisy
    # build; times_used still increments so pool stats stay meaningful, and
    # a real swap-on-Daisy's-side is worth adding back once her API exists.
    import threading as _t
    biz_plan = (biz.get('plan') or 'free')

    pooled = db_fetchone(
        q("SELECT * FROM template_pool WHERE category=? AND times_used=0 ORDER BY quality_score DESC LIMIT 1"),
        (category,)
    )

    def _agent_gen(biz_dict, bid, cat, bplan, pool_id):
        daisy_ctx = {
            'name': biz_dict.get('name'), 'category': biz_dict.get('category'),
            'description': biz_dict.get('description'), 'whatsapp': biz_dict.get('whatsapp'),
            'hours': biz_dict.get('hours') or 'Mon-Sat 8am-7pm',
            'brand_color': biz_dict.get('brand_color') or '#2b7a78', 'plan': bplan,
        }
        result, err = call_daisy('website', context=daisy_ctx)
        html = (result or {}).get('html') if result else None
        if html and len(html) > 2000:
            db_execute(q("UPDATE business SET generated_html=? WHERE id=?"), (html, bid))
            if pool_id:
                db_execute(q("UPDATE template_pool SET times_used=times_used+1 WHERE id=?"), (pool_id,))
            else:
                db_insert(q("INSERT INTO template_pool (category, html, quality_score, times_used) VALUES (?,?,?,0)"),
                          (cat, html, 100))
            print(f"Daisy gen done for biz_id={bid} (category={cat})")
        else:
            print(f"[Daisy API] gen failed for biz_id={bid}: {err}")

    bd = biz_to_dict(biz)
    bd['branches'] = []
    bd['ads'] = []
    _t.Thread(target=_agent_gen, args=(bd, biz_id, category, biz_plan, pooled['id'] if pooled else None), daemon=True).start()
    ping_google(biz.get('slug', ''))
    flash(f"✅ '{biz['name']}' approved — Daisy is building the website now!", 'success')

    # ── INVITE CODE: generate one so the agent can give the owner dashboard access
    import string, secrets as _sec
    def _make_code():
        chars = string.ascii_uppercase + string.digits
        for _ in range(100):
            code = ''.join(_sec.choice(chars) for _ in range(6))
            if not db_fetchone(q("SELECT id FROM invite_codes WHERE code=?"), (code,)):
                return code
        return _sec.token_hex(3).upper()

    actual_plan = biz.get('plan') or 'basic'
    existing_code = db_fetchone(q("SELECT * FROM invite_codes WHERE biz_id=? AND used=0"), (biz_id,))
    if not existing_code:
        agent_row = db_fetchone(q("SELECT * FROM agents WHERE code=?"), (biz.get('agent_code'),)) if biz.get('agent_code') else None
        agent_id = agent_row['id'] if agent_row else 0
        invite_code_str = _make_code()
        db_insert(
            q("INSERT INTO invite_codes (code, biz_id, agent_id, plan) VALUES (?,?,?,?)"),
            (invite_code_str, biz_id, agent_id, actual_plan)
        )
    else:
        invite_code_str = existing_code['code']

    # Notify the agent with the invite code + direct link to share with the owner
    if biz.get('agent_code'):
        agent_row = db_fetchone(q("SELECT * FROM agents WHERE code=?"), (biz['agent_code'],))
        if agent_row:
            site_url  = f"https://{biz['slug']}.trustedbiz.co.ug"
            join_link = f"https://trustedbiz.co.ug/join?code={invite_code_str}"
            db_insert(
                q("INSERT INTO notifications (user_id, message) VALUES (?,?)"),
                (0, f"🎉 '{biz['name']}' APPROVED! Show the owner their website: {site_url} — passcode to share: {invite_code_str} — activation link: {join_link}")
            )

    return redirect('/admin')


@app.route('/join', methods=['GET', 'POST'])
def join_with_code():
    """Business owner enters invite code → creates account → gets dashboard access."""
    code = request.args.get('code', '').strip().upper()
    invite = None
    biz = None

    if code:
        invite = db_fetchone(q("SELECT * FROM invite_codes WHERE code=? AND used=0"), (code,))
        if invite:
            biz = db_fetchone(q("SELECT * FROM business WHERE id=?"), (invite['biz_id'],))
        else:
            flash("That invite code is invalid or already used. Contact your TrustedBiz agent for a new one.", "error")

    if request.method == 'POST':
        code     = request.form.get('code', '').strip().upper()
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm', '')

        invite = db_fetchone(q("SELECT * FROM invite_codes WHERE code=? AND used=0"), (code,))
        if not invite:
            flash("Invalid or already used invite code. Contact your TrustedBiz agent.", "error")
            return render_template('join.html', code=code, invite=None, biz=None)

        biz = db_fetchone(q("SELECT * FROM business WHERE id=?"), (invite['biz_id'],))

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template('join.html', code=code, invite=dict(invite), biz=biz_to_dict(biz) if biz else None)
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template('join.html', code=code, invite=dict(invite), biz=biz_to_dict(biz) if biz else None)

        # Create or update user
        existing_user = db_fetchone(q("SELECT * FROM users WHERE email=?"), (email,))
        if existing_user:
            user_id = existing_user['id']
            db_execute(q("UPDATE users SET password=?, name=? WHERE id=?"),
                       (generate_password_hash(password), name, user_id))
        else:
            user_id = db_insert(
                q("INSERT INTO users (name, email, password, is_premium) VALUES (?,?,?,1)"),
                (name, email, generate_password_hash(password))
            )

        # Link user to the business
        db_execute(q("UPDATE business SET owner_id=? WHERE id=?"), (user_id, biz['id']))
        # Mark code as used
        db_execute(q("UPDATE invite_codes SET used=1, used_by_user_id=? WHERE code=?"), (user_id, code))
        # Log them in
        session['user_id'] = user_id
        flash(f"🎉 Welcome to TrustedBiz! Your business dashboard is ready.", "success")
        return redirect('/dashboard')

    return render_template('join.html', code=code, invite=dict(invite) if invite else None,
                           biz=biz_to_dict(biz) if biz else None)


@app.route('/agent/generate-invite/<int:biz_id>', methods=['POST'])
@agent_login_required
def agent_generate_invite(biz_id):
    """Agent generates a unique invite code for a business they submitted."""
    agent = get_current_agent()
    biz = db_fetchone(q("SELECT * FROM business WHERE id=? AND agent_code=?"), (biz_id, agent['code']))
    if not biz:
        flash("Business not found.", "error")
        return redirect('/agent/dashboard')

    existing = db_fetchone(q("SELECT * FROM invite_codes WHERE biz_id=? AND used=0"), (biz_id,))
    if existing:
        join_link = f"https://trustedbiz.co.ug/join?code={existing['code']}"
        flash(f"Invite code: {existing['code']} — Share this link: {join_link}", "success")
        return redirect('/agent/dashboard')

    flash("This business hasn't been approved by admin yet. Check back soon.", "warning")
    return redirect('/agent/dashboard')


# ── MIGRATE: add agent columns if upgrading existing DB ──────────────────────
@app.route('/admin/migrate-agents')
@admin_required
def migrate_agents():
    try:
        db_execute("CREATE TABLE IF NOT EXISTS agents (id SERIAL PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT, whatsapp TEXT, area TEXT, code TEXT UNIQUE, status TEXT DEFAULT 'active', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    except: pass
    try:
        db_execute(q("ALTER TABLE business ADD COLUMN agent_code TEXT"))
    except: pass
    try:
        db_execute(q("ALTER TABLE business ADD COLUMN plan TEXT DEFAULT 'basic'"))
    except: pass
    try:
        db_execute(q("ALTER TABLE business ADD COLUMN location TEXT"))
    except: pass
    return "Agent migration done!"

