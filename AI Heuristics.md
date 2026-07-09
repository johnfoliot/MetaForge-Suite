# AI Heuristics — How MetaForge Studio Determines the Data It Submits

This document explains the methodology behind edits submitted to MusicBrainz using **MetaForge Studio**, a personal music-library tagging tool. If you're a MusicBrainz editor reviewing one of these edits and want to know where the proposed data came from and how much to trust it, this is that explanation.

The short version: **nothing here submits itself.** MetaForge Studio builds evidence and pre-fills MusicBrainz's own real edit forms; a human reviews and clicks submit every single time. What follows is how that evidence gets built.

## Nothing is submitted automatically

MetaForge Studio never authenticates to MusicBrainz and never writes to it via the API. When the tool finds something worth proposing, it opens MusicBrainz's *own* edit page (the standard Release Editor or Recording relationship editor you'd use by hand), pre-filled with whatever evidence was found. A person reviews that page — including the artist match, the specific values, and the edit note — and decides whether to actually submit it. MetaForge Studio's role stops at "here's what I found and where it came from."

## Where the data comes from, in order of trust

Evidence is gathered in tiers, and a later tier is only ever consulted if the earlier ones came up empty or thin:

1. **MusicBrainz's own existing data.** If MusicBrainz already has a fact correct, there's nothing to propose.
2. **Discogs' structured release data** — catalog numbers, label info, release dates, and personnel credits as entered directly into Discogs' database by its editors. This is treated as high-confidence, structured evidence, not free text.
3. **AI-assisted web search** (Google's Gemini models, with real-time Google Search grounding) — used *only* as a fallback when the structured sources above don't have enough. This is the tier that needs the most scrutiny, so it gets the most safeguards (below).
4. **Manual entry** — facts a human (the tool's user) typed in directly, based on their own research (liner notes, discographies, etc.).

Every proposed fact carries a visible **provenance tag** (which of the above it came from) and a **confidence value**, both shown to the human reviewer before anything is submitted, and both included in the edit note MusicBrainz sees.

## The AI tier's anti-hallucination rule

Generative AI models can produce fluent, confident-sounding answers that are simply invented. MetaForge Studio treats that as a real risk, not a hypothetical one, and applies one hard rule to every AI-assisted search: **if the model's response isn't backed by an actual, real-time web search that the API confirms took place, the result is discarded — not surfaced, not flagged as "low confidence," just thrown away.** A plausible-sounding answer with no real search behind it is treated as no answer at all.

This isn't a formatting instruction to the model ("please only state verified facts") — it's a check against the API's own grounding metadata, which reports whether a real search actually happened. Asking an AI model nicely to avoid guessing doesn't reliably stop it from guessing; checking whether it actually searched does.

## Confidence isn't uniform, even within the AI tier

Not every AI-sourced fact is treated with the same confidence. For example, a person explicitly named as playing a specific instrument gets one confidence level; a person mentioned only as generally "associated with" a recording, without a clearly classifiable role, gets a lower one. A recording *session* date used as a stand-in for a *release* date is flagged as a weaker, proxy claim rather than presented as an equally strong fact. These distinctions are preserved and shown to the reviewer rather than flattened into a single "AI said so" bucket.

## Album-level facts vs. track-level facts

Some personnel credits are documented at the level of a specific track (a guest soloist on one song, for instance). Others are only known at the level of the whole album (e.g., "this was the session's regular backing band"). MetaForge Studio keeps that distinction rather than assuming one implies the other.

When a credit is only known at the album level but MusicBrainz's own data model requires editing one specific recording at a time, MetaForge Studio is explicit about the gap in the edit note itself: it states plainly that the underlying evidence describes the *album*, that it's being applied to *this* track on the assumption it holds across the release, and asks the reviewer to confirm that's accurate for this specific track before submitting. The assumption is visible, not hidden.

Before submitting, the tool's user can also review the album's full track list and explicitly exclude specific tracks a credit doesn't apply to (e.g. a single guest musician known to appear on only 2 of 16 tracks). Once any track has been excluded that way, the edit note for the remaining tracks changes accordingly — it no longer claims the credit is assumed to hold across the whole release, since that would no longer be true; instead it states that other tracks were reviewed and excluded, and this specific track was deliberately kept as one the credit is believed to apply to.

## Artist matching is never assumed

Discogs and free-text sources don't carry MusicBrainz artist identifiers. When a name needs to be matched to an existing MusicBrainz artist, MetaForge Studio performs a live search and shows the match's confidence score directly in the edit note — this is presented as a match to be verified, never as a settled fact.

## Data filtering

Credits like packaging design, photography, liner notes authorship, and similar non-musical roles are filtered out entirely before a candidate is ever built — they're excluded from consideration, not silently downgraded and left for a human to clean up. This isn't because that data isn't important, but rather MetaForge Studio doesn't require that data in the same way it requires information directly tied to the music itself.

## Why MetaForge Studio is seeking this type of granular data

(July 9, 2026) MetaForge Studio is still in Beta Testing, with the intention of further development and refinement.

The philosophy behind the suite of tools that comprise MetaForge Studio is based on the real-world observation that music metadata is often absent, inaccurate, or sometimes just plain useless. The suite refactors metadata to eliminate that useless and inaccurate data, and uses AI alongside command-line tools and libraries such as mp3val (bitstream validation and repair), fpcalc (AcoustID audio fingerprinting), and librosa (tempo/BPM analysis), among others, to tighten both the concepts of Genre (and Sub-Genre) as well as calculate additional data such as BPM, "Mood" (and Mood qualifiers), Starting Key, and more. The suite then writes those values to the host MP3 file via mutagen, and additionally to a locally hosted SQLite database. The suite also has the ability to query and store associated Personnel data (to the database only), to be used in an as-yet-undeveloped Intelligent Playlist Maker. More details on that effort will be published once the tool has been built.

Meanwhile, in the spirit of community contribution that is the cornerstone of the MusicBrainz resource, an additional tool was built to submit back data to the MusicBrainz database that is currently nonexistent there.

## Why this document exists

MetaForge Studio is a personal tool, not a bot account, and every edit it helps produce goes through a real person reading a real MusicBrainz form before submission. This document exists so that claim doesn't have to be taken on faith — the methodology above is what actually runs, and it's linked directly from the edit notes it produces.

Questions or concerns about a specific edit are welcome — see the [MetaForge Suite repository](https://github.com/johnfoliot/MetaForge-Suite) for contact details.
