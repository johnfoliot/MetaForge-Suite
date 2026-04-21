/**
 * Settings Logic Controller (Sub-Tab Data Trigger Fix)
 */

window.showSettingsPanel = function(panelId, element) {
    // Main Tab Navigation
    document.querySelectorAll('.nav-tab').forEach(el => {
        el.classList.remove('active');
        el.style.color = 'var(--text-message)';
    });
    if(element) {
        element.classList.add('active');
        element.style.color = 'var(--mf-gold)';
    }

    // Main Panel Switching
    document.querySelectorAll('.settings-panel').forEach(el => el.style.display = 'none');
    const target = document.getElementById('panel-' + panelId);
    if(target) target.style.display = 'block';

    // Contextual Data Loading for Main Tabs
    if(panelId === 'personalization') {
        // When entering personalization, check which sub-panel is active
        const activeSub = document.querySelector('.sub-nav-btn.active');
        if (activeSub && activeSub.id === 'sub-nav-toolbar') {
            window.loadToolbarCustomizer();
        }
    }
    if(panelId === 'api-keys') window.loadAPIConfig();
    if(panelId === 'help') window.aggregateHelpFiles();
};

/**
 * Sub-Panel Switcher: Now triggers data loading for specific sub-tabs
 */
window.showSubPanel = function(subId, element) {
    // Update button states
    document.querySelectorAll('.sub-nav-btn').forEach(btn => btn.classList.remove('active'));
    if(element) element.classList.add('active');

    // Toggle panel visibility
    document.querySelectorAll('.personalization-sub-panel').forEach(p => p.style.display = 'none');
    const target = document.getElementById('sub-panel-' + subId);
    if(target) {
        target.style.display = 'block';
    }

    // DATA TRIGGER: If switching TO the toolbar customization, load the data!
    if (subId === 'toolbar') {
        window.loadToolbarCustomizer();
    }
};

window.loadToolbarCustomizer = async function() {
    const grid = document.getElementById('toolbar-customizer-grid');
    if(!grid) return;

    // Show loading state while fetching
    grid.innerHTML = '<p class="tool_notes">Refreshing tool manifests...</p>';

    try {
        const res = await fetch('/run_tool_logic/settings/get_discovery');
        const data = await res.json();
        
        let html = `
        <table style="width:100%; max-width: 480px; font-size: 0.75rem; border-collapse: collapse; line-height: 1.1; margin-top: 5px;">
            <thead>
                <tr style="text-align:left; border-bottom: 2px solid var(--mf-gold); color: var(--mf-gold);">
                    <th style="padding: 4px;">Show</th>
                    <th style="padding: 4px;">Tool Name</th>
                    <th style="padding: 4px; text-align:center;">Order</th>
                </tr>
            </thead>
            <tbody>`;

        data.all_tools.forEach(tool => {
            const isEnabled = data.enabled_ids.includes(tool.id);
            const checked = isEnabled ? 'checked' : '';
            const locked = tool.required ? 'disabled checked' : '';
            
            html += `
            <tr style="border-bottom: 1px solid #222;">
                <td style="padding: 5px;">
                    <input type="checkbox" class="tool-toggle" data-id="${tool.id}" ${checked} ${locked}>
                </td>
                <td style="padding: 5px; color: #fff;">${tool.name}</td>
                <td style="padding: 5px; text-align:center;">
                    <input type="number" class="tool-order" data-id="${tool.id}" value="${tool.order}" 
                           style="width:35px; background:#000; color:var(--mf-gold); border:1px solid #555; padding:1px; font-size:0.7rem; text-align:center;">
                </td>
            </tr>`;
        });
        grid.innerHTML = html + '</tbody></table>';
    } catch (err) {
        grid.innerHTML = '<p style="color:red;">Failed to load toolbar data.</p>';
        console.error("Settings: Failed to discover tools", err);
    }
};

/**
 * Remaining functions (loadAPIConfig, browseSettingsLibrary, aggregateHelpFiles, saveSettings) 
 * should remain exactly as they were in your previous version.
 */