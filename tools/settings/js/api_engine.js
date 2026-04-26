// --- SETTINGS MINI-ENGINE: api_engine.js ---
/**
 * Standalone API & Config Manager. Build 5.2.2
 * Handles environmental variable auditing, editing, and persistence.
 */

window.metaforge.settings.api = {
    /**
     * Entry Point: Fetches current .env configuration from Python.
     */
    load: async function() {
        const container = document.getElementById('api-form-container');
        if(!container) return;

        container.innerHTML = '<p class="tool_notes">Synchronizing environment variables...</p>';

        try {
            const res = await fetch('/run_tool_logic/settings/get_env');
            const data = await res.json();
            this.render(data);
        } catch (e) {
            container.innerHTML = `<p class="error-text">Configuration load failure: ${e.message}</p>`;
        }
    },

    /**
     * Renders a dense table of configuration inputs.
     */
    render: function(data) {
        const container = document.getElementById('api-form-container');
        
        let html = '<table class="meta-table" style="width:100%;"><tbody>';
        
        for (const [key, value] of Object.entries(data)) {
            html += `
                <tr style="border-bottom: 1px solid var(--bg-main);">
                    <td style="padding:8px; color:var(--mf-gold); font-size:0.75rem; font-weight:bold; width:30%;">
                        ${key}
                    </td>
                    <td style="padding:8px;">
                        <label class="visually-hidden" for="env-${key}">Value for ${key}</label>
                        <input type="text" 
                               id="env-${key}" 
                               class="mf-input env-input" 
                               data-key="${key}" 
                               value="${value}" 
                               style="width:100%; margin-top:0;">
                    </td>
                </tr>`;
        }
        
        html += '</tbody></table>';
        container.innerHTML = html;
    },

    /**
     * Persists the modified configuration back to the .env file.
     */
    save: async function() {
        const status = document.getElementById('save-status');
        const inputs = document.querySelectorAll('.env-input');
        const config = {};
        
        // Collate values from the UI
        inputs.forEach(i => config[i.getAttribute('data-key')] = i.value);

        status.innerHTML = "<span class='data-text'>Writing environment...</span>";

        try {
            const res = await fetch('/run_tool_logic/settings/save_env', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            const result = await res.json();
            
            if (result.status === 'success') {
                status.innerHTML = "<span style='color:var(--status-success); font-size:0.75rem;'>✓ Configuration physically committed.</span>";
                setTimeout(() => { status.innerHTML = ""; }, 3000);
            }
        } catch (e) {
            status.innerHTML = "<span style='color:var(--status-error);'>Configuration write failure.</span>";
        }
    }
};

// --- SETTINGS MINI-ENGINE: api_engine.js END ---