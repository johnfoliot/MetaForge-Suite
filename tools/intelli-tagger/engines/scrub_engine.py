# --- START OF FILE scrub_engine.py ---
# ======================================================================
# MetaForge Engine: Whitelist Scrub (Phase 3)
# Role: Destructive removal of non-whitelisted ID3 legacy metadata.
# Build 1.0.4: Syntax Error Resolution (Comma Fix) | Forensic Sync.
# Physical Location: \tools\intelli-tagger\engines\scrub_engine.py
# ======================================================================
from pathlib import Path
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

    yield '<div class="it-log-entry it-val-gold" style="margin-top:25px;">🧼 Cleaning metadata...</div>'

    scrub_count = 0
    vanished_count = 0
    for f in files:
        # Same existence guard as health_engine.py's pass just before this
        # one (John's Matt Bianco box set report, 2026-07-21) -- a file
        # that disappeared between the initial glob and reaching it here
        # needs to be surfaced immediately, not silently skipped by
        # tag_engine.sanitize_file's own "File not found" return.
        if not f.exists():
            vanished_count += 1
            yield f'<div class="it-log-entry it-val-red" style="margin-left:15px;">🔥 MISSING BEFORE SCRUB: {f.name} was found by the initial scan but is gone from disk.</div>'
            continue

        # tag_engine.sanitize_file logic protects frames starting with whitelist entries.
        success, message = tag_engine.sanitize_file(f, WHITELIST)

        if success:
            scrub_count += 1
            if scrub_count % 5 == 0 or scrub_count == len(files):
                yield f'<div class="it-log-entry" style="margin-left:15px;">✅ Cleaned {scrub_count}/{len(files)} files.</div>'
        else:
            yield f'<div class="it-log-entry it-val-red" style="margin-left:15px;">🔥 Scrub failed on {f.name}: {message}</div>'

    if vanished_count > 0:
        yield f'<div class="it-log-entry it-val-red" style="margin-top:5px; margin-left:15px;">⚠️ SAFETY ALERT: {vanished_count} file(s) went missing during the scrub pass.</div>'
# --- END OF FILE scrub_engine.py ---