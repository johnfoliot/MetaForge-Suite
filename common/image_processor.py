# --- START OF FILE image_processor.py ---
# ======================================================================
# MetaForge Shared Primitive: Image Processor
# Role: Enforces Archival Fit (500x500) and JPEG standardization.
# Physical Location: \common\image_processor.py
# Build 1.0.1: Standardized Letterboxing Protocol (replaces Crop-Fit).
# Dependency: Pillow (PIL)
# ======================================================================
import io
from pathlib import Path
from PIL import Image, ImageOps

# Near-square rule (John, 2026-11-13). A source whose width and height differ
# by no more than this fraction of its longer side is stretched to an exact
# square instead of letterboxed. Letterboxing a near-square image (e.g.
# 1405x1400) left 1px black lines along two edges of folder.jpg; a 2% stretch
# is invisible. Clearly non-square art is still letterboxed, never distorted.
NEAR_SQUARE_TOLERANCE = 0.02

def apply_archival_fit(image_source, destination_path, size=(500, 500)):
    """
    Standardizes an image to the MetaForge Archival Standard.
    - image_source: Can be a file Path, or a bytes object (from API).
    - destination_path: Where to save the final folder.jpg.
    - Protocol: Strict 500x500 Square, RGB JPEG. Near-square sources
      (within NEAR_SQUARE_TOLERANCE) are stretched to fill the square;
      everything else is letterboxed.
    """
    try:
        # 1. Load the image from file path or byte-stream
        if isinstance(image_source, (str, Path)):
            img = Image.open(str(image_source))
        else:
            img = Image.open(io.BytesIO(image_source))

        # 2. Format Compliance: Force RGB for standard JPEG bitstream
        if img.mode != "RGB":
            img = img.convert("RGB")

        # 3. Archival Fit
        width, height = img.size
        near_square = abs(width - height) <= NEAR_SQUARE_TOLERANCE * max(width, height)

        if near_square:
            # Stretch straight to the target square: no letterbox bars.
            img = img.resize(size, Image.Resampling.LANCZOS)
            fit = "stretched"
        else:
            # Letterbox (never crop) clearly non-square art.
            img = ImageOps.pad(
                img,
                size,
                method=Image.Resampling.LANCZOS,
                color=(0, 0, 0),  # Black background letterbox; change to (255, 255, 255) for white
                centering=(0.5, 0.5)
            )
            fit = "letterboxed"

        # 4. Atomic Save
        img.save(destination_path, "JPEG", quality=90, optimize=True)
        
        return {
            "status": "success",
            "dims": f"{size[0]}x{size[1]}",
            "format": "JPEG",
            "fit": fit,
            "source_dims": f"{width}x{height}"
        }

    except Exception as e:
        return {"status": "error", "message": f"Image processing failed: {str(e)}"}

# --- END OF FILE image_processor.py ---