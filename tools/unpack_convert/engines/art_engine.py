# --- START OF FILE art_engine.py ---
# ======================================================================
# MetaForge Engine: Artwork Orchestrator
# Role: Manages local art discovery and Discogs cloud recovery.
# Build 2.1.1: Forensic Loop Verification (Physical APIC Embedding).
# Physical Location: \tools\unpack_convert\engines\art_engine.py
# ======================================================================
import io
import os
import base64
from pathlib import Path
from PIL import Image
from common import io_bridge, tag_engine, discogs_engine, image_processor

# Gallery cards render in a 4-column grid (unpack_convert.mfi's
# .art-selection-grid) -- realistically never wider than ~300px even on a
# large display. 320px longest-side is generous headroom for that (incl.
# high-DPI) while keeping each preview a few tens of KB instead of the
# multi-MB original -- a box set's booklet scans especially.
GALLERY_THUMB_MAX = 320
GALLERY_THUMB_QUALITY = 78

def scan_art_folder(album_path):
    """
    Scans the directory for candidate images for the UI Gallery.
    Returns cheap preview thumbnails, not the full-size originals --
    real bug, found live 2026-07-28 (John's report): this used to
    base64-encode and ship every candidate at its FULL original size in
    one blocking request, so a box set with several multi-MB booklet
    scans meant the gallery showed nothing at all until every one of
    those had been read, encoded, and downloaded. finalize_cover() below
    still re-reads the actual selected file from disk for the real
    archival-quality resize -- this only ever affects the picker preview.
    """
    album_path = Path(album_path)
    image_extensions = {'.jpg', '.jpeg', '.png'}
    candidates = []

    # Priority 1: Check root
    for item in album_path.iterdir():
        if item.is_file() and item.suffix.lower() in image_extensions:
            candidates.append(item)

    # Priority 2: Check \art\ subfolder
    art_sub = album_path / "art"
    if art_sub.exists() and art_sub.is_dir():
        for item in art_sub.iterdir():
            if item.is_file() and item.suffix.lower() in image_extensions:
                candidates.append(item)

    gallery = []
    for img_path in candidates:
        try:
            with Image.open(img_path) as img:
                # Real (not placeholder) dimensions -- the old hardcoded
                # "500x500" label was never actually measured and was
                # simply wrong for every image that wasn't already 500x500.
                orig_width, orig_height = img.size

                if img.mode != "RGB":
                    img = img.convert("RGB")

                thumb = img.copy()
                thumb.thumbnail((GALLERY_THUMB_MAX, GALLERY_THUMB_MAX), Image.Resampling.LANCZOS)

                buf = io.BytesIO()
                thumb.save(buf, "JPEG", quality=GALLERY_THUMB_QUALITY)
                encoded_string = base64.b64encode(buf.getvalue()).decode('utf-8')

                gallery.append({
                    "filename": img_path.name,
                    "data": f"data:image/jpeg;base64,{encoded_string}",
                    "width": orig_width,
                    "height": orig_height
                })
        except Exception:
            continue

    return gallery

def finalize_cover(album_path, selected_filename):
    """
    User Path (Step 4): Promotes a specific image to folder.jpg and embeds.
    """
    album_path = Path(album_path)
    source_path = album_path / selected_filename
    
    # Fallback to \art\ if not in root
    if not source_path.exists():
        source_path = album_path / "art" / selected_filename

    if not source_path.exists():
        return {"status": "error", "message": "Source image not found on disk."}

    dest_path = album_path / "folder.jpg"
    
    try:
        # 1. Enforce Archival Fit (500x500 RGB JPEG)
        res = image_processor.apply_archival_fit(source_path, dest_path)
        if res['status'] != 'success':
            return res

        # 2. Forensic Loop: Physical bitstream embedding
        audio_files = io_bridge.get_audio_targets(album_path, recursive=True)
        embedded_count = 0
        for audio in audio_files:
            # Uses tag_engine Build 1.0.3 APIC logic
            if tag_engine.embed_artwork(audio, dest_path):
                embedded_count += 1

        return {
            "status": "success",
            "embedded_count": embedded_count,
            "dims": res['dims']
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

def trigger_discogs_fetch(album_path, artist, album_name):
    """
    Cloud Path: Downloads from Discogs and physically embeds.
    Build 2.1.1: Hardened iteration ensures every converted file is tagged.
    """
    album_path = Path(album_path)
    
    # 1. Fetch from Discogs (Handles download and Archival Fit resize)
    # Result returns status, dims, and source.
    res = discogs_engine.fetch_archival_cover(artist, album_name, album_path)
    
    if res['status'] == 'success':
        folder_jpg = album_path / "folder.jpg"
        
        # 2. Forensic Loop: Iterative Embedding (Building bitstream provenance)
        # Scan for the newly converted .mp3 files
        audio_files = io_bridge.get_audio_targets(album_path, recursive=True)
        embedded_count = 0
        
        for audio in audio_files:
            # Physically inject the binary data into ID3v2.3 APIC frame
            success, msg = tag_engine.embed_artwork(audio, folder_jpg)
            if success:
                embedded_count += 1
        
        # Enrich result for the Hub's UI stream
        res['embedded_count'] = embedded_count
        
    return res

# --- END OF FILE art_engine.py ---