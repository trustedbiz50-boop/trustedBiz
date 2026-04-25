import os
import math
import json
import re
import secrets
import statistics
from datetime import timedelta, datetime
from difflib import SequenceMatcher
from functools import wraps
from pathlib import Path
from collections import defaultdict

from flask import (Flask, render_template, request, redirect,
                   flash, session, jsonify, send_file, url_for)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ─────────────────────────────────────────────────────────────────────
# APP CONFIG
# ─────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

# Custom JSON encoder handles datetime objects from PostgreSQL
class SafeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        from datetime import datetime, date
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

app.json_encoder = SafeJSONEncoder

@app.template_filter('dateformat')
def dateformat(value, fmt='%Y-%m-%d'):
    if not value:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime(fmt)
    return str(value)[:10]
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max upload

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

# ─────────────────────────────────────────────────────────────────────
# DATABASE — PostgreSQL on Render, SQLite locally
# ─────────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Render gives postgres:// but psycopg2 needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras

    def get_db():
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        return conn

    # PostgreSQL uses %s placeholders, not ?
    PH = "%s"

else:
    import sqlite3

    DB_PATH = os.environ.get("DB_PATH", "database.db")

    def get_db():
        conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    PH = "?"


def q(sql):
    """Convert ? placeholders to %s for PostgreSQL."""
    if USE_POSTGRES:
        return sql.replace("?", "%s")
    return sql


def create_tables():
    conn = get_db()

    if USE_POSTGRES:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            role TEXT DEFAULT 'user',
            is_premium INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS business (
            id SERIAL PRIMARY KEY,
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
            template_id TEXT DEFAULT 'trade',
            brand_color TEXT DEFAULT '#2b7a78',
            slug TEXT UNIQUE,
            hero_price REAL,
            hero_price_label TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            business_id INTEGER,
            user_id INTEGER,
            rating INTEGER,
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            business_id INTEGER,
            user_identifier TEXT
        )""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            user_identifier TEXT,
            message TEXT,
            seen INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        conn.commit()
        cur.close()

    else:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, email TEXT UNIQUE, password TEXT,
            role TEXT DEFAULT 'user', is_premium INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS business (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, category TEXT, whatsapp TEXT,
            lat REAL, lng REAL, photos TEXT,
            description TEXT, hours TEXT,
            status TEXT DEFAULT 'pending',
            verified INTEGER DEFAULT 0, reports INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0, owner_id INTEGER, owner_ip TEXT,
            is_premium INTEGER DEFAULT 0,
            template_id TEXT DEFAULT 'trade',
            brand_color TEXT DEFAULT '#2b7a78',
            slug TEXT UNIQUE,
            hero_price REAL, hero_price_label TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER, user_id INTEGER,
            rating INTEGER, comment TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER, user_identifier TEXT)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, user_identifier TEXT,
            message TEXT, seen INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")

        conn.commit()

    conn.close()


try:
    create_tables()
except Exception as e:
    print(f"DB init warning: {e}")


# ─────────────────────────────────────────────────────────────────────
# IMAGE STORAGE — Cloudinary on Render, local otherwise
# ─────────────────────────────────────────────────────────────────────
CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")
USE_CLOUDINARY = bool(CLOUDINARY_URL)

if USE_CLOUDINARY:
    import cloudinary
    import cloudinary.uploader
    cloudinary.config(cloudinary_url=CLOUDINARY_URL)

LOCAL_UPLOAD = Path("static/images")
LOCAL_UPLOAD.mkdir(parents=True, exist_ok=True)


def save_photos(files):
    """
    Save uploaded photos.
    - On Render with Cloudinary: upload to cloud, return URLs.
    - Locally: save to static/images/, return filenames.
    """
    results = []
    for photo in files:
        if not photo or not photo.filename:
            continue
        if not allowed_file(photo.filename):
            continue
        if not photo.mimetype.startswith('image/'):
            continue

        try:
            if USE_CLOUDINARY:
                # Upload to Cloudinary
                upload = cloudinary.uploader.upload(
                    photo,
                    folder="trustedbiz",
                    resource_type="image",
                    transformation=[
                        {"width": 1200, "height": 900,
                         "crop": "limit", "quality": "auto:good"}
                    ]
                )
                # Store the full Cloudinary URL
                results.append(upload["secure_url"])
            else:
                # Save locally
                ext = photo.filename.rsplit('.', 1)[1].lower()
                fname = f"{secrets.token_hex(8)}.{ext}"
                photo.save(str(LOCAL_UPLOAD / fname))
                results.append(fname)

        except Exception as e:
            print(f"Photo upload error: {e}")
            continue

    return results


def photo_url(photo_ref):
    """
    Given a photo reference (either a Cloudinary URL or a local filename),
    return the correct src URL for use in templates.
    """
    if not photo_ref:
        return ""
    if photo_ref.startswith("http"):
        return photo_ref  # already a full Cloudinary URL
    return f"/static/images/{photo_ref}"  # local filename


# Make photo_url available in all templates
app.jinja_env.globals['photo_url'] = photo_url


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────
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
        try:
            if USE_POSTGRES:
                cur = conn.cursor()
                cur.execute("SELECT * FROM users WHERE id=%s", (session['user_id'],))
                user = cur.fetchone()
                cur.close()
            else:
                user = conn.execute("SELECT * FROM users WHERE id=?",
                                    (session['user_id'],)).fetchone()
        finally:
            conn.close()
        return user
    return None


def db_fetchall(sql, params=()):
    conn = get_db()
    try:
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            cur.close()
            return rows
        else:
            return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def db_fetchone(sql, params=()):
    conn = get_db()
    try:
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            cur.close()
            return row
        else:
            return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def db_execute(sql, params=()):
    """Run INSERT/UPDATE/DELETE. Commits. Returns None."""
    conn = get_db()
    try:
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            cur.close()
        else:
            conn.execute(sql, params)
            conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"db_execute error: {e} | sql: {sql[:80]}")
        raise e
    finally:
        try:
            conn.close()
        except Exception:
            pass


def db_insert(sql, params=()):
    """INSERT and return last inserted id."""
    conn = get_db()
    try:
        if USE_POSTGRES:
            # Add RETURNING id to get back the new id
            if "RETURNING" not in sql.upper():
                sql = sql.rstrip(';') + " RETURNING id"
            cur = conn.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            conn.commit()
            cur.close()
            return row['id'] if row else None
        else:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        raise e
    finally:
        conn.close()


def make_slug(name):
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:60]
    base, i = slug, 1
    while db_fetchone(q("SELECT id FROM business WHERE slug=?"), (slug,)):
        slug = f"{base}-{i}"
        i += 1
    return slug


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def business_to_dict(b):
    """Convert a db row to a plain dict, converting datetime to strings."""
    from datetime import datetime, date
    d = dict(b)
    for k, v in d.items():
        if isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
    return d


# ─────────────────────────────────────────────────────────────────────
# ROUTES — HOME + SEARCH
# ─────────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    query    = request.args.get('query', '').strip()
    user_lat = request.args.get('lat', type=float)
    user_lng = request.args.get('lng', type=float)

    all_biz = db_fetchall(
        q("SELECT * FROM business WHERE status='approved' ORDER BY is_premium DESC, id DESC")
    )

    if query:
        ql = query.lower()
        scored = []
        for b in all_biz:
            bd = business_to_dict(b)
            name_score = similar(ql, (bd.get('name') or '').lower())
            cat_score  = similar(ql, (bd.get('category') or '').lower())
            score = max(name_score, cat_score)
            if (ql in (bd.get('name') or '').lower() or
                    ql in (bd.get('category') or '').lower() or
                    score > 0.45):
                scored.append((b, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        filtered = [b for b, _ in scored]
    else:
        filtered = list(all_biz)

    results = []
    for b in filtered:
        bd = business_to_dict(b)
        dist = 9999.0
        if user_lat and user_lng and bd.get('lat') and bd.get('lng'):
            try:
                dist = haversine(user_lat, user_lng,
                                 float(bd['lat']), float(bd['lng']))
            except Exception:
                dist = 9999.0
        results.append((bd, round(dist, 2)))

    if user_lat and user_lng:
        results.sort(key=lambda x: (0 if x[0].get('is_premium') else 1, x[1]))

    notifications = []
    if 'user_id' in session:
        notifications = db_fetchall(
            q("SELECT * FROM notifications WHERE user_id=? AND seen=0 ORDER BY created_at DESC LIMIT 5"),
            (session['user_id'],)
        )
        if notifications:
            db_execute(
                q("UPDATE notifications SET seen=1 WHERE user_id=?"),
                (session['user_id'],)
            )

    return render_template('home.html',
        results=[(dict(b), d) for b, d in results],
        businesses_json=json.dumps([business_to_dict(b) for b in all_biz]),
        current_user=get_current_user(),
        notifications=[dict(n) for n in notifications]
    )


# ─────────────────────────────────────────────────────────────────────
# ROUTES — AUTH
# ─────────────────────────────────────────────────────────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()[:100]
        email    = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')

        if not name or not email:
            flash("Please fill in all fields.")
            return render_template('register.html', current_user=None)
        if len(password) < 6:
            flash("Password must be at least 6 characters.")
            return render_template('register.html', current_user=None)

        try:
            db_insert(
                q("INSERT INTO users (name, email, password) VALUES (?,?,?)"),
                (name, email, generate_password_hash(password))
            )
            flash("Account created! Please log in.")
            return redirect('/login')
        except Exception:
            flash("That email is already registered.")

    return render_template('register.html', current_user=None)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')
        user = db_fetchone(q("SELECT * FROM users WHERE email=?"), (email,))
        if user and check_password_hash(user['password'], password):
            session.permanent = True
            session['user_id'] = user['id']
            next_url = request.args.get('next', '/dashboard')
            return redirect(next_url)
        flash("Wrong email or password.")
    return render_template('login.html', current_user=None)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ─────────────────────────────────────────────────────────────────────
# ROUTES — BUSINESS
# ─────────────────────────────────────────────────────────────────────
@app.route('/business/<int:biz_id>')
def business(biz_id):
    b = db_fetchone(q("SELECT * FROM business WHERE id=?"), (biz_id,))
    if not b:
        return render_template('404.html', current_user=get_current_user()), 404

    bd = business_to_dict(b)

    # Increment views
    db_execute(
        q("UPDATE business SET views = views + 1 WHERE id=?"), (biz_id,)
    )

    reviews = db_fetchall(
        q("""SELECT r.*, u.name as reviewer_name
             FROM reviews r
             LEFT JOIN users u ON u.id = r.user_id
             WHERE r.business_id=?
             ORDER BY r.created_at DESC"""),
        (biz_id,)
    )

    total_reviews = len(reviews)
    avg_rating    = 0
    if total_reviews > 0:
        try:
            avg_rating = round(sum(r['rating'] for r in reviews) / total_reviews, 1)
        except Exception:
            avg_rating = 0

    return render_template('business.html',
        business=bd,
        reviews=[dict(r) for r in reviews],
        total_reviews=total_reviews,
        avg_rating=avg_rating,
        current_user=get_current_user()
    )


@app.route('/add-business', methods=['GET', 'POST'])
@login_required
def add_business():
    if request.method == 'POST':
        name        = request.form.get('name', '').strip()[:100]
        category    = request.form.get('category', '').strip()
        whatsapp    = request.form.get('whatsapp', '').strip()
        lat         = request.form.get('lat', '').strip() or None
        lng         = request.form.get('lng', '').strip() or None
        description = request.form.get('description', '').strip()
        hours       = request.form.get('hours', '').strip()

        # Price Guard fields
        hero_price_label = request.form.get('hero_price_label', '').strip()
        hero_price_raw   = request.form.get('hero_price', '').strip()
        try:
            hero_price = float(hero_price_raw) if hero_price_raw else None
        except ValueError:
            hero_price = None

        if not name or not category or not whatsapp:
            flash("Business name, category, and WhatsApp are required.")
            return render_template('add-business.html', current_user=get_current_user())

        photos = save_photos(request.files.getlist('photos'))
        slug   = make_slug(name)

        try:
            db_insert(
                q("""INSERT INTO business
                     (name, category, whatsapp, lat, lng, photos,
                      description, hours, status, owner_id, owner_ip,
                      slug, hero_price, hero_price_label)
                     VALUES (?,?,?,?,?,?,?,?,'pending',?,?,?,?,?)"""),
                (name, category, whatsapp, lat, lng,
                 ','.join(photos), description, hours,
                 session['user_id'], request.remote_addr,
                 slug, hero_price, hero_price_label)
            )
            flash("Business submitted! It will appear after admin approval.")
        except Exception as e:
            flash(f"Error saving business: {str(e)[:100]}")

        return redirect('/dashboard')

    return render_template('add-business.html', current_user=get_current_user())


@app.route('/review/<int:biz_id>', methods=['POST'])
@login_required
def add_review(biz_id):
    # One review per user per business
    existing = db_fetchone(
        q("SELECT id FROM reviews WHERE business_id=? AND user_id=?"),
        (biz_id, session['user_id'])
    )
    if existing:
        flash("You have already reviewed this business.")
        return redirect(f'/business/{biz_id}')

    try:
        rating  = int(request.form.get('rating', 5))
        comment = request.form.get('comment', '').strip()[:500]
        rating  = max(1, min(5, rating))
    except ValueError:
        return redirect(f'/business/{biz_id}')

    db_insert(
        q("INSERT INTO reviews (business_id, user_id, rating, comment) VALUES (?,?,?,?)"),
        (biz_id, session['user_id'], rating, comment)
    )

    # Notify business owner
    b = db_fetchone(q("SELECT owner_id, name FROM business WHERE id=?"), (biz_id,))
    if b and b['owner_id']:
        db_insert(
            q("INSERT INTO notifications (user_id, message) VALUES (?,?)"),
            (b['owner_id'],
             f"New {rating}★ review on your business '{b['name']}'")
        )

    return redirect(f'/business/{biz_id}')


@app.route('/report/<int:biz_id>')
def report_business(biz_id):
    identifier = session.get('user_id') or request.remote_addr
    existing = db_fetchone(
        q("SELECT id FROM reports WHERE business_id=? AND user_identifier=?"),
        (biz_id, str(identifier))
    )
    if not existing:
        db_insert(
            q("INSERT INTO reports (business_id, user_identifier) VALUES (?,?)"),
            (biz_id, str(identifier))
        )
        db_execute(
            q("UPDATE business SET reports = reports + 1 WHERE id=?"), (biz_id,)
        )
        flash("Report submitted. Thank you.")
    return redirect(f'/business/{biz_id}')


# ─────────────────────────────────────────────────────────────────────
# ROUTES — PREMIUM WEBSITE
# ─────────────────────────────────────────────────────────────────────
@app.route('/site/<slug>')
def premium_site(slug):
    b = db_fetchone(
        q("SELECT * FROM business WHERE slug=? AND status='approved'"), (slug,)
    )
    if not b:
        return render_template('404.html', current_user=get_current_user()), 404

    bd = business_to_dict(b)

    try:
        from premium_templates import render_template_html, get_templates_for_category
        template_id = bd.get('template_id') or get_templates_for_category(bd.get('category', ''))
        html = render_template_html(template_id, bd)
        return html
    except Exception as e:
        return f"<h1>Website coming soon</h1><p>{bd.get('name')}</p>", 200


# ─────────────────────────────────────────────────────────────────────
# ROUTES — DASHBOARD
# ─────────────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    user = get_current_user()
    rows = db_fetchall(
        q("SELECT * FROM business WHERE owner_id=? ORDER BY created_at DESC"),
        (user['id'],)
    )
    businesses = [dict(b) for b in rows]

    # Stats the original dashboard template needs
    total_listings = len(businesses)
    live_count     = sum(1 for b in businesses if b.get('status') == 'approved')
    total_views    = sum(b.get('views') or 0 for b in businesses)

    # Per-business review stats
    stats = {}
    for b in businesses:
        rev_rows = db_fetchall(
            q("SELECT rating FROM reviews WHERE business_id=?"), (b['id'],)
        )
        ratings = [r['rating'] for r in rev_rows]
        stats[b['id']] = {
            'total_reviews': len(ratings),
            'avg_rating': round(sum(ratings)/len(ratings), 1) if ratings else 0
        }

    return render_template('dashboard.html',
        current_user=user,
        businesses=businesses,
        total_listings=total_listings,
        live_count=live_count,
        total_views=total_views,
        stats=stats
    )


@app.route('/edit-business/<int:biz_id>', methods=['GET', 'POST'])
@login_required
def edit_business(biz_id):
    b = db_fetchone(
        q("SELECT * FROM business WHERE id=? AND owner_id=?"),
        (biz_id, session['user_id'])
    )
    if not b:
        return redirect('/dashboard')

    if request.method == 'POST':
        name        = request.form.get('name', '').strip()[:100]
        category    = request.form.get('category', '').strip()
        whatsapp    = request.form.get('whatsapp', '').strip()
        description = request.form.get('description', '').strip()
        hours       = request.form.get('hours', '').strip()

        hero_price_raw = request.form.get('hero_price', '').strip()
        try:
            hero_price = float(hero_price_raw) if hero_price_raw else None
        except ValueError:
            hero_price = None
        hero_price_label = request.form.get('hero_price_label', '').strip()

        db_execute(
            q("""UPDATE business
                 SET name=?, category=?, whatsapp=?,
                     description=?, hours=?,
                     hero_price=?, hero_price_label=?
                 WHERE id=? AND owner_id=?"""),
            (name, category, whatsapp,
             description, hours,
             hero_price, hero_price_label,
             biz_id, session['user_id'])
        )
        flash("Business updated.")
        return redirect('/dashboard')

    return render_template('add-business.html',
        current_user=get_current_user(),
        editing=dict(b)
    )


@app.route('/dashboard/set-template/<int:biz_id>', methods=['POST'])
@login_required
def set_template(biz_id):
    template_id = request.form.get('template_id', 'trade')
    brand_color = request.form.get('brand_color', '#2b7a78')
    db_execute(
        q("UPDATE business SET template_id=?, brand_color=? WHERE id=? AND owner_id=?"),
        (template_id, brand_color, biz_id, session['user_id'])
    )
    flash("Website style updated.")
    return redirect('/dashboard')


# ─────────────────────────────────────────────────────────────────────
# ROUTES — PRICE GUARD
# ─────────────────────────────────────────────────────────────────────
@app.route('/price-guard')
def price_guard():
    rows = db_fetchall(
        q("""SELECT category, hero_price, hero_price_label
             FROM business
             WHERE status='approved' AND hero_price IS NOT NULL AND hero_price > 0""")
    )

    cat_data = defaultdict(list)
    cat_labels = {}
    for row in rows:
        cat = (row['category'] or '').lower().strip()
        price = float(row['hero_price'])
        label = row['hero_price_label'] or ''
        cat_data[cat].append(price)
        if label and cat not in cat_labels:
            cat_labels[cat] = label

    result = []
    for cat, prices in cat_data.items():
        if not prices:
            continue
        med = statistics.median(prices)
        filtered = [p for p in prices if med / 4 <= p <= med * 4]
        if not filtered:
            filtered = prices
        avg = round(sum(filtered) / len(filtered))
        result.append({
            'category':  cat,
            'label':     cat_labels.get(cat, f'Service in {cat}'),
            'average':   avg,
            'count':     len(filtered),
            'formatted': f"UGX {avg:,}",
        })

    result.sort(key=lambda x: x['count'], reverse=True)
    return jsonify(result)


# ─────────────────────────────────────────────────────────────────────
# ROUTES — ADMIN
# ─────────────────────────────────────────────────────────────────────
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

    # ── LOGIN CHECK ──────────────────────────────────────────────────
    if not session.get('admin_auth'):
        if request.method == 'POST' and 'admin_pass' in request.form:
            if request.form.get('admin_pass') == ADMIN_PASS:
                session.permanent = True
                session['admin_auth'] = True
                return redirect('/admin')
            else:
                flash("Wrong password.")
                return render_template('admin_login.html')
        return render_template('admin_login.html')

    # ── HANDLE FORM ACTIONS (approve/reject/verify/premium/delete) ───
    if request.method == 'POST' and 'action' in request.form:
        action = request.form.get('action', '')
        biz_id = request.form.get('id', '')
        try:
            biz_id = int(biz_id)
        except (ValueError, TypeError):
            flash("Invalid business ID.")
            return redirect('/admin')

        if action == 'approve':
            db_execute(q("UPDATE business SET status='approved' WHERE id=?"), (biz_id,))
            b = db_fetchone(q("SELECT owner_id, name FROM business WHERE id=?"), (biz_id,))
            if b and b['owner_id']:
                db_insert(q("INSERT INTO notifications (user_id, message) VALUES (?,?)"),
                    (b['owner_id'], f"✅ Your business '{b['name']}' is now live on TrustedBiz!"))
            flash(f"Business approved and is now live.")

        elif action == 'reject':
            db_execute(q("UPDATE business SET status='rejected' WHERE id=?"), (biz_id,))
            flash("Business rejected.")

        elif action == 'verify':
            db_execute(q("UPDATE business SET verified=1 WHERE id=?"), (biz_id,))
            flash("Business verified.")

        elif action == 'unverify':
            db_execute(q("UPDATE business SET verified=0 WHERE id=?"), (biz_id,))
            flash("Verification removed.")

        elif action == 'set_premium':
            db_execute(q("UPDATE business SET is_premium=1 WHERE id=?"), (biz_id,))
            b = db_fetchone(q("SELECT owner_id, name FROM business WHERE id=?"), (biz_id,))
            if b and b['owner_id']:
                db_insert(q("INSERT INTO notifications (user_id, message) VALUES (?,?)"),
                    (b['owner_id'], f"⭐ '{b['name']}' is now Premium on TrustedBiz! Your website is ready."))
            flash("Business upgraded to Premium.")

        elif action == 'remove_premium':
            db_execute(q("UPDATE business SET is_premium=0 WHERE id=?"), (biz_id,))
            flash("Premium removed.")

        elif action == 'delete':
            db_execute(q("DELETE FROM business WHERE id=?"), (biz_id,))
            flash("Business deleted.")

        return redirect('/admin')

    # ── LOAD ADMIN PAGE ──────────────────────────────────────────────
    businesses = db_fetchall(q("""
        SELECT b.*, u.name as owner_name
        FROM business b
        LEFT JOIN users u ON u.id = b.owner_id
        ORDER BY
            CASE WHEN b.status='pending' THEN 0 ELSE 1 END,
            b.created_at DESC
    """))

    all_biz          = list(businesses)
    total_businesses = len(all_biz)
    total_approved   = sum(1 for b in all_biz if b['status'] == 'approved')
    total_premium    = sum(1 for b in all_biz if b['is_premium'])
    pending          = sum(1 for b in all_biz if b['status'] == 'pending')
    total_reported   = sum(1 for b in all_biz if (b['reports'] or 0) > 0)
    total_users      = db_fetchone(q("SELECT COUNT(*) as c FROM users"))['c']
    total_reviews    = db_fetchone(q("SELECT COUNT(*) as c FROM reviews"))['c']

    return render_template('admin.html',
        businesses=[dict(b) for b in businesses],
        total_businesses=total_businesses,
        total_approved=total_approved,
        total_premium=total_premium,
        pending=pending,
        total_reported=total_reported,
        total_users=total_users,
        total_reviews=total_reviews,
    )


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_auth', None)
    return redirect('/')


@app.route('/admin/approve/<int:biz_id>')
def admin_approve(biz_id):
    if not session.get('admin_auth'):
        return redirect('/admin')
    db_execute(q("UPDATE business SET status='approved' WHERE id=?"), (biz_id,))
    b = db_fetchone(q("SELECT owner_id, name FROM business WHERE id=?"), (biz_id,))
    if b and b['owner_id']:
        db_insert(
            q("INSERT INTO notifications (user_id, message) VALUES (?,?)"),
            (b['owner_id'], f"✅ Your business '{b['name']}' is now live on TrustedBiz!")
        )
    return redirect(f"/admin?tab={request.args.get('tab','pending')}")


@app.route('/admin/reject/<int:biz_id>')
def admin_reject(biz_id):
    if not session.get('admin_auth'):
        return redirect('/admin')
    db_execute(q("UPDATE business SET status='rejected' WHERE id=?"), (biz_id,))
    return redirect(f"/admin?tab={request.args.get('tab','pending')}")


@app.route('/admin/delete/<int:biz_id>')
def admin_delete(biz_id):
    if not session.get('admin_auth'):
        return redirect('/admin')
    db_execute(q("DELETE FROM business WHERE id=?"), (biz_id,))
    return redirect(f"/admin?tab={request.args.get('tab','all')}")


@app.route('/admin/verify/<int:biz_id>')
def admin_verify(biz_id):
    if not session.get('admin_auth'):
        return redirect('/admin')
    db_execute(q("UPDATE business SET verified=1 WHERE id=?"), (biz_id,))
    return redirect(f"/admin?tab={request.args.get('tab','all')}")


@app.route('/admin/set-premium/<int:biz_id>')
def admin_set_premium(biz_id):
    if not session.get('admin_auth'):
        return redirect('/admin')
    db_execute(q("UPDATE business SET is_premium=1 WHERE id=?"), (biz_id,))
    b = db_fetchone(q("SELECT owner_id, name FROM business WHERE id=?"), (biz_id,))
    if b and b['owner_id']:
        db_insert(
            q("INSERT INTO notifications (user_id, message) VALUES (?,?)"),
            (b['owner_id'],
             f"⭐ '{b['name']}' is now Premium on TrustedBiz!")
        )
    return redirect(f"/admin?tab={request.args.get('tab','all')}")


@app.route('/admin/remove-premium/<int:biz_id>')
def admin_remove_premium(biz_id):
    if not session.get('admin_auth'):
        return redirect('/admin')
    db_execute(q("UPDATE business SET is_premium=0 WHERE id=?"), (biz_id,))
    return redirect(f"/admin?tab={request.args.get('tab','all')}")


# ─────────────────────────────────────────────────────────────────────
# ROUTES — DATABASE BACKUP
# ─────────────────────────────────────────────────────────────────────
@app.route('/admin/backup-db')
def backup_db():
    secret = request.args.get('secret', '')
    if secret != os.environ.get('ADMIN_PASS', 'admin123'):
        return "Unauthorized", 403
    if USE_POSTGRES:
        return jsonify({"info": "PostgreSQL is managed by Render. Use Render dashboard to backup."})
    import sqlite3 as _sq, shutil
    Path('backups').mkdir(exist_ok=True)
    name = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db"
    path = Path('backups') / name
    src  = _sq.connect('database.db')
    dst  = _sq.connect(str(path))
    src.backup(dst)
    src.close(); dst.close()
    return send_file(str(path), as_attachment=True, download_name=name)


# ─────────────────────────────────────────────────────────────────────
# ROUTES — STATIC PAGES
# ─────────────────────────────────────────────────────────────────────
@app.route('/privacy')
def privacy():
    return render_template('privacy.html', current_user=get_current_user())

@app.route('/terms')
def terms():
    return render_template('terms.html', current_user=get_current_user())

@app.route('/favicon.ico')
def favicon():
    return '', 204


# ─────────────────────────────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html', current_user=get_current_user()), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('404.html', current_user=get_current_user()), 500


# ─────────────────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
