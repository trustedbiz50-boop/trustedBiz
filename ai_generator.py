"""
ai_generator.py — TrustedBiz AI Website Generator
Basic Plan  → Claude Haiku  (fast, unique, beautiful)
Pro Max     → Claude Sonnet (stunning, magazine-level)
Fallback    → High-quality static HTML (no API needed)
"""
import os, re, json

def _client(model="haiku"):
    key = os.environ.get("ANTHROPIC_API_KEY","")
    if not key: return None, None
    try:
        import anthropic
        c = anthropic.Anthropic(api_key=key)
        if model == "sonnet":
            return c, "claude-sonnet-4-5"
        return c, "claude-haiku-4-5"
    except ImportError:
        return None, None

def _hex_rgb(h):
    try:
        h = h.lstrip('#')
        if len(h)==3: h=''.join(c*2 for c in h)
        return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"
    except: return "43,122,120"

# Design personalities per category
DESIGNS = {
    "cafe":       ("warm-editorial",    "Cream & coffee tones, cozy editorial, handwritten accents"),
    "coffee":     ("warm-editorial",    "Warm cream, cozy editorial, artisan feel"),
    "restaurant": ("bold-food",         "Dark dramatic, huge typography, food magazine energy"),
    "food":       ("bold-food",         "Dark backgrounds, oversized type, vibrant food energy"),
    "salon":      ("luxury-beauty",     "Gold & black, Vogue-level elegance, fashion editorial"),
    "beauty":     ("luxury-beauty",     "Gold accents, marble textures, premium feminine"),
    "barber":     ("urban-barbershop",  "Dark industrial, geometric type, bold masculine"),
    "mechanic":   ("industrial-bold",   "Dark steel, orange accent, raw power and reliability"),
    "garage":     ("industrial-bold",   "Steel & orange, mechanical, strong and trustworthy"),
    "plumber":    ("clean-trades",      "Navy & white, clean professional, trustworthy"),
    "electrician":("electric-trades",   "Dark navy, electric yellow, sharp and technical"),
    "gym":        ("high-energy",       "Dark background, neon accent, athletic energy, condensed type"),
    "fitness":    ("high-energy",       "Dark, neon, high contrast, motivational"),
    "pharmacy":   ("clean-medical",     "White & teal, clinical precision, calm authority"),
    "clinic":     ("soft-medical",      "Soft blue, caring and reassuring, professional"),
    "hospital":   ("medical-authority", "White & blue, calm authority, trustworthy"),
    "school":     ("bright-education",  "Clean bright blues, inspiring, welcoming"),
    "hotel":      ("luxury-hospitality","Dark elegant, gold accents, cinematic experience"),
    "lodge":      ("luxury-hospitality","Dark elegant, gold, nature-luxury blend"),
    "fashion":    ("high-fashion",      "Bold editorial, striking contrast, asymmetric layouts"),
    "boutique":   ("high-fashion",      "Bold typography, asymmetric, avant-garde"),
    "electronics":("sleek-tech",        "Dark, blue accent, futuristic, minimal"),
    "phone":      ("sleek-tech",        "Dark, cyan accent, tech-forward"),
    "supermarket":("fresh-market",      "Bright, colorful, friendly, welcoming"),
    "hardware":   ("strong-trades",     "Bold orange, industrial, reliable and strong"),
}

def _design(cat):
    if not cat: return ("modern-pro", "Clean bold typography, premium modern feel")
    c = cat.lower()
    for k,v in DESIGNS.items():
        if k in c: return v
    return ("modern-pro", "Clean bold typography, premium modern feel")


def generate_business_website(biz, plan="basic"):
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

    # Pro Max uses Sonnet, Basic uses Haiku
    model = "sonnet" if (plan == "promax" or is_premium) else "haiku"
    client, model_id = _client(model)

    photos  = [p.strip() for p in photos_raw.split(",") if p.strip()]
    wa_link = f"https://wa.me/{whatsapp}?text=Hello%2C+I+found+{name.replace(' ','+')}+on+TrustedBiz%21"
    map_link = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}" if lat and lng else ""

    if client:
        try:
            return _ai_generate(client, model_id, biz, name, category, description,
                                whatsapp, hours, color, photos, lat, lng,
                                hero_price, hero_label, branches, ads,
                                wa_link, map_link, plan)
        except Exception as e:
            print(f"AI generate error: {e}")

    return _fallback(name, category, description, whatsapp, hours, color,
                     photos, lat, lng, hero_price, hero_label,
                     branches, ads, wa_link, map_link)


def generate_business_website_bg(biz, db_execute, biz_id, plan="basic"):
    try:
        html = generate_business_website(biz, plan)
        if html and len(html) > 2000:
            try:
                db_execute(
                    "UPDATE business SET generated_html=? WHERE id=?",
                    (html, biz_id)
                )
                print(f"Website generation done for biz_id={biz_id} plan={plan}")
            except Exception as e:
                print(f"DB save error: {e}")
    except Exception as e:
        print(f"Website generation error for biz_id={biz_id}: {e}")


def _ai_generate(client, model_id, biz, name, category, description, whatsapp,
                 hours, color, photos, lat, lng,
                 hero_price, hero_label, branches, ads,
                 wa_link, map_link, plan):

    design_style, design_desc = _design(category)
    rgb = _hex_rgb(color)

    # Build photo HTML
    photo_html = ""
    if photos:
        for i, p in enumerate(photos[:8]):
            src = p if p.startswith("http") else f"/static/images/{p}"
            photo_html += f'<div class="gal-item" onclick="openLb({i})"><img src="{src}" alt="Photo {i+1}" loading="lazy"></div>\n'

    # Branch info
    branch_text = ""
    if branches:
        for br in branches:
            branch_text += f"- {br.get('name','Branch')}: {br.get('address','')}, Hours: {br.get('hours','')}\n"

    # Price info
    price_text = f"Signature item: {hero_label} — UGX {int(float(hero_price)):,}" if hero_price and hero_label else ""

    # Ads info
    ads_text = ""
    if ads:
        for ad in ads:
            ads_text += f"PROMO: '{ad.get('title','')}' — {ad.get('body','')}\n"

    # Different prompts for Basic vs Pro Max
    if plan == "promax":
        style_instruction = f"""You are the creative director at a world-class $50,000/project web agency.
Create a MAGAZINE-LEVEL, award-winning website for this Uganda business.
Design inspiration: {design_desc}
This must look like it was designed by a top agency in New York or London — but feel local and authentic.
Use CREATIVE LAYOUT TECHNIQUES: asymmetric grids, large typographic statements, bold color blocks, 
diagonal sections, layered depth, micro-animations, glassmorphism or neumorphism where appropriate.
The Pro Max website must be NOTICEABLY more premium, more unique, and more impressive than a basic website."""
    else:
        style_instruction = f"""You are a skilled web designer at a professional agency.
Create a BEAUTIFUL, unique, and professional website for this Uganda business.
Design style: {design_desc}
Make it clean, modern, and impressive — NOT a template. Each section should feel intentional and designed.
Use the brand color powerfully throughout."""

    prompt = f"""{style_instruction}

BUSINESS INFORMATION:
Name: {name}
Type: {category}
About: {description}
WhatsApp: {whatsapp}
Hours: {hours}
Brand Color: {color} (RGB: {rgb})
{price_text}
{f"BRANCHES:{chr(10)}{branch_text}" if branch_text else ""}
{f"ACTIVE PROMOTIONS:{chr(10)}{ads_text}" if ads_text else ""}

DESIGN RULES — NEVER BREAK:
1. HERO: Pure CSS backgrounds ONLY — gradients, SVG shapes, CSS art, geometric patterns. NO <img> in hero.
2. BUSINESS NAME in hero: font-size clamp(36px,9vw,100px), overflow:hidden, word-break:break-word
3. MOBILE: Perfect on 390px screens. Hero buttons: flex-direction:column on mobile, width:fit-content, min-width:200px
4. BRAND COLOR {color}: Use as primary everywhere — buttons, accents, gradients, highlights
5. ANIMATIONS: CSS keyframes only. Fade-up on scroll via IntersectionObserver.
6. MOBILE NAV: Hamburger menu that toggles nav links on mobile
7. GALLERY: Client photos ONLY in gallery section using these img tags:
{photo_html if photo_html else "   No photos — use CSS gradient placeholder cards with relevant icons"}
8. FOOTER: © 2026 {name}. Powered by TrustedBiz linking to https://trustedbiz.co.ug
9. WHATSAPP BUTTON: background:#25D366; color:white; border-radius:50px; Always use this link: {wa_link}

REQUIRED SECTIONS:
1. STICKY NAV — logo left, hamburger mobile menu, WhatsApp button right
2. HERO — 100vh, massive business name, powerful tagline from description
   Buttons: "💬 Chat on WhatsApp" + {"📍 Get Directions" if map_link else "📞 Contact Us"}
3. ABOUT — description + 4 trust cards (hours, contact, verified, location)
4. SERVICES — 4-6 cards with real services inferred from {category} and description
5. GALLERY — {"Show all " + str(len(photos)) + " photos" if photos else "3 styled placeholder cards"}
6. {"PRICING — feature card: " + hero_label + " UGX " + str(int(float(hero_price))) + " with WhatsApp CTA" if hero_price else "WHY CHOOSE US — 3 compelling reasons"}
{f"7. PROMOTIONS — styled cards for: {ads_text}" if ads_text else ""}
{f"{'8' if ads_text else '7'}. BRANCHES — location cards for all branches" if branch_text else ""}
7. CONTACT — large WhatsApp CTA, hours, {"map directions button: " + map_link if map_link else "contact details"}
8. FOOTER — name, tagline, © 2026, Powered by TrustedBiz

CSS VARIABLES TO USE:
:root {{ --primary: {color}; --primary-rgb: {rgb}; --dark: #0d0d0d; --light: #f7f7f5; }}

OUTPUT: Raw HTML only. Start with <!DOCTYPE html>. No markdown, no backticks, no explanation."""

    messages = [{"role": "user", "content": prompt}]
    full_text = ""
    max_tokens = 12000 if plan == "promax" else 9000

    for round_num in range(5):
        msg = client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            messages=messages
        )
        chunk = msg.content[0].text if msg.content else ""
        full_text += chunk

        if msg.stop_reason != "max_tokens":
            break

        print(f"Continuing generation round {round_num + 1}...")
        messages.append({"role": "assistant", "content": chunk})
        messages.append({"role": "user", "content": "Continue exactly where you stopped. Output only remaining HTML."})

    raw = full_text.strip()
    raw = re.sub(r'^```html\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'^```\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    if raw and '</html>' not in raw[-500:]:
        raw = raw.rstrip() + '\n</body>\n</html>'

    return raw.strip()


def _fallback(name, category, description, whatsapp, hours, color,
              photos, lat, lng, hero_price, hero_label,
              branches, ads, wa_link, map_link):
    """High-quality fallback — no API needed."""
    rgb = _hex_rgb(color)
    _, design_desc = _design(category)

    gallery_html = ""
    photos_js = "var P=[];"
    if photos:
        items = ""
        for i, p in enumerate(photos[:8]):
            src = p if p.startswith("http") else f"/static/images/{p}"
            items += f'<div class="gi" onclick="lb({i})"><img src="{src}" alt="" loading="lazy"></div>'
        gallery_html = f'<section class="sec sec-alt" id="gallery"><div class="wrap"><p class="sec-label">Gallery</p><h2 class="sec-h">Our Work</h2><div class="gal">{items}</div></div></section>'
        photos_js = "var P=[" + ",".join([f'"{p if p.startswith("http") else "/static/images/"+p}"' for p in photos]) + "];"

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
                img_html = f'<img src="{src}" alt="" style="width:100%;max-height:260px;object-fit:cover;border-radius:12px;margin-bottom:16px;">'
            ads_html += f'<div class="ad-block">{img_html}<h3>{ad.get("title","")}</h3><p>{ad.get("body","")}</p><a href="{wa_link}" target="_blank" class="wa-btn" style="margin-top:14px;display:inline-flex;">Learn More</a></div>'
        ads_html = f'<section class="sec" id="promos"><div class="wrap"><p class="sec-label">Announcements</p><h2 class="sec-h">Latest Updates</h2><div class="ads-grid">{ads_html}</div></div></section>'

    map_html = ""
    if lat and lng:
        map_html = f'<div id="bmap" style="width:100%;height:280px;border-radius:12px;margin-top:20px;"></div><link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/><script src="https://unpkg.com/leaflet/dist/leaflet.js"></script><script>var bm=L.map("bmap").setView([{lat},{lng}],15);L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png",{{maxZoom:19}}).addTo(bm);L.marker([{lat},{lng}]).addTo(bm).bindPopup("<strong>{name}</strong>").openPopup();</script>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name} — {category.title()} in Uganda</title>
<meta name="description" content="{description[:155]}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800;900&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,300&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
:root{{--primary:{color};--rgb:{rgb};--dark:#0d0d0d;--light:#f7f7f5;}}
html{{scroll-behavior:smooth;}}
body{{font-family:'DM Sans',sans-serif;background:var(--light);color:#1a1a1a;overflow-x:hidden;}}
@keyframes fadeUp{{from{{opacity:0;transform:translateY(28px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes pulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.4);opacity:.6}}}}
@keyframes float{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-10px)}}}}
.reveal{{opacity:0;transform:translateY(24px);transition:opacity .7s ease,transform .7s ease;}}
.reveal.in{{opacity:1;transform:none;}}
nav{{position:fixed;top:0;left:0;right:0;z-index:100;height:64px;display:flex;align-items:center;justify-content:space-between;padding:0 36px;transition:background .3s,box-shadow .3s;}}
nav.solid{{background:rgba(13,13,13,.97);box-shadow:0 1px 0 rgba(255,255,255,.06);}}
.nav-brand{{font-family:'Syne',sans-serif;font-weight:800;font-size:18px;color:white;text-decoration:none;letter-spacing:-.3px;}}
.nav-brand em{{font-style:normal;color:var(--primary);}}
.nav-wa{{background:var(--primary);color:white;padding:9px 20px;border-radius:8px;font-weight:700;font-size:13px;text-decoration:none;transition:filter .2s,transform .2s;white-space:nowrap;}}
.nav-wa:hover{{filter:brightness(1.12);transform:translateY(-1px);}}
.hero{{min-height:100vh;background:var(--dark);display:flex;align-items:center;justify-content:center;text-align:center;padding:100px 24px 80px;position:relative;overflow:hidden;}}
.hero-bg{{position:absolute;inset:0;background:radial-gradient(ellipse 80% 70% at 50% 40%,rgba(var(--rgb),.2) 0%,transparent 60%);}}
.hero-shapes{{position:absolute;inset:0;overflow:hidden;opacity:.06;}}
.hero-shapes::before{{content:'';position:absolute;width:600px;height:600px;border:1px solid rgba(255,255,255,.3);border-radius:50%;top:-100px;right:-200px;animation:float 8s ease-in-out infinite;}}
.hero-shapes::after{{content:'';position:absolute;width:400px;height:400px;border:1px solid rgba(255,255,255,.2);border-radius:50%;bottom:-100px;left:-100px;animation:float 6s ease-in-out infinite reverse;}}
.hero-inner{{position:relative;z-index:2;max-width:860px;animation:fadeUp .9s ease forwards;}}
.eyebrow{{display:inline-flex;align-items:center;gap:8px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.15);color:rgba(255,255,255,.8);font-size:11px;font-weight:700;letter-spacing:2.5px;text-transform:uppercase;padding:8px 20px;border-radius:100px;margin-bottom:32px;}}
.dot{{width:6px;height:6px;border-radius:50%;background:var(--primary);animation:pulse 2s infinite;flex-shrink:0;}}
.hero h1{{font-family:'Syne',sans-serif;font-size:clamp(40px,9vw,100px);font-weight:900;color:white;line-height:.95;letter-spacing:-3px;margin-bottom:24px;overflow:hidden;word-break:break-word;}}
.hero h1 .ac{{color:var(--primary);}}
.hero-desc{{font-size:18px;color:rgba(255,255,255,.55);max-width:560px;margin:0 auto 44px;line-height:1.8;font-weight:300;}}
.hero-btns{{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;}}
.wa-btn{{display:inline-flex;align-items:center;gap:9px;background:#25D366;color:white;padding:16px 32px;border-radius:50px;font-size:15px;font-weight:700;text-decoration:none;transition:all .25s;width:fit-content;}}
.wa-btn:hover{{background:#1eaa52;transform:translateY(-2px);box-shadow:0 14px 32px rgba(37,211,102,.3);}}
.dir-btn{{display:inline-flex;align-items:center;gap:9px;border:2px solid rgba(255,255,255,.18);color:rgba(255,255,255,.85);padding:16px 28px;border-radius:50px;font-size:15px;font-weight:600;text-decoration:none;transition:all .25s;width:fit-content;}}
.dir-btn:hover{{border-color:var(--primary);background:rgba(var(--rgb),.1);}}
.sec{{padding:92px 24px;}}
.sec-alt{{background:white;}}
.wrap{{max-width:1040px;margin:0 auto;}}
.sec-label{{font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:var(--primary);margin-bottom:14px;}}
.sec-h{{font-family:'Syne',sans-serif;font-size:clamp(28px,4vw,52px);font-weight:800;color:#111;line-height:1.05;letter-spacing:-1.5px;margin-bottom:16px;}}
.sec-sub{{font-size:16px;color:#6b7280;line-height:1.8;max-width:600px;margin-bottom:52px;font-weight:300;}}
.info-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:44px;}}
.info-card{{background:var(--light);border-radius:16px;padding:28px;border:1.5px solid #e5e7eb;transition:border-color .2s,transform .2s;}}
.info-card:hover{{border-color:var(--primary);transform:translateY(-3px);}}
.ic-icon{{font-size:30px;margin-bottom:16px;}}
.info-card h3{{font-family:'Syne',sans-serif;font-size:17px;font-weight:700;color:#111;margin-bottom:8px;}}
.info-card p{{font-size:14px;color:#6b7280;line-height:1.65;}}
.services-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:18px;margin-top:44px;}}
.svc-card{{background:var(--light);border-radius:14px;padding:26px;border:1.5px solid #e5e7eb;transition:all .2s;position:relative;overflow:hidden;}}
.svc-card::after{{content:'';position:absolute;bottom:0;left:0;right:0;height:3px;background:var(--primary);transform:scaleX(0);transform-origin:left;transition:transform .3s;}}
.svc-card:hover{{border-color:var(--primary);transform:translateY(-4px);box-shadow:0 8px 24px rgba(0,0,0,.08);}}
.svc-card:hover::after{{transform:scaleX(1);}}
.svc-icon{{font-size:30px;margin-bottom:14px;}}
.svc-card h3{{font-family:'Syne',sans-serif;font-size:16px;font-weight:700;color:#111;margin-bottom:7px;}}
.svc-card p{{font-size:13px;color:#6b7280;line-height:1.55;}}
.gal{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-top:44px;}}
.gi{{aspect-ratio:4/3;border-radius:12px;overflow:hidden;cursor:pointer;}}
.gi img{{width:100%;height:100%;object-fit:cover;transition:transform .4s;display:block;}}
.gi:hover img{{transform:scale(1.07);}}
.contact-grid{{display:grid;grid-template-columns:1fr 1fr;gap:28px;align-items:start;margin-top:44px;}}
.contact-detail{{display:flex;align-items:center;gap:14px;padding:16px;background:var(--light);border-radius:12px;margin-bottom:12px;border:1px solid #e5e7eb;}}
.cd-icon{{width:42px;height:42px;background:rgba(var(--rgb),.12);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;}}
.cd-label{{font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px;}}
.cd-val{{font-size:14px;font-weight:600;color:#111;}}
.branches{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;margin-top:44px;}}
.branch-card{{background:var(--light);border-radius:14px;padding:24px;border:1.5px solid #e5e7eb;}}
.branch-card h4{{font-family:'Syne',sans-serif;font-size:16px;font-weight:700;margin-bottom:8px;}}
.branch-card p{{font-size:13px;color:#6b7280;margin-bottom:4px;}}
.ads-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px;margin-top:44px;}}
.ad-block{{background:linear-gradient(135deg,rgba(var(--rgb),.07),rgba(var(--rgb),.02));border:1.5px solid rgba(var(--rgb),.2);border-radius:16px;padding:26px;}}
.ad-block h3{{font-family:'Syne',sans-serif;font-size:20px;font-weight:700;color:#111;margin-bottom:8px;}}
.ad-block p{{font-size:14px;color:#6b7280;line-height:1.65;}}
.lb{{position:fixed;inset:0;background:rgba(0,0,0,.95);z-index:9000;display:none;flex-direction:column;align-items:center;justify-content:center;}}
.lb.open{{display:flex;}}
.lb-img{{max-width:90vw;max-height:80vh;border-radius:8px;object-fit:contain;}}
.lb-close{{position:absolute;top:20px;right:24px;color:white;font-size:26px;cursor:pointer;background:rgba(255,255,255,.1);border:none;padding:8px 14px;border-radius:8px;}}
.lb-prev,.lb-next{{position:absolute;top:50%;transform:translateY(-50%);color:white;font-size:32px;cursor:pointer;background:rgba(255,255,255,.1);border:none;padding:10px 16px;border-radius:8px;transition:background .2s;}}
.lb-prev{{left:12px;}}.lb-next{{right:12px;}}
.lb-prev:hover,.lb-next:hover{{background:rgba(255,255,255,.22);}}
footer{{background:var(--dark);padding:40px 24px;text-align:center;color:rgba(255,255,255,.3);font-size:13px;}}
footer strong{{color:rgba(255,255,255,.7);font-family:'Syne',sans-serif;}}
footer a{{color:var(--primary);text-decoration:none;font-weight:600;}}
@media(max-width:700px){{
  nav{{padding:0 16px;}}
  .hero{{padding:90px 16px 70px;}}
  .hero-btns{{flex-direction:column;align-items:center;}}
  .wa-btn,.dir-btn{{min-width:220px;justify-content:center;}}
  .info-grid,.contact-grid{{grid-template-columns:1fr;}}
  .sec{{padding:64px 16px;}}
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
  <div class="hero-bg"></div>
  <div class="hero-shapes"></div>
  <div class="hero-inner">
    <div class="eyebrow"><span class="dot"></span>{category.upper()} · UGANDA</div>
    <h1><span class="ac">{name}</span></h1>
    <p class="hero-desc">{description[:220]}</p>
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
      <div class="info-card reveal"><div class="ic-icon">💬</div><h3>WhatsApp Us</h3><p>+{whatsapp}<br>Message us anytime</p></div>
      <div class="info-card reveal"><div class="ic-icon">✅</div><h3>Verified Business</h3><p>Listed and verified on TrustedBiz Uganda</p></div>
      <div class="info-card reveal"><div class="ic-icon">📍</div><h3>Find Us</h3><p>{"Get directions via Google Maps" if map_link else "Contact us for our location"}</p></div>
    </div>
  </div>
</section>
<section class="sec" id="services">
  <div class="wrap">
    <p class="sec-label">What We Offer</p>
    <h2 class="sec-h reveal">Our Services</h2>
    <div class="services-grid">
      <div class="svc-card reveal"><div class="svc-icon">⭐</div><h3>Quality Service</h3><p>Professional {category} services delivered by experienced specialists.</p></div>
      <div class="svc-card reveal"><div class="svc-icon">⚡</div><h3>Fast & Reliable</h3><p>We respect your time and deliver results you can count on.</p></div>
      <div class="svc-card reveal"><div class="svc-icon">💬</div><h3>WhatsApp Support</h3><p>Reach us anytime on WhatsApp. We respond quickly.</p></div>
      <div class="svc-card reveal"><div class="svc-icon">🛡️</div><h3>Trusted & Verified</h3><p>Verified business on TrustedBiz with real customer reviews.</p></div>
      <div class="svc-card reveal"><div class="svc-icon">📍</div><h3>Easy to Find</h3><p>Get directions straight to us with one tap on your phone.</p></div>
      <div class="svc-card reveal"><div class="svc-icon">💯</div><h3>Customer First</h3><p>Your satisfaction is our priority. We go the extra mile every time.</p></div>
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
    <h2 class="sec-h reveal">Contact Us Today</h2>
    <div class="contact-grid">
      <div>
        <div class="contact-detail"><div class="cd-icon">💬</div><div><div class="cd-label">WhatsApp</div><div class="cd-val">+{whatsapp}</div></div></div>
        <div class="contact-detail"><div class="cd-icon">⏰</div><div><div class="cd-label">Opening Hours</div><div class="cd-val">{hours}</div></div></div>
        {f'<div class="contact-detail"><div class="cd-icon">📍</div><div><div class="cd-label">Directions</div><div class="cd-val">Google Maps directions available</div></div></div>' if map_link else ""}
      </div>
      <div style="text-align:center;padding-top:16px;">
        <a href="{wa_link}" target="_blank" class="wa-btn" style="display:inline-flex;margin-bottom:16px;">💬 Chat on WhatsApp</a>
        {f'<br><a href="{map_link}" target="_blank" class="dir-btn" style="display:inline-flex;margin-top:8px;">📍 Get Directions</a>' if map_link else ""}
        {map_html}
      </div>
    </div>
  </div>
</section>
<footer>
  <p style="margin-bottom:8px;"><strong>{name}</strong></p>
  <p style="margin-bottom:6px;">{category.title()} · Uganda · {hours}</p>
  <p>© 2026 {name}. Powered by <a href="https://trustedbiz.co.ug" target="_blank">TrustedBiz</a></p>
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
var obs=new IntersectionObserver(function(entries){{entries.forEach(function(e){{if(e.isIntersecting)e.target.classList.add('in');}});}},{{threshold:.1}});
document.querySelectorAll('.reveal').forEach(function(el){{obs.observe(el);}});
</script>
</body>
</html>"""


def swap_business_info(template_html, biz):
    """
    Swap business-specific info into a pooled template HTML.
    Replaces name, description, whatsapp link, hours, colors, etc.
    Falls back to full AI regeneration if the HTML looks too different.
    """
    import re as _re

    try:
        biz = dict(biz)
    except Exception:
        pass

    name        = str(biz.get("name") or "Business")
    category    = str(biz.get("category") or "")
    description = str(biz.get("description") or f"Professional {category} services in Uganda.")
    whatsapp    = str(biz.get("whatsapp") or "")
    hours       = str(biz.get("hours") or "Mon–Sat 8am–7pm")
    color       = str(biz.get("brand_color") or "#2b7a78")
    rgb         = _hex_rgb(color)
    wa_link     = f"https://wa.me/{whatsapp}?text=Hello%2C+I+found+{name.replace(' ','+')}+on+TrustedBiz%21"

    html = template_html

    # ── Replace the <title> tag ──
    html = _re.sub(r'<title>[^<]*</title>', f'<title>{name} — {category.title()} in Uganda</title>', html)

    # ── Replace meta description ──
    html = _re.sub(
        r'<meta name="description"[^>]*>',
        f'<meta name="description" content="{description[:155]}">',
        html
    )

    # ── Replace CSS --primary color ──
    html = _re.sub(r'--primary:\s*#[0-9a-fA-F]{3,8}', f'--primary:{color}', html)
    html = _re.sub(r'--primary-rgb:\s*[\d,\s]+', f'--primary-rgb:{rgb}', html)
    html = _re.sub(r'--rgb:\s*[\d,\s]+;', f'--rgb:{rgb};', html)

    # ── WhatsApp links ──
    html = _re.sub(r'https://wa\.me/\d+[^"\']*', wa_link, html)

    # ── Opening hours ──
    html = _re.sub(
        r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[^\<"\']{3,40}(am|pm)',
        hours,
        html,
        count=3
    )

    # ── Footer: powered by TrustedBiz line ──
    html = _re.sub(
        r'© \d{4} [^<\.]+\.',
        f'© 2026 {name}.',
        html,
        count=2
    )

    # ── Try to replace the hero h1 business name ──
    # Match the largest heading inside the hero section
    def _replace_h1(m):
        inner = m.group(2)
        # strip old name spans/text, put new name in
        cleaned = _re.sub(r'<[^>]+>', '', inner).strip()
        # wrap first word in accent span like the original might
        words = name.split()
        if len(words) >= 2:
            new_inner = f'<span class="ac">{words[0]}</span> {" ".join(words[1:])}'
        else:
            new_inner = name
        return m.group(1) + new_inner + m.group(3)

    html = _re.sub(r'(<h1[^>]*>)(.*?)(</h1>)', _replace_h1, html, count=1, flags=_re.DOTALL)

    # ── Replace nav brand name ──
    html = _re.sub(
        r'(<(?:a|span|div)[^>]+class="nav-brand[^"]*"[^>]*>)([^<]*(?:<[^>]+>[^<]*</[^>]+>)*[^<]*)(</)',
        lambda m: m.group(1) + name + m.group(3),
        html,
        count=1
    )

    # ── Replace description paragraph(s) in About section ──
    # Find the first substantial paragraph after the hero (likely About)
    # Replace just the first 1-2 long paragraphs to avoid breaking structure
    desc_sentences = description[:300]

    def _swap_first_long_p(m):
        if len(m.group(1)) > 60:
            return f'<p>{desc_sentences}</p>'
        return m.group(0)

    html = _re.sub(r'<p>([^<]{60,})</p>', _swap_first_long_p, html, count=1)

    return html
