"""Detect available hardware video acceleration and build optimised ffmpeg args."""
import subprocess
import shutil
import os
import json
from dataclasses import dataclass, field
from typing import List, Optional
from functools import lru_cache

_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


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
        encode_extra=["-global_quality", "28"],
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
    resolution: int = 720,
    codec: str = "h264",   # "h264" | "vp9"
    hw: Optional[HWProfile] = None,
) -> List[str]:
    """Build an ffmpeg command for web-optimised transcoding."""
    if hw is None:
        hw = detect_hw()

    scale = f"scale=-2:{resolution}"

    # QSV: software-decode → scale → upload to QSV surfaces → h264_qsv encode.
    # This is the validated, codec-agnostic path (no HW-decode init that breaks on
    # odd input codecs); the expensive encode runs on the Intel GPU. Falls back to
    # software in transcode_video_task if it ever errors.
    if codec == "h264" and hw.name == "qsv":
        return [
            _FFMPEG, "-y",
            "-init_hw_device", "qsv=hw", "-filter_hw_device", "hw",
            "-i", input_path,
            "-vf", f"{scale},format=nv12,hwupload=extra_hw_frames=64",
            "-c:v", "h264_qsv", *hw.encode_extra,
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", output_path,
        ]

    cmd = [_FFMPEG, "-y"]

    if hw.decode_args:
        cmd += hw.decode_args

    cmd += ["-i", input_path]

    if codec == "h264":
        vcodec = hw.encode_h264_codec
        cmd += ["-c:v", vcodec]
        if hw.encode_extra:
            cmd += hw.encode_extra
        if "nvenc" in vcodec or "vaapi" in vcodec or "videotoolbox" in vcodec:
            cmd += ["-vf", f"scale_{'npp' if 'nvenc' in vcodec else vcodec.split('_')[1]}={'-2'}:{resolution}"]
        else:
            cmd += ["-vf", scale]
        cmd += ["-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", output_path]

    else:  # vp9 / webm
        vcodec = hw.encode_video_codec if "vp9" in hw.encode_video_codec or hw.name == "software" else "libvpx-vp9"
        cmd += [
            "-c:v", vcodec,
            "-vf", scale,
            "-crf", "33", "-b:v", "0",
            "-c:a", "libopus", "-b:a", "128k",
            output_path,
        ]

    return cmd
