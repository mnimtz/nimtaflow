"""Face detection + embedding via InsightFace (SCRFD detector + ArcFace).

Uses the `buffalo_l` model pack: SCRFD for detection and a ResNet50 ArcFace
recognition head producing **512-dim, L2-normalised** embeddings — the same
dimensionality as the facenet path, so it drops straight into the existing
faces.embedding Vector(512) column with no migration.

Runs on CPU via onnxruntime (GPU automatically if onnxruntime-gpu is present).
Models download once into INSIGHTFACE_HOME (kept on the /models volume).
Lazy-loaded and fully best-effort: any failure returns [] so the pipeline
degrades to the other engine / no faces rather than crashing.
"""
import os
from typing import List
from PIL import Image

from app.services.ai.base import DetectedFace

_cache: dict = {}
_ROOT = os.getenv("INSIGHTFACE_HOME", "/models/insightface")


def _app():
    if "app" in _cache:
        return _cache["app"]
    from insightface.app import FaceAnalysis
    # CPU by default; onnxruntime picks CUDA automatically if the GPU build is present.
    providers = ["CPUExecutionProvider"]
    try:
        import onnxruntime as ort
        if "CUDAExecutionProvider" in ort.get_available_providers():
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    except Exception:
        pass
    app = FaceAnalysis(name="buffalo_l", root=_ROOT, providers=providers,
                       allowed_modules=["detection", "recognition"])
    app.prepare(ctx_id=0 if providers[0].startswith("CUDA") else -1, det_size=(640, 640))
    _cache["app"] = app
    return app


def detect_faces(image: Image.Image, min_conf: float = 0.5) -> List[DetectedFace]:
    try:
        import numpy as np
        img = image.convert("RGB")
        W, H = img.size
        # InsightFace expects BGR (cv2 convention)
        arr = np.asarray(img)[:, :, ::-1]
        faces = _app().get(arr)
        out: List[DetectedFace] = []
        for f in faces:
            score = float(getattr(f, "det_score", 1.0) or 0.0)
            if score < min_conf:
                continue
            emb = getattr(f, "normed_embedding", None)
            if emb is None:
                continue
            x1, y1, x2, y2 = [float(v) for v in f.bbox]
            out.append(DetectedFace(
                bbox_x=max(0.0, min(1.0, x1 / W)),
                bbox_y=max(0.0, min(1.0, y1 / H)),
                bbox_w=max(0.0, min(1.0, (x2 - x1) / W)),
                bbox_h=max(0.0, min(1.0, (y2 - y1) / H)),
                confidence=score,
                embedding=[float(x) for x in emb],
            ))
        return out
    except Exception:
        return []


def available() -> bool:
    try:
        import insightface  # noqa
        import onnxruntime  # noqa
        return True
    except Exception:
        return False
