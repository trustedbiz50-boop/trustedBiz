import os
import math
import json
import re
import shutil
import sqlite3
import secrets
from datetime import timedelta, datetime
from difflib import SequenceMatcher
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, redirect, flash, session, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ─────────────────────────────────────────────
# APP CONFIG
# ─────────────────────────────────────────────
app = Flask(__name__)

# STRONG SECRET KEY
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['UPLOAD_FOLDER'] = 'static/images'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # reduced to 5MB

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

# ─────────────────────────────────────────────
# DATABASE (Render persistent disk compatible)
# ─────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def create_tables():
    conn = get_db()

    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT DEFAULT 'user',
        is_premium INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS business (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        category TEXT,
        whatsapp TEXT,
        lat REAL,
        lng REAL,
        photos TEXT,
        description TEXT,
        hours TEXT,
        status TEXT DEFAULT 'pending',
        verified INTEGER DEFAULT 0,
        reports INTEGER DEFAULT 0,
        views INTEGER DEFAULT 0,
        owner_id INTEGER,
        owner_ip TEXT,
        is_premium INTEGER DEFAULT 0,
        template_id TEXT DEFAULT 'cafe_warm',
        brand_color TEXT DEFAULT '#2b7a78',
        slug TEXT UNIQUE,
        hero_price REAL,
        hero_price_label TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id INTEGER,
        user_id INTEGER,
        rating INTEGER,
        comment TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id INTEGER,
        user_identifier TEXT
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        user_identifier TEXT,
        message TEXT,
        seen INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.commit()
    conn.close()

create_tables()

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(f'/login?next={request.path}')
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    if 'user_id' in session:
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        conn.close()
        return user
    return None

def make_slug(name):
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:60]
    conn = get_db()
    base, i = slug, 1
    while conn.execute("SELECT id FROM business WHERE slug=?", (slug,)).fetchone():
        slug = f"{base}-{i}"
        i += 1
    conn.close()
    return slug

# ─────────────────────────────────────────────
# SAFE FILE SAVE
# ─────────────────────────────────────────────
def save_photos(files):
    filenames = []
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    for photo in files:
        if photo and allowed_file(photo.filename):
            if not photo.mimetype.startswith('image/'):
                continue

            ext = photo.filename.rsplit('.', 1)[1].lower()
            unique_name = f"{secrets.token_hex(8)}.{ext}"
            path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)

            photo.save(path)
            filenames.append(unique_name)

    return filenames

# ─────────────────────────────────────────────
# ROUTES (UNCHANGED LOGIC)
# ─────────────────────────────────────────────
@app.route('/')
def home():
    conn = get_db()
    businesses = conn.execute("SELECT * FROM business WHERE status='approved'").fetchall()
    conn.close()

    return render_template('home.html',
        businesses_json=json.dumps([dict(b) for b in businesses]),
        current_user=get_current_user()
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '')[:100]
        email = request.form.get('email', '').lower()
        password = request.form.get('password', '')

        if len(password) < 6:
            flash("Password too short")
            return render_template('register.html')

        try:
            conn = get_db()
            conn.execute("INSERT INTO users (name, email, password) VALUES (?,?,?)",
                         (name, email, generate_password_hash(password)))
            conn.commit()
            conn.close()
            return redirect('/login')
        except:
            flash("Email exists")

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            return redirect('/dashboard')

        flash("Invalid login")

    return render_template('login.html')

@app.route('/add-business', methods=['POST'])
@login_required
def add_business():
    name = request.form.get('name', '')[:100]
    category = request.form.get('category', '')
    whatsapp = request.form.get('whatsapp', '')
    lat = request.form.get('lat')
    lng = request.form.get('lng')

    photos = save_photos(request.files.getlist('photos'))
    slug = make_slug(name)

    conn = get_db()
    conn.execute(
        "INSERT INTO business (name, category, whatsapp, lat, lng, photos, status, owner_id, slug) VALUES (?,?,?,?,?,?, 'pending', ?,?)",
        (name, category, whatsapp, lat, lng, ','.join(photos), session['user_id'], slug)
    )
    conn.commit()
    conn.close()

    return redirect('/dashboard')

# ─────────────────────────────────────────────
# ADMIN (SAFER)
# ─────────────────────────────────────────────
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    ADMIN_PASS = os.environ.get("ADMIN_PASS")

    if not ADMIN_PASS:
        return "Admin not configured", 500

    if not session.get('admin_auth'):
        if request.method == 'POST' and request.form.get('admin_pass') == ADMIN_PASS:
            session['admin_auth'] = True
        else:
            return render_template('admin_login.html')

    conn = get_db()
    businesses = conn.execute("SELECT * FROM business").fetchall()
    conn.close()

    return render_template('admin.html', businesses=businesses)

# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

