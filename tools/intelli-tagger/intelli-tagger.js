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
        mbTrackMap: []
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
                this.setFieldValue('it-mb-country', m.mb_release_country);
                
                // Persist Year for reporting fallback
                this.state.releaseYear = m.release_year || "Unknown";
                // Persist per-track MB IDs so run() can send them for the FAST_PATH lookup
                this.state.mbTrackMap = m.mb_track_map || [];
            } else {
                // No manifest for this path -- don't carry over a previous album's track map
                this.state.mbTrackMap = [];
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
     * Orchestration: Run Phase 1-7 Batch
     */
    run: async function() {
        if (this.state.isProcessing) return;

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
            db_write: this.state.dbWriteEnabled
        };

        try {
            const res = await fetch('/run_tool_logic/intelli-tagger/run_batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const reader = res.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                
                // Progress Hook Extraction (Meta-parsing for the Progress Bar)
                const progMatch = chunk.match(/PROGRESS:(\d+):([^-]+)/);
                if (progMatch) {
                    if (progressFill) progressFill.style.width = `${progMatch[1]}%`;
                    if (progressLabel) progressLabel.innerText = progMatch[2];
                }

                if (chunk.includes('HANDOFF_READY')) {
                    const handoff = document.getElementById('it-handoff-area');
                    if (handoff) handoff.style.display = 'block';
                }

                consoleBox.insertAdjacentHTML('beforeend', chunk);

                // Remove acoustic wait indicator on first track result
                if (chunk.includes('it-log-row')) {
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