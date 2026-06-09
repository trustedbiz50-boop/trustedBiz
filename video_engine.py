"""
video_engine.py — Daisy Video Engine
=====================================
Hollywood-level video editing using FFmpeg + Claude.
Zero third party video services. Runs entirely on your server.

Flow:
  1. User uploads video + types what they want
  2. Claude analyzes request → decides style, text, mood, cuts
  3. FFmpeg executes: color grade, titles, subtitles, music, transitions
  4. Cloudinary stores finished video
  5. User gets download link

Styles:
  cinematic   — dark grade, gold titles, film grain, dramatic
  warm        — warm orange tone, soft glow, friendly
  clean       — bright, sharp, minimal, professional
  dark        — deep shadows, neon accent, club/night energy
  tiktok      — 9:16, fast cuts, bold text, high energy
  youtube     — 16:9, clean, logo safe zones
  reels       — 9:16, smooth, trending look
"""

import os, json, re, subprocess, tempfile, threading, uuid, math
from pathlib import Path

# ── Music library (bundled royalty-free beats) ────────────────────────────────
# These are generated silent placeholders — replace with real .mp3 files
# in static/music/ folder. Daisy picks the right one based on mood.
MUSIC_DIR = Path(__file__).parent / "static" / "music"
MUSIC_TRACKS = {
    "hype":       "hype.mp3",        # fast, energetic — gyms, promos
    "warm":       "warm.mp3",        # soft, welcoming — cafes, salons
    "cinematic":  "cinematic.mp3",   # deep, dramatic — movie trailers
    "corporate":  "corporate.mp3",   # clean, professional — business
    "afrobeat":   "afrobeat.mp3",    # Ugandan/African energy
    "minimal":    "minimal.mp3",     # quiet, elegant — luxury brands
}

# ── Color grade presets (FFmpeg filter strings) ───────────────────────────────
GRADES = {
    "cinematic": "curves=r='0/0 0.5/0.42 1/0.9':g='0/0 0.5/0.45 1/0.85':b='0/0.05 0.5/0.48 1/0.8',unsharp=5:5:0.8:3:3:0.4,vignette=PI/4",
    "warm":      "curves=r='0/0 0.5/0.56 1/1':g='0/0 0.5/0.50 1/0.95':b='0/0 0.5/0.42 1/0.85',unsharp=3:3:0.5",
    "clean":     "curves=r='0/0.02 1/1':g='0/0.02 1/1':b='0/0.02 1/1',unsharp=3:3:0.3,eq=contrast=1.05:brightness=0.02:saturation=1.1",
    "dark":      "curves=r='0/0 0.5/0.38 1/0.85':g='0/0 0.5/0.38 1/0.82':b='0/0.05 0.5/0.45 1/1.0',vignette=PI/3",
    "vibrant":   "eq=contrast=1.1:brightness=0.03:saturation=1.4,unsharp=3:3:0.6",
    "moody":     "curves=r='0/0 0.3/0.25 1/0.88':g='0/0 0.3/0.22 1/0.82':b='0/0.08 0.5/0.5 1/0.95',vignette=PI/3.5",
    "fresh":     "eq=contrast=1.05:brightness=0.05:saturation=1.2,curves=b='0/0.05 1/0.98'",
}

# ── Font map ──────────────────────────────────────────────────────────────────
# FFmpeg uses system fonts. These are common on Ubuntu (Render uses Ubuntu).
FONTS = {
    "bold":    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "mono":    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
}

def _font(style="bold"):
    f = FONTS.get(style, FONTS["bold"])
    return f if Path(f).exists() else "Sans"


def _check_ffmpeg():
    """Check FFmpeg is installed on the server."""
    try:
        r = subprocess.run(["ffmpeg", "-version"],
                           capture_output=True, timeout=5)
        return r.returncode == 0
    except:
        return False


def _get_video_info(path):
    """Get duration, width, height of a video file."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams", str(path)
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=10)
        data = json.loads(r.stdout.decode())
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                return {
                    "width":    stream.get("width", 1920),
                    "height":   stream.get("height", 1080),
                    "duration": float(stream.get("duration", 30))
                }
    except:
        pass
    return {"width": 1920, "height": 1080, "duration": 30}


def _analyze_with_claude(user_prompt, video_info):
    """
    Ask Claude to analyze what the user wants and return
    structured editing instructions Daisy will follow.
    """
    try:
        import anthropic
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            return _default_plan(user_prompt)

        client = anthropic.Anthropic(api_key=key)

        system = """You are Daisy's video intelligence brain.
A user wants to edit a video. Analyze their request and return ONLY a JSON object — no explanation, no markdown.

JSON structure:
{
  "title": "Main title text (business name or headline, max 30 chars)",
  "subtitle": "Subtitle text (tagline or service, max 50 chars)",
  "grade": "one of: cinematic | warm | clean | dark | vibrant | moody | fresh",
  "music": "one of: hype | warm | cinematic | corporate | afrobeat | minimal",
  "format": "one of: tiktok | reels | youtube | square",
  "outro_text": "Call to action text, max 40 chars e.g. 'Call us on WhatsApp'",
  "outro_sub": "Contact or URL, max 40 chars",
  "title_color": "hex color for title e.g. #FFFFFF",
  "accent_color": "hex color for accents e.g. #FFD700",
  "speed": "one of: normal | slow | fast",
  "add_subtitles": true or false,
  "subtitle_text": "If add_subtitles true — the subtitle text to burn in",
  "mood": "one or two words describing the feel e.g. powerful dramatic"
}

Rules:
- For restaurants, cafes, food: grade=warm or vibrant, music=afrobeat or warm
- For gyms, sports, energy: grade=cinematic or dark, music=hype
- For salons, beauty: grade=moody or warm, music=minimal or warm
- For business/corporate: grade=clean, music=corporate
- For TikTok/Reels mentions: format=tiktok or reels
- If user says "cinematic" or "movie": grade=cinematic, music=cinematic
- Default format=tiktok (most Ugandan users post to TikTok/WhatsApp status)
- Default music=afrobeat unless request says otherwise"""

        prompt = f"""User request: "{user_prompt}"
Video info: {video_info['width']}x{video_info['height']}, {video_info['duration']:.1f} seconds

Return the JSON editing plan."""

        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r'```json|```', '', raw).strip()
        return json.loads(raw)

    except Exception as e:
        print(f"[VideoEngine/Claude] {e}")
        return _default_plan(user_prompt)


def _default_plan(user_prompt):
    """Fallback plan when Claude is unavailable."""
    msg = user_prompt.lower()
    grade   = "warm"
    music   = "afrobeat"
    format_ = "tiktok"
    if any(w in msg for w in ["gym", "sport", "fitness", "energy", "power"]):
        grade = "cinematic"; music = "hype"
    elif any(w in msg for w in ["salon", "beauty", "spa", "luxury"]):
        grade = "moody"; music = "minimal"
    elif any(w in msg for w in ["restaurant", "food", "cafe", "eat"]):
        grade = "vibrant"; music = "afrobeat"
    elif any(w in msg for w in ["business", "corporate", "office", "company"]):
        grade = "clean"; music = "corporate"
    elif any(w in msg for w in ["youtube", "16:9"]):
        format_ = "youtube"
    elif any(w in msg for w in ["reels", "instagram"]):
        format_ = "reels"

    return {
        "title":         "TrustedBiz",
        "subtitle":      "Your Business, Online",
        "grade":         grade,
        "music":         music,
        "format":        format_,
        "outro_text":    "Find us on TrustedBiz",
        "outro_sub":     "trustedbiz.co.ug",
        "title_color":   "#FFFFFF",
        "accent_color":  "#FFD700",
        "speed":         "normal",
        "add_subtitles": False,
        "subtitle_text": "",
        "mood":          "professional"
    }


def _build_ffmpeg_command(input_path, output_path, plan, video_info, music_path=None):
    """
    Build the FFmpeg command that creates the Hollywood edit.
    Returns a list of command arguments.
    """
    w, h, duration = video_info["width"], video_info["height"], video_info["duration"]

    # ── Output dimensions based on format ────────────────────────────────────
    fmt = plan.get("format", "tiktok")
    if fmt in ("tiktok", "reels"):
        out_w, out_h = 1080, 1920
    elif fmt == "square":
        out_w, out_h = 1080, 1080
    else:  # youtube / default
        out_w, out_h = 1920, 1080

    # ── Speed ─────────────────────────────────────────────────────────────────
    speed = plan.get("speed", "normal")
    pts_val = "1.0"
    if speed == "slow":
        pts_val = "1.5"   # 0.67x speed
    elif speed == "fast":
        pts_val = "0.75"  # 1.33x speed

    # ── Colors ────────────────────────────────────────────────────────────────
    title_color  = plan.get("title_color", "#FFFFFF").lstrip("#")
    accent_color = plan.get("accent_color", "#FFD700").lstrip("#")
    title_color_ffmpeg  = f"0x{title_color}FF"
    accent_color_ffmpeg = f"0x{accent_color}FF"

    # ── Text (escape special chars for FFmpeg drawtext) ───────────────────────
    def esc(text):
        if not text:
            return ""
        # FFmpeg drawtext escaping: apostrophe needs special handling
        # Replace ' with unicode right single quote (looks identical, no escape needed)
        text = str(text)
        text = text.replace("'", "\u2019")   # ' → ' (right single quote)
        text = text.replace("\\", "\\\\")  # backslash
        text = text.replace(":", "\\:")       # colon
        text = text.replace(",", "\\,")       # comma
        text = text.replace("[", "\\[").replace("]", "\\]")
        return text

    title      = esc(plan.get("title", ""))
    subtitle   = esc(plan.get("subtitle", ""))
    outro_text = esc(plan.get("outro_text", ""))
    outro_sub  = esc(plan.get("outro_sub", ""))

    # ── Grade filter ──────────────────────────────────────────────────────────
    grade       = plan.get("grade", "warm")
    grade_filter = GRADES.get(grade, GRADES["warm"])

    # ── Fade timings ──────────────────────────────────────────────────────────
    fade_in_dur  = 0.8
    fade_out_st  = max(0, duration - 1.2)
    title_start  = 0.5
    title_end    = min(4.0, duration * 0.35)
    outro_start  = max(0, duration - 4.0)

    # ── Build the massive filter_complex ─────────────────────────────────────
    # Scale + pad to target format, keeping aspect ratio
    scale_filter = (
        f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:black"
    )

    # Speed ramp
    speed_filter = f"setpts={pts_val}*PTS"

    # Fade in/out
    fade_filter = (
        f"fade=t=in:st=0:d={fade_in_dur}:alpha=0,"
        f"fade=t=out:st={fade_out_st:.2f}:d=1.0:alpha=0"
    )

    # Title text (slides in from left, fades out)
    title_filter = ""
    if title:
        title_filter = (
            f"drawtext=fontfile='{_font('bold')}':"
            f"text='{title}':"
            f"fontcolor={title_color_ffmpeg}:"
            f"fontsize={int(out_w * 0.07)}:"
            f"x='if(lt(t\\,{title_start+0.3})\\,w\\,(w-text_w)/2)':"
            f"y={int(out_h * 0.12)}:"
            f"alpha='if(lt(t\\,{title_start})\\,0\\,"
            f"if(lt(t\\,{title_start+0.4})\\,(t-{title_start})/0.4\\,"
            f"if(lt(t\\,{title_end})\\,1\\,"
            f"if(lt(t\\,{title_end+0.4})\\,1-(t-{title_end})/0.4\\,0))))':"
            f"shadowcolor=0x000000AA:shadowx=3:shadowy=3,"
        )

    # Subtitle text
    sub_filter = ""
    if subtitle:
        sub_filter = (
            f"drawtext=fontfile='{_font('regular')}':"
            f"text='{subtitle}':"
            f"fontcolor={title_color_ffmpeg}:"
            f"fontsize={int(out_w * 0.038)}:"
            f"x=(w-text_w)/2:"
            f"y={int(out_h * 0.20)}:"
            f"alpha='if(lt(t\\,{title_start+0.3})\\,0\\,"
            f"if(lt(t\\,{title_start+0.7})\\,(t-{title_start+0.3})/0.4\\,"
            f"if(lt(t\\,{title_end})\\,1\\,0)))':"
            f"shadowcolor=0x000000AA:shadowx=2:shadowy=2,"
        )

    # Accent line under title
    accent_filter = ""
    if title:
        line_w = int(out_w * 0.25)
        line_x = (out_w - line_w) // 2
        line_y = int(out_h * 0.225)
        accent_filter = (
            f"drawbox=x={line_x}:y={line_y}:w={line_w}:h=4:"
            f"color=0x{accent_color}FF:t=fill:"
            f"enable='between(t,{title_start+0.5},{title_end})',"
        )

    # Outro card (dark overlay + text at end)
    outro_filter = ""
    if outro_text:
        outro_filter = (
            f"drawbox=x=0:y={int(out_h*0.72)}:w={out_w}:h={int(out_h*0.28)}:"
            f"color=0x000000CC:t=fill:"
            f"enable='gte(t,{outro_start})',"
            f"drawtext=fontfile='{_font('bold')}':"
            f"text='{outro_text}':"
            f"fontcolor={title_color_ffmpeg}:"
            f"fontsize={int(out_w * 0.05)}:"
            f"x=(w-text_w)/2:"
            f"y={int(out_h * 0.76)}:"
            f"alpha='if(lt(t\\,{outro_start})\\,0\\,"
            f"if(lt(t\\,{outro_start+0.5})\\,(t-{outro_start})/0.5\\,1))':"
            f"shadowcolor=0x000000FF:shadowx=2:shadowy=2,"
        )

    outro_sub_filter = ""
    if outro_sub:
        outro_sub_filter = (
            f"drawtext=fontfile='{_font('regular')}':"
            f"text='{outro_sub}':"
            f"fontcolor={accent_color_ffmpeg}:"
            f"fontsize={int(out_w * 0.035)}:"
            f"x=(w-text_w)/2:"
            f"y={int(out_h * 0.84)}:"
            f"alpha='if(lt(t\\,{outro_start+0.3})\\,0\\,"
            f"if(lt(t\\,{outro_start+0.8})\\,(t-{outro_start+0.3})/0.5\\,1))',"
        )

    # Burned-in subtitles (bottom center)
    sub_burn_filter = ""
    if plan.get("add_subtitles") and plan.get("subtitle_text"):
        sub_text = esc(plan["subtitle_text"])
        sub_burn_filter = (
            f"drawtext=fontfile='{_font('bold')}':"
            f"text='{sub_text}':"
            f"fontcolor=white:"
            f"fontsize={int(out_w * 0.042)}:"
            f"x=(w-text_w)/2:"
            f"y={int(out_h * 0.88)}:"
            f"box=1:boxcolor=0x000000BB:boxborderw=10,"
        )

    # Assemble full video filter chain
    vf = (
        f"{scale_filter},"
        f"{speed_filter},"
        f"{grade_filter},"
        f"{fade_filter},"
        f"{title_filter}"
        f"{sub_filter}"
        f"{accent_filter}"
        f"{outro_filter}"
        f"{outro_sub_filter}"
        f"{sub_burn_filter}"
        f"format=yuv420p"
    )

    # ── Build command ─────────────────────────────────────────────────────────
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]

    has_music = music_path and Path(music_path).exists()
    if has_music:
        cmd += ["-i", str(music_path)]

    cmd += ["-vf", vf]

    if has_music:
        # Mix original audio (voice) with music
        # Voice at 100%, music ducked to 15%
        cmd += [
            "-filter_complex",
            f"[1:a]volume=0.15,apad[music];"
            f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "0:v",
            "-map", "[aout]",
        ]
    else:
        # Just use original audio with noise reduction
        cmd += [
            "-af", "afftdn=nf=-25,equalizer=f=200:width_type=o:width=2:g=2",
        ]

    cmd += [
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-t", str(duration),
        str(output_path)
    ]

    return cmd


def _upload_to_cloudinary(file_path, public_id=None):
    """Upload finished video to Cloudinary and return secure URL."""
    try:
        cloudinary_url = os.environ.get("CLOUDINARY_URL", "")
        if not cloudinary_url:
            return None
        import cloudinary, cloudinary.uploader
        cloudinary.config(cloudinary_url=cloudinary_url)

        opts = {
            "resource_type": "video",
            "folder":        "trustedbiz-videos",
            "quality":       "auto:good",
        }
        if public_id:
            opts["public_id"] = public_id

        result = cloudinary.uploader.upload(str(file_path), **opts)
        return result.get("secure_url")
    except Exception as e:
        print(f"[VideoEngine/Cloudinary] {e}")
        return None


def process_video(input_path, user_prompt, job_id, on_complete=None, on_error=None):
    """
    Main entry point. Called in a background thread.

    Args:
        input_path  : Path to uploaded raw video file
        user_prompt : What the user typed ("make restaurant promo")
        job_id      : Unique ID for this job (used for status tracking)
        on_complete : Callback(job_id, output_url, plan)
        on_error    : Callback(job_id, error_message)
    """
    try:
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input video not found: {input_path}")

        if not _check_ffmpeg():
            raise RuntimeError("FFmpeg not installed on this server")

        # 1. Get video info
        video_info = _get_video_info(input_path)
        print(f"[VideoEngine] Job {job_id}: {video_info}")

        # 2. Ask Claude for the edit plan
        plan = _analyze_with_claude(user_prompt, video_info)
        print(f"[VideoEngine] Job {job_id}: Plan = {json.dumps(plan, indent=2)}")

        # 3. Find music track
        music_track = plan.get("music", "afrobeat")
        music_path  = MUSIC_DIR / MUSIC_TRACKS.get(music_track, "afrobeat.mp3")
        if not music_path.exists():
            music_path = None  # no music if file missing, still works

        # 4. Set up temp output path
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / f"daisy_edit_{job_id}.mp4"

            # 5. Build and run FFmpeg
            cmd = _build_ffmpeg_command(
                input_path, output_path, plan, video_info, music_path
            )
            print(f"[VideoEngine] Job {job_id}: Running FFmpeg...")

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=300,   # 5 min max
            )

            if result.returncode != 0:
                err = result.stderr.decode()[-1000:]
                raise RuntimeError(f"FFmpeg failed: {err}")

            if not output_path.exists() or output_path.stat().st_size < 1000:
                raise RuntimeError("Output file empty or missing")

            print(f"[VideoEngine] Job {job_id}: FFmpeg done. Uploading...")

            # 6. Upload to Cloudinary
            public_id  = f"daisy_{job_id}"
            output_url = _upload_to_cloudinary(output_path, public_id)

            if not output_url:
                # Fallback: serve locally if Cloudinary fails
                local_out = Path(__file__).parent / "static" / "videos" / f"{job_id}.mp4"
                local_out.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy(output_path, local_out)
                output_url = f"/static/videos/{job_id}.mp4"

            print(f"[VideoEngine] Job {job_id}: Done → {output_url}")

            if on_complete:
                on_complete(job_id, output_url, plan)

            return output_url, plan

    except Exception as e:
        print(f"[VideoEngine] Job {job_id} ERROR: {e}")
        if on_error:
            on_error(job_id, str(e))
        return None, None


# ── Job status store (in-memory, good enough for free tier) ──────────────────
_jobs = {}   # job_id → {"status", "url", "plan", "error", "prompt"}

def get_job(job_id):
    return _jobs.get(job_id)

def submit_video_job(input_path, user_prompt):
    """
    Submit a video job. Returns job_id immediately.
    Processing happens in background thread.
    """
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "status": "processing",
        "url":    None,
        "plan":   None,
        "error":  None,
        "prompt": user_prompt
    }

    def _on_complete(jid, url, plan):
        _jobs[jid]["status"] = "done"
        _jobs[jid]["url"]    = url
        _jobs[jid]["plan"]   = plan

    def _on_error(jid, err):
        _jobs[jid]["status"] = "error"
        _jobs[jid]["error"]  = err

    t = threading.Thread(
        target=process_video,
        args=(input_path, user_prompt, job_id),
        kwargs={"on_complete": _on_complete, "on_error": _on_error},
        daemon=True
    )
    t.start()
    return job_id
