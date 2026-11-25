# --- START OF FILE scrub_engine.py ---
# ======================================================================
# MetaForge Engine: Whitelist Scrub (Phase 3)
# Role: Destructive removal of non-whitelisted ID3 legacy metadata.
# Build 1.0.4: Syntax Error Resolution (Comma Fix) | Forensic Sync.
# Physical Location: \tools\intelli-tagger\engines\scrub_engine.py
# ======================================================================
from pathlib import Path
from common.mf_events import event, signal   # v2: events, not HTML (see common/mf_events.py)
from common import tag_engine

# --- [ THE AUTHORITATIVE WHITELIST ] ---
# Build 1.0.4: Synchronized with Commit Engine Build 1.6.0.
# Frames not starting with these strings are purged to maintain a Clean Room.
WHITELIST = [
    'TIT2',   # Track Title
    'TPE1',   # Filing Artist
    'TALB',   # Album Title
    'TRCK',   # Track Number
    'TCON',   # Genre
    'TMOO',   # Mood
    'TBPM',   # BPM
    'TKEY',   # Key
    'APIC',   # Embedded Album cover
    'UFID',   # MusicBrainz Recording ID (Track ID)
    'COMM',   # MetaForge Forensic Signature
    'TYER',   # Release Year
    'TORY',   # Original Year
    'TPUB',   # Historical Label
    
    # --- SURGICAL TXXX WHITELIST ---
    'TXXX:MusicBrainz Artist Id',
    'TXXX:MusicBrainz Album Id',
    'TXXX:MusicBrainz Release Group Id',
    'TXXX:MusicBrainz Release Country',
    'TXXX:Acoustid Id',
    'TXXX:Sub-Genre',
    'TXXX:Intensity',
    'TXXX:Country',
    'TXXX:Mood_Modifiers'
]

def scrub_tags(root_path):
    """
    Executes surgical sanitation on all .mp3 files.
    Purges legacy data while protecting the MetaForge forensic whitelist.
    """
    files = list(root_path.glob("**/*.mp3"))
    if not files:
        return

    yield event("step", "Step 2: Reviewing and remediating existing metadata")

    scrub_count = 0
    vanished_count = 0
    for f in files:
        if not f.exists():
            vanished_count += 1
            yield event("error", "File went missing before its old metadata could be checked", file=f.name)
            continue

        # tag_engine.sanitize_file logic protects frames starting with whitelist entries.
        success, message = tag_engine.sanitize_file(f, WHITELIST)

        if success:
            scrub_count += 1
            if scrub_count % 5 == 0 or scrub_count == len(files):
                yield event("detail", f"Reviewed {scrub_count} of {len(files)} files",
            ok=(scrub_count == len(files)))   # ✓ on the final line (John, 2026-11-15)
        else:
            yield event("error", f"Review failed: {message}", file=f.name)

    if vanished_count > 0:
        yield event("warning", f"{vanished_count} file{'s' if vanished_count != 1 else ''} went missing during the review")
# --- END OF FILE scrub_engine.py ---