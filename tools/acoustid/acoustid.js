/* --- START OF FILE acoustid.js --- */
/**
 * AcoustID Manager: Logic Bridge. Build 1.1.0
 * Role: Real-time console orchestration & focus management.
 * Build 1.1.0: Accessibility Hardening & Seek-Confirmation Implementation.
 */

// --- 1. NAMESPACE INITIALIZATION ---
window.metaforge = window.metaforge || {};
window.metaforge.acoustid = {
    
    lastTrigger: null,

    /**
     * Master Task Runner: Orchestrates Step 1 (Submit) or Step 2 (Resolve).
     */
    runTask: async function(taskType) {
        const consoleBox = document.getElementById('acoustid-console');
        if (!consoleBox) return;

        // Reset console and show initialization state
        consoleBox.innerHTML = `<div class="status-warn"><span style="font-size:1rem;">ᯓ➤ Initializing AcoustID ${taskType} sequence...</span><p style="margin-left:2.3rem; font-size:.8rem; margin-bottom:.5rem;"> ⚠ <span style="color:red; font-weight:bold;">(Do not close window!)</span></p>`;

        try {
            const response = await fetch(`/run_tool_logic/acoustid/${taskType}`);
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
        } catch (err) {
            consoleBox.insertAdjacentHTML('beforeend', `<div class="status-err"><span aria-hidden="true">🔥</span> Execution Error: ${err.message}</div>`);
        }
    },

    /**
     * Helper: Appends text or HTML fragments to the console.
     * Hardened to preserve ARIA-hidden spans sent from backend.
     */
    appendOutput: function(container, text) {
        if (!text) return;

        // Check if incoming text is a pre-formatted HTML fragment from Build 1.0.5 backend
        if (text.includes('<div') || text.includes('<span')) {
            container.insertAdjacentHTML('beforeend', text);
        } else {
            // Fallback for plain text streams, ensuring emoji protection
            let formatted = text
                .replace(/\[PASS\]/g, '<span class="status-ok">[PASS]</span>')
                .replace(/✅/g, '<span aria-hidden="true">✅</span>')
                .replace(/🔥/g, '<span aria-hidden="true">🔥</span>')
                .replace(/⚠/g, '<span aria-hidden="true">⚠</span>')
                .replace(/🛰️/g, '<span aria-hidden="true">🛰️</span>');

            const div = document.createElement('div');
            div.innerHTML = formatted;
            container.appendChild(div);
        }
        
        container.scrollTop = container.scrollHeight;
    },

};

console.log("MetaForge AcoustID: Logic Bridge Build 1.1.0 Synchronized.");

/* --- ACOUSTID LOGIC BRIDGE END --- */
/* --- END OF FILE acoustid.js --- */