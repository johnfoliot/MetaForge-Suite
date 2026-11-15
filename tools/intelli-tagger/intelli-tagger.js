/* --- START OF FILE intelli-tagger.js --- */
/**
 * MetaForge Studio: Intelli-Tagger (pipeline step 3 of 3)
 * v2 (2026-11-13): per-tool pass.
 *  - The run is an event stream (MFEvents): one entry per track with every
 *    value in full; problems are red/orange and spoken; the Next-step bar
 *    (Album Personnel + Bio Builder) appears only after a clean run.
 *  - Real <form>: Enter starts the run. Native switch for database writing.
 *    Native <dialog> for the Various Artists genre question.
 *  - MusicBrainz IDs disclosure: collapsed when the IDs arrive filled in.
 */

window.metaforge = window.metaforge || {};

window.metaforge.intelli_tagger = {
    state: {
        isProcessing: false,
        observer: null,
        releaseYear: "Unknown",
        mbTrackMap: [],
        releaseGroupFirstDate: "",
        releaseGroupSecondaryTypes: []
    },

    /** SPA re-entry: runs each time the tool's screen is built. */
    init: function() {
        const header = document.getElementById('it-header');
        if (!header || header.getAttribute('data-synced') === 'true') return;
        header.setAttribute('data-synced', 'true');

        this.wire();
        setTimeout(() => this.ingestContext(), 10);
        this.setupReentryWatcher();
    },

    /** Event wiring (was inline onclick/onkeydown attributes). */
    wire: function() {
        const form = document.getElementById('it-form');
        if (!form || form.dataset.wired) return;
        form.dataset.wired = 'true';

        form.addEventListener('submit', (e) => {
            e.preventDefault();
            if (!document.getElementById('it-start-btn')?.disabled) this.run();
        });
        form.addEventListener('input', () => this.validate());
        document.getElementById('it-browse-btn')?.addEventListener('click', () => this.pickFolder());
        document.getElementById('it-search-mb-btn')?.addEventListener('click', () => this.backtrackToMB());
        document.getElementById('it-personnel-btn')?.addEventListener('click', () => this.advance('personnel'));
        document.getElementById('it-bio-btn')?.addEventListener('click', () => this.advance('biography'));
    },

    ingestContext: async function() {
        const path = window.mf_context_path || document.getElementById('it-path')?.value;
        if (!path) { this.validate(); return; }
        const pathIn = document.getElementById('it-path');
        if (pathIn) pathIn.value = path;

        try {
            const res = await fetch('/run_tool_logic/intelli-tagger/get_context', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path })
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            if (data.status === "success" && data.manifest) {
                const m = data.manifest;
                this.setFieldValue('it-artist', m.artist_seed);
                this.setFieldValue('it-album', m.album_seed);
                this.setFieldValue('it-mb-artist-id', m.mb_artist_id);
                this.setFieldValue('it-mb-album-id', m.mb_album_id);
                this.setFieldValue('it-mb-group-id', m.mb_release_group_id);
                // The ARTIST's home country (where a band formed), which
                // Personnel/IPM need; falls back to the release country only
                // when MusicBrainz has no artist-level country. Editable:
                // whatever is here when the run starts wins.
                this.setFieldValue('it-mb-country', m.mb_artist_country || m.mb_release_country);
                this.state.releaseYear = m.release_year || "Unknown";
                this.state.mbTrackMap = m.mb_track_map || [];
                this.state.releaseGroupFirstDate = m.mb_release_group_first_date || "";
                this.state.releaseGroupSecondaryTypes = m.mb_release_group_secondary_types || [];
            } else {
                // No manifest for this path: don't carry over a previous album's data.
                this.state.mbTrackMap = [];
                this.state.releaseGroupFirstDate = "";
                this.state.releaseGroupSecondaryTypes = [];
            }
        } catch (err) {
            console.error("METAFORGE: Context ingestion failure:", err);
        } finally {
            window.mf_context_path = null;
            this.validate(true);
        }
    },

    /**
     * Begin Tagging needs Artist and Album (disabled until then, by design).
     * The MusicBrainz IDs disclosure: collapsed + "(filled in from step 2)"
     * when all three are present; open + a way back to step 2 when not.
     * `settleIds` re-applies open/closed (only on load, so typing in the
     * fields never collapses the box under the user's cursor).
     */
    validate: function(settleIds) {
        const v = (id) => (document.getElementById(id)?.value || '').trim();
        const startBtn = document.getElementById('it-start-btn');
        if (startBtn) startBtn.disabled = !(v('it-artist') && v('it-album')) || this.state.isProcessing;

        const allIds = v('it-mb-artist-id') && v('it-mb-album-id') && v('it-mb-group-id');
        const searchBtn = document.getElementById('it-search-mb-btn');
        if (searchBtn) searchBtn.hidden = !!(v('it-mb-artist-id') && v('it-mb-album-id'));
        const stateText = document.getElementById('it-ids-state');
        if (stateText) stateText.textContent = allIds ? '(filled in from step 2)' : '(Recommended)';
        if (settleIds) {
            const box = document.getElementById('it-ids');
            if (box) box.open = !allIds;
        }
    },

    setFieldValue: function(id, value) {
        const el = document.getElementById(id);
        if (el) el.value = value || "";
    },

    pickFolder: async function() {
        try {
            const response = await fetch('/select_folder');
            const data = await response.json();
            if (data.path) {
                document.getElementById('it-path').value = data.path;
                this.ingestContext();
            }
        } catch (err) {
            console.error("METAFORGE: Folder selection failed:", err);
        }
    },

    /**
     * Various Artists genre question. Individual track artists on a VA
     * compilation are often obscure, so the AI's per-track genre drifts
     * (confirmed live 2026-07-17: a Gospel compilation drifted to "Rock").
     * Asks once per album. Resolves the chosen genre, or null for "let the
     * AI decide" (Skip, Esc, or the taxonomy couldn't be loaded).
     */
    promptForcedGenre: async function() {
        let genres = [];
        try {
            const res = await fetch('/run_tool_logic/intelli-tagger/get_taxonomy');
            const data = await res.json();
            if (data.status === "success") genres = data.genres || [];
        } catch (err) {
            console.error("METAFORGE: Taxonomy fetch failed:", err);
        }
        const dialog = document.getElementById('it-genre-dialog');
        const select = document.getElementById('it-genre-select');
        if (!genres.length || !dialog || !select) return null;

        select.replaceChildren(...genres.map(g => new Option(g, g)));
        return new Promise((resolve) => {
            dialog.addEventListener('close', () => {
                resolve(dialog.returnValue === 'confirm' ? select.value : null);
            }, { once: true });
            dialog.returnValue = '';
            dialog.showModal();     // focus goes to the select (first control)
        });
    },

    run: async function() {
        if (this.state.isProcessing) return;

        const artistVal = (document.getElementById('it-artist').value || '').trim().toLowerCase();
        const forcedParentGenre = artistVal === "various artists" ? await this.promptForcedGenre() : null;

        const consoleBox = document.getElementById('it-console');
        const fieldset = document.getElementById('it-fieldset');
        const path = document.getElementById('it-path').value;
        const dbWrite = document.getElementById('it-db-write').checked;

        this.state.isProcessing = true;
        fieldset.disabled = true;
        consoleBox.replaceChildren();
        document.getElementById('it-handoff').hidden = true;
        this.setProgress(0, 'Starting Intelli-Tagger…');

        const payload = {
            path: path,
            artist: document.getElementById('it-artist').value,
            album: document.getElementById('it-album').value,
            mb_ids: {
                artist: document.getElementById('it-mb-artist-id').value,
                album: document.getElementById('it-mb-album-id').value,
                group: document.getElementById('it-mb-group-id').value,
                country: document.getElementById('it-mb-country').value
            },
            mb_track_map: this.state.mbTrackMap,
            release_year: this.state.releaseYear,
            mb_release_group_first_date: this.state.releaseGroupFirstDate,
            mb_release_group_secondary_types: this.state.releaseGroupSecondaryTypes,
            db_write: dbWrite,
            forced_parent_genre: forcedParentGenre
        };

        let handoff = false;
        try {
            const res = await fetch('/run_tool_logic/intelli-tagger/run_batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            await window.MFEvents.read(res, {
                log: consoleBox,
                onSignal: (name, data) => {
                    if (name === 'progress') this.setProgress(data.percent, data.label);
                    else if (name === 'handoff_ready') handoff = true;
                    // Audible completion cue (John's request, 2026-08-08).
                    else if (name === 'batch_complete') this.playCompletionChime();
                }
            });
        } catch (err) {
            window.MFEvents.render(consoleBox, { kind: 'error', text: `The run stopped: ${err.message}` });
            window.MFAnnounce(`Error: the run stopped: ${err.message}`, { urgent: true });
        } finally {
            this.state.isProcessing = false;
            fieldset.disabled = false;
            this.validate();
        }
        if (handoff) this.showHandoff();
    },

    setProgress: function(percent, label) {
        const fill = document.getElementById('it-progress-fill');
        const text = document.getElementById('it-progress-label');
        const bar = document.getElementById('it-progress-container');
        const pct = Math.max(0, Math.min(100, Number(percent) || 0));
        if (fill) fill.style.width = `${pct}%`;
        if (text && label) text.textContent = label;
        if (bar) {
            bar.setAttribute('aria-valuenow', String(Math.round(pct)));
            if (label) bar.setAttribute('aria-valuetext', `${label} (${Math.round(pct)}%)`);
        }
    },

    /** Focus goes to the first next step: the control last used (Begin Tagging) was disabled. */
    showHandoff: function() {
        const bar = document.getElementById('it-handoff');
        if (!bar) return;
        bar.hidden = false;
        document.getElementById('it-personnel-btn')?.focus();
    },

    // Short two-tone chime, synthesized via Web Audio (no sound file to
    // bundle). Never allowed to break the result over a missed sound.
    playCompletionChime: function() {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const now = ctx.currentTime;
            [659.25, 440.00].forEach((freq, i) => {   // E5 -> A4
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.value = freq;
                const start = now + i * 0.12;
                gain.gain.setValueAtTime(0, start);
                gain.gain.linearRampToValueAtTime(0.3, start + 0.02);
                gain.gain.exponentialRampToValueAtTime(0.001, start + 0.5);
                osc.connect(gain).connect(ctx.destination);
                osc.start(start);
                osc.stop(start + 0.5);
            });
        } catch (e) {
            console.warn('Completion chime failed:', e);
        }
    },

    backtrackToMB: function() {
        window.mfAdvanceWorkflow?.('musicbrainz_id', document.getElementById('it-path').value);
    },

    advance: function(toolId) {
        window.mfAdvanceWorkflow?.(toolId, document.getElementById('it-path').value);
    },

    setupReentryWatcher: function() {
        if (this.state.observer) this.state.observer.disconnect();
        const stage = document.getElementById('mfi-content');
        if (!stage) return;
        this.state.observer = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                if (mutation.addedNodes.length && document.getElementById('it-header')) {
                    this.init();
                    break;
                }
            }
        });
        this.state.observer.observe(stage, { childList: true });
    }
};

window.metaforge.intelli_tagger.init();
/* --- END OF FILE intelli-tagger.js --- */
