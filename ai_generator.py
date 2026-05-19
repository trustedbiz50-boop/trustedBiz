"""
ai_generator.py — TrustedBiz AI Website Generator
Add ANTHROPIC_API_KEY to environment variables and it works.
Without the key it uses a high-quality fallback.
"""
import os, re, json, threading

def _client():
    key = os.environ.get("ANTHROPIC_API_KEY","")
    if not key: return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=key)
    except ImportError:
        return None

def _hex_rgb(h):
    try:
        h = h.lstrip('#')
        if len(h)==3: h=''.join(c*2 for c in h)
        return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"
    except: return "43,122,120"

DIRECTIONS = {
    "cafe":"warm editorial — cream tones, cozy but stylish, coffee culture",
    "coffee":"warm editorial — cream tones, cozy but stylish",
    "restaurant":"bold food magazine — dark dramatic backgrounds, huge typography",
    "food":"bold food magazine — dark dramatic backgrounds",
    "salon":"luxury beauty editorial — gold accents, Vogue-level elegance",
    "beauty":"luxury beauty editorial — gold accents, elegant",
    "barber":"bold urban barbershop — dark industrial, strong geometric type",
    "mechanic":"bold industrial — dark steel, orange accent, raw power",
    "garage":"bold industrial — dark steel, orange accent",
    "plumber":"clean professional trades — navy, clear and trustworthy",
    "electrician":"clean trades — dark navy, electric yellow accent",
    "gym":"high energy athletic — dark background, neon accent, condensed type",
    "fitness":"high energy athletic — dark background, neon accent",
    "pharmacy":"clean medical — white and teal, professional calm",
    "clinic":"clean medical — soft blue, reassuring and clear",
    "hospital":"clean medical — white and blue, calm authority",
    "school":"educational — clean bright, inspiring blues",
    "hotel":"luxury hospitality — dark elegant, gold accents, cinematic",
    "lodge":"luxury hospitality — dark elegant, gold",
    "fashion":"high fashion editorial — bold type, striking contrast",
    "boutique":"high fashion — bold typography, asymmetric",
    "electronics":"sleek tech — dark, blue accent, futuristic",
    "phone":"sleek tech — dark, cyan accent",
    "supermarket":"fresh market — bright, colorful, welcoming",
    "hardware":"strong trades — bold orange, industrial, reliable",
}

def _direction(cat):
    if not cat: return "modern professional — clean bold typography, premium feel"
    c = cat.lower()
    for k,v in DIRECTIONS.items():
        if k in c: return v
    return "modern professional — clean bold typography, premium feel"

def generate_business_website(biz):
    try: biz = dict(biz)
    except: pass

    name        = str(biz.get("name") or "Business")
    category    = str(biz.get("category") or "")
    description = str(biz.get("description") or f"Professional {category} services in Uganda.")
    whatsapp    = str(biz.get("whatsapp") or "")
    hours       = str(biz.get("hours") or "Mon–Sat 8am–7pm")
    color       = str(biz.get("brand_color") or "#2b7a78")
    photos_raw  = str(biz.get("photos") or "")
    lat         = biz.get("lat") or 0
    lng         = biz.get("lng") or 0
    is_premium  = bool(biz.get("is_premium"))
    hero_price  = biz.get("hero_price")
    hero_label  = str(biz.get("hero_price_label") or "")
    branches    = biz.get("branches") or []
    ads         = biz.get("ads") or []

    photos   = [p.strip() for p in photos_raw.split(",") if p.strip()]
    wa_link  = f"https://wa.me/{whatsapp}?text=Hello%2C+I+found+{name.replace(' ','+')}+on+TrustedBiz%21"
    map_link = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}" if lat and lng else ""

    client = _client()
    if client:
        try:
            return _ai_generate(client, biz, name, category, description, whatsapp,
                                hours, color, photos, lat, lng, is_premium,
                                hero_price, hero_label, branches, ads, wa_link, map_link)
        except Exception as e:
            print(f"AI generate error: {e}")

    return _fallback(name, category, description, whatsapp, hours, color,
                     photos, lat, lng, hero_price, hero_label,
                     branches, ads, wa_link, map_link)



def generate_business_website_bg(biz, db_execute, biz_id):
    """Generate AI website in a true background thread — never blocks the caller.
    Always call this from inside a daemon thread (app.py fires a thread before
    calling this). The fallback is already saved in DB; if AI succeeds it
    overwrites the fallback with the better result."""
    try:
        html = generate_business_website(biz)
        if html and len(html) > 2000:
            try:
                db_execute(
                    "UPDATE business SET generated_html=? WHERE id=?",
                    (html, biz_id)
                )
                print(f"AI generation done for biz_id={biz_id}")
            except Exception as e:
                print(f"DB save error: {e}")
        else:
            print(f"AI generation returned too-short result for biz_id={biz_id} — fallback kept")
    except Exception as e:
        print(f"AI generation error for biz_id={biz_id}: {e}")


def _ai_generate(client, biz, name, category, description, whatsapp,
                 hours, color, photos, lat, lng, is_premium,
                 hero_price, hero_label, branches, ads, wa_link, map_link):

    direction = _direction(category)
    rgb       = _hex_rgb(color)

    photo_html = ""
    if photos:
        for i,p in enumerate(photos[:6]):
            src = p if p.startswith("http") else f"/static/images/{p}"
            photo_html += f'<div class="gal-item" onclick="openLb({i})"><img src="{src}" alt="Photo {i+1}" loading="lazy"></div>\n'

    branch_text = ""
    if branches:
        for br in branches:
            branch_text += f"- {br.get('name','Branch')}: {br.get('address','')}, {br.get('hours','')}\n"

    price_text = f"Starting price: {hero_label} from UGX {int(float(hero_price)):,}" if hero_price and hero_label else ""

    ads_text = ""
    if ads:
        for ad in ads:
            ads_text += f"AD: '{ad.get('title','')}' — {ad.get('body','')}\n"

    prompt = f"""You are a senior creative director at a $10,000/project web agency. Build a STUNNING, world-class business website for a Uganda business. This must look like Vibram, PureCare, OLLY, or CSWatch — not a template.

BUSINESS DATA:
Name: {name}
Category: {category}
Description: {description}
WhatsApp: {whatsapp}
Hours: {hours}
Brand Color: {color}
{price_text}
{f"BRANCHES:{chr(10)}{branch_text}" if branch_text else ""}
{f"PROMOTIONS:{chr(10)}{ads_text}" if ads_text else ""}

DESIGN DIRECTION: {direction}

CRITICAL DESIGN RULES — NEVER BREAK THESE:
1. HERO BACKGROUND: Use ONLY pure CSS — dark gradients, geometric SVG shapes, animated particles, or abstract CSS art. NEVER use <img> tags in the hero. No photos as backgrounds.
2. TYPOGRAPHY: Business name in the hero must be MASSIVE (clamp 60px to 120px), bold, full-width. Think billboard not heading.
3. MOBILE FIRST: Every section must look perfect on a 390px wide phone screen. No horizontal scroll. Buttons must be thumb-friendly (min 48px height).
4. BRAND COLOR: {color} must be used powerfully — not just as accents. Use it for backgrounds, gradients, glows.
5. ANIMATIONS: CSS keyframe animations only — fade-up on scroll, pulsing CTAs, hover transforms. No JS animation libraries.
6. HAMBURGER MENU: On mobile, nav links must collapse into a hamburger menu (pure CSS or minimal JS toggle).
7. GALLERY PHOTOS: Client photos go ONLY in the gallery section using these exact img tags — never in hero or backgrounds:
{photo_html if photo_html else "   No photos provided — use CSS gradient placeholder cards with category-relevant icons"}
8. YEAR: Footer copyright must say 2026, NOT 2024 or 2025.
9. FOOTER LINK: "Powered by TrustedBiz" must link to https://trustedbiz.co.ug

REQUIRED SECTIONS IN ORDER:
1. NAV — sticky, logo left, hamburger on mobile, WhatsApp CTA button right
2. HERO — fullscreen 100vh, massive business name, powerful tagline from description, two CTAs: WhatsApp + {f"Get Directions" if map_link else "Learn More"}
3. ABOUT — split layout on desktop, stacked on mobile. Description + 4 trust badges (hours, location, verified, WhatsApp)
4. SERVICES — grid of 4-6 cards. Infer real services from category+description. Each card has icon, title, description.
5. GALLERY — masonry-style photo grid. {f"Use these {len(photos)} photos: show all" if photos else "Use 3 CSS gradient placeholder cards"}
6. {f"PRICING — hero price card: {hero_label} from UGX {int(float(hero_price)):,} with WhatsApp CTA" if hero_price else "WHY CHOOSE US — 3 compelling reasons with icons"}
{f"7. PROMOTIONS — styled promo cards for: {ads_text}" if ads_text else ""}
{f"{'8' if ads_text else '7'}. BRANCHES — location cards for: {branch_text}" if branch_text else ""}
7. CONTACT — large WhatsApp CTA button, hours card, {f"embedded map directions button linking to {map_link}" if map_link else "call to action"}
8. FOOTER — business name, tagline, hours, WhatsApp, © 2026 {name}, Powered by TrustedBiz (link to https://trustedbiz.co.ug)

WHATSAPP BUTTON STYLE — use this exact green everywhere:
background: #25D366; color: white; padding: 16px 32px; border-radius: 50px; font-weight: 700; display: inline-flex; align-items: center; gap: 10px;
WhatsApp link: {wa_link}
{f"Directions link: {map_link}" if map_link else ""}

TECHNICAL REQUIREMENTS:
- Single HTML file. All CSS in <style>. All JS in <script> before </body>.
- No external JS libraries (no jQuery, no GSAP). Google Fonts OK.
- CSS custom properties for colors: --primary, --primary-rgb, --dark, --light
- Smooth scroll behavior
- Intersection Observer for scroll animations
- Touch-friendly on mobile

OUTPUT: Return ONLY raw HTML starting with <!DOCTYPE html>. No markdown. No backticks. No explanation."""

    messages = [{"role": "user", "content": prompt}]
    full_text = ""
    max_rounds = 4  # safety cap on continuation calls

    for round_num in range(max_rounds):
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=9000,
            messages=messages
        )
        chunk = msg.content[0].text if msg.content else ""
        full_text += chunk

        # If the model finished naturally, we're done
        if msg.stop_reason != "max_tokens":
            break

        # Model was cut off — ask it to continue exactly where it stopped
        print(f"AI generation hit max_tokens on round {round_num + 1}, continuing...")
        messages.append({"role": "assistant", "content": chunk})
        messages.append({"role": "user", "content": "Continue exactly from where you stopped. Output only the remaining HTML, no preamble."})
    else:
        print("Warning: AI generation hit max continuation rounds — HTML may be incomplete.")

    raw = full_text
    raw = re.sub(r'^```html\s*', '', raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r'^```\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw.strip())

    # Ensure the HTML is properly closed
    if raw and '</html>' not in raw[-500:]:
        raw = raw.rstrip() + '\n</body>\n</html>'

    return raw.strip()


def _fallback(name, category, description, whatsapp, hours, color,
              photos, lat, lng, hero_price, hero_label,
              branches, ads, wa_link, map_link):
    """High-quality fallback website — no API needed."""
    rgb = _hex_rgb(color)

    gallery_html = ""
    if photos:
        items = ""
        for i,p in enumerate(photos[:6]):
            src = p if p.startswith("http") else f"/static/images/{p}"
            items += f'<div class="gi" onclick="lb({i})"><img src="{src}" alt="" loading="lazy"></div>'
        gallery_html = f'<section class="sec sec-alt" id="gallery"><div class="wrap"><p class="sec-label">Gallery</p><h2 class="sec-h">Our Work</h2><div class="gal">{items}</div></div></section>'
        photos_js = "var P=[" + ",".join([f'"{p if p.startswith("http") else "/static/images/"+p}"' for p in photos]) + "];"
    else:
        photos_js = "var P=[];"

    price_html = ""
    if hero_price and hero_label:
        price_html = f'<section class="sec" id="pricing"><div class="wrap" style="text-align:center"><p class="sec-label">Pricing</p><h2 class="sec-h">Starting Price</h2><div style="font-size:52px;font-weight:900;color:{color};margin:20px 0 6px">{int(float(hero_price)):,}</div><p style="font-size:18px;color:#6b7280;margin-bottom:24px">UGX — {hero_label}</p><a href="{wa_link}" target="_blank" class="wa-btn">Ask About Pricing</a></div></section>'

    branches_html = ""
    if branches:
        cards = "".join([f'<div class="branch-card"><h4>{b.get("name","Branch")}</h4><p>{b.get("address","")}</p><p>⏰ {b.get("hours","")}</p></div>' for b in branches])
        branches_html = f'<section class="sec sec-alt"><div class="wrap"><p class="sec-label">Locations</p><h2 class="sec-h">Our Branches</h2><div class="branches">{cards}</div></div></section>'

    ads_html = ""
    if ads:
        for ad in ads:
            img_html = ""
            if ad.get("image_ref"):
                src = ad["image_ref"] if ad["image_ref"].startswith("http") else f'/static/images/{ad["image_ref"]}'
                img_html = f'<img src="{src}" alt="" style="width:100%;max-height:300px;object-fit:cover;border-radius:12px;margin-bottom:16px;">'
            ads_html += f'<div class="ad-block">{img_html}<h3>{ad.get("title","")}</h3><p>{ad.get("body","")}</p><a href="{wa_link}" target="_blank" class="wa-btn" style="margin-top:16px;display:inline-flex;">Learn More</a></div>'
        ads_html = f'<section class="sec" id="announcements"><div class="wrap"><p class="sec-label">Announcements</p><h2 class="sec-h">Latest Updates</h2><div class="ads-grid">{ads_html}</div></div></section>'

    map_html = ""
    if lat and lng:
        map_html = f"""
<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
<div id="bmap" style="width:100%;height:300px;border-radius:12px;margin-top:24px;"></div>
<script>
var bm=L.map('bmap').setView([{lat},{lng}],15);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:19}}).addTo(bm);
L.marker([{lat},{lng}]).addTo(bm).bindPopup('<strong>{name}</strong>').openPopup();
</script>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name} — {category.title()} | TrustedBiz</title>
<meta name="description" content="{description[:155]}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
:root{{--c:{color};--rgb:{rgb};--dark:#0f0f0f;--light:#f8f8f6;}}
html{{scroll-behavior:smooth;}}
body{{font-family:'DM Sans',sans-serif;background:var(--light);color:#1a1a1a;overflow-x:hidden;}}
@keyframes fadeUp{{from{{opacity:0;transform:translateY(24px)}}to{{opacity:1;transform:translateY(0)}}}}
.reveal{{opacity:0;transform:translateY(24px);transition:opacity .7s,transform .7s;}}
.reveal.in{{opacity:1;transform:none;}}
nav{{position:fixed;top:0;left:0;right:0;z-index:100;height:62px;display:flex;align-items:center;justify-content:space-between;padding:0 36px;transition:background .4s;}}
nav.solid{{background:rgba(15,15,15,.96);border-bottom:1px solid rgba(255,255,255,.06);}}
.nav-brand{{font-family:'Syne',sans-serif;font-weight:800;font-size:17px;color:white;text-decoration:none;}}
.nav-brand em{{font-style:normal;color:var(--c);}}
.nav-wa{{background:var(--c);color:white;padding:8px 18px;border-radius:8px;font-weight:700;font-size:13px;text-decoration:none;transition:filter .2s;}}
.nav-wa:hover{{filter:brightness(1.1);}}
.hero{{min-height:100vh;background:var(--dark);display:flex;align-items:center;justify-content:center;text-align:center;padding:100px 24px 80px;position:relative;overflow:hidden;}}
.hero-bg{{position:absolute;inset:0;background:radial-gradient(ellipse 70% 60% at 50% 50%,rgba(var(--rgb),.18) 0%,transparent 65%);}}
.hero-grid{{position:absolute;inset:0;opacity:.03;background-image:linear-gradient(rgba(255,255,255,.5) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.5) 1px,transparent 1px);background-size:50px 50px;}}
.hero-inner{{position:relative;z-index:2;max-width:820px;animation:fadeUp .9s ease forwards;}}
.eyebrow{{display:inline-flex;align-items:center;gap:8px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);color:rgba(255,255,255,.75);font-size:12px;font-weight:600;letter-spacing:2px;text-transform:uppercase;padding:7px 18px;border-radius:100px;margin-bottom:28px;}}
.dot{{width:6px;height:6px;border-radius:50%;background:var(--c);animation:pulse 2s infinite;}}
@keyframes pulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.5);opacity:.5}}}}
.hero h1{{font-family:'Syne',sans-serif;font-size:clamp(44px,8vw,96px);font-weight:800;color:white;line-height:.95;letter-spacing:-2px;margin-bottom:24px;}}
.hero h1 .ac{{color:var(--c);}}
.hero-desc{{font-size:18px;color:rgba(255,255,255,.6);max-width:540px;margin:0 auto 40px;line-height:1.75;font-weight:300;}}
.hero-btns{{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;}}
.wa-btn{{display:inline-flex;align-items:center;gap:9px;background:#22c55e;color:white;padding:15px 30px;border-radius:10px;font-size:15px;font-weight:700;text-decoration:none;transition:all .25s;}}
.wa-btn:hover{{background:#16a34a;transform:translateY(-2px);box-shadow:0 12px 30px rgba(34,197,94,.3);}}
.dir-btn{{display:inline-flex;align-items:center;gap:9px;border:2px solid rgba(255,255,255,.2);color:white;padding:15px 26px;border-radius:10px;font-size:15px;font-weight:600;text-decoration:none;transition:all .25s;}}
.dir-btn:hover{{border-color:var(--c);background:rgba(255,255,255,.05);}}
.sec{{padding:88px 24px;}}
.sec-alt{{background:white;}}
.wrap{{max-width:1000px;margin:0 auto;}}
.sec-label{{font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:var(--c);margin-bottom:12px;}}
.sec-h{{font-family:'Syne',sans-serif;font-size:clamp(30px,4vw,52px);font-weight:800;color:#1a1a1a;line-height:1.05;letter-spacing:-1px;margin-bottom:20px;}}
.sec-sub{{font-size:16px;color:#6b7280;line-height:1.75;max-width:580px;margin-bottom:48px;}}
.info-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:40px;}}
.info-card{{background:#f8f8f6;border-radius:14px;padding:28px;border:1.5px solid rgba(0,0,0,.06);transition:border-color .2s,transform .2s;}}
.info-card:hover{{border-color:var(--c);transform:translateY(-3px);}}
.ic-icon{{font-size:28px;margin-bottom:14px;}}
.info-card h3{{font-family:'Syne',sans-serif;font-size:18px;font-weight:700;color:#1a1a1a;margin-bottom:8px;}}
.info-card p{{font-size:14px;color:#6b7280;line-height:1.6;}}
.services-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;margin-top:40px;}}
.svc-card{{background:#f8f8f6;border-radius:12px;padding:24px;border:1.5px solid rgba(0,0,0,.06);transition:all .2s;position:relative;overflow:hidden;}}
.svc-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--c);transform:scaleX(0);transform-origin:left;transition:transform .3s;}}
.svc-card:hover{{border-color:var(--c);transform:translateY(-3px);}}.svc-card:hover::before{{transform:scaleX(1);}}
.svc-icon{{font-size:28px;margin-bottom:12px;}}
.svc-card h3{{font-family:'Syne',sans-serif;font-size:16px;font-weight:700;color:#1a1a1a;margin-bottom:6px;}}
.svc-card p{{font-size:13px;color:#6b7280;line-height:1.5;}}
.gal{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin-top:40px;}}
.gi{{aspect-ratio:4/3;border-radius:10px;overflow:hidden;cursor:pointer;}}
.gi img{{width:100%;height:100%;object-fit:cover;transition:transform .4s;display:block;}}
.gi:hover img{{transform:scale(1.06);}}
.contact-grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start;margin-top:40px;}}
.contact-detail{{display:flex;align-items:center;gap:14px;padding:16px;background:#f8f8f6;border-radius:12px;margin-bottom:12px;}}
.cd-icon{{width:40px;height:40px;background:rgba(var(--rgb),.12);border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;}}
.cd-label{{font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px;}}
.cd-val{{font-size:14px;font-weight:600;color:#1a1a1a;}}
.branches{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;margin-top:40px;}}
.branch-card{{background:#f8f8f6;border-radius:12px;padding:22px;border:1.5px solid rgba(0,0,0,.06);}}
.branch-card h4{{font-family:'Syne',sans-serif;font-size:16px;font-weight:700;margin-bottom:8px;}}
.branch-card p{{font-size:13px;color:#6b7280;margin-bottom:4px;}}
.ads-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px;margin-top:40px;}}
.ad-block{{background:linear-gradient(135deg,rgba(var(--rgb),.06),rgba(var(--rgb),.02));border:1.5px solid rgba(var(--rgb),.2);border-radius:14px;padding:24px;}}
.ad-block h3{{font-family:'Syne',sans-serif;font-size:20px;font-weight:700;color:#1a1a1a;margin-bottom:8px;}}
.ad-block p{{font-size:14px;color:#6b7280;line-height:1.6;}}
.lb{{position:fixed;inset:0;background:rgba(0,0,0,.94);z-index:9000;display:none;flex-direction:column;align-items:center;justify-content:center;}}
.lb.open{{display:flex;}}
.lb-img{{max-width:90vw;max-height:78vh;border-radius:8px;object-fit:contain;}}
.lb-close{{position:absolute;top:18px;right:22px;color:white;font-size:28px;cursor:pointer;background:rgba(255,255,255,.1);border:none;padding:8px 14px;border-radius:8px;}}
.lb-prev,.lb-next{{position:absolute;top:50%;transform:translateY(-50%);color:white;font-size:34px;cursor:pointer;background:rgba(255,255,255,.1);border:none;padding:10px 14px;border-radius:8px;transition:background .2s;}}
.lb-prev{{left:10px;}}.lb-next{{right:10px;}}
.lb-prev:hover,.lb-next:hover{{background:rgba(255,255,255,.22);}}
footer{{background:var(--dark);padding:36px 24px;text-align:center;color:rgba(255,255,255,.35);font-size:13px;}}
footer a{{color:var(--c);text-decoration:none;font-weight:600;}}
@media(max-width:700px){{
  nav{{padding:0 16px;}}
  .hero{{padding:90px 16px 70px;}}
  .info-grid,.contact-grid{{grid-template-columns:1fr;}}
  .sec{{padding:60px 16px;}}
}}
</style>
</head>
<body>
<div class="lb" id="lb">
  <button class="lb-close" onclick="lbc()">✕</button>
  <button class="lb-prev" onclick="lbn(-1)">‹</button>
  <img class="lb-img" id="lbi" src="" alt="">
  <button class="lb-next" onclick="lbn(1)">›</button>
</div>
<nav id="nav">
  <a href="/" class="nav-brand">Trusted<em>Biz</em></a>
  <a href="{wa_link}" target="_blank" class="nav-wa">WhatsApp Us</a>
</nav>
<section class="hero">
  <div class="hero-bg"></div><div class="hero-grid"></div>
  <div class="hero-inner">
    <div class="eyebrow"><span class="dot"></span>{category.upper()}</div>
    <h1><span class="ac">{name}</span></h1>
    <p class="hero-desc">{description[:200]}</p>
    <div class="hero-btns">
      <a href="{wa_link}" target="_blank" class="wa-btn">💬 Chat on WhatsApp</a>
      {f'<a href="{map_link}" target="_blank" class="dir-btn">📍 Get Directions</a>' if map_link else ""}
    </div>
  </div>
</section>
<section class="sec sec-alt" id="about">
  <div class="wrap">
    <p class="sec-label">About Us</p>
    <h2 class="sec-h reveal">Who We Are</h2>
    <p class="sec-sub reveal">{description}</p>
    <div class="info-grid">
      <div class="info-card reveal"><div class="ic-icon">⏰</div><h3>Opening Hours</h3><p>{hours}</p></div>
      <div class="info-card reveal"><div class="ic-icon">📱</div><h3>Contact Us</h3><p>+{whatsapp}<br>Message anytime on WhatsApp</p></div>
      <div class="info-card reveal"><div class="ic-icon">✅</div><h3>Verified Business</h3><p>Listed and verified on TrustedBiz Uganda</p></div>
      <div class="info-card reveal"><div class="ic-icon">📍</div><h3>Location</h3><p>{"Get directions on Google Maps" if map_link else "Contact us for directions"}</p></div>
    </div>
  </div>
</section>
<section class="sec" id="services">
  <div class="wrap">
    <p class="sec-label">What We Offer</p>
    <h2 class="sec-h reveal">Our Services</h2>
    <div class="services-grid">
      <div class="svc-card reveal"><div class="svc-icon">⭐</div><h3>Professional Service</h3><p>High-quality {category} services delivered by experts.</p></div>
      <div class="svc-card reveal"><div class="svc-icon">🚀</div><h3>Fast Turnaround</h3><p>We value your time and deliver results quickly.</p></div>
      <div class="svc-card reveal"><div class="svc-icon">💬</div><h3>WhatsApp Support</h3><p>Contact us anytime. We respond fast.</p></div>
      <div class="svc-card reveal"><div class="svc-icon">🛡️</div><h3>Trusted Quality</h3><p>Verified on TrustedBiz. Real reviews from real customers.</p></div>
    </div>
  </div>
</section>
{gallery_html}
{price_html}
{ads_html}
{branches_html}
<section class="sec sec-alt" id="contact">
  <div class="wrap">
    <p class="sec-label">Get In Touch</p>
    <h2 class="sec-h reveal">Contact Us</h2>
    <div class="contact-grid">
      <div>
        <div class="contact-detail"><div class="cd-icon">💬</div><div><div class="cd-label">WhatsApp</div><div class="cd-val">+{whatsapp}</div></div></div>
        <div class="contact-detail"><div class="cd-icon">⏰</div><div><div class="cd-label">Hours</div><div class="cd-val">{hours}</div></div></div>
        {f'<div class="contact-detail"><div class="cd-icon">📍</div><div><div class="cd-label">Directions</div><div class="cd-val">Get directions on Google Maps</div></div></div>' if map_link else ""}
      </div>
      <div style="text-align:center">
        <a href="{wa_link}" target="_blank" class="wa-btn" style="display:inline-flex;margin-bottom:14px;">💬 Chat on WhatsApp</a>
        {f'<br><a href="{map_link}" target="_blank" class="dir-btn" style="display:inline-flex;margin-top:8px;">📍 Get Directions</a>' if map_link else ""}
        {map_html}
      </div>
    </div>
  </div>
</section>
<footer>
  <p style="margin-bottom:6px;">© 2026 {name}. All rights reserved.</p>
  <p>Powered by <a href="https://trustedbiz.co.ug" target="_blank">TrustedBiz</a> — Uganda's Trusted Business Directory</p>
</footer>
<script>
{photos_js}
var li=0;
function lb(i){{li=i;document.getElementById('lbi').src=P[i];document.getElementById('lb').classList.add('open');document.body.style.overflow='hidden';}}
function lbc(){{document.getElementById('lb').classList.remove('open');document.body.style.overflow='';}}
function lbn(d){{li=(li+d+P.length)%P.length;document.getElementById('lbi').src=P[li];}}
document.getElementById('lb').addEventListener('click',function(e){{if(e.target===this)lbc();}});
document.addEventListener('keydown',function(e){{if(document.getElementById('lb').classList.contains('open')){{if(e.key==='ArrowRight')lbn(1);if(e.key==='ArrowLeft')lbn(-1);if(e.key==='Escape')lbc();}}}});
window.addEventListener('scroll',function(){{document.getElementById('nav').classList.toggle('solid',window.scrollY>60);}});
var obs=new IntersectionObserver(function(e){{e.forEach(function(x){{if(x.isIntersecting)x.target.classList.add('in');}});}},{{threshold:.12}});
document.querySelectorAll('.reveal').forEach(function(el){{obs.observe(el);}});
</script>
</body>
</html>"""
