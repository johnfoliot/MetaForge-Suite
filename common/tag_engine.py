# --- START OF FILE tag_engine.py ---
# ======================================================================
# MetaForge Shared Primitive: Tag Engine (Forensic ID3v2.3)
# Physical Location: \common\tag_engine.py
# Build 1.0.3: Binary APIC Support & UTF-16 BOM Compliance.
# ======================================================================
import sys
from pathlib import Path
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TYER, TORY, TRCK, TCON, TXXX, TBPM, TKEY, UFID, APIC, ID3NoHeaderError

# --- [ PATH BOOTSTRAP ] ---
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def update_tags(file_path, metadata):
    """
    CONSTRUCTIVE: Updates or adds specific tags to an MP3 file.
    Build 1.0.3: Enforces Encoding 1 (UTF-16 BOM) per Section V.3.
    """
    try:
        path = Path(file_path)
        if not path.exists(): return False, "File not found"

        try:
            # translate=False: default load auto-upgrades v2.3-only frames
            # (TYER, TORY) to their v2.4 equivalents (TDRC, TDOR) in memory.
            # Adding a fresh TYER/TORY afterward doesn't overwrite that
            # translated frame -- different HashKey -- so both get written,
            # producing a duplicate "Original Date" entry. Same root-cause
            # class as the earlier TYER/TDRC and TMOO frame-compatibility
            # bugs; loading untranslated keeps on-disk v2.3 frames as
            # themselves so a same-named .add() correctly overwrites them.
            tags = ID3(str(path), translate=False)
        except ID3NoHeaderError:
            tags = ID3()

        # Mapping internal MetaForge keys to ID3v2.3 Frames
        mapping = {
            'title': (TIT2, 'TIT2'),
            'artist': (TPE1, 'TPE1'),
            'album': (TALB, 'TALB'),
            'year': (TYER, 'TYER'),
            'original_year': (TORY, 'TORY'),
            'genre': (TCON, 'TCON'),
            'track': (TRCK, 'TRCK'),
            'bpm': (TBPM, 'TBPM'),
            'key': (TKEY, 'TKEY'),
        }

        # Non-standard fields with no dedicated ID3v2.3 frame -- same TXXX
        # desc names commit_engine.py's canonical writer uses (_write_
        # physical_tags), so a track edited here and a track written by the
        # normal Intelli-Tagger pipeline end up with identical tag shape.
        TXXX_MAPPING = {
            'sub_genre': 'Sub-Genre',
            'mood': 'Mood',
            'sonic_texture': 'Sonic Texture',
            'emotional_flavor': 'Emotional Flavor',
            'intensity': 'Intensity',
            'mb_artist_id': 'MusicBrainz Artist Id',
            'mb_track_id': 'MusicBrainz Release Track Id',
            'acoustid': 'Acoustid Id',
        }

        for key, value in metadata.items():
            if key in mapping:
                frame_class, _ = mapping[key]
                # Enforcing encoding=1 (UTF-16 BOM) per requirements
                tags.add(frame_class(encoding=1, text=[str(value)]))

            elif key in TXXX_MAPPING:
                desc = TXXX_MAPPING[key]
                tags.delall(f"TXXX:{desc}")
                tags.add(TXXX(encoding=1, desc=desc, text=[str(value)]))

            # Recording ID uses UFID (Picard convention), not TXXX -- same
            # as commit_engine.py/musicbrainz_id.py's writers, the true
            # cross-release identity anchor.
            elif key == 'mb_recording_id':
                tags.delall("UFID:http://musicbrainz.org")
                tags.add(UFID(owner="http://musicbrainz.org", data=str(value).encode("utf-8")))

            # Handle custom MetaForge Forensic IDs (TXXX)
            elif key.startswith('mf_'):
                tags.add(TXXX(encoding=1, desc=key.upper(), text=[str(value)]))

        # Defense-in-depth alongside translate=False above: collapses any
        # genuinely v2.4-native frame already on disk (e.g. from a
        # different tool) down to its v2.3 equivalent before saving --
        # same established pattern as commit_engine.py's physical writer.
        tags.update_to_v23()
        tags.save(str(path), v2_version=3)
        return True, "Update successful"

    except Exception as e:
        return False, str(e)

def embed_artwork(file_path, image_path):
    """
    Surgically injects an image into the ID3v2.3 APIC frame.
    Protocol: APIC Type 3 (Front Cover), MIME: image/jpeg.
    """
    try:
        path = Path(file_path)
        img_path = Path(image_path)
        if not path.exists() or not img_path.exists():
            return False, "Audio or Image file missing."

        try:
            tags = ID3(str(path))
        except ID3NoHeaderError:
            tags = ID3()

        with open(img_path, 'rb') as img:
            tags.add(APIC(
                encoding=0, # Latin-1 for MIME string
                mime='image/jpeg',
                type=3,     # Front Cover
                desc='Cover',
                data=img.read()
            ))
        
        tags.save(str(path), v2_version=3)
        return True, "Artwork embedded successfully"
    except Exception as e:
        return False, str(e)

def sanitize_file(file_path, preserve_list):
    """
    DESTRUCTIVE: Removes all ID3 tags except those provided in preserve_list.
    """
    try:
        path = Path(file_path)
        if not path.exists(): return False, "File not found"

        tags = ID3(str(path))
        existing_keys = list(tags.keys())

        for key in existing_keys:
            should_preserve = any(key.startswith(p) for p in preserve_list)
            if not should_preserve:
                tags.delall(key)

        tags.save(str(path), v2_version=3)
        return True, "Sanitization complete"
    except Exception as e:
        return False, str(e)

# --- [ DIAGNOSTIC SUITE ] ---

def run_diagnostics():
    print("\n--- MetaForge Primitive Diagnostic: Tag Engine (Build 1.0.3) ---")
    
    test_file = PROJECT_ROOT / "temp_diag_test.mp3"
    test_file.write_bytes(b'\x00' * 1024) 
    
    # Test 1: Constructive Update (UTF-16 Check)
    print("[1/3] Testing Constructive Update (UTF-16)...", end=" ")
    success, _ = update_tags(test_file, {'title': 'Diagnostic', 'mf_id': 'MF-123'})
    
    tags = ID3(str(test_file))
    if success and tags['TIT2'].encoding == 1 and 'TXXX:MF_ID' in tags:
        print("PASS")
    else:
        print("FAIL")

    # Test 2: Artwork Embedding
    print("[2/3] Testing APIC Embedding...", end=" ")
    temp_img = PROJECT_ROOT / "temp_art.jpg"
    temp_img.write_bytes(b'\xFF\xD8\xFF' + b'\x00' * 10) # Mock JPEG header
    
    art_success = embed_artwork(test_file, temp_img)
    tags = ID3(str(test_file))
    if art_success and 'APIC:Cover' in tags:
        print("PASS")
    else:
        print("FAIL")

    # Test 3: Destructive Sanitization
    print("[3/3] Testing Dynamic Sanitization...", end=" ")
    my_whitelist = ['TIT2', 'TXXX', 'APIC']
    sanitize_file(test_file, my_whitelist)
    
    tags = ID3(str(test_file))
    # Confirming TIT2, TXXX, and APIC remain while others are gone
    if 'TIT2' in tags and 'TXXX:MF_ID' in tags and 'APIC:Cover' in tags:
        print("PASS")
    else:
        print("FAIL")

    if test_file.exists(): test_file.unlink()
    if temp_img.exists(): temp_img.unlink()
    print("--- Diagnostic Complete ---\n")

if __name__ == "__main__":
    run_diagnostics()

# --- END OF FILE tag_engine.py ---