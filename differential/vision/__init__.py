"""Meter-photo reading: Claude vision in live mode, a classical reader offline.

``read_meter`` returns a *proposal*: the technician confirms or corrects it before
anything is recorded (the agent enforces this).
"""

from __future__ import annotations

from typing import Any


def _media_type(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def strip_metadata(image_bytes: bytes) -> tuple[bytes, str]:
    """Re-encode a photo without metadata (EXIF, GPS, device data) before it leaves
    the machine; the pixels are kept, turned upright by the EXIF orientation first."""
    from io import BytesIO

    from PIL import Image, ImageOps

    with Image.open(BytesIO(image_bytes)) as im:
        upright = ImageOps.exif_transpose(im)
        rgb = upright.convert("RGB")
    out = BytesIO()
    rgb.save(out, format="JPEG", quality=92)  # a fresh image carries no metadata
    return out.getvalue(), "image/jpeg"


def read_meter(image_bytes: bytes, client: Any | None = None) -> dict[str, Any]:
    from differential.vision.meter_read import read_llm, read_offline

    reading = None
    source_note = ""
    if client is not None:
        try:
            clean, media_type = strip_metadata(image_bytes)
            reading = read_llm(clean, media_type, client)
        except Exception as exc:  # no key, no cache or API error: fall back to offline
            source_note = f"live reading unavailable ({type(exc).__name__}); offline reader used"
    if reading is None:
        reading = read_offline(image_bytes)
    if reading is None:
        return {"legible": False, "error": "The display could not be read. Please type the "
                                           "reading instead.", "note": source_note}
    out = reading.to_json()
    out["legible"] = reading.value is not None or reading.overload
    out["base_value"] = reading.base_value()
    if source_note:
        out["note"] = source_note
    return out


__all__ = ["read_meter", "strip_metadata"]
