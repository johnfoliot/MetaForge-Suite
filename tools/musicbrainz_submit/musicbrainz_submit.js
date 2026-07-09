/* --- START OF FILE musicbrainz_submit.js --- */
/**
 * MetaForge Studio: MusicBrainz Submit Logic Bridge
 * Role: Renders the original-year correction review queue and opens a
 * seeded MusicBrainz Add Release wizard in a companion "pseudo-tab"
 * window per candidate -- MetaForge builds the evidence-filled form,
 * MusicBrainz's own website is where the human actually reviews/submits.
 * Physical Location: \tools\musicbrainz_submit\musicbrainz_submit.js
 */

window.metaforge = window.metaforge || {};
window.metaforge.musicbrainz_submit = {
    state: {
        candidates: [],
        personnelCandidates: [],
        personnelLoaded: false,
        // Album-grouped rows (Yandex Mail-style thread collapse, John's
        // idea 2026-07-09 -- one album's worth of rows was an
        // overwhelming "wall of data" otherwise, e.g. 40 personnel rows
        // for a single 16-track album). Keyed by "artist::album", one
        // Set per tab since expand state is independent per queue.
        // Ephemeral by design, same as personnelLoaded below -- reset on
        // every fresh visit, not persisted.
        expandedGroups: { year: new Set(), personnel: new Set() }
    },

    init: function() {
        // This tool's namespace object is a singleton that survives
        // across tool re-visits (metaforge_core.js's loadTool() rebuilds
        // the DOM fresh each time but never recreates window.metaforge.*
        // objects, only calls .init() again) -- so personnelLoaded must
        // be reset here, or a flag set true on an earlier visit this
        // session permanently skips the fetch on every later visit,
        // leaving the freshly-injected "Loading candidates..." row
        // frozen forever (confirmed live 2026-07-09, John).
        this.state.personnelLoaded = false;
        this.state.personnelCandidates = [];
        this.state.expandedGroups = { year: new Set(), personnel: new Set() };
        setTimeout(() => {
            const h1 = document.querySelector('h1.main');
            if (h1) h1.focus();
            this.loadCandidates();
        }, 50);
    },

    switchTab: function(tab) {
        const yearTab = document.getElementById('mbs-tab-year');
        const personnelTab = document.getElementById('mbs-tab-personnel');
        const yearPanel = document.getElementById('mbs-panel-year');
        const personnelPanel = document.getElementById('mbs-panel-personnel');
        if (!yearTab || !personnelTab || !yearPanel || !personnelPanel) return;

        const isYear = tab === 'year';
        yearTab.setAttribute('aria-selected', isYear ? 'true' : 'false');
        yearTab.tabIndex = isYear ? 0 : -1;
        personnelTab.setAttribute('aria-selected', isYear ? 'false' : 'true');
        personnelTab.tabIndex = isYear ? -1 : 0;
        yearPanel.style.display = isYear ? 'flex' : 'none';
        personnelPanel.style.display = isYear ? 'none' : 'flex';

        if (!isYear && !this.state.personnelLoaded) {
            this.loadPersonnelCandidates();
        }
    },

    escapeHtml: function(str) {
        const div = document.createElement('div');
        div.textContent = str === null || str === undefined ? '' : String(str);
        return div.innerHTML;
    },

    // Groups a flat candidate list by (artist, album) -- MusicBrainz's
    // own primary mental model is albums, and a flat table of 40 rows
    // for one album read as an undifferentiated wall of data. Groups
    // with at least one pending/in_progress row sort first, then
    // alphabetically, so albums still needing attention surface above
    // ones that are fully resolved.
    _groupByAlbum: function(rows) {
        const groups = new Map();
        for (const r of rows) {
            const key = `${r.artist}::${r.album}`;
            if (!groups.has(key)) {
                groups.set(key, { key, artist: r.artist, album: r.album, rows: [], pending: 0, submitted: 0, dismissed: 0 });
            }
            const g = groups.get(key);
            g.rows.push(r);
            if (r.status === "submitted") g.submitted++;
            else if (r.status === "dismissed") g.dismissed++;
            else g.pending++; // "pending" and "in_progress" (stepper) both still need attention
        }
        const list = Array.from(groups.values());
        list.sort((a, b) => {
            const aOpen = a.pending > 0 ? 0 : 1;
            const bOpen = b.pending > 0 ? 0 : 1;
            if (aOpen !== bOpen) return aOpen - bOpen;
            return `${a.artist}${a.album}`.localeCompare(`${b.artist}${b.album}`);
        });
        return list;
    },

    toggleGroup: function(tab, key) {
        const set = this.state.expandedGroups[tab];
        if (set.has(key)) set.delete(key); else set.add(key);
        if (tab === "year") this.renderQueue(); else this.renderPersonnelQueue();
    },

    // Shared collapsed/expanded header row for both queues -- colspan
    // must match the tab's own column count (year: 5, personnel: 4,
    // since personnel dropped its now-redundant Artist/Album column
    // once every row already lives under a group header naming it).
    _renderGroupHeader: function(tab, group, colspan) {
        const esc = (s) => this.escapeHtml(s);
        const expanded = this.state.expandedGroups[tab].has(group.key);
        const chevron = expanded ? "▾" : "▸";
        const parts = [];
        if (group.pending) parts.push(`${group.pending} pending`);
        if (group.submitted) parts.push(`${group.submitted} submitted`);
        if (group.dismissed) parts.push(`${group.dismissed} dismissed`);
        const keyEsc = esc(group.key).replace(/'/g, "\\'");
        return `
            <tr class="mbs-group-header" role="button" tabindex="0" aria-expanded="${expanded}"
                onclick="window.metaforge.musicbrainz_submit.toggleGroup('${tab}', '${keyEsc}')"
                onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault(); window.metaforge.musicbrainz_submit.toggleGroup('${tab}', '${keyEsc}');}">
                <td colspan="${colspan}" style="padding:8px;">
                    <span aria-hidden="true" style="display:inline-block; width:1em; color:var(--mf-gold);">${chevron}</span>
                    <span style="color:var(--mf-gold); font-weight:bold;">${esc(group.artist)}</span>
                    <em style="font-weight:normal;"> &mdash; ${esc(group.album)}</em>
                    <span style="color:var(--text-message); font-weight:normal; font-size:0.8rem; margin-left:10px;">
                        ${group.rows.length} item${group.rows.length === 1 ? "" : "s"} (${esc(parts.join(", "))})
                    </span>
                </td>
            </tr>`;
    },

    loadCandidates: async function() {
        this.updateStatus("Loading candidates...", "success");
        try {
            const res = await fetch('/run_tool_logic/musicbrainz_submit/list_candidates');
            const data = await res.json();
            if (data.status === "success") {
                this.state.candidates = data.candidates;
                this.renderQueue();
                this.renderCounts(data.counts);
                this.updateStatus(`${data.counts.pending} candidate(s) awaiting review.`, "success");
            } else {
                this.updateStatus(data.message || "Failed to load candidates.", "error");
            }
        } catch (e) {
            this.updateStatus("Network error loading candidates.", "error");
        }
    },

    renderCounts: function(counts) {
        const p = document.getElementById('mbs-count-pending');
        const s = document.getElementById('mbs-count-submitted');
        const d = document.getElementById('mbs-count-dismissed');
        if (p) p.innerText = counts.pending;
        if (s) s.innerText = counts.submitted;
        if (d) d.innerText = counts.dismissed;
    },

    renderQueue: function() {
        const body = document.getElementById('mbs-queue-body');
        if (!body) return;

        if (this.state.candidates.length === 0) {
            body.innerHTML = '<tr><td colspan="5" style="padding:20px; text-align:center; opacity:0.6;">No correction candidates found yet -- run albums through Intelli-Tagger with the original-year waterfall to populate this queue.</td></tr>';
            return;
        }

        const groups = this._groupByAlbum(this.state.candidates);
        body.innerHTML = groups.map(group => {
            const header = this._renderGroupHeader("year", group, 5);
            if (!this.state.expandedGroups.year.has(group.key)) return header;
            return header + group.rows.map(c => this._renderYearRow(c)).join('');
        }).join('');
    },

    _renderYearRow: function(c) {
        const esc = (s) => this.escapeHtml(s);
        const statusLabel = c.status === "pending" ? "" :
            `<div style="font-size:0.7rem; color:var(--text-message); margin-top:4px;">Marked ${esc(c.status)}</div>`;
        const disabled = c.status !== "pending" ? "disabled" : "";
        return `
            <tr style="border-bottom:1px solid #333; ${c.status !== 'pending' ? 'opacity:0.55;' : ''}">
                <td style="padding:8px 8px 8px 28px; color:var(--mf-gold);">${esc(c.title)}</td>
                <td style="padding:8px; text-align:center;">${esc(c.current_release_year)}</td>
                <td style="padding:8px; text-align:center; color:var(--status-success); font-weight:bold;">${esc(c.proposed_original_year)}</td>
                <td style="padding:8px;">
                    <div>${esc(c.orig_year_source)}</div>
                    <div style="color:var(--text-message); font-size:0.75rem;">conf ${esc(c.orig_year_conf)}</div>
                </td>
                <td style="padding:8px;">
                    <div style="display:flex; gap:6px; flex-wrap:wrap;">
                        <button class="mf-button-gold-fixed" style="font-size:0.75rem; padding:4px 8px; height:auto;"
                                onclick="window.metaforge.musicbrainz_submit.openInMusicBrainz('${esc(c.mb_recording_id)}')" ${disabled}>
                            Open in MusicBrainz
                        </button>
                        <button class="mf-button-gold-fixed" style="font-size:0.75rem; padding:4px 8px; height:auto; background:transparent!important; border:1px solid var(--mf-gold); color:var(--mf-gold)!important;"
                                onclick="window.metaforge.musicbrainz_submit.markHandled('${esc(c.mb_recording_id)}', 'submitted')" ${disabled}>
                            Mark Submitted
                        </button>
                        <button class="mf-btn-danger" style="font-size:0.75rem; padding:4px 8px;"
                                onclick="window.metaforge.musicbrainz_submit.markHandled('${esc(c.mb_recording_id)}', 'dismissed')" ${disabled}>
                            Dismiss
                        </button>
                    </div>
                    ${statusLabel}
                </td>
            </tr>
        `;
    },

    openInMusicBrainz: async function(recordingId) {
        this.updateStatus("Building seeded MusicBrainz submission...", "success");
        try {
            const seedRes = await fetch('/run_tool_logic/musicbrainz_submit/build_seed', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mb_recording_id: recordingId })
            });
            const seedData = await seedRes.json();
            if (seedData.status !== "success") {
                this.updateStatus(seedData.message || "Failed to build submission.", "error");
                return;
            }

            // Opens a genuine second top-level pywebview window (not an
            // iframe -- musicbrainz.org blocks framing entirely via
            // X-Frame-Options: DENY). Confirmed live 2026-07-09 this
            // shares the main window's persistent profile, so a
            // MusicBrainz login only has to happen once, ever.
            const openRes = await fetch('/open_mb_seeded_window', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: seedData.title, html: seedData.html })
            });
            const openData = await openRes.json();
            if (openData.status === "success") {
                this.updateStatus("MusicBrainz opened -- review and submit there, then come back and mark it here.", "success");
            } else {
                this.updateStatus(openData.message || "Failed to open MusicBrainz window.", "error");
            }
        } catch (e) {
            this.updateStatus("Network error building submission.", "error");
        }
    },

    markHandled: async function(recordingId, status) {
        try {
            const res = await fetch('/run_tool_logic/musicbrainz_submit/mark_handled', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mb_recording_id: recordingId, status: status })
            });
            const data = await res.json();
            if (data.status === "success") {
                this.updateStatus(`Marked ${status}.`, "success");
                this.loadCandidates();
            } else {
                this.updateStatus(data.message || "Failed to update status.", "error");
            }
        } catch (e) {
            this.updateStatus("Network error updating status.", "error");
        }
    },

    updateStatus: function(msg, type) {
        const el = document.getElementById('mbs-status-text');
        if (!el) return;
        el.innerText = msg;
        el.style.color = type === "error" ? "var(--status-error)" : "var(--status-success)";
    },

    // ======================================================
    // PERSONNEL CORRECTIONS (Phase 2)
    // ======================================================

    loadPersonnelCandidates: async function() {
        this.updateStatus("Loading personnel candidates...", "success");
        try {
            const res = await fetch('/run_tool_logic/musicbrainz_submit/list_personnel_candidates');
            const data = await res.json();
            if (data.status === "success") {
                this.state.personnelCandidates = data.candidates;
                this.state.personnelLoaded = true;
                this.renderPersonnelQueue();
                this.renderPersonnelCounts(data.counts);
                this.updateStatus(`${data.counts.pending} personnel candidate(s) awaiting review.`, "success");
            } else {
                this.updateStatus(data.message || "Failed to load personnel candidates.", "error");
            }
        } catch (e) {
            this.updateStatus("Network error loading personnel candidates.", "error");
        }
    },

    renderPersonnelCounts: function(counts) {
        const p = document.getElementById('mbs-p-count-pending');
        const s = document.getElementById('mbs-p-count-submitted');
        const d = document.getElementById('mbs-p-count-dismissed');
        if (p) p.innerText = counts.pending;
        if (s) s.innerText = counts.submitted;
        if (d) d.innerText = counts.dismissed;
    },

    renderPersonnelQueue: function() {
        const body = document.getElementById('mbs-p-queue-body');
        if (!body) return;

        if (this.state.personnelCandidates.length === 0) {
            body.innerHTML = '<tr><td colspan="4" style="padding:20px; text-align:center; opacity:0.6;">No personnel correction candidates found yet -- run Personnel Scout on an album to populate this queue. Note: credits committed before 2026-07-09 won\'t appear here even after that, since they predate recording-ID capture.</td></tr>';
            return;
        }

        const groups = this._groupByAlbum(this.state.personnelCandidates);
        body.innerHTML = groups.map(group => {
            const header = this._renderGroupHeader("personnel", group, 4);
            if (!this.state.expandedGroups.personnel.has(group.key)) return header;
            return header + group.rows.map(c => this._renderPersonnelRow(c)).join('');
        }).join('');
    },

    _renderPersonnelRow: function(c) {
        const esc = (s) => this.escapeHtml(s);
        const key = esc(c.key).replace(/'/g, "\\'");
        // Artist/Album is intentionally not repeated here -- it's shown
        // once in this row's group header (John's Yandex Mail-style
        // grouping, 2026-07-09), so each row only needs the identity
        // that varies within the album.
        const identityCells = `
                <td style="padding:8px 8px 8px 28px; color:var(--mf-gold);">${esc(c.name)}</td>
                <td style="padding:8px;">${esc(c.role)}</td>
                <td style="padding:8px;">
                    <div>${esc(c.provenance)}</div>
                    <div style="color:var(--text-message); font-size:0.75rem;">conf ${esc(c.confidence)}</div>
                </td>`;

        // Album-scoped credit (AI Web Search/manual entries -- no
        // single recording, see _candidate_key in musicbrainz_submit.py)
        // gets a per-track stepper instead of the single Open/Mark/
        // Dismiss row below (John, 2026-07-09).
        if (!c.mb_recording_id) {
            return this._renderAlbumScopeRow(c, key, identityCells);
        }

        const statusLabel = c.status === "pending" ? "" :
            `<div style="font-size:0.7rem; color:var(--text-message); margin-top:4px;">Marked ${esc(c.status)}</div>`;
        const disabled = c.status !== "pending" ? "disabled" : "";
        return `
            <tr style="border-bottom:1px solid #333; ${c.status !== 'pending' ? 'opacity:0.55;' : ''}">
                ${identityCells}
                <td style="padding:8px;">
                    <div style="display:flex; gap:6px; flex-wrap:wrap;">
                        <button class="mf-button-gold-fixed" style="font-size:0.75rem; padding:4px 8px; height:auto;"
                                onclick="window.metaforge.musicbrainz_submit.openPersonnelInMusicBrainz('${key}')" ${disabled}>
                            Open in MusicBrainz
                        </button>
                        <button class="mf-button-gold-fixed" style="font-size:0.75rem; padding:4px 8px; height:auto; background:transparent!important; border:1px solid var(--mf-gold); color:var(--mf-gold)!important;"
                                onclick="window.metaforge.musicbrainz_submit.markPersonnelHandled('${key}', 'submitted')" ${disabled}>
                            Mark Submitted
                        </button>
                        <button class="mf-btn-danger" style="font-size:0.75rem; padding:4px 8px;"
                                onclick="window.metaforge.musicbrainz_submit.markPersonnelHandled('${key}', 'dismissed')" ${disabled}>
                            Dismiss
                        </button>
                    </div>
                    ${statusLabel}
                </td>
            </tr>
        `;
    },

    // Album-scoped credits carry no single mb_recording_id -- MB's
    // Recording editor only ever edits one recording at a time, so
    // there's no single URL to seed for "this person played on the
    // album." Instead of dropping this data (which used to silently
    // exclude almost all AI Web Search/manual personnel from ever
    // reaching this queue) or firing one companion window per track at
    // once, this steps through the album's tracks one at a time --
    // John's own "assume it applies to every track, review track-by-
    // track" call (2026-07-09), with Skip/Dismiss escape hatches for the
    // real cases where that assumption is wrong (e.g. a percussionist
    // who likely only played a few tracks, not all sixteen).
    _renderAlbumScopeRow: function(c, key, identityCells) {
        const esc = (s) => this.escapeHtml(s);
        const total = (c.album_tracks || []).length;
        const done = Object.keys(c.track_progress || {}).length;

        if (total === 0) {
            return `
                <tr style="border-bottom:1px solid #333;">
                    ${identityCells}
                    <td style="padding:8px;">
                        <div style="color:var(--text-message); font-size:0.75rem; max-width:260px;">
                            No MusicBrainz recording IDs found yet for this album -- run MusicBrainz ID / Intelli-Tagger first.
                        </div>
                        <button class="mf-btn-danger" style="font-size:0.75rem; padding:4px 8px; margin-top:4px;"
                                onclick="window.metaforge.musicbrainz_submit.markPersonnelHandled('${key}', 'dismissed')">
                            Dismiss
                        </button>
                    </td>
                </tr>`;
        }

        if (c.status === "dismissed" || c.status === "submitted") {
            const submittedCount = Object.values(c.track_progress || {}).filter(v => v === "submitted").length;
            const skippedCount = Object.values(c.track_progress || {}).filter(v => v === "skipped").length;
            const summary = c.status === "dismissed" ? "Dismissed" :
                `${submittedCount} submitted, ${skippedCount} skipped (${total}/${total} tracks reviewed)`;
            return `
                <tr style="border-bottom:1px solid #333; opacity:0.55;">
                    ${identityCells}
                    <td style="padding:8px;"><div style="font-size:0.7rem; color:var(--text-message);">${esc(summary)}</div></td>
                </tr>`;
        }

        const currentTrack = (c.album_tracks || []).find(t => !(t.recording_id in (c.track_progress || {})));
        const stepNum = done + 1;
        const trackId = esc(currentTrack.recording_id).replace(/'/g, "\\'");
        const trackTitle = esc(currentTrack.title || `Track ${currentTrack.track_number}`);

        return `
            <tr style="border-bottom:1px solid #333;">
                ${identityCells}
                <td style="padding:8px;">
                    <div style="font-size:0.7rem; color:var(--mf-gold); margin-bottom:4px;">
                        Album-wide credit -- Track ${stepNum} of ${total}: "${trackTitle}"
                    </div>
                    <div style="display:flex; gap:6px; flex-wrap:wrap;">
                        <button class="mf-button-gold-fixed" style="font-size:0.75rem; padding:4px 8px; height:auto; background:transparent!important; border:1px solid var(--mf-gold); color:var(--mf-gold)!important;"
                                onclick="window.metaforge.musicbrainz_submit.openTrackSelectionModal('${key}')">
                            Select Tracks
                        </button>
                        <button class="mf-button-gold-fixed" style="font-size:0.75rem; padding:4px 8px; height:auto;"
                                onclick="window.metaforge.musicbrainz_submit.openPersonnelInMusicBrainz('${key}', '${trackId}')">
                            Submit to MB
                        </button>
                        <button class="mf-button-gold-fixed" style="font-size:0.75rem; padding:4px 8px; height:auto; background:transparent!important; border:1px solid var(--mf-gold); color:var(--mf-gold)!important;"
                                onclick="window.metaforge.musicbrainz_submit.markTrackProgress('${key}', '${trackId}', 'submitted')">
                            Mark Submitted, Next
                        </button>
                        <button class="mf-button-gold-fixed" style="font-size:0.75rem; padding:4px 8px; height:auto; background:transparent!important; border:1px solid var(--text-message); color:var(--text-message)!important;"
                                onclick="window.metaforge.musicbrainz_submit.markTrackProgress('${key}', '${trackId}', 'skipped')">
                            Skip Track
                        </button>
                        <button class="mf-btn-danger" style="font-size:0.75rem; padding:4px 8px;"
                                onclick="window.metaforge.musicbrainz_submit.markPersonnelHandled('${key}', 'dismissed')">
                            Dismiss Remaining
                        </button>
                    </div>
                    ${done > 0 ? `<div style="font-size:0.7rem; color:var(--text-message); margin-top:4px;">${done} of ${total} tracks already reviewed</div>` : ''}
                </td>
            </tr>`;
    },

    openPersonnelInMusicBrainz: async function(key, recordingId) {
        // recordingId is only passed for an album-scoped credit's
        // stepper step (the current track) -- a track-scoped candidate
        // already has its own recording and needs no override.
        this.updateStatus("Building seeded MusicBrainz submission...", "success");
        try {
            const body = { key: key };
            if (recordingId) body.recording_id = recordingId;
            const seedRes = await fetch('/run_tool_logic/musicbrainz_submit/build_personnel_seed', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            const seedData = await seedRes.json();
            if (seedData.status !== "success") {
                this.updateStatus(seedData.message || "Failed to build submission.", "error");
                return;
            }

            const openRes = await fetch('/open_mb_seeded_window', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: seedData.title, html: seedData.html })
            });
            const openData = await openRes.json();
            if (openData.status !== "success") {
                this.updateStatus(openData.message || "Failed to open MusicBrainz window.", "error");
                return;
            }

            // artist_match is null when the candidate already carried a
            // real MBID (no live search needed) -- only surface the
            // caveat when a fuzzy name search actually ran, since that's
            // the case genuinely needing extra scrutiny before submitting.
            if (seedData.artist_match) {
                this.updateStatus(`MusicBrainz opened -- artist matched via search (score ${seedData.artist_match.score}/100) to "${seedData.artist_match.name}", please confirm this is correct before submitting.`, "success");
            } else {
                this.updateStatus("MusicBrainz opened -- review and submit there, then come back and mark it here.", "success");
            }
        } catch (e) {
            this.updateStatus("Network error building submission.", "error");
        }
    },

    markPersonnelHandled: async function(key, status) {
        try {
            const res = await fetch('/run_tool_logic/musicbrainz_submit/mark_personnel_handled', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: key, status: status })
            });
            const data = await res.json();
            if (data.status === "success") {
                this.updateStatus(`Marked ${status}.`, "success");
                this.loadPersonnelCandidates();
            } else {
                this.updateStatus(data.message || "Failed to update status.", "error");
            }
        } catch (e) {
            this.updateStatus("Network error updating status.", "error");
        }
    },

    markTrackProgress: async function(key, recordingId, status) {
        try {
            const res = await fetch('/run_tool_logic/musicbrainz_submit/mark_track_progress', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: key, recording_id: recordingId, status: status })
            });
            const data = await res.json();
            if (data.status === "success") {
                this.updateStatus(`Track ${status}. Advancing to the next track...`, "success");
                this.loadPersonnelCandidates();
            } else {
                this.updateStatus(data.message || "Failed to update track progress.", "error");
            }
        } catch (e) {
            this.updateStatus("Network error updating track progress.", "error");
        }
    },

    // Track-selection modal (John, 2026-07-09) -- "Open Track 1" gave no
    // way to see the whole album or scope a credit down before diving
    // into the stepper track-by-track, which is genuinely wrong for a
    // credit that likely only applies to 1-2 of an album's tracks (e.g.
    // a single guest musician), not all of them. Pure MetaForge markup,
    // same fixed-position-div pattern as database_tools/album_editor.js's
    // openModal() -- this never touches musicbrainz.org at all, so it
    // has nothing to do with the separate companion-window mechanism
    // that DOES need its own top-level window (MB blocks iframing).
    // Already-resolved tracks are shown, not hidden, but locked --
    // reflects their real submitted/skipped state with a disabled
    // checkbox, so reopening this modal after using the stepper doesn't
    // let a decision already made get silently re-litigated.
    openTrackSelectionModal: function(key) {
        if (document.getElementById("mbs-track-modal")) return;
        const c = this.state.personnelCandidates.find(x => x.key === key);
        if (!c) return;
        const esc = (s) => this.escapeHtml(s);
        const progress = c.track_progress || {};

        const rows = (c.album_tracks || []).map(t => {
            const resolved = progress[t.recording_id];
            const checked = resolved ? resolved === "submitted" : true;
            const disabled = !!resolved;
            const statusNote = resolved ? ` <span style="color:var(--text-message); font-size:0.75rem;">(already ${esc(resolved)})</span>` : "";
            const idEsc = esc(t.recording_id).replace(/'/g, "\\'");
            return `
                <label style="display:flex; align-items:center; gap:8px; padding:4px 0; ${disabled ? 'opacity:0.55;' : ''}">
                    <input type="checkbox" data-recording-id="${idEsc}" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""}>
                    <span>${esc(t.track_number)}. ${esc(t.title)}</span>${statusNote}
                </label>`;
        }).join('');

        const modal = document.createElement('div');
        modal.id = "mbs-track-modal";
        modal.style = "position:fixed; top:12%; left:30%; width:40%; max-height:70%; display:flex; flex-direction:column; background:var(--bg-main); border:1px solid var(--mf-gold); padding:20px; z-index:10000;";
        modal.innerHTML = `
            <h3 style="color:var(--mf-gold); margin-top:0;">Select Tracks -- ${esc(c.name)} (${esc(c.role)})</h3>
            <p style="font-size:0.75rem; color:var(--text-message);">
                Every track is checked by default (MetaForge Studio's assumption is that an album-wide credit applies throughout). Uncheck any track you know this credit doesn't apply to -- unchecked tracks are marked skipped immediately, no need to step through each one individually.
            </p>
            <div style="overflow-y:auto; flex:1; border-top:1px solid #333; border-bottom:1px solid #333; padding:8px 0; margin:8px 0;">
                ${rows}
            </div>
            <div style="display:flex; gap:10px; justify-content:flex-end;">
                <button class="mf-button-gold-fixed" onclick="window.metaforge.musicbrainz_submit.confirmTrackSelection('${esc(key).replace(/'/g, "\\'")}')">Confirm Selection</button>
                <button class="mf-button-gold-fixed" style="background:transparent!important; border:1px solid var(--mf-gold); color:var(--mf-gold)!important;"
                        onclick="document.getElementById('mbs-track-modal').remove()">Cancel</button>
            </div>
        `;
        document.body.appendChild(modal);
    },

    confirmTrackSelection: async function(key) {
        const modal = document.getElementById("mbs-track-modal");
        if (!modal) return;
        const uncheckedIds = Array.from(modal.querySelectorAll('input[type="checkbox"]:not(:checked):not(:disabled)'))
            .map(el => el.getAttribute("data-recording-id"));
        modal.remove();

        try {
            const res = await fetch('/run_tool_logic/musicbrainz_submit/apply_track_selection', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: key, unchecked_recording_ids: uncheckedIds })
            });
            const data = await res.json();
            if (data.status === "success") {
                this.updateStatus(uncheckedIds.length > 0 ? `${uncheckedIds.length} track(s) marked skipped.` : "Selection confirmed.", "success");
                this.loadPersonnelCandidates();
            } else {
                this.updateStatus(data.message || "Failed to apply track selection.", "error");
            }
        } catch (e) {
            this.updateStatus("Network error applying track selection.", "error");
        }
    }
};
/* --- END OF FILE musicbrainz_submit.js --- */
