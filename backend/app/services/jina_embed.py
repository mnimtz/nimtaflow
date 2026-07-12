"""jina-clip-v2 — multimodal embeddings (image + multilingual text) in ONE joint
vector space.

Used for:
  • VISUAL search: a German query → image vectors directly (finds things no
    description mentions, works even before a photo is described).
  • description-TEXT search: the AI description → a text vector in the same space.

Same model runs on GPU (remote bulk worker) or CPU (cpu-host — everyday trickle +
the search query), so every vector is comparable → one space. 768-dim via the
model's Matryoshka truncation, so it fits the existing pgvector(768) column.

Loaded via transformers AutoModel (NOT sentence-transformers — that path errors
on jina's custom `custom_st` module). The model is multilingual (89 langs, strong
German: "Hund im Garten" ↔ "dog in the garden" ≈ 0.91).
"""
import os
from typing import List, Optional

from PIL import Image

_MODEL = "jinaai/jina-clip-v2"
_DIM = 768
_cache: dict = {}


def _get():
    """Lazy-load + cache the model (single instance per process)."""
    if "m" not in _cache:
        import torch
        from transformers import AutoModel
        m = AutoModel.from_pretrained(_MODEL, trust_remote_code=True)
        want_cpu = os.getenv("JINA_DEVICE", "auto").lower() == "cpu"
        dev = "cuda" if (torch.cuda.is_available() and not want_cpu) else "cpu"
        try:
            m = m.to(dev)
        except Exception:
            dev = "cpu"
        m.eval()
        _cache["m"], _cache["dev"] = m, dev
    return _cache["m"]


def _norm(vec) -> List[float]:
    import numpy as np
    a = np.asarray(vec, dtype="float32")
    n = float(np.linalg.norm(a)) or 1.0
    return (a / n).tolist()


def embed_image(image: Image.Image) -> Optional[List[float]]:
    """768-dim L2-normalised image vector, or None on failure."""
    try:
        import torch
        m = _get()
        # inference_mode disables autograd graph building. Without it, jina's
        # encode_* retained grad tensors per call, so the long-lived backend
        # process grew a few hundred MB per search/chat query until the kernel
        # OOM-killed it (SIGKILL/137) → 502s + empty pages. Inference needs no
        # gradients, so this both fixes the leak and speeds up encoding.
        with torch.inference_mode():
            vec = m.encode_image([image.convert("RGB")], truncate_dim=_DIM)[0]
        return _norm(vec)
    except Exception:
        return None


_LOAD_ATTEMPTED = False
_LOAD_FAILED = False


def embed_text(text: str) -> Optional[List[float]]:
    """v1.543: Auf CPU-only-Containern (backend im LXC) hängt der Modell-Load
    oft und blockt so JEDEN Chat-Call auf 90 s Timeout. Wir versuchen den
    Load EINMAL beim ersten Aufruf mit hartem Timeout. Failed er, schalten
    wir für den Prozess dauerhaft auf None-Rückgabe — Text-Vector-Search fällt
    weg, Suche degradiert auf Keyword+Structural, aber der Chat antwortet
    innerhalb Sekunden."""
    global _LOAD_ATTEMPTED, _LOAD_FAILED
    text = (text or "").strip()
    if not text:
        return None
    if _LOAD_FAILED:
        return None
    if not _LOAD_ATTEMPTED:
        _LOAD_ATTEMPTED = True
        # Model-Load mit 12 s Deckel — fällt es länger, bleibt es aus dem
        # Chat-Pfad raus, statt jeden Turn zu blockieren.
        import threading, queue as _q
        q: _q.Queue = _q.Queue()
        def _try_load():
            try:
                _get(); q.put(True)
            except Exception as e:
                q.put(e)
        th = threading.Thread(target=_try_load, daemon=True)
        th.start()
        try:
            r = q.get(timeout=12.0)
            if r is not True:
                _LOAD_FAILED = True
                return None
        except _q.Empty:
            _LOAD_FAILED = True
            return None
    try:
        import torch
        m = _get()
        with torch.inference_mode():
            vec = m.encode_text([text], truncate_dim=_DIM)[0]
        return _norm(vec)
    except Exception:
        return None


def available() -> bool:
    try:
        _get()
        return True
    except Exception:
        return False
