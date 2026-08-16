"""
plan_power.py — TrustedBiz Plan Power Config
═════════════════════════════════════════════
Single source of truth for what each plan actually gets when Daisy builds
something. Before this file existed, every plan (free, basic, promax) got
the exact same model, same token budget, and a single generation pass —
the billing page promised more but the generator never checked what plan
it was building for. This file is what call_daisy() and the artifact
builders read to make that real.

Raise POWER numbers here and every generator picks it up automatically —
no need to hunt through app.py.
"""

# ── WEBSITE GENERATION ──────────────────────────────────────────────────────
# max_tokens   — output budget per generation round (more = a fuller, more
#                detailed site with more sections, less chance of the AI
#                cutting corners to fit).
# passes       — 1 = single-shot build. 2 = build, then a second Claude call
#                acting as a senior art director that reviews its own first
#                draft and rewrites it for a noticeably more premium result.
#                This is the real, structural difference between plans, not
#                just a bigger number — it's what makes a Pro Max site look
#                like agency work instead of a fast first draft.
# images       — how many AI-generated custom images (hero art, section
#                graphics) Daisy is allowed to create for this business when
#                they haven't supplied their own photos. 0 = text/CSS only.
#
# All three tiers use Sonnet — quality never drops on free, only scope does.
# Cheaper model tiers were considered for free but rejected: it visibly hurt
# layout/design quality, and every free site is a public shopfront for
# TrustedBiz itself, so a weak free tier costs more in reputation than the
# extra API spend saves. If free-tier API cost becomes a real problem at
# volume, the token budget below is the lever to pull first, not the model.
WEBSITE_POWER = {
    "free": {
        "model":      "claude-sonnet-5",
        "max_tokens": 8000,
        "passes":     1,
        "images":     0,
        "label":      "Free",
    },
    "basic": {
        "model":      "claude-sonnet-5",
        "max_tokens": 14000,
        "passes":     1,
        "images":     2,
        "label":      "Basic",
    },
    "pro_max": {
        "model":      "claude-sonnet-5",
        "max_tokens": 24000,
        "passes":     2,
        "images":     6,
        "label":      "Pro Max",
    },
}


# 'promax' is used in a couple of older call sites as an alias for 'pro_max'
_ALIASES = {"promax": "pro_max"}


def get_website_power(plan):
    plan = _ALIASES.get((plan or "free").strip().lower(), (plan or "free").strip().lower())
    return WEBSITE_POWER.get(plan, WEBSITE_POWER["free"])


# ── DAISY ARTIFACT BUILDER (catalog, flyer, logo, cards, CV, presentation) ──
# Which artifact types each plan is allowed to ask Daisy for in chat, and
# how many Daisy will build per calendar month. "unlimited" is a soft cap
# high enough nobody hits it by hand.
ARTIFACT_TYPES = ["logo", "catalog", "flyer", "cards", "cv", "presentation", "exam"]

ARTIFACT_POWER = {
    "free": {
        "allowed":       ["logo", "catalog"],
        "monthly_limit": 3,
        "max_tokens":    8000,
    },
    "basic": {
        "allowed":       ["logo", "catalog", "flyer", "cards", "cv"],
        "monthly_limit": 20,
        "max_tokens":    9000,
    },
    "pro_max": {
        "allowed":       ARTIFACT_TYPES,
        "monthly_limit": None,  # unlimited
        "max_tokens":    12000,
    },
}


def get_artifact_power(plan):
    plan = _ALIASES.get((plan or "free").strip().lower(), (plan or "free").strip().lower())
    return ARTIFACT_POWER.get(plan, ARTIFACT_POWER["free"])


def artifact_allowed(plan, artifact_type):
    power = get_artifact_power(plan)
    return artifact_type in power["allowed"]
