import hashlib, os

# ── helpers ──────────────────────────────────────────────────────────────────
def _daisy_hex_dark(h):
    try:
        h = h.lstrip('#')
        if len(h) == 3: h = ''.join(c*2 for c in h)
        r,g,b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
        dr,dg,db = max(0,r-40), max(0,g-40), max(0,b-40)
        return '#'+h, f"#{dr:02x}{dg:02x}{db:02x}"
    except:
        return '#2b7a78', '#1f5c5a'

def _daisy_variant(uid):
    v = [
        dict(font='DM Sans',radius='16px',weight='800',align='center',justify='center'),
        dict(font='Syne',   radius='4px', weight='900',align='left',  justify='flex-start'),
        dict(font='DM Sans',radius='50px',weight='700',align='center',justify='center'),
        dict(font='Syne',   radius='12px',weight='800',align='center',justify='center'),
        dict(font='DM Sans',radius='0px', weight='900',align='left',  justify='flex-start'),
        dict(font='DM Sans',radius='8px', weight='700',align='center',justify='center'),
        dict(font='Syne',   radius='24px',weight='800',align='center',justify='center'),
        dict(font='DM Sans',radius='2px', weight='900',align='left',  justify='flex-start'),
    ]
    return v[int(uid[:2], 16) % len(v)]

# ── Claude AI call ────────────────────────────────────────────────────────────
def _claude(prompt, max_tokens=4000):
    """Call Claude Haiku and return raw text, or None on failure."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip() if msg.content else ""
        # strip markdown fences if model added them
        import re
        text = re.sub(r'^```html\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^```\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        return text if len(text) > 200 else None
    except Exception as e:
        print(f"[Daisy/Claude] {e}")
        return None

# ── LOGO ─────────────────────────────────────────────────────────────────────
def _daisy_logo(name, color, style, uid):
    prompt = f"""You are a world-class logo designer. Create a PROFESSIONAL, UNIQUE logo page in pure HTML+CSS+SVG for:

Business name: {name}
Brand color: {color}
Style: {style}
Unique ID: {uid}

REQUIREMENTS:
1. Full standalone HTML page (<!DOCTYPE html> ... </html>)
2. Hero: large SVG logo mark — NOT just a letter. Design a real icon that fits the business name/type.
   Ideas: geometric shapes, abstract marks, monogram with design flair, icon that tells a story.
3. Show the logo in 3 variants: LIGHT background, DARK background, COLOR background
4. Business name in large, styled typography below the mark
5. Tagline: "Uganda · Verified" in small caps
6. Import Google Fonts: DM Sans + Syne
7. Brand color {color} used powerfully throughout
8. White background, clean card layout, centered
9. No lorem ipsum. No placeholder text.
10. OUTPUT: Raw HTML only. No markdown, no explanation."""

    html = _claude(prompt, max_tokens=3000)
    if html and '</html>' in html:
        return html
    return _daisy_logo_fallback(name, color, style, uid)


def _daisy_logo_fallback(name, color, style, uid):
    """Fallback logo — better than before with real geometric design."""
    name = name or 'Business'
    _, dark = _daisy_hex_dark(color)
    v = _daisy_variant(uid)
    initial = name[0].upper()
    second  = name[1].upper() if len(name) > 1 else ''

    # Pick a more interesting icon shape based on uid
    shape_idx = int(uid[2:4], 16) % 6
    shapes = [
        # Hexagon
        f'<polygon points="40,8 68,24 68,56 40,72 12,56 12,24" fill="none" stroke="{color}" stroke-width="3"/>'
        f'<text x="40" y="46" text-anchor="middle" font-size="22" fill="{color}" font-weight="900" font-family="Syne,sans-serif">{initial}{second}</text>',
        # Circle with inner ring
        f'<circle cx="40" cy="40" r="30" fill="none" stroke="{color}" stroke-width="3"/>'
        f'<circle cx="40" cy="40" r="20" fill="{color}" opacity=".12"/>'
        f'<text x="40" y="47" text-anchor="middle" font-size="20" fill="{color}" font-weight="900" font-family="Syne,sans-serif">{initial}{second}</text>',
        # Diamond
        f'<polygon points="40,8 72,40 40,72 8,40" fill="none" stroke="{color}" stroke-width="2.5"/>'
        f'<text x="40" y="46" text-anchor="middle" font-size="20" fill="{color}" font-weight="900" font-family="Syne,sans-serif">{initial}{second}</text>',
        # Rounded square with dot accent
        f'<rect x="10" y="10" width="60" height="60" rx="14" fill="{color}" opacity=".1"/>'
        f'<rect x="10" y="10" width="60" height="60" rx="14" fill="none" stroke="{color}" stroke-width="2.5"/>'
        f'<circle cx="58" cy="22" r="5" fill="{color}"/>'
        f'<text x="37" y="48" text-anchor="middle" font-size="22" fill="{color}" font-weight="900" font-family="Syne,sans-serif">{initial}{second}</text>',
        # Triangle with bar
        f'<polygon points="40,10 68,62 12,62" fill="none" stroke="{color}" stroke-width="2.5"/>'
        f'<line x1="26" y1="62" x2="54" y2="62" stroke="{color}" stroke-width="4" stroke-linecap="round"/>'
        f'<text x="40" y="55" text-anchor="middle" font-size="16" fill="{color}" font-weight="900" font-family="Syne,sans-serif">{initial}{second}</text>',
        # Cross/plus mark
        f'<rect x="34" y="8" width="12" height="64" rx="3" fill="{color}" opacity=".9"/>'
        f'<rect x="8" y="34" width="64" height="12" rx="3" fill="{color}" opacity=".9"/>'
        f'<rect x="34" y="8" width="12" height="64" rx="3" fill="none" stroke="white" stroke-width="1" opacity=".3"/>'
    ]
    icon = shapes[shape_idx]
    words = name.split()
    first = words[0]; rest = ' '.join(words[1:]) if len(words) > 1 else ''
    font = v['font']; weight = v['weight']

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{name} Logo</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;700;800&family=Syne:wght@700;800;900&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:#f5f8f8;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;font-family:'{font}',sans-serif;padding:24px;}}
.wrap{{background:#fff;border-radius:24px;padding:56px 72px;box-shadow:0 8px 48px rgba(0,0,0,.10);text-align:center;max-width:520px;width:100%;}}
.mark{{display:flex;align-items:center;justify-content:center;gap:20px;margin-bottom:10px;}}
.bname{{font-family:'Syne',sans-serif;font-size:clamp(28px,6vw,46px);font-weight:{weight};color:#0d1c1c;letter-spacing:-1.5px;line-height:1;}}
.bname em{{font-style:normal;color:{color};}}
.tag{{font-size:11px;color:#87a3a3;letter-spacing:3.5px;text-transform:uppercase;margin-top:6px;margin-bottom:40px;font-family:'DM Sans',sans-serif;}}
.variants{{display:flex;gap:16px;justify-content:center;margin-top:8px;}}
.vbox{{border-radius:14px;padding:18px 14px;text-align:center;flex:1;}}
.vlabel{{font-size:9px;letter-spacing:2px;text-transform:uppercase;margin-bottom:10px;font-family:'DM Sans',sans-serif;}}
</style></head>
<body><div class="wrap">
<div class="mark">
  <svg width="80" height="80" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">{icon}</svg>
</div>
<div class="bname"><em>{first}</em>{(' ' + rest) if rest else ''}</div>
<div class="tag">Uganda &middot; Verified</div>
<div class="variants">
  <div class="vbox" style="background:{color}15">
    <div class="vlabel" style="color:#87a3a3">LIGHT</div>
    <svg width="48" height="48" viewBox="0 0 80 80">{icon}</svg>
  </div>
  <div class="vbox" style="background:#0d1c1c">
    <div class="vlabel" style="color:#555">DARK</div>
    <svg width="48" height="48" viewBox="0 0 80 80">{icon.replace(color,'white').replace('opacity=".1"','opacity=".2"')}</svg>
  </div>
  <div class="vbox" style="background:{color}">
    <div class="vlabel" style="color:rgba(255,255,255,.65)">COLOR</div>
    <svg width="48" height="48" viewBox="0 0 80 80">{icon.replace(color,'white').replace('opacity=".1"','opacity=".25"')}</svg>
  </div>
</div>
</div>
<p style="color:#d1d5db;font-size:11px;margin-top:20px;text-align:center;font-family:'DM Sans',sans-serif">TrustedBiz Uganda &middot; {uid}</p>
</body></html>"""


# ── FLYER ─────────────────────────────────────────────────────────────────────
def _daisy_flyer(name, color, style, description, uid):
    prompt = f"""You are a world-class graphic designer. Create a STUNNING promotional flyer as a standalone HTML page for:

Business name: {name}
Brand color: {color}
Style: {style}
Description: {description}
Unique ID: {uid}

REQUIREMENTS:
1. Full standalone HTML page
2. Portrait flyer card (420×594px centered on screen)
3. Rich background — use the brand color powerfully: gradients, geometric shapes, layered CSS elements
4. Large bold business name (no clipart, pure CSS/SVG design)
5. Short punchy tagline from the description
6. "Contact Us" call-to-action
7. "TrustedBiz Uganda Verified" badge at bottom
8. Import Google Fonts: Syne + DM Sans
9. NO images or external assets beyond Google Fonts
10. Looks like a real agency-designed flyer — not a template
11. OUTPUT: Raw HTML only. No markdown."""

    html = _claude(prompt, max_tokens=2500)
    if html and '</html>' in html:
        return html
    return _daisy_flyer_fallback(name, color, style, description, uid)


def _daisy_flyer_fallback(name, color, style, description, uid):
    name = name or 'Business'
    _, dark = _daisy_hex_dark(color)
    v = _daisy_variant(uid)
    desc = description[:120] if description else 'Professional services you can trust.'
    bgs = [
        f'linear-gradient(135deg,{color} 0%,{dark} 100%)',
        f'linear-gradient(160deg,#0d1c1c 55%,{color} 100%)',
        f'radial-gradient(ellipse at 30% 40%,{color} 0%,#0d1c1c 70%)',
        f'linear-gradient(180deg,{color} 0%,{dark} 50%,#0a0a0a 100%)',
    ]
    bg = bgs[int(uid[6:8], 16) % len(bgs)]
    radius = v['radius']; font = v['font']; weight = v['weight']
    words = name.split(); first = words[0]
    rest = ' '.join(words[1:]) if len(words) > 1 else 'Uganda'
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{name} Flyer</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800;900&family=DM+Sans:wght@300;400;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:#e5e5e5;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px;}}
.flyer{{width:420px;min-height:594px;background:{bg};border-radius:{radius};padding:48px 40px;display:flex;flex-direction:column;justify-content:space-between;color:white;box-shadow:0 20px 60px rgba(0,0,0,.35);position:relative;overflow:hidden;font-family:'{font}',sans-serif;}}
.flyer::before{{content:'';position:absolute;width:300px;height:300px;border-radius:50%;border:1px solid rgba(255,255,255,.1);top:-80px;right:-60px;}}
.flyer::after{{content:'';position:absolute;width:200px;height:200px;border-radius:50%;border:1px solid rgba(255,255,255,.07);bottom:-50px;left:-30px;}}
.tag{{display:inline-block;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.25);border-radius:100px;padding:6px 16px;font-size:11px;font-weight:700;letter-spacing:2.5px;text-transform:uppercase;margin-bottom:28px;}}
h1{{font-family:'Syne',sans-serif;font-size:clamp(32px,8vw,52px);font-weight:{weight};line-height:.95;letter-spacing:-2px;margin-bottom:20px;}}
h1 span{{opacity:.55;}}
.desc{{font-size:14px;line-height:1.75;opacity:.72;font-weight:300;margin-bottom:28px;}}
.div{{width:48px;height:3px;background:rgba(255,255,255,.4);border-radius:2px;margin-bottom:24px;}}
.foot{{display:flex;align-items:center;justify-content:space-between;position:relative;z-index:1;}}
.foot-brand{{font-size:11px;opacity:.4;letter-spacing:1px;}}
.cta{{background:rgba(255,255,255,.15);border:1.5px solid rgba(255,255,255,.3);border-radius:100px;padding:9px 22px;font-size:13px;font-weight:700;}}
</style></head>
<body><div class="flyer">
<div>
  <div class="tag">&#9733; Uganda Business</div>
  <h1>{first} <span>{rest}</span></h1>
  <div class="div"></div>
  <p class="desc">{desc}</p>
</div>
<div class="foot">
  <span class="foot-brand">TRUSTEDBIZ.CO.UG</span>
  <span class="cta">Contact Us</span>
</div>
</div></body></html>"""


# ── BUSINESS CARDS ─────────────────────────────────────────────────────────────
def _daisy_cards(name, color, style, whatsapp, description, uid):
    prompt = f"""You are a world-class card designer. Create PROFESSIONAL double-sided business cards as a standalone HTML page for:

Business name: {name}
Brand color: {color}
Style: {style}
Description: {description}
WhatsApp: {whatsapp}
Unique ID: {uid}

REQUIREMENTS:
1. Full standalone HTML page
2. Show TWO cards side by side (or stacked on mobile): FRONT and BACK
3. Card size: 350×200px each
4. FRONT: Brand color background, business name large, tagline, logo mark (CSS/SVG only)
5. BACK: Clean white/light background, contact details (WhatsApp: {whatsapp}), "Uganda · Verified" 
6. Real design: geometric accents, not just plain colored rectangles
7. Import Syne + DM Sans fonts
8. "TrustedBiz Verified" badge
9. NO external images
10. OUTPUT: Raw HTML only. No markdown."""

    html = _claude(prompt, max_tokens=2500)
    if html and '</html>' in html:
        return html
    return _daisy_cards_fallback(name, color, style, whatsapp, description, uid)


def _daisy_cards_fallback(name, color, style, whatsapp, description, uid):
    name = name or 'Business'
    _, dark = _daisy_hex_dark(color)
    v = _daisy_variant(uid)
    title = description[:40] if description else 'Professional Services'
    radius = v['radius']; font = v['font']; weight = v['weight']
    initial = name[0].upper()
    wa = whatsapp or '256 XXX XXX XXX'
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{name} Business Cards</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800;900&family=DM+Sans:wght@300;400;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:#e5e5e5;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;gap:24px;padding:32px;font-family:'{font}',sans-serif;}}
.label{{font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#999;margin-bottom:8px;}}
.card{{width:350px;height:200px;border-radius:{radius};position:relative;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.2);}}
.front{{background:linear-gradient(135deg,{color},{dark});color:white;display:flex;flex-direction:column;justify-content:space-between;padding:24px 28px;}}
.front::after{{content:'{initial}';position:absolute;right:-10px;bottom:-20px;font-family:'Syne',sans-serif;font-size:120px;font-weight:900;opacity:.08;line-height:1;}}
.f-name{{font-family:'Syne',sans-serif;font-size:22px;font-weight:{weight};letter-spacing:-0.5px;}}
.f-title{{font-size:11px;opacity:.65;letter-spacing:1.5px;text-transform:uppercase;margin-top:4px;}}
.f-badge{{display:inline-flex;align-items:center;gap:5px;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.25);border-radius:100px;padding:4px 12px;font-size:9px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;}}
.back{{background:white;border:1.5px solid #e5e7eb;display:flex;flex-direction:column;justify-content:space-between;padding:24px 28px;}}
.back::before{{content:'';position:absolute;top:0;left:0;width:6px;height:100%;background:{color};}}
.b-name{{font-family:'Syne',sans-serif;font-size:16px;font-weight:700;color:#111;}}
.b-detail{{font-size:12px;color:#6b7280;margin-top:3px;}}
.b-wa{{font-size:13px;font-weight:600;color:{color};}}
.b-foot{{font-size:10px;color:#9ca3af;letter-spacing:1px;}}
</style></head>
<body>
<div>
  <div class="label">Front</div>
  <div class="card front">
    <div>
      <div class="f-name">{name}</div>
      <div class="f-title">{title}</div>
    </div>
    <div class="f-badge">&#10003; TrustedBiz Verified &middot; Uganda</div>
  </div>
</div>
<div>
  <div class="label">Back</div>
  <div class="card back">
    <div>
      <div class="b-name">{name}</div>
      <div class="b-detail">{title}</div>
    </div>
    <div>
      <div class="b-wa">&#128247; +{wa}</div>
      <div class="b-foot" style="margin-top:8px">TRUSTEDBIZ.CO.UG &middot; {uid}</div>
    </div>
  </div>
</div>
</body></html>"""


# ── CV ─────────────────────────────────────────────────────────────────────────
def _daisy_cv(ctx, uid):
    name    = str(ctx.get('fullname') or ctx.get('name') or 'Your Name')
    role    = str(ctx.get('role') or ctx.get('title') or ctx.get('description') or 'Professional')
    email   = str(ctx.get('email') or '')
    phone   = str(ctx.get('phone') or ctx.get('whatsapp') or '')
    color   = str(ctx.get('color') or '#2b7a78')
    skills  = str(ctx.get('skills') or '')

    prompt = f"""You are a professional CV/resume designer. Create a BEAUTIFUL, ATS-friendly CV as a standalone HTML page for:

Full name: {name}
Role/Title: {role}
Email: {email}
Phone/WhatsApp: {phone}
Brand color: {color}
Skills (if provided): {skills}
Unique ID: {uid}

REQUIREMENTS:
1. Full standalone HTML page — single page CV
2. Clean professional layout: colored left sidebar or top header band using {color}
3. Sections: Profile Summary, Key Skills, Experience, Education, Contact
4. Write REAL, professional content inferred from the role "{role}" — not placeholders
5. Skills section: 6-8 relevant skills for a {role} in Uganda
6. Typography: DM Sans body, Syne for name/headings
7. Print-ready: max-width 800px, clean margins
8. The design should look like a $50 Canva premium template
9. Brand color {color} used tastefully (sidebar, borders, skill tags, section titles)
10. OUTPUT: Raw HTML only. No markdown."""

    html = _claude(prompt, max_tokens=3500)
    if html and '</html>' in html:
        return html
    return _daisy_cv_fallback(ctx, uid)


def _daisy_cv_fallback(ctx, uid):
    name  = str(ctx.get('fullname') or ctx.get('name') or 'Your Name')
    role  = str(ctx.get('role') or ctx.get('title') or 'Professional')
    email = str(ctx.get('email') or '')
    phone = str(ctx.get('phone') or ctx.get('whatsapp') or '')
    color = str(ctx.get('color') or '#2b7a78')

    email_line = f'<span>&#128231; {email}</span>' if email else ''
    phone_line = f'<span>&#128247; +{phone}</span>' if phone else ''

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{name} CV</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'DM Sans',sans-serif;background:#f5f5f5;}}
.cv{{max-width:800px;margin:0 auto;background:white;box-shadow:0 4px 32px rgba(0,0,0,.08);}}
.head{{background:{color};padding:36px 44px;color:white;}}
.hname{{font-family:'Syne',sans-serif;font-size:32px;font-weight:800;letter-spacing:-1px;}}
.hrole{{font-size:14px;opacity:.78;margin-top:5px;letter-spacing:1px;text-transform:uppercase;}}
.hcon{{display:flex;flex-wrap:wrap;gap:18px;margin-top:18px;font-size:13px;opacity:.85;}}
.body{{padding:36px 44px;}}
.sec{{margin-bottom:32px;}}
.stitle{{font-size:10px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:{color};border-bottom:2px solid {color}20;padding-bottom:8px;margin-bottom:16px;}}
.item{{margin-bottom:16px;}}
.ititle{{font-weight:700;font-size:15px;}}
.isub{{font-size:13px;color:#6b7280;margin-top:2px;}}
.idesc{{font-size:13px;color:#4b5563;margin-top:6px;line-height:1.6;}}
.skills{{display:flex;flex-wrap:wrap;gap:8px;}}
.sk{{background:{color}12;border:1px solid {color}30;border-radius:100px;padding:5px 14px;font-size:12px;font-weight:600;color:{color};}}
</style></head>
<body><div class="cv">
<div class="head">
  <div class="hname">{name}</div>
  <div class="hrole">{role}</div>
  <div class="hcon">{email_line}{phone_line}<span>&#127482;&#127468; Uganda</span></div>
</div>
<div class="body">
<div class="sec"><div class="stitle">Profile</div>
  <div class="idesc">Dedicated {role.lower()} with proven expertise and commitment to quality. Based in Uganda, available locally and internationally.</div>
</div>
<div class="sec"><div class="stitle">Experience</div>
  <div class="item">
    <div class="ititle">{role}</div>
    <div class="isub">Previous Employer &middot; 2022 – Present</div>
    <div class="idesc">Led key projects delivering measurable results. Collaborated with cross-functional teams to achieve business goals on time.</div>
  </div>
</div>
<div class="sec"><div class="stitle">Education</div>
  <div class="item">
    <div class="ititle">Bachelor's Degree</div>
    <div class="isub">Makerere University &middot; 2018 – 2022</div>
  </div>
</div>
<div class="sec"><div class="stitle">Skills</div>
  <div class="skills">
    <span class="sk">Communication</span><span class="sk">Teamwork</span>
    <span class="sk">Problem Solving</span><span class="sk">Leadership</span>
    <span class="sk">Microsoft Office</span><span class="sk">Time Management</span>
  </div>
</div>
</div></div>
<p style="text-align:center;color:#d1d5db;font-size:11px;margin:16px">TrustedBiz Uganda &middot; {uid}</p>
</body></html>"""


# ── EXAM ───────────────────────────────────────────────────────────────────────
def _daisy_exam(ctx, uid):
    subject = str(ctx.get('subject') or ctx.get('topic') or 'General Knowledge')
    level   = str(ctx.get('level') or 'O-Level')

    prompt = f"""You are an experienced Uganda curriculum teacher. Create a REAL, complete exam paper as a standalone HTML page for:

Subject: {subject}
Level: {level}
Paper ID: {uid.upper()}

REQUIREMENTS:
1. Full standalone HTML page, print-ready
2. Header: "REPUBLIC OF UGANDA", subject name, level, "2026 Examination", time: 2hr 30min
3. Section A: 10 SHORT ANSWER questions (2 marks each = 20 marks total)
   - Write REAL {subject} questions appropriate for {level} level
   - Leave 2 answer lines per question
4. Section B: 4 ESSAY questions (20 marks each, answer any 3 = 60 marks)
   - Write REAL {subject} essay questions for {level}
   - Leave 8 answer lines per question
5. Instructions box at top
6. Total marks: 80
7. Typography: Georgia serif, professional exam paper look
8. OUTPUT: Raw HTML only. No markdown."""

    html = _claude(prompt, max_tokens=4000)
    if html and '</html>' in html:
        return html
    return _daisy_exam_fallback(ctx, uid)


def _daisy_exam_fallback(ctx, uid):
    subject = str(ctx.get('subject') or ctx.get('topic') or 'General Knowledge')
    level   = str(ctx.get('level') or 'O-Level')
    lines2  = '<div style="border-bottom:1px solid #ccc;height:24px;margin-bottom:2px"></div>' * 2
    lines8  = '<div style="border-bottom:1px solid #ccc;height:24px;margin-bottom:2px"></div>' * 8
    qa = ''.join([
        f'<div style="margin-bottom:18px;font-size:14px;line-height:1.7">'
        f'<span style="font-weight:bold">{i}.</span> '
        f'Write a short answer to a typical {subject} question at {level} level. <em>[2 marks]</em>'
        f'<div style="margin-top:8px">{lines2}</div></div>'
        for i in range(1, 11)
    ])
    qb = ''.join([
        f'<div style="margin-bottom:24px;font-size:14px;line-height:1.7">'
        f'<span style="font-weight:bold">{i}.</span> '
        f'Discuss an important concept in {subject} with relevant examples. <em>[20 marks]</em>'
        f'<div style="margin-top:8px">{lines8}</div></div>'
        for i in range(1, 5)
    ])
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{subject} Exam</title>
<style>body{{font-family:Georgia,serif;max-width:700px;margin:0 auto;padding:40px 24px;color:#1a1a1a;}}
.hd{{text-align:center;border-bottom:3px double #333;padding-bottom:20px;margin-bottom:24px;}}
h1{{font-size:18px;text-transform:uppercase;letter-spacing:1px;}}
.meta{{font-size:13px;margin-top:8px;color:#555;}}
.inst{{background:#f9f9f9;border:1px solid #ddd;padding:14px 18px;font-size:13px;margin-bottom:28px;}}
.stitle{{font-size:14px;font-weight:bold;text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid #333;padding-bottom:6px;margin:28px 0 16px;}}
</style></head>
<body>
<div class="hd">
  <div style="font-size:13px;color:#666;margin-bottom:8px">REPUBLIC OF UGANDA</div>
  <h1>{subject}</h1><h1>Examination Paper 2026</h1>
  <div class="meta">{level} &middot; Time: 2 Hours 30 Minutes &middot; Paper ID: {uid.upper()}</div>
</div>
<div class="inst"><strong>Instructions:</strong> Two sections. Answer ALL in Section A and any THREE in Section B.</div>
<div class="stitle">Section A — Short Answer (40 Marks)</div>
{qa}
<div class="stitle">Section B — Essay Questions (60 Marks)</div>
{qb}
<p style="text-align:center;color:#aaa;font-size:11px;margin-top:40px">TrustedBiz Uganda &middot; {uid.upper()}</p>
</body></html>"""


# ── GENERIC ────────────────────────────────────────────────────────────────────
def _daisy_generic(name, mode, color, uid):
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{name}</title>
<style>body{{font-family:sans-serif;display:flex;align-items:center;justify-content:center;
min-height:100vh;margin:0;background:#f5f8f8;}}
.b{{text-align:center;padding:48px 40px;background:#fff;border-radius:16px;
box-shadow:0 4px 24px rgba(0,0,0,.08);max-width:400px;}}
h1{{color:{color};font-size:24px;font-weight:800;margin-bottom:8px;}}
p{{color:#6b7280;font-size:14px;line-height:1.6;}}</style></head>
<body><div class="b"><div style="font-size:48px;margin-bottom:16px">&#10024;</div>
<h1>{name}</h1><p>Your {mode} is ready.</p>
<p style="margin-top:12px;font-size:12px;color:#d1d5db">TrustedBiz Uganda &middot; {uid}</p>
</div></body></html>"""
