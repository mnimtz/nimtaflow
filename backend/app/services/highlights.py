"""Highlights / memory-video assistant.

Builds a short slideshow MP4 from a user's photos for a chosen "motto"
(e.g. one person across the years, a year-in-review, a trip album, a season).

Two layers:
  • select_photos_for_motto() — picks the right photos for a motto (async, DB)
  • render_slideshow()        — turns their cached LARGE thumbnails into an MP4
                                via ffmpeg (xfade crossfades, concat fallback).

The slideshow always renders from the cached `thumb_large` JPEGs (already sized,
no original decode), and NEVER hard-fails: if the xfade chain errors it falls
back to a plain concat so a file is always produced.
"""
import os
import shutil
import subprocess
import tempfile
from typing import List, Optional, Any

from sqlalchemy import select, or_, and_, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo, PhotoStatus
from app.models.face import Face
from app.models.album import AlbumPhoto

_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
_RENDER_TIMEOUT = 360  # 6 minutes


# ── Motto catalogue ────────────────────────────────────────────────────────────
# label: German UI label
# params: which form fields the UI must collect for this motto
#   person  → person_id      person2 → person_id2
#   year    → year           album   → album_id        season → season
MOTTOS: List[dict] = [
    {"motto": "person_years",      "label": "Eine Person im Laufe der Jahre",
     "params": ["person"],
     "description": "Ein Mensch, quer durch alle Jahre — chronologisch."},
    {"motto": "person_happy",      "label": "Die schönsten Lächeln einer Person",
     "params": ["person"],
     "description": "Fröhliche Momente, Lachen und glückliche Gesichter."},
    {"motto": "parent_child",      "label": "Mutter/Vater & Kind im Laufe der Jahre",
     "params": ["person", "person2"],
     "description": "Fotos, auf denen beide zusammen sind — über die Jahre."},
    {"motto": "muttertag",         "label": "Muttertag — Tribut an die Mama",
     "params": ["person"],
     "description": "Eine Hommage: die schönsten Momente der Mama, am liebsten mit der Familie."},
    {"motto": "vatertag",          "label": "Vatertag — Tribut an den Papa",
     "params": ["person"],
     "description": "Eine Hommage: die schönsten Momente des Papas, am liebsten mit der Familie."},
    {"motto": "year_review",       "label": "Jahresrückblick",
     "params": ["year"],
     "description": "Die Highlights eines Jahres (Favoriten & bestbewertet zuerst)."},
    {"motto": "through_the_years", "label": "Quer durch alle Jahre",
     "params": [],
     "description": "Ein Bild pro Jahr aus der gesamten Mediathek."},
    {"motto": "trip",              "label": "Eine Reise / ein Album",
     "params": ["album"],
     "description": "Die Fotos einer Reise in Aufnahme-Reihenfolge."},
    {"motto": "season",            "label": "Jahreszeit / Feiertag",
     "params": ["season"],
     "description": "Weihnachten, Ostern, Sommer … über mehrere Jahre."},
    {"motto": "newest_50",         "label": "Die neuesten Aufnahmen",
     "params": [],
     "description": "Die zuletzt aufgenommenen Fotos."},
    {"motto": "most_favorited",    "label": "Deine Favoriten",
     "params": [],
     "description": "Alle als Favorit markierten Fotos, neueste zuerst."},
    {"motto": "top_rated",         "label": "Bestbewertete Fotos",
     "params": [],
     "description": "Die am höchsten bewerteten Fotos."},
    {"motto": "random_memories",   "label": "Zufällige Erinnerungen",
     "params": [],
     "description": "Eine bunte, zufällige Auswahl aus der ganzen Mediathek."},
    {"motto": "album_highlight",   "label": "Album / Smart-Album als Highlight",
     "params": ["album"],
     "description": "Die besten Fotos eines beliebigen Albums oder Smart-Albums — Favoriten & gut bewertete zuerst."},
    {"motto": "week_review",       "label": "Highlight der Woche",
     "params": [],
     "description": "Die schönsten Aufnahmen der letzten 7 Tage (sonst der letzten 30)."},
    {"motto": "people_together",   "label": "Gemeinsame Fotos (mehrere Personen)",
     "params": ["people"],
     "description": "Fotos, auf denen alle ausgewählten Personen gemeinsam zu sehen sind — chronologisch."},
]

# season name → list of (month, day) anchor windows (±~3 weeks) across all years
_SEASON_MONTHS = {
    "christmas": [12],
    "weihnachten": [12],
    "easter": [3, 4],
    "ostern": [3, 4],
    "summer": [6, 7, 8],
    "sommer": [6, 7, 8],
    "winter": [12, 1, 2],
    "spring": [3, 4, 5],
    "fruehling": [3, 4, 5],
    "frühling": [3, 4, 5],
    "autumn": [9, 10, 11],
    "fall": [9, 10, 11],
    "herbst": [9, 10, 11],
    "halloween": [10],
}


def _cap_from_duration(duration_sec: Optional[float]) -> int:
    """How many images fit in `duration_sec` (~2.5 s each), clamped 8..120."""
    d = duration_sec or 60.0
    n = int(round(d / 2.5))
    return max(8, min(120, n))


def _base_conditions(extra_conditions: Optional[list]) -> list:
    return [
        Photo.status == PhotoStatus.done,
        Photo.is_trashed == False,            # noqa: E712
        Photo.is_missing == False,            # noqa: E712
        Photo.thumb_large.isnot(None),
        *(extra_conditions or []),
    ]


def _opt(opts: Any, key: str, default=None):
    """Read a value from opts whether it's a dict or an object."""
    if opts is None:
        return default
    if isinstance(opts, dict):
        return opts.get(key, default)
    return getattr(opts, key, default)


def _quality_key(p: Photo):
    """Best-first within a group: favorites, then higher rating, then chronological."""
    return (0 if p.is_favorite else 1, -(p.user_rating or 0), p.taken_at or _MIN_DT())


def _dedupe_bursts(photos: List[Photo], gap_sec: int = 150) -> List[Photo]:
    """Collapse bursts: among photos taken within `gap_sec` of each other, keep only the
    BEST one (favorite/rated). Stops a highlight from showing 8 near-identical shots of the
    same moment ('zeitlich total nah aneinander'). Photos without a date pass through."""
    ts = sorted((p for p in photos if p.taken_at), key=lambda p: p.taken_at)
    no_ts = [p for p in photos if not p.taken_at]
    kept: List[Photo] = []
    group: List[Photo] = []
    def flush():
        if group:
            kept.append(min(group, key=_quality_key))
    for p in ts:
        if group and (p.taken_at - group[-1].taken_at).total_seconds() > gap_sec:
            flush(); group = []
        group.append(p)
    flush()
    return kept + no_ts


def _spread_even(photos: List[Photo], cap: int, bucket_fn) -> List[Photo]:
    """Burst-dedupe, bucket by `bucket_fn` (e.g. month/day), then round-robin best-first
    across buckets → an even spread over the period instead of a clump from one event."""
    from collections import defaultdict
    photos = _dedupe_bursts(photos)
    buckets: dict = defaultdict(list)
    for p in photos:
        buckets[bucket_fn(p)].append(p)
    for k in buckets:
        buckets[k].sort(key=_quality_key)
    keys = sorted(buckets.keys())
    chosen: List[Photo] = []
    idx = 0
    while len(chosen) < cap:
        added = False
        for k in keys:
            if idx < len(buckets[k]):
                chosen.append(buckets[k][idx]); added = True
                if len(chosen) >= cap:
                    break
        if not added:
            break
        idx += 1
    chosen.sort(key=lambda p: (p.taken_at or _MIN_DT()))
    return chosen


def _spread_across_years(photos: List[Photo], cap: int) -> List[Photo]:
    """One+ representative photo per year, chronological, capped to `cap`.

    Picks at least one per year (favorites/rated first within a year), then, if
    room remains, fills more from the busiest years — always returned in
    chronological order so the video reads as a timeline.
    """
    from collections import defaultdict
    photos = _dedupe_bursts(photos)
    by_year: dict = defaultdict(list)
    for p in photos:
        y = p.taken_at.year if p.taken_at else 0
        by_year[y].append(p)
    for y in by_year:
        by_year[y].sort(key=lambda p: (
            0 if p.is_favorite else 1,
            -(p.user_rating or 0),
            p.taken_at or _MIN_DT(),
        ))
    years = sorted(by_year.keys())
    chosen: List[Photo] = []
    # round-robin: take the i-th best of each year until we hit the cap
    idx = 0
    while len(chosen) < cap:
        added = False
        for y in years:
            if idx < len(by_year[y]):
                chosen.append(by_year[y][idx])
                added = True
                if len(chosen) >= cap:
                    break
        if not added:
            break
        idx += 1
    chosen.sort(key=lambda p: (p.taken_at or _MIN_DT()))
    return chosen


def _MIN_DT():
    from datetime import datetime, timezone
    return datetime.min.replace(tzinfo=timezone.utc)


async def _person_photo_ids(db: AsyncSession, person_id: int) -> List[int]:
    rows = (await db.execute(
        select(Face.photo_id).where(Face.person_id == person_id)
    )).all()
    return [r[0] for r in rows]


# ── Motto selectors ─────────────────────────────────────────────────────────────

async def select_photos_for_motto(db: AsyncSession, motto: str, opts: Any,
                                   extra_conditions: Optional[list] = None) -> List[Photo]:
    """Pick the photos for a given motto. Returns an ordered list of Photo.

    `opts` may be a dict or an object exposing: person_id, person_id2, year,
    album_id, season, duration_sec.
    `extra_conditions` is a list of SQLAlchemy WHERE clauses (ACL) to AND in.
    """
    cap = _cap_from_duration(_opt(opts, "duration_sec"))
    base = _base_conditions(extra_conditions)

    # ── person across the years ──────────────────────────────────────────────
    if motto == "person_years":
        pid = _opt(opts, "person_id")
        if not pid:
            return []
        photo_ids = await _person_photo_ids(db, int(pid))
        if not photo_ids:
            return []
        photos = (await db.execute(
            select(Photo).where(*base, Photo.id.in_(photo_ids))
        )).scalars().all()
        return _spread_across_years(list(photos), cap)

    # ── person, happy/smiling moments ────────────────────────────────────────
    if motto == "person_happy":
        pid = _opt(opts, "person_id")
        if not pid:
            return []
        photo_ids = set(await _person_photo_ids(db, int(pid)))
        if not photo_ids:
            return []
        try:
            from app.services.photo_search import search_photos
            from app.services.settings_loader import load_settings
            s = await load_settings(db)
            hits = await search_photos(
                db, "lächeln fröhlich lachen glücklich", s,
                limit=cap * 4, extra_conditions=extra_conditions,
            )
        except Exception:
            await db.rollback()
            hits = []
        happy = [p for p in hits if p.id in photo_ids and p.thumb_large]
        if not happy:
            # fallback: just that person's photos, chronological
            photos = (await db.execute(
                select(Photo).where(*base, Photo.id.in_(list(photo_ids)))
                .order_by(Photo.taken_at)
            )).scalars().all()
            return list(photos)[:cap]
        happy.sort(key=lambda p: (p.taken_at or _MIN_DT()))
        return happy[:cap]

    # ── two people together (parent & child) over the years ──────────────────
    if motto == "parent_child":
        p1 = _opt(opts, "person_id")
        p2 = _opt(opts, "person_id2")
        if not p1 or not p2:
            return []
        ids1 = set(await _person_photo_ids(db, int(p1)))
        ids2 = set(await _person_photo_ids(db, int(p2)))
        both = ids1 & ids2
        if not both:
            return []
        photos = (await db.execute(
            select(Photo).where(*base, Photo.id.in_(list(both)))
            .order_by(Photo.taken_at)
        )).scalars().all()
        photos = list(photos)
        if len(photos) <= cap:
            return photos
        # evenly subsample across the timeline so the whole span is represented
        step = len(photos) / cap
        return [photos[int(i * step)] for i in range(cap)]

    # ── Muttertag / Vatertag: a tribute to one parent, preferring photos that
    #    also show the family (≥2 people), spread across the years ──────────────
    if motto in ("muttertag", "vatertag"):
        pid = _opt(opts, "person_id")
        if not pid:
            return []
        from app.models.face import Face
        ids = await _person_photo_ids(db, int(pid))
        if not ids:
            return []
        with_family = set((await db.execute(
            select(Face.photo_id).where(Face.photo_id.in_(ids), Face.person_id.isnot(None))
            .group_by(Face.photo_id).having(func.count(func.distinct(Face.person_id)) > 1)
        )).scalars().all())
        photos = list((await db.execute(
            select(Photo).where(*base, Photo.id.in_(ids)))).scalars().all())
        family = [p for p in photos if p.id in with_family]
        # use the with-family set if it's rich enough, else fall back to all of them
        pool = family if len(family) >= max(8, cap // 2) else photos
        return _spread_across_years(pool, cap)

    # ── best of a single year ────────────────────────────────────────────────
    if motto == "year_review":
        year = _opt(opts, "year")
        if not year:
            return []
        photos = list((await db.execute(
            select(Photo).where(*base, extract("year", Photo.taken_at) == int(year))
        )).scalars().all())
        # Spread across the MONTHS of the year (best-first per month, bursts collapsed)
        # → real year-in-review, not a clump of near-identical shots from one day.
        return _spread_even(photos, cap, lambda p: p.taken_at.month if p.taken_at else 0)

    # ── one representative per year, whole library ───────────────────────────
    if motto == "through_the_years":
        photos = (await db.execute(
            select(Photo).where(*base, Photo.taken_at.isnot(None))
        )).scalars().all()
        return _spread_across_years(list(photos), cap)

    # ── a trip / album in capture order ──────────────────────────────────────
    if motto == "trip":
        album_id = _opt(opts, "album_id")
        if not album_id:
            return []
        photos = (await db.execute(
            select(Photo)
            .join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id)
            .where(*base, AlbumPhoto.album_id == int(album_id))
            .order_by(Photo.taken_at, AlbumPhoto.sort_order)
        )).scalars().all()
        photos = list(photos)
        if len(photos) <= cap:
            return photos
        step = len(photos) / cap
        return [photos[int(i * step)] for i in range(cap)]

    # ── a season / holiday across years ──────────────────────────────────────
    if motto == "season":
        season = (_opt(opts, "season") or "").strip().lower()
        months: List[int] = []
        if season in _SEASON_MONTHS:
            months = _SEASON_MONTHS[season]
        else:
            m = _opt(opts, "month")
            if m:
                try:
                    months = [int(m)]
                except (TypeError, ValueError):
                    months = []
        if not months:
            return []
        photos = (await db.execute(
            select(Photo).where(
                *base,
                Photo.taken_at.isnot(None),
                extract("month", Photo.taken_at).in_(months),
            ).order_by(Photo.taken_at)
        )).scalars().all()
        photos = list(photos)
        if len(photos) <= cap:
            return photos
        step = len(photos) / cap
        return [photos[int(i * step)] for i in range(cap)]

    # ── newest N ─────────────────────────────────────────────────────────────
    if motto == "newest_50":
        n = min(cap, 50) if cap < 50 else cap
        photos = (await db.execute(
            select(Photo).where(*base)
            .order_by(Photo.taken_at.desc().nullslast(), Photo.id.desc())
            .limit(n)
        )).scalars().all()
        photos = list(photos)
        photos.sort(key=lambda p: (p.taken_at or _MIN_DT()))
        return photos

    # ── favorites ────────────────────────────────────────────────────────────
    if motto == "most_favorited":
        photos = (await db.execute(
            select(Photo).where(*base, Photo.is_favorite == True)   # noqa: E712
            .order_by(Photo.taken_at.desc().nullslast()).limit(cap)
        )).scalars().all()
        photos = list(photos)
        photos.sort(key=lambda p: (p.taken_at or _MIN_DT()))
        return photos

    # ── top rated ────────────────────────────────────────────────────────────
    if motto == "top_rated":
        photos = (await db.execute(
            select(Photo).where(*base, Photo.user_rating.isnot(None), Photo.user_rating > 0)
            .order_by(Photo.user_rating.desc(), Photo.taken_at.desc().nullslast())
            .limit(cap)
        )).scalars().all()
        photos = list(photos)
        photos.sort(key=lambda p: (p.taken_at or _MIN_DT()))
        return photos

    # ── random memories ──────────────────────────────────────────────────────
    if motto == "random_memories":
        photos = (await db.execute(
            select(Photo).where(*base).order_by(func.random()).limit(cap)
        )).scalars().all()
        return list(photos)

    # ── best of ANY album / smart-album (favorites & rated first) ─────────────
    if motto == "album_highlight":
        album_id = _opt(opts, "album_id")
        if not album_id:
            return []
        photos = (await db.execute(
            select(Photo)
            .join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id)
            .where(*base, AlbumPhoto.album_id == int(album_id))
            .order_by(
                Photo.is_favorite.desc(),
                Photo.user_rating.desc().nullslast(),
                Photo.taken_at, AlbumPhoto.sort_order,
            )
        )).scalars().all()
        best = _dedupe_bursts(list(photos))
        best.sort(key=_quality_key)
        best = best[:cap]
        best.sort(key=lambda p: (p.taken_at or _MIN_DT()))
        return best

    # ── several people together (intersection) over the years ─────────────────
    if motto == "people_together":
        raw = _opt(opts, "person_ids") or []
        try:
            pids = [int(x) for x in raw if x]
        except (TypeError, ValueError):
            pids = []
        if not pids:
            return []
        sets = [set(await _person_photo_ids(db, p)) for p in pids]
        common = set.intersection(*sets) if sets else set()
        if not common:
            return []
        photos = (await db.execute(
            select(Photo).where(*base, Photo.id.in_(list(common))).order_by(Photo.taken_at)
        )).scalars().all()
        return _spread_across_years(list(photos), cap)

    # ── highlight of the week: best of the last 7 (else 30) days ──────────────
    if motto == "week_review":
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        # Optional config (from the weekly settings): restrict to selected persons
        # and/or use a custom window (7=week, 30=month, 365=year).
        pids = _opt(opts, "person_ids") or ([_opt(opts, "person_id")] if _opt(opts, "person_id") else [])
        pids = [int(p) for p in (pids or []) if str(p).strip().isdigit() or isinstance(p, int)]
        person_cond = ([Photo.id.in_(select(Face.photo_id).where(Face.person_id.in_(pids)))] if pids else [])
        win = _opt(opts, "window_days")
        windows = [int(win)] if win else [7, 30]
        for days in windows:
            since = now - timedelta(days=days)
            photos = (await db.execute(
                select(Photo).where(*base, *person_cond, Photo.taken_at >= since)
                .order_by(
                    Photo.is_favorite.desc(),
                    Photo.user_rating.desc().nullslast(),
                    Photo.taken_at,
                )
            )).scalars().all()
            photos = list(photos)
            if photos:
                # spread across the days of the window, bursts collapsed
                return _spread_even(photos, cap, lambda p: p.taken_at.toordinal() if p.taken_at else 0)
        return []

    return []


# ── Slideshow rendering ─────────────────────────────────────────────────────────

def _scale_pad(w: int, h: int) -> str:
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,"
            f"fps=30,format=yuv420p")


def _fill_graph(inp: str, out: str, w: int, h: int) -> str:
    """Modern 'blur-fill' look instead of black bars: cover the WxH frame with a
    zoomed, blurred + dimmed copy of the image, then overlay the full image centred
    on top. Portraits/odd ratios fill the frame nicely (no tiny-thumbnail-on-black
    look). `inp`/`out` are filtergraph stream labels (without brackets)."""
    return (
        f"[{inp}]split=2[bg_{out}][fg_{out}];"
        f"[bg_{out}]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"gblur=sigma=22,eq=brightness=-0.07[bgb_{out}];"
        f"[fg_{out}]scale={w}:{h}:force_original_aspect_ratio=decrease[fgb_{out}];"
        f"[bgb_{out}][fgb_{out}]overlay=(W-w)/2:(H-h)/2,setsar=1,fps=30,format=yuv420p[{out}]"
    )


def _fill_vf(w: int, h: int) -> str:
    """Same blur-fill as `_fill_graph`, but as a simple `-vf` chain (implicit single
    in/out) for the concat fallback path."""
    return (
        f"split=2[a][b];"
        f"[b]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"gblur=sigma=22,eq=brightness=-0.07[bg];"
        f"[a]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps=30,format=yuv420p"
    )


# ── Beat detection (optional librosa) — drives "beat-sync" slideshows ──────────

def detect_beats(audio_path: str) -> List[float]:
    """Beat onset times (seconds) of a music track via librosa. Returns [] if
    librosa is unavailable or analysis fails — callers then fall back to uniform
    timing, so beat-sync degrades gracefully and NEVER breaks a render."""
    if not audio_path or not os.path.exists(audio_path):
        return []
    try:
        import librosa  # lazy: heavy import, optional dependency
        y, sr = librosa.load(audio_path, mono=True)
        _, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
        beats = librosa.frames_to_time(beat_frames, sr=sr)
        return [float(b) for b in beats if b > 0.05]
    except Exception:
        return []


def beat_durations(beats: List[float], n: int, target_per: float) -> Optional[List[float]]:
    """Pick a subset of `beats` so each of `n` images lasts ~target_per seconds
    and every transition lands on a beat. Returns per-image durations, or None
    if the beats are too sparse to be useful (→ caller uses uniform timing)."""
    if n <= 0 or len(beats) < 4:
        return None
    period = (beats[-1] - beats[0]) / max(1, len(beats) - 1)
    if period <= 0:
        return None
    step = max(1, round(target_per / period))         # beats per image
    picks = beats[::step]
    if len(picks) < 2:
        return None
    durs = [picks[i + 1] - picks[i] for i in range(len(picks) - 1)]
    durs = [max(0.5, d) for d in durs]
    # Stretch / trim the beat grid to exactly n images.
    if len(durs) < n:
        avg = sum(durs) / len(durs)
        durs += [avg] * (n - len(durs))
    return durs[:n]


def _audio_filter(music_idx: int, total: float, volume: float) -> str:
    """Filtergraph snippet that takes the looped music input, sets volume and a
    1.5s fade-out at the end, producing [outa]."""
    fo = max(0.0, total - 1.5)
    return (f"[{music_idx}:a]volume={max(0.0, min(2.0, volume)):.2f},"
            f"afade=t=out:st={fo:.2f}:d=1.5[outa]")


# ── Mood + CC0 library for soundtracks (Phase 2/3) ────────────────────────────

# motto → (mood key, style words for the generation prompt)
_MOODS = {
    "week_review":      ("bright", "uplifting, warm, gently upbeat"),
    "newest_50":        ("bright", "uplifting, warm, gently upbeat"),
    "year_review":      ("nostalgic", "nostalgic, cinematic, heartfelt"),
    "through_the_years":("nostalgic", "nostalgic, reflective, cinematic"),
    "album_highlight":  ("happy", "joyful, light, feel-good"),
    "season":           ("cozy", "cozy, warm, festive"),
    "parent_child":     ("tender", "tender, warm, emotional piano"),
}
_DEFAULT_MOOD = ("warm", "warm, gentle cinematic")


def mood_key(motto: str, opts: Optional[dict] = None) -> str:
    """A short mood label used to pick a library track."""
    if opts and isinstance(opts.get("mood"), str) and opts["mood"] not in ("", "auto"):
        return opts["mood"]
    return _MOODS.get(motto, _DEFAULT_MOOD)[0]


def mood_prompt(motto: str, opts: Optional[dict] = None) -> str:
    """Build a text prompt for music generation from the highlight's motto/season.
    Only this short text ever leaves the machine for cloud generation — no photos."""
    if opts and isinstance(opts.get("mood"), str) and opts["mood"] not in ("", "auto"):
        style = opts["mood"]
    else:
        style = _MOODS.get(motto, _DEFAULT_MOOD)[1]
    return (f"{style}, instrumental, no vocals, soft dynamics, "
            f"suitable as a background soundtrack for a family photo slideshow")


def library_dir(cache_path: str) -> str:
    return os.path.join(cache_path, "music", "library")


def library_pick(cache_path: str, mood: str) -> Optional[str]:
    """Pick a track from the CC0/generated library: prefer the mood (filename
    prefix `mood_…`), else any track. Returns None if the library is empty."""
    import glob
    import random
    d = library_dir(cache_path)
    if not os.path.isdir(d):
        return None
    files = [f for f in glob.glob(os.path.join(d, "*")) if os.path.isfile(f)]
    if not files:
        return None
    matched = [f for f in files if os.path.basename(f).lower().startswith(mood.lower() + "_")]
    return random.choice(matched or files)


def render_slideshow(image_paths: List[str], out_path: str, seconds_per: float,
                     width: int = 1920, height: int = 1080,
                     music_path: Optional[str] = None, beat_sync: bool = False,
                     music_volume: float = 0.8) -> bool:
    """Render a slideshow MP4 from `image_paths` (cached large thumbnails).

    Optionally lays a music track under it, and — when `beat_sync` is on and the
    track yields usable beats — varies the per-image durations so transitions
    land on the beat. Tries xfade first, falls back to concat. Output: H.264 +
    yuv420p + AAC + faststart. Returns True if an MP4 was written.
    """
    images = [p for p in image_paths if p and os.path.exists(p)]
    if not images:
        return False

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    seconds_per = max(0.8, float(seconds_per or 2.5))
    music = music_path if (music_path and os.path.exists(music_path)) else None

    # Per-image durations: beat-synced when possible, else uniform.
    durations = [seconds_per] * len(images)
    if music and beat_sync:
        bd = beat_durations(detect_beats(music), len(images), seconds_per)
        if bd:
            durations = bd

    if len(images) >= 2 and _render_xfade(images, out_path, durations, width, height, music, music_volume):
        return True
    if _render_concat(images, out_path, durations, width, height, music, music_volume):
        return True
    return os.path.exists(out_path) and os.path.getsize(out_path) > 1000


def _render_xfade(images: List[str], out_path: str, durations: List[float],
                  width: int, height: int,
                  music: Optional[str] = None, volume: float = 0.8) -> bool:
    """Crossfade chain with per-image `durations` (beat-synced or uniform) and
    an optional looped music bed. Kept modest in size to avoid a huge graph."""
    if len(images) > 80:
        return False
    n = len(images)
    fade = min(0.6, min(durations) * 0.4)
    total = sum(durations)

    cmd = [_FFMPEG, "-y", "-hide_banner", "-loglevel", "error"]
    for img, dur in zip(images, durations):
        cmd += ["-loop", "1", "-t", f"{dur + fade:.3f}", "-i", img]
    if music:
        cmd += ["-stream_loop", "-1", "-i", music]   # loop music to cover the video

    filt = [_fill_graph(f"{i}:v", f"v{i}", width, height) for i in range(n)]
    last, cum = "v0", durations[0]
    for i in range(1, n):
        out_lbl = "outv" if i == n - 1 else f"x{i}"
        filt.append(f"[{last}][v{i}]xfade=transition=fade:duration={fade:.3f}:"
                    f"offset={cum:.3f}[{out_lbl}]")
        last = out_lbl
        cum += durations[i]
    if n == 1:
        filt.append(f"[v0]null[outv]")
    if music:
        filt.append(_audio_filter(n, total, volume))

    cmd += ["-filter_complex", ";".join(filt), "-map", "[outv]"]
    if music:
        cmd += ["-map", "[outa]", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=_RENDER_TIMEOUT)
        return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000
    except Exception:
        return False


def _render_concat(images: List[str], out_path: str, durations: List[float],
                   width: int, height: int,
                   music: Optional[str] = None, volume: float = 0.8) -> bool:
    """Plain concat slideshow (no transitions) with per-image `durations` and an
    optional looped music bed. The always-works fallback."""
    tmp = tempfile.mkdtemp(prefix="pfhl_")
    list_file = os.path.join(tmp, "list.txt")
    try:
        lines = []
        for img, dur in zip(images, durations):
            lines.append(f"file '{img}'")
            lines.append(f"duration {dur:.3f}")
        lines.append(f"file '{images[-1]}'")   # concat drops last duration → repeat
        with open(list_file, "w") as f:
            f.write("\n".join(lines) + "\n")

        total = sum(durations)
        cmd = [_FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
               "-f", "concat", "-safe", "0", "-i", list_file]
        if music:
            cmd += ["-stream_loop", "-1", "-i", music]
            # video chain via -filter_complex (so we can also map audio)
            filt = f"[0:v]{_fill_vf(width, height)}[outv];" + _audio_filter(1, total, volume)
            cmd += ["-filter_complex", filt, "-map", "[outv]", "-map", "[outa]",
                    "-c:a", "aac", "-b:a", "192k", "-shortest"]
        else:
            cmd += ["-vf", _fill_vf(width, height)]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path]
        r = subprocess.run(cmd, capture_output=True, timeout=_RENDER_TIMEOUT)
        return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000
    except Exception:
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_hybrid(clip_paths: List[str], slideshow_path: Optional[str], out_path: str,
                  width: int = 1920, height: int = 1080, music_path: Optional[str] = None) -> bool:
    """Stitch AI-animated clips + the still slideshow into ONE reel. Every segment is
    re-encoded to the same WxH/30fps (via the concat FILTER, not the demuxer, so
    mismatched fal/veo clip sizes don't break it). Optional background music over the
    whole thing. Robust → returns False on any failure so the caller falls back to the
    plain slideshow. Order: animated clips first, then the slideshow of the rest."""
    segments = [c for c in (clip_paths or []) if c and os.path.exists(c) and os.path.getsize(c) > 1000]
    if slideshow_path and os.path.exists(slideshow_path):
        segments.append(slideshow_path)
    if not segments:
        return False
    cmd = [_FFMPEG, "-y", "-hide_banner", "-loglevel", "error"]
    for s in segments:
        cmd += ["-i", s]
    music_idx = None
    if music_path and os.path.exists(music_path):
        cmd += ["-i", music_path]
        music_idx = len(segments)
    sp = _scale_pad(width, height)
    filt = [f"[{i}:v]{sp},fps=30,setsar=1,format=yuv420p[v{i}]" for i in range(len(segments))]
    filt.append("".join(f"[v{i}]" for i in range(len(segments))) + f"concat=n={len(segments)}:v=1:a=0[outv]")
    cmd += ["-filter_complex", ";".join(filt), "-map", "[outv]"]
    if music_idx is not None:
        cmd += ["-map", f"{music_idx}:a", "-shortest", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=_RENDER_TIMEOUT)
        return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000
    except Exception:
        return False


def highlight_output_path(cache_path: str, highlight_id: int) -> str:
    return os.path.join(cache_path, "highlights", f"{highlight_id}.mp4")
