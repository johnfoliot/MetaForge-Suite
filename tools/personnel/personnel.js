/* --- START OF FILE personnel.js --- */
/**
 * MetaForge Studio: Album Personnel (Personnel Engine v2)
 * Role: the MusicBrainz + Discogs automatic waterfall (with the AI web
 * search fallback), Wikipedia search, AllMusic paste, and the shared
 * review-and-save table.
 * v2 (2026-11-15): per-tool pass.
 *  - "Find credits" is the form's submit (Enter re-runs the automatic
 *    search with whatever is in the fields, so a folder without a manifest
 *    or a corrected name is no longer a dead end).
 *  - Everything is built with the DOM API (1.x pasted Wikipedia titles into
 *    onclick strings, so an apostrophe broke "Select").
 *  - Credit rows: labelled fields, named remove buttons, real sort buttons,
 *    focus kept in place across re-renders.
 *  - No blocking alert()s: a status line + the shared announcer.
 *  - AllMusic paste is a native <dialog>.
 *  - The save reports what it saved and what it couldn't; a clean save
 *    offers Bio Builder only when the artist has no bio yet (John).
 */

window.metaforge = window.metaforge || {};
window.metaforge.personnel = {
    state: {
        localPath: "",
        mapping: [],
        isLocked: false,
        pendingVerifyIdx: null,
        sortKey: null,
        sortDir: 1,
        manualConfirmConfidence: null
    },

    _sourceLabels: { mb: 'MusicBrainz', wiki: 'Wikipedia', discogs: 'Discogs', allmusic: 'AllMusic' },

    $: (id) => document.getElementById(id),

    init: function() {
        setTimeout(() => {
            if (!this.$('p-form')) return;
            this.wire();
            document.querySelector('#mfi-content h1.main')?.focus();
            this.ingestContext();
        }, 50);
    },

    /** Event wiring (was inline onclick attributes). Once per screen build. */
    wire: function() {
        const form = this.$('p-form');
        if (form.dataset.wired) return;
        form.dataset.wired = 'true';

        form.addEventListener('submit', (e) => { e.preventDefault(); this.resolveWaterfall(); });
        this.$('p-browse-btn').addEventListener('click', () => this.selectFolder());
        this.$('p-src-wiki-btn').addEventListener('click', () => this.searchWikipedia());
        this.$('p-src-allmusic-btn').addEventListener('click', () => this.checkAllMusic());
        this.$('p-add-btn').addEventListener('click', () => this.addManualRow());
        this.$('p-commit-btn').addEventListener('click', () => this.commitToDatabase());
        this.$('p-bio-btn').addEventListener('click', () => window.mfAdvanceWorkflow?.('biography', this.state.localPath));
        document.querySelectorAll('.p-sort').forEach(b => b.addEventListener('click', () => this.sortMapping(b.dataset.sort)));

        // Wikipedia results: one delegated listener (no per-row onclick strings).
        this.$('p-search-results-body').addEventListener('click', (e) => {
            const btn = e.target.closest('button[data-title]');
            if (btn) this.selectCandidate(btn.dataset.title);
        });

        // Credit rows: delegated input/change/click by row index.
        const body = this.$('p-mapping-body');
        body.addEventListener('input', (e) => {
            const idx = Number(e.target.closest('tr')?.dataset.idx);
            if (Number.isNaN(idx)) return;
            if (e.target.matches('.p-map-name')) this.updateMappingField(idx, 'name', e.target.value);
            if (e.target.matches('.p-map-role')) this.updateMappingField(idx, 'role', e.target.value);
        });
        body.addEventListener('change', (e) => {
            const idx = Number(e.target.closest('tr')?.dataset.idx);
            if (e.target.matches('.p-map-status')) this.updateConfidenceStatus(idx, e.target.value);
        });
        body.addEventListener('click', (e) => {
            const idx = Number(e.target.closest('tr')?.dataset.idx);
            if (e.target.closest('.p-remove')) this.removeRow(idx);
            if (e.target.closest('.p-verify')) this.verifySource(idx);
        });

        // AllMusic dialog: paste handler, and "closed without a paste" = checked, nothing found.
        const dlg = this.$('p-allmusic-dialog');
        this.$('p-allmusic-paste').addEventListener('paste', (e) => this.handleAllMusicPaste(e));
        dlg.addEventListener('close', () => {
            if (dlg.returnValue !== 'found') this._markSourceChecked('allmusic', false);
            // The dialog hands focus back to "Search AllMusic", which has just
            // been replaced by its "checked" badge; never leave focus nowhere.
            setTimeout(() => {
                const a = document.activeElement;
                if (!a || a === document.body || a.hidden || a.closest('[hidden]')) this.$('p-find-btn')?.focus();
            }, 0);
        });
    },

    // ------------------------------------------------------------ status
    /** Visible status line beside Find credits; spoken when `speak`. */
    updateStatus: function(msg, type, speak) {
        const el = this.$('p-status');
        if (!el) return;
        el.textContent = msg;
        el.className = type === 'error' ? 'is-error' : (type === 'success' ? 'is-ok' : '');
        if (speak && msg) window.MFAnnounce?.(type === 'error' ? `Error: ${msg}` : msg);
    },

    toggleLoading: function(show, text) {
        const overlay = this.$('p-busy');
        if (!overlay) return;
        if (show && text) this.$('p-busy-text').textContent = text;
        overlay.hidden = !show;
        // The rest of the screen is inert while the search runs.
        this.$('p-left').inert = show;
        document.querySelector('.p-right').inert = show;
        if (show) window.MFAnnounce?.(text || 'Searching for credits');
    },

    _markSourceChecked: function(key, found) {
        const btn = this.$(`p-src-${key}-btn`);
        const badge = this.$(`p-src-${key}-check`);
        if (btn) {
            // Keep focus somewhere sensible if the button the user just used disappears.
            if (document.activeElement === btn) this.$('p-find-btn')?.focus();
            btn.hidden = true;
        }
        if (!badge) return;
        badge.hidden = false;
        const label = this._sourceLabels[key] || key;
        badge.className = 'p-badge ' + (found ? 'is-found' : 'is-none');
        badge.textContent = found ? '✓' : '–';
        badge.setAttribute('role', 'img');
        badge.setAttribute('aria-label', found ? `${label}: credits found` : `${label}: checked, nothing found`);
    },

    // A new album folder means none of the four sources has been checked yet.
    _resetSourceChecks: function() {
        ['mb', 'wiki', 'discogs', 'allmusic'].forEach(key => {
            const btn = this.$(`p-src-${key}-btn`);
            const badge = this.$(`p-src-${key}-check`);
            if (btn) btn.hidden = false;
            if (badge) {
                badge.hidden = true;
                badge.className = 'p-badge';
                badge.textContent = '';
                badge.removeAttribute('aria-label');
                badge.removeAttribute('role');
            }
        });
    },

    // ------------------------------------------------------------ album context
    ingestContext: function() {
        if (window.mf_context_artist) this.$('p-artist-input').value = window.mf_context_artist;
        if (window.mf_context_album) this.$('p-album-input').value = window.mf_context_album;
        if (window.mf_context_path) {
            this.$('p-local-path').value = window.mf_context_path;
            this.state.localPath = window.mf_context_path;
            this.getFolderContext(window.mf_context_path);
            window.mf_context_path = null;
        }
    },

    selectFolder: async function() {
        try {
            const response = await fetch('/select_folder');
            const data = await response.json();
            if (data && data.path) {
                this.state.localPath = data.path;
                this.$('p-local-path').value = data.path;
                await this.getFolderContext(data.path);
            }
        } catch (err) {
            console.error("Path selection failed:", err);
            this.updateStatus("The folder couldn't be opened.", "error", true);
        }
    },

    getFolderContext: async function(path) {
        if (!path) return;
        this._resetSourceChecks();
        this.$('p-handoff').hidden = true;
        try {
            const response = await fetch('/run_tool_logic/personnel/get_folder_context', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ local_path: path })
            });
            const data = await response.json();
            if (data.status === "success" && data.context) {
                this.$('p-artist-input').value = data.context.artist_seed || "";
                this.$('p-album-input').value = data.context.album_seed || "";
                this.$('p-year-input').value = data.context.release_year || "";
                this.updateStatus("Album details filled in from the manifest.", "success");
                this.resolveWaterfall();
            } else {
                // v2: shown, not swallowed (1.x left the screen sitting there).
                this.updateStatus(data.message || "The album details couldn't be read.", "error", true);
                this.$('p-artist-input').focus();
            }
        } catch (err) {
            this.updateStatus("The album details couldn't be read.", "error", true);
        }
    },

    // ------------------------------------------------------------ automatic search
    resolveWaterfall: async function() {
        const artist = this.$('p-artist-input').value.trim();
        const album = this.$('p-album-input').value.trim();
        if (!artist || !album) {
            this.updateStatus("Enter both Artist and Album to find credits.", "error", true);
            this.$(artist ? 'p-album-input' : 'p-artist-input').focus();
            return;
        }
        // The whole call can run long (a grounded AI web search may happen
        // inside it), and the backend can't report sub-stages, so the
        // message says what's POSSIBLE, not exactly what's running.
        this.toggleLoading(true, "Checking MusicBrainz and Discogs, with an AI web search if they come up thin. This can take a little while.");
        this.updateStatus("Searching for credits…", "");

        try {
            const res = await fetch('/run_tool_logic/personnel/resolve_waterfall', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ local_path: this.state.localPath, artist, album })
            });
            const data = await res.json();
            if (data.status === "success") {
                this.state.mapping = data.candidates || [];
                // Single source of truth for the manual-confirm value (John,
                // 2026-07-11): read from the backend, never a second copy here.
                this.state.manualConfirmConfidence = data.manual_confirm_confidence;
                this.renderMapping();
                // Per-source outcome from each credit's own provenance (John,
                // 2026-08-13), not one shared tick for the merged call.
                const mbCount = this.state.mapping.filter(c => c.provenance === 'MusicBrainz').length;
                const discogsCount = this.state.mapping.filter(c => c.provenance === 'Discogs').length;
                this._markSourceChecked('mb', mbCount > 0);
                this._markSourceChecked('discogs', discogsCount > 0);
                const n = this.state.mapping.length;
                if (n === 0) {
                    this.updateStatus("No credits found automatically. Try Search Wikipedia or Search AllMusic.", "error", true);
                } else if (data.thin) {
                    this.updateStatus(`${n} credit${n === 1 ? '' : 's'} found, still thin after the AI web search. Wikipedia or AllMusic may add more.`, "success", true);
                } else {
                    // Named from each row's real provenance (John, 2026-07-09:
                    // an all-AI result was once labelled "MusicBrainz + Discogs").
                    const sources = [...new Set(this.state.mapping.map(c => c.provenance))];
                    this.updateStatus(`${n} credit${n === 1 ? '' : 's'} found via ${sources.join(' + ')}.`, "success", true);
                }
            } else {
                this.updateStatus(data.message || "The automatic search failed. Try Wikipedia or AllMusic.", "error", true);
            }
        } catch (e) {
            console.error("Waterfall resolution failed:", e);
            this.updateStatus("The automatic search failed. Try Wikipedia or AllMusic.", "error", true);
        } finally {
            this.toggleLoading(false);
        }
    },

    // ------------------------------------------------------------ Wikipedia
    searchWikipedia: async function() {
        const artist = this.$('p-artist-input').value.trim();
        const album = this.$('p-album-input').value.trim();
        const year = this.$('p-year-input').value.trim();
        if (!artist || !album) {
            this.updateStatus("Enter both Artist and Album to search Wikipedia.", "error", true);
            return;
        }
        this.updateStatus("Searching Wikipedia…", "");
        const body = this.$('p-search-results-body');
        body.replaceChildren(this._noteRow("Searching Wikipedia…"));

        try {
            const res = await fetch('/run_tool_logic/personnel/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ artist, album, year })
            });
            const data = await res.json();
            // Badge only after a real completed response (never on a network
            // failure). "Found" here means candidate pages, which you review.
            const found = data.status === "success" && data.results.length > 0;
            this._markSourceChecked('wiki', found);
            if (found) {
                this.renderCandidates(data.results);
                this.updateStatus(`${data.results.length} Wikipedia page${data.results.length === 1 ? '' : 's'} found. Choose the album's page.`, "success", true);
            } else {
                body.replaceChildren(this._noteRow("No Wikipedia pages found."));
                this.updateStatus("No Wikipedia pages found.", "error", true);
            }
        } catch (e) {
            body.replaceChildren(this._noteRow("Wikipedia couldn't be reached."));
            this.updateStatus("Wikipedia couldn't be reached.", "error", true);
        }
    },

    _noteRow: function(text) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 2;
        td.className = 'p-note';
        td.textContent = text;
        tr.append(td);
        return tr;
    },

    renderCandidates: function(candidates) {
        const rows = candidates.map(c => {
            const tr = document.createElement('tr');
            const title = document.createElement('td');
            const score = document.createElement('span');
            score.className = 'p-wiki-score';
            score.textContent = ` (match ${c.score}%)`;
            title.append(document.createTextNode(c.title), score);
            const act = document.createElement('td');
            act.className = 'p-col-action';
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'mf-button-gold-fixed';
            btn.dataset.title = c.title;
            btn.textContent = 'Use';
            btn.setAttribute('aria-label', `Use the Wikipedia page ${c.title}`);
            act.append(btn);
            tr.append(title, act);
            return tr;
        });
        this.$('p-search-results-body').replaceChildren(...rows);
    },

    // Staging-level dedup (name + exact role), mirroring edge_store's key,
    // so a double-add never leaves a duplicated row to delete by hand.
    _mergeCandidates: function(existing, incoming) {
        const key = (name, role) => `${(name || '').trim().toLowerCase()}::${(role || '').trim().toLowerCase()}`;
        const seen = new Set(existing.map(p => key(p.name, p.role)));
        const merged = existing.slice();
        for (const c of (incoming || [])) {
            const k = key(c.name, c.role);
            if (seen.has(k)) continue;
            seen.add(k);
            merged.push(c);
        }
        return merged;
    },

    selectCandidate: async function(title) {
        this.updateStatus(`Reading credits from ${title}…`, "");
        try {
            const res = await fetch('/run_tool_logic/personnel/fetch_content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title })
            });
            const data = await res.json();
            if (data.status === "success") {
                // A manual Wikipedia pick ADDS to what the automatic search staged.
                const before = this.state.mapping.length;
                this.state.mapping = this._mergeCandidates(this.state.mapping, data.candidates);
                const added = this.state.mapping.length - before;
                this.renderMapping();
                this.updateStatus(added ? `${added} credit${added === 1 ? '' : 's'} added from Wikipedia.` : "Those credits were already in the list.", "success", true);
            } else {
                this.updateStatus(data.message || "The page's credits couldn't be read.", "error", true);
            }
        } catch (e) {
            this.updateStatus("The Wikipedia page couldn't be read.", "error", true);
        }
    },

    // ------------------------------------------------------------ the credits table
    /**
     * Rebuilds the credit rows. `refocus` = {idx, sel}: after a rebuild,
     * focus returns to that control in that row (or the nearest row), so
     * keyboard users never get thrown back to the top of the page.
     */
    renderMapping: function(refocus) {
        const body = this.$('p-mapping-body');
        const rows = this.state.mapping.map((row, idx) => this._mappingRow(row, idx));
        body.replaceChildren(...rows);

        const n = this.state.mapping.length;
        this.$('p-mapping-count').textContent = `${n} credit${n === 1 ? '' : 's'} ready to save`;
        this.$('p-commit-btn').disabled = n === 0;

        if (refocus && n) {
            const i = Math.min(refocus.idx, n - 1);
            body.querySelector(`tr[data-idx="${i}"] ${refocus.sel}`)?.focus();
        } else if (refocus) {
            this.$('p-add-btn').focus();
        }
    },

    _mappingRow: function(row, idx) {
        const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
        const tr = el('tr');
        tr.dataset.idx = String(idx);
        const label = (row.name || 'unnamed').trim() || 'unnamed';

        const nameTd = el('td');
        const name = el('input', 'p-cell-input p-map-name');
        name.type = 'text';
        name.value = row.name || '';
        name.setAttribute('aria-label', `Name, credit ${idx + 1}`);
        nameTd.append(name);

        const roleTd = el('td');
        const role = el('input', 'p-cell-input p-map-role');
        role.type = 'text';
        role.value = row.role || '';
        role.setAttribute('aria-label', `Role, credit ${idx + 1}`);
        roleTd.append(role);

        // Where the credit came from, and (for AI web-search rows) the
        // confirmed/inferred control and the "verify the source" window.
        const meta = el('div', 'p-meta');
        const isAiTier = row.ai_confirmed !== null && row.ai_confirmed !== undefined;
        if (isAiTier) {
            const sel = el('select', 'p-map-status');
            sel.setAttribute('aria-label', `Confidence for ${label}`);
            sel.append(new Option('Confirmed', 'confirmed', false, !!row.ai_confirmed),
                       new Option('Inferred', 'inferred', false, !row.ai_confirmed));
            meta.append(sel);
            if (Array.isArray(row.candidate_urls) && row.candidate_urls.length) {
                const v = el('button', 'mf-button-gold-fixed p-verify', `Verify source${row.candidate_urls.length > 1 ? 's' : ''}`);
                v.type = 'button';
                v.setAttribute('aria-label', `Verify the source${row.candidate_urls.length > 1 ? 's' : ''} for ${label}`);
                meta.append(v);
            }
        }
        const scope = row.evidence_scope === 'track' && row.evidence_detail ? `Track ${row.evidence_detail}`
                    : (row.evidence_scope === 'album' ? 'Album-wide' : '');
        const tier = row.verification_tier ? `Verified: ${row.verification_tier.charAt(0).toUpperCase()}${row.verification_tier.slice(1)}` : '';
        const facts = [row.provenance || 'MetaForge (Manual)',
                       row.confidence !== undefined ? `confidence ${row.confidence}` : '', scope, tier].filter(Boolean).join(' · ');
        meta.append(el('span', '', facts));
        roleTd.append(meta);

        const rmTd = el('td', 'p-col-remove');
        const rm = el('button', 'p-remove');
        rm.type = 'button';
        rm.setAttribute('aria-label', `Remove ${label}${row.role ? ', ' + row.role : ''}`);
        rm.append(Object.assign(el('span', '', '✕'), { ariaHidden: 'true' }));
        rmTd.append(rm);

        tr.append(nameTd, roleTd, rmTd);
        return tr;
    },

    updateMappingField: function(idx, field, value) {
        const row = this.state.mapping[idx];
        if (!row) return;
        row[field] = value;
        // Keep the remove button's name in step with what's typed.
        const tr = this.$('p-mapping-body').querySelector(`tr[data-idx="${idx}"]`);
        const rm = tr?.querySelector('.p-remove');
        if (rm) rm.setAttribute('aria-label', `Remove ${(row.name || 'unnamed').trim() || 'unnamed'}${row.role ? ', ' + row.role : ''}`);
    },

    updateConfidenceStatus: function(idx, value) {
        // Manual override of an AI web-search row (John, 2026-07-10/11).
        // Confirmed = the backend's MANUAL_CONFIRM_CONFIDENCE (never a
        // duplicated constant) + provenance "Submitter Confirmed"; Inferred
        // = the AI's own inferred confidence + provenance "AI Web Search".
        // Either way manually_reviewed = true.
        const row = this.state.mapping[idx];
        if (!row) return;
        const confirmed = value === 'confirmed';
        row.ai_confirmed = confirmed;
        row.manually_reviewed = true;
        if (confirmed) {
            const target = this.state.manualConfirmConfidence;
            row.confidence = (target !== undefined && target !== null) ? target : row.confirmed_confidence;
            row.provenance = "Submitter Confirmed";
        } else {
            if (row.inferred_confidence !== undefined && row.inferred_confidence !== null) row.confidence = row.inferred_confidence;
            row.provenance = "AI Web Search";
        }
        this.renderMapping({ idx, sel: '.p-map-status' });
    },

    // "Verify the source" companion window (John, 2026-07-11): one session
    // at a time; pendingVerifyIdx is the row the result applies to.
    verifySource: async function(idx) {
        const row = this.state.mapping[idx];
        if (!row || !Array.isArray(row.candidate_urls) || row.candidate_urls.length === 0) return;
        this.state.pendingVerifyIdx = idx;
        try {
            await fetch('/open_verify_window', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ urls: row.candidate_urls, title: `Verify: ${row.name} — ${row.role}` })
            });
        } catch (e) {
            console.error("Failed to open verify window:", e);
            this.updateStatus("The verify window couldn't be opened.", "error", true);
        }
    },

    // Called by ui/app.py's VerifyWindowAPI._finish() via evaluate_js. A
    // discarded session deliberately leaves the row exactly as it was.
    onVerifyModalResult: function(result) {
        const idx = this.state.pendingVerifyIdx;
        this.state.pendingVerifyIdx = null;
        if (idx === null || idx === undefined || !this.state.mapping[idx]) return;
        const row = this.state.mapping[idx];
        if (!result || result.discarded) {
            this.updateStatus("No source confirmed this credit, so it was left unchanged.", "success", true);
            return;
        }
        row.ai_confirmed = true;
        row.manually_reviewed = true;
        row.verification_tier = result.verification_tier;
        row.confidence = result.confidence;
        row.provenance = "Submitter Confirmed";
        // The RESOLVED page URL from inside the verify window (John,
        // 2026-07-13), citable to MusicBrainz unlike the raw grounding link.
        row.verified_source_url = result.source_url || null;
        this.renderMapping({ idx, sel: '.p-verify, .p-map-status' });
        this.updateStatus(`Verified as "${result.verification_tier}"; confidence updated.`, "success", true);
    },

    addManualRow: function() {
        this.state.mapping.push({ name: "", role: "", provenance: "MetaForge (Manual)" });
        this.renderMapping({ idx: this.state.mapping.length - 1, sel: '.p-map-name' });
    },

    removeRow: function(idx) {
        const row = this.state.mapping[idx];
        this.state.mapping.splice(idx, 1);
        this.renderMapping({ idx, sel: '.p-remove' });
        window.MFAnnounce?.(`Removed ${(row?.name || 'the credit').trim() || 'the credit'}.`);
    },

    sortMapping: function(key) {
        // Same column flips direction; a different column starts ascending
        // (John, 2026-07-16).
        if (this.state.sortKey === key) this.state.sortDir *= -1;
        else { this.state.sortKey = key; this.state.sortDir = 1; }
        const dir = this.state.sortDir;
        this.state.mapping.sort((a, b) => {
            const A = (a[key] || '').toLowerCase(), B = (b[key] || '').toLowerCase();
            return A < B ? -dir : (A > B ? dir : 0);
        });
        this.renderMapping();
        ['name', 'role'].forEach(k => {
            this.$(`p-th-${k}`).setAttribute('aria-sort', k === key ? (dir === 1 ? 'ascending' : 'descending') : 'none');
        });
        window.MFAnnounce?.(`Sorted by ${key}, ${dir === 1 ? 'A to Z' : 'Z to A'}.`);
    },

    // ------------------------------------------------------------ AllMusic (last resort)
    checkAllMusic: function() {
        const artist = this.$('p-artist-input').value.trim();
        const album = this.$('p-album-input').value.trim();
        const query = encodeURIComponent(`${artist} ${album}`.trim());
        // Just a URL for a companion window, the same as typing into
        // AllMusic's own search; MetaForge never fetches AllMusic itself.
        window.open(`https://www.allmusic.com/search/albums/${query}`, 'metaforge_allmusic_lookup');
        const dlg = this.$('p-allmusic-dialog');
        this.$('p-allmusic-paste').textContent = '';
        dlg.returnValue = '';
        dlg.showModal();
        this.$('p-allmusic-paste').focus();
    },

    handleAllMusicPaste: async function(event) {
        event.preventDefault();
        // text/html normally carries the real markup; from a "View Selection
        // Source" page the literal source is in text/plain instead (John,
        // 2026-07-08). Both are sent; the server tries both.
        const html = event.clipboardData?.getData('text/html') || '';
        const plain = event.clipboardData?.getData('text/plain') || '';
        const target = this.$('p-allmusic-paste');
        if (!html && !plain) {
            target.textContent = "The clipboard was empty. Copy the credits table again.";
            return;
        }
        target.textContent = `Captured ${(html || plain).length} characters. Reading the credits…`;
        try {
            const res = await fetch('/run_tool_logic/personnel/parse_allmusic_html', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ html, plain })
            });
            const data = await res.json();
            const found = data.status === "success" && data.candidates.length > 0;
            const dlg = this.$('p-allmusic-dialog');
            if (found) {
                this._markSourceChecked('allmusic', true);
                const before = this.state.mapping.length;
                this.state.mapping = this._mergeCandidates(this.state.mapping, data.candidates);
                const added = this.state.mapping.length - before;
                this.renderMapping();
                dlg.close('found');
                this.updateStatus(added ? `${added} credit${added === 1 ? '' : 's'} added from AllMusic.` : "Those credits were already in the list.", "success", true);
            } else {
                // Checked, nothing usable: say so in the dialog, then close
                // it (the close handler marks AllMusic as checked).
                const msg = data.message || "No credits were found in what was pasted.";
                target.textContent = msg;
                this.updateStatus(msg, "error", true);
                dlg.close('none');
            }
        } catch (e) {
            // A real failure stays open so the paste can be retried.
            target.textContent = "The pasted credits couldn't be read. Copy the table and paste again.";
            this.updateStatus("The pasted AllMusic credits couldn't be read.", "error", true);
        }
    },

    // ------------------------------------------------------------ save
    commitToDatabase: async function() {
        if (this.state.isLocked) return;
        // From state (kept in step on every edit), not re-scraped from the
        // DOM: MB/Discogs rows carry metadata that only exists in state.
        const personnelData = this.state.mapping.filter(p => p.name && p.role);
        if (personnelData.length === 0) {
            this.updateStatus("Nothing to save yet: every credit needs a name and a role.", "error", true);
            return;
        }
        const artist = this.$('p-artist-input').value;
        const album = this.$('p-album-input').value;
        this.state.isLocked = true;
        const btn = this.$('p-commit-btn');
        btn.disabled = true;
        this.$('p-handoff').hidden = true;
        this.updateStatus("Saving to the database…", "");

        try {
            const res = await fetch('/run_tool_logic/personnel/commit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ artist, album, personnel: personnelData })
            });
            const data = await res.json();
            if (data.status === "success") {
                this.updateStatus(`Saved ${data.count} credit${data.count === 1 ? '' : 's'} for ${artist} / ${album}.`, "success", true);
                if (!data.has_bio) this.showHandoff(artist);
            } else if (data.status === "partial") {
                const names = (data.failed || []).map(f => f.role ? `${f.name} (${f.role})` : f.name).join(', ');
                this.updateStatus(`Saved ${data.count}, but ${data.failed.length} couldn't be saved: ${names}. Try saving again.`, "error", true);
            } else {
                this.updateStatus(data.message || "Nothing was saved.", "error", true);
            }
        } catch (e) {
            console.error("MetaForge Commit Error:", e);
            this.updateStatus(`Nothing was saved: ${e.message}`, "error", true);
        } finally {
            this.state.isLocked = false;
            btn.disabled = this.state.mapping.length === 0;
        }
    },

    /** Bio Builder, offered only when the artist has no bio yet (John). */
    showHandoff: function(artist) {
        this.$('p-next-artist').textContent = artist || 'This artist';
        this.$('p-handoff').hidden = false;
        this.$('p-bio-btn').focus();
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.metaforge.personnel.init());
} else {
    window.metaforge.personnel.init();
}
/* --- END OF FILE personnel.js --- */
