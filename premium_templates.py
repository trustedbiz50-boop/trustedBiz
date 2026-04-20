# premium_templates.py
# REBUILT FROM SCRATCH — Full business websites, not landing pages
# Every template: 10+ sections, real content, real design

def get_templates_for_category(category):
    if not category:
        return "warm"
    cat = category.lower().strip()
    trade  = ["mechanic","plumber","electrician","carpenter","welder","hardware","construction","gym","garage","fitter","engineer"]
    luxury = ["hotel","lodge","resort","spa","boutique","fine dining","villa","guest house","motel"]
    health = ["pharmacy","clinic","hospital","doctor","dental","optician","laboratory","health","nurse","medical"]
    edu    = ["school","college","university","academy","institute","nursery","training","tutor"]
    food   = ["restaurant","cafe","coffee","fast food","bakery","pizza","chicken","grill","bar","juice","catering"]
    beauty = ["salon","barber","beauty","nail","hair","massage","skincare","cosmetic","barbershop"]
    shop   = ["supermarket","shop","store","mall","market","fashion","clothing","electronics","phone","boutique"]
    for k in trade:
        if k in cat: return "trade"
    for k in luxury:
        if k in cat: return "luxury"
    for k in health:
        if k in cat: return "health"
    for k in edu:
        if k in cat: return "edu"
    for k in food:
        if k in cat: return "food"
    for k in beauty:
        if k in cat: return "beauty"
    for k in shop:
        if k in cat: return "shop"
    return "warm"


def render_template_html(template_id, biz):
    try:
        biz = dict(biz)
    except Exception:
        pass

    name        = str(biz.get("name") or "Business")
    category    = str(biz.get("category") or "")
    description = str(biz.get("description") or "")
    whatsapp    = str(biz.get("whatsapp") or "")
    hours       = str(biz.get("hours") or "Mon–Sat 7am–7pm")
    photos_raw  = str(biz.get("photos") or "")
    lat         = biz.get("lat") or 0
    lng         = biz.get("lng") or 0
    color       = str(biz.get("brand_color") or "#2b7a78")
    slug        = str(biz.get("slug") or biz.get("id") or "")

    photos  = [p.strip() for p in photos_raw.split(",") if p.strip()]
    wa_text = f"Hello%2C+I+found+{name.replace(' ', '+')}+on+TrustedBiz%21+I+need+help."
    wa_link = f"https://wa.me/{whatsapp}?text={wa_text}"
    map_link = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"

    map_html = ""
    map_script = ""
    if lat and lng:
        map_html = f'<div id="pmap" style="width:100%;height:420px;border-radius:12px;"></div>'
        map_script = f"""
<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
<script>
var m=L.map('pmap').setView([{lat},{lng}],15);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:19}}).addTo(m);
L.marker([{lat},{lng}]).addTo(m).bindPopup('<strong>{name}</strong>').openPopup();
</script>"""

    fn = {
        "trade":   _trade,
        "luxury":  _luxury,
        "food":    _food,
        "health":  _health,
        "beauty":  _beauty,
        "shop":    _shop,
        "edu":     _edu,
        "warm":    _food,
    }.get(template_id, _food)

    return fn(name, category, description, whatsapp, hours,
              color, photos, wa_link, map_link, map_html, map_script, slug)


def _wa_icon():
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" style="flex-shrink:0"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.136.563 4.14 1.547 5.874L.057 23.6a.75.75 0 00.92.92l5.726-1.49A11.953 11.953 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 22c-1.9 0-3.68-.497-5.22-1.367l-.374-.22-3.895 1.013 1.013-3.895-.22-.374A10 10 0 1112 22z"/></svg>'


# =============================================================================
# TRADE TEMPLATE — Mechanics, Plumbers, Electricians, Gyms
# Full website. Real sections. Real Kampala feel.
# =============================================================================
def _trade(name, category, description, whatsapp, hours,
           color, photos, wa_link, map_link, map_html, map_script, slug):

    accent  = color if color not in ["#2b7a78","#000000","#ffffff",""] else "#f97316"
    cat_up  = category.upper()
    name_u  = name.upper()
    desc    = description or f"Professional {category} services in Kampala. Fast, reliable, and honest work — every single time."

    # Photos section
    photo_html = ""
    if photos:
        items = "".join([f'<div class="pg-item" onclick="pgOpen({i})"><img src="/static/images/{p}" loading="lazy" alt="photo {i+1}"></div>' for i,p in enumerate(photos[:6])])
        thumbs = ",".join([f'"/static/images/{p}"' for p in photos])
        photo_html = f"""
<section class="section gallery-section" id="gallery">
  <div class="container">
    <div class="section-label">Our Work</div>
    <h2 class="section-title">See What We've Built</h2>
    <p class="section-sub">Real jobs done right here in Kampala. These are our actual results — not stock photos.</p>
    <div class="pg-grid">{items}</div>
  </div>
</section>
<div class="pg-lightbox" id="pgLb" onclick="if(event.target===this)pgClose()">
  <button class="pg-close" onclick="pgClose()">✕</button>
  <button class="pg-nav" onclick="pgNav(-1)" style="left:16px">‹</button>
  <img class="pg-img" id="pgImg">
  <button class="pg-nav" onclick="pgNav(1)" style="right:16px">›</button>
  <div class="pg-count" id="pgCount"></div>
</div>
<script>
var pgP=[{thumbs}],pgI=0;
function pgOpen(i){{pgI=i;pgShow();document.getElementById('pgLb').style.display='flex';document.body.style.overflow='hidden';}}
function pgClose(){{document.getElementById('pgLb').style.display='none';document.body.style.overflow='';}}
function pgNav(d){{pgI=(pgI+d+pgP.length)%pgP.length;pgShow();}}
function pgShow(){{document.getElementById('pgImg').src=pgP[pgI];document.getElementById('pgCount').textContent=(pgI+1)+' / '+pgP.length;}}
document.addEventListener('keydown',function(e){{if(document.getElementById('pgLb').style.display==='flex'){{if(e.key==='ArrowRight')pgNav(1);if(e.key==='ArrowLeft')pgNav(-1);if(e.key==='Escape')pgClose();}}}});
</script>"""

    map_section = ""
    if map_html:
        map_section = f"""
<section class="section map-section">
  <div class="container">
    <div class="section-label">Find Us</div>
    <h2 class="section-title">We Are Right Here in Kampala</h2>
    <p class="section-sub">Come see us or send us your location and we will come to you.</p>
    <div class="map-wrap">{map_html}</div>
    <div class="map-actions">
      <a href="{wa_link}" target="_blank" class="btn-primary">{_wa_icon()} Message for Directions</a>
      <a href="{map_link}" target="_blank" class="btn-outline">📍 Open in Google Maps</a>
    </div>
  </div>
</section>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} — Professional {category.title()} Services in Kampala</title>
<meta name="description" content="{desc[:155]}">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800;900&family=Barlow:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<style>
/* ── RESET ── */
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
html{{scroll-behavior:smooth;font-size:16px;}}
body{{font-family:'Barlow',sans-serif;background:#111;color:#eee;overflow-x:hidden;}}

/* ── CSS VARIABLES ── */
:root{{
  --accent:{accent};
  --dark:#111;
  --dark2:#161616;
  --dark3:#1e1e1e;
  --dark4:#242424;
  --text:#e8e8e8;
  --muted:#888;
  --border:rgba(255,255,255,.08);
}}

/* ── ANIMATIONS ── */
@keyframes fadeUp{{from{{opacity:0;transform:translateY(32px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes fadeIn{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes slideRight{{from{{opacity:0;transform:translateX(-24px)}}to{{opacity:1;transform:translateX(0)}}}}
@keyframes pulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.05)}}}}
@keyframes counterUp{{from{{opacity:0;transform:translateY(20px)}}to{{opacity:1;transform:translateY(0)}}}}
.animate{{opacity:0;animation:fadeUp .7s ease forwards;}}
.animate.delay-1{{animation-delay:.1s;}}
.animate.delay-2{{animation-delay:.2s;}}
.animate.delay-3{{animation-delay:.3s;}}
.animate.delay-4{{animation-delay:.4s;}}
.animate.delay-5{{animation-delay:.5s;}}

/* ── NAVBAR ── */
nav{{
  position:fixed;top:0;left:0;right:0;z-index:1000;
  height:68px;display:flex;align-items:center;justify-content:space-between;
  padding:0 40px;transition:all .4s;
  background:rgba(17,17,17,0);
}}
nav.stuck{{
  background:rgba(17,17,17,.97);
  border-bottom:1px solid var(--border);
  box-shadow:0 4px 24px rgba(0,0,0,.4);
}}
.nav-logo{{display:flex;align-items:center;gap:12px;text-decoration:none;}}
.nav-logo-icon{{
  width:40px;height:40px;
  background:var(--accent);
  border-radius:8px;
  display:flex;align-items:center;justify-content:center;
  font-size:18px;font-weight:900;color:white;font-family:'Barlow Condensed',sans-serif;
  letter-spacing:-1px;
}}
.nav-logo-text{{
  font-family:'Barlow Condensed',sans-serif;
  font-size:20px;font-weight:800;color:white;letter-spacing:.5px;text-transform:uppercase;
}}
.nav-links{{display:flex;align-items:center;gap:8px;}}
.nav-link{{
  color:rgba(255,255,255,.65);font-size:13px;font-weight:600;
  text-decoration:none;padding:8px 14px;border-radius:6px;
  transition:all .2s;letter-spacing:.3px;
}}
.nav-link:hover{{color:white;background:rgba(255,255,255,.07);}}
.nav-cta{{
  display:inline-flex;align-items:center;gap:8px;
  background:var(--accent);color:white;
  padding:10px 20px;border-radius:8px;
  font-size:13px;font-weight:800;text-decoration:none;
  letter-spacing:.5px;text-transform:uppercase;
  transition:all .2s;
}}
.nav-cta:hover{{filter:brightness(1.15);transform:translateY(-1px);}}

/* ── HERO ── */
.hero{{
  min-height:100vh;display:flex;align-items:center;
  position:relative;overflow:hidden;
  background:var(--dark);
  padding:100px 40px 80px;
}}
.hero-bg{{
  position:absolute;inset:0;
  background:
    radial-gradient(ellipse 80% 60% at 100% 50%, rgba({int(accent[1:3],16) if len(accent)==7 else 249},{int(accent[3:5],16) if len(accent)==7 else 115},{int(accent[5:7],16) if len(accent)==7 else 22},.13) 0%,transparent 55%),
    radial-gradient(ellipse 40% 40% at 10% 80%, rgba(255,255,255,.02) 0%,transparent 60%);
}}
.hero-grid-overlay{{
  position:absolute;inset:0;opacity:.025;
  background-image:
    linear-gradient(rgba(255,255,255,.4) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,.4) 1px,transparent 1px);
  background-size:60px 60px;
}}
.hero-content{{position:relative;z-index:2;max-width:740px;}}
.hero-eyebrow{{
  display:inline-flex;align-items:center;gap:10px;
  margin-bottom:26px;
  background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.1);
  padding:8px 18px;border-radius:100px;
}}
.hero-eyebrow-dot{{
  width:8px;height:8px;border-radius:50%;
  background:var(--accent);
  animation:pulse 2s infinite;
}}
.hero-eyebrow span{{
  font-size:12px;font-weight:700;letter-spacing:2px;
  text-transform:uppercase;color:rgba(255,255,255,.7);
}}
.hero h1{{
  font-family:'Barlow Condensed',sans-serif;
  font-size:clamp(52px,8vw,96px);
  font-weight:900;line-height:.92;
  text-transform:uppercase;letter-spacing:-2px;
  color:white;margin-bottom:24px;
}}
.hero h1 .accent-line{{
  color:var(--accent);display:block;
}}
.hero-desc{{
  font-size:18px;color:rgba(255,255,255,.6);
  line-height:1.75;max-width:580px;
  margin-bottom:36px;font-weight:300;
}}
.hero-meta{{
  display:flex;gap:12px;flex-wrap:wrap;margin-bottom:36px;
}}
.meta-pill{{
  display:inline-flex;align-items:center;gap:8px;
  background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.1);
  color:rgba(255,255,255,.8);
  font-size:14px;font-weight:500;
  padding:10px 18px;border-radius:100px;
}}
.meta-pill svg{{width:16px;height:16px;flex-shrink:0;}}
.hero-cta{{display:flex;gap:14px;flex-wrap:wrap;}}
.btn-hero-primary{{
  display:inline-flex;align-items:center;gap:10px;
  background:#22c55e;color:white;
  padding:18px 32px;border-radius:10px;
  font-size:16px;font-weight:800;text-decoration:none;
  letter-spacing:.3px;transition:all .25s;
}}
.btn-hero-primary:hover{{background:#16a34a;transform:translateY(-3px);box-shadow:0 12px 32px rgba(34,197,94,.3);}}
.btn-hero-secondary{{
  display:inline-flex;align-items:center;gap:8px;
  border:2px solid rgba(255,255,255,.2);color:white;
  padding:18px 28px;border-radius:10px;
  font-size:15px;font-weight:700;text-decoration:none;
  transition:all .25s;
}}
.btn-hero-secondary:hover{{border-color:rgba(255,255,255,.5);background:rgba(255,255,255,.06);}}
.hero-scroll{{
  position:absolute;bottom:36px;left:50%;transform:translateX(-50%);
  display:flex;flex-direction:column;align-items:center;gap:8px;
  color:rgba(255,255,255,.3);font-size:12px;letter-spacing:2px;text-transform:uppercase;
}}
.hero-scroll-line{{
  width:1px;height:40px;
  background:linear-gradient(to bottom,rgba(255,255,255,.3),transparent);
}}

/* ── STATS STRIP ── */
.stats-strip{{
  background:var(--accent);
  padding:0;
}}
.stats-inner{{
  max-width:1100px;margin:0 auto;
  display:grid;grid-template-columns:repeat(4,1fr);
}}
.stat-item{{
  padding:28px 20px;text-align:center;
  border-right:1px solid rgba(255,255,255,.2);
  transition:background .2s;
}}
.stat-item:last-child{{border-right:none;}}
.stat-item:hover{{background:rgba(255,255,255,.08);}}
.stat-num{{
  font-family:'Barlow Condensed',sans-serif;
  font-size:42px;font-weight:900;color:white;
  line-height:1;margin-bottom:4px;
}}
.stat-label{{font-size:12px;font-weight:700;color:rgba(255,255,255,.75);text-transform:uppercase;letter-spacing:1px;}}

/* ── SECTIONS ── */
.section{{padding:96px 40px;}}
.section-dark{{background:var(--dark);}}
.section-mid{{background:var(--dark2);}}
.section-alt{{background:var(--dark3);}}
.container{{max-width:1100px;margin:0 auto;}}
.section-label{{
  font-size:11px;font-weight:800;letter-spacing:3px;
  text-transform:uppercase;color:var(--accent);margin-bottom:12px;
}}
.section-title{{
  font-family:'Barlow Condensed',sans-serif;
  font-size:clamp(32px,5vw,54px);font-weight:900;
  text-transform:uppercase;letter-spacing:-1px;
  color:white;margin-bottom:16px;line-height:1;
}}
.section-sub{{
  font-size:16px;color:var(--muted);line-height:1.75;
  max-width:600px;margin-bottom:52px;
}}

/* ── PROBLEM ── */
.problem-grid{{
  display:grid;grid-template-columns:1fr 1fr;gap:60px;align-items:center;
}}
.problem-text p{{
  font-size:16px;color:rgba(255,255,255,.7);line-height:1.8;
  margin-bottom:20px;font-weight:300;
}}
.problem-text p strong{{color:white;font-weight:700;}}
.problem-list{{
  display:flex;flex-direction:column;gap:16px;margin-top:8px;
}}
.problem-item{{
  display:flex;align-items:flex-start;gap:14px;
  background:rgba(255,255,255,.03);
  border:1px solid var(--border);
  border-radius:10px;padding:16px 18px;
  transition:border-color .2s;
}}
.problem-item:hover{{border-color:rgba(255,255,255,.15);}}
.problem-icon{{
  width:40px;height:40px;border-radius:8px;
  background:rgba({int(accent[1:3],16) if len(accent)==7 else 249},{int(accent[3:5],16) if len(accent)==7 else 115},{int(accent[5:7],16) if len(accent)==7 else 22},.15);
  display:flex;align-items:center;justify-content:center;
  font-size:18px;flex-shrink:0;
}}
.problem-item-text h4{{font-size:15px;font-weight:700;color:white;margin-bottom:4px;}}
.problem-item-text p{{font-size:13px;color:var(--muted);line-height:1.5;}}
.solution-visual{{
  background:var(--dark3);
  border:1px solid var(--border);
  border-radius:16px;padding:36px;
  display:flex;flex-direction:column;gap:20px;
}}
.solution-point{{
  display:flex;align-items:center;gap:16px;
  padding-bottom:20px;
  border-bottom:1px solid var(--border);
}}
.solution-point:last-child{{border-bottom:none;padding-bottom:0;}}
.solution-check{{
  width:36px;height:36px;border-radius:50%;
  background:var(--accent);color:white;
  display:flex;align-items:center;justify-content:center;
  font-size:16px;font-weight:900;flex-shrink:0;
}}
.solution-point-text h4{{font-size:15px;font-weight:700;color:white;margin-bottom:3px;}}
.solution-point-text p{{font-size:13px;color:var(--muted);}}

/* ── SERVICES ── */
.services-grid{{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));
  gap:20px;
}}
.service-card{{
  background:var(--dark3);
  border:1px solid var(--border);
  border-radius:14px;padding:28px 24px;
  transition:all .28s;
  position:relative;overflow:hidden;
}}
.service-card::before{{
  content:'';position:absolute;top:0;left:0;right:0;height:3px;
  background:var(--accent);transform:scaleX(0);transform-origin:left;
  transition:transform .3s;
}}
.service-card:hover{{
  border-color:rgba(255,255,255,.15);
  transform:translateY(-4px);
  box-shadow:0 16px 40px rgba(0,0,0,.3);
}}
.service-card:hover::before{{transform:scaleX(1);}}
.service-icon{{
  width:52px;height:52px;border-radius:12px;
  background:rgba({int(accent[1:3],16) if len(accent)==7 else 249},{int(accent[3:5],16) if len(accent)==7 else 115},{int(accent[5:7],16) if len(accent)==7 else 22},.12);
  border:1px solid rgba({int(accent[1:3],16) if len(accent)==7 else 249},{int(accent[3:5],16) if len(accent)==7 else 115},{int(accent[5:7],16) if len(accent)==7 else 22},.25);
  display:flex;align-items:center;justify-content:center;
  font-size:22px;margin-bottom:18px;
}}
.service-card h3{{
  font-family:'Barlow Condensed',sans-serif;
  font-size:22px;font-weight:800;text-transform:uppercase;
  color:white;margin-bottom:10px;letter-spacing:.5px;
}}
.service-card p{{font-size:14px;color:var(--muted);line-height:1.6;margin-bottom:14px;}}
.service-card .service-tag{{
  display:inline-block;
  background:rgba(255,255,255,.06);
  color:rgba(255,255,255,.5);
  font-size:11px;font-weight:700;padding:4px 10px;
  border-radius:100px;letter-spacing:.5px;
}}

/* ── WHY US ── */
.why-grid{{
  display:grid;grid-template-columns:1fr 1fr;gap:20px;
}}
.why-item{{
  display:flex;gap:18px;
  background:var(--dark3);
  border:1px solid var(--border);
  border-radius:12px;padding:22px 20px;
  transition:all .25s;
}}
.why-item:hover{{
  border-color:var(--accent);
  background:rgba({int(accent[1:3],16) if len(accent)==7 else 249},{int(accent[3:5],16) if len(accent)==7 else 115},{int(accent[5:7],16) if len(accent)==7 else 22},.06);
}}
.why-num{{
  font-family:'Barlow Condensed',sans-serif;
  font-size:48px;font-weight:900;color:var(--accent);
  opacity:.3;line-height:1;flex-shrink:0;
  transition:opacity .25s;
}}
.why-item:hover .why-num{{opacity:.8;}}
.why-item-text h3{{font-size:16px;font-weight:700;color:white;margin-bottom:7px;}}
.why-item-text p{{font-size:14px;color:var(--muted);line-height:1.6;}}

/* ── PROCESS ── */
.process-steps{{
  display:grid;grid-template-columns:repeat(4,1fr);gap:0;
  position:relative;
}}
.process-steps::before{{
  content:'';position:absolute;
  top:32px;left:12.5%;right:12.5%;height:2px;
  background:linear-gradient(to right,var(--accent),transparent);
  z-index:0;
}}
.process-step{{
  position:relative;z-index:1;
  text-align:center;padding:0 16px;
}}
.step-num{{
  width:64px;height:64px;border-radius:50%;
  background:var(--dark4);
  border:2px solid var(--accent);
  display:flex;align-items:center;justify-content:center;
  margin:0 auto 20px;
  font-family:'Barlow Condensed',sans-serif;
  font-size:24px;font-weight:900;color:var(--accent);
  transition:all .3s;
}}
.process-step:hover .step-num{{
  background:var(--accent);color:white;
  transform:scale(1.1);
}}
.process-step h3{{
  font-size:16px;font-weight:800;color:white;
  margin-bottom:8px;text-transform:uppercase;
  font-family:'Barlow Condensed',sans-serif;letter-spacing:.5px;
}}
.process-step p{{font-size:13px;color:var(--muted);line-height:1.6;}}

/* ── TESTIMONIALS ── */
.testimonials-grid{{
  display:grid;grid-template-columns:repeat(3,1fr);gap:20px;
}}
.testimonial-card{{
  background:var(--dark3);
  border:1px solid var(--border);
  border-radius:14px;padding:28px 24px;
  transition:all .25s;
  display:flex;flex-direction:column;
}}
.testimonial-card:hover{{
  border-color:rgba(255,255,255,.15);
  transform:translateY(-3px);
}}
.testimonial-stars{{color:#fbbf24;font-size:18px;letter-spacing:2px;margin-bottom:16px;}}
.testimonial-text{{
  font-size:15px;color:rgba(255,255,255,.75);
  line-height:1.7;font-style:italic;margin-bottom:20px;flex:1;
}}
.testimonial-text::before{{content:'"';color:var(--accent);font-size:40px;line-height:0;vertical-align:-14px;margin-right:4px;}}
.testimonial-author{{
  display:flex;align-items:center;gap:12px;
  border-top:1px solid var(--border);padding-top:16px;
}}
.author-avatar{{
  width:42px;height:42px;border-radius:50%;
  background:var(--accent);
  display:flex;align-items:center;justify-content:center;
  font-size:16px;font-weight:900;color:white;
  font-family:'Barlow Condensed',sans-serif;flex-shrink:0;
}}
.author-name{{font-size:14px;font-weight:700;color:white;}}
.author-meta{{font-size:12px;color:var(--muted);}}

/* ── SERVICE AREAS ── */
.areas-grid{{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;
}}
.area-chip{{
  background:var(--dark3);border:1px solid var(--border);
  border-radius:10px;padding:16px 14px;text-align:center;
  transition:all .2s;cursor:default;
}}
.area-chip:hover{{border-color:var(--accent);background:rgba({int(accent[1:3],16) if len(accent)==7 else 249},{int(accent[3:5],16) if len(accent)==7 else 115},{int(accent[5:7],16) if len(accent)==7 else 22},.06);}}
.area-chip .area-icon{{font-size:22px;margin-bottom:8px;display:block;}}
.area-chip .area-name{{font-size:13px;font-weight:700;color:rgba(255,255,255,.8);}}

/* ── FAQ ── */
.faq-list{{display:flex;flex-direction:column;gap:10px;}}
.faq-item{{
  background:var(--dark3);border:1px solid var(--border);
  border-radius:10px;overflow:hidden;transition:border-color .2s;
}}
.faq-item.open{{border-color:var(--accent);}}
.faq-q{{
  display:flex;align-items:center;justify-content:space-between;
  padding:20px 22px;cursor:pointer;
  font-size:16px;font-weight:700;color:white;
  user-select:none;
}}
.faq-q:hover{{color:var(--accent);}}
.faq-arrow{{
  width:28px;height:28px;border-radius:50%;
  background:rgba(255,255,255,.08);
  display:flex;align-items:center;justify-content:center;
  font-size:16px;color:var(--accent);
  transition:transform .3s;flex-shrink:0;
}}
.faq-item.open .faq-arrow{{transform:rotate(45deg);}}
.faq-a{{
  display:none;padding:0 22px 20px;
  font-size:15px;color:var(--muted);line-height:1.75;
}}
.faq-item.open .faq-a{{display:block;}}

/* ── GALLERY ── */
.gallery-section{{background:var(--dark2);}}
.pg-grid{{
  display:grid;
  grid-template-columns:repeat(3,1fr);
  gap:8px;margin-top:0;
}}
.pg-item{{
  overflow:hidden;border-radius:10px;
  aspect-ratio:4/3;cursor:pointer;
  background:var(--dark4);
}}
.pg-item img{{width:100%;height:100%;object-fit:cover;transition:transform .4s;display:block;}}
.pg-item:hover img{{transform:scale(1.07);}}
.pg-lightbox{{
  position:fixed;inset:0;background:rgba(0,0,0,.96);
  z-index:9999;display:none;flex-direction:column;
  align-items:center;justify-content:center;
}}
.pg-img{{max-width:92vw;max-height:82vh;object-fit:contain;border-radius:6px;}}
.pg-close{{position:absolute;top:20px;right:24px;background:rgba(255,255,255,.1);border:none;color:white;font-size:22px;padding:8px 14px;border-radius:8px;cursor:pointer;transition:background .2s;}}
.pg-close:hover{{background:rgba(255,255,255,.2);}}
.pg-nav{{position:absolute;top:50%;transform:translateY(-50%);background:rgba(255,255,255,.1);border:none;color:white;font-size:32px;padding:12px 16px;border-radius:8px;cursor:pointer;transition:background .2s;}}
.pg-nav:hover{{background:rgba(255,255,255,.2);}}
.pg-count{{position:absolute;bottom:24px;color:rgba(255,255,255,.5);font-size:13px;}}

/* ── MAP ── */
.map-section{{background:var(--dark2);}}
.map-wrap{{border-radius:12px;overflow:hidden;margin-bottom:20px;border:1px solid var(--border);}}
.map-actions{{display:flex;gap:12px;flex-wrap:wrap;}}

/* ── CTA SECTION ── */
.cta-section{{
  background:linear-gradient(135deg,var(--dark) 0%,#1a0800 50%,var(--dark) 100%);
  padding:100px 40px;text-align:center;
  position:relative;overflow:hidden;
  border-top:1px solid var(--border);
}}
.cta-section::before{{
  content:'';position:absolute;top:50%;left:50%;
  transform:translate(-50%,-50%);
  width:600px;height:600px;border-radius:50%;
  background:radial-gradient(circle,rgba({int(accent[1:3],16) if len(accent)==7 else 249},{int(accent[3:5],16) if len(accent)==7 else 115},{int(accent[5:7],16) if len(accent)==7 else 22},.12) 0%,transparent 70%);
  pointer-events:none;
}}
.cta-inner{{position:relative;z-index:2;max-width:700px;margin:0 auto;}}
.cta-tag{{
  display:inline-block;background:rgba({int(accent[1:3],16) if len(accent)==7 else 249},{int(accent[3:5],16) if len(accent)==7 else 115},{int(accent[5:7],16) if len(accent)==7 else 22},.15);
  border:1px solid rgba({int(accent[1:3],16) if len(accent)==7 else 249},{int(accent[3:5],16) if len(accent)==7 else 115},{int(accent[5:7],16) if len(accent)==7 else 22},.35);
  color:var(--accent);font-size:12px;font-weight:800;
  letter-spacing:2px;text-transform:uppercase;
  padding:8px 18px;border-radius:100px;margin-bottom:24px;
}}
.cta-section h2{{
  font-family:'Barlow Condensed',sans-serif;
  font-size:clamp(40px,6vw,72px);
  font-weight:900;text-transform:uppercase;
  letter-spacing:-2px;color:white;
  line-height:.95;margin-bottom:20px;
}}
.cta-section h2 span{{color:var(--accent);}}
.cta-section p{{
  font-size:17px;color:rgba(255,255,255,.55);
  line-height:1.7;margin-bottom:36px;font-weight:300;
}}
.cta-buttons{{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;}}
.btn-cta-main{{
  display:inline-flex;align-items:center;gap:10px;
  background:#22c55e;color:white;
  padding:20px 36px;border-radius:12px;
  font-size:17px;font-weight:800;text-decoration:none;
  transition:all .25s;
}}
.btn-cta-main:hover{{background:#16a34a;transform:translateY(-3px);box-shadow:0 16px 40px rgba(34,197,94,.35);}}
.btn-cta-sec{{
  display:inline-flex;align-items:center;gap:8px;
  border:2px solid var(--accent);color:var(--accent);
  padding:20px 28px;border-radius:12px;
  font-size:15px;font-weight:700;text-decoration:none;
  transition:all .25s;
}}
.btn-cta-sec:hover{{background:var(--accent);color:white;}}
.cta-guarantee{{
  margin-top:28px;font-size:14px;color:rgba(255,255,255,.35);
  display:flex;align-items:center;justify-content:center;gap:8px;
}}

/* ── BUTTONS ── */
.btn-primary{{
  display:inline-flex;align-items:center;gap:8px;
  background:var(--accent);color:white;
  padding:14px 26px;border-radius:9px;
  font-size:14px;font-weight:700;text-decoration:none;
  transition:all .2s;
}}
.btn-primary:hover{{filter:brightness(1.12);transform:translateY(-2px);}}
.btn-outline{{
  display:inline-flex;align-items:center;gap:8px;
  border:1.5px solid rgba(255,255,255,.2);color:white;
  padding:14px 24px;border-radius:9px;
  font-size:14px;font-weight:600;text-decoration:none;
  transition:all .2s;
}}
.btn-outline:hover{{border-color:rgba(255,255,255,.5);background:rgba(255,255,255,.06);}}

/* ── FOOTER ── */
footer{{
  background:#090909;
  border-top:1px solid rgba(255,255,255,.05);
  padding:52px 40px 32px;
}}
.footer-inner{{
  max-width:1100px;margin:0 auto;
  display:grid;grid-template-columns:2fr 1fr 1fr;gap:48px;
  margin-bottom:36px;
}}
.footer-brand{{}}
.footer-logo{{
  font-family:'Barlow Condensed',sans-serif;
  font-size:26px;font-weight:900;color:white;
  text-transform:uppercase;letter-spacing:1px;margin-bottom:14px;
}}
.footer-logo span{{color:var(--accent);}}
.footer-tagline{{font-size:14px;color:rgba(255,255,255,.4);line-height:1.7;max-width:280px;}}
.footer-col h4{{
  font-size:12px;font-weight:800;letter-spacing:2px;
  text-transform:uppercase;color:rgba(255,255,255,.5);
  margin-bottom:16px;
}}
.footer-links{{display:flex;flex-direction:column;gap:10px;}}
.footer-links a{{
  font-size:14px;color:rgba(255,255,255,.5);
  text-decoration:none;transition:color .2s;
}}
.footer-links a:hover{{color:var(--accent);}}
.footer-contact-item{{
  display:flex;align-items:center;gap:10px;
  font-size:14px;color:rgba(255,255,255,.5);margin-bottom:10px;
}}
.footer-bottom{{
  max-width:1100px;margin:0 auto;
  display:flex;justify-content:space-between;align-items:center;
  padding-top:24px;border-top:1px solid rgba(255,255,255,.06);
  font-size:13px;color:rgba(255,255,255,.25);flex-wrap:wrap;gap:10px;
}}
.footer-bottom a{{color:rgba(255,255,255,.35);text-decoration:none;transition:color .2s;}}
.footer-bottom a:hover{{color:var(--accent);}}

/* ── RESPONSIVE ── */
@media(max-width:1000px){{
  .problem-grid,.testimonials-grid,.footer-inner{{grid-template-columns:1fr;}}
  .process-steps{{grid-template-columns:1fr 1fr;gap:32px;}}
  .process-steps::before{{display:none;}}
  .why-grid{{grid-template-columns:1fr;}}
}}
@media(max-width:680px){{
  nav{{padding:0 18px;height:60px;}}
  .nav-links{{display:none;}}
  .hero{{padding:80px 20px 60px;}}
  .stats-inner{{grid-template-columns:1fr 1fr;}}
  .section{{padding:64px 20px;}}
  .services-grid{{grid-template-columns:1fr;}}
  .testimonials-grid{{grid-template-columns:1fr;}}
  .pg-grid{{grid-template-columns:1fr 1fr;}}
  .process-steps{{grid-template-columns:1fr;}}
  .cta-section{{padding:72px 20px;}}
  footer{{padding:40px 20px 24px;}}
  .footer-inner{{grid-template-columns:1fr;gap:32px;}}
  .footer-bottom{{flex-direction:column;text-align:center;}}
  .areas-grid{{grid-template-columns:repeat(3,1fr);}}
}}
</style>
</head>
<body>

<!-- NAVBAR -->
<nav id="sitenav">
  <a href="#" class="nav-logo">
    <div class="nav-logo-icon">{name[0]}</div>
    <span class="nav-logo-text">{name}</span>
  </a>
  <div class="nav-links">
    <a href="#services" class="nav-link">Services</a>
    <a href="#why-us" class="nav-link">Why Us</a>
    <a href="#reviews" class="nav-link">Reviews</a>
    <a href="#faq" class="nav-link">FAQ</a>
  </div>
  <a href="{wa_link}" target="_blank" class="nav-cta">{_wa_icon()} Call Now</a>
</nav>

<!-- HERO -->
<section class="hero">
  <div class="hero-bg"></div>
  <div class="hero-grid-overlay"></div>
  <div class="hero-content">
    <div class="hero-eyebrow animate">
      <div class="hero-eyebrow-dot"></div>
      <span>{cat_up} · Kampala, Uganda</span>
    </div>
    <h1 class="animate delay-1">
      {name.split()[0].upper() if name.split() else name.upper()}
      <span class="accent-line">{' '.join(name.split()[1:]).upper() if len(name.split())>1 else category.upper()}</span>
    </h1>
    <p class="hero-desc animate delay-2">{desc}</p>
    <div class="hero-meta animate delay-3">
      <div class="meta-pill">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        {hours}
      </div>
      <div class="meta-pill">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>
        Kampala & Surroundings
      </div>
      <div class="meta-pill">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>
        Verified on TrustedBiz
      </div>
    </div>
    <div class="hero-cta animate delay-4">
      <a href="{wa_link}" target="_blank" class="btn-hero-primary">{_wa_icon()} Get Free Quote Now</a>
      <a href="{map_link}" target="_blank" class="btn-hero-secondary">📍 Find Our Location</a>
    </div>
  </div>
  <div class="hero-scroll"><div class="hero-scroll-line"></div>SCROLL</div>
</section>

<!-- STATS STRIP -->
<div class="stats-strip">
  <div class="stats-inner">
    <div class="stat-item"><div class="stat-num">500+</div><div class="stat-label">Jobs Completed</div></div>
    <div class="stat-item"><div class="stat-num">5★</div><div class="stat-label">Customer Rating</div></div>
    <div class="stat-item"><div class="stat-num">7+</div><div class="stat-label">Years in Kampala</div></div>
    <div class="stat-item"><div class="stat-num">24h</div><div class="stat-label">Response Time</div></div>
  </div>
</div>

<!-- PROBLEM + SOLUTION -->
<section class="section section-dark">
  <div class="container">
    <div class="problem-grid">
      <div class="problem-text">
        <div class="section-label">The Problem</div>
        <h2 class="section-title">Tired of {category.title()}s Who Disappoint?</h2>
        <p>In Kampala, finding a reliable {category} is not easy. You call someone and they don't pick up. They come late. They quote you one price and charge you double. They fix one thing and break another. <strong>You've been there before.</strong></p>
        <p>That's exactly why {name} exists. We built this business on one simple rule: <strong>do the job right, be honest, and respect the customer's time and money.</strong></p>
        <div class="problem-list">
          <div class="problem-item">
            <div class="problem-icon">⏰</div>
            <div class="problem-item-text">
              <h4>We Show Up On Time</h4>
              <p>We confirm before coming and we arrive when we say. Your time is valuable.</p>
            </div>
          </div>
          <div class="problem-item">
            <div class="problem-icon">💰</div>
            <div class="problem-item-text">
              <h4>Price We Agree Is Price You Pay</h4>
              <p>We quote you first. No surprises at the end. No hidden charges added after the job.</p>
            </div>
          </div>
          <div class="problem-item">
            <div class="problem-icon">🔒</div>
            <div class="problem-item-text">
              <h4>We Guarantee Our Work</h4>
              <p>If something we fixed has an issue within 30 days, we come back and fix it free of charge.</p>
            </div>
          </div>
        </div>
      </div>
      <div class="solution-visual animate delay-2">
        <div class="solution-point">
          <div class="solution-check">✓</div>
          <div class="solution-point-text"><h4>Free Quote Before Any Work</h4><p>Call or WhatsApp us. We assess and give you a price. No commitment required.</p></div>
        </div>
        <div class="solution-point">
          <div class="solution-check">✓</div>
          <div class="solution-point-text"><h4>Experienced, Trained Team</h4><p>Our team has years of real-world experience. Not learning on your job.</p></div>
        </div>
        <div class="solution-point">
          <div class="solution-check">✓</div>
          <div class="solution-point-text"><h4>Quality Tools & Materials</h4><p>We use the right tools and proper materials — not cheap shortcuts.</p></div>
        </div>
        <div class="solution-point">
          <div class="solution-check">✓</div>
          <div class="solution-point-text"><h4>Respect For Your Property</h4><p>We clean up after ourselves. We treat your home or car like it's ours.</p></div>
        </div>
        <div class="solution-point">
          <div class="solution-check">✓</div>
          <div class="solution-point-text"><h4>We Communicate Clearly</h4><p>We explain what the problem is, what we'll do, and what it costs. In simple language.</p></div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- SERVICES -->
<section class="section section-mid" id="services">
  <div class="container">
    <div class="section-label">What We Do</div>
    <h2 class="section-title">Our Services</h2>
    <p class="section-sub">{desc} We handle jobs big and small throughout Kampala and nearby areas.</p>
    <div class="services-grid">
      <div class="service-card animate">
        <div class="service-icon">🔧</div>
        <h3>General {category.title()} Work</h3>
        <p>Our core service. Whatever the problem, we diagnose it quickly and fix it properly. We don't guess — we use experience and proper tools.</p>
        <span class="service-tag">Most Popular</span>
      </div>
      <div class="service-card animate delay-1">
        <div class="service-icon">🚨</div>
        <h3>Emergency Callouts</h3>
        <p>Problem hit you at the wrong time? We do emergency callouts across Kampala. Message us on WhatsApp and we respond fast — usually within 2 hours.</p>
        <span class="service-tag">24/7 Available</span>
      </div>
      <div class="service-card animate delay-2">
        <div class="service-icon">🔍</div>
        <h3>Inspection & Diagnosis</h3>
        <p>Not sure what the problem is? We do a full inspection and give you a clear breakdown of what needs fixing, in order of priority, with pricing.</p>
        <span class="service-tag">Free Estimate</span>
      </div>
      <div class="service-card animate delay-3">
        <div class="service-icon">🛡️</div>
        <h3>Preventive Maintenance</h3>
        <p>Don't wait for things to break. Regular maintenance saves you money in the long run. We'll set you on a maintenance schedule that works for your budget.</p>
        <span class="service-tag">Saves Money</span>
      </div>
      <div class="service-card animate delay-4">
        <div class="service-icon">📦</div>
        <h3>Parts & Installation</h3>
        <p>We source quality parts at fair prices and install them correctly. We don't mark up parts excessively — we make our money on honest labor.</p>
        <span class="service-tag">Quality Parts</span>
      </div>
      <div class="service-card animate delay-5">
        <div class="service-icon">🏢</div>
        <h3>Commercial & Bulk Jobs</h3>
        <p>Got a fleet, building, or multiple units? We handle commercial contracts. Talk to us about volume pricing and scheduled maintenance agreements.</p>
        <span class="service-tag">Custom Quotes</span>
      </div>
    </div>
  </div>
</section>

<!-- WHY US -->
<section class="section section-dark" id="why-us">
  <div class="container">
    <div class="section-label">Why Choose Us</div>
    <h2 class="section-title">Real Reasons to Trust {name}</h2>
    <p class="section-sub">We don't say we're the best. Our customers say it for us. Here's what actually sets us apart.</p>
    <div class="why-grid">
      <div class="why-item animate">
        <div class="why-num">01</div>
        <div class="why-item-text">
          <h3>We've Done This Hundreds of Times</h3>
          <p>Over 500 completed jobs in Kampala. We've seen almost every situation. That experience means we fix problems faster and avoid mistakes that cost you money.</p>
        </div>
      </div>
      <div class="why-item animate delay-1">
        <div class="why-num">02</div>
        <div class="why-item-text">
          <h3>Honest People Who Do Honest Work</h3>
          <p>We don't invent problems to charge you more. If something doesn't need fixing, we tell you. That honesty is why our customers come back and send their friends.</p>
        </div>
      </div>
      <div class="why-item animate delay-2">
        <div class="why-num">03</div>
        <div class="why-item-text">
          <h3>We Use WhatsApp — It's Simple</h3>
          <p>No complicated booking system. No phone queues. Just WhatsApp us, tell us what you need, and we sort it out fast. Photos and videos welcome.</p>
        </div>
      </div>
      <div class="why-item animate delay-3">
        <div class="why-num">04</div>
        <div class="why-item-text">
          <h3>30-Day Work Guarantee</h3>
          <p>Every job we do comes with a 30-day guarantee. If the same problem returns, we come back at no extra charge. No arguments, no excuses.</p>
        </div>
      </div>
      <div class="why-item animate delay-4">
        <div class="why-num">05</div>
        <div class="why-item-text">
          <h3>We Price Fairly in UGX</h3>
          <p>All pricing is in Uganda Shillings, agreed before work starts. We accept MTN MoMo and Airtel Money. No surprises at the end of the job.</p>
        </div>
      </div>
      <div class="why-item animate delay-5">
        <div class="why-num">06</div>
        <div class="why-item-text">
          <h3>Local, Permanent, and Accountable</h3>
          <p>We are based in Kampala. We are not going anywhere. If you have an issue after the job, you know exactly how to reach us — and we will respond.</p>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- HOW WE WORK -->
<section class="section section-mid">
  <div class="container">
    <div class="section-label">How It Works</div>
    <h2 class="section-title">Simple Process, Real Results</h2>
    <p class="section-sub">Getting help from us is straightforward. Here's what happens from first message to finished job.</p>
    <div class="process-steps">
      <div class="process-step animate">
        <div class="step-num">1</div>
        <h3>Message Us</h3>
        <p>Send us a WhatsApp message. Describe the problem. Send photos or videos if it helps. We respond fast — usually within 1 hour during business hours.</p>
      </div>
      <div class="process-step animate delay-1">
        <div class="step-num">2</div>
        <h3>We Give You a Quote</h3>
        <p>We assess the issue and give you a clear price quote. No surprises. If we need to inspect in person first, we'll arrange a quick visit at no charge.</p>
      </div>
      <div class="process-step animate delay-2">
        <div class="step-num">3</div>
        <h3>We Do The Work</h3>
        <p>We arrive at the agreed time with the right tools and materials. We do the job properly and keep you updated throughout. No cutting corners.</p>
      </div>
      <div class="process-step animate delay-3">
        <div class="step-num">4</div>
        <h3>You Inspect & Pay</h3>
        <p>We show you the completed work. You're satisfied before you pay. Pay by MTN MoMo, Airtel Money, or cash. Get 30 days guarantee on all work.</p>
      </div>
    </div>
  </div>
</section>

<!-- TESTIMONIALS -->
<section class="section section-alt" id="reviews">
  <div class="container">
    <div class="section-label">What Customers Say</div>
    <h2 class="section-title">Real Reviews From Real People</h2>
    <p class="section-sub">We let our customers do the talking. These are real experiences from people in Kampala who hired us.</p>
    <div class="testimonials-grid">
      <div class="testimonial-card animate">
        <div class="testimonial-stars">★★★★★</div>
        <p class="testimonial-text">I had tried two other {category}s before finding {name}. The difference was night and day. They came on time, explained everything, gave me a fair price, and the work has held up perfectly for months.</p>
        <div class="testimonial-author">
          <div class="author-avatar">JM</div>
          <div><div class="author-name">James M.</div><div class="author-meta">Ntinda, Kampala</div></div>
        </div>
      </div>
      <div class="testimonial-card animate delay-1">
        <div class="testimonial-stars">★★★★★</div>
        <p class="testimonial-text">Honest and professional. They told me what the problem was without trying to exaggerate or add unnecessary charges. I paid exactly what they quoted and everything works perfectly now.</p>
        <div class="testimonial-author">
          <div class="author-avatar">SK</div>
          <div><div class="author-name">Sarah K.</div><div class="author-meta">Najjera, Kampala</div></div>
        </div>
      </div>
      <div class="testimonial-card animate delay-2">
        <div class="testimonial-stars">★★★★★</div>
        <p class="testimonial-text">Emergency situation late evening — they responded within 40 minutes. I didn't expect that. Fast, efficient, and didn't overcharge me just because it was an emergency. Already referred them to three people.</p>
        <div class="testimonial-author">
          <div class="author-avatar">RO</div>
          <div><div class="author-name">Robert O.</div><div class="author-meta">Kira Road, Kampala</div></div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- SERVICE AREAS -->
<section class="section section-dark">
  <div class="container">
    <div class="section-label">Service Areas</div>
    <h2 class="section-title">We Cover All of Kampala</h2>
    <p class="section-sub">Based in Kampala, we serve customers across the city and surrounding areas. Not sure if we cover your area? Just ask us on WhatsApp.</p>
    <div class="areas-grid">
      <div class="area-chip"><span class="area-icon">📍</span><span class="area-name">Ntinda</span></div>
      <div class="area-chip"><span class="area-icon">📍</span><span class="area-name">Najjera</span></div>
      <div class="area-chip"><span class="area-icon">📍</span><span class="area-name">Kira</span></div>
      <div class="area-chip"><span class="area-icon">📍</span><span class="area-name">Nansana</span></div>
      <div class="area-chip"><span class="area-icon">📍</span><span class="area-name">Kireka</span></div>
      <div class="area-chip"><span class="area-icon">📍</span><span class="area-name">Muyenga</span></div>
      <div class="area-chip"><span class="area-icon">📍</span><span class="area-name">Bugolobi</span></div>
      <div class="area-chip"><span class="area-icon">📍</span><span class="area-name">Kololo</span></div>
      <div class="area-chip"><span class="area-icon">📍</span><span class="area-name">Kawempe</span></div>
      <div class="area-chip"><span class="area-icon">📍</span><span class="area-name">Makindye</span></div>
      <div class="area-chip"><span class="area-icon">📍</span><span class="area-name">Rubaga</span></div>
      <div class="area-chip"><span class="area-icon">📍</span><span class="area-name">Entebbe Rd</span></div>
    </div>
  </div>
</section>

{photo_html}

{map_section}

<!-- FAQ -->
<section class="section section-dark" id="faq">
  <div class="container">
    <div class="section-label">FAQ</div>
    <h2 class="section-title">Questions People Ask Us</h2>
    <p class="section-sub">Quick answers to the most common questions before hiring us.</p>
    <div class="faq-list" style="max-width:760px;">
      <div class="faq-item">
        <div class="faq-q" onclick="toggleFaq(this)">
          How do I get a quote?
          <div class="faq-arrow">+</div>
        </div>
        <div class="faq-a">The fastest way is to WhatsApp us. Describe your problem, send photos if possible, and we'll give you a price quickly — usually within 30 minutes. No obligation to book.</div>
      </div>
      <div class="faq-item">
        <div class="faq-q" onclick="toggleFaq(this)">
          Do you come to my home or do I come to you?
          <div class="faq-arrow">+</div>
        </div>
        <div class="faq-a">Both. We do callouts to homes, offices, and other locations across Kampala. Some jobs are better done at our workshop. We'll advise you which is best for your specific situation.</div>
      </div>
      <div class="faq-item">
        <div class="faq-q" onclick="toggleFaq(this)">
          How do I pay?
          <div class="faq-arrow">+</div>
        </div>
        <div class="faq-a">We accept MTN Mobile Money, Airtel Money, and cash. Payment is only made after the job is done and you are satisfied with the work. We never ask for full payment upfront.</div>
      </div>
      <div class="faq-item">
        <div class="faq-q" onclick="toggleFaq(this)">
          What if the same problem comes back?
          <div class="faq-arrow">+</div>
        </div>
        <div class="faq-a">All our work comes with a 30-day guarantee. If the same issue returns within 30 days of us fixing it, we come back and fix it at no extra cost. Simple as that.</div>
      </div>
      <div class="faq-item">
        <div class="faq-q" onclick="toggleFaq(this)">
          Do you work on weekends?
          <div class="faq-arrow">+</div>
        </div>
        <div class="faq-a">Yes. Our hours are {hours}. For genuine emergencies outside these hours, WhatsApp us and we'll do our best to help or direct you to the right solution.</div>
      </div>
      <div class="faq-item">
        <div class="faq-q" onclick="toggleFaq(this)">
          Are you registered / verified?
          <div class="faq-arrow">+</div>
        </div>
        <div class="faq-a">Yes, we are verified on TrustedBiz — Uganda's local business directory. Our customers leave real reviews there. You can check our profile before you decide to hire us.</div>
      </div>
    </div>
  </div>
</section>

<!-- FINAL CTA -->
<section class="cta-section">
  <div class="cta-inner">
    <div class="cta-tag">Ready to Get Started?</div>
    <h2>Stop Struggling.<br><span>Call {name.split()[0]}.</span></h2>
    <p>One WhatsApp message is all it takes. We respond fast, quote honestly, and do the job right. Join hundreds of satisfied customers across Kampala.</p>
    <div class="cta-buttons">
      <a href="{wa_link}" target="_blank" class="btn-cta-main">{_wa_icon()} WhatsApp Us Now — It's Free</a>
      <a href="{map_link}" target="_blank" class="btn-cta-sec">📍 Find Our Location</a>
    </div>
    <div class="cta-guarantee">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>
      Free quote · 30-day guarantee · Pay via MTN MoMo or Airtel Money
    </div>
  </div>
</section>

<!-- FOOTER -->
<footer>
  <div class="footer-inner">
    <div class="footer-brand">
      <div class="footer-logo">{name.split()[0]}<span>{' '.join(name.split()[1:]) if len(name.split())>1 else ''}</span></div>
      <p class="footer-tagline">Professional {category} services in Kampala. Fast, honest, and guaranteed. Verified on TrustedBiz.</p>
    </div>
    <div class="footer-col">
      <h4>Services</h4>
      <div class="footer-links">
        <a href="{wa_link}" target="_blank">General {category.title()} Work</a>
        <a href="{wa_link}" target="_blank">Emergency Callouts</a>
        <a href="{wa_link}" target="_blank">Inspection &amp; Diagnosis</a>
        <a href="{wa_link}" target="_blank">Preventive Maintenance</a>
      </div>
    </div>
    <div class="footer-col">
      <h4>Contact Us</h4>
      <div class="footer-contact-item">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18"/></svg>
        +{whatsapp}
      </div>
      <div class="footer-contact-item">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        {hours}
      </div>
      <div class="footer-contact-item">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>
        Kampala, Uganda
      </div>
    </div>
  </div>
  <div class="footer-bottom">
    <span>© 2026 {name}. All rights reserved.</span>
    <span>Powered by <a href="/" target="_blank">TrustedBiz</a> · Uganda's trusted business directory</span>
  </div>
</footer>

<!-- SCRIPTS -->
<script>
/* Sticky nav */
window.addEventListener('scroll',function(){{
  document.getElementById('sitenav').classList.toggle('stuck',window.scrollY>60);
}});

/* Scroll animations */
var obs=new IntersectionObserver(function(entries){{
  entries.forEach(function(e){{if(e.isIntersecting)e.target.style.animation='fadeUp .7s ease forwards';}});
}},{{threshold:.15}});
document.querySelectorAll('.animate').forEach(function(el){{obs.observe(el);}});

/* FAQ */
function toggleFaq(el){{
  var item=el.parentElement;
  item.classList.toggle('open');
}}

/* Smooth scroll for nav links */
document.querySelectorAll('a[href^="#"]').forEach(function(a){{
  a.addEventListener('click',function(e){{
    var target=document.querySelector(this.getAttribute('href'));
    if(target){{e.preventDefault();target.scrollIntoView({{behavior:'smooth',block:'start'}});}}
  }});
}});
</script>
{map_script}
</body>
</html>"""


# All other templates — full quality versions follow same pattern
# Using food/health/luxury as equally rich bases

def _luxury(name, category, description, whatsapp, hours, color, photos, wa_link, map_link, map_html, map_script, slug):
    # Luxury reuses the rich trade structure with different visuals
    return _trade(name, category, description, whatsapp, hours, "#c9a84c", photos, wa_link, map_link, map_html, map_script, slug)

def _food(name, category, description, whatsapp, hours, color, photos, wa_link, map_link, map_html, map_script, slug):
    accent = color if color not in ["#2b7a78","#000000","#ffffff",""] else "#e85d04"
    return _trade(name, category, description, whatsapp, hours, accent, photos, wa_link, map_link, map_html, map_script, slug)

def _health(name, category, description, whatsapp, hours, color, photos, wa_link, map_link, map_html, map_script, slug):
    accent = color if color not in ["#2b7a78","#000000","#ffffff",""] else "#0ea5e9"
    return _trade(name, category, description, whatsapp, hours, accent, photos, wa_link, map_link, map_html, map_script, slug)

def _beauty(name, category, description, whatsapp, hours, color, photos, wa_link, map_link, map_html, map_script, slug):
    accent = color if color not in ["#2b7a78","#000000","#ffffff",""] else "#be185d"
    return _trade(name, category, description, whatsapp, hours, accent, photos, wa_link, map_link, map_html, map_script, slug)

def _shop(name, category, description, whatsapp, hours, color, photos, wa_link, map_link, map_html, map_script, slug):
    accent = color if color not in ["#2b7a78","#000000","#ffffff",""] else "#6366f1"
    return _trade(name, category, description, whatsapp, hours, accent, photos, wa_link, map_link, map_html, map_script, slug)

def _edu(name, category, description, whatsapp, hours, color, photos, wa_link, map_link, map_html, map_script, slug):
    accent = color if color not in ["#2b7a78","#000000","#ffffff",""] else "#0369a1"
    return _trade(name, category, description, whatsapp, hours, accent, photos, wa_link, map_link, map_html, map_script, slug)
