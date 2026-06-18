"""
OCR Service — Extract text dari foto struk
Mendukung 2 backend:
  1. Google Cloud Vision API (butuh credentials, lebih akurat)
  2. Tesseract OCR (lokal, gratis, cukup akurat untuk struk)
"""
import logging
import httpx
import base64
from pathlib import Path

logger = logging.getLogger(__name__)

# Try Google Vision first, fallback to Tesseract
USE_GOOGLE_VISION = False
try:
    from google.cloud import vision
    USE_GOOGLE_VISION = True
    logger.info("Using Google Cloud Vision for OCR")
except Exception:
    logger.info("Google Vision not available, using Tesseract")


async def download_image(url: str, save_path: str = "/tmp/waha_media") -> str | None:
    """Download image dari WAHA media URL dan simpan lokal."""
    Path(save_path).mkdir(parents=True, exist_ok=True)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                # Determine extension from content-type
                ct = resp.headers.get("content-type", "image/jpeg")
                ext = ".jpg"
                if "png" in ct:
                    ext = ".png"
                elif "webp" in ct:
                    ext = ".webp"

                filepath = f"{save_path}/receipt_{hash(url)}{ext}"
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                logger.info(f"Image saved to {filepath}")
                return filepath
    except Exception as e:
        logger.error(f"Error downloading image: {e}")
    return None


def ocr_google_vision(image_path: str) -> str:
    """OCR pakai Google Cloud Vision API."""
    client = vision.ImageAnnotatorClient()

    with open(image_path, "rb") as f:
        content = f.read()

    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    texts = response.text_annotations

    if texts:
        return texts[0].description
    return ""


def ocr_tesseract(image_path: str) -> str:
    """OCR pakai Tesseract (lokal)."""
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(image_path)
        # Convert to grayscale for better OCR
        img = img.convert("L")

        text = pytesseract.image_to_string(img, lang="ind+eng")
        return text
    except Exception as e:
        logger.error(f"Tesseract OCR error: {e}")
        return ""


async def extract_text_from_image(image_url: str) -> str:
    """Extract text dari URL gambar. Auto-detect backend."""
    # Download image first
    local_path = await download_image(image_url)
    if not local_path:
        return ""

    # Try Google Vision first
    if USE_GOOGLE_VISION:
        try:
            text = ocr_google_vision(local_path)
            if text.strip():
                return text
        except Exception as e:
            logger.warning(f"Google Vision failed, falling back to Tesseract: {e}")

    # Fallback to Tesseract
    return ocr_tesseract(local_path)
