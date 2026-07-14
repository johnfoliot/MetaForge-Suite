# --- START OF FILE edge_constants.py ---
from enum import Enum

class RelationType(Enum):
    PERFORMED_ON = "PERFORMED_ON"
    COMPOSED = "COMPOSED"
    PRODUCED = "PRODUCED"
    ENGINEERED_BY = "ENGINEERED_BY"
    ARRANGED_BY = "ARRANGED_BY"
    WRITTEN_BY = "WRITTEN_BY"
    # Split out from WRITTEN_BY 2026-07-14, confirmed against MusicBrainz's
    # own style guide: "Writer" is deliberately the GENERIC fallback for an
    # unsplit music+lyrics credit ("...when no more specific information is
    # available. If possible, the more specific composer, lyricist and/or
    # librettist types should be used..."). LYRICIST is that more specific
    # type for the words-only side, mirroring COMPOSED on the music-only
    # side (Discogs "Music By"/"Lyrics By" pairing -- see performance.json).
    LYRICIST = "LYRICIST"
    # A&R (Artists & Repertoire) -- talent discovery/career-shaping
    # figures like Mitch Miller or John Hammond Sr. Real, distinct IPM
    # connective tissue from PRODUCED (hands-on studio involvement isn't
    # the same relationship as discovering/signing/steering an artist).
    # Added 2026-07-08 as a deliberate, explicit exception to this
    # taxonomy's normal "don't expand without a real reason" rule --
    # John's own call as chief architect, not a casual addition.
    A_AND_R = "A_AND_R"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
# --- END OF FILE edge_constants.py ---