"""Generate a shareable 'postcard' image from a photo — the picture in a clean
card with a greeting line, an optional personal message, the date and a tasteful
NimtaFlow signature.

Pure Pillow (no AI, no external deps) → fast and reliable. Used by the
/photos/{id}/postcard endpoints (web dialog + iOS share). Greeting, message and
theme are caller-supplied so the web/iOS dialogs can offer a live editor."""
import io
import os
from datetime import datetime
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

_FONT_DIRS = [
    "/usr/local/lib/python3.12/site-packages/matplotlib/mpl-data/fonts/ttf",
    "/usr/share/fonts/truetype/dejavu",
]

# theme → (frame paper, title ink, sub ink, accent gold, bg darken, bg tint add)
_THEMES = {
    "warm":  ((252, 250, 245), (38, 34, 28),  (120, 110, 95), (232, 181, 74), 0.45, 18),
    "dark":  ((24, 24, 30),    (244, 241, 234), (179, 174, 164), (232, 181, 74), 0.30, 6),
    "gold":  ((252, 248, 238), (60, 45, 16),  (150, 120, 60),  (198, 150, 50),  0.42, 22),
    "film":  ((250, 249, 246), (30, 30, 34),  (110, 110, 118), (232, 181, 74), 0.38, 14),
}


def _font(name: str, size: int):
    for d in _FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _fit_font(draw, text, bold, max_w, start, min_size=30):
    """Largest font (DejaVu) at which `text` fits into max_w, down to min_size."""
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    size = start
    while size > min_size:
        f = _font(name, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 3
    return _font(name, min_size)


def _fmt_date(dt: Optional[datetime], lang: str = "de") -> str:
    if not dt:
        return ""
    months_de = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                 "August", "September", "Oktober", "November", "Dezember"]
    months_en = ["January", "February", "March", "April", "May", "June", "July",
                 "August", "September", "October", "November", "December"]
    m = (months_en if lang == "en" else months_de)[dt.month - 1]
    return f"{dt.day}. {m} {dt.year}" if lang != "en" else f"{m} {dt.day}, {dt.year}"


def default_greeting(place: Optional[str], lang: str = "de") -> str:
    if lang == "en":
        return f"Greetings from {place}" if place else "Warm wishes"
    return f"Grüße aus {place}" if place else "Liebe Grüße"


def make_postcard(image_path: str, place: Optional[str], taken_at: Optional[datetime],
                  lang: str = "de", text: Optional[str] = None,
                  subtitle: Optional[str] = None, theme: str = "warm") -> bytes:
    """Compose the postcard PNG.

    text     — greeting line (defaults to 'Grüße aus <place>' / 'Liebe Grüße').
    subtitle — optional personal message shown under the greeting.
    theme    — warm | dark | gold | film.
    """
    paper, ink, subink, gold, darken, tint = _THEMES.get(theme, _THEMES["warm"])
    photo = Image.open(image_path).convert("RGB")

    # Landscape card. The photo sits in a frame; a caption band sits below.
    W, H = 1600, 1120
    band = 230                      # caption band height
    pad = 70                        # outer padding
    frame = 18                      # frame around the photo
    inner_w = W - 2 * pad
    inner_h = H - 2 * pad - band
    fitted = ImageOps.fit(photo, (inner_w - 2 * frame, inner_h - 2 * frame), Image.LANCZOS)

    # Background: blurred, darkened copy of the photo (soft, themed vignette).
    bg = ImageOps.fit(photo, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(40))
    bg = Image.eval(bg, lambda v: int(v * darken + tint))
    card = bg.convert("RGB")

    # Drop shadow + frame around the photo.
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    fx, fy = pad, pad
    sd.rounded_rectangle([fx + 8, fy + 12, fx + inner_w + 8, fy + inner_h + 12], radius=14, fill=(0, 0, 0, 120))
    card = Image.alpha_composite(card.convert("RGBA"), shadow.filter(ImageFilter.GaussianBlur(16))).convert("RGB")
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([fx, fy, fx + inner_w, fy + inner_h], radius=12, fill=paper)
    card.paste(fitted, (fx + frame, fy + frame))

    # ── Caption band ──────────────────────────────────────────────
    cap_x = pad + 6
    cap_w = W - 2 * pad - 230        # leave room for the signature on the right
    by = H - band - pad + 34

    greet = (text or "").strip() or default_greeting(place, lang)
    title_f = _fit_font(draw, greet, True, cap_w, 66, 34)
    draw.text((cap_x, by), greet, font=title_f, fill=ink)
    y = by + title_f.size + 14

    msg = (subtitle or "").strip()
    if msg:
        msg_f = _fit_font(draw, msg, False, cap_w, 36, 24)
        draw.text((cap_x, y), msg, font=msg_f, fill=subink)
        y += msg_f.size + 10

    date_txt = _fmt_date(taken_at, lang)
    if date_txt:
        d_f = _font("DejaVuSans.ttf", 30)
        draw.text((cap_x, y), date_txt, font=d_f, fill=subink)

    # ── NimtaFlow logo (the real transparent wordmark) — top-right ON the photo,
    # with a soft shadow so it stays legible on bright or busy backgrounds.
    logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "nimtaflow_logo.png")
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            lw = int(inner_w * 0.15)
            lh = max(1, int(lw * logo.height / logo.width))
            logo = logo.resize((lw, lh), Image.LANCZOS)
            lx = fx + inner_w - frame - lw - 12
            ly = fy + frame + 10
            # soft drop shadow from the logo's own alpha silhouette
            alpha = logo.split()[3]
            sil = Image.new("RGBA", logo.size, (0, 0, 0, 0))
            sil = Image.composite(Image.new("RGBA", logo.size, (0, 0, 0, 150)), sil, alpha)
            sil = sil.filter(ImageFilter.GaussianBlur(7))
            card = card.convert("RGBA")
            card.alpha_composite(sil, (lx + 3, ly + 5))
            card.alpha_composite(logo, (lx, ly))
            card = card.convert("RGB")
            draw = ImageDraw.Draw(card)
        except Exception:
            pass

    # subtle marketing URL bottom-right of the caption band
    url_f = _font("DejaVuSans.ttf", 24)
    url_txt = "nimtaflow.com"
    url_w = draw.textlength(url_txt, font=url_f)
    draw.text((W - pad - url_w - 2, H - pad - 34), url_txt, font=url_f, fill=subink)

    out = io.BytesIO()
    card.save(out, format="PNG")
    return out.getvalue()
