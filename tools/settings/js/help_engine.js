// --- SETTINGS MINI-ENGINE: help_engine.js ---
/**
 * Standalone Documentation Aggregator. Build 5.2.2
 * Handles the rendering of tool-specific help fragments.
 */

window.metaforge.settings.help = {
    /**
     * Entry Point: Fetches aggregated help data from the Python backend.
     */
    load: async function() {
        const container = document.getElementById('help-aggregator');
        if(!container) return;

        container.innerHTML = '<p class="tool_notes">Aggregating tool documentation...</p>';

        try {
            const res = await fetch('/run_tool_logic/settings/get_help_docs');
            const docs = await res.json();

            this.render(docs);
        } catch (e) {
            container.innerHTML = `<p class="error-text">Documentation load failure: ${e.message}</p>`;
        }
    },

    /**
     * Renders an accordion-style list of help documents.
     */
    render: function(docs) {
        const container = document.getElementById('help-aggregator');
        
        if (!docs || docs.length === 0) {
            container.innerHTML = "<p class='tool_notes'>No documentation fragments discovered in the current suite.</p>";
            return;
        }

        let html = "";
        docs.forEach(doc => {
            html += `
                <details style="margin-bottom:10px; border:1px solid var(--bg-accent); border-radius:4px; background:var(--bg-main);">
                    <summary style="color:var(--mf-gold); cursor:pointer; font-weight:bold; font-size:0.85rem; padding:10px; outline:none;">
                        ${doc.name}
                    </summary>
                    <div class="help-content-silo" style="padding:15px; border-top:1px solid var(--bg-accent); color:var(--text-message); font-size:0.85rem; line-height:1.5;">
                        ${doc.html}
                    </div>
                </details>`;
        });
        
        container.innerHTML = html;
    }
};

// --- SETTINGS MINI-ENGINE: help_engine.js END ---