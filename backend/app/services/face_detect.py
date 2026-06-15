"""Local face detection + embedding via facenet-pytorch (MTCNN + InceptionResnetV1).

Pure-Python on top of the already-installed torch — no compiler, no InsightFace
build. Produces 512-dim embeddings (fits the faces.embedding Vector(512) column)
and relative bounding boxes. Models download once to TORCH_HOME (/models volume).
Lazy-loaded and fully best-effort: any failure returns [].
"""
from typing import List
from PIL import Image
from app.services.ai.base import DetectedFace

_cache: dict = {}


def _models():
    if "m" in _cache:
        return _cache["m"]
    from facenet_pytorch import MTCNN, InceptionResnetV1
    # keep_all → detect every face; post_process False → keep raw crops for ArcFace-style net
    mtcnn = MTCNN(keep_all=True, device="cpu", post_process=True, min_face_size=40)
    resnet = InceptionResnetV1(pretrained="vggface2").eval()
    _cache["m"] = (mtcnn, resnet)
    return _cache["m"]


def detect_faces(image: Image.Image, min_conf: float = 0.9) -> List[DetectedFace]:
    try:
        import torch
        img = image.convert("RGB")
        W, H = img.size
        mtcnn, resnet = _models()
        boxes, probs = mtcnn.detect(img)
        if boxes is None:
            return []
        aligned = mtcnn.extract(img, boxes, save_path=None)  # tensor [n,3,160,160]
        if aligned is None:
            return []
        if aligned.ndim == 3:
            aligned = aligned.unsqueeze(0)
        with torch.no_grad():
            embs = resnet(aligned).tolist()
        out: List[DetectedFace] = []
        for box, prob, emb in zip(boxes, probs, embs):
            if prob is None or float(prob) < min_conf:
                continue
            x1, y1, x2, y2 = [float(v) for v in box]
            out.append(DetectedFace(
                bbox_x=max(0.0, min(1.0, x1 / W)),
                bbox_y=max(0.0, min(1.0, y1 / H)),
                bbox_w=max(0.0, min(1.0, (x2 - x1) / W)),
                bbox_h=max(0.0, min(1.0, (y2 - y1) / H)),
                confidence=float(prob),
                embedding=emb,
            ))
        return out
    except Exception:
        return []


def available() -> bool:
    try:
        import facenet_pytorch  # noqa
        return True
    except Exception:
        return False


# ── Engine dispatch ────────────────────────────────────────────────────────────
# Lets the face engine be chosen in Settings (face.engine). InsightFace/ArcFace
# is more accurate; facenet is the lighter default. Both yield 512-dim embeddings.

def engine_available(engine: str) -> bool:
    if engine == "insightface":
        try:
            from app.services import face_detect_insightface as fi
            return fi.available()
        except Exception:
            return False
    return available()


def detect_faces_engine(image: Image.Image, min_conf: float, engine: str) -> List[DetectedFace]:
    """Detect with the requested engine, falling back to facenet if the
    requested one isn't installed/loadable (so a half-built image still works)."""
    if engine == "insightface":
        try:
            from app.services import face_detect_insightface as fi
            if fi.available():
                return fi.detect_faces(image, min_conf)
        except Exception:
            pass
    return detect_faces(image, min_conf)
