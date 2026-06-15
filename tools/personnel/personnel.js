/* --- START OF FILE personnel.js --- */
/**
 * MetaForge Studio: Personnel Scout Logic Bridge
 * Role: Orchestrates Wikipedia extraction and Graph Layer mapping.
 * Physical Location: \tools\personnel\personnel.js
 * Build 1.2.3: Stabilized File Picker and Guaranteed Feedback Loop.
 * Adheres to Directive III (High-Density Workbench) and Directive IV (Logic Isolation).
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
            }
        } catch (err) { 
            console.warn("Manifest discovery failed."); 
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
                resultsBody.innerHTML = '<tr><td colspan="2" style="padding:10px; text-align:center;">No matches found.</td></tr>';
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
                this.state.mapping = data.candidates;
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
            tr.innerHTML = `
                <td style="padding:4px;"><input type="text" class="mb-input-text p-map-name" value="${row.name.replace(/"/g, '&quot;')}" style="width:100%; border:none; background:transparent; color:var(--text-output);"></td>
                <td style="padding:4px;"><input type="text" class="mb-input-text p-map-role" value="${row.role.replace(/"/g, '&quot;')}" style="width:100%; border:none; background:transparent; color:var(--text-output);"></td>
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

    addManualRow: function() {
        this.state.mapping.push({ name: "", role: "" });
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
            const valA = a[key].toLowerCase();
            const valB = b[key].toLowerCase();
            if (valA < valB) return -1 * this.state.sortDir;
            if (valA > valB) return 1 * this.state.sortDir;
            return 0;
        });

        this.renderMapping();
    },


    commitToDatabase: async function() {
        if (this.state.isLocked) return;

        const rows = document.querySelectorAll('#p-mapping-body tr');
        const personnelData = [];
        rows.forEach(tr => {
            const name = tr.querySelector('.p-map-name').value.trim();
            const role = tr.querySelector('.p-map-role').value.trim();
            if (name && role) personnelData.push({ name, role });
        });

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