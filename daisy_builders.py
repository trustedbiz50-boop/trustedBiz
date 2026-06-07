"""
daisy_builders.py — Daizy's production engine v3
=================================================
Claude generates professional, usable outputs.
- Logo: single clean SVG file, not a webpage
- Flyer: print-ready A5, looks like a real agency made it
- Cards: two clean business cards, front and back
- CV: single page, premium template quality
- Exam: authentic Uganda curriculum paper
- Presentation: real slides with navigation
- Catalog: mobile WhatsApp catalog
"""
import hashlib, os, re

def _uid(name, seed):
    return hashlib.md5(f"{name}{seed}".encode()).hexdigest()[:8]

_save_template_fn = None

def register_template_saver(fn):
    global _save_template_fn
    _save_template_fn = fn

def _save(mode, html):
    if _save_template_fn and html and len(html) > 300:
        try:
            _save_template_fn(mode, html)
        except Exception as e:
            print(f"[Daisy/SaveTemplate] {e}")

def _claude(prompt, max_tokens=8000):
    """Call Claude. Handles truncation. Returns output string or None."""
    client = None
    try:
        from app import get_anthropic_client
        client = get_anthropic_client()
    except Exception:
        pass
    if client is None:
        key = os.environ.get("ANTHROPIC_API_KEY","")
        if not key:
            print("[Daisy/Claude] No API key")
            return None
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
        except Exception as e:
            print(f"[Daisy/Claude] init error: {e}")
            return None
    try:
        messages = [{"role":"user","content":prompt}]
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
            messages.append({"role":"assistant","content":chunk})
            messages.append({"role":"user","content":"Continue exactly where you stopped."})

        text = full_text.strip()
        # Strip markdown fences
        text = re.sub(r'^```[a-z]*\s*','',text,flags=re.IGNORECASE)
        text = re.sub(r'\s*```$','',text)
        return text if len(text) > 200 else None
    except Exception as e:
        print(f"[Daisy/Claude] {e}")
        return None


# ── LOGO ──────────────────────────────────────────────────────────────────────

def _daisy_logo(name, color, style, uid, ctx=None):
    full_req = (ctx or {}).get('full_request') or (ctx or {}).get('description') or ''
    design_brief = f"The user specifically asked for: {full_req}" if full_req else ""

    prompt = f"""Create a professional standalone SVG logo for a business called "{name}".

Brand color: {color}
Style: {style}
{design_brief}
Size: 400x400 viewBox

RULES — follow exactly:
1. Output ONLY the SVG. Start with <svg and end with </svg>. Nothing else.
2. No HTML wrapper. No markdown. No explanation. Just the SVG.
3. Design a REAL logo mark — geometric shapes, abstract icon, or letterform with design intent. Not clip art.
4. Include the business name "{name}" as text inside the SVG using a clean sans-serif font
5. Use {color} as the primary color. Can use lighter/darker shades of it.
6. Clean white or transparent background
7. Professional enough to print on a business card, signboard or shirt
8. The design must be unique and specific to "{name}" — not generic
9. No external fonts or images — embed everything in the SVG
10. Make it look like it was designed by a professional logo designer, not generated

Output the SVG now:"""

    result = _claude(prompt, max_tokens=4000)
    if result and '<svg' in result:
        # Strip anything before the <svg tag
        svg_start = result.find('<svg')
        svg_end   = result.rfind('</svg>') + 6
        if svg_start > 0:
            result = result[svg_start:svg_end]
        # Wrap in minimal HTML for preview/download
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{name} Logo</title>
<style>
* {{ margin:0;padding:0;box-sizing:border-box; }}
body {{ background:#f8f8f8;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;font-family:sans-serif; }}
.card {{ background:#fff;border-radius:16px;padding:48px;box-shadow:0 4px 32px rgba(0,0,0,.1);text-align:center; }}
.card svg {{ width:280px;height:280px; }}
.on-dark {{ background:#111;border-radius:12px;padding:32px;margin-top:24px;display:inline-block; }}
.on-dark svg {{ width:160px;height:160px; }}
p {{ margin-top:16px;font-size:12px;color:#999;letter-spacing:1px;text-transform:uppercase; }}
</style>
</head>
<body>
<div class="card">
{result}
<p>{name} · TrustedBiz Uganda</p>
<div class="on-dark">{result}</div>
</div>
</body>
</html>"""
        _save('logo', html)
        return html
    return None


# ── FLYER ─────────────────────────────────────────────────────────────────────

def _daisy_flyer(name, color, style, description, uid):
    prompt = f"""Design a professional promotional flyer as a complete standalone HTML page.

Business: {name}
Color: {color}
Style: {style}
Description: {description}

RULES — follow exactly:
1. Output complete HTML from <!DOCTYPE html> to </html>
2. Single A5 flyer card (420×594px) centered on a neutral background
3. The flyer must look like it was designed by a professional agency in Uganda
4. Use {color} powerfully — bold gradient backgrounds, strong typography
5. Large impactful headline using the business name
6. Short punchy tagline from the description (max 8 words)
7. One clear call to action
8. "TrustedBiz Verified" small badge
9. Google Fonts via @import: Syne for headings, DM Sans for body
10. NO lorem ipsum. NO placeholder text. Real content only.
11. Design must be striking — someone should want to share it on WhatsApp
12. No external images. CSS only for decoration.

Output the HTML now:"""

    html = _claude(prompt, max_tokens=5000)
    if html and '<!DOCTYPE' in html:
        if '</html>' not in html[-100:]:
            html = html.rstrip() + "\n</body>\n</html>"
        _save('flyer', html)
        return html
    return None


# ── BUSINESS CARDS ────────────────────────────────────────────────────────────

def _daisy_cards(name, color, style, whatsapp, description, uid):
    prompt = f"""Design professional double-sided business cards as a complete standalone HTML page.

Business: {name}
Color: {color}
Style: {style}
Role/tagline: {description}
WhatsApp: +{whatsapp}

RULES — follow exactly:
1. Output complete HTML from <!DOCTYPE html> to </html>
2. Show FRONT card and BACK card side by side (stacked on mobile)
3. Card dimensions: 350×200px each
4. FRONT: {color} gradient background, business name in large bold Syne font, role/tagline, small geometric mark in SVG, "TrustedBiz ✓" badge
5. BACK: Clean white, business name in {color}, WhatsApp number prominently, "trustedbiz.co.ug", thin {color} left border accent
6. Each card must look premium — like a Moo.com or Canva premium card
7. Google Fonts: Syne + DM Sans via @import
8. Crisp typography, tight spacing, no clutter
9. No lorem ipsum. Real content only.
10. Cards must be practical — someone prints this and hands it out

Output the HTML now:"""

    html = _claude(prompt, max_tokens=4000)
    if html and '<!DOCTYPE' in html:
        if '</html>' not in html[-100:]:
            html = html.rstrip() + "\n</body>\n</html>"
        _save('cards', html)
        return html
    return None


# ── CV ────────────────────────────────────────────────────────────────────────

def _daisy_cv(ctx, uid):
    name   = str(ctx.get('fullname') or ctx.get('name') or 'Your Name')
    role   = str(ctx.get('role') or ctx.get('title') or ctx.get('description') or 'Professional')
    email  = str(ctx.get('email') or 'email@example.com')
    phone  = str(ctx.get('phone') or ctx.get('whatsapp') or '')
    color  = str(ctx.get('color') or '#2b7a78')
    skills = str(ctx.get('skills') or '')

    prompt = f"""Design a professional CV/resume as a complete standalone HTML page.

Name: {name}
Role: {role}
Email: {email}
Phone: {phone}
Color: {color}
Skills hint: {skills or 'infer from role'}

RULES — follow exactly:
1. Output complete HTML from <!DOCTYPE html> to </html>
2. Single page layout, max-width 780px, centered, print-ready
3. Top header band in {color} — name, role, contact details in white
4. Sections: Profile Summary, Key Skills (tag pills), Experience, Education
5. Write REAL professional content for a {role} working in Uganda — no placeholders
6. Skills: 6 relevant skills as colored pill badges using {color}
7. Google Fonts: DM Sans body, Syne for name
8. Design quality: looks like a ¢50,000 Canva Pro template
9. {color} for headings, skill tags, section dividers
10. This CV must be ready to send to an employer TODAY

Output the HTML now:"""

    html = _claude(prompt, max_tokens=6000)
    if html and '<!DOCTYPE' in html:
        if '</html>' not in html[-100:]:
            html = html.rstrip() + "\n</body>\n</html>"
        _save('cv', html)
        return html
    return None


# ── EXAM ──────────────────────────────────────────────────────────────────────

def _daisy_exam(ctx, uid):
    subject = str(ctx.get('subject') or ctx.get('topic') or 'General Knowledge')
    level   = str(ctx.get('level') or 'O-Level')

    prompt = f"""Create a complete, authentic Uganda curriculum exam paper as a standalone HTML page.

Subject: {subject}
Level: {level}
Year: 2026
Paper ID: {uid.upper()}

RULES — follow exactly:
1. Output complete HTML from <!DOCTYPE html> to </html>
2. Looks exactly like a real Uganda National Examinations Board paper
3. Header: REPUBLIC OF UGANDA, subject, level, time (2hrs 30min), paper ID
4. Instructions box with proper UNEB style instructions
5. Section A — 10 SHORT ANSWER questions. Real {subject} questions for {level}. 2 marks each. 2 answer lines per question.
6. Section B — 4 ESSAY questions. Real {subject} questions for {level}. 20 marks each. 8 answer lines per question.
7. Questions MUST be real, specific, curriculum-accurate — not vague
8. Georgia serif font, proper academic typography
9. Print-ready — a teacher could photocopy this tomorrow
10. Total marks: 80

Output the HTML now:"""

    html = _claude(prompt, max_tokens=8000)
    if html and '<!DOCTYPE' in html:
        if '</html>' not in html[-100:]:
            html = html.rstrip() + "\n</body>\n</html>"
        _save('exam', html)
        return html
    return None


# ── PRESENTATION ──────────────────────────────────────────────────────────────

def _daisy_presentation(ctx, uid):
    topic = str(ctx.get('description') or ctx.get('topic') or ctx.get('name') or 'Presentation')
    color = str(ctx.get('color') or '#2b7a78')
    style = str(ctx.get('style') or 'modern')

    prompt = f"""Create a professional multi-slide presentation as a complete standalone HTML page.

Topic: {topic}
Color: {color}
Style: {style}

RULES — follow exactly:
1. Output complete HTML from <!DOCTYPE html> to </html>
2. 7 slides minimum: Title, Agenda, 4 content slides, Call to Action
3. Each slide fills 100vh, clean full-screen design
4. Navigation: ← → arrow buttons + "2 / 7" counter, fixed bottom center
5. Left/right keyboard arrows also work
6. CSS transitions between slides (fade or slide)
7. {color} used boldly — full color slide backgrounds, large typography
8. Real, useful content about "{topic}" — no lorem ipsum
9. Google Fonts: Syne headings, DM Sans body via @import
10. Mobile responsive
11. Looks like a ¢200,000 PowerPoint template
12. "TrustedBiz Uganda" small footer on each slide

Output the HTML now:"""

    html = _claude(prompt, max_tokens=8000)
    if html and '<!DOCTYPE' in html:
        if '</html>' not in html[-100:]:
            html = html.rstrip() + "\n</body>\n</html>"
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
    items_text = '\n'.join([f"- {i}" for i in items]) if items else 'infer 6 products/services from the business'

    prompt = f"""Create a professional WhatsApp product catalog as a complete standalone HTML page.

Business: {name}
Description: {desc}
WhatsApp: {wa}
Color: {color}
Products/Services:
{items_text}

RULES — follow exactly:
1. Output complete HTML from <!DOCTYPE html> to </html>
2. Header: business name, colorful logo mark, "Order on WhatsApp" button → wa.me/{wa}
3. Product grid: 2 columns mobile, 3 columns desktop
4. Each product card: emoji icon, product name, 1-line description, price (UGX), "Order" button → WhatsApp
5. {color} for header, buttons, card accents
6. Clean mobile-first design — this gets shared on WhatsApp
7. Google Fonts: DM Sans via @import
8. "TrustedBiz Verified ✓" badge in header
9. Real product names and descriptions — no placeholders
10. Someone should be able to share this link and get orders TODAY

Output the HTML now:"""

    html = _claude(prompt, max_tokens=5000)
    if html and '<!DOCTYPE' in html:
        if '</html>' not in html[-100:]:
            html = html.rstrip() + "\n</body>\n</html>"
        _save('catalog', html)
        return html
    return None


# ── GENERIC ───────────────────────────────────────────────────────────────────

def _daisy_generic(name, mode, color, uid):
    prompt = f"""Create a professional {mode} as a complete standalone HTML page.

Name: {name}
Color: {color}

Output complete, professional HTML. Google Fonts (DM Sans + Syne). {color} used throughout.
Real content — no placeholders. Ready to use TODAY.
Start with <!DOCTYPE html>:"""

    html = _claude(prompt, max_tokens=5000)
    if html and '<!DOCTYPE' in html:
        if '</html>' not in html[-100:]:
            html = html.rstrip() + "\n</body>\n</html>"
        _save(mode, html)
        return html
    return None
