// --- START OF FILE update_engine.js ---
/**
 * Standalone Update Engine Spoke. Build 5.3.21
 * Role: Handles the UI rendering for system updates and state synchronization.
 * Build 5.3.21: Linguistic Sync (Dismissal label) and Accessibility Hardening.
 */

window.metaforge.settings.updates = {
    // Internal state to hold the current update payload
    currentUpdate: null,

    /**
     * Entry Point: Triggers the Python manifest comparison.
     */
    run: async function() {
        const container = document.getElementById('binary-audit-container');
        if (!container) return;

        container.innerHTML = '<p class="tool_notes" style="margin-top: 20px;">Checking for updates...</p>';

        try {
            const res = await fetch('/run_tool_logic/settings/check_updates');
            const data = await res.json();

            if (data.status === 'error') {
                container.innerHTML = `<p class="error-text" style="margin-top: 20px;">Update Error: ${data.message}</p>`;
                return;
            }

            this.currentUpdate = data;
            this.render(data);
        } catch (e) {
            container.innerHTML = `<p class="error-text" style="margin-top: 20px;">Update failure: ${e.message}</p>`;
        }
    },

    /**
     * Renders the update status and the Heartbeat timestamp.
     * Hardened for WCAG 2.2 AA (SC 1.1.1) and COGA 4.4.1.
     */
    render: function(data) {
        const container = document.getElementById('binary-audit-container');
        
        // 1. Generate the Heartbeat (Last Checked) line
        const heartbeatHtml = `
            <p class="data-text" style="font-size: 0.75rem; color: var(--text-message); margin-top: 15px; border-top: 1px solid var(--bg-accent); padding-top: 10px;">
                Last checked: <span style="color: var(--mf-gold);">${data.last_checked}</span>
            </p>`;

        // CASE 1: System is Up to Date
        if (!data.update_available) {
            container.innerHTML = `
                <p class="data-text" style="color: var(--status-success); font-weight: bold; margin-top: 20px;">
                    <span aria-hidden="true">✅</span> Rest easy, your system is up to date. Happy tagging!
                </p>
                ${heartbeatHtml}`;
            return;
        }

        // CASE 2: Update Available / Announcement
        const priorityColor = data.priority.toLowerCase() === 'required' ? 'var(--status-error)' : 'var(--mf-gold)';
        const priorityLabel = data.priority.charAt(0).toUpperCase() + data.priority.slice(1);

        // COGA 4.4.1: Transitioned "No thank you" to literal "Dismiss update notification"
        const dismissBtn = (data.priority.toLowerCase() !== 'required') 
            ? `<button class="mf-button-gold-fixed" 
                       style="background: transparent !important; border: 1px solid var(--text-message); color: var(--text-message) !important;" 
                       onclick="metaforge.settings.updates.syncState(true)"
                       aria-label="Dismiss this update notification">
                       Dismiss update notification
               </button>` 
            : '';

        container.innerHTML = `
            <div class="update-announcement" style="margin-top: 25px;">
                <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 10px;">
                    <h3 class="data-text" style="color: ${priorityColor}; margin: 0; font-size: 1rem;">${data.title}</h3>
                    <span class="data-text" style="font-size: 0.7rem; color: ${priorityColor}; border: 1px solid ${priorityColor}; padding: 1px 4px; font-weight: bold; border-radius: 2px;">
                        ${priorityLabel}
                    </span>
                </div>
                
                <p class="data-text" style="font-size: 0.85rem; line-height: 1.5; color: var(--text-message); margin-bottom: 15px; max-width: 600px;">
                    ${data.body}
                </p>

                <div style="display: flex; gap: 15px; align-items: center;">
                    <button class="mf-button-gold-fixed" 
                            onclick="metaforge.settings.updates.syncState(false)"
                            aria-label="View update details for ${data.title} on GitHub">
                        View update details
                    </button>
                    ${dismissBtn}
                    <span class="data-text" style="font-size: 0.75rem; color: var(--text-message); margin-left: auto;">
                        Remote version: <span style="color: var(--mf-gold);">${data.remote_version}</span>
                    </span>
                </div>
            </div>
            ${heartbeatHtml}
        `;
    },

    /**
     * Synchronizes the local state with the backend.
     */
    syncState: async function(isDismissed) {
        if (!this.currentUpdate) return;

        const payload = {
            ...this.currentUpdate,
            dismissed: isDismissed
        };

        try {
            const res = await fetch('/run_tool_logic/settings/commit_update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();

            if (result.status === 'success') {
                if (!isDismissed) {
                    window.open(this.currentUpdate.action_url, '_new');
                }
                this.run();
            }
        } catch (e) {
            console.error("MetaForge Update Sync Error:", e);
        }
    }
};

// --- SETTINGS UPDATE ENGINE END ---
// --- END OF FILE update_engine.js ---