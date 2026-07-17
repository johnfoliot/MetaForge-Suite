/* --- START OF FILE [D:\MetaForge Suite\tools\database_tools\album\album_editor.js] --- */
/**
 * MetaForge Studio: Database Tools - Album Editor Spoke
 * Build 1.8.11: Remediated Syntax and Personnel Hydration Fix.
 */

window.metaforge = window.metaforge || {};
window.metaforge.database_tools = window.metaforge.database_tools || {};

window.metaforge.database_tools.album = {
    taxonomyData: null,
    moodsData: null,

    // 24 keys (12 notes x Major/Minor), sharps only -- matches
    // acoustic_engine.py's own note-name convention exactly. The
    // algorithm itself only ever detects Major ("Simplified for Major
    // only as per legacy" per its own code comment), so Minor is only
    // ever reachable via this manual dropdown -- a real, known blind
    // spot in the automated detection (relative major/minor share a key
    // signature, a classic source of algorithmic confusion), not a
    // vocabulary gap in this list.
    KEY_OPTIONS: (() => {
        const notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
        const out = [];
        notes.forEach(n => out.push(`${n}Maj`));
        notes.forEach(n => out.push(`${n}Min`));
        return out;
    })(),

    escapeHTML: function(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    },

    // Shared by initTaxonomy (album-level) and openTrackModal (track-level)
    // -- one fetch, cached, both dropdowns' data comes from the exact same
    // taxonomy.json/moods.json the server-side validation checks against.
    loadTaxonomyAndMoods: async function() {
        if (this.taxonomyData) return;
        try {
            const res = await fetch('/run_tool_logic/database_tools/get_taxonomy');
            const data = await res.json();
            if (data.status === "success") {
                this.taxonomyData = data.taxonomy;
                this.moodsData = data.moods || null;
            }
        } catch (e) { console.error("Taxonomy error:", e); }
    },

    initTaxonomy: async function(selectedGenre, selectedSubGenre) {
        await this.loadTaxonomyAndMoods();

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
                        <td style="border-bottom:1px solid #ccc; padding: 4px; width: 100px;">
                            <input type="text" class="mb-input-text track-year" value="${t.original_year || ''}" aria-label="Original year, track ${idx + 1}: ${this.escapeHTML(t.title || '')}" aria-describedby="${confId}" style="width: 100%; box-sizing: border-box; background: var(--input-background2); color: var(--input-foreground2); padding: 4px; border: 0; border-left: 3px solid ${flagColor};">
                            <span id="${confId}" style="display:block; font-size: 0.6rem; margin-top: 2px; color: ${flagColor === 'transparent' ? 'var(--input-foreground2)' : flagColor};">${confText}</span>
                        </td>
                        <td style="border-bottom:1px solid #ccc; padding: 4px; width: 60px; text-align:center;">
                            <button type="button" class="mf-button-gold-fixed" style="padding: 4px 8px; font-size: 0.7rem;" onclick="window.metaforge.database_tools.album.openTrackModal('${(t.file_path || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'")}')" aria-label="Edit detailed track data for ${this.escapeHTML(t.title || 'track ' + (idx + 1))}">Edit</button>
                        </td>
						`;
                    trackBody.appendChild(tr);
                });
            }
        }

        const pContainer = document.getElementById('personnel-rows-container');
        if (pContainer) {
            pContainer.innerHTML = '';
            if (data.personnel) data.personnel.forEach(p => this.appendPersonnelRow(p.role, p.name, p.id));
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

    addBlankPersonnel: function() { this.appendPersonnelRow('', '', null); },

    appendPersonnelRow: function(role, name, id) {
        const pContainer = document.getElementById('personnel-rows-container');
        if (!pContainer) return;
        const div = document.createElement('div');
        div.className = "personnel-edit-row";
        // Carries the row's existing edges.id (if any) so save() can tell
        // the backend "update this exact row" instead of "here's a fresh
        // list, wipe and rebuild everything" -- untouched rows (including
        // ones sourced from MB/Discogs/Wikipedia) are then left alone
        // rather than losing their provenance/confidence on every save.
        if (id !== undefined && id !== null) div.dataset.edgeId = id;
        div.style = "display: flex; gap: 6px; align-items: center; margin-bottom: 4px;";
        // Real bug, found live 2026-07-16: name/role were interpolated raw
        // into the value="..." attribute with no escaping -- a name
        // containing a literal double quote (e.g. Willie "Big Eyes" Smith,
        // a real credit in this library) prematurely terminated the
        // attribute, corrupting the markup and producing a garbled
        // &quot;-laden duplicate artist row on save. escapeHTML() already
        // exists in this file (used elsewhere for track titles) and
        // already handles quotes correctly -- it just was never called
        // here.
        div.innerHTML = `
			<input type="text" class="mb-input-text p-name" placeholder="Name" value="${this.escapeHTML(name || '')}" style="flex: 1.5; background: var(--input-background2); color: var(--input-foreground2); font-family: 'Cascadia Mono', monospace; padding: 4px;">
            <input type="text" class="mb-input-text p-role" placeholder="Role" value="${this.escapeHTML(role || '')}" style="flex: 1; background: var(--input-background2); color: var(--input-foreground2); font-family: 'Cascadia Code', monospace; padding: 4px;">
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
            name: row.querySelector('.p-name').value.trim(),
            id: row.dataset.edgeId ? parseInt(row.dataset.edgeId, 10) : null
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
    },

    // =========================================================
    // TRACK-LEVEL DETAIL MODAL (2026-07-17)
    // =========================================================
    // Fields the main track table can't expose (Title/Artist/Original Year
    // already have their own inline inputs there): Genre/Sub-Genre/Mood/
    // Sonic Texture/Emotional Flavor, the measured BPM/Key/Intensity trio
    // (plus a per-track "Re-analyze from Audio" action -- deliberately NOT
    // a full album re-run, so a 5-disc box set doesn't need reprocessing
    // to fix one track's BPM), and forensic MB/AcoustID IDs tucked into a
    // collapsed Advanced section. Personnel is out of scope -- has its own
    // tool (Personnel Scout).
    openTrackModal: async function(filePath) {
        if (document.getElementById("track-detail-modal")) return;

        await this.loadTaxonomyAndMoods();

        let track = null;
        try {
            const res = await fetch(`/run_tool_logic/database_tools/get_track_detail?file_path=${encodeURIComponent(filePath)}`);
            const data = await res.json();
            if (data.status !== "success") { alert(data.message || "Track not found."); return; }
            track = data.track;
        } catch (e) {
            console.error("Track detail fetch error:", e);
            alert("Failed to load track detail.");
            return;
        }

        const genres = this.taxonomyData ? Object.keys(this.taxonomyData).sort() : [];
        const moods = this.moodsData ? (this.moodsData.anchors || []) : [];
        const textures = this.moodsData ? ((this.moodsData.modifiers || {}).Sonic_Texture || []) : [];
        const flavors = this.moodsData ? ((this.moodsData.modifiers || {}).Emotional_Flavor || []) : [];

        const buildOptions = (list, current) => ['<option value="">-- Unset --</option>'].concat(
            list.map(v => `<option value="${this.escapeHTML(v)}" ${v === current ? 'selected' : ''}>${this.escapeHTML(v)}</option>`)
        ).join('');

        const modal = document.createElement('div');
        modal.id = "track-detail-modal";
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-labelledby', 'track-detail-title');
        modal.dataset.filePath = filePath;
        modal.style = "position:fixed; top:6%; left:26%; width:48%; max-height:88vh; overflow-y:auto; background:var(--bg-main); border:1px solid var(--mf-gold); padding:20px; z-index:10000; box-shadow: 0 0 20px rgba(0,0,0,0.5);";
        modal.innerHTML = `
            <h3 id="track-detail-title" style="color:var(--mf-gold); margin-top:0;">Track Detail: ${this.escapeHTML(track.title || filePath.split('/').pop())}</h3>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-bottom:14px;">
                <div><label class="mf-card-label" style="color:var(--mf-gold);">Genre</label>
                    <select id="tm-genre" class="mb-input-text" style="width:100%; background:white; color:black;">
                        <option value="">-- Unset --</option>
                        ${genres.map(g => `<option value="${this.escapeHTML(g)}" ${g === track.genre ? 'selected' : ''}>${this.escapeHTML(g)}</option>`).join('')}
                    </select>
                </div>
                <div><label class="mf-card-label" style="color:var(--mf-gold);">Sub-Genre</label>
                    <select id="tm-subgenre" class="mb-input-text" style="width:100%; background:white; color:black;"></select>
                </div>
                <div><label class="mf-card-label" style="color:var(--mf-gold);">Mood</label>
                    <select id="tm-mood" class="mb-input-text" style="width:100%; background:white; color:black;">${buildOptions(moods, track.mood)}</select>
                </div>
                <div><label class="mf-card-label" style="color:var(--mf-gold);">Sonic Texture</label>
                    <select id="tm-texture" class="mb-input-text" style="width:100%; background:white; color:black;">${buildOptions(textures, track.sonic_texture)}</select>
                </div>
                <div><label class="mf-card-label" style="color:var(--mf-gold);">Emotional Flavor</label>
                    <select id="tm-flavor" class="mb-input-text" style="width:100%; background:white; color:black;">${buildOptions(flavors, track.emotional_flavor)}</select>
                </div>
            </div>

            <div style="border-top:1px solid var(--bg-accent); padding-top:12px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <strong style="color:var(--mf-gold); font-size:0.8rem;">Measured</strong>
                    <button type="button" class="mf-button-gold-fixed" id="tm-reanalyze-btn" style="font-size:0.7rem; padding:4px 8px;">Re-analyze from Audio</button>
                </div>
                <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px;">
                    <div><label class="mf-card-label" style="color:var(--mf-gold);">BPM</label>
                        <input type="number" id="tm-bpm" class="mb-input-text" value="${track.bpm != null ? track.bpm : ''}" style="width:100%; background:white; color:black;">
                    </div>
                    <div><label class="mf-card-label" style="color:var(--mf-gold);">Key</label>
                        <select id="tm-key" class="mb-input-text" style="width:100%; background:white; color:black;">
                            <option value="">-- Unset --</option>
                            ${this.KEY_OPTIONS.map(k => `<option value="${k}" ${k === track.key_val ? 'selected' : ''}>${k}</option>`).join('')}
                        </select>
                    </div>
                    <div><label class="mf-card-label" style="color:var(--mf-gold);">Intensity (1-10)</label>
                        <input type="number" id="tm-intensity" min="1" max="10" class="mb-input-text" value="${track.intensity != null ? track.intensity : ''}" style="width:100%; background:white; color:black;">
                    </div>
                </div>
                <div id="tm-reanalyze-status" role="status" aria-live="polite" style="font-size:0.7rem; color:var(--text-message); margin-top:6px;"></div>
            </div>

            <details style="margin-bottom:16px;">
                <summary style="color:var(--mf-gold); cursor:pointer; font-size:0.8rem;">Advanced / Forensic IDs</summary>
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-top:10px;">
                    <div><label class="mf-card-label" style="color:var(--mf-gold);">MB Track ID</label>
                        <input type="text" id="tm-mbtrack" class="mb-input-text" value="${this.escapeHTML(track.mb_track_id || '')}" style="width:100%; background:white; color:black;">
                    </div>
                    <div><label class="mf-card-label" style="color:var(--mf-gold);">MB Recording ID</label>
                        <input type="text" id="tm-mbrecording" class="mb-input-text" value="${this.escapeHTML(track.mb_recording_id || '')}" style="width:100%; background:white; color:black;">
                    </div>
                    <div><label class="mf-card-label" style="color:var(--mf-gold);">MB Work ID</label>
                        <input type="text" id="tm-mbwork" class="mb-input-text" value="${this.escapeHTML(track.mb_work_id || '')}" style="width:100%; background:white; color:black;">
                    </div>
                    <div><label class="mf-card-label" style="color:var(--mf-gold);">MB Artist ID</label>
                        <input type="text" id="tm-mbartist" class="mb-input-text" value="${this.escapeHTML(track.mb_artist_id || '')}" style="width:100%; background:white; color:black;">
                    </div>
                    <div><label class="mf-card-label" style="color:var(--mf-gold);">AcoustID</label>
                        <input type="text" id="tm-acoustid" class="mb-input-text" value="${this.escapeHTML(track.acoustid || '')}" style="width:100%; background:white; color:black;">
                    </div>
                </div>
            </details>

            <div style="display:flex; gap:10px; justify-content:flex-end;">
                <button type="button" class="mf-button-gold-fixed" id="tm-save-btn">Save</button>
                <button type="button" class="mf-button-gold-fixed" id="tm-cancel-btn">Cancel</button>
            </div>
        `;
        document.body.appendChild(modal);

        this.populateTrackSubGenres(track.genre, track.sub_genre);
        document.getElementById('tm-genre').addEventListener('change', (e) => this.populateTrackSubGenres(e.target.value, null));
        document.getElementById('tm-reanalyze-btn').addEventListener('click', () => this.reanalyzeTrackDetail());
        document.getElementById('tm-save-btn').addEventListener('click', () => this.saveTrackDetail());
        document.getElementById('tm-cancel-btn').addEventListener('click', () => this.closeTrackModal());
        document.getElementById('tm-genre').focus();
    },

    populateTrackSubGenres: function(parentGenre, activeSubGenre) {
        const subSelect = document.getElementById('tm-subgenre');
        if (!subSelect) return;
        subSelect.innerHTML = '<option value="">-- Unset --</option>';
        if (this.taxonomyData && parentGenre && this.taxonomyData[parentGenre]) {
            this.taxonomyData[parentGenre].sort().forEach(sg => {
                const opt = document.createElement('option');
                opt.value = sg; opt.textContent = sg;
                subSelect.appendChild(opt);
            });
        }
        if (activeSubGenre) subSelect.value = activeSubGenre;
    },

    closeTrackModal: function() {
        const modal = document.getElementById('track-detail-modal');
        if (modal) modal.remove();
    },

    // Deliberately its own atomic action, independent of the modal's main
    // Save button: writes straight to the DB + tags server-side (see
    // intelli-tagger.py's reanalyze_track action) the moment it succeeds,
    // rather than waiting for the user to also click Save.
    reanalyzeTrackDetail: async function() {
        const modal = document.getElementById('track-detail-modal');
        if (!modal) return;
        const statusEl = document.getElementById('tm-reanalyze-status');
        const btn = document.getElementById('tm-reanalyze-btn');
        if (statusEl) statusEl.textContent = "Re-analyzing from audio...";
        if (btn) btn.disabled = true;

        try {
            const res = await fetch('/run_tool_logic/intelli-tagger/reanalyze_track', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ file_path: modal.dataset.filePath })
            });
            const data = await res.json();
            if (data.status === "success") {
                document.getElementById('tm-bpm').value = data.bpm;
                document.getElementById('tm-key').value = data.key;
                document.getElementById('tm-intensity').value = data.intensity;
                if (statusEl) statusEl.textContent = "Re-analysis complete -- values updated and saved.";
            } else if (statusEl) {
                statusEl.textContent = "Re-analysis failed: " + (data.message || "unknown error");
            }
        } catch (e) {
            console.error("Re-analyze error:", e);
            if (statusEl) statusEl.textContent = "Re-analysis failed.";
        } finally {
            if (btn) btn.disabled = false;
        }
    },

    saveTrackDetail: async function() {
        const modal = document.getElementById('track-detail-modal');
        if (!modal) return;

        const payload = {
            file_path: modal.dataset.filePath,
            genre: document.getElementById('tm-genre').value,
            sub_genre: document.getElementById('tm-subgenre').value,
            mood: document.getElementById('tm-mood').value,
            sonic_texture: document.getElementById('tm-texture').value,
            emotional_flavor: document.getElementById('tm-flavor').value,
            bpm: document.getElementById('tm-bpm').value,
            key: document.getElementById('tm-key').value,
            intensity: document.getElementById('tm-intensity').value,
            mb_track_id: document.getElementById('tm-mbtrack').value.trim(),
            mb_recording_id: document.getElementById('tm-mbrecording').value.trim(),
            mb_work_id: document.getElementById('tm-mbwork').value.trim(),
            mb_artist_id: document.getElementById('tm-mbartist').value.trim(),
            acoustid: document.getElementById('tm-acoustid').value.trim()
        };

        try {
            const res = await fetch('/run_tool_logic/database_tools/save_track_detail', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.status === "success") {
                this.closeTrackModal();
            } else {
                alert(data.message || "Save failed.");
            }
        } catch (e) {
            console.error("Save track detail error:", e);
            alert("Save failed.");
        }
    }
};

window.metaforge.database_tools.album_editor = window.metaforge.database_tools.album;
window.metaforge.album_importer = { openModal: () => window.metaforge.database_tools.album.openModal() };
// --- END OF FILE ---