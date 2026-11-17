# Changelog

## 2.0.0 — in development (13–16 November 2026)

MetaForge Studio 2 is a rebuild of every screen to the WCAG 2.2 AA accessibility standard, with plain-language wording, and with layouts that still work when Windows text is enlarged to 150% or 200%. MetaForge 1.x is retired; its last version is kept as the tag `v1-final`.

### Across the whole app
- **New look:** the Atkinson Hyperlegible Next font is now included with the app, and themes get a consistent set of colours. Focus outlines are clearly visible on every surface, and scrollbars use the brand colour.
- **Left toolbar:** it can be expanded or collapsed (» button, or Ctrl+B), and tool names can be shown or hidden. You choose the tool order and add your own separators in Settings › Toolbar.
- **Every screen starts the same way:** the tool's icon and name, then a Help button that opens one shared Help window.
- **Enter does the obvious thing:** in any group of fields, pressing Enter runs its main button (search, save, and so on).
- **Live progress for long jobs:** Unpack & Convert, MusicBrainz IDs and Intelli-Tagger show one log entry per track as they work, and the same entries go to MetaForge.log.
- **"Next step" bar:** after a step finishes, a bar offers to open the next tool in the pipeline, already pointed at the same album.
- **Unsaved work is protected:** a tool with unsaved changes asks before you leave it.
- **Security:** the app's built-in web server now accepts connections only from this computer.

### Tools
- **Unpack & Convert:** rebuilt screen; a new step for choosing the album cover; one log entry per track. The form now fits the window without scrolling.
- **MusicBrainz IDs:** rebuilt screen and live progress. Results are a list you choose from with radio buttons, and you can reorder tracks by typing a position. Filename number prefixes are renumbered after a reorder.
- **Intelli-Tagger:** rebuilt screen and live progress, with track details laid out clearly. Results are labelled in bold with a colon (for example "Genre: Blues"), and it checks that old tags were fully removed.
- **Album Personnel:** rebuilt screen. *Fixed:* saved credits could sometimes be filed under the wrong album with a similar name; each album is now matched exactly.
- **Bio Builder:** biographies are based on a real web search; new portraits stay drafts until you save; a new Regenerate button; and the current album's artist loads by itself.
- **Database Tools:** rebuilt screens. Renaming, merging and removing artists or albums now shows a preview first and makes a backup. Changes also carry through to the music files' tags and MetaForge's own records.
- **AcoustID Manager:** rebuilt. It now remembers what was submitted, so it can check whether each submission was accepted. Its queues are safer to read and write. *Fixed:* file paths in a queue could get stuck together on one line.
- **Audio Repair:** rebuilt. Each file is repaired on a copy and checked before replacing the original, and the original is kept as a backup. *Fixed:* damaged files were never sent to Audio Repair, because the file checker always reported "OK".
- **Music Sharing:** rebuilt. It uses the album cover, adds title/artist/album/year to the video, and asks before replacing an existing file.
- **MusicBrainz Submit:** rebuilt around albums. You choose an album, MetaForge checks what MusicBrainz already has, and the rest of the credits are added to MusicBrainz's own page in batches of up to 25 for you to confirm. Only credits backed by a checked source are ever sent. The AI Heuristics document is updated to match.
- **YouTube to MP3:** new. It handles single songs, playlists and whole-album videos, and can split an album video into tracks; you review each cut, with a Play button, before the files are made. Files are saved into the album folder you choose.
- **Settings:** a new tab layout, a Genre list that shows how many tracks use each genre, plain-language configuration labels, and a clearer update check.
  - **Create a theme:** new. Build your own theme from scratch, from one colour, or from a pasted palette. Every colour is checked for contrast, and a matching 3-D logo is made for you.
- **Dashboard:** new. Tiles answer four questions: how much is tagged (by category folder or by genre), what's waiting in other tools, who needs a biography, and what looks wrong in the data. Each tile is a self-contained plug-in. You choose which tiles show, their width and their order in Settings › Dashboard.

### Behind the scenes
- **Faster artist lookups:** new database indexes make the "Who needs a bio?" count take about 2 seconds instead of over 2 minutes.
- **Retired:** old one-off scripts moved out of the app.

