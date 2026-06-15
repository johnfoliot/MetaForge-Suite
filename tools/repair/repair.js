/* --- START OF FILE repair.js --- */
/**
 * Audio Repair Workbench: Logic Bridge. Build 1.0.2
 * Handles remediation queue synchronization and batch FFmpeg orchestration.
 * Build 1.0.2: Implemented Seek-Confirmation and Accessibility Hardening.
 */

// --- 1. NAMESPACE INITIALIZATION ---
window.metaforge = window.metaforge || {};
window.metaforge.repair = {
    
    lastTrigger: null,
    isProcessing: false,

    /**
     * Entry Point: Synchronizes the UI with the remediation_queue.log.
     * Build 1.0.2: Corrected "Recommendation" linguistic sync.
     */
    loadQueue: async function() {
        const container = document.getElementById('repair-queue-container');
        const btnAll = document.getElementById('btn-repair-all');
        if (!container) return;

        try {
            const response = await fetch('/run_tool_logic/repair/get_queue');
            const data = await response.json();

            if (!data.queue || data.queue.length === 0) {
                container.innerHTML = `
                    <div class="status-ok" style="padding: 10px;">
                        <span aria-hidden="true">✅</span> Remediation queue is empty.
                    </div>
                    <div class="tool_notes" style="margin-top: 15px;">
                        <strong style="color:var(--mf-gold);">Recommendation:</strong><br>
                        All identified bitstream errors have been resolved. You may now return to the Intelli-Tagger.
                    </div>`;
                if (btnAll) btnAll.style.display = 'none';
                return;
            }

            let html = '';
            data.queue.forEach((item) => {
                html += `
                    <div class="repair-item">
                        <span class="file-name">${item.filename}</span>
                        <span class="error-msg">${item.error}</span>
                    </div>`;
            });

            container.innerHTML = html;
            if (btnAll) btnAll.style.display = 'block';

        } catch (err) {
            container.innerHTML = `<p class="status-err">Queue Sync Error: ${err.message}</p>`;
        }
    },

    /**
     * Orchestrates the batch RAW rebuild process.
     * Implements Directive VI: Seek Confirmation (COGA 4.5.4).
     */
    runBatch: async function() {
        if (this.isProcessing) return;

        // 1. SEEK CONFIRMATION GATE
        if (!confirm("This will initiate a precision rebuild of all corrupted files in the queue. Continue?")) {
            return;
        }
        
        const consoleBox = document.getElementById('repair-console');
        if (!consoleBox) return;

        this.isProcessing = true;
        consoleBox.innerHTML = '<div class="status-warn" style="font-size:1rem; color:var(--mf-gold);"><span aria-hidden="true">🛠️</span> Initializing Precision Rebuild...</div>';

        try {
            const response = await fetch('/run_tool_logic/repair/run_rebuild');
            
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.message || `HTTP ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const text = decoder.decode(value, { stream: true });
                this.appendOutput(consoleBox, text);
            }

            // Refresh queue after completion to show terminal empty state
            this.loadQueue();

        } catch (err) {
            consoleBox.insertAdjacentHTML('beforeend', `<div class="status-err"><span aria-hidden="true">🔥</span> Surgical Failure: ${err.message}</div>`);
        } finally {
            this.isProcessing = false;
        }
    },

    /**
     * Helper: Appends text to the console with semantic class mapping.
     * Hardened to preserve ARIA-hidden spans from Build 1.0.3 backend.
     */
    appendOutput: function(container, text) {
        if (!text) return;

        // If the backend has already wrapped the content in HTML, append as-is
        if (text.includes('<div') || text.includes('<span')) {
            container.insertAdjacentHTML('beforeend', text);
        } else {
            // Fallback: Surgical symbol wrapping for plain text streams
            let formatted = text
                .replace(/✅/g, '<span class="status-ok" aria-hidden="true">✅</span>')
                .replace(/🔥/g, '<span class="status-err" aria-hidden="true">🔥</span>')
                .replace(/⚠/g, '<span class="status-warn" aria-hidden="true">⚠</span>')
                .replace(/⚙️/g, '<span class="status-api" aria-hidden="true">⚙️</span>')
                .replace(/🛠️/g, '<span class="status-api" aria-hidden="true">🛠️</span>');

            const div = document.createElement('div');
            div.innerHTML = formatted;
            container.appendChild(div);
        }
        
        container.scrollTop = container.scrollHeight;
    },

    // --- 2. HELP PANEL & FOCUS ENGINE ---

    openHelp: async function() {
        const panel = document.getElementById('repair-help-panel');
        const body = document.getElementById('repair-help-body');
        const title = document.getElementById('repair-help-title');
        
        this.lastTrigger = document.activeElement;
        if (!panel || !body) return;

        try {
            const response = await fetch('/tool_asset/repair/help.mfi');
            if (!response.ok) throw new Error("Documentation offline.");
            
            const html = await response.text();
            body.innerHTML = html;
            panel.style.display = 'flex';

            setTimeout(() => {
                if (title) {
                    title.setAttribute('tabindex', '-1');
                    title.focus();
                }
                document.addEventListener('keydown', this.trapFocus);
            }, 20);

        } catch (err) {
            body.innerHTML = `<p class="status-err">Error: ${err.message}</p>`;
            panel.style.display = 'flex';
        }
    },

    trapFocus: function(e) {
        if (e.key !== 'Tab') return;
        const panel = document.getElementById('repair-help-panel');
        if (!panel || panel.style.display === 'none') return;

        const focusables = panel.querySelectorAll('button, [href], [tabindex]:not([tabindex="-1"])');
        if (focusables.length === 0) return;

        const first = focusables[0];
        const last = focusables[focusables.length - 1];

        if (e.shiftKey) { 
            if (document.activeElement === first) { last.focus(); e.preventDefault(); }
        } else { 
            if (document.activeElement === last) { first.focus(); e.preventDefault(); }
        }
    },

    closeHelp: function() {
        const panel = document.getElementById('repair-help-panel');
        if (panel) {
            panel.style.display = 'none';
            document.removeEventListener('keydown', this.trapFocus);
            if (this.lastTrigger) this.lastTrigger.focus();
        }
    }
};

// Initial Sync upon tool load
(function() {
    if (document.getElementById('repair-queue-container')) {
        window.metaforge.repair.loadQueue();
    }
})();

console.log("MetaForge Audio Repair: Logic Bridge Build 1.0.2 Synchronized.");
/* --- AUDIO REPAIR LOGIC BRIDGE END --- */
/* --- END OF FILE repair.js --- */