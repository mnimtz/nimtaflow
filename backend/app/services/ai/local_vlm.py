"""Integrated (local) vision-language provider — no Ollama/cloud required.

Two tiers, selectable in settings:
  - "florence2-base"  (Optimum): small/fast, English captions → translated to DE
  - "qwen2.5-vl-3b"   (Best):    larger, multilingual (native German)

Models load lazily on first use and are cached for the worker's lifetime.
Everything is wrapped defensively: if torch/transformers or a model is missing,
methods return empty results so the pipeline degrades gracefully (best-effort).

Downloads are cached to HF_HOME (/models volume) so they survive rebuilds.
"""
import os
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

# In a structured/JSON tag response: keys whose VALUE is a sentence, not tags —
# skipped even in valid JSON (we don't want the description text as a tag).
_NON_TAG_KEYS = {
    "beschreibung_kurz", "beschreibung", "description", "summary", "caption",
}
# All recognised tag-container field NAMES. Used only when salvaging truncated
# JSON via regex, so the key strings themselves don't end up as tags.
_TAG_FIELD_KEYS = _NON_TAG_KEYS | {
    "top_tags", "personen_tags", "aktivitaets_tags", "objekt_tags", "ort_tags",
    "tier_tags", "natur_tags", "ereignis_tags", "stimmungs_tags",
    "technische_tags", "suchbegriffe", "tags", "keywords",
}


_STRUCT_WORDS = {
    "beschreibungkurz", "beschreibung", "name", "ziel", "regeln", "anforderungen",
    "beispiel", "json", "stimmung", "stimmungs", "qualitat", "qualitats", "qualität",
    "technisch", "technische", "personen", "objekt", "ort", "tier", "natur", "ereignis",
}


def _is_structural_tag(t: str) -> bool:
    """True if a candidate is leaked JSON scaffolding (a field name / key) rather
    than a real tag — e.g. 'top_tags', 'personen_tags', 'natur_tages', 'suchbegriffe',
    '[]', 'beschreibung_kurz'. Robust to the mangling a small model adds under
    repetition_penalty (spaces/missing underscores)."""
    import re as _re
    n = _re.sub(r"[\s_:\[\]\"'.,]+", "", (t or "").lower())
    if len(n) < 2:
        return True
    if n.endswith(("tags", "tages", "tag", "begriffe")):
        return True
    return n in _STRUCT_WORDS


def _extract_tag_candidates(raw: str) -> List[str]:
    """Turn a tag-prompt response into a flat list of candidate tags.

    Supports three shapes, in order:
      1. A JSON object (e.g. {top_tags:[…], ort_tags:[…], suchbegriffe:[…]}) —
         flattens every list/string value EXCEPT the description sentence.
      2. Truncated/invalid JSON — salvages every quoted string, dropping the
         known field-name keys (Qwen's 256-token cap often cuts JSON mid-array).
      3. Plain comma/newline list — the original simple behaviour.
    """
    import json, re
    raw = (raw or "").strip()

    def _collect(obj) -> List[str]:
        out: List[str] = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).strip().lower() in _NON_TAG_KEYS:
                    continue
                out += _collect(v)
        elif isinstance(obj, list):
            for v in obj:
                out += _collect(v)
        elif isinstance(obj, str):
            out.append(obj)
        return out

    # 1) strict JSON (grab the outermost {...} if there's surrounding prose)
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            return _collect(json.loads(m.group(0)))
        except Exception:
            pass
    # 2) truncated JSON → quoted strings minus the field-name keys
    if "{" in raw or '":' in raw:
        quoted = re.findall(r'"([^"\n]+)"', raw)
        cand = [s for s in quoted if s.strip().lower() not in _TAG_FIELD_KEYS]
        if cand:
            return cand
    # 3) plain delimited list
    return re.split(r"[,\n;•\-–]+", raw)


class LocalVLMProvider(AIProvider):
    name = "local"

    def __init__(self, model_key: str = "florence2-base"):
        self.model_key = model_key if model_key in MODELS else "florence2-base"
        self.repo = MODELS[self.model_key]

    @property
    def label(self) -> str:
        return f"local:{self.model_key}"

    # ── lazy loaders ──────────────────────────────────────────────────────────
    def _load_vlm(self):
        if self.model_key in _vlm_cache:
            return _vlm_cache[self.model_key]
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor
        # Use the GPU in fp16 when available (huge speed-up; fp16 also lets the
        # 3B Qwen fit in the RTX 2080's 8 GB). CPU stays fp32.
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
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
                    self.repo, trust_remote_code=True, torch_dtype=dtype
                )
                proc = AutoProcessor.from_pretrained(self.repo, trust_remote_code=True)
            _vlm_cache[self.model_key] = ("florence", model.eval().to(device), proc, device, dtype)
        else:  # qwen2.5-vl
            from transformers import Qwen2_5_VLForConditionalGeneration
            if device == "cuda":
                # Qwen-3B fp16 weights (~7.5 GB) leave no room for inference
                # activations on an 8 GB card → every generate() OOMs. 4-bit nf4
                # shrinks the weights to ~2.5 GB so it actually runs. Needs
                # bitsandbytes; falls back to fp16 if that import fails.
                try:
                    from transformers import BitsAndBytesConfig
                    bnb = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=torch.float16,
                        bnb_4bit_use_double_quant=True,
                    )
                    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                        self.repo, quantization_config=bnb, device_map={"": 0},
                        torch_dtype=torch.float16,
                    )
                except Exception:
                    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                        self.repo, torch_dtype=dtype
                    ).to(device)
            else:
                model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                    self.repo, torch_dtype=dtype
                ).to(device)
            proc = AutoProcessor.from_pretrained(self.repo)
            _vlm_cache[self.model_key] = ("qwen", model.eval(), proc, device, dtype)
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
    async def describe_image(self, image: Image.Image, language: str = "de", prompt: Optional[str] = None,
                             max_new_tokens: int = 512, frames: Optional[List[Image.Image]] = None,
                             repetition_penalty: float = 1.0) -> str:
        try:
            kind, model, proc, device, dtype = self._load_vlm()
            import torch
            image = image.convert("RGB")
            # Cap the input resolution. A full 4000×3000 HEIC produces huge
            # pixel/activation tensors that OOM the 8 GB card; ~1280 px keeps
            # caption quality while bounding VRAM. Best-effort.
            try:
                max_edge = int(os.getenv("VLM_MAX_EDGE", "1280"))
                if max(image.size) > max_edge:
                    image.thumbnail((max_edge, max_edge), Image.LANCZOS)
            except Exception:
                pass
            if kind == "florence":
                # Florence-2 only understands its task tokens, not free prompts
                task = "<MORE_DETAILED_CAPTION>"
                inputs = proc(text=task, images=image, return_tensors="pt")
                with torch.no_grad():
                    ids = model.generate(
                        input_ids=inputs["input_ids"].to(device),
                        pixel_values=inputs["pixel_values"].to(device, dtype),
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
                # The fallback (used only when no ai.prompt.image is configured)
                # must be detailed + explicitly single-language: a terse prompt
                # lets this multilingual model code-switch into Chinese mid-text.
                user_text = prompt or (
                    f"Beschreibe dieses Foto sachlich in 2-3 Sätzen {lang_word}. "
                    f"Nenne Personen, Ort, Aktivität und Stimmung. Antworte ausschließlich {lang_word}."
                )
                if frames:
                    # Multi-frame video mode: downscale each frame hard (≤448 px)
                    # so up to 16 frames still fit the 8 GB card, and pass them as
                    # a video so Qwen reasons over the whole clip.
                    vframes = []
                    for fr in frames:
                        fr = fr.convert("RGB")
                        if max(fr.size) > 448:
                            fr.thumbnail((448, 448), Image.LANCZOS)
                        vframes.append(fr)
                    vid_text = user_text
                    if not prompt:
                        vid_text = (f"Dies sind Einzelbilder aus einem Video (zeitlich geordnet). "
                                    f"Beschreibe das Video als Ganzes sachlich in 2-4 Sätzen {lang_word} — "
                                    f"Personen, Ort, Handlung/Ablauf, Stimmung. Antworte ausschließlich {lang_word}.")
                    messages = [{"role": "user", "content": [
                        {"type": "video", "video": vframes},
                        {"type": "text", "text": vid_text},
                    ]}]
                else:
                    messages = [{"role": "user", "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": user_text},
                    ]}]
                text = proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                from qwen_vl_utils import process_vision_info
                img_inputs, vid_inputs = process_vision_info(messages)
                inputs = proc(text=[text], images=img_inputs, videos=vid_inputs, padding=True, return_tensors="pt")
                inputs = inputs.to(device)
                if "pixel_values" in inputs:  # match model dtype on GPU (fp16)
                    inputs["pixel_values"] = inputs["pixel_values"].to(dtype)
                with torch.no_grad():
                    # repetition_penalty defaults to 1.0 (off) for DESCRIPTIONS —
                    # on this multilingual model a penalty pushes prose into
                    # Chinese mid-sentence. The TAG pass passes >1.0 on purpose:
                    # for a discrete keyword list it breaks loops (e.g. the
                    # "babyschutzschal/-band/-…" runaway) without the prose risk.
                    gen = model.generate(**inputs, max_new_tokens=max_new_tokens,
                                         repetition_penalty=repetition_penalty)
                trimmed = [o[len(i):] for i, o in zip(inputs.input_ids, gen)]
                return proc.batch_decode(trimmed, skip_special_tokens=True)[0].strip()
        except Exception as e:
            # Surface *why* a description failed (OOM, bad file, …) instead of a
            # silent empty string — the worker's "AI lieferte keine Beschreibung"
            # warning otherwise hides the real cause.
            try:
                from app.services.feature_log import log as _flog
                _flog("ai", "WARNING", f"VLM-Fehler ({self.model_key}): {type(e).__name__}: {str(e)[:200]}")
            except Exception:
                pass
            return ""
        finally:
            # Release cached CUDA blocks between photos so fragmentation doesn't
            # accumulate into "tried to allocate X MiB, Y free" OOMs.
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    async def generate_tags(self, image: Image.Image, language: str = "de", prompt: Optional[str] = None,
                            caption: Optional[str] = None) -> List[str]:
        # If a tag prompt is configured AND the model can follow free prompts
        # (Qwen, not Florence), ask the VLM directly for a keyword list. This is
        # a SECOND model pass (≈ doubles GPU time per photo) — opt-in via the
        # 'ai.prompt.tags' setting. Otherwise derive tags cheaply from the caption.
        if prompt and self.model_key.startswith("qwen"):
            try:
                # Bigger budget: structured/JSON tag prompts are long and would
                # otherwise be truncated mid-output at the default 256 tokens.
                raw = await self.describe_image(image, language, prompt, max_new_tokens=640, repetition_penalty=1.3)
                cand = _extract_tag_candidates(raw)
                tags, seen = [], set()
                for c in cand:
                    t = c.strip().strip(".,;").lower()
                    # crisp keywords only: ≤3 words, no instruction-echo ("keine
                    # identifikation", "kein alter …"), no leaked JSON scaffold.
                    if not (2 <= len(t) <= 40) or t in seen:
                        continue
                    if len(t.split()) > 3 or t.startswith(("kein", "keine", "keiner", "ohne ", "nicht ")):
                        continue
                    if _is_structural_tag(t):
                        continue
                    seen.add(t); tags.append(t)
                if tags:
                    return tags[:25]
            except Exception:
                pass  # fall through to caption-derived tags
        # Derive simple tags from the caption (keeps deps minimal & robust).
        # REUSE the caption the caller already generated — re-running the VLM here
        # would be a second full pass (~doubles per-photo time). Only generate a
        # fresh caption if none was passed in.
        try:
            if not caption:
                caption = await self.describe_image(image, language)
            import re
            words = re.findall(r"[a-zA-ZäöüÄÖÜßéèêàâ]{4,}", caption.lower())
            stop = {
                # English
                "this", "that", "with", "from", "image", "photo", "shows", "there",
                "appears", "while", "their", "have", "very", "into", "over",
                # German
                "und", "oder", "eine", "einen", "einem", "einer", "dieser", "diese",
                "dieses", "wird", "sind", "auch", "sich", "dem", "den", "das", "der",
                "die", "ein", "mit", "auf", "von", "für", "ist", "bild", "foto",
                "zeigt", "sowie", "einige", "mehrere", "etwas", "sehr",
            }
            seen, tags = set(), []
            for w in words:
                if w not in stop and w not in seen:
                    seen.add(w); tags.append(w)
            return tags[:12]
        except Exception:
            return []

    async def generate_text(self, prompt: str, max_new_tokens: int = 400) -> str:
        """Text-only generation (for the local chat assistant). Qwen only.
        NB: slow on a CPU-only host — the chat toggle warns about this."""
        if not self.model_key.startswith("qwen"):
            return ""
        try:
            import torch
            kind, model, proc, device, dtype = self._load_vlm()
            messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
            text = proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = proc(text=[text], return_tensors="pt").to(device)
            with torch.no_grad():
                gen = model.generate(**inputs, max_new_tokens=max_new_tokens)
            trimmed = [o[len(i):] for i, o in zip(inputs.input_ids, gen)]
            return proc.batch_decode(trimmed, skip_special_tokens=True)[0].strip()
        except Exception as e:
            try:
                from app.services.feature_log import log as _flog
                _flog("ai", "WARNING", f"Chat-Textgenerierung fehlgeschlagen: {type(e).__name__}: {str(e)[:160]}")
            except Exception:
                pass
            return ""
        finally:
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

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
