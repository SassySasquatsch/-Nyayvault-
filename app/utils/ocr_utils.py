"""
OCR utility service.

FIRs and case diaries frequently arrive as scanned PDFs or photographed /
handwritten image files with no real text layer, so `/api/search` has
nothing to match against them. This module makes a best-effort attempt to
turn that into real, searchable text using Tesseract (via `pytesseract`),
following exactly the same "never break the caller" style as
`app/utils/exif_utils.py`:

* Missing `pytesseract` / `Pillow` / `pdf2image`, or the underlying
  `tesseract` / `poppler` binaries not being installed on the host -> we say
  so (by returning `(None, None)`) instead of raising or inventing text.
* A PDF that already has a real, embedded text layer is returned as-is --
  we don't rasterise and OCR pages that are already digital text, which
  would be slower and lossier than just reading it.
* A PDF with no usable text layer (i.e. a scanned/photographed document) is
  rasterised page-by-page with `pdf2image` (needs the `poppler` system
  package: `pdftoppm`/`pdfinfo`) and OCR'd. If `poppler` isn't available, we
  fall back to pulling whatever raster images `pypdf` finds embedded
  directly in each page -- this is how most scanners actually produce a
  "scanned PDF" (one full-page image per page), so it works without poppler
  at all in the common case.
* A plain image upload (.png/.jpg/...) is OCR'd directly.

Read-only, always: this module never writes to, or otherwise modifies, the
evidence file on disk. It only opens it for reading, so it can never affect
the SHA-256 hash already captured at upload time (`app/utils/hashing.py`)
or cause a later `POST /{document_id}/verify` to report tampering.
"""
from pathlib import Path
from typing import Optional

# Below this many characters, don't trust a PDF's "text layer" -- a handful
# of stray characters from a scan artifact or a form's static labels isn't
# a real digital document, and OCR will do far better on the actual content.
MIN_TEXT_LAYER_CHARS = 20

# Cap so one huge scanned filing (hundreds of pages) can't hang the OCR
# background task or the box it's running on.
MAX_OCR_PAGES = 30

# Cap so a single document's extracted text can't blow up the DB row.
MAX_STORED_CHARS = 200_000

# Values returned in the `method` half of extract_searchable_text()'s result.
METHOD_TEXT_LAYER = "text_layer"
METHOD_OCR = "ocr"


def _clip(text: str) -> str:
    text = text.strip()
    if len(text) > MAX_STORED_CHARS:
        text = text[:MAX_STORED_CHARS] + "\n\n[... truncated: OCR text exceeded the storage limit ...]"
    return text


def pdf_has_text_layer(path: Path) -> bool:
    """True if pypdf can pull a real amount of text straight out of the PDF
    (i.e. it's born-digital, not a scan) -- used by callers that just want
    a quick yes/no without keeping the extracted text around."""
    return _extract_pdf_text_layer(path) is not None


def _extract_pdf_text_layer(path: Path) -> Optional[str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(str(path))
        chunks = [page.extract_text() or "" for page in reader.pages[:MAX_OCR_PAGES]]
        text = "\n".join(chunks).strip()
        return text if len(text) >= MIN_TEXT_LAYER_CHARS else None
    except Exception:
        # Encrypted, corrupt, or otherwise unparseable -- treat as "no text
        # layer" so the caller falls through to OCR instead of failing.
        return None


def _ocr_image_file(path: Path) -> Optional[str]:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            text = pytesseract.image_to_string(img) or ""
        return _clip(text) if text.strip() else None
    except Exception:
        # Covers pytesseract.TesseractNotFoundError (binary not installed),
        # an unreadable/corrupt image, an unsupported format, etc.
        return None


def _ocr_pdf_via_pdf2image(path: Path) -> Optional[str]:
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        return None
    try:
        pages = convert_from_path(str(path), first_page=1, last_page=MAX_OCR_PAGES)
    except Exception:
        # Most commonly: poppler (pdftoppm/pdfinfo) isn't installed on this
        # host. Let the caller try the pypdf-embedded-image fallback instead.
        return None
    texts = []
    for page_image in pages:
        try:
            texts.append(pytesseract.image_to_string(page_image) or "")
        except Exception:
            # Tesseract binary missing/broken -- bail on the whole document
            # rather than return text for some pages and silently drop others.
            return None
    text = "\n\n".join(t for t in texts if t)
    return _clip(text) if text.strip() else None


def _ocr_pdf_via_embedded_images(path: Path) -> Optional[str]:
    """Fallback when pdf2image/poppler aren't available. Most scanners save
    each scanned page as a single full-page raster image embedded in the
    PDF, so pypdf can pull those out directly and we OCR them -- no poppler
    needed for the common case."""
    try:
        import pytesseract
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(str(path))
    except Exception:
        return None

    texts = []
    for page in reader.pages[:MAX_OCR_PAGES]:
        try:
            images = list(page.images)
        except Exception:
            images = []
        for img_file in images:
            try:
                pil_image = img_file.image  # pypdf's ImageFile -> PIL.Image
                if pil_image is not None:
                    texts.append(pytesseract.image_to_string(pil_image) or "")
            except Exception:
                continue
    text = "\n\n".join(t for t in texts if t)
    return _clip(text) if text.strip() else None


def needs_ocr(doc_type: str) -> bool:
    """Quick check the upload router uses to decide whether it's worth
    scheduling the background extraction task at all."""
    return doc_type in ("IMAGE", "PDF")


def extract_searchable_text(path: Path, doc_type: str) -> tuple[Optional[str], Optional[str]]:
    """
    Best-effort text extraction so a document becomes searchable via
    `/api/search`. Wrapped so this can never raise or fail an upload.

    Returns (text, method):
      text   -- extracted text, or None if nothing could be extracted
      method -- METHOD_TEXT_LAYER, METHOD_OCR, or None
    """
    try:
        if doc_type == "IMAGE":
            text = _ocr_image_file(path)
            return (text, METHOD_OCR) if text else (None, None)

        if doc_type == "PDF":
            text = _extract_pdf_text_layer(path)
            if text:
                return text, METHOD_TEXT_LAYER

            # No usable text layer -- this is a scanned/photographed filing.
            text = _ocr_pdf_via_pdf2image(path)
            if text:
                return text, METHOD_OCR

            text = _ocr_pdf_via_embedded_images(path)
            if text:
                return text, METHOD_OCR

            return None, None

        return None, None
    except Exception:
        # Absolute last resort -- OCR is a best-effort enhancement and must
        # never be the reason an upload or a background task fails.
        return None, None
