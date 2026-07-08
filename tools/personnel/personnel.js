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
        isLocked: false
    },

    init: function() {
        setTimeout(() => {
            const h1 = document.querySelector('h1.main');
            if (h1) h1.focus();
            this.ingestContext();
        }, 50);
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
                this.renderMapping();
                if (this.state.mapping.length === 0) {
                    this.updateStatus("No automatic matches found -- try Wikipedia search or Check AllMusic below.", "error");
                } else if (data.thin) {
                    this.updateStatus(`${this.state.mapping.length} credits found (thin -- Wikipedia auto-checked too). Consider AllMusic if still incomplete.`, "success");
                } else {
                    this.updateStatus(`${this.state.mapping.length} credits found via MusicBrainz + Discogs.`, "success");
                }
            }
        } catch (e) {
            console.error("Waterfall resolution failed:", e);
            this.updateStatus("Automatic resolution failed -- try manual search below.", "error");
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

    selectCandidate: async function(title) {
        this.updateStatus(`Extracting from: ${title}...`, "success");
        const rawContainer = document.getElementById('p-wiki-raw-container');
        rawContainer.innerHTML = 'Aggregating wikitext sections...';
        try {
            const res = await fetch('/run_tool_logic/personnel/fetch_content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: title })
            });
            const data = await res.json();
            if (data.status === "success") {
                rawContainer.innerText = data.raw_text;
                // A manual Wikipedia search ADDS to whatever the automatic
                // waterfall already staged, rather than replacing it --
                // MB/Discogs edges already found stay put. Candidates
                // arrive already junk-filtered and classified.
                this.state.mapping = this.state.mapping.concat(data.candidates);
                this.renderMapping();
                this.updateStatus("Extraction complete. Map identities on right.", "success");
            } else {
                rawContainer.innerHTML = `<span style="color:var(--status-error);">${data.message}</span>`;
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
            const meta = row.confidence !== undefined ? `${provenance} · conf ${row.confidence}` : provenance;
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
        // Simple toggle sort (ascending/descending)
        if (!this.state.sortDir) this.state.sortDir = 1;
        else this.state.sortDir *= -1;

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
                this.state.mapping = this.state.mapping.concat(data.candidates);
                this.renderMapping();
                this.updateStatus(`Added ${data.candidates.length} credits from AllMusic.`, "success");
                const modal = document.getElementById('p-allmusic-modal');
                if (modal) modal.remove();
            } else {
                this.updateStatus(data.message || "No credits found in pasted content.", "error");
            }
        } catch (e) {
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
