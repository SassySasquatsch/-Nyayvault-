"""
Best-effort metadata extraction for uploaded evidence.

* Images  -> real EXIF via Pillow (camera model, GPS, capture time).
* PDFs    -> real document info dictionary via pypdf, when available.
* Video/Audio/other -> filesystem timestamps only; real device/GPS/IMEI
  extraction for those formats needs a media-probing library (e.g. ffprobe)
  which isn't bundled here. We say so explicitly rather than inventing data.

Every code path is wrapped so a corrupt or unusual file never breaks the
upload -- we degrade to the "—" placeholders the frontend already expects.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

PLACEHOLDER = "—"


def _fmt(dt: Optional[datetime]) -> str:
    if not dt:
        return PLACEHOLDER
    return dt.strftime("%d %b %Y, %H:%M:%S")


def _from_filesystem(path: Path) -> dict:
    stat = path.stat()
    return {
        "device": PLACEHOLDER,
        "gps": PLACEHOLDER,
        "imei": PLACEHOLDER,
        "created": _fmt(datetime.fromtimestamp(stat.st_mtime)),
    }


def _extract_image_exif(path: Path) -> dict:
    try:
        from PIL import Image
        from PIL.ExifTags import GPSTAGS, TAGS
    except ImportError:
        return _from_filesystem(path)

    result = _from_filesystem(path)
    try:
        img = Image.open(path)
        raw = img.getexif()
        if not raw:
            return result

        tags = {TAGS.get(k, k): v for k, v in raw.items()}

        make = tags.get("Make", "")
        model = tags.get("Model", "")
        device = f"{make} {model}".strip()
        if device:
            result["device"] = device

        dt_original = tags.get("DateTimeOriginal") or tags.get("DateTime")
        if dt_original:
            try:
                parsed = datetime.strptime(str(dt_original), "%Y:%m:%d %H:%M:%S")
                result["created"] = _fmt(parsed)
            except ValueError:
                pass

        gps_ifd = raw.get_ifd(0x8825) if hasattr(raw, "get_ifd") else None
        if gps_ifd:
            gps_tags = {GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
            lat = gps_tags.get("GPSLatitude")
            lat_ref = gps_tags.get("GPSLatitudeRef")
            lon = gps_tags.get("GPSLongitude")
            lon_ref = gps_tags.get("GPSLongitudeRef")
            if lat and lon:
                lat_dd = _dms_to_dd(lat, lat_ref)
                lon_dd = _dms_to_dd(lon, lon_ref)
                result["gps"] = f"{lat_dd:.4f}° {lat_ref}, {lon_dd:.4f}° {lon_ref}"
    except Exception:
        # Any parsing hiccup -> fall back to filesystem-only metadata.
        return _from_filesystem(path)

    return result


def _dms_to_dd(dms, ref) -> float:
    degrees, minutes, seconds = [float(v) for v in dms]
    dd = degrees + minutes / 60 + seconds / 3600
    return dd


def _extract_pdf_info(path: Path) -> dict:
    result = _from_filesystem(path)
    try:
        from pypdf import PdfReader
    except ImportError:
        return result

    try:
        reader = PdfReader(str(path))
        info = reader.metadata or {}
        producer = info.get("/Producer") or info.get("/Creator")
        if producer:
            result["device"] = str(producer)
        created = info.get("/CreationDate")
        if created:
            # PDF dates look like D:20260910093022+05'30'
            raw = str(created).lstrip("D:")[:14]
            try:
                parsed = datetime.strptime(raw, "%Y%m%d%H%M%S")
                result["created"] = _fmt(parsed)
            except ValueError:
                pass
    except Exception:
        return _from_filesystem(path)

    return result


def extract_metadata(path: Path, doc_type: str) -> dict:
    if doc_type == "IMAGE":
        return _extract_image_exif(path)
    if doc_type == "PDF":
        return _extract_pdf_info(path)
    # VIDEO / AUDIO / OTHER: no bundled media-probing library, be honest
    # about it instead of fabricating a device/GPS value.
    return _from_filesystem(path)


def classify_doc_type(filename: str, content_type: Optional[str]) -> str:
    ext = Path(filename).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".webp"}:
        return "IMAGE"
    if ext == ".pdf":
        return "PDF"
    if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        return "VIDEO"
    if ext in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}:
        return "AUDIO"
    if content_type:
        if content_type.startswith("image/"):
            return "IMAGE"
        if content_type == "application/pdf":
            return "PDF"
        if content_type.startswith("video/"):
            return "VIDEO"
        if content_type.startswith("audio/"):
            return "AUDIO"
    return "OTHER"
