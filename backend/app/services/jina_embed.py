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
        m = _get()
        vec = m.encode_image([image.convert("RGB")], truncate_dim=_DIM)[0]
        return _norm(vec)
    except Exception:
        return None


def embed_text(text: str) -> Optional[List[float]]:
    """768-dim L2-normalised text vector (multilingual), or None."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        m = _get()
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
