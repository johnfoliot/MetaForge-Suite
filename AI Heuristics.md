# AI Heuristics — How MetaForge Studio Determines the Data It Submits to MusicBrainz

This document explains the methodology behind edits submitted to MusicBrainz using **MetaForge Studio**, a personal music-library tagging tool. If you're a MusicBrainz editor reviewing one of these edits and want to know where the proposed data came from and how much to trust it, this is that explanation.

The short version: **nothing here submits itself.** MetaForge Studio builds evidence and fills in MusicBrainz's own edit page; a human reviews it and clicks "Enter edit" every single time. What follows is how that evidence gets built.

## Nothing is submitted automatically

MetaForge Studio never authenticates to MusicBrainz and never writes to it via the API; it only reads MusicBrainz's public data. When the tool has credits worth proposing for a release, it opens that release's *own* relationship editor (the page you'd use by hand) in a window where the user is logged in as themselves. It adds the proposed relationships there and writes the edit note, then stops. The user checks the relationships, the artists and the note on that page, and decides whether to click "Enter edit". MetaForge Studio's role stops at "here's what I found and where it came from."

## What MetaForge Studio submits

Today, MetaForge Studio proposes **release relationships** only: who produced, arranged, wrote, composed, sang or played an instrument on a release. (Original release-date proposals are paused, and per-track credits are not sent yet.)

## Where the data comes from

Personnel credits come from these sources:

1. **MusicBrainz's own existing data.** If MusicBrainz already has a credit, there's nothing to propose.
2. **Discogs' structured release data** — credits as entered into Discogs' database by its editors, read through the Discogs API.
3. **Wikipedia and AllMusic** — credits from an album's Wikipedia article or its AllMusic credits page, brought in when the tool's user asks for them (never automatically).
4. **Manual entry** — credits the tool's user typed in directly from their own research (liner notes, discographies, etc.).
5. **AI-assisted web search** (Google's Gemini models, with real-time Google Search grounding) — used automatically *only* when MusicBrainz and Discogs together come up thin. **AI-found credits are never sent to MusicBrainz on the AI's word alone:** a person has to confirm each one first (see "How a human verifies an AI-sourced fact").

Each line of the edit note names the source of that credit (for example "from Discogs release credits" or "from the Wikipedia article on this album"). MetaForge Studio keeps an internal confidence number for each credit for its own use; it isn't shown in edit notes and doesn't decide what gets proposed.

## What is checked before anything is proposed

When an album is reviewed, MetaForge Studio reads the release's existing relationships from MusicBrainz (release, track and song level; the user can re-check at any time) and:

- **Leaves out anything MusicBrainz already has.** If the same person is already credited in a related but different way (say "organ" where the source says "keyboards"), the credit is held back for the user to decide, unticked.
- **Leaves out credits for only some tracks.** When the source limits a credit to certain tracks ("tracks 3, 5 and 11"), it isn't proposed as a release-wide fact.
- **Maps each role to a MusicBrainz relationship by its wording**, and leaves out roles too general to map honestly ("Featuring", "Musician") or ones MetaForge Studio doesn't send yet (engineering, mastering, executive or reissue production, artwork).
- **Matches instruments to MusicBrainz's own instrument list**, by an instrument's exact name first, then by an alias that belongs to exactly one instrument. A role with no such match isn't sent, rather than being guessed.

## The AI tier's anti-hallucination rule

Generative AI models can produce fluent, confident-sounding answers that are simply invented. MetaForge Studio treats that as a real risk, not a hypothetical one, and applies one hard rule to every AI-assisted search: **if the model's response isn't backed by an actual, real-time web search that the API confirms took place, the result is discarded — not surfaced, not flagged as "low confidence," just thrown away.** A plausible-sounding answer with no real search behind it is treated as no answer at all.

This isn't a formatting instruction to the model ("please only state verified facts") — it's a check against the API's own grounding metadata, which reports whether a real search actually happened. Asking an AI model nicely to avoid guessing doesn't reliably stop it from guessing; checking whether it actually searched does.

## Confirmed and inferred AI credits

The model is asked to tag every credit it returns as one of two kinds, and the difference is kept:

- **Confirmed** — the model reports that a source ties this credit to this specific track: liner notes, a discography entry keyed to that exact recording, a review naming the specific performance.
- **Inferred** — the credit is reasonable but not track-specific. "This was the label's regular house band during this era" is real, useful context, but it isn't the same claim as a source stating that band played on *this particular* recording.

The model's own "confirmed" tag isn't taken at face value. MetaForge Studio checks that the person's name (or at least their surname) actually appears in the parts of the answer the API says are backed by search results. A credit the model tags as confirmed whose name never appears in that search-backed text is treated as inferred instead. This check is about the *name*, not the role or the track, so it catches invented people, not every possible error, which is one reason a human still has to confirm each AI credit before it can be sent.

## How a human verifies an AI-sourced fact

Before an AI-found credit can reach MusicBrainz, the tool's user has to check it against a real source: clicking through to one of the actual pages the AI's search surfaced, reading it in a live window, and recording an honest judgment of what it shows, at one of three levels rather than a single "verified" checkbox:

- **Explicit** — the page directly and specifically confirms this credit.
- **Inferred** — the page supports the credit, but isn't specific to this exact track or release.
- **Anecdotal** — the page offers some supporting mention, without being a solid, citable source.

Only **explicit** and **inferred** credits are proposed to MusicBrainz. An anecdotal mention is kept for the tool's own use and never sent. For the credits that are sent, the edit note states that the submitter checked a source, gives that level in plain words, and includes the page they looked at as a link. Because a person chose and read that page themselves, it is their own citation, not something extracted from the AI's search results.

The tool's user can also mark an AI credit as confirmed on their own judgment, without opening a source. That's useful for their own library, but it isn't a citation, so those credits are never sent to MusicBrainz.

Unconfirmed AI credits, and the names of the sites the AI's search consulted, are never included in an edit: Google's search-grounding terms don't allow MetaForge Studio to pass what its AI search surfaced on to a different audience, and an unchecked AI credit isn't something to ask MusicBrainz editors to trust.

If the page a user confirmed a credit with appears to describe a different album, the credit is held back, unticked, for the user to look at again.

## Release-wide credits

Some personnel credits belong to a specific track (a guest soloist on one song, for instance); others describe the whole release. MetaForge Studio keeps that distinction and, for now, proposes only credits the source gives for the release as a whole, as release relationships: one real release-level fact, not an assumption copied onto every track. Credits the source ties to particular tracks are kept back for a later, track-level step.

## Artist matching is never assumed

Discogs and free-text sources don't carry MusicBrainz artist identifiers. A credit is proposed only when its person is matched to a MusicBrainz artist with certainty: by a MusicBrainz ID MetaForge Studio already has, or because exactly one MusicBrainz artist has that exact name (or that exact alias). When there's more than one, or no exact match, the user chooses the artist from MusicBrainz's search results or doesn't send the credit. Every edit note states these matching rules.

## Data filtering

Credits like packaging design, photography, liner-notes authorship, mastering and similar non-musical roles are filtered out when credits are gathered, and any that slip through are never proposed to MusicBrainz. This isn't because that data isn't important, but rather MetaForge Studio doesn't require that data in the same way it requires information directly tied to the music itself.

## Why MetaForge Studio is seeking this type of granular data

(Updated November 16, 2026) MetaForge Studio is still in Beta Testing, with the intention of further development and refinement.

The philosophy behind the suite of tools that comprise MetaForge Studio is based on the real-world observation that music metadata is often absent, inaccurate, or sometimes just plain useless. The suite refactors metadata to eliminate that useless and inaccurate data, and uses AI alongside command-line tools and libraries such as mp3val (bitstream validation and repair), fpcalc (AcoustID audio fingerprinting), and librosa (tempo/BPM analysis), among others, to tighten both the concepts of Genre (and Sub-Genre) as well as calculate additional data such as BPM, "Mood" (and Mood qualifiers), Starting Key, and more. The suite then writes those values to the host MP3 file via mutagen, and additionally to a locally hosted SQLite database. The suite also has the ability to query and store associated Personnel data (to the database only), to be used in an as-yet-undeveloped Intelligent Playlist Maker. More details on that effort will be published once the tool has been built.

**Meanwhile, in the spirit of community contribution that is the cornerstone of the MusicBrainz resource, an additional tool was built to submit back data to the MusicBrainz database that is currently nonexistent there.**

## Why this document exists

MetaForge Studio is a personal tool, not a bot account, and every edit it helps produce goes through a real person reading a real MusicBrainz page before submission. This document exists so that claim doesn't have to be taken on faith — the methodology above is what actually runs, and it's linked directly from the edit notes it produces.

Questions or concerns about a specific edit are welcome — see the [MetaForge Suite repository](https://github.com/johnfoliot/MetaForge-Suite) for contact details.
