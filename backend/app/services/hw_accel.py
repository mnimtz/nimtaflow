"""Detect available hardware video acceleration and build optimised ffmpeg args."""
import subprocess
import shutil
import os
import json
from dataclasses import dataclass, field
from typing import List, Optional
from functools import lru_cache

_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
# Cap encoder threads so a SOFTWARE (libx264) transcode can't grab every core and
# starve the interactive backend (the cause of "Galerie/Personen laden ewig" while a
# video backlog drains). Hardware encoders ignore it. Tune via FFMPEG_THREADS.
_FF_THREADS = os.environ.get("FFMPEG_THREADS", "3")
_FFPROBE = shutil.which("ffprobe") or "ffprobe"


def _probe_dims(path: str):
    """Source video stream dimensions (w, h) or None. Used to pre-compute the QSV
    scale target, because the QSV scaler (vpp_qsv) does NOT accept ffmpeg's
    min()/force_original_aspect_ratio expressions — we must pass explicit pixels."""
    try:
        r = subprocess.run(
            [_FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", path],
            capture_output=True, text=True, timeout=20)
        parts = r.stdout.strip().split("\n")[0].split("x")
        return int(parts[0]), int(parts[1])
    except Exception:
        return None


def _probe_source(path: str) -> dict:
    """Umfassendere Quell-Info: Dimensions, Framerate, Pixelformat, Farb-Transfer.
    Nötig für den Web-Transcode (10-bit-Erkennung, HDR-Downmix, fps-Cap).
    Fällt bei Fehler auf leeres dict zurück — nie fatal."""
    try:
        r = subprocess.run(
            [_FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries",
             "stream=width,height,r_frame_rate,pix_fmt,color_transfer,color_primaries",
             "-of", "default=nw=1", path],
            capture_output=True, text=True, timeout=20)
        out = {}
        for ln in (r.stdout or "").splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                out[k.strip()] = v.strip()
        # framerate parsen (r_frame_rate = "60000/1001" o.ä.)
        try:
            fr = out.get("r_frame_rate", "")
            if "/" in fr:
                n, d = fr.split("/"); out["_fps"] = float(n) / float(d)
            else:
                out["_fps"] = float(fr) if fr else 0.0
        except Exception:
            out["_fps"] = 0.0
        return out
    except Exception:
        return {}


def _is_hdr_or_10bit(info: dict) -> bool:
    """Erkennt 10-bit- oder HDR-Content. Web-Player können 10-bit AVC NICHT hardware-
    dekodieren → software decoding → Ruckeln. HDR-Farbtiefe wird zusätzlich zu SDR
    heruntergemischt."""
    pix = (info.get("pix_fmt") or "").lower()
    tr  = (info.get("color_transfer") or "").lower()
    return ("10le" in pix) or ("12le" in pix) or (tr in {"smpte2084", "arib-std-b67"})


def _scale_target(iw: int, ih: int, long_cap: int):
    """Cap the LONGER side to long_cap, preserve aspect, NEVER upscale, even dims."""
    m = max(iw, ih)
    if m <= long_cap:
        tw, th = iw, ih
    else:
        s = long_cap / m
        tw, th = round(iw * s), round(ih * s)
    return max(2, tw - tw % 2), max(2, th - th % 2)


@dataclass
class HWProfile:
    name: str                   # "cuda" | "qsv" | "vaapi" | "videotoolbox" | "software"
    hwaccel: Optional[str]      # ffmpeg -hwaccel value
    decode_args: List[str] = field(default_factory=list)
    encode_video_codec: str = "libvpx-vp9"  # VP9 software default
    encode_h264_codec: str = "libx264"
    encode_extra: List[str] = field(default_factory=list)
    available: bool = False
    info: str = ""


def _run(cmd: List[str], timeout: int = 8) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).decode(errors="replace")
    except Exception as e:
        return -1, str(e)


def _probe_cuda() -> HWProfile:
    """Check for NVIDIA CUDA / NVENC (RTX 2080 etc.)."""
    code, out = _run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
    if code != 0:
        return HWProfile(name="cuda", hwaccel="cuda", info="nvidia-smi not found")

    gpu_name = out.split("\n")[0].strip()

    # Verify ffmpeg has nvenc
    code2, out2 = _run([_FFMPEG, "-hide_banner", "-encoders"])
    has_nvenc = "h264_nvenc" in out2
    has_nvenc_hevc = "hevc_nvenc" in out2

    if not has_nvenc:
        return HWProfile(name="cuda", hwaccel="cuda", info=f"{gpu_name} — ffmpeg lacks h264_nvenc")

    return HWProfile(
        name="cuda",
        hwaccel="cuda",
        decode_args=["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"],
        encode_video_codec="h264_nvenc",
        encode_h264_codec="h264_nvenc",
        encode_extra=["-preset", "p4", "-tune", "hq", "-rc", "vbr", "-cq", "28", "-b:v", "0"],
        available=True,
        info=f"{gpu_name}, nvenc={'hevc+h264' if has_nvenc_hevc else 'h264'}",
    )


def _probe_qsv() -> HWProfile:
    """Check for Intel Quick Sync Video."""
    # Intel devices expose as /dev/dri/renderD*
    has_render = any(
        os.path.exists(f"/dev/dri/renderD{i}") for i in range(128, 140)
    )
    if not has_render:
        return HWProfile(name="qsv", hwaccel="qsv", info="No /dev/dri/renderD* found")

    code, out = _run([_FFMPEG, "-hide_banner", "-encoders"])
    has_qsv = "h264_qsv" in out

    # Real test: actually ENCODE a couple of frames with h264_qsv. The old test
    # (-hwaccel qsv on a nullsrc) returns 0 even when it silently runs on the CPU,
    # so it falsely reported QSV "available" and the transcode then fell back to
    # software at runtime. This exercises the same init_hw_device + hwupload +
    # h264_qsv path the transcode uses, so detection matches reality.
    code2, out2 = _run([
        _FFMPEG, "-hide_banner", "-init_hw_device", "qsv=hw", "-filter_hw_device", "hw",
        "-f", "lavfi", "-i", "testsrc=s=256x256:d=0.2",
        "-vf", "format=nv12,hwupload=extra_hw_frames=64",
        "-c:v", "h264_qsv", "-frames:v", "2", "-f", "null", "-",
    ], timeout=10)

    if not has_qsv or code2 != 0:
        return HWProfile(name="qsv", hwaccel="qsv", info=f"QSV encode test failed: {out2[-80:]}")

    return HWProfile(
        name="qsv",
        hwaccel="qsv",
        # Software-decode → QSV-encode (see build_transcode_cmd): robust across all
        # input codecs; the costly encode still runs on the Intel GPU.
        decode_args=[],
        encode_video_codec="h264_qsv",
        encode_h264_codec="h264_qsv",
        # global_quality 23: the 1080p web version now feeds BOTH the player AND
        # the video-AI frame sampling, so keep it crisp (lower = higher quality).
        encode_extra=["-global_quality", "23"],
        available=True,
        info="Intel Quick Sync (h264_qsv, sw-decode→qsv-encode)",
    )


def _probe_vaapi() -> HWProfile:
    """Check for VAAPI (Intel/AMD on Linux, fallback after QSV)."""
    device = "/dev/dri/renderD128"
    if not os.path.exists(device):
        return HWProfile(name="vaapi", hwaccel="vaapi", info="No VAAPI device")

    code, out = _run([_FFMPEG, "-hide_banner", "-encoders"])
    has_vaapi = "h264_vaapi" in out

    code2, _ = _run([
        _FFMPEG, "-hide_banner", "-hwaccel", "vaapi",
        "-hwaccel_device", device, "-hwaccel_output_format", "vaapi",
        "-f", "lavfi", "-i", "nullsrc=s=128x128:d=0.1",
        "-vf", "format=nv12|vaapi,hwupload",
        "-vframes", "1", "-f", "null", "-",
    ], timeout=6)

    if not has_vaapi or code2 != 0:
        return HWProfile(name="vaapi", hwaccel="vaapi", info="VAAPI test failed")

    return HWProfile(
        name="vaapi",
        hwaccel="vaapi",
        decode_args=[
            "-hwaccel", "vaapi",
            "-hwaccel_device", device,
            "-hwaccel_output_format", "vaapi",
        ],
        encode_video_codec="h264_vaapi",
        encode_h264_codec="h264_vaapi",
        encode_extra=["-qp", "28"],
        available=True,
        info=f"VAAPI ({device})",
    )


def _probe_videotoolbox() -> HWProfile:
    """Apple VideoToolbox — macOS only."""
    import platform
    if platform.system() != "Darwin":
        return HWProfile(name="videotoolbox", hwaccel="videotoolbox", info="Not macOS")

    code, out = _run([_FFMPEG, "-hide_banner", "-encoders"])
    if "h264_videotoolbox" not in out:
        return HWProfile(name="videotoolbox", hwaccel="videotoolbox", info="videotoolbox not in ffmpeg")

    return HWProfile(
        name="videotoolbox",
        hwaccel="videotoolbox",
        decode_args=["-hwaccel", "videotoolbox"],
        encode_video_codec="h264_videotoolbox",
        encode_h264_codec="h264_videotoolbox",
        encode_extra=["-q:v", "65", "-allow_sw", "1"],
        available=True,
        info="Apple VideoToolbox",
    )


@lru_cache(maxsize=1)
def detect_hw() -> HWProfile:
    """Return the best available hardware profile. Cached after first call."""
    if not shutil.which("ffmpeg"):
        return HWProfile(name="software", hwaccel=None, info="ffmpeg not found")

    for probe in [_probe_cuda, _probe_qsv, _probe_vaapi, _probe_videotoolbox]:
        try:
            p = probe()
            if p.available:
                return p
        except Exception:
            pass

    return HWProfile(
        name="software",
        hwaccel=None,
        encode_video_codec="libvpx-vp9",
        encode_h264_codec="libx264",
        available=True,
        info="Software encoding (libvpx-vp9 / libx264)",
    )


def build_transcode_cmd(
    input_path: str,
    output_path: str,
    resolution: int = 1080,
    codec: str = "h264",   # "h264" | "vp9"
    hw: Optional[HWProfile] = None,
) -> List[str]:
    """Build an ffmpeg command for web-optimised transcoding."""
    if hw is None:
        hw = detect_hw()

    # Cap the LONGER side to a 16:9-equivalent of `resolution` (1080 → 1920) and
    # NEVER upscale: the fit-box is clamped to the source size via min(), so small
    # old videos keep their NATIVE resolution instead of being blown up (upscaling
    # adds no detail, only bloat). force_original_aspect_ratio=decrease preserves
    # aspect (works for portrait too); force_divisible_by=2 keeps even dims for h264.
    _long = int(resolution * 16 / 9)
    scale = (f"scale=w='min({_long},iw)':h='min({_long},ih)'"
             ":force_original_aspect_ratio=decrease:force_divisible_by=2")

    # Quellenanalyse für HDR/10-bit + Framerate.
    src = _probe_source(input_path)
    is_hdr = _is_hdr_or_10bit(src)
    src_fps = src.get("_fps", 0.0)
    # 60fps-HDR-4K führt selbst auf Desktops zu Software-Decoding-Ruckeln, wenn 10-bit
    # nicht auf 8-bit abgemappt wird UND die Bitrate niedrig genug ist. Der Player
    # bekommt eine 30-fps-8-bit-SDR-Version, die Hardware-decodable ist.
    cap_fps = 30 if src_fps > 45 else 0   # 0 = keine Cap

    # Farbraum + 8-bit erzwingen. Ohne yuv420p behält ffmpeg das Quell-Pixelformat
    # (yuv420p10le bei iPhones ab 12 Pro) → H.264 „High 10" Profile → kein Browser
    # dekodiert das in Hardware → CPU-Software-Decoding → Ruckeln in Safari/iOS.
    #
    # Für HDR (HLG/PQ) mappen wir zusätzlich Farbraum + Gamma auf BT.709/SDR mit einem
    # Hable-Tonemap (billiger als reinhard, robuster als linear-clamp). zscale
    # existiert in Debian-ffmpeg (libzimg).
    if is_hdr:
        color_ops = (
            ",zscale=t=linear:npl=100,format=gbrpf32le,"
            "zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
            "zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
        )
    else:
        color_ops = ",format=yuv420p"
    fps_op = f",fps={cap_fps}" if cap_fps else ""
    scale = scale + fps_op + color_ops

    # Web-optimiertes Encoder-Preset: konstante-Qualität CRF + Bitrate-Deckel.
    # 1080p Zielbitrate ≤ 6 Mbps, 720p ≤ 3.5 Mbps — reicht für Handy-Aufnahmen im
    # Web, spart Bandbreite auf schlechten Verbindungen. profile:v high + level 4.1
    # sind die kompatibelsten Werte für iOS/Safari HW-Decoder.
    _target_bitrate = {2160: "12M", 1440: "8M", 1080: "6M", 720: "3500k", 480: "1500k"}.get(resolution, "6M")
    _bufsize = {"12M": "24M", "8M": "16M", "6M": "12M", "3500k": "7M", "1500k": "3M"}.get(_target_bitrate, "12M")
    _sw_quality_args = [
        "-preset", "veryfast",
        "-profile:v", "high", "-level", "4.1",
        "-crf", "23",
        "-maxrate", _target_bitrate, "-bufsize", _bufsize,
        "-g", "60", "-keyint_min", "60",   # 2s GOP bei 30fps → Seek-freundlich
    ]

    # HDR-Guard: QSV's vpp_qsv-Filter kann kein HLG→BT.709-Tonemapping. Ohne die
    # zscale-Kette bleibt die 10-bit-HDR-Quelle → 10-bit-Output → Safari/iOS-HW-
    # Decoder aus → Ruckeln → requeue_hdr_transcodes markiert dieselben Files
    # ERNEUT als HDR → Endlos-Loop. Für HDR-Inputs die HW-Profile-Referenz auf
    # software zwingen — dann fällt der ganze Pfad unten auf libx264 mit der
    # vollen zscale/tonemap-Filterkette.
    if is_hdr and hw.name in ("qsv", "cuda", "vaapi"):
        # Nicht-mutierender Fallback: lokale Kopie mit software-Codec.
        hw = HWProfile(name="software", hwaccel=None,
                       encode_h264_codec="libx264", available=True,
                       info="hdr fallback to software")

    # QSV: software-decode → scale → upload to QSV surfaces → h264_qsv encode.
    # This is the validated, codec-agnostic path (no HW-decode init that breaks on
    # odd input codecs); the expensive encode runs on the Intel GPU. Falls back to
    # software in transcode_video_task if it ever errors.
    if codec == "h264" and hw.name == "qsv":
        # Full QSV: HARDWARE decode + scale + encode — ~6× faster than software
        # decoding on 4K (which was the real bottleneck). vpp_qsv needs EXPLICIT
        # pixel dims (it rejects ffmpeg's min()/force_original_aspect_ratio
        # expressions), so probe the source and pre-compute the no-upscale target.
        # Display rotation is preserved in the output metadata (players orient
        # correctly). If probing fails OR the input isn't QSV-decodable, the cmd
        # errors and transcode_video_task's libx264 fallback takes over.
        dims = _probe_dims(input_path)
        if dims:
            tw, th = _scale_target(dims[0], dims[1], _long)
            return [
                _FFMPEG, "-nostdin", "-y",
                "-hwaccel", "qsv", "-hwaccel_output_format", "qsv",
                "-i", input_path,
                "-vf", f"vpp_qsv=w={tw}:h={th}",
                "-c:v", "h264_qsv", *hw.encode_extra,
                "-map", "0:v:0?", "-map", "0:a:0?", "-dn", "-sn",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", output_path,
            ]
        # Probe failed → robust software-decode → QSV-encode path.
        return [
            _FFMPEG, "-nostdin", "-y",
            "-init_hw_device", "qsv=hw", "-filter_hw_device", "hw",
            "-i", input_path,
            "-vf", f"{scale},format=nv12,hwupload=extra_hw_frames=64",
            "-c:v", "h264_qsv", *hw.encode_extra,
            "-map", "0:v:0?", "-map", "0:a:0?", "-dn", "-sn",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", output_path,
        ]

    cmd = [_FFMPEG, "-y"]

    if hw.decode_args:
        cmd += hw.decode_args

    cmd += ["-i", input_path]

    if codec == "h264":
        vcodec = hw.encode_h264_codec
        cmd += ["-c:v", vcodec]
        _extra = list(hw.encode_extra or [])
        _is_hw_bitrate_path = ("nvenc" in vcodec or "vaapi" in vcodec or "videotoolbox" in vcodec)
        if _is_hw_bitrate_path:
            # Widersprüchliche Rate-Control-Modi vermeiden: encode_extra enthält für
            # VideoToolbox `-q:v 65` / für NVENC `-cq` / für VAAPI `-qp`, das mit
            # den gleich folgenden `-b:v/-maxrate` kollidiert. Bitrate-Cap gewinnt
            # (unser Zielfall), also die Qualitäts-Only-Args entfernen.
            def _drop_pair(lst, key):
                out = []
                i = 0
                while i < len(lst):
                    if lst[i] == key and i + 1 < len(lst):
                        i += 2; continue
                    out.append(lst[i]); i += 1
                return out
            for _k in ("-q:v", "-qp", "-cq", "-global_quality", "-b:v"):
                _extra = _drop_pair(_extra, _k)
        cmd += _extra
        if _is_hw_bitrate_path:
            # HW-Encoder-Pfad: nutzt CPU-Filter-Kette (mit yuv420p/tonemap) auf CPU,
            # gibt an HW-Encoder weiter. Deutlich robuster als HW-Scaler + HW-Encoder
            # gemischt (die kollidieren bei HDR).
            cmd += ["-vf", scale]
            # HW-Encoder wollen kein CRF; steuern über Bitrate.
            cmd += [
                "-b:v", _target_bitrate, "-maxrate", _target_bitrate, "-bufsize", _bufsize,
                "-profile:v", "high", "-level", "4.1", "-g", "60",
            ]
        else:
            # libx264 → nutze die kompletten Qualitäts-Args (CRF + bitrate cap + GOP).
            cmd += ["-vf", scale]
            cmd += _sw_quality_args
        cmd += ["-threads", _FF_THREADS,
                "-map", "0:v:0?", "-map", "0:a:0?", "-dn", "-sn",
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", output_path]

    else:  # vp9 / webm
        vcodec = hw.encode_video_codec if "vp9" in hw.encode_video_codec or hw.name == "software" else "libvpx-vp9"
        cmd += [
            "-c:v", vcodec,
            "-vf", scale,
            "-crf", "33", "-b:v", "0",
            "-threads", _FF_THREADS,
            "-c:a", "libopus", "-b:a", "128k",
            output_path,
        ]

    return cmd
