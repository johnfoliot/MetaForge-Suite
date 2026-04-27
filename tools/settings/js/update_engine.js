// --- START OF FILE update_engine.js ---
/**
 * Standalone Update Engine Spoke. Build 5.3.15
 * Handles the UI rendering for system updates and announcements.
 * Build 5.3.15: Updated window target to _new and refined button labeling.
 */

window.metaforge.settings.updates = {
    /**
     * Entry Point: Triggers the Python manifest comparison.
     */
    run: async function() {
        const container = document.getElementById('binary-audit-container');
        if (!container) return;

        container.innerHTML = '<p class="tool_notes" style="margin-top: 20px;">Checking for Updates...</p>';

        try {
            const res = await fetch('/run_tool_logic/settings/check_updates');
            const data = await res.json();

            if (data.status === 'error') {
                container.innerHTML = `<p class="error-text" style="margin-top: 20px;">Update Error: ${data.message}</p>`;
                return;
            }

            this.render(data);
        } catch (e) {
            container.innerHTML = `<p class="error-text" style="margin-top: 20px;">Update failure: ${e.message}</p>`;
        }
    },

    /**
     * Renders the update status based on the Engine's decision.
     */
    render: function(data) {
        const container = document.getElementById('binary-audit-container');
        
        // CASE 1: System is Up to Date
        if (!data.update_available) {
            container.innerHTML = `
                <p class="data-text" style="color: var(--status-success); font-weight: bold; margin-top: 20px;">
                    ✅ Rest easy, your system is up to date. Happy tagging!
                </p>`;
            return;
        }

        // CASE 2: Update Available / Announcement
        const priorityColor = data.priority === 'required' ? 'var(--status-error)' : 'var(--mf-gold)';
        const priorityLabel = data.priority.charAt(0).toUpperCase() + data.priority.slice(1);

        container.innerHTML = `
            <div class="update-announcement" style="margin-top: 25px; border-top: 1px solid var(--bg-accent); padding-top: 15px;">
                <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 10px;">
                    <h3 class="data-text" style="color: ${priorityColor}; margin: 0; font-size: 1rem;">${data.title}</h3>
                    <span class="data-text" style="font-size: 0.7rem; color: ${priorityColor}; border: 1px solid ${priorityColor}; padding: 1px 4px; font-weight: bold; border-radius: 2px;">
                        ${priorityLabel}
                    </span>
                </div>
                
                <p class="data-text" style="font-size: 0.85rem; line-height: 1.5; color: var(--text-message); margin-bottom: 15px; max-width: 600px;">
                    ${data.body}
                </p>

                <div style="display: flex; gap: 20px; align-items: center;">
                    <button class="mf-button-gold-fixed" 
                            onclick="window.open('${data.action_url}', '_new')"
                            aria-label="View update details for ${data.title} on GitHub">
                        View update details
                    </button>
                    <span class="data-text" style="font-size: 0.75rem; color: var(--text-message);">
                        Remote version: <span style="color: var(--mf-gold);">${data.remote_version}</span>
                    </span>
                </div>
            </div>
        `;
    }
};

// --- SETTINGS UPDATE ENGINE END ---
// --- END OF FILE update_engine.js ---