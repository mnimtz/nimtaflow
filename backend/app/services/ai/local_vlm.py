"""Integrated (local) vision-language provider — no Ollama/cloud required.

Two tiers, selectable in settings:
  - "florence2-base"  (Optimum): small/fast, English captions → translated to DE
  - "qwen2.5-vl-3b"   (Best):    larger, multilingual (native German)

Models load lazily on first use and are cached for the worker's lifetime.
Everything is wrapped defensively: if torch/transformers or a model is missing,
methods return empty results so the pipeline degrades gracefully (best-effort).

Downloads are cached to HF_HOME (/models volume) so they survive rebuilds.
"""
from typing import List, Optional
from PIL import Image

from .base import AIProvider, DetectedFace

MODELS = {
    "florence2-base": "microsoft/Florence-2-base",
    "qwen2.5-vl-3b": "Qwen/Qwen2.5-VL-3B-Instruct",
}
EMBED_MODEL = "intfloat/multilingual-e5-base"
TRANSLATE_MODEL = "Helsinki-NLP/opus-mt-en-de"

# process-wide caches (load once)
_vlm_cache: dict = {}
_embed_cache: dict = {}
_translate_cache: dict = {}


class LocalVLMProvider(AIProvider):
    name = "local"

    def __init__(self, model_key: str = "florence2-base"):
        self.model_key = model_key if model_key in MODELS else "florence2-base"
        self.repo = MODELS[self.model_key]

    # ── lazy loaders ──────────────────────────────────────────────────────────
    def _load_vlm(self):
        if self.model_key in _vlm_cache:
            return _vlm_cache[self.model_key]
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor
        if self.model_key == "florence2-base":
            # work around Florence-2's hard flash_attn import on CPU
            from unittest.mock import patch
            import transformers.dynamic_module_utils as dmu
            _orig = dmu.get_imports

            def _no_flash(filename):
                imports = _orig(filename)
                return [i for i in imports if i != "flash_attn"]

            with patch.object(dmu, "get_imports", _no_flash):
                model = AutoModelForCausalLM.from_pretrained(
                    self.repo, trust_remote_code=True, torch_dtype=torch.float32
                )
                proc = AutoProcessor.from_pretrained(self.repo, trust_remote_code=True)
            _vlm_cache[self.model_key] = ("florence", model.eval(), proc)
        else:  # qwen2.5-vl
            from transformers import Qwen2_5_VLForConditionalGeneration
            model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                self.repo, torch_dtype=torch.float32
            )
            proc = AutoProcessor.from_pretrained(self.repo)
            _vlm_cache[self.model_key] = ("qwen", model.eval(), proc)
        return _vlm_cache[self.model_key]

    def _translate_de(self, text: str) -> str:
        if not text:
            return text
        try:
            if "t" not in _translate_cache:
                from transformers import MarianMTModel, MarianTokenizer
                tok = MarianTokenizer.from_pretrained(TRANSLATE_MODEL)
                mdl = MarianMTModel.from_pretrained(TRANSLATE_MODEL)
                _translate_cache["t"] = (tok, mdl)
            tok, mdl = _translate_cache["t"]
            batch = tok([text], return_tensors="pt", truncation=True, max_length=512)
            out = mdl.generate(**batch, max_length=512)
            return tok.decode(out[0], skip_special_tokens=True)
        except Exception:
            return text  # fall back to original (English) on any failure

    # ── interface ───────────────────────────────────────────────────────────
    async def describe_image(self, image: Image.Image, language: str = "de", prompt: Optional[str] = None) -> str:
        try:
            kind, model, proc = self._load_vlm()
            import torch
            image = image.convert("RGB")
            if kind == "florence":
                # Florence-2 only understands its task tokens, not free prompts
                task = "<MORE_DETAILED_CAPTION>"
                inputs = proc(text=task, images=image, return_tensors="pt")
                with torch.no_grad():
                    ids = model.generate(
                        input_ids=inputs["input_ids"],
                        pixel_values=inputs["pixel_values"],
                        max_new_tokens=256, num_beams=3, do_sample=False,
                    )
                text = proc.batch_decode(ids, skip_special_tokens=True)[0]
                parsed = proc.post_process_generation(
                    text, task=task, image_size=(image.width, image.height)
                )
                caption = (parsed.get(task) or "").strip() if isinstance(parsed, dict) else str(parsed).strip()
                if language == "de":
                    caption = self._translate_de(caption)
                return caption
            else:  # qwen — multilingual, honours a custom prompt directly
                lang_word = {"de": "auf Deutsch", "en": "in English", "fr": "en français", "es": "en español"}.get(language, "auf Deutsch")
                user_text = prompt or f"Beschreibe dieses Bild {lang_word} in 1-2 Sätzen, sachlich."
                messages = [{"role": "user", "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": user_text},
                ]}]
                text = proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                from qwen_vl_utils import process_vision_info
                img_inputs, vid_inputs = process_vision_info(messages)
                inputs = proc(text=[text], images=img_inputs, videos=vid_inputs, padding=True, return_tensors="pt")
                with torch.no_grad():
                    gen = model.generate(**inputs, max_new_tokens=256)
                trimmed = [o[len(i):] for i, o in zip(inputs.input_ids, gen)]
                return proc.batch_decode(trimmed, skip_special_tokens=True)[0].strip()
        except Exception:
            return ""

    async def generate_tags(self, image: Image.Image) -> List[str]:
        # Derive simple tags from the caption (keeps deps minimal & robust)
        try:
            caption = await self.describe_image(image, "en")
            import re
            words = re.findall(r"[a-zA-ZäöüÄÖÜ]{4,}", caption.lower())
            stop = {"this", "that", "with", "from", "image", "photo", "shows", "there", "appears", "while", "their", "have", "very", "into", "over"}
            seen, tags = set(), []
            for w in words:
                if w not in stop and w not in seen:
                    seen.add(w); tags.append(w)
            return tags[:12]
        except Exception:
            return []

    async def detect_faces(self, image: Image.Image) -> List[DetectedFace]:
        return []  # handled by the dedicated InsightFace step (Stage 3)

    async def embed_text(self, text: str) -> List[float]:
        if not text:
            return []
        try:
            if "m" not in _embed_cache:
                from sentence_transformers import SentenceTransformer
                _embed_cache["m"] = SentenceTransformer(EMBED_MODEL)
            model = _embed_cache["m"]
            vec = model.encode(f"passage: {text}", normalize_embeddings=True)
            return vec.tolist()
        except Exception:
            return []

    async def is_available(self) -> bool:
        try:
            import torch  # noqa
            import transformers  # noqa
            return True
        except Exception:
            return False
