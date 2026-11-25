"""
mascot.py — "Crest", the TrustedBiz crested crane (Uganda's national bird).

Everything is hand-built SVG so there are no image files to upload or load. The art
is parameterised by *pose*, so the character shows what is really happening:

    wave     greeting (home, empty states)          sleep    project paused
    happy    success / celebration                  wrench   maintenance mode
    deliver  carrying a ZIP (uploading / deploying) oops     errors and 404
    fly      flying (Paid, speed)                   think    loading / waiting
    egg      sitting on an egg (app waiting for its server to launch)
    lost     holding a map (nothing found)          ok       all systems operational
    flock    three cranes (Teams)

Templates use:   {{ crest('wave', size=220) }}         full character
                 {{ crest('happy', crop='face') }}      head only (used in popups)
                 {{ scene_deploy() }}                   the animated "ZIP to live" scene
                 {{ icon('upload') }}                   small cartoon icons

CSS for all animations lives in templates/_cartoon_css.html and respects
prefers-reduced-motion.
"""
import itertools
from markupsafe import Markup

OUT = "#14302f"
BODY, BODY_D, BELLY = "#93a8bb", "#7a90a5", "#e8eff4"
GOLD, GOLD_D, RED = "#ffc933", "#f2a900", "#e5432f"
BEAK, BLUSH = "#2f3a3a", "#ff9fa8"

_ids = itertools.count(1)


def _path(d, fill, sw=4, extra=""):
    return (f'<path d="{d}" fill="{fill}" stroke="{OUT}" stroke-width="{sw}" '
            f'stroke-linejoin="round" stroke-linecap="round" {extra}/>')


def _crown():
    out = []
    for i, ang in enumerate((-74, -56, -38, -19, 0, 19, 38, 56, 74)):
        s = 1.18 - abs(ang) / 74 * 0.34
        out.append(f'<g transform="translate(120 66) rotate({ang}) scale({s:.2f})">'
                   f'{_path("M0 4 C-7 -8 -6 -26 0 -42 C6 -26 7 -8 0 4Z", GOLD, 3)}</g>')
    return f'<g class="cr-crown">{"".join(out)}</g>'


def _eye(cx, cy, kind):
    if kind == "joy":
        return f'<path d="M{cx-9} {cy+4} Q{cx} {cy-9} {cx+9} {cy+4}" fill="none" stroke="{OUT}" stroke-width="4.5" stroke-linecap="round"/>'
    if kind == "closed":
        return f'<path d="M{cx-9} {cy-1} Q{cx} {cy+8} {cx+9} {cy-1}" fill="none" stroke="{OUT}" stroke-width="4.5" stroke-linecap="round"/>'
    dx, dy, pr, er = 0, 0, 5.5, 10
    if kind == "up":
        dx, dy = -2, -3.5
    elif kind == "side":
        dx, dy = 3.5, 0
    elif kind == "wide":
        pr, er = 3.4, 12.5
    return (f'<g class="cr-eye"><circle cx="{cx}" cy="{cy}" r="{er}" fill="#fff" stroke="{OUT}" stroke-width="3.5"/>'
            f'<circle cx="{cx+dx}" cy="{cy+dy}" r="{pr}" fill="{OUT}"/>'
            f'<circle cx="{cx+dx+1.8}" cy="{cy+dy-2}" r="1.8" fill="#fff"/></g>')


def _beak(mouth):
    wattle = _path("M107 126 Q120 154 133 126 Q120 119 107 126Z", RED, 3)
    if mouth == "open":
        return (wattle + _path("M109 110 Q120 103 131 110 Q126 119 120 121 Q114 119 109 110Z", BEAK, 3)
                + f'<ellipse cx="120" cy="127" rx="9" ry="7.5" fill="#7a1f1f" stroke="{OUT}" stroke-width="3" class="cr-mouth"/>'
                + '<ellipse cx="120" cy="130" rx="5" ry="3.2" fill="#ff8b94"/>')
    if mouth == "o":
        return (wattle + _path("M110 110 Q120 104 130 110 Q125 119 120 121 Q115 119 110 110Z", BEAK, 3)
                + f'<ellipse cx="120" cy="127" rx="5.5" ry="6.5" fill="#7a1f1f" stroke="{OUT}" stroke-width="3"/>')
    return wattle + _path("M109 108 Q120 101 131 108 Q126 124 120 129 Q114 124 109 108Z", BEAK, 3)


_WING = ("M72 136 C44 138 30 168 36 194 C40 210 58 214 66 202 C78 184 86 160 84 146 C82 140 78 136 72 136Z")


def _wing(side, rot, scale=1.0):
    pivot_x = 70 if side == "L" else 170
    inner = (_path(_WING, BODY_D, 4)
             + _path("M37 196 C40 210 58 214 66 202 C56 208 46 205 37 196Z", GOLD, 3)
             + f'<path d="M45 178 Q54 186 64 184 M43 164 Q52 171 62 169" fill="none" stroke="{OUT}" stroke-width="3" stroke-linecap="round"/>')
    if side == "R":
        inner = f'<g transform="translate(240 0) scale(-1 1)">{inner}</g>'
    return (f'<g class="cr-wing cr-wing-{side.lower()}" style="--rot:{rot}deg;--sc:{scale};'
            f'transform-origin:{pivot_x}px 146px">{inner}</g>')


# ── props and effects ────────────────────────────────────────────────────────
def _zip_box(x=88, y=170):
    return (f'<g class="cr-zip"><rect x="{x}" y="{y}" width="64" height="48" rx="8" fill="#f6c36b" stroke="{OUT}" stroke-width="4"/>'
            f'<path d="M{x+32} {y} V{y+48}" stroke="#e08a2b" stroke-width="7"/>'
            f'<rect x="{x+14}" y="{y+16}" width="36" height="18" rx="5" fill="#fff" stroke="{OUT}" stroke-width="3"/>'
            f'<text x="{x+32}" y="{y+30}" text-anchor="middle" font-family="Fredoka,DM Sans,sans-serif" font-weight="700" font-size="13" fill="{OUT}">ZIP</text></g>')


def _wrench():
    return (f'<g transform="translate(206 150) rotate(38)"><rect x="-5" y="-4" width="10" height="46" rx="5" fill="#b9c4cc" stroke="{OUT}" stroke-width="3.5"/>'
            f'<path d="M-12 -4 L-12 -22 Q-12 -30 -4 -30 L-4 -20 L4 -20 L4 -30 Q12 -30 12 -22 L12 -4Z" fill="#b9c4cc" stroke="{OUT}" stroke-width="3.5" stroke-linejoin="round"/></g>')


def _map():
    return (f'<g transform="translate(196 176) rotate(14)"><rect x="-26" y="-20" width="52" height="40" rx="5" fill="#fff3c9" stroke="{OUT}" stroke-width="3.5"/>'
            f'<path d="M-9 -20 V20 M9 -20 V20" stroke="#e0cf94" stroke-width="3"/>'
            f'<path d="M-16 -4 L-6 6 M-6 -4 L-16 6" stroke="{RED}" stroke-width="4" stroke-linecap="round"/>'
            f'<path d="M4 8 Q12 -8 20 4" stroke="{OUT}" stroke-width="2.5" stroke-dasharray="4 4" fill="none"/></g>')


def _nest_and_egg():
    straw = "".join(f'<path d="M{x} {y} q10 -6 22 0" stroke="#8a5a2b" stroke-width="3" fill="none" stroke-linecap="round"/>'
                    for x, y in ((56, 222), (84, 230), (120, 232), (150, 226), (70, 238), (110, 242), (142, 238)))
    nest = (f'<g class="cr-nest"><path d="M40 218 Q120 196 200 218 Q204 246 120 252 Q36 246 40 218Z" fill="#d49a58" stroke="{OUT}" stroke-width="4" stroke-linejoin="round"/>{straw}</g>')
    egg = (f'<g class="cr-egg"><path d="M206 208 C186 208 180 236 192 246 C200 252 214 252 222 246 C232 236 226 208 206 208Z" fill="#fff8ec" stroke="{OUT}" stroke-width="4"/>'
           f'<circle cx="199" cy="226" r="3" fill="#e6d3b3"/><circle cx="212" cy="236" r="2.5" fill="#e6d3b3"/>'
           f'<path d="M193 224 l6 -6 l5 7 l6 -7 l7 8" fill="none" stroke="{OUT}" stroke-width="2.5" stroke-linejoin="round"/></g>')
    return nest, egg


def _star(x, y, s, cls="cr-spark", delay=0):
    return (f'<g class="{cls}" style="animation-delay:{delay}s;transform-origin:{x}px {y}px"><path d="M{x} {y-s} Q{x} {y} {x+s} {y} Q{x} {y} {x} {y+s} Q{x} {y} {x-s} {y} Q{x} {y} {x} {y-s}Z" fill="#fff" stroke="{OUT}" stroke-width="2.5" stroke-linejoin="round"/></g>')


def _fx(name):
    if name == "sparkle":
        return _star(200, 66, 9) + _star(36, 92, 7, delay=.6) + _star(190, 112, 5, delay=1.2)
    if name == "confetti":
        cols = (RED, GOLD, "#3ec6a8", "#7aa7ff", "#ff9fa8")
        out = []
        for i, (x, y) in enumerate(((40, 40), (70, 14), (110, 6), (150, 10), (188, 34), (210, 78), (24, 90), (96, 30))):
            c = cols[i % len(cols)]
            shape = (f'<rect x="{x}" y="{y}" width="9" height="13" rx="2" fill="{c}" stroke="{OUT}" stroke-width="2" transform="rotate({i*37} {x} {y})"/>'
                     if i % 2 else f'<circle cx="{x}" cy="{y}" r="5" fill="{c}" stroke="{OUT}" stroke-width="2"/>')
            out.append(f'<g class="cr-conf" style="animation-delay:{i*0.18:.2f}s">{shape}</g>')
        return "".join(out)
    if name == "thought":
        return (f'<circle cx="176" cy="64" r="5" fill="#fff" stroke="{OUT}" stroke-width="2.5"/><circle cx="190" cy="48" r="8" fill="#fff" stroke="{OUT}" stroke-width="2.5"/>'
                f'<g class="cr-think"><ellipse cx="212" cy="22" rx="24" ry="17" fill="#fff" stroke="{OUT}" stroke-width="3"/>'
                f'<circle cx="202" cy="22" r="3" fill="{OUT}"/><circle cx="212" cy="22" r="3" fill="{OUT}"/><circle cx="222" cy="22" r="3" fill="{OUT}"/></g>')
    if name == "zzz":
        return "".join(f'<text class="cr-z" x="{x}" y="{y}" style="animation-delay:{d}s" font-family="Fredoka,DM Sans,sans-serif" font-weight="700" font-size="{s}" fill="#fff" stroke="{OUT}" stroke-width="2.4" paint-order="stroke">z</text>'
                       for x, y, s, d in ((176, 74, 20, 0), (192, 52, 26, .8), (212, 26, 32, 1.6)))
    if name == "gear":
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in _gear_pts(0, 0, 14, 10, 8))
        return (f'<g transform="translate(206 52)"><g class="cr-gear"><polygon points="{pts}" fill="#ffc933" stroke="{OUT}" stroke-width="3" stroke-linejoin="round"/>'
                f'<circle r="4.5" fill="#fff" stroke="{OUT}" stroke-width="2.5"/></g></g>')
    if name == "sweat":
        return (f'<path class="cr-sweat" d="M172 60 q-7 10 0 16 q7 -6 0 -16Z" fill="#8fd3ff" stroke="{OUT}" stroke-width="2.5" stroke-linejoin="round"/>'
                f'<path class="cr-sweat" style="animation-delay:.5s" d="M62 74 q-7 10 0 16 q7 -6 0 -16Z" fill="#8fd3ff" stroke="{OUT}" stroke-width="2.5" stroke-linejoin="round"/>')
    if name == "bang":
        return (f'<g class="cr-pop"><path d="M196 10 l6 16 l16 -4 l-8 14 l14 8 l-17 3 l2 17 l-12 -12 l-12 12 l1 -17 l-17 -3 l14 -8 l-8 -14 l16 4Z" fill="{GOLD}" stroke="{OUT}" stroke-width="3" stroke-linejoin="round" transform="scale(.8) translate(40 6)"/>'
                f'<text x="206" y="40" text-anchor="middle" font-family="Fredoka,DM Sans,sans-serif" font-weight="700" font-size="24" fill="{OUT}">!</text></g>')
    if name == "speed":
        return "".join(f'<path class="cr-speed" style="animation-delay:{d}s" d="M{x} {y} h{l}" stroke="{OUT}" stroke-width="4" stroke-linecap="round" opacity=".5"/>'
                       for x, y, l, d in ((10, 120, 28, 0), (0, 160, 40, .25), (14, 200, 24, .5)))
    if name == "qmark":
        return "".join(f'<text class="cr-q" x="{x}" y="{y}" style="animation-delay:{d}s" font-family="Fredoka,DM Sans,sans-serif" font-weight="700" font-size="{s}" fill="{GOLD}" stroke="{OUT}" stroke-width="2.6" paint-order="stroke">?</text>'
                       for x, y, s, d in ((44, 56, 28, 0), (182, 40, 34, .7)))
    if name == "check":
        return (f'<g class="cr-pop"><circle cx="196" cy="70" r="17" fill="#3ec67f" stroke="{OUT}" stroke-width="3.5"/>'
                f'<path d="M187 70 l7 7 l12 -14" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></g>')
    return ""


def _gear_pts(cx, cy, r_out, r_in, teeth):
    import math
    pts = []
    for i in range(teeth * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.pi * i / teeth
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


POSES = {
    "wave":    dict(L=4, R=-118, eyes="open", mouth="closed", fx=("sparkle",), anim="wave"),
    "happy":   dict(L=112, R=-112, eyes="joy", mouth="open", fx=("confetti",), anim="hop"),
    "think":   dict(L=4, R=-150, eyes="up", mouth="closed", fx=("thought",)),
    "sleep":   dict(L=2, R=-2, eyes="closed", mouth="closed", fx=("zzz",), anim="breathe"),
    "wrench":  dict(L=4, R=-52, eyes="open", mouth="closed", prop="wrench", fx=("gear",)),
    "oops":    dict(L=146, R=-146, eyes="wide", mouth="o", fx=("sweat", "bang"), anim="shake"),
    "deliver": dict(L=-24, R=24, eyes="open", mouth="closed", prop="zip"),
    "fly":     dict(L=82, R=-82, scale=1.3, eyes="open", mouth="closed", fx=("speed",), tilt=-9, anim="float", shadow=False),
    "egg":     dict(L=4, R=-4, eyes="open", mouth="closed", prop="nest", lower=10),
    "lost":    dict(L=4, R=-38, eyes="side", mouth="closed", prop="map", fx=("qmark",)),
    "ok":      dict(L=4, R=-118, eyes="joy", mouth="closed", fx=("check", "sparkle"), anim="wave"),
}


def _inner(pose, face=False):
    c = POSES[pose]
    nest = egg = ""
    if c.get("prop") == "nest":
        nest, egg = _nest_and_egg()
    legs = (f'<g stroke="#2d3b3b" stroke-width="7" stroke-linecap="round"><path d="M104 206 V238"/><path d="M136 206 V238"/></g>'
            f'<path d="M90 241 Q104 232 118 241 Q104 247 90 241Z M122 241 Q136 232 150 241 Q136 247 122 241Z" fill="#3a4a4a" stroke="{OUT}" stroke-width="3" stroke-linejoin="round"/>')
    tail = (_path("M150 188 C180 182 200 194 204 212 C180 214 162 208 148 202Z", GOLD, 4)
            + _path("M150 172 C178 160 202 168 208 186 C184 192 166 188 150 184Z", GOLD_D, 4))
    body = _path("M120 112 C70 112 50 160 58 192 C66 222 96 232 120 232 C144 232 174 222 182 192 C190 160 170 112 120 112Z", BODY, 4)
    belly = '<ellipse cx="120" cy="190" rx="38" ry="36" fill="%s"/>' % BELLY
    belly += f'<path d="M104 176 q6 6 12 0 M124 176 q6 6 12 0 M114 196 q6 6 12 0" fill="none" stroke="#c4d2dc" stroke-width="3" stroke-linecap="round"/>'
    head = (_crown()
            + _path("M120 50 C146 50 166 70 166 96 C166 122 146 142 120 142 C94 142 74 122 74 96 C74 70 94 50 120 50Z", "#a9bccb", 4)
            + '<path d="M82 78 C90 56 150 56 158 78 C146 68 94 68 82 78Z" fill="#1f2a2a"/>'
            + f'<ellipse cx="120" cy="104" rx="37" ry="31" fill="#fff" stroke="{OUT}" stroke-width="3"/>'
            + _eye(102, 99, c["eyes"]) + _eye(138, 99, c["eyes"])
            + f'<circle cx="86" cy="114" r="7" fill="{BLUSH}" opacity=".85"/><circle cx="154" cy="114" r="7" fill="{BLUSH}" opacity=".85"/>'
            + _beak(c["mouth"]))
    wl, wr = _wing("L", c["L"], c.get("scale", 1.0)), _wing("R", c["R"], c.get("scale", 1.0))
    prop = {"zip": _zip_box(), "wrench": _wrench(), "map": _map()}.get(c.get("prop"), "")
    # In a head-only crop, big floating props (bubbles, z, ?, !) would be cut off, so skip them.
    fx = "".join(_fx(n) for n in c.get("fx", ()) if not (face and n in ("thought", "zzz", "bang", "qmark", "gear", "speed")))
    shadow = '<ellipse class="cr-shadow" cx="120" cy="246" rx="64" ry="9" fill="#14302f" opacity=".16"/>' if c.get("shadow", True) else ""
    lower = c.get("lower", 0)
    tilt = c.get("tilt", 0)
    anim = c.get("anim", "idle")
    return (f'{shadow}<g class="cr-body cr-{anim}" style="transform-origin:120px 238px" transform="translate(0 {lower}) rotate({tilt} 120 200)">'
            f'{tail}{legs}{body}{belly}{wl}{wr}{head}{nest}{prop}</g>{egg}{fx}')


def crest(pose="wave", size=None, cls="", crop=None, label=None):
    """Full character, or crop='face' for the head only (used in popups)."""
    if pose == "flock":
        return _flock(size, cls)
    if pose not in POSES:
        pose = "wave"
    vb = "0 0 240 260" if crop != "face" else "46 14 148 148"
    w = f' width="{size}"' if size else ""
    aria = f'role="img" aria-label="{label}"' if label else 'aria-hidden="true"'
    face = " crest-face" if crop == "face" else ""
    return Markup(f'<svg class="crest crest-{pose}{face} {cls}" viewBox="{vb}"{w} {aria} xmlns="http://www.w3.org/2000/svg">{_inner(pose, face=(crop == "face"))}</svg>')


def _flock(size, cls):
    w = f' width="{size}"' if size else ""
    return Markup(
        f'<svg class="crest crest-flock {cls}" viewBox="0 0 520 280"{w} aria-hidden="true" xmlns="http://www.w3.org/2000/svg">'
        f'<g transform="translate(0 40) scale(.8)">{_inner("wave")}</g>'
        f'<g transform="translate(150 0)">{_inner("happy")}</g>'
        f'<g transform="translate(330 40) scale(.8)">{_inner("deliver")}</g></svg>')


# ── scene: a ZIP is carried to a site and it goes live ───────────────────────
def scene_deploy(cls=""):
    n = next(_ids)
    sky = f"sky{n}"
    hills = (f'<path d="M0 262 C90 214 170 228 250 250 C330 270 420 226 520 244 V340 H0Z" fill="#8ee0b1" stroke="{OUT}" stroke-width="4" stroke-linejoin="round"/>'
             f'<path d="M0 296 C110 262 200 286 300 290 C390 294 450 274 520 284 V340 H0Z" fill="#5fcf98" stroke="{OUT}" stroke-width="4" stroke-linejoin="round"/>')
    tufts = "".join(f'<path d="M{x} {y} l4 -12 l5 12 l5 -14 l4 14" fill="none" stroke="{OUT}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
                    for x, y in ((46, 300), (190, 306), (470, 300), (300, 312)))
    cloud = lambda x, y, s, d: (f'<g class="sc-cloud" style="animation-delay:{d}s"><g transform="translate({x} {y}) scale({s})">'
                                f'<path d="M0 30 C-6 14 12 4 24 14 C30 -4 58 -2 62 18 C78 14 90 30 76 38 H6 C0 38 -2 34 0 30Z" fill="#fff" stroke="{OUT}" stroke-width="4" stroke-linejoin="round"/></g></g>')
    sun = (f'<g class="sc-sun" style="transform-origin:436px 70px"><circle cx="436" cy="70" r="30" fill="{GOLD}" stroke="{OUT}" stroke-width="4"/>'
           + "".join(f'<path d="M436 {70-44} v-10" stroke="{OUT}" stroke-width="4" stroke-linecap="round" transform="rotate({a} 436 70)"/>' for a in range(0, 360, 45))
           + f'<circle cx="426" cy="66" r="3.5" fill="{OUT}"/><circle cx="446" cy="66" r="3.5" fill="{OUT}"/><path d="M426 78 Q436 87 446 78" fill="none" stroke="{OUT}" stroke-width="3.5" stroke-linecap="round"/></g>')
    phone = (f'<g transform="translate(26 176)"><rect x="0" y="0" width="64" height="112" rx="14" fill="#2b3f3e" stroke="{OUT}" stroke-width="4"/>'
             f'<rect x="7" y="12" width="50" height="82" rx="6" fill="#d6f4ee"/><rect x="22" y="4" width="20" height="4" rx="2" fill="#6f8c8b"/>'
             f'<rect x="16" y="30" width="32" height="26" rx="5" fill="#f6c36b" stroke="{OUT}" stroke-width="3"/><path d="M32 30 V56" stroke="#e08a2b" stroke-width="5"/>'
             f'<path d="M24 70 h16" stroke="{OUT}" stroke-width="3" stroke-linecap="round"/><path d="M26 78 h12" stroke="#7aa7a1" stroke-width="3" stroke-linecap="round"/></g>')
    win = (f'<g transform="translate(324 134)"><g class="sc-win"><rect x="0" y="0" width="170" height="130" rx="16" fill="#fff" stroke="{OUT}" stroke-width="4"/>'
           f'<path d="M0 30 H170" stroke="{OUT}" stroke-width="4"/><path d="M2 16 a14 14 0 0 1 14 -14 H154 a14 14 0 0 1 14 14 V30 H2Z" fill="#ffe08a"/>'
           f'<circle cx="18" cy="16" r="5" fill="{RED}" stroke="{OUT}" stroke-width="2.5"/><circle cx="34" cy="16" r="5" fill="{GOLD}" stroke="{OUT}" stroke-width="2.5"/><circle cx="50" cy="16" r="5" fill="#3ec67f" stroke="{OUT}" stroke-width="2.5"/>'
           f'<rect x="64" y="9" width="92" height="14" rx="7" fill="#fff" stroke="{OUT}" stroke-width="2.5"/>'
           f'<rect x="16" y="44" width="70" height="12" rx="6" fill="#bfe9ff"/><rect x="16" y="64" width="110" height="9" rx="4.5" fill="#e4eef2"/><rect x="16" y="80" width="96" height="9" rx="4.5" fill="#e4eef2"/>'
           f'<rect x="16" y="98" width="52" height="20" rx="10" fill="#1f9d8f" stroke="{OUT}" stroke-width="3"/>'
           f'<circle cx="132" cy="102" r="14" fill="{GOLD}" stroke="{OUT}" stroke-width="3"/><circle cx="127" cy="99" r="2.2" fill="{OUT}"/><circle cx="137" cy="99" r="2.2" fill="{OUT}"/><path d="M126 106 Q132 112 138 106" fill="none" stroke="{OUT}" stroke-width="2.6" stroke-linecap="round"/></g>'
           f'<g class="sc-live" style="transform-origin:150px 6px"><g transform="translate(150 6) rotate(10)"><rect x="-34" y="-15" width="68" height="30" rx="9" fill="{RED}" stroke="{OUT}" stroke-width="4"/>'
           f'<text x="0" y="6" text-anchor="middle" font-family="Fredoka,DM Sans,sans-serif" font-weight="700" font-size="17" fill="#fff" letter-spacing="1">LIVE</text></g></g>'
           + "".join(f'<g class="sc-conf sc-conf-{i}"><circle cx="{20+i*26}" cy="-4" r="4.5" fill="{c}" stroke="{OUT}" stroke-width="2"/></g>'
                     for i, c in enumerate((RED, GOLD, "#3ec6a8", "#7aa7ff", "#ff9fa8", GOLD)))
           + '</g>')
    flight = (f'<g transform="translate(46 150)"><g class="sc-fly"><g transform="scale(.46)">{_inner("fly")}</g>'
              f'<g class="sc-box"><g transform="translate(34 78) scale(.5)">{_zip_box(0, 0)}</g></g></g></g>')
    return Markup(
        f'<svg class="scene {cls}" viewBox="0 0 520 340" role="img" aria-label="A crane carries a ZIP file to a website, which goes live" xmlns="http://www.w3.org/2000/svg">'
        f'<defs><linearGradient id="{sky}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b9e8ff"/><stop offset="1" stop-color="#fff2cc"/></linearGradient></defs>'
        f'<rect x="2" y="2" width="516" height="336" rx="28" fill="url(#{sky})" stroke="{OUT}" stroke-width="4"/>'
        f'<clipPath id="clip{n}"><rect x="2" y="2" width="516" height="336" rx="28"/></clipPath>'
        f'<g clip-path="url(#clip{n})">{sun}{cloud(60, 36, 1, 0)}{cloud(250, 70, .8, -4)}{cloud(380, 22, .6, -8)}{hills}{tufts}{phone}{win}{flight}</g></svg>')


# ── little cartoon icons ─────────────────────────────────────────────────────
_ICONS = {
    "upload": (f'<path d="M18 44 C6 44 6 26 20 26 C22 12 44 12 46 26 C58 26 58 44 46 44Z" fill="#fff" stroke="{OUT}" stroke-width="3.5" stroke-linejoin="round"/>'
               f'<path d="M32 52 V30 M23 38 L32 29 L41 38" fill="none" stroke="{OUT}" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round"/>'
               '<path d="M32 52 V30 M23 38 L32 29 L41 38" fill="none" stroke="#1f9d8f" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'),
    "globe": (f'<circle cx="32" cy="32" r="22" fill="#7bd3f7" stroke="{OUT}" stroke-width="3.5"/>'
              f'<path d="M20 22 q8 -4 12 2 q-2 8 -10 6 q-6 -2 -2 -8Z M36 38 q8 -2 10 4 q-4 8 -10 4 q-4 -4 0 -8Z" fill="#6fd09a" stroke="{OUT}" stroke-width="2.5" stroke-linejoin="round"/>'
              '<path d="M24 20 q-3 -2 -4 -5" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" opacity=".7"/>'),
    "coin": (f'<circle cx="32" cy="32" r="22" fill="{GOLD}" stroke="{OUT}" stroke-width="3.5"/><circle cx="32" cy="32" r="15" fill="none" stroke="{GOLD_D}" stroke-width="3"/>'
             f'<text x="32" y="37" text-anchor="middle" font-family="Fredoka,DM Sans,sans-serif" font-weight="700" font-size="14" fill="{OUT}">UGX</text>'),
    "git": (f'<path d="M20 14 V50 M20 30 C20 40 44 34 44 20" fill="none" stroke="{OUT}" stroke-width="3.5" stroke-linecap="round"/>'
            f'<circle cx="20" cy="14" r="7" fill="#fff" stroke="{OUT}" stroke-width="3.5"/><circle cx="20" cy="50" r="7" fill="{GOLD}" stroke="{OUT}" stroke-width="3.5"/><circle cx="44" cy="20" r="7" fill="#3ec6a8" stroke="{OUT}" stroke-width="3.5"/>'),
    "shield": (f'<path d="M32 8 L52 16 V32 C52 46 42 54 32 58 C22 54 12 46 12 32 V16Z" fill="#1f9d8f" stroke="{OUT}" stroke-width="3.5" stroke-linejoin="round"/>'
               '<path d="M22 32 l8 8 l14 -16" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>'),
    "db": (f'<path d="M12 18 C12 8 52 8 52 18 V46 C52 56 12 56 12 46Z" fill="#7aa7ff" stroke="{OUT}" stroke-width="3.5" stroke-linejoin="round"/>'
           f'<ellipse cx="32" cy="18" rx="20" ry="8" fill="#b7d0ff" stroke="{OUT}" stroke-width="3.5"/>'
           f'<path d="M12 31 C12 41 52 41 52 31" fill="none" stroke="{OUT}" stroke-width="3"/><circle cx="42" cy="44" r="2.6" fill="{OUT}"/>'),
    "kv": (f'<circle cx="22" cy="32" r="13" fill="{GOLD}" stroke="{OUT}" stroke-width="3.5"/><circle cx="22" cy="32" r="4.5" fill="#fff" stroke="{OUT}" stroke-width="3"/>'
           f'<path d="M34 32 H56 M48 32 V42 M56 32 V40" fill="none" stroke="{OUT}" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round"/>'
           f'<path d="M34 32 H56 M48 32 V42 M56 32 V40" fill="none" stroke="{GOLD}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'),
    "rocket": (f'<path d="M32 6 C44 14 46 32 40 44 H24 C18 32 20 14 32 6Z" fill="#fff" stroke="{OUT}" stroke-width="3.5" stroke-linejoin="round"/>'
               f'<circle cx="32" cy="26" r="6" fill="#7bd3f7" stroke="{OUT}" stroke-width="3"/>'
               f'<path d="M24 36 L14 46 L24 44Z M40 36 L50 46 L40 44Z" fill="{RED}" stroke="{OUT}" stroke-width="3" stroke-linejoin="round"/>'
               f'<path d="M27 46 Q32 60 37 46Z" fill="{GOLD}" stroke="{OUT}" stroke-width="3" stroke-linejoin="round" class="cr-flame"/>'),
}


def icon(name, size=56, cls=""):
    body = _ICONS.get(name, "")
    return Markup(f'<svg class="ico-art {cls}" viewBox="0 0 64 64" width="{size}" height="{size}" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">{body}</svg>')


def init_mascot(app):
    app.jinja_env.globals["crest"] = crest
    app.jinja_env.globals["scene_deploy"] = scene_deploy
    app.jinja_env.globals["icon"] = icon
