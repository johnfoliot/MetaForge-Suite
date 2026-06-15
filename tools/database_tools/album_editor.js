// --- START OF FILE album_editor.js ---
/**
 * MetaForge Studio: Database Tools - Album Editor Spoke
 * Role: Manages Album workspace rendering and edit logic.
 * Physical Location: \tools\database_tools\album_editor.js
 */

window.metaforge = window.metaforge || {};
window.metaforge.database_tools = window.metaforge.database_tools || {};

window.metaforge.database_tools.album_editor = {

    load: async function(mfId) {
        try {
            const res = await fetch(`/run_tool_logic/database_tools/get_album_details?mf_id=${mfId}`);
            const data = await res.json();
            if (data.status === "success") this.render(data.album);
            else alert("Error loading album details: " + data.message);
        } catch (e) { console.error("Album detail retrieval error:", e); }
    },

    render: function(data) {
        const workspace = document.getElementById('workspace-stage');
        const artistArea = document.getElementById('artist-workspace');
        const albumArea = document.getElementById('album-workspace');
        
        if (workspace) workspace.style.display = 'flex';
        if (artistArea) artistArea.style.display = 'none';
        if (albumArea) albumArea.style.display = 'flex';
        
        window.metaforge.database_tools.state.activeId = data.mf_id;
        
        const titleEl = document.getElementById('alb-title');
        const artEl = document.getElementById('alb-artist');
        const yrEl = document.getElementById('alb-year');
        const labEl = document.getElementById('alb-label');

        if (titleEl) titleEl.value = data.album_title || '';
        if (artEl) artEl.value = data.artist_name || '';
        if (yrEl) yrEl.value = data.original_year || '';
        if (labEl) labEl.value = data.label || '';

        // Restore Cover Art
        const img = document.getElementById('alb-img');
        if (img) {
            img.src = `/ui/covers/${data.mf_id}.jpg?t=${new Date().getTime()}`;
            img.style.display = 'block';
        }

        // Restore Personnel
        const pContainer = document.getElementById('personnel-rows-container');
        if (pContainer) {
            pContainer.innerHTML = '';
            if (data.personnel && data.personnel.length > 0) {
                data.personnel.forEach(p => this.addPersonnelRow(p));
            } else { this.addPersonnelRow(); }
        }

        // Restore Track List
        const trackBody = document.getElementById('album-track-list');
        if (trackBody && data.tracks) {
            trackBody.innerHTML = '';
            data.tracks.forEach((t, index) => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td style="padding:4px; border-bottom:1px solid #333;"><input type="text" class="mb-input-text track-num" value="${index + 1}" style="width:30px; text-align:center; background:transparent; border:none; color:var(--input-foreground2);"></td>
                    <td style="padding:4px; border-bottom:1px solid #333;"><input type="text" class="mb-input-text track-title" value="${t.title}" style="width:100%; background:transparent; border:none; color:var(--input-foreground2);" data-path="${t.file_path}"></td>
                    <td style="padding:4px; border-bottom:1px solid #333;"><input type="text" class="mb-input-text track-artist" value="${t.artist}" style="width:100%; background:transparent; border:none; color:var(--input-foreground2);"></td>
                `;
                trackBody.appendChild(tr);
            });
        }
    },

    addBlankPersonnel: function() { this.addPersonnelRow(); },

    addPersonnelRow: function(p = {}) {
        const container = document.getElementById('personnel-rows-container');
        if (!container) return;
        const div = document.createElement('div');
        div.className = 'personnel-entry-row';
        div.style = "background: var(--bg-accent); padding:6px; border: 1px solid #444; border-radius:2px; margin-bottom: 4px;";
        div.innerHTML = `
            <div style="display:grid; grid-template-columns: 1.5fr 1fr 1fr auto; gap:5px; align-items: center;">
                <input type="text" class="mb-input-text p-name" placeholder="Name" value="${p.name || ''}" style="background:var(--input-background2); color:var(--input-foreground2); font-size: 0.75rem;">
                <select class="mb-input-text p-role" style="background:var(--input-background2); color:var(--input-foreground2); font-size: 0.75rem;">
                    ${["Instrument", "Vocal", "Composer", "Lyricist", "Producer", "Engineer", "Arranger", "Conductor", "Mastering"]
                      .map(r => `<option value="${r}" ${p.role === r ? 'selected' : ''}>${r}</option>`).join('')}
                </select>
                <select class="mb-input-text p-source" style="background:var(--input-background2); color:var(--input-foreground2); font-size: 0.7rem;">
                    ${["MetaForge", "Wikipedia", "Liner Notes", "Personal Knowledge", "External Fetch"]
                      .map(s => `<option value="${s}" ${p.source === s ? 'selected' : ''}>${s}</option>`).join('')}
                </select>
                <button class="mf-button-gold-fixed" style="font-size:0.6rem; padding: 2px 8px; background: var(--status-error) !important; border: 1px solid #000; color: #fff !important;" onclick="this.closest('.personnel-entry-row').remove()">Remove</button>
            </div>
        `;
        container.appendChild(div);
    },

    browseCover: async function() {
        const res = await fetch('/select_file');
        const data = await res.json();
        if (data.path) {
            window.metaforge.database_tools.state.stagedCoverPath = data.path;
            const img = document.getElementById('alb-img');
            if (img) img.style.border = "2px solid var(--status-success)";
            alert("New cover staged.");
        }
    },

    save: async function() {
        const tracks = Array.from(document.querySelectorAll('#album-track-list tr')).map(tr => ({
            track_num: tr.querySelector('.track-num').value,
            file_path: tr.querySelector('.track-title').getAttribute('data-path'),
            title: tr.querySelector('.track-title').value,
            artist: tr.querySelector('.track-artist').value
        }));
        const personnel = Array.from(document.querySelectorAll('.personnel-entry-row')).map(div => ({
            name: div.querySelector('.p-name').value,
            role: div.querySelector('.p-role').value,
            source: div.querySelector('.p-source').value
        }));

        const payload = {
            mf_id: window.metaforge.database_tools.state.activeId,
            title: document.getElementById('alb-title').value,
            artist: document.getElementById('alb-artist').value,
            year: document.getElementById('alb-year').value,
            label: document.getElementById('alb-label').value,
            tracks: tracks,
            personnel: personnel,
            cover_path: window.metaforge.database_tools.state.stagedCoverPath
        };

        const res = await fetch('/run_tool_logic/database_tools/save_album', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.status === "success") {
            alert("MetaForge Database updated.");
            window.metaforge.database_tools.state.stagedCoverPath = null;
        }
    }
};
// --- END OF FILE album_editor.js ---