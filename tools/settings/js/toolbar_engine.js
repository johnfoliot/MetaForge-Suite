// --- SETTINGS MINI-ENGINE: toolbar_engine.js ---
/**
 * Standalone Toolbar Customizer. Build 5.2.2
 * Handles tool visibility, custom ordering, and sequence normalization.
 */

window.metaforge.settings.toolbar = {
    /**
     * Entry Point: Fetches tool manifests and saved layout from Python.
     */
    load: async function() {
        const grid = document.getElementById('toolbar-customizer-grid');
        if(!grid) return;

        grid.innerHTML = '<p class="tool_notes">Synchronizing workbench matrix...</p>';

        try {
            const res = await fetch('/run_tool_logic/settings/get_discovery');
            const data = await res.json();
            this.render(data);
        } catch (e) {
            grid.innerHTML = `<p class="error-text">Discovery failure: ${e.message}</p>`;
        }
    },

    /**
     * Renders the matrix table using global primitives.
     */
    render: function(data) {
        const grid = document.getElementById('toolbar-customizer-grid');
        
        let html = `
            <table class="meta-table">
                <thead>
                    <tr style="text-align:left; color:var(--mf-gold); border-bottom:1px solid var(--bg-accent);">
                        <th style="padding:8px; font-size:0.75rem;">Show</th>
                        <th style="padding:8px; font-size:0.75rem;">Tool component</th>
                        <th style="padding:8px; font-size:0.75rem; text-align:center;">Order</th>
                    </tr>
                </thead>
                <tbody>`;

        // The counter ensures we display a clean 1-N sequence on load
        let visibleCounter = 1;

        data.layout.forEach((entry) => {
            // Security: Dashboard and Settings are core and not customisable here
            if (["dashboard", "settings"].includes(entry.id)) return;

            const tool = data.manifests[entry.id];
            const iconPath = `/tool_asset/${entry.id}/${tool.icon || 'default.svg'}`;
            const isVisible = entry.visible ? 'checked' : '';
            const isRequired = (tool && tool.required) ? 'disabled checked' : '';

            html += `
                <tr style="border-bottom:1px solid var(--bg-main);">
                    <td style="padding:8px;">
                        <input type="checkbox" class="tool-toggle" data-id="${entry.id}" ${isVisible} ${isRequired} aria-label="Toggle visibility for ${tool ? tool.name : entry.id}">
                    </td>
                    <td style="padding:8px; display:flex; align-items:center; gap:10px;">
                        <div class="mf-icon-mask" style="-webkit-mask-image: url('${iconPath}'); mask-image: url('${iconPath}'); width:18px; height:18px; background-color: var(--mf-gold);"></div>
                        <span class="data-text" style="font-size:0.85rem;">${tool ? tool.name : entry.id}</span>
                    </td>
                    <td style="padding:8px; text-align:center;">
                        <input type="number" class="tool-order" data-id="${entry.id}" value="${visibleCounter}" aria-label="Order for ${tool ? tool.name : entry.id}">
                    </td>
                </tr>`;
            visibleCounter++;
        });

        html += '</tbody></table>';
        grid.innerHTML = html;
    },

    /**
     * Normalization Logic: Resolves conflicts and re-indexes the entire set.
     */
    save: async function() {
        const status = document.getElementById('save-status');
        const orderInputs = Array.from(document.querySelectorAll('.tool-order'));
        
        // 1. Map user inputs
        const userLayout = orderInputs.map(input => {
            const tid = input.getAttribute('data-id');
            const toggle = document.querySelector(`.tool-toggle[data-id="${tid}"]`);
            return {
                id: tid,
                userValue: parseInt(input.value) || 99,
                visible: toggle ? toggle.checked : true
            };
        });

        // 2. Conflict Resolution: Stable sort by user value, then ID
        userLayout.sort((a, b) => {
            if (a.userValue !== b.userValue) return a.userValue - b.userValue;
            return a.id.localeCompare(b.id);
        });

        // 3. Normalization: Re-index 1..N
        const finalLayout = [
            { id: "dashboard", visible: true },
            ...userLayout.map((item, index) => ({
                id: item.id,
                visible: item.visible,
                order: index + 1
            })),
            { id: "settings", visible: true }
        ];

        // 4. Commitment
        status.innerHTML = "<span class='data-text'>Normalizing Matrix...</span>";
        try {
            const res = await fetch('/run_tool_logic/settings/save_toolbar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(finalLayout)
            });
            const result = await res.json();
            if (result.status === 'success') {
                status.innerHTML = "<span style='color:var(--status-success);'>✓ Matrix re-aligned.</span>";
                // Hot-reload the shell to apply new order
                setTimeout(() => { location.reload(); }, 1200);
            }
        } catch (e) {
            status.innerHTML = "<span style='color:var(--status-error);'>Save failure.</span>";
        }
    }
};

// --- SETTINGS MINI-ENGINE: toolbar_engine.js END ---