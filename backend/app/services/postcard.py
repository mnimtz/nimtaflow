"""Generate a shareable 'postcard' image from a photo — the picture in a clean
card with a 'Grüße aus <place>' line, the date and a little NimtaFlow stamp.

Pure Pillow (no AI, no external deps) → fast and reliable. Used by the
/photos/{id}/postcard endpoints (web + iOS share)."""
import io
import os
from datetime import datetime
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

_FONT_DIRS = [
    "/usr/local/lib/python3.12/site-packages/matplotlib/mpl-data/fonts/ttf",
    "/usr/share/fonts/truetype/dejavu",
]


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


def _fmt_date(dt: Optional[datetime], lang: str = "de") -> str:
    if not dt:
        return ""
    months_de = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                 "August", "September", "Oktober", "November", "Dezember"]
    months_en = ["January", "February", "March", "April", "May", "June", "July",
                 "August", "September", "October", "November", "December"]
    m = (months_en if lang == "en" else months_de)[dt.month - 1]
    return f"{dt.day}. {m} {dt.year}" if lang != "en" else f"{m} {dt.day}, {dt.year}"


def make_postcard(image_path: str, place: Optional[str], taken_at: Optional[datetime],
                  lang: str = "de") -> bytes:
    """Compose the postcard PNG. `place` like 'Lissabon, Portugal' (may be None)."""
    GOLD = (232, 181, 74)
    INK = (38, 34, 28)
    photo = Image.open(image_path).convert("RGB")

    # Landscape card. The photo sits in a white frame; a caption band sits below.
    W, H = 1600, 1120
    band = 200                      # caption band height
    pad = 70                        # outer padding
    frame = 18                      # white frame around the photo
    inner_w = W - 2 * pad
    inner_h = H - 2 * pad - band
    # cover-fit the photo into the inner frame
    fitted = ImageOps.fit(photo, (inner_w - 2 * frame, inner_h - 2 * frame), Image.LANCZOS)

    # Warm paper background with a soft vignette from a blurred, darkened copy.
    bg = ImageOps.fit(photo, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(40))
    bg = Image.eval(bg, lambda v: int(v * 0.45 + 18))
    card = bg.convert("RGB")
    draw = ImageDraw.Draw(card)

    # White photo frame + drop shadow
    fx, fy = pad, pad
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([fx + 8, fy + 12, fx + inner_w + 8, fy + inner_h + 12], radius=14, fill=(0, 0, 0, 110))
    card.paste(Image.alpha_composite(card.convert("RGBA"), shadow.filter(ImageFilter.GaussianBlur(16))).convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([fx, fy, fx + inner_w, fy + inner_h], radius=12, fill=(252, 250, 245))
    card.paste(fitted, (fx + frame, fy + frame))

    # Caption band
    by = H - band - pad + 24
    title_f = _font("DejaVuSans-Bold.ttf", 64)
    sub_f = _font("DejaVuSans.ttf", 38)
    place_txt = place or ("Schöne Erinnerung" if lang != "en" else "A lovely memory")
    greet = (f"Grüße aus {place}" if place else "Liebe Grüße") if lang != "en" else (f"Greetings from {place}" if place else "Warm wishes")
    draw.text((pad + 6, by), greet, font=title_f, fill=INK)
    date_txt = _fmt_date(taken_at, lang)
    if date_txt:
        draw.text((pad + 8, by + 84), date_txt, font=sub_f, fill=(120, 110, 95))

    # NimtaFlow 'stamp' top-right corner of the card
    sw, sh = 150, 180
    sx, sy = W - pad - sw + 6, pad - 6
    stamp = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    st = ImageDraw.Draw(stamp)
    st.rounded_rectangle([0, 0, sw - 1, sh - 1], radius=10, fill=(255, 255, 255, 235), outline=GOLD + (255,), width=4)
    nf = _font("DejaVuSans-Bold.ttf", 80)
    st.text((sw / 2, sh / 2 - 18), "N", font=nf, fill=GOLD, anchor="mm")
    sm = _font("DejaVuSans.ttf", 20)
    st.text((sw / 2, sh - 28), "NimtaFlow", font=sm, fill=INK, anchor="mm")
    card.paste(stamp, (sx, sy), stamp)

    out = io.BytesIO()
    card.save(out, format="PNG")
    return out.getvalue()
