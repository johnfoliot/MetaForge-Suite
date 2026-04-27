// --- START OF FILE update_engine.js ---
/**
 * Standalone Update Gatekeeper Spoke. Build 5.3.5
 * Handles the UI rendering for system updates and announcements.
 * Physical Location: \tools\settings\js\update_engine.js
 */

window.metaforge.settings.updates = {
    /**
     * Entry Point: Triggers the Python manifest comparison.
     */
    run: async function() {
        const container = document.getElementById('binary-audit-container');
        if (!container) return;

        // Visual feedback during the fetch
        container.innerHTML = '<p class="tool_notes">Consulting the Gatekeeper manifest...</p>';

        try {
            const res = await fetch('/run_tool_logic/settings/check_updates');
            const data = await res.json();

            if (data.status === 'error') {
                container.innerHTML = `<p class="error-text">Gatekeeper Error: ${data.message}</p>`;
                return;
            }

            this.render(data);
        } catch (e) {
            container.innerHTML = `<p class="error-text">Update bridge failure: ${e.message}</p>`;
        }
    },

    /**
     * Renders the update status based on the Gatekeeper's decision.
     */
    render: function(data) {
        const container = document.getElementById('binary-audit-container');
        
        // CASE 1: System is Up to Date
        if (!data.update_available) {
            container.innerHTML = `
                <div style="padding: 20px; border: 1px solid var(--status-success); background: rgba(42, 217, 90, 0.1); border-radius: 4px; margin-top: 20px;">
                    <p class="data-text" style="color: var(--status-success); font-weight: bold; font-size: 0.9rem; margin: 0;">
                        ${data.message}
                    </p>
                </div>`;
            return;
        }

        // CASE 2: Update Available / Announcement
        const priorityColor = data.priority === 'required' ? 'var(--status-error)' : 'var(--mf-gold)';
        const priorityLabel = data.priority.toUpperCase();

        container.innerHTML = `
            <div class="update-announcement-card" style="margin-top: 20px; border: 1px solid ${priorityColor}; background: var(--bg-main); border-radius: 4px; padding: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 1px solid var(--bg-accent); padding-bottom: 10px;">
                    <h3 class="data-text" style="color: ${priorityColor}; margin: 0; font-size: 1rem;">${data.title}</h3>
                    <span class="data-text" style="font-size: 0.7rem; background: ${priorityColor}; color: #000; padding: 2px 6px; font-weight: bold; border-radius: 2px;">
                        ${priorityLabel}
                    </span>
                </div>
                
                <p class="data-text" style="font-size: 0.85rem; line-height: 1.5; color: var(--text-message); margin-bottom: 20px;">
                    ${data.body}
                </p>

                <div style="display: flex; gap: 15px; align-items: center;">
                    <button class="mf-button-gold-fixed" 
                            onclick="window.open('${data.action_url}', '_blank')"
                            aria-label="Visit update resource for ${data.title}">
                        GET UPDATE / VIEW DETAILS
                    </button>
                    <span class="data-text" style="font-size: 0.75rem; color: var(--text-message);">
                        Remote Version: <span style="color: var(--mf-gold);">${data.remote_version}</span>
                    </span>
                </div>
            </div>
        `;
    }
};

// --- SETTINGS UPDATE ENGINE END ---
// --- END OF FILE update_engine.js ---