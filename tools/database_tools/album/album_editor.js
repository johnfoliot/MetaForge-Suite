// --- START OF FILE album_editor.js ---
/**
 * MetaForge Studio: Database Tools - Album Editor Spoke
 * Physical Location: \tools\database_tools\album\album_editor.js
 * Build 1.8.9: Remediated attribute escaping for special character support.
 */

window.metaforge = window.metaforge || {};
window.metaforge.database_tools = window.metaforge.database_tools || {};

window.metaforge.database_tools.album = {
    taxonomyData: null,

    // Helper to prevent HTML attribute breaking
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
                if (data.status === "success") {
                    this.taxonomyData = data.taxonomy;
                }
            } catch (e) {
                console.error("Failed to load taxonomy metadata configuration:", e);
                return;
            }
        }

        const genreSelect = document.getElementById('alb-genre');
        if (!genreSelect) return;

        genreSelect.innerHTML = '<option value="">-- Modify Genre --</option>';
        if (this.taxonomyData) {
            Object.keys(this.taxonomyData).sort().forEach(g => {
                const opt = document.createElement('option');
                opt.value = g;
                opt.textContent = g;
                genreSelect.appendChild(opt);
            });
        }

        genreSelect.onchange = () => {
            this.populateSubGenres(genreSelect.value, null);
        };

        if (selectedGenre) {
            genreSelect.value = selectedGenre;
            this.populateSubGenres(selectedGenre, selectedSubGenre);
        } else {
            this.populateSubGenres('', null);
        }
    },

    populateSubGenres: function(parentGenre, activeSubGenre) {
        const subSelect = document.getElementById('alb-subgenre');
        if (!subSelect) return;

        subSelect.innerHTML = '<option value="">-- Modify Sub Genre --</option>';
        
        if (this.taxonomyData && parentGenre && this.taxonomyData[parentGenre]) {
            this.taxonomyData[parentGenre].sort().forEach(sg => {
                const opt = document.createElement('option');
                opt.value = sg;
                opt.textContent = sg;
                subSelect.appendChild(opt);
            });
        }

        if (activeSubGenre) {
            subSelect.value = activeSubGenre;
        }
    },

    search: async function() {
        const query = document.getElementById('search-album').value.trim();
        if (!query) return;

        try {
            const res = await fetch(`/run_tool_logic/database_tools/search_album?album=${encodeURIComponent(query)}`);
            const data = await res.json();
            
            setTimeout(() => {
                if (data.status === "success") {
                    this.render(data.album);
                } else {
                    alert(data.message || "Album not found.");
                }
            }, 10);
        } catch (e) { console.error("Album search error:", e); }
    },

    load: async function(mfId) {
        try {
            const res = await fetch(`/run_tool_logic/database_tools/get_album_details?mf_id=${mfId}`);
            const data = await res.json();
            
            setTimeout(() => {
                if (data.status === "success") {
                    this.render(data.album);
                } else {
                    alert("Error loading album details: " + data.message);
                }
            }, 10);
        } catch (e) { console.error("Load album error:", e); }
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
            const parentTable = trackBody.closest('table');
            if (parentTable) {
                parentTable.style.width = "100%";
                parentTable.style.tableLayout = "fixed";
            }

            if (data.tracks && data.tracks.length > 0) {
                data.tracks.sort((a, b) => {
                    const extractNum = (trackObj) => {
                        const pathStr = trackObj.file_path || '';
                        const nameStr = pathStr.split('/').pop() || '';
                        const match = nameStr.match(/^(\d+)/);
                        return match ? parseInt(match[1], 10) : 999;
                    };
                    return extractNum(a) - extractNum(b);
                });

                data.tracks.forEach((t, idx) => {
                    const tr = document.createElement('tr');
                    tr.style.borderBottom = "1px solid #333";
                    tr.innerHTML = `
                        <td style="padding: 6px 8px; width: 50px; font-family: 'Cascadia Mono', monospace; color: var(--input-foreground2); vertical-align: middle;">${idx + 1}</td>
                        <td style="padding: 4px; width: 60%;">
                            <input type="text" class="mb-input-text track-title" value="${this.escapeHTML(t.title || '')}" data-path="${t.file_path || ''}" style="width: 100%; box-sizing: border-box; background: var(--input-background2); color: var(--input-foreground2); padding: 4px; border:0;">
                        </td>
                        <td style="padding: 4px; width: 35%;">
                            <input type="text" class="mb-input-text track-artist" value="${this.escapeHTML(t.artist || '')}" style="width: 100%; box-sizing: border-box; background: var(--input-background2); color: var(--input-foreground2); padding: 4px; Border:0">
                        </td>
                    `;
                    trackBody.appendChild(tr);
                });
            }
        }

        const pContainer = document.getElementById('personnel-rows-container');
        if (pContainer) {
            pContainer.innerHTML = '';
            if (data.personnel && data.personnel.length > 0) {
                data.personnel.forEach(p => {
                    this.appendPersonnelRow(p.role, p.name);
                });
            }
        }
    },

    addBlankPersonnel: function() {
        this.appendPersonnelRow('', '');
    },

    appendPersonnelRow: function(role, name) {
        const pContainer = document.getElementById('personnel-rows-container');
        if (!pContainer) return;

        const div = document.createElement('div');
        div.className = "personnel-edit-row";
        div.style = "display: flex; gap: 6px; align-items: center; margin-bottom: 4px;";
        
        div.innerHTML = `
            <input type="text" class="mb-input-text p-name" placeholder="Name" value="${this.escapeHTML(name || '')}" style="flex: 1.5; background: var(--input-background2); color: var(--input-foreground2); font-family: 'Cascadia Mono', monospace; padding: 4px;">
            <input type="text" class="mb-input-text p-role" placeholder="Role" value="${this.escapeHTML(role || '')}" style="flex: 1; background: var(--input-background2); color: var(--input-foreground2); font-family: 'Cascadia Code', monospace; padding: 4px;">
            <button class="mf-button-gold-fixed" style="background: var(--status-error) !important; width: 30px; min-width: 30px; height: 28px; padding: 0;" onclick="this.parentElement.remove()" aria-label="Remove Row" title="Remove Row">&times;</button>
        `;
        pContainer.appendChild(div);
    },

    browseCover: async function() {
        const res = await fetch('/select_file');
        const data = await res.json();
        if (data.path) {
            window.metaforge.database_tools.state.stagedCoverPath = data.path;
            const img = document.getElementById('alb-img');
            if (img) {
                img.src = data.path;
                img.style.display = 'block';
            }
        }
    },

    save: async function() {
        const trackRows = document.querySelectorAll('#album-track-list tr');
        const tracks = Array.from(trackRows).map(tr => ({
            file_path: tr.querySelector('.track-title').getAttribute('data-path'),
            title: tr.querySelector('.track-title').value.trim(),
            artist: tr.querySelector('.track-artist').value.trim()
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
            if ((await res.json()).status === "success") {
                alert("Album adjustments committed safely.");
                window.metaforge.database_tools.state.stagedCoverPath = null;
            }
        } catch (e) { console.error("Save album error:", e); }
    }
};

window.metaforge.database_tools.album_editor = window.metaforge.database_tools.album;
// --- END OF FILE album_editor.js ---