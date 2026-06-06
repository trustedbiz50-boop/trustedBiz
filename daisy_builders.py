import hashlib

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

def _daisy_logo(name, color, style, uid):
    _, dark = _daisy_hex_dark(color)
    v = _daisy_variant(uid)
    initial = name[0].upper()
    icons = [
        f'<circle cx="40" cy="40" r="32" fill="{color}" opacity=".15"/><text x="40" y="52" text-anchor="middle" font-size="30" fill="{color}" font-weight="900">{initial}</text>',
        f'<rect x="12" y="12" width="56" height="56" rx="14" fill="{color}" opacity=".12"/><text x="40" y="53" text-anchor="middle" font-size="28" fill="{color}" font-weight="900">{initial}</text>',
        f'<polygon points="40,8 72,64 8,64" fill="{color}" opacity=".12"/><text x="40" y="56" text-anchor="middle" font-size="24" fill="{color}" font-weight="900">{initial}</text>',
        f'<rect x="8" y="20" width="64" height="40" rx="6" fill="{color}" opacity=".12"/><text x="40" y="46" text-anchor="middle" font-size="26" fill="{color}" font-weight="900">{initial}</text>',
    ]
    icon = icons[int(uid[2:4], 16) % len(icons)]
    words = name.split()
    first = words[0]
    rest  = ' '.join(words[1:]) if len(words) > 1 else ''
    font = v['font']; weight = v['weight']; align = v['align']; justify = v['justify']

    css = (
        "body{background:#f5f8f8;display:flex;flex-direction:column;align-items:center;"
        f"justify-content:center;min-height:100vh;font-family:'{font}',sans-serif;padding:24px;}}"
        ".wrap{background:#fff;border-radius:20px;padding:60px 80px;"
        f"box-shadow:0 4px 40px rgba(0,0,0,.08);text-align:{align};}}"
        f".mark{{display:flex;align-items:center;gap:18px;justify-content:{justify};}}"
        f".bname{{font-size:42px;font-weight:{weight};color:#0d1c1c;letter-spacing:-1.5px;line-height:1;}}"
        f".bname em{{font-style:normal;color:{color};}}"
        ".tag{font-size:13px;color:#87a3a3;letter-spacing:3px;text-transform:uppercase;margin-top:8px;}"
        ".variants{display:flex;gap:20px;margin-top:40px;justify-content:center;}"
        ".vbox{border-radius:12px;padding:20px;text-align:center;}"
        ".vlabel{font-size:10px;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;}"
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{name} Logo</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;700;800&family=Syne:wght@700;800;900&display=swap" rel="stylesheet">
<style>*{{box-sizing:border-box;margin:0;padding:0;}}{css}</style></head>
<body><div class="wrap">
<div class="mark">
<svg width="80" height="80" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">{icon}</svg>
<div><div class="bname"><em>{first}</em>{(' '+rest) if rest else ''}</div>
<div class="tag">Uganda &middot; Verified</div></div></div>
<div class="variants">
<div class="vbox" style="background:{color}15"><div class="vlabel" style="color:#87a3a3">LIGHT</div>
<svg width="50" height="50" viewBox="0 0 80 80">{icon}</svg></div>
<div class="vbox" style="background:#0d1c1c"><div class="vlabel" style="color:#555">DARK</div>
<svg width="50" height="50" viewBox="0 0 80 80"><rect width="80" height="80" fill="#0d1c1c"/>{icon}</svg></div>
<div class="vbox" style="background:{color}"><div class="vlabel" style="color:rgba(255,255,255,.6)">COLOR</div>
<svg width="50" height="50" viewBox="0 0 80 80"><rect width="80" height="80" fill="{color}"/>
<text x="40" y="52" text-anchor="middle" font-size="30" fill="white" font-weight="900">{initial}</text></svg></div>
</div></div>
<p style="color:#d1d5db;font-size:11px;margin-top:20px;text-align:center">TrustedBiz Uganda &middot; {uid}</p>
</body></html>"""


def _daisy_flyer(name, color, style, description, uid):
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

    css = (
        "*{box-sizing:border-box;margin:0;padding:0;}"
        "body{background:#e5e5e5;display:flex;align-items:center;justify-content:center;"
        "min-height:100vh;padding:24px;}"
        f".flyer{{width:420px;min-height:594px;background:{bg};border-radius:{radius};"
        "padding:48px 40px;display:flex;flex-direction:column;justify-content:space-between;"
        f"color:white;box-shadow:0 20px 60px rgba(0,0,0,.35);position:relative;overflow:hidden;font-family:'{font}',sans-serif;}}"
        ".flyer::before{content:'';position:absolute;width:280px;height:280px;border-radius:50%;"
        "border:1px solid rgba(255,255,255,.07);top:-80px;right:-60px;pointer-events:none;}"
        ".flyer::after{content:'';position:absolute;width:180px;height:180px;border-radius:50%;"
        "border:1px solid rgba(255,255,255,.05);bottom:-50px;left:-30px;pointer-events:none;}"
        ".tag{display:inline-block;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.22);"
        "border-radius:100px;padding:6px 16px;font-size:11px;font-weight:700;letter-spacing:2px;"
        "text-transform:uppercase;margin-bottom:28px;}"
        f"h1{{font-family:'{font}',sans-serif;font-size:clamp(30px,8vw,50px);font-weight:{weight};"
        "line-height:.95;letter-spacing:-2px;margin-bottom:20px;}"
        "h1 span{opacity:.6;}"
        ".desc{font-size:14px;line-height:1.7;opacity:.72;font-weight:300;margin-bottom:28px;}"
        ".div{width:48px;height:3px;background:rgba(255,255,255,.35);border-radius:2px;margin-bottom:24px;}"
        ".foot{display:flex;align-items:center;justify-content:space-between;}"
        ".foot-brand{font-size:11px;opacity:.45;letter-spacing:1px;}"
        ".cta{background:rgba(255,255,255,.14);border:1.5px solid rgba(255,255,255,.28);"
        "border-radius:100px;padding:9px 20px;font-size:13px;font-weight:700;}"
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{name} Flyer</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800;900&family=DM+Sans:wght@300;400;600&display=swap" rel="stylesheet">
<style>{css}</style></head>
<body><div class="flyer">
<div><div class="tag">&#9733; Uganda Business</div>
<h1>{first} <span>{rest}</span></h1>
<div class="div"></div>
<p class="desc">{desc}</p></div>
<div class="foot"><span class="foot-brand">TRUSTEDBIZ.CO.UG</span>
<span class="cta">Contact Us</span></div>
</div></body></html>"""


def _daisy_cards(name, color, style, whatsapp, description, uid):
    _, dark = _daisy_hex_dark(color)
    v = _daisy_variant(uid)
    title = description[:40] if description else 'Professional Services'
    radius = v['radius']; font = v['font']; weight = v['weight']
    initial = name[0].upper()
    wa = whatsapp or '256 XXX XXX XXX'

    css = (
        "*{box-sizing:border-box;margin:0;padding:0;}"
        "body{background:#e5e5e5;display:flex;flex-direction:column;align-items:center;"
        "justify-content:center;min-height:100vh;gap:20px;padding:24px;"
        f"font-family:'{font}',sans-serif;}}"
        ".lbl{font-size:10px;color:#9ca3af;letter-spacing:2px;text-transform:uppercase;}"
        f".card{{width:340px;height:190px;border-radius:{radius};box-shadow:0 12px 40px rgba(0,0,0,.2);"
        "position:relative;overflow:hidden;display:flex;flex-direction:column;"
        "justify-content:space-between;padding:28px;}"
        f".front{{background:linear-gradient(135deg,{color},{dark});color:white;}}"
        ".front::before{content:'';position:absolute;width:180px;height:180px;border-radius:50%;"
        "border:1px solid rgba(255,255,255,.1);top:-60px;right:-40px;pointer-events:none;}"
        f".fname{{font-family:'{font}',sans-serif;font-size:22px;font-weight:{weight};letter-spacing:-.5px;}}"
        ".ftitle{font-size:12px;opacity:.65;margin-top:4px;}"
        ".ffoot{display:flex;justify-content:space-between;align-items:flex-end;}"
        ".fwa{font-size:12px;opacity:.8;}"
        ".fmark{width:36px;height:36px;background:rgba(255,255,255,.15);border-radius:8px;"
        "display:flex;align-items:center;justify-content:center;font-weight:900;font-size:16px;}"
        ".back{background:#fff;border:2px solid #f0f0f0;}"
        f".blogo{{font-family:'{font}',sans-serif;font-size:28px;font-weight:{weight};color:{color};}}"
        ".btag{font-size:11px;color:#9ca3af;letter-spacing:2px;text-transform:uppercase;}"
        ".bweb{font-size:11px;color:#d1d5db;margin-top:4px;}"
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{name} Business Card</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;600&display=swap" rel="stylesheet">
<style>{css}</style></head>
<body>
<div class="lbl">Front</div>
<div class="card front">
<div><div class="fname">{name}</div><div class="ftitle">{title}</div></div>
<div class="ffoot"><div class="fwa">&#128247; +{wa}</div><div class="fmark">{initial}</div></div>
</div>
<div class="lbl">Back</div>
<div class="card back">
<div class="blogo">{name}</div>
<div><div class="btag">Uganda &middot; TrustedBiz Verified</div><div class="bweb">trustedbiz.co.ug</div></div>
</div></body></html>"""


def _daisy_cv(ctx, uid):
    name  = str(ctx.get('name') or ctx.get('fullname') or 'Your Name')
    role  = str(ctx.get('role') or ctx.get('description') or 'Professional')
    email = str(ctx.get('email') or '')
    phone = str(ctx.get('whatsapp') or ctx.get('phone') or '')
    color = str(ctx.get('color') or '#2b7a78')
    v = _daisy_variant(uid)
    font = v['font']

    css = (
        "*{box-sizing:border-box;margin:0;padding:0;}"
        f"body{{font-family:'{font}',sans-serif;background:#f5f8f8;padding:32px 16px;color:#1a1a1a;}}"
        ".cv{max-width:700px;margin:0 auto;background:white;box-shadow:0 4px 24px rgba(0,0,0,.08);}"
        f".head{{background:{color};color:white;padding:40px 44px;}}"
        ".hname{font-size:32px;font-weight:700;letter-spacing:-.5px;}"
        ".hrole{font-size:15px;opacity:.75;margin-top:6px;}"
        ".hcon{display:flex;gap:20px;margin-top:20px;font-size:13px;opacity:.8;flex-wrap:wrap;}"
        ".body{padding:36px 44px;}"
        ".sec{margin-bottom:32px;}"
        f".stitle{{font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;"
        f"color:{color};border-bottom:2px solid {color}20;padding-bottom:8px;margin-bottom:16px;}}"
        ".item{margin-bottom:16px;}"
        ".ititle{font-weight:700;font-size:15px;}"
        ".isub{font-size:13px;color:#6b7280;margin-top:2px;}"
        ".idesc{font-size:13px;color:#4b5563;margin-top:6px;line-height:1.6;}"
        ".skills{display:flex;flex-wrap:wrap;gap:8px;}"
        f".sk{{background:{color}12;border:1px solid {color}30;border-radius:100px;"
        f"padding:5px 14px;font-size:12px;font-weight:600;color:{color};}}"
    )

    email_line = f'<span>&#128231; {email}</span>' if email else ''
    phone_line = f'<span>&#128247; +{phone}</span>' if phone else ''

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{name} CV</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>{css}</style></head>
<body><div class="cv">
<div class="head">
<div class="hname">{name}</div><div class="hrole">{role}</div>
<div class="hcon">{email_line}{phone_line}<span>&#127482;&#127468; Uganda</span></div>
</div>
<div class="body">
<div class="sec"><div class="stitle">Profile</div>
<div class="idesc">Dedicated {role.lower()} with proven expertise and a strong commitment to quality results. Based in Uganda, available locally and internationally.</div></div>
<div class="sec"><div class="stitle">Experience</div>
<div class="item"><div class="ititle">{role}</div><div class="isub">Previous Employer &middot; 2022 – Present</div>
<div class="idesc">Led key projects delivering measurable results. Collaborated with cross-functional teams to achieve business goals.</div></div></div>
<div class="sec"><div class="stitle">Education</div>
<div class="item"><div class="ititle">Bachelor's Degree</div><div class="isub">Makerere University &middot; 2018 – 2022</div></div></div>
<div class="sec"><div class="stitle">Skills</div>
<div class="skills">
<span class="sk">Communication</span><span class="sk">Teamwork</span>
<span class="sk">Problem Solving</span><span class="sk">Leadership</span>
<span class="sk">Microsoft Office</span><span class="sk">Time Management</span>
</div></div>
</div></div>
<p style="text-align:center;color:#d1d5db;font-size:11px;margin-top:16px">TrustedBiz Uganda &middot; {uid}</p>
</body></html>"""


def _daisy_exam(ctx, uid):
    subject = str(ctx.get('subject') or ctx.get('topic') or 'General Knowledge')
    level   = str(ctx.get('level') or 'O-Level')
    lines2  = '<div style="border-bottom:1px solid #ccc;height:24px;margin-bottom:2px"></div>' * 2
    lines8  = '<div style="border-bottom:1px solid #ccc;height:24px;margin-bottom:2px"></div>' * 8
    qa = ''.join([
        f'<div style="margin-bottom:18px;font-size:14px;line-height:1.7">'
        f'<span style="font-weight:bold">{i}.</span> '
        f'Write a short answer to a typical {subject} question at {level} level. <em>[2 marks]</em>'
        f'<div style="margin-top:8px">{lines2}</div></div>'
        for i in range(1,11)
    ])
    qb = ''.join([
        f'<div style="margin-bottom:24px;font-size:14px;line-height:1.7">'
        f'<span style="font-weight:bold">{i}.</span> '
        f'Discuss an important concept in {subject} with relevant examples. <em>[20 marks]</em>'
        f'<div style="margin-top:8px">{lines8}</div></div>'
        for i in range(1,5)
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


def build_route_code():
    return '''
@app.route('/daisy/build', methods=['POST'])
def daisy_build():
    from daisy_builders import (hashlib, _daisy_hex_dark, _daisy_variant,
        _daisy_logo, _daisy_flyer, _daisy_cards, _daisy_cv,
        _daisy_exam, _daisy_generic)
    data    = request.get_json() or {}
    mode    = (data.get('mode') or '').strip()
    ctx     = data.get('context') or {}
    seed    = data.get('seed') or 0
    name    = str(ctx.get('name') or ctx.get('fullname') or ctx.get('topic') or 'Business')
    color   = str(ctx.get('color') or '#2b7a78')
    style   = str(ctx.get('style') or 'modern')
    desc    = str(ctx.get('description') or '')
    wa      = str(ctx.get('whatsapp') or '')
    uid     = hashlib.md5(f"{name}{seed}".encode()).hexdigest()[:8]
    try:
        if mode == 'logo':
            html = _daisy_logo(name, color, style, uid)
        elif mode == 'flyer':
            html = _daisy_flyer(name, color, style, desc, uid)
        elif mode in ('cards','card'):
            html = _daisy_cards(name, color, style, wa, desc, uid)
        elif mode == 'cv':
            html = _daisy_cv(ctx, uid)
        elif mode == 'website':
            from ai_generator import generate_business_website
            biz = {'name':name,'category':mode,'description':desc,
                   'whatsapp':wa,'brand_color':color,'hours':ctx.get('hours','Mon-Sat 8am-7pm')}
            html = generate_business_website(biz, 'basic')
        elif mode == 'exam':
            html = _daisy_exam(ctx, uid)
        else:
            html = _daisy_generic(name, mode, color, uid)
        return jsonify({'html':html,'mode':mode,'uid':uid})
    except Exception as e:
        print(f'[Daisy/Build] {e}')
        return jsonify({'html':_daisy_generic(name, mode, color, uid),'mode':mode,'uid':uid})
'''

