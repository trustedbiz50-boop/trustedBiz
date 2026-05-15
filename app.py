"""
TrustedBiz — app.py
All routes. Add your keys in environment variables and run.

REQUIRED ENV VARS (add on Render dashboard):
  SECRET_KEY          = any random string
  ANTHROPIC_API_KEY   = sk-ant-... (from console.anthropic.com)
  DATABASE_URL        = auto-set by Render PostgreSQL
  CLOUDINARY_URL      = from cloudinary.com
  ADMIN_PASSWORD      = your secret admin password
  ADMIN_WHATSAPP      = 256753187966
  DGATEWAY_API_KEY    = (add when ready)
  DGATEWAY_MERCHANT_ID= (add when ready)
"""

import os, math, json, re, secrets
from datetime import timedelta, datetime
from difflib import SequenceMatcher
from functools import wraps
from pathlib import Path
from flask import (Flask, render_template, request, redirect,
                   flash, session, jsonify, url_for)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ── APP ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

ALLOWED_EXTENSIONS = {'png','jpg','jpeg','gif','webp'}
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
        "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT, role TEXT DEFAULT 'user', is_premium INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS business (id SERIAL PRIMARY KEY, name TEXT, category TEXT, whatsapp TEXT, lat REAL, lng REAL, photos TEXT, description TEXT, hours TEXT, status TEXT DEFAULT 'pending', verified INTEGER DEFAULT 0, reports INTEGER DEFAULT 0, views INTEGER DEFAULT 0, owner_id INTEGER, owner_ip TEXT, is_premium INTEGER DEFAULT 0, brand_color TEXT DEFAULT '#2b7a78', slug TEXT UNIQUE, hero_price REAL, hero_price_label TEXT, generated_html TEXT, last_payment_date DATE, payment_months_late INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS branches (id SERIAL PRIMARY KEY, business_id INTEGER, name TEXT, address TEXT, whatsapp TEXT, hours TEXT, lat REAL, lng REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS reviews (id SERIAL PRIMARY KEY, business_id INTEGER, user_id INTEGER, rating INTEGER, comment TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS reports (id SERIAL PRIMARY KEY, business_id INTEGER, user_identifier TEXT)",
        "CREATE TABLE IF NOT EXISTS notifications (id SERIAL PRIMARY KEY, user_id INTEGER, user_identifier TEXT, message TEXT, seen INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS price_guard_items (id SERIAL PRIMARY KEY, business_id INTEGER, category TEXT, label TEXT, price REAL, image_ref TEXT, ai_name TEXT, ai_verified INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS ads (id SERIAL PRIMARY KEY, business_id INTEGER, title TEXT, body TEXT, image_ref TEXT, active INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        ]
        cur = conn.cursor()
        for t in tables: cur.execute(t)
        conn.commit(); cur.close()
    else:
        tables = [
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, password TEXT, role TEXT DEFAULT 'user', is_premium INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS business (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category TEXT, whatsapp TEXT, lat REAL, lng REAL, photos TEXT, description TEXT, hours TEXT, status TEXT DEFAULT 'pending', verified INTEGER DEFAULT 0, reports INTEGER DEFAULT 0, views INTEGER DEFAULT 0, owner_id INTEGER, owner_ip TEXT, is_premium INTEGER DEFAULT 0, brand_color TEXT DEFAULT '#2b7a78', slug TEXT UNIQUE, hero_price REAL, hero_price_label TEXT, generated_html TEXT, last_payment_date DATE, payment_months_late INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS branches (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, name TEXT, address TEXT, whatsapp TEXT, hours TEXT, lat REAL, lng REAL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, user_id INTEGER, rating INTEGER, comment TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, user_identifier TEXT)",
        "CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, user_identifier TEXT, message TEXT, seen INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS price_guard_items (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, category TEXT, label TEXT, price REAL, image_ref TEXT, ai_name TEXT, ai_verified INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS ads (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, title TEXT, body TEXT, image_ref TEXT, active INTEGER DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
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

def get_anthropic_client():
    key = os.environ.get("ANTHROPIC_API_KEY","")
    if not key: return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=key)
    except ImportError:
        return None

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

    return render_template('home.html',
        results=results,
        current_user=get_current_user(),
        notifications=notifications)

# ── PRICE GUARD API ───────────────────────────────────────────────────────────
@app.route('/price-guard')
def price_guard_api():
    # Use price_guard_items table (richer data with images)
    rows = db_fetchall(q("""
        SELECT p.category, p.label, p.price, p.image_ref, p.ai_name,
               b.name as biz_name, b.slug, b.is_premium,
               AVG(p.price) OVER (PARTITION BY p.category, p.label) as average,
               COUNT(*) OVER (PARTITION BY p.category, p.label) as count
        FROM price_guard_items p
        JOIN business b ON b.id = p.business_id
        WHERE b.status='approved'
        ORDER BY count DESC, p.created_at DESC
        LIMIT 60
    """)) if USE_POSTGRES else db_fetchall("""
        SELECT p.category, p.label, p.price, p.image_ref, p.ai_name,
               b.name as biz_name, b.slug, b.is_premium
        FROM price_guard_items p
        JOIN business b ON b.id = p.business_id
        WHERE b.status='approved'
        ORDER BY p.created_at DESC
        LIMIT 60
    """)

    # Group by category+label
    grouped = {}
    for r in rows:
        key = f"{r['category']}|{r['label']}"
        if key not in grouped:
            grouped[key] = {
                "category": str(r['category'] or '').title(),
                "label":    str(r['label'] or ''),
                "average":  0, "count": 0,
                "images":   []
            }
        grouped[key]['count'] += 1
        grouped[key]['average'] = (grouped[key]['average'] * (grouped[key]['count']-1) + float(r['price'] or 0)) / grouped[key]['count']
        if r.get('image_ref'):
            grouped[key]['images'].append({
                "src":      photo_url(r['image_ref']),
                "biz_name": r['biz_name'],
                "slug":     r['slug'],
                "premium":  bool(r['is_premium'])
            })

    data = []
    for item in sorted(grouped.values(), key=lambda x: x['count'], reverse=True)[:20]:
        item['average'] = round(item['average'], 0)
        data.append(item)

    return jsonify(data)

# ── AI DESCRIPTION HELPER ─────────────────────────────────────────────────────
@app.route('/ai-describe', methods=['POST'])
def ai_describe():
    """Generate a business description using AI."""
    data     = request.get_json() or {}
    name     = str(data.get('name','')).strip()[:100]
    category = str(data.get('category','')).strip()[:50]

    if not name or not category:
        return jsonify({"error": "Name and category required"}), 400

    client = get_anthropic_client()
    if not client:
        # Fallback template when no API key
        desc = (f"{name} is a professional {category} business in Uganda. "
                f"We provide high-quality {category} services to our customers. "
                f"Our team is experienced, reliable, and dedicated to giving you the best service. "
                f"Contact us on WhatsApp anytime for inquiries and bookings.")
        return jsonify({"description": desc})

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{"role":"user","content":
                f"Write a 3-sentence business description for a {category} business called '{name}' in Uganda. "
                f"Make it sound professional, warm, and specific to what a {category} business does. "
                f"Do NOT use generic phrases like 'we strive' or 'we are committed'. "
                f"Make it feel real and local. Return ONLY the description, no extra text."}]
        )
        desc = msg.content[0].text.strip()
        return jsonify({"description": desc})
    except Exception as e:
        print(f"AI describe error: {e}")
        return jsonify({"description": f"Professional {category} services in Uganda. We deliver quality work every time. Contact us on WhatsApp for a quote."}), 200

# ── AI PRICE GUARD INSPECTOR ──────────────────────────────────────────────────
@app.route('/ai-inspect-price', methods=['POST'])
@login_required
def ai_inspect_price():
    """
    AI inspects a product image and returns:
    - ai_name: what AI thinks the product is
    - local_name: what the user called it
    - price_suggestion: fair price range
    - verified: bool
    """
    label = request.form.get('label','').strip()
    price = request.form.get('price','').strip()
    image = request.files.get('image')

    client = get_anthropic_client()

    # Save image first
    image_ref = None
    if image and image.filename:
        image_ref = save_single_photo(image)

    if not client or not image_ref:
        # No AI — just accept as-is
        return jsonify({
            "ai_name":   label,
            "verified":  True,
            "message":   "Added successfully.",
            "image_ref": image_ref
        })

    try:
        import base64
        # Read image for Claude vision
        if USE_CLOUDINARY and image_ref.startswith("http"):
            # For Cloudinary we can't re-read easily — skip vision, just name check
            msg = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                messages=[{"role":"user","content":
                    f"A business called this product: '{label}' with price UGX {price}. "
                    f"What is the common/international name for this product? "
                    f"Is UGX {price} a fair price in Uganda? "
                    f"Reply in JSON only: {{\"ai_name\":\"...\",\"fair_price\":true/false,\"message\":\"...\"}}"}]
            )
        else:
            # Local file — use vision
            img_path = LOCAL_UPLOAD / image_ref
            with open(str(img_path),'rb') as f:
                img_data = base64.standard_b64encode(f.read()).decode('utf-8')

            # Detect media type
            ext = image_ref.rsplit('.',1)[-1].lower()
            media_type = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","webp":"image/webp","gif":"image/gif"}.get(ext,"image/jpeg")

            msg = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=250,
                messages=[{"role":"user","content":[
                    {"type":"image","source":{"type":"base64","media_type":media_type,"data":img_data}},
                    {"type":"text","text":
                        f"Look at this product image. The seller calls it '{label}' and priced it at UGX {price} in Uganda. "
                        f"1. What is this product's proper/international name? "
                        f"2. Is UGX {price} a fair price for Uganda? "
                        f"Reply in JSON only: {{\"ai_name\":\"proper product name\",\"local_name\":\"{label}\",\"fair_price\":true/false,\"message\":\"one sentence explanation\"}}"}
                ]}]
            )

        raw = msg.content[0].text.strip()
        raw = re.sub(r'^```json|^```|```$','',raw.strip()).strip()
        result = json.loads(raw)
        result['image_ref'] = image_ref
        result['verified']  = True
        return jsonify(result)

    except Exception as e:
        print(f"AI inspect error: {e}")
        return jsonify({"ai_name": label, "verified": True, "image_ref": image_ref, "message": "Added."})

# ── ADD PRICE GUARD ITEM ──────────────────────────────────────────────────────
@app.route('/add-price-item', methods=['POST'])
@login_required
def add_price_item():
    """Save a price guard item after AI inspection."""
    biz_id   = request.form.get('business_id')
    label    = request.form.get('label','').strip()
    price    = request.form.get('price','').strip()
    ai_name  = request.form.get('ai_name', label).strip()
    image_ref= request.form.get('image_ref','').strip()

    # Verify this business belongs to user
    biz = db_fetchone(q("SELECT id,category FROM business WHERE id=? AND owner_id=?"),
                      (biz_id, session['user_id']))
    if not biz:
        return jsonify({"error":"Not found"}), 404

    try:
        db_insert(q("""
            INSERT INTO price_guard_items (business_id,category,label,price,image_ref,ai_name,ai_verified)
            VALUES (?,?,?,?,?,?,1)
        """), (biz_id, biz['category'], label, float(price), image_ref, ai_name))
        return jsonify({"success": True, "message": "Price item added to Price Guard!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── AUTH ──────────────────────────────────────────────────────────────────────
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
            db_insert(q("INSERT INTO users (name,email,password) VALUES (?,?,?)"),
                      (name,email,generate_password_hash(pwd)))
            flash("Account created! Please login.")
            return redirect('/login')
        except: flash("Email already registered.")
    return render_template('register.html', current_user=None)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email','').lower().strip()
        pwd   = request.form.get('password','')
        user  = db_fetchone(q("SELECT * FROM users WHERE email=?"), (email,))
        if user and check_password_hash(user['password'], pwd):
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
def site(slug):
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

    from ai_generator import generate_business_website
    html = generate_business_website(bd)
    try: db_execute(q("UPDATE business SET generated_html=? WHERE id=?"), (html, biz['id']))
    except Exception as e: print(f"Cache error: {e}")
    return html

# ── REGENERATE ────────────────────────────────────────────────────────────────
@app.route('/generate-site/<int:biz_id>', methods=['POST'])
@login_required
def generate_site(biz_id):
    biz = db_fetchone(q("SELECT * FROM business WHERE id=? AND owner_id=?"), (biz_id,session['user_id']))
    if not biz: flash("Not found."); return redirect('/dashboard')
    bd = biz_to_dict(biz)
    branches = db_fetchall(q("SELECT * FROM branches WHERE business_id=?"), (biz_id,))
    bd['branches'] = [dict(b) for b in branches]
    ads = db_fetchall(q("SELECT * FROM ads WHERE business_id=? AND active=1 LIMIT 2"), (biz_id,))
    bd['ads'] = [dict(a) for a in ads]
    from ai_generator import generate_business_website
    html = generate_business_website(bd)
    try: db_execute(q("UPDATE business SET generated_html=? WHERE id=?"), (html,biz_id))
    except Exception as e: print(f"Regen error: {e}")
    flash("✅ Website regenerated!")
    return redirect('/dashboard')

# ── ADD BUSINESS ──────────────────────────────────────────────────────────────
@app.route('/add-business', methods=['GET','POST'])
@login_required
def add_business():
    user = get_current_user()
    existing = db_fetchall(q("SELECT id FROM business WHERE owner_id=?"), (user['id'],))
    if len(existing) >= 1 and not user['is_premium']:
        return render_template('upgrade.html', business=None,
                               basic_link=f"https://wa.me/{ADMIN_WHATSAPP}?text=I+want+to+upgrade+TrustedBiz",
                               promax_link=f"https://wa.me/{ADMIN_WHATSAPP}?text=I+want+Pro+Max+TrustedBiz",
                               use_dgateway=False, current_user=user)

    if request.method == 'POST':
        name        = request.form.get('name','').strip()[:100]
        category    = request.form.get('category','').strip().lower()
        whatsapp    = request.form.get('whatsapp','').strip()
        lat         = request.form.get('lat','').strip() or None
        lng         = request.form.get('lng','').strip() or None
        description = request.form.get('description','').strip()
        hours       = request.form.get('hours','').strip()
        color       = request.form.get('brand_color','#2b7a78').strip()
        hero_price  = request.form.get('hero_price','').strip() or None
        hero_label  = request.form.get('hero_price_label','').strip()
        slug        = make_slug(name)
        photos      = save_photos(request.files.getlist('photos'))
        photos_str  = ",".join(photos)

        try:
            biz_id = db_insert(q("""
                INSERT INTO business
                  (name,category,whatsapp,lat,lng,photos,description,hours,
                   brand_color,slug,hero_price,hero_price_label,
                   status,owner_ip,owner_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)
            """), (name,category,whatsapp,lat,lng,photos_str,description,hours,
                   color,slug,hero_price,hero_label,request.remote_addr,user['id']))

            # Auto-add to price guard if price provided
            if hero_price and hero_label and biz_id:
                db_insert(q("""
                    INSERT INTO price_guard_items (business_id,category,label,price,ai_name,ai_verified)
                    VALUES (?,?,?,?,?,0)
                """), (biz_id, category, hero_label, float(hero_price), hero_label))

            flash("Business submitted! Waiting for approval.")
            return redirect('/dashboard')
        except Exception as e:
            print(e); flash("Error submitting. Please try again.")

    return render_template('add-business.html', editing=None, current_user=user)

# ── EDIT BUSINESS ─────────────────────────────────────────────────────────────
@app.route('/edit-business/<int:biz_id>', methods=['GET','POST'])
@login_required
def edit_business(biz_id):
    biz = db_fetchone(q("SELECT * FROM business WHERE id=? AND owner_id=?"), (biz_id,session['user_id']))
    if not biz: flash("Not found."); return redirect('/dashboard')

    if request.method == 'POST':
        name        = request.form.get('name','').strip()
        category    = request.form.get('category','').strip().lower()
        whatsapp    = request.form.get('whatsapp','').strip()
        description = request.form.get('description','').strip()
        hours       = request.form.get('hours','').strip()
        color       = request.form.get('brand_color', biz['brand_color'] or '#2b7a78').strip()
        hero_price  = request.form.get('hero_price','').strip() or None
        hero_label  = request.form.get('hero_price_label','').strip()
        db_execute(q("""UPDATE business SET
            name=?,category=?,whatsapp=?,description=?,hours=?,
            brand_color=?,hero_price=?,hero_price_label=?,generated_html=NULL
            WHERE id=?"""),
            (name,category,whatsapp,description,hours,color,hero_price,hero_label,biz_id))
        flash("Updated! Your website is being regenerated.")
        return redirect('/dashboard')

    return render_template('add-business.html', editing=biz_to_dict(biz), current_user=get_current_user())

# ── ADD BRANCH ────────────────────────────────────────────────────────────────
@app.route('/add-branch/<int:biz_id>', methods=['GET','POST'])
@login_required
def add_branch(biz_id):
    biz = db_fetchone(q("SELECT * FROM business WHERE id=? AND owner_id=?"), (biz_id,session['user_id']))
    if not biz: flash("Not found."); return redirect('/dashboard')
    if request.method == 'POST':
        db_insert(q("INSERT INTO branches (business_id,name,address,whatsapp,hours,lat,lng) VALUES (?,?,?,?,?,?,?)"),
                  (biz_id,request.form.get('name','').strip(),request.form.get('address','').strip(),
                   request.form.get('whatsapp','').strip(),request.form.get('hours','').strip(),
                   request.form.get('lat','').strip() or None,request.form.get('lng','').strip() or None))
        db_execute(q("UPDATE business SET generated_html=NULL WHERE id=?"), (biz_id,))
        flash("Branch added! Website will update.")
        return redirect('/dashboard')
    return render_template('add-branch.html', business=biz_to_dict(biz), current_user=get_current_user())

# ── ADS — CREATE / EDIT / DELETE ─────────────────────────────────────────────
@app.route('/ads/<int:biz_id>', methods=['GET','POST'])
@login_required
def manage_ads(biz_id):
    biz = db_fetchone(q("SELECT * FROM business WHERE id=? AND owner_id=?"), (biz_id,session['user_id']))
    if not biz: flash("Not found."); return redirect('/dashboard')
    if not biz['is_premium']:
        flash("Ads are a Pro Max feature. Upgrade to use them.")
        return redirect('/dashboard')

    # Count active ads this month (limit 2 per month)
    ads = db_fetchall(q("SELECT * FROM ads WHERE business_id=? ORDER BY created_at DESC"), (biz_id,))

    if request.method == 'POST':
        action = request.form.get('action','')

        if action == 'create':
            active_count = sum(1 for a in ads if a['active'])
            if active_count >= 2:
                flash("You already have 2 active ads. Delete one to add a new ad.")
                return redirect(f'/ads/{biz_id}')
            title  = request.form.get('title','').strip()[:100]
            body   = request.form.get('body','').strip()[:300]
            image  = request.files.get('image')
            img_ref= save_single_photo(image) if image and image.filename else None

            # AI generates ad copy if body is short
            client = get_anthropic_client()
            if client and len(body) < 20 and title:
                try:
                    msg = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=120,
                        messages=[{"role":"user","content":
                            f"Write a short, exciting 2-sentence ad announcement for a {biz['category']} business "
                            f"called '{biz['name']}'. The ad is about: '{title}'. "
                            f"Make it feel urgent and local (Uganda). Return ONLY the 2 sentences."}]
                    )
                    body = msg.content[0].text.strip()
                except: pass

            db_insert(q("INSERT INTO ads (business_id,title,body,image_ref,active) VALUES (?,?,?,?,1)"),
                      (biz_id,title,body,img_ref))
            db_execute(q("UPDATE business SET generated_html=NULL WHERE id=?"), (biz_id,))
            flash("✅ Ad created! Your website has been updated.")

        elif action == 'toggle':
            ad_id  = request.form.get('ad_id')
            ad     = db_fetchone(q("SELECT * FROM ads WHERE id=? AND business_id=?"), (ad_id,biz_id))
            if ad:
                db_execute(q("UPDATE ads SET active=? WHERE id=?"), (0 if ad['active'] else 1, ad_id))
                db_execute(q("UPDATE business SET generated_html=NULL WHERE id=?"), (biz_id,))
                flash("Ad updated.")

        elif action == 'delete':
            ad_id = request.form.get('ad_id')
            db_execute(q("DELETE FROM ads WHERE id=? AND business_id=?"), (ad_id,biz_id))
            db_execute(q("UPDATE business SET generated_html=NULL WHERE id=?"), (biz_id,))
            flash("Ad deleted.")

        return redirect(f'/ads/{biz_id}')

    return render_template('ads.html', business=biz_to_dict(biz), ads=[dict(a) for a in ads], current_user=get_current_user())

# ── DASHBOARD ─────────────────────────────────────────────────────────────────
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
    return render_template('dashboard.html', businesses=businesses, stats=stats,
                           current_user=get_current_user(), total_listings=len(businesses),
                           live_count=live_count, total_views=total_views)

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
@app.route('/upgrade/<int:biz_id>')
@login_required
def upgrade_page(biz_id):
    user = get_current_user()
    biz  = db_fetchone(q("SELECT * FROM business WHERE id=? AND owner_id=?"), (biz_id,user['id']))
    if not biz: flash("Not found."); return redirect('/dashboard')
    name = biz['name']
    basic_link  = f"https://wa.me/{ADMIN_WHATSAPP}?text=Hi+TrustedBiz!+I+want+to+upgrade+'{name}'+to+Basic+Plan+(UGX+7500/month).+My+name+is+{user['name']}."
    promax_link = f"https://wa.me/{ADMIN_WHATSAPP}?text=Hi+TrustedBiz!+I+want+to+upgrade+'{name}'+to+Pro+Max+Plan+(UGX+15000/month).+My+name+is+{user['name']}."
    return render_template('upgrade.html', business=biz_to_dict(biz),
                           basic_link=basic_link, promax_link=promax_link,
                           use_dgateway=False, current_user=user)

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
            if owner and owner.get('owner_id'):
                db_insert(q("INSERT INTO notifications (user_id,message) VALUES (?,?)"),
                          (owner['owner_id'], "✅ Your business is now live on TrustedBiz!"))
        elif action == 'reject':
            db_execute(q("UPDATE business SET status='rejected' WHERE id=?"), (biz_id,))
        elif action == 'verify':
            db_execute(q("UPDATE business SET verified=1 WHERE id=?"), (biz_id,))
        elif action == 'unverify':
            db_execute(q("UPDATE business SET verified=0 WHERE id=?"), (biz_id,))
        elif action == 'set_premium':
            db_execute(q("UPDATE business SET is_premium=1,last_payment_date=CURRENT_DATE,payment_months_late=0 WHERE id=?"), (biz_id,))
            owner = db_fetchone(q("SELECT owner_id FROM business WHERE id=?"), (biz_id,))
            if owner and owner.get('owner_id'):
                db_insert(q("INSERT INTO notifications (user_id,message) VALUES (?,?)"),
                          (owner['owner_id'], "⭐ You're now Premium! Your AI website is being generated."))
        elif action == 'remove_premium':
            db_execute(q("UPDATE business SET is_premium=0 WHERE id=?"), (biz_id,))
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
                from ai_generator import generate_business_website
                html = generate_business_website(bd)
                db_execute(q("UPDATE business SET generated_html=? WHERE id=?"), (html,biz_id))
                flash("Website regenerated!")
        elif action == 'delete':
            db_execute(q("DELETE FROM business WHERE id=?"), (biz_id,))

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
        'pending':          (db_fetchone(q("SELECT COUNT(*) as c FROM business WHERE status='pending'")) or {}).get('c',0),
        'total_reviews':    (db_fetchone(q("SELECT COUNT(*) as c FROM reviews")) or {}).get('c',0),
        'total_premium':    (db_fetchone(q("SELECT COUNT(*) as c FROM business WHERE is_premium=1")) or {}).get('c',0),
    }

    return render_template('admin.html',
        businesses=[biz_to_dict(b) for b in businesses],
        late_alert=[biz_to_dict(b) for b in (late_alert or [])],
        **stats)

# ── ADMIN DEMO ────────────────────────────────────────────────────────────────
@app.route('/admin/demo', methods=['GET','POST'])
@admin_required
def admin_demo():
    demo_html = None; form_data = {}
    if request.method == 'POST':
        form_data = {
            'name': request.form.get('name','').strip(),
            'category': request.form.get('category','').strip().lower(),
            'description': request.form.get('description','').strip(),
            'whatsapp': request.form.get('whatsapp','256700000000').strip(),
            'hours': request.form.get('hours','Mon–Sat 8am–7pm').strip(),
            'brand_color': request.form.get('brand_color','#2b7a78').strip(),
            'hero_price': request.form.get('hero_price','').strip() or None,
            'hero_price_label': request.form.get('hero_price_label','').strip(),
            'is_premium': True, 'slug':'demo', 'lat':0, 'lng':0, 'photos':'', 'branches':[], 'ads':[]
        }
        from ai_generator import generate_business_website
        demo_html = generate_business_website(form_data)
    return render_template('admin_demo.html', demo_html=demo_html, form_data=form_data, current_user=None)

# ── ADMIN PREVIEW ────────────────────────────────────────────────────────────
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
    from ai_generator import generate_business_website
    html = generate_business_website(bd)
    return html

# ── STATIC PAGES ──────────────────────────────────────────────────────────────
@app.route('/privacy')
def privacy():
    return render_template('privacy.html', current_user=get_current_user())

@app.route('/terms')
def terms():
    return render_template('terms.html', current_user=get_current_user())

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html', current_user=get_current_user()), 404

# ── RUN ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
