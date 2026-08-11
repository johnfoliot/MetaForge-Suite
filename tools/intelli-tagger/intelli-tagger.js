/* --- START OF FILE intelli-tagger.js --- */
/**
 * MetaForge Studio: Intelli-Tagger Logic Bridge
 * Build 4.0.8: Acoustic Wait Indicator Removal
 * Role: Orchestrates UI state, manifest ingestion, and forensic feedback.
 * Accessibility: WCAG 2.2 AA | COGA 4.5.4
 */

window.metaforge = window.metaforge || {};

window.metaforge.intelli_tagger = {
    state: {
        isProcessing: false,
        dbWriteEnabled: true,
        lastTrigger: null,
        observer: null,
        releaseYear: "Unknown",
        mbTrackMap: [],
        releaseGroupFirstDate: "",
        releaseGroupSecondaryTypes: []
    },

    /**
     * Directive XIX: SPA Re-entry Protocol
     * Initializes UI state and triggers manifest ingestion if path exists.
     */
    init: function() {
        const header = document.getElementById('it-header');
        // Prevent double-initialization via the SPA orchestrator
        if (!header || header.getAttribute('data-synced') === 'true') return;
        header.setAttribute('data-synced', 'true');

        console.log("METAFORGE: Intelli-Tagger Logic Bridge initializing...");
        
        // 1. Hook Input Listeners for real-time validation
        const inputs = ['it-artist', 'it-album', 'it-mb-artist-id', 'it-mb-album-id', 'it-mb-group-id', 'it-mb-country'];
        inputs.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('input', () => this.validate());
        });

        // 2. Ingest Context from Global Orchestrator (10ms Paint Guard)
        setTimeout(() => this.ingestContext(), 10);
        
        // 3. Setup Re-entry Watcher (MutationObserver)
        this.setupReentryWatcher();
    },

    /**
     * Logic: Forensic Ingestion
     * Physically pulls pathing and seed data from the Global Orchestrator.
     */
    ingestContext: async function() {
        const path = window.mf_context_path || document.getElementById('it-path')?.value;
        if (!path) {
            console.log("METAFORGE: No context path detected. Awaiting manual input.");
            return;
        }

        const pathIn = document.getElementById('it-path');
        if (pathIn) pathIn.value = path;

        console.log(`METAFORGE: Ingesting forensic context for: ${path}`);

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
                console.log("METAFORGE: Manifest seeds recovered. Syncing UI...");
                
                // Direct Mapping of Forensic Seeds
                this.setFieldValue('it-artist', m.artist_seed);
                this.setFieldValue('it-album', m.album_seed);
                this.setFieldValue('it-mb-artist-id', m.mb_artist_id);
                this.setFieldValue('it-mb-album-id', m.mb_album_id);
                this.setFieldValue('it-mb-group-id', m.mb_release_group_id);
                // Pre-fill with the ARTIST's own home country (MB artist
                // entity's "country", e.g. where a band formed) -- what
                // Personnel Bridge/IPM actually needs -- not this specific
                // release's distribution country. Falls back to the release
                // country only when MB had no artist-level country on file
                // (e.g. an obscure/incomplete MB artist entry), so the field
                // is never left blank. Still just a starting point: John
                // edits this by hand whenever MB's data is wrong, same as
                // always -- whatever's here when Run is clicked wins.
                this.setFieldValue('it-mb-country', m.mb_artist_country || m.mb_release_country);
                
                // Persist Year for reporting fallback
                this.state.releaseYear = m.release_year || "Unknown";
                // Persist per-track MB IDs so run() can send them for the FAST_PATH lookup
                this.state.mbTrackMap = m.mb_track_map || [];
                // Persist release-group data for original-year resolution's tier 2
                this.state.releaseGroupFirstDate = m.mb_release_group_first_date || "";
                this.state.releaseGroupSecondaryTypes = m.mb_release_group_secondary_types || [];
            } else {
                // No manifest for this path -- don't carry over a previous album's track map
                this.state.mbTrackMap = [];
                this.state.releaseGroupFirstDate = "";
                this.state.releaseGroupSecondaryTypes = [];
            }
        } catch (err) {
            console.error("METAFORGE: Context ingestion failure:", err);
        } finally {
            window.mf_context_path = null; // Flush global context
            this.validate();
        }
    },

    /**
     * UI Logic: State Validation
     */
    validate: function() {
        const artist = document.getElementById('it-artist')?.value.trim();
        const album = document.getElementById('it-album')?.value.trim();
        const startBtn = document.getElementById('it-start-btn');
        const searchMbBtn = document.getElementById('it-search-mb-btn');

        const mbArtist = document.getElementById('it-mb-artist-id')?.value.trim();
        const mbAlbum = document.getElementById('it-mb-album-id')?.value.trim();

        if (startBtn) {
            const isReady = (artist && album);
            startBtn.disabled = !isReady;
        }

        if (searchMbBtn) {
            // Hide discovery logic button if forensic IDs are already present
            searchMbBtn.style.display = (mbArtist && mbAlbum) ? 'none' : 'block';
        }
    },

    setFieldValue: function(id, value) {
        const el = document.getElementById(id);
        if (el) el.value = value || "";
    },

    /**
     * Logic Bridge: Toggle Primitive Integration
     */
    toggleDatabase: function(container) {
        const wrapper = container.querySelector('[role="switch"]');
        const label = container.querySelector('.mf-toggle-label');
        if (!wrapper || !label || this.state.isProcessing) return;

        const isChecked = wrapper.getAttribute('aria-checked') === 'true';
        this.state.dbWriteEnabled = !isChecked;
        
        wrapper.setAttribute('aria-checked', this.state.dbWriteEnabled.toString());
        label.innerHTML = this.state.dbWriteEnabled ? 
            "Also Write to <br>MetaForge Database: On" : 
            "Also Write to <br>MetaForge Database: Off";
    },

    pickFolder: async function() {
        try {
            const response = await fetch('/select_folder');
            const data = await response.json();
            
            if (data.path) {
                const pathIn = document.getElementById('it-path');
                if (pathIn) {
                    pathIn.value = data.path;
                    this.ingestContext();
                }
            }
        } catch (err) {
            console.error("METAFORGE: Folder selection failed:", err);
        }
    },

    /**
     * Various Artists Genre Gate: individual track artists on a VA
     * compilation are often obscure enough that Gemini has weak or no
     * training knowledge of them (unlike a recognizable album artist),
     * causing per-track genre to drift wildly (confirmed live 2026-07-17:
     * a Gospel compilation drifted as far as "Rock" / "Punk & Post-Punk").
     * The user already knows the real genre -- it's why the album is filed
     * where it is -- so this asks once per album instead of guessing per
     * track. Returns the chosen genre string, or null if the user chose
     * "Skip / Let AI Decide" (or taxonomy couldn't be fetched at all).
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

        if (!genres.length) return null;

        return new Promise((resolve) => {
            const modal = document.createElement('div');
            modal.id = "it-genre-gate-modal";
            modal.setAttribute('role', 'dialog');
            modal.setAttribute('aria-modal', 'true');
            modal.setAttribute('aria-labelledby', 'it-genre-gate-title');
            modal.style = "position:fixed; top:25%; left:35%; width:30%; background:var(--bg-main); border:1px solid var(--mf-gold); padding:20px; z-index:10000; box-shadow: 0 0 20px rgba(0,0,0,0.5);";
            modal.innerHTML = `
                <h3 id="it-genre-gate-title" style="color:var(--mf-gold); margin-top:0;">Confirm Album Genre</h3>
                <p style="color:var(--text-output); font-size:0.8rem; margin-bottom:8px;">
                    This album is filed under "Various Artists." Individual track
                    artists are often obscure enough that AI genre classification
                    drifts wildly per track. Confirm a Parent Genre to keep every
                    track consistent, or let the AI decide freely per track.
                </p>
                <select id="it-genre-gate-select" class="it-input-text" style="color:#000!important; margin-bottom:15px;">
                    ${genres.map(g => `<option value="${g}">${g}</option>`).join('')}
                </select>
                <div style="display:flex; gap:10px; justify-content:flex-end;">
                    <button type="button" class="mf-button-gold-fixed" id="it-genre-gate-confirm">Confirm</button>
                    <button type="button" class="mf-button-gold-fixed" id="it-genre-gate-skip">Skip / Let AI Decide</button>
                </div>
            `;
            document.body.appendChild(modal);

            const select = document.getElementById('it-genre-gate-select');
            select.focus();

            document.getElementById('it-genre-gate-confirm').addEventListener('click', () => {
                const chosen = select.value;
                modal.remove();
                resolve(chosen);
            });
            document.getElementById('it-genre-gate-skip').addEventListener('click', () => {
                modal.remove();
                resolve(null);
            });
        });
    },

    /**
     * Orchestration: Run Phase 1-7 Batch
     */
    run: async function() {
        if (this.state.isProcessing) return;

        const artistVal = (document.getElementById('it-artist').value || '').trim().toLowerCase();
        let forcedParentGenre = null;

        if (artistVal === "various artists") {
            forcedParentGenre = await this.promptForcedGenre();
        }

        const consoleBox = document.getElementById('it-console');
        const progressFill = document.getElementById('it-progress-fill');
        const progressLabel = document.getElementById('it-progress-label');
        const path = document.getElementById('it-path').value;

        this.state.isProcessing = true;
        const startBtn = document.getElementById('it-start-btn');
        if (startBtn) startBtn.disabled = true;

        consoleBox.innerHTML = '';

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
            db_write: this.state.dbWriteEnabled,
            forced_parent_genre: forcedParentGenre
        };

        try {
            const res = await fetch('/run_tool_logic/intelli-tagger/run_batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            // One-shot guard -- buffer only ever grows (see the marker-
            // detection note below), so an unguarded includes() check would
            // fire the chime again on every remaining read() after
            // BATCH_COMPLETE first appears.
            let chimePlayed = false;

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                // stream:true correctly buffers a multi-byte UTF-8 character
                // (e.g. a curly apostrophe) that gets split across two reads,
                // instead of mangling it into a replacement character.
                const chunk = decoder.decode(value, { stream: true });
                // Marker checks run against the full accumulated buffer, not
                // just this one chunk -- a marker like HANDOFF_READY can land
                // split across two separate reads, and checking only the
                // latest chunk would silently miss it.
                buffer += chunk;

                // Progress Hook Extraction (Meta-parsing for the Progress Bar).
                // buffer only ever grows (see marker-detection note above), so
                // a non-global match() would keep re-finding the very FIRST
                // progress event (e.g. "5:Ingesting Content") forever -- the
                // bar would look stuck even while later per-track progress
                // kept arriving further along in the same buffer. Take the
                // LAST match instead.
                // (.+?)\s*--> stops at the literal closing marker rather than
                // the first hyphen -- labels can now safely contain their own
                // hyphens (e.g. "Tagging Track 12/25 - Resolving Original Year").
                const progMatches = [...buffer.matchAll(/PROGRESS:(\d+):(.+?)\s*-->/g)];
                if (progMatches.length > 0) {
                    const progMatch = progMatches[progMatches.length - 1];
                    if (progressFill) progressFill.style.width = `${progMatch[1]}%`;
                    if (progressLabel) progressLabel.innerText = progMatch[2];
                }

                if (buffer.includes('HANDOFF_READY')) {
                    const handoff = document.getElementById('it-handoff-area');
                    if (handoff) handoff.style.display = 'block';
                }

                // Audible completion cue (John's request, 2026-08-08) --
                // BATCH_COMPLETE was already yielded by the backend at the
                // very end of every run (intelli-tagger.py) but nothing on
                // this side ever looked for it before now.
                if (!chimePlayed && buffer.includes('BATCH_COMPLETE')) {
                    chimePlayed = true;
                    this.playCompletionChime();
                }

                consoleBox.insertAdjacentHTML('beforeend', chunk);

                // Remove acoustic wait indicator on first track result
                if (buffer.includes('it-log-row')) {
                    const wait = document.getElementById('it-acoustic-wait');
                    if (wait) wait.parentNode.removeChild(wait);
                }

                consoleBox.scrollTop = consoleBox.scrollHeight;
            }
        } catch (err) {
            consoleBox.insertAdjacentHTML('beforeend', `<div class="it-val-error">Critical Failure: ${err.message}</div>`);
        } finally {
            this.state.isProcessing = false;
            this.validate();
        }
    },

    // Short two-tone chime, synthesized directly via Web Audio -- no sound
    // asset file to bundle/maintain. Wrapped in try/catch since autoplay-
    // policy or an unsupported browser must never break the actual tagging
    // result over a missed notification sound.
    playCompletionChime: function() {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const now = ctx.currentTime;
            const notes = [659.25, 440.00]; // E5 -> A4
            notes.forEach((freq, i) => {
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
        const path = document.getElementById('it-path').value;
        if (window.mfAdvanceWorkflow) {
            window.mfAdvanceWorkflow('musicbrainz_id', path);
        }
    },

    advance: function() {
        const path = document.getElementById('it-path').value;
        if (window.mfAdvanceWorkflow) {
            window.mfAdvanceWorkflow('personnel', path);
        }
    },

    // --- DOCUMENTATION & FOCUS ---

    openHelp: async function() {
        const panel = document.getElementById('it-help-panel');
        const body = document.getElementById('it-help-body');
        const title = document.getElementById('it-help-title');
        this.state.lastTrigger = document.activeElement;
        if (!panel || !body) return;

        try {
            const response = await fetch('/tool_asset/intelli-tagger/help.mfi');
            body.innerHTML = await response.text();
            panel.style.display = 'flex';
            setTimeout(() => { 
                if (title) { 
                    title.setAttribute('tabindex', '-1'); 
                    title.focus(); 
                } 
            }, 20);
        } catch (err) {
            body.innerHTML = "Documentation offline.";
            panel.style.display = 'flex';
        }
    },

    closeHelp: function() {
        const panel = document.getElementById('it-help-panel');
        if (panel) {
            panel.style.display = 'none';
            if (this.state.lastTrigger) this.state.lastTrigger.focus();
        }
    },

    setupReentryWatcher: function() {
        if (this.state.observer) this.state.observer.disconnect();
        const stage = document.getElementById('mfi-content');
        if (!stage) return;
        this.state.observer = new MutationObserver((mutations) => {
            for (let mutation of mutations) {
                if (mutation.addedNodes.length && document.getElementById('it-header')) {
                    this.init();
                    break;
                }
            }
        });
        this.state.observer.observe(stage, { childList: true });
    }
};

// Auto-boot
window.metaforge.intelli_tagger.init();
/* --- END OF FILE intelli-tagger.js --- */