/* --- START OF FILE musicbrainz_id.js --- */
/**
 * ======================================================================
 * MetaForge Studio: MusicBrainz Logic Bridge (Structural Sync Build)
 * File Location: \tools\musicbrainz_id\musicbrainz_id.js
 * Build 2.20.8: Implemented Physical Rename Support in Commit Payload.
 * Role: Orchestrates MusicBrainz discovery and forensic track alignment.
 * Accessibility: WCAG 2.2 AA | COGA 4.6.1 (Working Memory)
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
        localFiles: [], // [ { filename: str, title: str } ]
        remoteTracks: [], // [ { position: str, title: str, track_id: uuid } ]
        isLocked: false
    },

    init: function() {
        setTimeout(() => {
            const header = document.getElementById('mb-id-header');
            if (header) header.focus();
            this.ingestContext();
        }, 50);
    },

    ingestContext: function() {
        const contextPath = window.mf_context_path || "";
        if (!contextPath) return;

        const pathInput = document.getElementById('mb-local-path');
        if (pathInput) {
            this.state.localPath = contextPath;
            pathInput.value = contextPath;
            this.getFolderContext(contextPath);
            window.mf_context_path = null; 
            this.announceStatus("MetaForge recognizes this album.", "success");
        }
    },

    selectFolder: async function() {
        try {
            const response = await fetch('/select_folder');
            const data = await response.json();
            if (data.path) {
                this.state.localPath = data.path;
                document.getElementById('mb-local-path').value = data.path;
                this.getFolderContext(data.path);
            }
        } catch (err) { console.error("Path selection failed:", err); }
    },

    getFolderContext: async function(path) {
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
            }
        } catch (err) { console.warn("Discovery context failed."); }
    },

    search: async function() {
        const artist = document.getElementById('mb-artist-input').value;
        const album = document.getElementById('mb-album-input').value;
        const resultsBody = document.getElementById('mb-results-body');

        if (!artist || !album) {
            this.announceStatus("⚠️ Artist and Album required.", "error");
            return;
        }

        this.announceStatus("Searching MusicBrainz...", "success");
        resultsBody.innerHTML = `<tr><td colspan="5" style="padding:20px; color:var(--mf-gold);">Consulting MusicBrainz...</td></tr>`;

        try {
            const response = await fetch('/run_tool_logic/musicbrainz_id/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ artist, album })
            });
            const data = await response.json();
            this.renderResults(data.status === "success" ? data.results : []);
        } catch (err) { this.announceStatus("⚠️ Search failed.", "error"); }
    },

    renderResults: function(results) {
        const body = document.getElementById('mb-results-body');
        if (!results || results.length === 0) {
            body.innerHTML = `<tr><td colspan="5" style="padding:20px;">No matches found.</td></tr>`;
            return;
        }

        body.innerHTML = results.map(r => {
            const cc = r.country_code ? r.country_code.toLowerCase() : "??";
            const hasValidCC = cc !== '??' && cc !== 'xw';
            const flagHtml = hasValidCC 
                ? `<img src="https://flagcdn.com/h20/${cc}.png" width="auto" height="12" alt="" style="vertical-align: middle;" title="${cc.toUpperCase()}">`
                : `<span style="font-size: 0.6rem; opacity: 0.5;">[${cc.toUpperCase()}]</span>`;

            return `
                <tr onclick="metaforge.musicbrainz_id.selectRelease('${r.id}')" tabindex="0" role="button" onkeydown="if(event.key==='Enter'||event.key===' ') this.click()">
                    <td>${r.score}%</td>
                    <td><strong>${r.artist}</strong><br>${r.title}</td>
                    <td>${r.track_count}</td>
                    <td>${r.year}</td>
                    <td style="text-align:center;" aria-label="Country: ${cc.toUpperCase()}">${flagHtml}</td>
                </tr>
            `;
        }).join('');
    },

    selectRelease: async function(releaseId) {
        if (this.state.isLocked) return;
        this.state.currentReleaseId = releaseId;
        const summary = document.getElementById('mb-id-summary');
        summary.innerHTML = "Retrieving MusicBrainz data...";
        
        try {
            const response = await fetch('/run_tool_logic/musicbrainz_id/get_release_details', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ release_id: releaseId, local_path: this.state.localPath })
            });
            const data = await response.json();
            if (data.status === "success") {
                this.state.currentArtistId = data.artist_id;
                this.state.currentReleaseGroupId = data.release_group_id;
                this.state.currentCountryCode = data.country_code;
                this.state.currentReleaseYear = data.release_year;
                this.state.remoteTracks = data.remote_tracks;
                this.state.localFiles = data.local_tracks;
                
                summary.innerHTML = `ALBUM: ${releaseId} | COUNTRY: ${data.country_code} | YEAR: ${data.release_year}`;
                this.renderComparison();
                document.getElementById('mb-commit-btn').disabled = false;
                document.getElementById('mb-commit-btn').style.opacity = "1";
                this.announceStatus("Release data ready.", "success");
            }
        } catch (err) { this.announceStatus("⚠️ Metadata fetch failed.", "error"); }
    },

    renderComparison: function() {
        const viewport = document.getElementById('mb-comparison-viewport');
        if (!viewport) return;
        viewport.innerHTML = '';

        const maxRows = Math.max(this.state.localFiles.length, this.state.remoteTracks.length);

        for (let i = 0; i < maxRows; i++) {
            const local = this.state.localFiles[i] || null;
            const remote = this.state.remoteTracks[i] || null;

            const row = document.createElement('div');
            row.className = 'mb-handshake-row';

            const colLocal = document.createElement('div');
            colLocal.className = 'mb-col';
            if (local) {
                colLocal.innerHTML = `
                    <div class="mb-sort-ctrls">
                        <button class="mb-btn-sort" onclick="metaforge.musicbrainz_id.moveTrack(${i}, -1)" ${i === 0 ? 'disabled' : ''}>▲</button>
                        <button class="mb-btn-sort" onclick="metaforge.musicbrainz_id.moveTrack(${i}, 1)" ${i === this.state.localFiles.length - 1 ? 'disabled' : ''}>▼</button>
                    </div>
                    <span class="mb-track-text">${i + 1}. ${local.filename}</span>
                `;
            }

            const colRemote = document.createElement('div');
            colRemote.className = 'mb-col';
            colRemote.style.borderLeft = '1px solid var(--bg-accent)';
            if (remote) {
                colRemote.innerHTML = `<span class="mb-track-text">${remote.position}. ${remote.title}</span>`;
            }

            row.appendChild(colLocal);
            row.appendChild(colRemote);
            viewport.appendChild(row);
        }
    },

    moveTrack: function(index, direction) {
        const newIndex = index + direction;
        if (newIndex < 0 || newIndex >= this.state.localFiles.length) return;

        [this.state.localFiles[index], this.state.localFiles[newIndex]] =
        [this.state.localFiles[newIndex], this.state.localFiles[index]];

        this.renderComparison();
    },

    commit: async function() {
        this.announceStatus("Committing IDs & Physical Rename...", "success");
        this.state.isLocked = true;

        const artistSeed = document.getElementById('mb-artist-input').value.trim();

        // ✅ FIX: include recording_id + work_id from remoteTracks
        const mapping = this.state.localFiles.map((file, index) => {
            const remote = this.state.remoteTracks[index];

            return {
                current_filename: file.filename,
                target_title: remote ? remote.title : "Unknown Title",

                track_id: remote ? remote.track_id : "",
                recording_id: remote ? remote.recording_id : "",
                work_id: remote ? remote.work_id : "",

                track_num: index + 1,
                artist_id: this.state.currentArtistId,
                album_id: this.state.currentReleaseId,
                release_group_id: this.state.currentReleaseGroupId,
                country_code: this.state.currentCountryCode
            };
        });

        try {
            const response = await fetch('/run_tool_logic/musicbrainz_id/commit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    local_path: this.state.localPath,
                    artist_seed: artistSeed,
                    release_year: this.state.currentReleaseYear,
                    mapping: mapping 
                })
            });

            const data = await response.json();
            if (data.status === "success") {
                this.announceStatus(`✅ Sync Complete:<br> ${data.summary.success} files updated/renamed.`, "success");
                this.injectHandoffButton();
            }
        } catch (err) {
            this.announceStatus("⚠️ Commit failure.", "error");
        } finally {
            this.state.isLocked = false;
        }
    },

    injectHandoffButton: function() {
        const container = document.getElementById('mb-handoff-container');
        if (!container) return;
        const path = this.state.localPath;
        // Built via the DOM API (not string-interpolated HTML) so a path
        // containing a single quote or other special character can't break
        // the handler -- no escaping needed since path is a real closure
        // variable, not text embedded into an onclick attribute string.
        container.innerHTML = '';
        const btn = document.createElement('button');
        btn.className = 'mf-button-gold-fixed';
        btn.textContent = 'Continue to: Intelli-Tagger';
        btn.onclick = () => window.mfAdvanceWorkflow('intelli-tagger', path);
        container.appendChild(btn);
    },

    announceStatus: function(msg, type) {
        const el = document.getElementById('mb-status-announcer');
        if (!el) return;
        el.innerHTML = msg.replace(/⚠️/g, '<span aria-hidden="true">⚠️</span>').replace(/✅/g, '<span aria-hidden="true">✅</span>');
        el.className = (type === "success") ? "status-success" : "status-error";
    },

    openHelp: async function() {
        const body = document.getElementById('mb-help-body');
        try {
            const res = await fetch('/tool_asset/musicbrainz_id/help.mfi');
            body.innerHTML = await res.text();
            document.getElementById('mb-help-panel').style.display = 'flex';
        } catch (e) {
            body.innerHTML = "Help unavailable.";
        }
    },

    closeHelp: function() {
        document.getElementById('mb-help-panel').style.display = 'none';
    }
};

window.metaforge.musicbrainz_id.init();
/* --- END OF FILE musicbrainz_id.js --- */