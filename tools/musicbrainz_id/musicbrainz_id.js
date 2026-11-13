/* --- START OF FILE musicbrainz_id.js --- */
/**
 * ======================================================================
 * MetaForge Studio: MusicBrainz IDs (pipeline step 2 of 3)
 * File Location: \tools\musicbrainz_id\musicbrainz_id.js
 * v2 (2026-11-13): per-tool pass.
 *  - Search results: a radio per release (the table stays a table);
 *    MusicBrainz text is always inserted as text, never as HTML.
 *  - Country flags are local (ui/images/flags) with the country's name
 *    as alt text; codes without a flag show as text.
 *  - Track order: type each file's intended position, then Apply order
 *    (or Enter), the Settings toolbar pattern (John, 2026-11-13).
 *  - Commit streams one Activity log entry per file (MFEvents) and only
 *    offers the Next-step bar after a clean commit.
 * ======================================================================
 */

window.metaforge = window.metaforge || {};

window.metaforge.musicbrainz_id = {
    state: {
        localPath: "",
        localTrackCount: 0,
        currentReleaseId: "",
        currentArtistId: "",
        currentReleaseGroupId: "",
        currentCountryCode: "",
        currentReleaseYear: "Unknown",
        releaseGroupFirstDate: "",
        releaseGroupSecondaryTypes: [],
        localFiles: [],   // [ { filename: str, title: str } ]
        remoteTracks: [], // [ { position, title, track_id, recording_id, work_id, artist } ]
        isLocked: false
    },
    detailsTimer: null,
    detailsRequest: 0,

    init: function() {
        setTimeout(() => {
            const header = document.getElementById('mb-id-header');
            if (!header) return;
            this.wire();
            header.focus();
            this.ingestContext();
        }, 50);
    },

    /** Event wiring (was inline onclick/onsubmit). Once per screen build. */
    wire: function() {
        const form = document.getElementById('mb-search-form');
        if (!form || form.dataset.wired) return;
        form.dataset.wired = 'true';

        form.addEventListener('submit', (e) => { e.preventDefault(); this.search(); });
        document.getElementById('mb-browse-btn')?.addEventListener('click', () => this.selectFolder());
        document.getElementById('mb-order-form')?.addEventListener('submit', (e) => { e.preventDefault(); this.applyOrder(); });
        document.getElementById('mb-commit-btn')?.addEventListener('click', () => this.commit());

        // Choosing a release. Arrow keys move through a radio group and
        // check each radio as they go, so the details fetch waits until the
        // choice settles (MusicBrainz allows about one request a second).
        const body = document.getElementById('mb-results-body');
        body?.addEventListener('change', (e) => {
            if (e.target.matches('.mb-pick')) this.queueRelease(e.target.value);
        });
        // A click anywhere on a row chooses it (the radio is the real control).
        body?.addEventListener('click', (e) => {
            const row = e.target.closest('tr[data-release-id]');
            if (!row || e.target.matches('.mb-pick')) return;
            const radio = row.querySelector('.mb-pick');
            if (radio && !radio.checked && !radio.disabled) {
                radio.checked = true;
                radio.focus();
                this.queueRelease(radio.value);
            }
        });
    },

    ingestContext: function() {
        const contextPath = window.mf_context_path || "";
        if (!contextPath) return;
        const pathInput = document.getElementById('mb-local-path');
        if (!pathInput) return;
        this.state.localPath = contextPath;
        pathInput.value = contextPath;
        window.mf_context_path = null;
        this.getFolderContext(contextPath, true);
    },

    selectFolder: async function() {
        try {
            const response = await fetch('/select_folder');
            const data = await response.json();
            if (data.path) {
                this.state.localPath = data.path;
                document.getElementById('mb-local-path').value = data.path;
                this.getFolderContext(data.path, false);
            }
        } catch (err) { console.error("Path selection failed:", err); }
    },

    getFolderContext: async function(path, fromHandoff) {
        try {
            const response = await fetch('/run_tool_logic/musicbrainz_id/get_folder_context', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ local_path: path })
            });
            const data = await response.json();
            if (data.status === "success" && data.context) {
                document.getElementById('mb-album-input').value = data.context.album || "";
                document.getElementById('mb-artist-input').value = data.context.artist || "";
                this.state.localTrackCount = data.context.track_count || 0;
                document.getElementById('mb-local-track-count').value = this.state.localTrackCount || "--";
                if (fromHandoff) this.setStatus("Album details filled in from the album folder.", "ok", true);
            }
        } catch (err) { console.warn("Discovery context failed."); }
    },

    // ------------------------------------------------------------ search
    search: async function() {
        const artist = document.getElementById('mb-artist-input').value.trim();
        const album = document.getElementById('mb-album-input').value.trim();
        const body = document.getElementById('mb-results-body');

        if (!artist || !album) {
            this.setStatus("Enter both Artist and Album to search.", "error", true);
            document.getElementById(artist ? 'mb-album-input' : 'mb-artist-input').focus();
            return;
        }

        // Visible "in progress" note only; not announced (an interstitial
        // "Searching..." is just noise for screen-reader users).
        this.setStatus("", "");
        body.replaceChildren(this.noteRow("Searching MusicBrainz…"));

        try {
            const response = await fetch('/run_tool_logic/musicbrainz_id/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ artist, album })
            });
            const data = await response.json();
            // A failed search is shown and announced as a failure, never as
            // "no results" (John, 2026-11-13: a busy MusicBrainz used to look
            // exactly like "nothing exists").
            if (data.status === "success") {
                this.renderResults(data.results);
                const n = (data.results || []).length;
                this.setStatus(n === 0 ? "No matches found." : `${n} matching release${n === 1 ? "" : "s"} found.`, "ok", true);
            } else {
                this.renderSearchError(data.message || "MusicBrainz search failed.", data.reason);
            }
        } catch (err) {
            this.renderSearchError("MetaForge could not complete the search (the request got no reply). Try again.", "failed");
        }
    },

    noteRow: function(text, isError) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 7;
        cell.className = 'mb-results-note' + (isError ? ' is-error' : '');
        cell.textContent = text;
        row.append(cell);
        return row;
    },

    renderSearchError: function(message, reason) {
        document.getElementById('mb-results-body').replaceChildren(this.noteRow(message, true));
        this.setStatus(
            reason === "unavailable"
                ? "MusicBrainz is busy right now. Wait a few seconds and search again."
                : "The MusicBrainz search failed. The reason is shown in the results list.",
            "error", true
        );
    },

    /** Country flag (local SVG) + code. Alt text is the country's name. */
    countryCell: function(code) {
        const cc = (code || '').toUpperCase();
        const wrap = document.createElement('span');
        wrap.className = 'mb-country';
        const special = { XW: 'Worldwide', XE: 'Europe', '': 'Unknown', '??': 'Unknown' };
        let name = special[cc];
        if (!name) {
            try { name = new Intl.DisplayNames(['en'], { type: 'region' }).of(cc); } catch { name = cc; }
        }
        const flagFile = cc === 'XE' ? 'eu' : (special[cc] ? '' : cc.toLowerCase());
        if (flagFile) {
            const img = document.createElement('img');
            img.className = 'mb-flag';
            img.src = `/ui/images/flags/${flagFile}.svg`;
            img.alt = name;
            img.title = name;
            // No flag for this code (e.g. a historic country): the code stays as text.
            img.addEventListener('error', () => {
                const t = document.createElement('span');
                t.className = 'mf-visually-hidden';
                t.textContent = name;
                img.replaceWith(t);
            });
            wrap.append(img);
        } else {
            const t = document.createElement('span');
            t.className = 'mf-visually-hidden';
            t.textContent = name;
            wrap.append(t);
        }
        const codeText = document.createElement('span');
        codeText.className = 'mb-country-code';
        codeText.textContent = cc && cc !== '??' ? cc : '—';
        codeText.setAttribute('aria-hidden', 'true');   // the name above is what's read
        wrap.append(codeText);
        return wrap;
    },

    renderResults: function(results) {
        const body = document.getElementById('mb-results-body');
        if (!results || results.length === 0) {
            body.replaceChildren(this.noteRow("No matches found."));
            return;
        }
        const rows = results.map((r, i) => {
            const tr = document.createElement('tr');
            tr.dataset.releaseId = r.id;
            const titleId = `mb-rel-${i}`;

            const td = (cls) => { const c = document.createElement('td'); if (cls) c.className = cls; return c; };

            const pick = td();
            const radio = document.createElement('input');
            radio.type = 'radio';
            radio.name = 'mb-release';
            radio.className = 'mb-pick';
            radio.value = r.id;
            radio.setAttribute('aria-labelledby', titleId);
            radio.setAttribute('aria-describedby', `${titleId}-facts`);
            pick.append(radio);

            const score = td('mb-num'); score.textContent = `${r.score}%`;

            const title = td();
            title.id = titleId;
            const artist = document.createElement('span');
            artist.className = 'mb-release-artist';
            artist.textContent = r.artist;
            title.append(artist, document.createTextNode(r.title));

            const format = td(); format.textContent = r.format;
            const tracks = td('mb-num'); tracks.textContent = r.track_count;
            // No date on MusicBrainz arrives as "Unkn" ("Unknown" cut to 4).
            const hasYear = /^\d{4}$/.test(String(r.year || ''));
            const year = td('mb-num'); year.textContent = hasYear ? r.year : '—';
            const country = td(); country.append(this.countryCell(r.country_code));

            // Spoken description of the choice: "CD, 12 tracks, 1974, Netherlands".
            const facts = document.createElement('span');
            facts.id = `${titleId}-facts`;
            facts.hidden = true;   // description only: not read again when browsing the table
            const countryName = country.querySelector('img')?.alt || country.querySelector('.mf-visually-hidden')?.textContent || '';
            facts.textContent = [r.format, `${r.track_count} tracks`, hasYear ? r.year : 'year unknown', countryName, `score ${r.score}%`].filter(Boolean).join(', ');
            pick.append(facts);

            tr.append(pick, score, title, format, tracks, year, country);
            return tr;
        });
        body.replaceChildren(...rows);
    },

    queueRelease: function(releaseId) {
        if (this.state.isLocked) return;
        clearTimeout(this.detailsTimer);
        this.detailsTimer = setTimeout(() => this.selectRelease(releaseId), 500);
    },

    // ------------------------------------------------- release details
    selectRelease: async function(releaseId) {
        if (this.state.isLocked) return;
        this.state.currentReleaseId = releaseId;
        const requestNo = ++this.detailsRequest;

        const summary = document.getElementById('mb-id-summary');
        summary.className = '';
        summary.textContent = "Getting the release details from MusicBrainz…";
        this.showComparison();
        this.setOrderEnabled(false);
        document.getElementById('mb-commit-btn').disabled = true;

        try {
            const response = await fetch('/run_tool_logic/musicbrainz_id/get_release_details', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ release_id: releaseId, local_path: this.state.localPath })
            });
            const data = await response.json();
            if (requestNo !== this.detailsRequest) return;   // a newer choice replaced this one

            if (data.status === "success") {
                Object.assign(this.state, {
                    currentArtistId: data.artist_id,
                    currentReleaseGroupId: data.release_group_id,
                    currentCountryCode: data.country_code,
                    currentArtistCountry: data.artist_country,
                    currentReleaseTitle: data.release_title,
                    currentFormat: data.format,
                    currentReleaseYear: data.release_year,
                    releaseGroupFirstDate: data.release_group_first_date,
                    releaseGroupSecondaryTypes: data.release_group_secondary_types,
                    mbLabelName: data.mb_label_name,
                    mbCatalogNumber: data.mb_catalog_number,
                    remoteTracks: data.remote_tracks || [],
                    localFiles: data.local_tracks || []
                });
                // The folder's own order, so the commit knows whether the
                // user reordered (and so whether to renumber the prefixes).
                this.state.originalOrder = this.state.localFiles.map(f => f.filename);

                summary.replaceChildren(
                    document.createTextNode(`${data.release_title || 'Release'}: ${data.format || 'format unknown'}, ${data.release_year}, ${this.countryName(data.country_code)}`)
                );
                const id = document.createElement('span');
                id.className = 'mb-summary-id';
                id.textContent = `MusicBrainz release ID ${releaseId}`;
                summary.append(id);

                this.renderComparison();
                const hasFiles = this.state.localFiles.length > 0;
                this.setOrderEnabled(hasFiles);
                document.getElementById('mb-commit-btn').disabled = !hasFiles;
                this.setOrderMsg(hasFiles
                    ? "Check the two lists line up. To move a file, type its new position and choose Apply order."
                    : "No audio files were found in the album folder. Choose the folder with Browse.", hasFiles ? "" : "error");
                this.setStatus("Release details ready. Check the track order on the right.", "ok", true);
            } else {
                summary.className = 'is-error';
                summary.textContent = `The release details couldn't be loaded: ${data.message || "unknown error"}`;
                this.setStatus("The release details couldn't be loaded.", "error", true);
            }
        } catch (err) {
            if (requestNo !== this.detailsRequest) return;
            summary.className = 'is-error';
            summary.textContent = "The release details couldn't be loaded (the request got no reply).";
            this.setStatus("The release details couldn't be loaded.", "error", true);
        }
    },

    countryName: function(code) {
        const cc = (code || '').toUpperCase();
        if (cc === 'XW') return 'Worldwide';
        if (cc === 'XE') return 'Europe';
        if (!cc || cc === '??') return 'country unknown';
        try { return new Intl.DisplayNames(['en'], { type: 'region' }).of(cc); } catch { return cc; }
    },

    // ----------------------------------------------- side-by-side list
    renderComparison: function() {
        const form = document.getElementById('mb-order-form');
        if (!form) return;
        const { localFiles, remoteTracks } = this.state;
        const n = localFiles.length;
        const rows = [];
        const maxRows = Math.max(n, remoteTracks.length);

        for (let i = 0; i < maxRows; i++) {
            const local = localFiles[i] || null;
            const remote = remoteTracks[i] || null;
            const row = document.createElement('div');
            row.className = 'mb-handshake-row';

            const orderCell = document.createElement('div');
            const nameCell = document.createElement('div');
            nameCell.className = 'mb-local-name';
            if (local) {
                const input = document.createElement('input');
                input.type = 'number';
                input.className = 'mb-order-input';
                input.min = '1';
                input.max = String(n);
                input.value = String(i + 1);
                input.dataset.index = String(i);
                input.setAttribute('aria-label', `Position for ${local.filename}`);
                input.addEventListener('input', () => this.clearOrderError(input));
                orderCell.append(input);
                nameCell.textContent = local.filename;
            }

            const remoteCell = document.createElement('div');
            remoteCell.className = 'mb-remote-name';
            if (remote) {
                const pos = document.createElement('span');
                pos.className = 'mb-remote-pos';
                pos.textContent = `${remote.position}. `;
                remoteCell.append(pos, document.createTextNode(remote.title));
            }

            row.append(orderCell, nameCell, remoteCell);
            rows.push(row);
        }
        form.replaceChildren(...rows);
    },

    /**
     * The Settings toolbar pattern (type numbers, apply once), with "move
     * to" semantics: each file whose number was changed is taken out and
     * put back at exactly the position typed; every other file keeps its
     * order. So typing 3 makes a file 3rd whether it moves up or down, and
     * typing 2 and 1 on the first two files swaps them. Numbers outside
     * 1..N, or blank, aren't applied: the field is marked and focused.
     */
    applyOrder: function() {
        if (this.state.isLocked) return;
        const inputs = [...document.querySelectorAll('#mb-order-form .mb-order-input')];
        const n = inputs.length;
        if (!n) return;

        for (const input of inputs) {
            const v = Number(input.value);
            if (!Number.isInteger(v) || v < 1 || v > n) {
                const name = this.state.localFiles[Number(input.dataset.index)]?.filename || 'this file';
                input.setAttribute('aria-invalid', 'true');
                input.setAttribute('aria-describedby', 'mb-order-msg');
                this.setOrderMsg(`The position for ${name} must be a number from 1 to ${n}. Nothing was moved.`, "error");
                input.focus();
                input.select();
                return;
            }
        }

        const items = inputs.map((input, i) => {
            const v = Number(input.value);
            return { file: this.state.localFiles[i], v, i, changed: v !== i + 1 };
        });
        const ordered = items.filter(it => !it.changed);
        items.filter(it => it.changed)
             .sort((a, b) => (a.v - b.v) || (a.i - b.i))
             .forEach(it => ordered.splice(Math.min(it.v - 1, ordered.length), 0, it));

        // Count the files the user moved, not the ones that shifted to make room.
        const moved = items.filter(it => it.changed).length;
        this.state.localFiles = ordered.map(it => it.file);
        this.renderComparison();
        const msg = moved === 0
            ? "Order unchanged."
            : `Order applied: ${moved} file${moved === 1 ? '' : 's'} moved.`;
        this.setOrderMsg(msg, "");
        window.MFAnnounce?.(msg);
        document.getElementById('mb-apply-order-btn')?.focus();
    },

    clearOrderError: function(input) {
        if (input.getAttribute('aria-invalid') !== 'true') return;
        input.removeAttribute('aria-invalid');
        input.removeAttribute('aria-describedby');
        this.setOrderMsg("", "");
    },

    setOrderEnabled: function(on) {
        const btn = document.getElementById('mb-apply-order-btn');
        if (btn) btn.disabled = !on;
    },

    setOrderMsg: function(text, kind) {
        const el = document.getElementById('mb-order-msg');
        if (!el) return;
        el.textContent = text;
        el.className = kind === 'error' ? 'is-error' : '';
    },

    showComparison: function() {
        document.getElementById('mb-order-form').hidden = false;
        document.getElementById('mb-alignment-headers').hidden = false;
        const log = document.getElementById('mb-activity');
        log.hidden = true;
        log.replaceChildren();
        document.getElementById('mb-handoff').hidden = true;
    },

    // ------------------------------------------------------------ commit
    commit: async function() {
        if (this.state.isLocked || !this.state.localFiles.length) return;
        this.state.isLocked = true;

        const commitBtn = document.getElementById('mb-commit-btn');
        commitBtn.disabled = true;
        this.setOrderEnabled(false);
        document.querySelectorAll('.mb-pick').forEach(r => { r.disabled = true; });

        const artistSeed = document.getElementById('mb-artist-input').value.trim();
        const mapping = this.state.localFiles.map((file, index) => {
            const remote = this.state.remoteTracks[index];
            return {
                current_filename: file.filename,
                target_title: remote ? remote.title : "Unknown Title",
                track_id: remote ? remote.track_id : "",
                recording_id: remote ? remote.recording_id : "",
                work_id: remote ? remote.work_id : "",
                // Real per-recording artist-credit from MB (empty for a
                // normal single-artist release): Various Artists compilations
                // keep each track's own performer.
                track_artist: remote ? remote.artist : "",
                track_num: index + 1,
                artist_id: this.state.currentArtistId,
                album_id: this.state.currentReleaseId,
                release_group_id: this.state.currentReleaseGroupId,
                country_code: this.state.currentCountryCode,
                artist_country: this.state.currentArtistCountry
            };
        });

        // The side-by-side list has done its job: the Activity log takes
        // its place and fills in one entry per file as the commit runs.
        const log = document.getElementById('mb-activity');
        document.getElementById('mb-order-form').hidden = true;
        document.getElementById('mb-alignment-headers').hidden = true;
        log.replaceChildren();
        log.hidden = false;
        this.setOrderMsg("", "");

        let handoff = false;
        try {
            const response = await fetch('/run_tool_logic/musicbrainz_id/commit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    local_path: this.state.localPath,
                    artist_seed: artistSeed,
                    release_year: this.state.currentReleaseYear,
                    release_group_first_date: this.state.releaseGroupFirstDate,
                    release_group_secondary_types: this.state.releaseGroupSecondaryTypes,
                    mb_label_name: this.state.mbLabelName,
                    mb_catalog_number: this.state.mbCatalogNumber,
                    release_title: this.state.currentReleaseTitle,
                    format: this.state.currentFormat,
                    // Reordered on screen? Then the filename numbers follow
                    // the new order (disc hundreds kept). John, 2026-11-13.
                    renumber: this.state.localFiles.some((f, i) => f.filename !== (this.state.originalOrder || [])[i]),
                    mapping: mapping
                })
            });
            await window.MFEvents.read(response, {
                log,
                onSignal: (name) => { if (name === 'handoff_ready') handoff = true; }
            });
        } catch (err) {
            window.MFEvents.render(log, { kind: 'error', text: `The commit stopped: ${err.message}` });
            window.MFAnnounce(`Error: the commit stopped: ${err.message}`, { urgent: true });
        } finally {
            this.state.isLocked = false;
            // Files have been renamed, so the old list is out of date either
            // way: to retry, choose the release again (it re-reads the folder).
            document.querySelectorAll('.mb-pick').forEach(r => { r.disabled = false; });
        }

        if (handoff) this.showHandoff();
    },

    showHandoff: function() {
        const bar = document.getElementById('mb-handoff');
        const btn = document.getElementById('mb-continue-btn');
        if (!bar || !btn) return;
        const path = this.state.localPath;
        btn.onclick = () => window.mfAdvanceWorkflow('intelli-tagger', path);
        bar.hidden = false;
        btn.focus();
    },

    /** Visible status line beside Search; optionally spoken via the shared announcer. */
    setStatus: function(msg, kind, speak) {
        const el = document.getElementById('mb-status');
        if (!el) return;
        el.textContent = msg;
        el.className = kind === 'error' ? 'is-error' : (kind === 'ok' ? 'is-ok' : '');
        if (speak && msg) window.MFAnnounce?.(kind === 'error' ? `Error: ${msg}` : msg);
    }
};

window.metaforge.musicbrainz_id.init();
/* --- END OF FILE musicbrainz_id.js --- */
