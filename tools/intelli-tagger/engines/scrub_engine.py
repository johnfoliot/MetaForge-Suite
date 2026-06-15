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
# Build 1.0.4: Synchronized with Commit Engine Build 1.4.6.
# Frames not starting with these strings are purged to maintain a Clean Room.
WHITELIST = [
    'TIT2',   # Track Title
    'TPE1',   # Filing Artist
    'TALB',   # Album Title
    'TRCK',   # Track Number
    'TCON',   # Genre
    'APIC',   # Embedded Album cover
    'UFID',   # MusicBrainz Recording ID (Track ID)
    'COMM',   # MetaForge Forensic Signature
    'TYER',   # Release Year (Bimodal)
    'TORY',   # Original Year (Bimodal)
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
    'TXXX:Personnel',
    'TXXX:Release Year'
]

def scrub_tags(root_path):
    """
    Executes surgical sanitation on all .mp3 files.
    Purges legacy data while protecting the MetaForge forensic whitelist.
    """
    files = list(root_path.glob("*.mp3"))
    if not files:
        return

    yield '<div class="it-log-entry it-val-gold" style="margin-top:5px;">🧼 Cleaning metadata</div>'

    scrub_count = 0
    for f in files:
        # tag_engine.sanitize_file logic protects frames starting with whitelist entries.
        # Fixed Build 1.0.4: Corrected concatenated string error.
        success, message = tag_engine.sanitize_file(f, WHITELIST)
        
        if success:
            scrub_count += 1
            if scrub_count % 5 == 0 or scrub_count == len(files):
                yield f'<div class="it-log-entry" style="margin-left:15px;"><img src="/ui/images/cleaned.png" alt="" style="height:15px; width:auto;"> Cleaned {scrub_count}/{len(files)} files...</div>'
        else:
            yield f'<div class="it-log-entry it-val-red">⚠️ Scrub Error on {f.name}: {message}</div>'

    yield f'<div class="it-log-entry it-val-success">✅ Scrubbing Complete</div>'

# --- END OF FILE scrub_engine.py ---