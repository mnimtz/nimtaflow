"""Generate a shareable 'postcard' image from a photo.

Several real LAYOUTS (not just colour swaps): a classic split postcard, a modern
full-bleed caption bar, a Polaroid, a cinematic letterbox and a vintage sepia
card. Greeting, message, layout and text colour are caller-supplied so the web/iOS
editor can offer a live preview. Pure Pillow → fast, no external deps.
"""
import io
import os
from datetime import datetime
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

_FONT_DIRS = [
    "/usr/local/lib/python3.12/site-packages/matplotlib/mpl-data/fonts/ttf",
    "/usr/share/fonts/truetype/dejavu",
]

W, H = 1600, 1120
GOLD = (232, 181, 74)
INK = (38, 34, 28)
CREAM = (252, 248, 238)
WHITE = (250, 250, 248)
NEARBLACK = (24, 22, 20)

LAYOUTS = ("classic", "modern", "polaroid", "film", "vintage")


def _font(name: str, size: int):
    for d in _FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    for fb in ("DejaVuSans.ttf",):
        try:
            return ImageFont.truetype(fb, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _fit_font(draw, text, fontname, max_w, start, min_size=26):
    size = start
    while size > min_size:
        f = _font(fontname, size)
        if draw.textlength(text or "", font=f) <= max_w:
            return f
        size -= 3
    return _font(fontname, min_size)


def _wrap(draw, text, font, max_w):
    words = (text or "").split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def _hex(c, default):
    try:
        c = str(c).lstrip("#")
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    except Exception:
        return default


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


def _logo():
    p = os.path.join(os.path.dirname(__file__), "..", "assets", "nimtaflow_logo.png")
    if os.path.exists(p):
        try:
            return Image.open(p).convert("RGBA")
        except Exception:
            return None
    return None


def _paste_logo(card: Image.Image, x: int, y: int, w: int, shadow=True) -> Image.Image:
    """Paste the transparent wordmark at (x,y) scaled to width w. Returns RGB card."""
    logo = _logo()
    if not logo:
        return card
    h = max(1, int(w * logo.height / logo.width))
    logo = logo.resize((w, h), Image.LANCZOS)
    card = card.convert("RGBA")
    if shadow:
        alpha = logo.split()[3]
        sil = Image.composite(Image.new("RGBA", logo.size, (0, 0, 0, 130)),
                              Image.new("RGBA", logo.size, (0, 0, 0, 0)), alpha)
        sil = sil.filter(ImageFilter.GaussianBlur(6))
        card.alpha_composite(sil, (x + 2, y + 4))
    card.alpha_composite(logo, (x, y))
    return card.convert("RGB")


def _shadow_text(draw, xy, text, font, fill, anchor=None, soff=2, salpha=150):
    x, y = xy
    draw.text((x + soff, y + soff), text, font=font, fill=(0, 0, 0), anchor=anchor)
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)


def _sepia(img: Image.Image) -> Image.Image:
    g = ImageOps.grayscale(img)
    return ImageOps.colorize(g, black=(44, 28, 12), white=(255, 242, 206)).convert("RGB")


# ── Layouts ───────────────────────────────────────────────────────────────────

def _classic(photo, place, taken_at, lang, text, subtitle, tcol):
    """A real split postcard: photo left, written message + stamp right (cream)."""
    col = tcol or INK
    card = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(card)
    m = 46
    pw = int(W * 0.58)
    photo_fit = ImageOps.fit(photo, (pw, H - 2 * m), Image.LANCZOS)
    card.paste(photo_fit, (m, m))
    draw.rectangle([m, m, m + pw, H - m], outline=(0, 0, 0, 40), width=2)
    # vertical divider
    dx = m + pw + 46
    draw.line([(dx, m + 6), (dx, H - m - 6)], fill=GOLD, width=3)
    rx = dx + 34
    rw = W - 46 - rx
    greet = (text or "").strip() or default_greeting(place, lang)
    gf = _fit_font(draw, greet, "DejaVuSerif-Bold.ttf", rw, 60, 30)
    y = m + 18
    for line in _wrap(draw, greet, gf, rw)[:2]:
        draw.text((rx, y), line, font=gf, fill=col); y += gf.size + 8
    y += 14
    msg = (subtitle or "").strip()
    if msg:
        mf = _font("DejaVuSerif.ttf", 32)
        for line in _wrap(draw, msg, mf, rw)[:4]:
            draw.text((rx, y), line, font=mf, fill=col); y += mf.size + 10
    # faint address lines toward the bottom
    ly = H - m - 150
    for i in range(3):
        draw.line([(rx, ly + i * 34), (W - 60, ly + i * 34)], fill=(0, 0, 0, 28), width=1)
    dt = _fmt_date(taken_at, lang)
    if dt:
        draw.text((rx, H - m - 40), dt, font=_font("DejaVuSerif-Italic.ttf", 28), fill=col)
    # stamp box (logo) top-right
    sx, sy, sw = W - 46 - 150, m + 8, 150
    draw.rectangle([sx, sy, sx + sw, sy + 96], outline=GOLD, width=3)
    card = _paste_logo(card, sx + 10, sy + 26, sw - 20, shadow=False)
    return card


def _modern(photo, place, taken_at, lang, text, subtitle, tcol):
    """Full-bleed photo with a solid caption bar at the bottom (always readable)."""
    col = tcol or WHITE
    card = ImageOps.fit(photo, (W, H), Image.LANCZOS).convert("RGB")
    barh = int(H * 0.27)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([0, H - barh, W, H], fill=(12, 12, 16, 205))
    card = Image.alpha_composite(card.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(card)
    x = 60
    greet = (text or "").strip() or default_greeting(place, lang)
    gf = _fit_font(draw, greet, "DejaVuSans-Bold.ttf", W - 2 * x, 64, 32)
    y = H - barh + 28
    draw.text((x, y), greet, font=gf, fill=col); y += gf.size + 12
    msg = (subtitle or "").strip()
    if msg:
        mf = _fit_font(draw, msg, "DejaVuSans.ttf", W - 2 * x, 34, 24)
        draw.text((x, y), msg, font=mf, fill=col); y += mf.size + 8
    dt = _fmt_date(taken_at, lang)
    if dt:
        draw.text((x, y), dt, font=_font("DejaVuSans.ttf", 26), fill=GOLD)
    card = _paste_logo(card, W - 60 - 200, 30, 200)
    return card


def _polaroid(photo, place, taken_at, lang, text, subtitle, tcol):
    """Classic Polaroid: thick white frame, big bottom margin, handwritten-ish caption."""
    col = tcol or (40, 38, 36)
    card = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(card)
    side = 70
    bottom = 230
    box = (side, side, W - side, H - bottom)
    pw, ph = box[2] - box[0], box[3] - box[1]
    photo_fit = ImageOps.fit(photo, (pw, ph), Image.LANCZOS)
    card.paste(photo_fit, (box[0], box[1]))
    draw.rectangle(box, outline=(0, 0, 0, 30), width=1)
    cx = W // 2
    greet = (text or "").strip() or default_greeting(place, lang)
    gf = _fit_font(draw, greet, "DejaVuSerif-Italic.ttf", W - 2 * side, 60, 30)
    y = H - bottom + 34
    draw.text((cx, y), greet, font=gf, fill=col, anchor="ma"); y += gf.size + 14
    msg = (subtitle or "").strip()
    if msg:
        mf = _fit_font(draw, msg, "DejaVuSerif-Italic.ttf", W - 2 * side, 34, 22)
        draw.text((cx, y), msg, font=mf, fill=(110, 105, 100), anchor="ma"); y += mf.size + 8
    dt = _fmt_date(taken_at, lang)
    if dt:
        draw.text((cx, H - 56), dt, font=_font("DejaVuSans.ttf", 24), fill=(150, 145, 140), anchor="ma")
    card = _paste_logo(card, W - side - 150, H - bottom + 30, 150, shadow=False)
    return card


def _film(photo, place, taken_at, lang, text, subtitle, tcol):
    """Cinematic: black letterbox bars, centred title in the lower bar."""
    col = tcol or WHITE
    card = Image.new("RGB", (W, H), NEARBLACK)
    bar = 150
    photo_fit = ImageOps.fit(photo, (W, H - 2 * bar), Image.LANCZOS)
    card.paste(photo_fit, (0, bar))
    draw = ImageDraw.Draw(card)
    cx = W // 2
    greet = (text or "").strip() or default_greeting(place, lang)
    gf = _fit_font(draw, greet, "DejaVuSans-Bold.ttf", W - 200, 54, 30)
    draw.text((cx, H - bar + 34), greet, font=gf, fill=col, anchor="ma")
    msg = (subtitle or "").strip()
    sub_line = " · ".join([s for s in (msg, _fmt_date(taken_at, lang)) if s])
    if sub_line:
        draw.text((cx, H - bar + 34 + gf.size + 14), sub_line,
                  font=_font("DejaVuSans.ttf", 26), fill=GOLD, anchor="ma")
    card = _paste_logo(card, W - 60 - 180, 36, 180)
    return card


def _vintage(photo, place, taken_at, lang, text, subtitle, tcol):
    """Old-fashioned: sepia photo, ornate double border, serif 'Greetings from'."""
    col = tcol or (74, 48, 22)
    card = Image.new("RGB", (W, H), (244, 234, 212))
    draw = ImageDraw.Draw(card)
    m = 60
    bottom = 150
    box = (m, m, W - m, H - bottom)
    pw, ph = box[2] - box[0], box[3] - box[1]
    photo_fit = _sepia(ImageOps.fit(photo, (pw, ph), Image.LANCZOS))
    card.paste(photo_fit, (box[0], box[1]))
    # double ornate border around the photo
    draw.rectangle(box, outline=(120, 84, 38), width=4)
    draw.rectangle([box[0] - 10, box[1] - 10, box[2] + 10, box[3] + 10], outline=GOLD, width=2)
    cx = W // 2
    greet = (text or "").strip() or default_greeting(place, lang)
    gf = _fit_font(draw, greet, "DejaVuSerif-Bold.ttf", W - 2 * m, 56, 30)
    y = H - bottom + 24
    draw.text((cx, y), greet, font=gf, fill=col, anchor="ma"); y += gf.size + 8
    sub_line = " · ".join([s for s in ((subtitle or "").strip(), _fmt_date(taken_at, lang)) if s])
    if sub_line:
        draw.text((cx, y), sub_line, font=_font("DejaVuSerif-Italic.ttf", 28), fill=(120, 90, 50), anchor="ma")
    card = _paste_logo(card, W - m - 140, m + 14, 140)
    return card


_RENDERERS = {
    "classic": _classic, "modern": _modern, "polaroid": _polaroid,
    "film": _film, "vintage": _vintage,
}
# old theme names → a sensible layout, so existing share links keep working
_ALIAS = {"warm": "classic", "gold": "vintage", "dark": "film"}


def make_postcard(image_path: str, place: Optional[str], taken_at: Optional[datetime],
                  lang: str = "de", text: Optional[str] = None,
                  subtitle: Optional[str] = None, theme: str = "classic",
                  text_color: Optional[str] = None) -> bytes:
    """Compose the postcard PNG. `theme` selects a LAYOUT (classic/modern/polaroid/
    film/vintage). `text_color` is an optional '#rrggbb' override for the caption."""
    photo = Image.open(image_path).convert("RGB")
    layout = (theme or "classic").lower()
    layout = _ALIAS.get(layout, layout)
    render = _RENDERERS.get(layout, _classic)
    tcol = _hex(text_color, None) if text_color else None
    card = render(photo, place, taken_at, lang, text, subtitle, tcol)
    out = io.BytesIO()
    card.save(out, format="PNG")
    return out.getvalue()
