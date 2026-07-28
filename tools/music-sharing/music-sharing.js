/* --- START OF FILE music-sharing.js --- */
/**
 * Music Sharing Studio: Logic Bridge. Build 1.0.3
 * Role: Handles track selection, progress rendering, and studio previews.
 * Build 1.0.3: Hardened SPA Re-entry (Directive XIX) and Accessibility (Emoji Scrub).
 */

// --- 1. NAMESPACE INITIALIZATION ---
window.metaforge = window.metaforge || {};
window.metaforge.sharing = {
    
    lastTrigger: null,
    isRendering: false,
    selectedPath: null,

    /**
     * SPA Re-entry Protocol (Directive XIX)
     * Resets or synchronizes UI state upon navigation back to the tool.
     */
    init: function() {
        // 10ms Paint Guard to ensure DOM stability
        setTimeout(() => {
            const header = document.getElementById('sharing-info-label');
            if (!header) return;

            console.log("METAFORGE: Music Sharing Studio awakening...");

            // If not currently rendering, ensure the UI is in a clean "Standby" state
            if (!this.isRendering) {
                this.resetStudio();
                const previewImg = document.getElementById('sharing-preview-art');
                if (previewImg && !this.selectedPath) {
                    previewImg.src = '/ui/images/no-photo.png';
                    previewImg.style.opacity = '0.3';
                }
            }
        }, 10);
    },

    /**
     * Entry Point: Invokes the thread-safe Global File Picker.
     */
    pickFile: async function() {
        if (this.isRendering) return;

        try {
            const response = await fetch('/select_file');
            const data = await response.json();

            if (data.path) {
                this.selectedPath = data.path;
                document.getElementById('sharing-target-path').value = data.path;
                
                this.resetStudio();
                this.syncPreview(data.path);
                
                const btn = document.getElementById('btn-generate-video');
                if (btn) {
                    btn.disabled = false;
                    btn.style.opacity = '1';
                    btn.style.cursor = 'pointer';
                }
            }
        } catch (err) {
            console.error("Music Sharing: Picker failure", err);
        }
    },

    /**
     * Preview Engine: Localizes album art and updates the 250px replica.
     */
    syncPreview: async function(path) {
        const previewImg = document.getElementById('sharing-preview-art');
        const statusMsg = document.getElementById('sharing-status-msg');
        const wrapper = document.getElementById('sharing-progress-wrapper');

        if (!previewImg) return;
        
        try {
            const response = await fetch('/run_tool_logic/music-sharing/get_preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path })
            });
            const data = await response.json();

            if (wrapper) wrapper.style.display = 'block';
            if (statusMsg) statusMsg.className = 'data-text status-working';

            if (data.art_url) {
                previewImg.src = data.art_url;
                previewImg.style.opacity = '1';
                if (statusMsg) statusMsg.innerText = `Studio Ready: ${data.filename}`;
            } else {
                previewImg.src = '/ui/images/logo_silver.svg';
                previewImg.style.opacity = '0.3';
                if (statusMsg) statusMsg.innerText = "Ready (Using fallback branding)";
            }
        } catch (e) { console.error("Preview Sync Error", e); }
    },

    /**
     * Studio Progress Engine: Orchestrates FFmpeg.
     * Sanitizes symbols for AT during real-time status updates.
     */
    runRender: async function() {
        if (this.isRendering || !this.selectedPath) return;

        const wrapper = document.getElementById('sharing-progress-wrapper');
        const bar = document.getElementById('sharing-progress-bar');
        const statusMsg = document.getElementById('sharing-status-msg');
        const btnRender = document.getElementById('btn-generate-video');
        const btnOpen = document.getElementById('btn-open-output');

        this.isRendering = true;
        btnRender.disabled = true;
        btnRender.style.opacity = '0.5';
        
        wrapper.style.display = 'block';
        bar.style.width = '5%'; 
        statusMsg.className = 'data-text status-working';
        statusMsg.innerHTML = '<span aria-hidden="true">⚙️</span> Initializing Studio: Creating shareable file...';

        try {
            const response = await fetch('/run_tool_logic/music-sharing/render', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: this.selectedPath })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let progressCounter = 5;
            // Real bug, found live 2026-07-28 (John's King Crimson "Elephant
            // Talk" / "Frame By Frame" reports): the render always actually
            // completed and the MP4 was always written to disk correctly --
            // confirmed directly -- but the UI sat on "Initializing
            // Studio..." forever, looking exactly like a hang. Root cause:
            // music-sharing.py wraps every status emoji for accessibility
            // (<span aria-hidden="true">✅</span> SUCCESS: ...), so the
            // actual text is "✅</span> SUCCESS", never "✅ SUCCESS" adjacent
            // -- these emoji+word checks could never match, on any render,
            // ever. Anchored on the stable "WORD:" text instead (present in
            // every Processing/SUCCESS/ERROR line regardless of whatever
            // markup wraps it) rather than assuming emoji adjacency, which
            // is exactly the kind of thing an accessibility pass can change
            // without anyone noticing this check silently broke.
            // Also accumulates into `buffer` (not just the latest fragment)
            // so a marker split across two network chunks -- normal,
            // expected behavior for any streamed HTTP response -- still
            // gets caught as soon as its second half arrives. `finished`
            // stops re-processing the terminal state once reached.
            let buffer = '';
            let finished = false;

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                if (!finished && buffer.includes('Processing:')) {
                    progressCounter = Math.min(progressCounter + 2, 95);
                    bar.style.width = `${progressCounter}%`;
                    bar.setAttribute('aria-valuenow', progressCounter);
                    statusMsg.innerHTML = '<span aria-hidden="true">⚙️</span> Generating an MP4 file for sharing...';
                }

                if (buffer.includes('SUCCESS:')) {
                    finished = true;
                    bar.style.width = '100%';
                    bar.setAttribute('aria-valuenow', 100);
                    statusMsg.className = 'data-text status-success';
                    statusMsg.innerHTML = '<span aria-hidden="true">📻</span> Your file is ready to be shared.';
                    if (btnOpen) btnOpen.style.display = 'block';
                }

                if (buffer.includes('ERROR:')) {
                    finished = true;
                    statusMsg.className = 'data-text status-error';
                    statusMsg.innerHTML = '<span aria-hidden="true">🔥</span> Render failed. Check file integrity.';
                }
            }
        } catch (err) {
            statusMsg.className = 'data-text status-error';
            statusMsg.innerText = `System Error: ${err.message}`;
        } finally {
            this.isRendering = false;
        }
    },

    /**
     * UI Cleanup: Resets progress and buttons.
     */
    resetStudio: function() {
        const wrapper = document.getElementById('sharing-progress-wrapper');
        const bar = document.getElementById('sharing-progress-bar');
        const btnOpen = document.getElementById('btn-open-output');
        const statusMsg = document.getElementById('sharing-status-msg');
        
        if (wrapper) wrapper.style.display = 'none';
        if (bar) bar.style.width = '0%';
        if (btnOpen) btnOpen.style.display = 'none';
        if (statusMsg) statusMsg.innerText = '';
    },

    openOutputFolder: function() {
        fetch('/run_tool_logic/music-sharing/open_folder');
    },

    // --- 2. HELP PANEL & FOCUS ENGINE ---

    openHelp: async function() {
        const panel = document.getElementById('sharing-help-panel');
        const body = document.getElementById('sharing-help-body');
        const title = document.getElementById('sharing-help-title');
        this.lastTrigger = document.activeElement;

        try {
            const response = await fetch('/tool_asset/music-sharing/help.mfi');
            body.innerHTML = await response.text();
            panel.style.display = 'flex';
            setTimeout(() => {
                if (title) { title.setAttribute('tabindex', '-1'); title.focus(); }
                document.addEventListener('keydown', this.trapFocus);
            }, 20);
        } catch (err) { console.error("Help Load Error", err); }
    },

    trapFocus: function(e) {
        if (e.key !== 'Tab') return;
        const panel = document.getElementById('sharing-help-panel');
        if (!panel || panel.style.display === 'none') return;
        const focusables = panel.querySelectorAll('button, [href], [tabindex]:not([tabindex="-1"])');
        if (focusables.length === 0) return;
        const first = focusables[0], last = focusables[focusables.length - 1];

        if (e.shiftKey && document.activeElement === first) {
            last.focus(); e.preventDefault();
        } else if (!e.shiftKey && document.activeElement === last) {
            first.focus(); e.preventDefault();
        }
    },

    closeHelp: function() {
        const panel = document.getElementById('sharing-help-panel');
        if (panel) {
            panel.style.display = 'none';
            document.removeEventListener('keydown', this.trapFocus);
            if (this.lastTrigger) this.lastTrigger.focus();
        }
    }
};

// Start the SPA observer/initialization
(function() {
    window.metaforge.sharing.init();
})();

console.log("MetaForge Music Sharing: Studio Bridge Build 1.0.3 Synchronized.");
/* --- MUSIC SHARING LOGIC BRIDGE END --- */
/* --- END OF FILE music-sharing.js --- */