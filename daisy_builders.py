"""
daisy_builders.py — Daizy's production engine
==============================================
Claude (Haiku) generates everything.
No fallback templates — if Claude can't do it, we say so honestly.
Every successful output is saved to template_pool for future reuse.
"""
import hashlib, os, re

# ── Helpers ───────────────────────────────────────────────────────────────────

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
        dict(font='DM Sans', radius='16px', weight='800', align='center', justify='center'),
        dict(font='Syne',    radius='4px',  weight='900', align='left',   justify='flex-start'),
        dict(font='DM Sans', radius='50px', weight='700', align='center', justify='center'),
        dict(font='Syne',    radius='12px', weight='800', align='center', justify='center'),
        dict(font='DM Sans', radius='0px',  weight='900', align='left',   justify='flex-start'),
        dict(font='DM Sans', radius='8px',  weight='700', align='center', justify='center'),
        dict(font='Syne',    radius='24px', weight='800', align='center', justify='center'),
        dict(font='DM Sans', radius='2px',  weight='900', align='left',   justify='flex-start'),
    ]
    return v[int(uid[:2], 16) % len(v)]

def _uid(name, seed):
    return hashlib.md5(f"{name}{seed}".encode()).hexdigest()[:8]


# ── Claude caller ─────────────────────────────────────────────────────────────

def _claude(prompt, max_tokens=4000):
    """Call Claude Haiku. Returns clean HTML string or None."""
    # Try shared client from app.py first, then direct key lookup
    client = None
    try:
        from app import get_anthropic_client
        client = get_anthropic_client()
    except Exception:
        pass
    if client is None:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        print(f"[Daisy/Claude] fallback key={'SET' if key else 'MISSING'} len={len(key)}")
        if not key:
            return None
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
        except Exception as e:
            print(f"[Daisy/Claude] init error: {e}")
            return None
    try:
        import anthropic as _ant  # ensure available for type checks
        messages = [{"role": "user", "content": prompt}]
        full_text = ""
        for rnd in range(3):
            msg = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=max_tokens,
                messages=messages
            )
            chunk = msg.content[0].text if msg.content else ""
            full_text += chunk
            print(f"[Daisy/Claude] round={rnd+1} stop={msg.stop_reason} len={len(full_text)}")
            if msg.stop_reason != "max_tokens":
                break
            messages.append({"role": "assistant", "content": chunk})
            messages.append({"role": "user", "content": "Continue exactly where you stopped. Output only remaining HTML."})
        text = full_text.strip()
        text = re.sub(r'^```html\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^```\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        if text and '</html>' not in text[-200:]:
            text = text.rstrip() + "\n</body>\n</html>"
        if len(text) > 300:
            return text
        print(f"[Daisy/Claude] Too short ({len(text)} chars)")
        return None
    except Exception as e:
        print(f"[Daisy/Claude] {e}")
        return None


# ── Template saver (called back from app.py after generation) ─────────────────

_save_template_fn = None   # set by app.py on startup

def register_template_saver(fn):
    """app.py calls this with a function that saves to template_pool DB."""
    global _save_template_fn
    _save_template_fn = fn

def _save(mode, html):
    """Save a generated output to the template pool."""
    if _save_template_fn and html and len(html) > 500:
        try:
            _save_template_fn(mode, html)
        except Exception as e:
            print(f"[Daisy/SaveTemplate] {e}")


# ── LOGO ──────────────────────────────────────────────────────────────────────

def _daisy_logo(name, color, style, uid):
    prompt = f"""You are a world-class logo designer. Create a PROFESSIONAL, UNIQUE logo page in pure HTML+CSS+SVG.

Business name: {name}
Brand color: {color}
Style: {style}
Unique ID: {uid}

REQUIREMENTS:
1. Full standalone HTML page (<!DOCTYPE html> to </html>)
2. Large SVG logo mark — design a REAL icon, not just a letter. Use geometric shapes, abstract marks, or a monogram with design flair that feels intentional.
3. Show the logo in 3 variants side by side: LIGHT background, DARK (#0d1c1c) background, COLOR ({color}) background
4. Business name in large Syne font below the mark
5. Tagline: "Uganda · Verified" in small caps
6. Google Fonts: DM Sans + Syne (import via link tag)
7. Brand color {color} used powerfully
8. Clean white page, centered card layout, professional padding
9. No placeholder text. No lorem ipsum.
10. OUTPUT: Raw HTML only. Start with <!DOCTYPE html>. No markdown, no backticks."""

    html = _claude(prompt, max_tokens=3000)
    if html:
        _save('logo', html)
        return html
    return None


# ── FLYER ─────────────────────────────────────────────────────────────────────

def _daisy_flyer(name, color, style, description, uid):
    prompt = f"""You are a world-class graphic designer. Create a STUNNING promotional flyer as a standalone HTML page.

Business name: {name}
Brand color: {color}
Style: {style}
Description: {description}
Unique ID: {uid}

REQUIREMENTS:
1. Full standalone HTML page
2. Portrait flyer card (420×594px) centered on the page with a light gray background behind it
3. Rich background using {color}: bold gradients, geometric CSS shapes, layered elements — make it feel designed
4. Large bold business name as the hero text
5. Short punchy tagline pulled from the description
6. "Contact Us" call-to-action button
7. "TrustedBiz Uganda Verified" badge at the bottom
8. Google Fonts: Syne (headings) + DM Sans (body)
9. NO external images or assets beyond Google Fonts
10. Looks like a real agency flyer — each design should feel unique based on the uid {uid}
11. OUTPUT: Raw HTML only. Start with <!DOCTYPE html>. No markdown."""

    html = _claude(prompt, max_tokens=2500)
    if html:
        _save('flyer', html)
        return html
    return None


# ── BUSINESS CARDS ────────────────────────────────────────────────────────────

def _daisy_cards(name, color, style, whatsapp, description, uid):
    prompt = f"""You are a world-class card designer. Create PROFESSIONAL double-sided business cards as a standalone HTML page.

Business name: {name}
Brand color: {color}
Style: {style}
Description: {description}
WhatsApp: {whatsapp}
Unique ID: {uid}

REQUIREMENTS:
1. Full standalone HTML page
2. Two cards displayed: FRONT and BACK (side by side on desktop, stacked on mobile)
3. Card size: 350×200px each
4. FRONT: Use {color} as background via gradient, large business name in Syne font, role/tagline, small geometric logo mark in CSS/SVG
5. BACK: White/light background, left color accent strip ({color}), WhatsApp number (+{whatsapp}), "Uganda · Verified" tagline, "trustedbiz.co.ug" domain
6. Real geometric design accents — not plain rectangles
7. Google Fonts: Syne + DM Sans
8. "TrustedBiz Verified" checkmark badge on front
9. NO external images
10. OUTPUT: Raw HTML only. Start with <!DOCTYPE html>. No markdown."""

    html = _claude(prompt, max_tokens=2500)
    if html:
        _save('cards', html)
        return html
    return None


# ── CV ────────────────────────────────────────────────────────────────────────

def _daisy_cv(ctx, uid):
    name   = str(ctx.get('fullname') or ctx.get('name') or 'Your Name')
    role   = str(ctx.get('role') or ctx.get('title') or ctx.get('description') or 'Professional')
    email  = str(ctx.get('email') or '')
    phone  = str(ctx.get('phone') or ctx.get('whatsapp') or '')
    color  = str(ctx.get('color') or '#2b7a78')
    skills = str(ctx.get('skills') or '')

    prompt = f"""You are a professional CV/resume designer. Create a BEAUTIFUL, ATS-friendly CV as a standalone HTML page.

Full name: {name}
Role/Title: {role}
Email: {email}
Phone/WhatsApp: {phone}
Brand color: {color}
Skills: {skills or 'infer from role'}
Unique ID: {uid}

REQUIREMENTS:
1. Full standalone HTML page — single page CV layout
2. Colored top header band using {color} with name, role, and contact details in white
3. Sections: Profile Summary, Key Skills, Experience, Education, Contact
4. Write REAL professional content inferred from "{role}" — not generic placeholders
5. Skills: 6–8 skills relevant to a {role} in Uganda
6. Typography: DM Sans body, Syne for name and section headings
7. Max-width 800px, print-ready margins, clean layout
8. Design quality: looks like a premium Canva template
9. {color} used for sidebar accents, skill tags, section title borders
10. OUTPUT: Raw HTML only. Start with <!DOCTYPE html>. No markdown."""

    html = _claude(prompt, max_tokens=3500)
    if html:
        _save('cv', html)
        return html
    return None


# ── EXAM ──────────────────────────────────────────────────────────────────────

def _daisy_exam(ctx, uid):
    subject = str(ctx.get('subject') or ctx.get('topic') or 'General Knowledge')
    level   = str(ctx.get('level') or 'O-Level')

    prompt = f"""You are an experienced Uganda curriculum teacher. Create a REAL, complete exam paper as a standalone HTML page.

Subject: {subject}
Level: {level}
Year: 2026
Paper ID: {uid.upper()}

REQUIREMENTS:
1. Full standalone HTML page, print-ready
2. Header: "REPUBLIC OF UGANDA", subject name in capitals, level, "2026 Examination", Time: 2hrs 30min
3. Instructions box: answer ALL Section A, any THREE from Section B
4. Section A — Short Answer (40 marks): 10 REAL {subject} questions for {level}. 2 marks each. Leave 2 answer lines per question.
5. Section B — Essay Questions (60 marks): 4 REAL {subject} essay questions for {level}. 20 marks each. Leave 8 answer lines per question.
6. Questions must be AUTHENTIC — like a real Uganda national exam
7. Typography: Georgia serif, professional look like a printed exam paper
8. Total marks clearly shown: 80
9. Footer: Paper ID {uid.upper()}, "TrustedBiz Uganda"
10. OUTPUT: Raw HTML only. Start with <!DOCTYPE html>. No markdown."""

    html = _claude(prompt, max_tokens=4000)
    if html:
        _save('exam', html)
        return html
    return None


# ── PRESENTATION ──────────────────────────────────────────────────────────────

def _daisy_presentation(ctx, uid):
    name  = str(ctx.get('name') or ctx.get('topic') or 'Presentation')
    topic = str(ctx.get('description') or ctx.get('topic') or name)
    color = str(ctx.get('color') or '#2b7a78')
    style = str(ctx.get('style') or 'modern')

    prompt = f"""You are a world-class presentation designer. Create a BEAUTIFUL multi-slide presentation as a standalone HTML page.

Topic: {topic}
Brand color: {color}
Style: {style}
Unique ID: {uid}

REQUIREMENTS:
1. Full standalone HTML page with slide navigation
2. 6–8 slides: Title, Agenda, 3–4 content slides, Conclusion/CTA
3. Each slide: full viewport height (100vh), distinct section design
4. Navigation: arrow buttons (← →) and slide counter "3 / 7"
5. Keyboard navigation: left/right arrow keys
6. Slide transitions: smooth CSS fade or slide
7. Rich design: {color} used boldly, geometric backgrounds, large typography
8. Content relevant to "{topic}" — real, useful content not placeholders
9. Google Fonts: Syne (headings) + DM Sans (body)
10. Mobile responsive
11. "TrustedBiz Uganda" watermark in footer of each slide
12. OUTPUT: Raw HTML only. Start with <!DOCTYPE html>. No markdown."""

    html = _claude(prompt, max_tokens=5000)
    if html:
        _save('presentation', html)
        return html
    return None


# ── WHATSAPP CATALOG ──────────────────────────────────────────────────────────

def _daisy_catalog(ctx, uid):
    name  = str(ctx.get('name') or 'Business')
    desc  = str(ctx.get('description') or '')
    color = str(ctx.get('color') or '#2b7a78')
    wa    = str(ctx.get('whatsapp') or '')
    items = ctx.get('items') or []

    items_text = '\n'.join([f"- {i}" for i in items]) if items else '(infer 6 products/services from the business description)'

    prompt = f"""You are a product catalog designer. Create a BEAUTIFUL WhatsApp-style product catalog as a standalone HTML page.

Business name: {name}
Description: {desc}
WhatsApp: {wa}
Brand color: {color}
Products/Services:
{items_text}
Unique ID: {uid}

REQUIREMENTS:
1. Full standalone HTML page
2. Header: business name, logo mark, "Order on WhatsApp" button (wa.me/{wa})
3. Product/service grid: 2 columns on mobile, 3 on desktop
4. Each card: icon (emoji or SVG), name, short description, "Order" button linking to WhatsApp
5. Categories if applicable
6. Brand color {color} for header, buttons, accents
7. Clean, mobile-first design — this will be shared on WhatsApp
8. Google Fonts: DM Sans
9. "TrustedBiz Verified" badge in header
10. OUTPUT: Raw HTML only. Start with <!DOCTYPE html>. No markdown."""

    html = _claude(prompt, max_tokens=3500)
    if html:
        _save('catalog', html)
        return html
    return None


# ── GENERIC ───────────────────────────────────────────────────────────────────

def _daisy_generic(name, mode, color, uid):
    """Last resort — Claude tries to build anything."""
    prompt = f"""You are a skilled designer. Create a professional {mode} as a standalone HTML page.

Name/Title: {name}
Brand color: {color}
Type: {mode}
Unique ID: {uid}

Create the best possible {mode} page. Full HTML, professional design, Google Fonts (DM Sans + Syne), brand color {color} used throughout.
OUTPUT: Raw HTML only. Start with <!DOCTYPE html>. No markdown."""

    html = _claude(prompt, max_tokens=3000)
    if html:
        _save(mode, html)
        return html
    return None
