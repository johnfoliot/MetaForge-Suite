/* --- START OF FILE personnel.js --- */
/**
 * MetaForge Studio: Personnel Scout Logic Bridge (Personnel Engine v2)
 * Role: Orchestrates the MB+Discogs automatic waterfall, Wikipedia
 * search/fallback, AllMusic paste-modal, and the shared mapping/commit UI.
 * Physical Location: \tools\personnel\personnel.js
 */

window.metaforge = window.metaforge || {};
window.metaforge.personnel = {
    state: {
        localPath: "",
        mapping: [],
        isLocked: false,
        pendingVerifyIdx: null
    },

    init: function() {
        setTimeout(() => {
            const h1 = document.querySelector('h1.main');
            if (h1) h1.focus();
            this.ingestContext();
        }, 50);
    },

    // Same pattern as tools/biography/biography.js's toggleLoading()
    // (John, 2026-07-09) -- reused deliberately. `text` lets the overlay
    // say what's actually happening instead of a fixed generic message,
    // since the automatic waterfall can be doing genuinely different
    // things (MB+Discogs lookup vs. an AI grounded search) at different
    // points, and the small status-bar text alone read as a hang, not
    // progress.
    toggleLoading: function(show, text) {
        const overlay = document.getElementById('p-loading-overlay');
        if (!overlay) return;
        if (show && text) {
            const label = document.getElementById('p-loading-text');
            if (label) label.innerText = text;
        }
        overlay.style.display = show ? 'flex' : 'none';
    },

    ingestContext: function() {
        const artist = document.getElementById('p-artist-input');
        const album = document.getElementById('p-album-input');
        const pathInput = document.getElementById('p-local-path');

        if (window.mf_context_artist) artist.value = window.mf_context_artist;
        if (window.mf_context_album) album.value = window.mf_context_album;
        if (window.mf_context_path) {
            pathInput.value = window.mf_context_path;
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
                const pathInput = document.getElementById('p-local-path');
                if (pathInput) pathInput.value = data.path;
                await this.getFolderContext(data.path);
            }
        } catch (err) {
            console.error("Path selection failed:", err);
            this.updateStatus("File selection failed.", "error");
        }
    },

    getFolderContext: async function(path) {
        if (!path) return;
        try {
            const response = await fetch('/run_tool_logic/personnel/get_folder_context', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ local_path: path })
            });
            const data = await response.json();
            if (data.status === "success" && data.context) {
                document.getElementById('p-artist-input').value = data.context.artist_seed || "";
                document.getElementById('p-album-input').value = data.context.album_seed || "";
                document.getElementById('p-year-input').value = data.context.release_year || "";
                this.updateStatus("Directory context loaded from manifest.", "success");
                // Automatic Tier 1+2 (MB+Discogs merged, falling back to
                // Wikipedia if thin) -- no click required, mirrors the
                // "Optional: Add Personnel" hand-off already being
                // automatic up to this point.
                this.resolveWaterfall();
            }
        } catch (err) {
            console.warn("Manifest discovery failed.");
        }
    },

    resolveWaterfall: async function() {
        const artist = document.getElementById('p-artist-input').value.trim();
        const album = document.getElementById('p-album-input').value.trim();
        if (!artist || !album) return;

        // The overlay is the primary "something is happening" signal now
        // (John, 2026-07-09 -- the status bar text alone was easy to miss
        // and this whole call can run long, since a real AI grounded
        // search may happen inside it). The single backend call can't
        // report its own sub-stage progress, so the message says what's
        // POSSIBLE, not a false promise of exactly what's running.
        this.toggleLoading(true, "Checking MusicBrainz + Discogs, falling back to an AI web search if thin. Please stand-by, this can take a little while...");
        this.updateStatus("Resolving personnel via MusicBrainz + Discogs...", "success");

        try {
            const res = await fetch('/run_tool_logic/personnel/resolve_waterfall', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ local_path: this.state.localPath, artist, album })
            });
            const data = await res.json();
            if (data.status === "success") {
                this.state.mapping = data.candidates || [];
                // Single source of truth for the manual-confirm target
                // value (John, 2026-07-11) -- read once from the backend
                // rather than hardcoding a second copy of
                // MANUAL_CONFIRM_CONFIDENCE here that could drift.
                this.state.manualConfirmConfidence = data.manual_confirm_confidence;
                this.renderMapping();
                if (this.state.mapping.length === 0) {
                    this.updateStatus("No automatic matches found -- try Wikipedia search or Check AllMusic below.", "error");
                } else if (data.thin) {
                    this.updateStatus(`${this.state.mapping.length} credits found (still thin even after AI Web Search). Consider Wikipedia search or AllMusic if incomplete.`, "success");
                } else {
                    // Built from each row's own provenance rather than a
                    // hardcoded "via MusicBrainz + Discogs" (John, 2026-07-09
                    // -- caught live: a result that was 100% AI Web Search
                    // still got labeled as MB+Discogs, since that message
                    // never actually checked which tier(s) contributed).
                    const sourcesUsed = [...new Set(this.state.mapping.map(c => c.provenance))];
                    this.updateStatus(`${this.state.mapping.length} credits found via ${sourcesUsed.join(' + ')}.`, "success");
                }
            }
        } catch (e) {
            console.error("Waterfall resolution failed:", e);
            this.updateStatus("Automatic resolution failed -- try manual search below.", "error");
        } finally {
            this.toggleLoading(false);
        }
    },

    searchWikipedia: async function() {
        const artist = document.getElementById('p-artist-input').value.trim();
        const album = document.getElementById('p-album-input').value.trim();
        const year = document.getElementById('p-year-input').value.trim();

        if (!artist || !album) {
            this.updateStatus("⚠️ Artist and Album name required.", "error");
            return;
        }

        this.updateStatus("Scouting Wikipedia candidates...", "success");
        const resultsBody = document.getElementById('p-search-results-body');
        resultsBody.innerHTML = '<tr><td colspan="2" style="padding:10px; text-align:center;">Searching Wikipedia...</td></tr>';

        try {
            const res = await fetch('/run_tool_logic/personnel/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ artist, album, year })
            });
            const data = await res.json();
            if (data.status === "success" && data.results.length > 0) {
                this.renderCandidates(data.results);
                this.updateStatus(`Identified ${data.results.length} relevance matches.`, "success");
            } else {
                // Previously left the status bar stuck on "Scouting
                // Wikipedia candidates..." forever when the search
                // completed with zero results -- looked identical to a
                // hang even though the request had actually finished
                // (John, 2026-07-08).
                resultsBody.innerHTML = '<tr><td colspan="2" style="padding:10px; text-align:center;">No matches found.</td></tr>';
                this.updateStatus("No Wikipedia matches found.", "error");
            }
        } catch (e) {
            this.updateStatus("Network Error: Wikipedia API unreachable.", "error");
        }
    },

    renderCandidates: function(candidates) {
        const body = document.getElementById('p-search-results-body');
        body.innerHTML = candidates.map(c => `
            <tr style="border-bottom: 1px solid var(--bg-main);">
                <td style="padding:6px; color: var(--text-output);">${c.title} <span style="font-size:0.65rem; opacity:0.5;">(Rel: ${c.score}%)</span></td>
                <td style="padding:6px; text-align:right;">
                    <button class="mf-button-gold-fixed" style="font-size:0.65rem; padding: 2px 8px;"
                            onclick="window.metaforge.personnel.selectCandidate('${c.title}')">Select</button>
                </td>
            </tr>
        `).join('');
    },

    // Staging-level dedup: mirrors edge_store.find_matching_edge's key
    // (name + exact role text) but purely in-memory, before anything ever
    // reaches the database. Commit-time dedup already makes a double-add
    // harmless in the DB (John, 2026-07-08), but leaving a visibly
    // duplicated row in the review table is still confusing clutter he'd
    // have to notice and delete by hand -- this stops it from landing
    // there in the first place, at any concat site (Wikipedia extraction,
    // AllMusic paste), not just the one that got clicked twice.
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
        // The raw-wikitext debug panel was removed from the UI (John,
        // 2026-07-09 -- clutter for a feature that's now a rare manual
        // fallback, not the primary tool). data.raw_text is still
        // returned by the backend and simply unused here -- cheap to
        // leave available server-side in case it's ever wanted again,
        // no reason to touch that response shape for a pure UI removal.
        this.updateStatus(`Extracting from: ${title}...`, "success");
        try {
            const res = await fetch('/run_tool_logic/personnel/fetch_content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: title })
            });
            const data = await res.json();
            if (data.status === "success") {
                // A manual Wikipedia search ADDS to whatever the automatic
                // waterfall already staged, rather than replacing it --
                // MB/Discogs edges already found stay put. Candidates
                // arrive already junk-filtered and classified.
                this.state.mapping = this._mergeCandidates(this.state.mapping, data.candidates);
                this.renderMapping();
                this.updateStatus("Extraction complete. Map identities on right.", "success");
            } else {
                this.updateStatus(data.message || "Extraction failed.", "error");
            }
        } catch (e) {
            this.updateStatus("Error: Failed to retrieve page content.", "error");
        }
    },

    renderMapping: function() {
        const body = document.getElementById('p-mapping-body');
        const countLabel = document.getElementById('p-mapping-count');
        const commitBtn = document.getElementById('p-commit-btn');
        body.innerHTML = '';

        this.state.mapping.forEach((row, idx) => {
            const tr = document.createElement('tr');
            tr.style.borderBottom = "1px solid #444";
            const provenance = row.provenance || 'MetaForge (Manual)';
            // Track scope was already reaching this row object (every
            // source sets evidence_scope/evidence_detail server-side --
            // the AI Web Search tier's 2026-07-10 rebuild in particular
            // depends on this being visible for review, not just present
            // in the data) but was never actually rendered -- John caught
            // this live, testing the new confirmed/inferred prompt.
            const scopeLabel = row.evidence_scope === 'track' && row.evidence_detail
                ? `Track ${row.evidence_detail}`
                : (row.evidence_scope === 'album' ? 'Album-wide' : '');
            // Manual override control (John, 2026-07-10): only rendered
            // for genuine AI Web Search rows -- ai_confirmed is null for
            // MB/Discogs/Wikipedia, where the confirmed/inferred
            // distinction doesn't apply at all, not just "unset". Lets a
            // reviewer who independently checks an [inferred] credit
            // (his own example: spot-verifying the Clancy Eccles house
            // band roster) upgrade it BEFORE committing, instead of only
            // ever accepting whatever the AI tier assigned.
            const isAiTier = row.ai_confirmed !== null && row.ai_confirmed !== undefined;
            const nameForLabel = (row.name || '').replace(/"/g, '&quot;');
            const statusControl = isAiTier
                ? `<select class="p-map-status" aria-label="Confidence status for ${nameForLabel}"
                           style="font-size:0.6rem; background:var(--bg-main); color:var(--text-output); border:1px solid var(--bg-accent); margin-right:4px; vertical-align:middle;"
                           onchange="window.metaforge.personnel.updateConfidenceStatus(${idx}, this.value)">
                       <option value="confirmed" ${row.ai_confirmed ? 'selected' : ''}>Confirmed</option>
                       <option value="inferred" ${row.ai_confirmed ? '' : 'selected'}>Inferred</option>
                   </select>`
                : '';
            // "Click to verify" trigger (John, 2026-07-11): only rendered
            // when the AI tier actually surfaced source links for this
            // credit (candidate_urls -- see ai_engine.py's
            // _credit_candidate_uris, capped at 3, ephemeral/never
            // persisted). Distinct from the Confirmed/Inferred select
            // above: that's a quick self-assessed toggle, this opens a
            // live companion window so a human can look at the actual
            // source and record their OWN judgment (see
            // project_mb_contribution_tool memory for why Gemini's
            // grounding terms require that human-in-the-loop step).
            const hasVerifyLinks = isAiTier && Array.isArray(row.candidate_urls) && row.candidate_urls.length > 0;
            const verifyControl = hasVerifyLinks
                ? `<button class="mf-button-gold-fixed" style="font-size:0.6rem; padding:1px 6px; margin-right:4px; vertical-align:middle;"
                           onclick="window.metaforge.personnel.verifySource(${idx})">Verify Source${row.candidate_urls.length > 1 ? 's' : ''}</button>`
                : '';
            const tierLabel = row.verification_tier
                ? ` · Verified: ${row.verification_tier.charAt(0).toUpperCase()}${row.verification_tier.slice(1)}`
                : '';
            const meta = row.confidence !== undefined
                ? `${statusControl}${verifyControl}${provenance} · conf ${row.confidence}${scopeLabel ? ' · ' + scopeLabel : ''}${tierLabel}`
                : `${statusControl}${verifyControl}${provenance}`;
            tr.innerHTML = `
                <td style="padding:4px;"><input type="text" class="mb-input-text p-map-name" value="${(row.name || '').replace(/"/g, '&quot;')}" style="width:100%; border:none; background:transparent; color:var(--text-output);" oninput="window.metaforge.personnel.updateMappingField(${idx}, 'name', this.value)"></td>
                <td style="padding:4px;">
                    <input type="text" class="mb-input-text p-map-role" value="${(row.role || '').replace(/"/g, '&quot;')}" style="width:100%; border:none; background:transparent; color:var(--text-output);" oninput="window.metaforge.personnel.updateMappingField(${idx}, 'role', this.value)">
                    <span style="display:block; font-size:0.6rem; opacity:0.6; margin-top:2px;">${meta}</span>
                </td>
                <td style="padding:4px; text-align:center;">
                    <button class="mf-button-gold-fixed" style="background:var(--status-error)!important; font-size:0.6rem; padding: 2px 6px; color:#fff!important;"
                            onclick="window.metaforge.personnel.removeRow(${idx})" aria-label="Remove Row">X</button>
                </td>
            `;
            body.appendChild(tr);
        });

        countLabel.innerText = `${this.state.mapping.length} Rows Staged`;
        commitBtn.disabled = this.state.mapping.length === 0;
        commitBtn.style.opacity = this.state.mapping.length > 0 ? "1" : "0.5";
    },

    updateMappingField: function(idx, field, value) {
        if (this.state.mapping[idx]) this.state.mapping[idx][field] = value;
    },

    updateConfidenceStatus: function(idx, value) {
        // Manual override for an AI Web Search row's confirmed/inferred
        // status (John, 2026-07-10, fixed 2026-07-11). A CONFIRMED toggle
        // no longer switches to confirmed_confidence -- that number is
        // classify_role()'s role-TEXT classification confidence, not a
        // fact-verification confidence, so a generic role like "Backing
        // Band" capped out at 0.5 even after a human personally checked
        // it (real bug, caught live). A human confirmation now sets the
        // fixed MANUAL_CONFIRM_CONFIDENCE value (read from the backend as
        // state.manualConfirmConfidence, not duplicated here) and marks
        // provenance as "Submitter Confirmed" so the DB/evidence log can
        // tell "the AI said this, unverified" apart from "a human
        // verified this." An INFERRED toggle reverts provenance to "AI
        // Web Search" (every AI-tier row starts there; this control only
        // ever renders for AI-tier rows) and uses the AI's own
        // inferred_confidence, unchanged. Either direction sets
        // manually_reviewed=true -- even reverting to inferred means a
        // human looked at it and agreed, worth keeping distinct from
        // "never reviewed at all."
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
            if (row.inferred_confidence !== undefined && row.inferred_confidence !== null) {
                row.confidence = row.inferred_confidence;
            }
            row.provenance = "AI Web Search";
        }
        this.renderMapping();
    },

    // Opens the live "click to verify" companion window for one AI-tier
    // credit's candidate sources (John, 2026-07-11). Only one verify
    // session is ever open at a time -- pendingVerifyIdx just tracks
    // which mapping row the eventual result applies to, same
    // single-companion-window assumption MB Submit's pseudo-tab already
    // makes.
    verifySource: async function(idx) {
        const row = this.state.mapping[idx];
        if (!row || !Array.isArray(row.candidate_urls) || row.candidate_urls.length === 0) return;
        this.state.pendingVerifyIdx = idx;
        try {
            await fetch('/open_verify_window', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    urls: row.candidate_urls,
                    title: `Verify: ${row.name} — ${row.role}`
                })
            });
        } catch (e) {
            console.error("Failed to open verify window:", e);
            this.updateStatus("Could not open the verify window.", "error");
        }
    },

    // Called by ui/app.py's VerifyWindowAPI._finish() via evaluate_js once
    // the human either submits a real verdict or every source resolved
    // False (discarded). result.discarded means "leave this row exactly
    // as it was" -- per John's design, closing/discarding the verify
    // session is a deliberate no-op, never an implicit downgrade.
    onVerifyModalResult: function(result) {
        const idx = this.state.pendingVerifyIdx;
        this.state.pendingVerifyIdx = null;
        if (idx === null || idx === undefined || !this.state.mapping[idx]) return;
        const row = this.state.mapping[idx];

        if (!result || result.discarded) {
            this.updateStatus("No source confirmed this credit -- left unchanged.", "success");
            return;
        }

        row.ai_confirmed = true;
        row.manually_reviewed = true;
        row.verification_tier = result.verification_tier;
        row.confidence = result.confidence;
        row.provenance = "Submitter Confirmed";
        // The RESOLVED destination page's own URL (John, 2026-07-13) --
        // captured via window.location.href inside the verify window
        // itself, after a real human-driven page load, not Gemini's
        // opaque grounding-chunk redirect link. See
        // project_mb_contribution_tool memory for why that distinction
        // makes this citable to MusicBrainz where the raw grounding URL
        // wasn't.
        row.verified_source_url = result.source_url || null;
        this.renderMapping();
        this.updateStatus(`Verified as "${result.verification_tier}" -- confidence updated.`, "success");
    },

    addManualRow: function() {
        this.state.mapping.push({ name: "", role: "", provenance: "MetaForge (Manual)" });
        this.renderMapping();
        const names = document.querySelectorAll('.p-map-name');
        if (names.length > 0) names[names.length - 1].focus();
    },

    removeRow: function(idx) {
        this.state.mapping.splice(idx, 1);
        this.renderMapping();
    },

	sortMapping: function(key) {
        // Toggle sort (ascending/descending) -- re-clicking the SAME
        // column flips direction, clicking a DIFFERENT column starts
        // fresh ascending (John, 2026-07-16, added Role as a sortable
        // column alongside the existing Name one: without tracking which
        // column the current direction belongs to, switching from Name
        // to Role would carry over whatever direction Name was left on
        // instead of starting predictably).
        if (this.state.sortKey === key) {
            this.state.sortDir = (this.state.sortDir || 1) * -1;
        } else {
            this.state.sortKey = key;
            this.state.sortDir = 1;
        }

        this.state.mapping.sort((a, b) => {
            const valA = (a[key] || '').toLowerCase();
            const valB = (b[key] || '').toLowerCase();
            if (valA < valB) return -1 * this.state.sortDir;
            if (valA > valB) return 1 * this.state.sortDir;
            return 0;
        });

        this.renderMapping();
    },

    // ======================================================
    // TIER 4: ALLMUSIC (semi-manual, true last resort)
    // ======================================================

    checkAllMusic: function() {
        const artist = document.getElementById('p-artist-input').value.trim();
        const album = document.getElementById('p-album-input').value.trim();
        const query = encodeURIComponent(`${artist} ${album}`.trim());
        // Just constructing a URL for the user's own browser to open --
        // no different from typing it into AllMusic's search box by hand.
        // Named target so repeated lookups across albums reuse one
        // companion tab instead of piling up a new one each time.
        window.open(`https://www.allmusic.com/search/albums/${query}`, 'metaforge_allmusic_lookup');
        this.openAllMusicModal();
    },

    openAllMusicModal: function() {
        const existing = document.getElementById('p-allmusic-modal');
        if (existing) { existing.style.display = 'flex'; return; }

        const modal = document.createElement('div');
        modal.id = 'p-allmusic-modal';
        modal.style = "position:fixed; top:20%; left:30%; width:40%; background:var(--bg-main); border:1px solid var(--mf-gold); padding:20px; z-index:10000; display:flex; flex-direction:column; gap:10px;";
        modal.innerHTML = `
            <h3 style="color:var(--mf-gold); margin:0;">Paste AllMusic Credits</h3>
            <p class="tool_notes" style="margin:0; font-size:0.75rem;">On the AllMusic tab: find the album, scroll to Credits, select the credits table, and copy (Ctrl+C). Then click the box below and paste (Ctrl+V).</p>
            <div id="p-allmusic-paste-target" contenteditable="true" role="textbox" aria-label="Paste AllMusic credits table here"
                 style="min-height:100px; border:1px solid #444; background:var(--input-background2); color:var(--input-foreground2); padding:8px; overflow-y:auto; max-height:150px;"
                 onpaste="window.metaforge.personnel.handleAllMusicPaste(event)"></div>
            <div style="display:flex; gap:10px; justify-content:flex-end;">
                <button class="mf-button-gold-fixed" style="background:transparent!important; border:1px solid var(--mf-gold); color:var(--mf-gold)!important;" onclick="document.getElementById('p-allmusic-modal').remove()">Close</button>
            </div>
        `;
        document.body.appendChild(modal);
        document.getElementById('p-allmusic-paste-target').focus();
    },

    handleAllMusicPaste: async function(event) {
        event.preventDefault();
        // A normal Ctrl+C on rendered page text puts both text/html and
        // text/plain on the clipboard, and text/html normally carries the
        // real markup. But copying from a "View Selection Source" page
        // (John, 2026-07-08) is a different case: that page displays
        // markup AS TEXT, so its own text/html is the browser's syntax-
        // highlighting wrapper around that display, not the original
        // page's markup -- the literal source text you actually want is
        // in text/plain instead for that path. Sending both and trying
        // both server-side (see _parse_allmusic_html) covers both cases
        // without needing to know in advance which one the user did.
        const html = (event.clipboardData && event.clipboardData.getData('text/html')) || '';
        const plain = (event.clipboardData && event.clipboardData.getData('text/plain')) || '';
        if (!html && !plain) {
            this.updateStatus("Clipboard was empty -- try copying the table again.", "error");
            return;
        }

        // Visible confirmation that something was actually captured --
        // the paste target intentionally never shows the pasted content
        // itself (preventDefault blocks that), which John noted looked
        // like nothing had happened at all.
        const target = document.getElementById('p-allmusic-paste-target');
        if (target) target.innerText = `Captured ${(html || plain).length} characters -- parsing...`;

        this.updateStatus("Parsing pasted AllMusic content...", "success");
        try {
            const res = await fetch('/run_tool_logic/personnel/parse_allmusic_html', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ html, plain })
            });
            const data = await res.json();
            if (data.status === "success" && data.candidates.length > 0) {
                // Candidates arrive already junk-filtered and classified
                // (relation_type/confidence/evidence_scope/evidence_detail
                // included) -- carry all of it through, not just name/role,
                // so these commit the same way MB/Discogs results do.
                const before = this.state.mapping.length;
                this.state.mapping = this._mergeCandidates(this.state.mapping, data.candidates);
                const added = this.state.mapping.length - before;
                this.renderMapping();
                this.updateStatus(added > 0 ? `Added ${added} credits from AllMusic.` : "Those credits are already staged -- nothing new to add.", "success");
                const modal = document.getElementById('p-allmusic-modal');
                if (modal) modal.remove();
            } else {
                // The outcome must land inside the still-open modal, not just
                // the page's status bar underneath it -- John flagged (2026-07-08)
                // that a sighted user has to notice text behind an open modal,
                // and a screen reader focused in the modal's DOM never reaches
                // it at all. Same reasoning applies to the catch block below.
                const msg = data.message || "No credits found in pasted content.";
                if (target) target.innerText = msg;
                this.updateStatus(msg, "error");
            }
        } catch (e) {
            if (target) target.innerText = "AllMusic parse failed -- try copying the table again.";
            this.updateStatus("AllMusic parse failed.", "error");
        }
    },

    // ======================================================
    // COMMIT (shared by every tier)
    // ======================================================

    commitToDatabase: async function() {
        if (this.state.isLocked) return;

        // Reads from state (kept in sync via updateMappingField on every
        // edit), not re-scraped from the DOM -- MB/Discogs rows carry
        // relation_type/confidence/evidence_scope metadata that only
        // exists in state, not in the visible inputs.
        const personnelData = this.state.mapping.filter(p => p.name && p.role);

        if (personnelData.length === 0) {
            alert("Commit Error: No mappings staged for commit.");
            return;
        }

        this.state.isLocked = true;
        this.updateStatus("Transmitting to Database...", "success");

        try {
            const res = await fetch('/run_tool_logic/personnel/commit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    artist: document.getElementById('p-artist-input').value,
                    album: document.getElementById('p-album-input').value,
                    personnel: personnelData
                })
            });

            const data = await res.json();

            if (res.ok && data.status === "success") {
                this.updateStatus(`✅ Success: ${data.count} edges committed.`, "success");
                setTimeout(() => {
                    alert(`Transaction Complete: ${data.count} personnel records successfully written to the database.`);
                }, 100);
            } else {
                throw new Error(data.message || "Server returned error status.");
            }
        } catch (e) {
            console.error("MetaForge Commit Error:", e);
            this.updateStatus("Commit Failed.", "error");
            alert(`Commit Failed: ${e.message}`);
        } finally {
            this.state.isLocked = false;
        }
    },

    updateStatus: function(msg, type) {
        const el = document.getElementById('p-status-text');
        if (!el) return;
        el.innerText = msg;
        el.style.color = (type === "success") ? "var(--status-success)" : "var(--status-error)";
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.metaforge.personnel.init());
} else {
    window.metaforge.personnel.init();
}
/* --- END OF FILE personnel.js --- */
