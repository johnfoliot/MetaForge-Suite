/* --- START OF FILE [D:\MetaForge Suite\tools\database_tools\album\album_editor.js] --- */
/**
 * MetaForge Studio: Database Tools - Album Editor Spoke
 * Build 1.8.11: Remediated Syntax and Personnel Hydration Fix.
 */

window.metaforge = window.metaforge || {};
window.metaforge.database_tools = window.metaforge.database_tools || {};

window.metaforge.database_tools.album = {
    taxonomyData: null,

    escapeHTML: function(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    },

    initTaxonomy: async function(selectedGenre, selectedSubGenre) {
        if (!this.taxonomyData) {
            try {
                const res = await fetch('/run_tool_logic/database_tools/get_taxonomy');
                const data = await res.json();
                if (data.status === "success") this.taxonomyData = data.taxonomy;
            } catch (e) { console.error("Taxonomy error:", e); return; }
        }

        const genreSelect = document.getElementById('alb-genre');
        if (!genreSelect) return;

        genreSelect.innerHTML = '<option value="">-- Modify Genre --</option>';
        if (this.taxonomyData) {
            Object.keys(this.taxonomyData).sort().forEach(g => {
                const opt = document.createElement('option');
                opt.value = g; opt.textContent = g;
                genreSelect.appendChild(opt);
            });
        }

        genreSelect.onchange = () => this.populateSubGenres(genreSelect.value, null);
        if (selectedGenre) {
            genreSelect.value = selectedGenre;
            this.populateSubGenres(selectedGenre, selectedSubGenre);
        }
    },

    populateSubGenres: function(parentGenre, activeSubGenre) {
        const subSelect = document.getElementById('alb-subgenre');
        if (!subSelect) return;
        subSelect.innerHTML = '<option value="">-- Modify Sub Genre --</option>';
        if (this.taxonomyData && parentGenre && this.taxonomyData[parentGenre]) {
            this.taxonomyData[parentGenre].sort().forEach(sg => {
                const opt = document.createElement('option');
                opt.value = sg; opt.textContent = sg;
                subSelect.appendChild(opt);
            });
        }
        if (activeSubGenre) subSelect.value = activeSubGenre;
    },

    search: async function() {
        const query = document.getElementById('search-album').value.trim();
        if (!query) return;
        try {
            const res = await fetch(`/run_tool_logic/database_tools/search_album?album=${encodeURIComponent(query)}`);
            const data = await res.json();
            if (data.status === "success") this.render(data.album);
            else alert(data.message || "Album not found.");
        } catch (e) { console.error(e); }
    },

    load: async function(mfId) {
        try {
            const res = await fetch(`/run_tool_logic/database_tools/get_album_details?mf_id=${mfId}`);
            const data = await res.json();
            if (data.status === "success") this.render(data.album);
            else alert("Load error: " + data.message);
        } catch (e) { console.error(e); }
    },

    render: function(data) {
        const workspace = document.getElementById('album-workspace');
        if (workspace) workspace.style.display = 'flex';
        window.metaforge.database_tools.state.activeId = data.mf_id;

        document.getElementById('alb-title').value = data.album_title || '';
        document.getElementById('alb-artist').value = data.artist_name || '';
        document.getElementById('alb-year').value = data.original_year || '';
        document.getElementById('alb-label').value = data.label || '';
        document.getElementById('alb-last-update').textContent = data.last_updated || 'MM-DD-YYYY';
        document.getElementById('alb-country').value = data.country || '';

        this.initTaxonomy(data.genre, data.sub_genre);

        const img = document.getElementById('alb-img');
        if (img) {
            img.onerror = () => { img.style.display = 'none'; };
            img.src = `/ui/covers/${data.mf_id}.jpg?t=${new Date().getTime()}`;
            img.style.display = 'block';
        }

        const trackBody = document.getElementById('album-track-list');
        if (trackBody) {
            trackBody.innerHTML = '';
            if (data.tracks) {
                data.tracks.sort((a,b) => (parseInt((a.file_path||'').split('/').pop())||999) - (parseInt((b.file_path||'').split('/').pop())||999)).forEach((t, idx) => {
                    const tr = document.createElement('tr');
                    const conf = t.orig_year_conf || 0;
                    const flagColor = conf >= 90 ? 'transparent' : (conf >= 50 ? 'var(--mf-gold)' : 'var(--status-error)');
                    const confId = `track-year-conf-${idx}`;
                    const confText = t.original_year
                        ? `${this.escapeHTML(t.orig_year_source || 'Unknown')} · conf ${conf}`
                        : 'No data';
                    tr.innerHTML = `
					    <td style="border-bottom:1px solid #ccc; padding: 6px 8px; width: 50px; font-family: 'Cascadia Mono', monospace; color: var(--input-foreground2); vertical-align: middle;">${idx + 1}</td>
                        <td style="border-bottom:1px solid #ccc; padding: 4px; width: 40%;">
                            <input type="text" class="mb-input-text track-title" value="${t.title || ''}" data-path="${t.file_path || ''}" style="width: 100%; box-sizing: border-box; background: var(--input-background2); color: var(--input-foreground2); padding: 4px; border:0;">
                        </td>
                        <td style="border-bottom:1px solid #ccc; padding: 4px; width: 28%;">
                            <input type="text" class="mb-input-text track-artist" value="${t.artist || ''}" style="width: 100%; box-sizing: border-box; background: var(--input-background2); color: var(--input-foreground2); padding: 4px; Border:0">
                       </td>
                        <td style="border-bottom:1px solid #ccc; padding: 4px; width: 110px;">
                            <input type="text" class="mb-input-text track-year" value="${t.original_year || ''}" aria-label="Original year, track ${idx + 1}: ${this.escapeHTML(t.title || '')}" aria-describedby="${confId}" style="width: 100%; box-sizing: border-box; background: var(--input-background2); color: var(--input-foreground2); padding: 4px; border: 0; border-left: 3px solid ${flagColor};">
                            <span id="${confId}" style="display:block; font-size: 0.6rem; margin-top: 2px; color: ${flagColor === 'transparent' ? 'var(--input-foreground2)' : flagColor};">${confText}</span>
                        </td>
						`;
                    trackBody.appendChild(tr);
                });
            }
        }

        const pContainer = document.getElementById('personnel-rows-container');
        if (pContainer) {
            pContainer.innerHTML = '';
            if (data.personnel) data.personnel.forEach(p => this.appendPersonnelRow(p.role, p.name));
        }
    },

    browseCover: async function() {
        const res = await fetch('/select_file');
        const data = await res.json();
        if (!data.path) return;

        window.metaforge.database_tools.state.stagedCoverPath = data.path;

        // Best-effort local preview; falls back silently to the existing
        // cover art if the webview blocks the file:// URI.
        const img = document.getElementById('alb-img');
        if (img) {
            const normalized = data.path.replace(/\\/g, '/');
            img.onerror = () => { img.style.display = 'none'; };
            img.src = 'file:///' + normalized;
            img.style.display = 'block';
        }
    },

    addBlankPersonnel: function() { this.appendPersonnelRow('', ''); },

    appendPersonnelRow: function(role, name) {
        const pContainer = document.getElementById('personnel-rows-container');
        if (!pContainer) return;
        const div = document.createElement('div');
        div.className = "personnel-edit-row";
        div.style = "display: flex; gap: 6px; align-items: center; margin-bottom: 4px;";
        div.innerHTML = `
			<input type="text" class="mb-input-text p-name" placeholder="Name" value="${name || ''}" style="flex: 1.5; background: var(--input-background2); color: var(--input-foreground2); font-family: 'Cascadia Mono', monospace; padding: 4px;">
            <input type="text" class="mb-input-text p-role" placeholder="Role" value="${role || ''}" style="flex: 1; background: var(--input-background2); color: var(--input-foreground2); font-family: 'Cascadia Code', monospace; padding: 4px;">
			<button class="mf-button-gold-fixed" style="background: var(--status-error) !important; width: 30px; min-width: 30px; height: 28px; padding: 0;" onclick="this.parentElement.remove()" aria-label="Remove Row" title="Remove Row">&times;</button>`;
        pContainer.appendChild(div);
    },

    save: async function() {
        const trackRows = document.querySelectorAll('#album-track-list tr');
        const tracks = Array.from(trackRows).map(tr => ({
            file_path: tr.querySelector('.track-title').getAttribute('data-path'),
            title: tr.querySelector('.track-title').value.trim(),
            artist: tr.querySelector('.track-artist').value.trim(),
            original_year: tr.querySelector('.track-year').value.trim()
        }));
        const pRows = document.querySelectorAll('.personnel-edit-row');
        const personnel = Array.from(pRows).map(row => ({
            role: row.querySelector('.p-role').value.trim(),
            name: row.querySelector('.p-name').value.trim()
        })).filter(p => p.name && p.role);

        const payload = {
            mf_id: window.metaforge.database_tools.state.activeId,
            title: document.getElementById('alb-title').value.trim(),
            artist: document.getElementById('alb-artist').value.trim(),
            year: document.getElementById('alb-year').value.trim(),
            label: document.getElementById('alb-label').value.trim(),
            genre: document.getElementById('alb-genre').value,
            sub_genre: document.getElementById('alb-subgenre').value,
            country: document.getElementById('alb-country').value.trim(),
            cover_path: window.metaforge.database_tools.state.stagedCoverPath || null,
            tracks: tracks,
            personnel: personnel
        };
        try {
            const res = await fetch('/run_tool_logic/database_tools/save_album', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            if ((await res.json()).status === "success") alert("Database updated.");
        } catch (e) { console.error("Save album error:", e); }
    },

    openModal: function() {
        if (document.getElementById("p-json-modal")) return;
        const modal = document.createElement('div');
        modal.id = "p-json-modal";
        modal.style = "position:fixed; top:20%; left:30%; width:40%; background:var(--bg-main); border:1px solid var(--mf-gold); padding:20px; z-index:10000;";
        modal.innerHTML = `
            <h3 style="color:var(--mf-gold); margin-top:0;">Import JSON Credits</h3>
            <textarea id="p-json-input" style="width:100%; height:200px; background:var(--input-background2); color:var(--input-foreground2);"></textarea>
            <div style="margin-top:10px; display:flex; gap:10px; justify-content:flex-end;">
                <button class="mf-button-gold-fixed" onclick="window.metaforge.database_tools.album.processJson()">Import Data</button>
                <button class="mf-button-gold-fixed" onclick="document.getElementById('p-json-modal').remove()">Cancel</button>
            </div>
        `;
        document.body.appendChild(modal);
    },

    processJson: function() {
        try {
            const raw = document.getElementById('p-json-input').value;
            const data = JSON.parse(raw);
            if (!Array.isArray(data)) throw new Error("Expected an array.");
            data.forEach(entry => this.appendPersonnelRow(entry.role, entry.name));
            document.getElementById('p-json-modal').remove();
        } catch (e) { alert("Error: " + e.message); }
    }
};

window.metaforge.database_tools.album_editor = window.metaforge.database_tools.album;
window.metaforge.album_importer = { openModal: () => window.metaforge.database_tools.album.openModal() };
// --- END OF FILE ---