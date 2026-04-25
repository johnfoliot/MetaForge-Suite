// --- SETTINGS ENGINE: CORE LOGIC ---
// Trigger ➔ Handoff ➔ Render. Build 3.9.2: Theme-Aware Asset Selection (Twin Asset).


// --- SETTINGS PANEL ---
window.showSettingsPanel = function(panelId, element) {
    document.querySelectorAll('.nav-tab').forEach(el => {
        el.classList.remove('active');
        el.style.color = 'var(--text-message)';
    });
    if(element) {
        element.classList.add('active');
        element.style.color = 'var(--mf-gold)';
    }

    document.querySelectorAll('.settings-panel').forEach(el => el.style.display = 'none');
    const target = document.getElementById('panel-' + panelId);
    if(target) target.style.display = 'block';

    if(panelId === 'api-keys') window.loadAPIConfig();
    if(panelId === 'help') window.aggregateHelpFiles();
    if(panelId === 'personalization') {
        const activeSub = document.querySelector('.sub-nav-btn.active');
        if (activeSub && activeSub.id === 'sub-nav-toolbar') window.loadToolbarCustomizer();
    }
};

window.showSubPanel = function(subId, element) {
    document.querySelectorAll('.sub-nav-btn').forEach(btn => btn.classList.remove('active'));
    if(element) element.classList.add('active');

    document.querySelectorAll('.personalization-sub-panel').forEach(p => p.style.display = 'none');
    const target = document.getElementById('sub-panel-' + subId);
    if(target) target.style.display = 'block';

    if (subId === 'toolbar') window.loadToolbarCustomizer();
};

// --- SETTINGS PANEL END---

// --- THEME TOGGLE ENGINE ---
/**
 * Global Theme Switcher
 * Build 3.9.2: Swaps root attribute and forces Toolbar re-discovery.
 */
window.setMetaForgeTheme = function(theme) {
    const html = document.documentElement;
    
    // 1. Update Global Attribute
    html.setAttribute('data-theme', theme);
    
    // 2. Refresh Toolbar Customizer if it is currently visible
    const toolbarBtn = document.getElementById('sub-nav-toolbar');
    if (toolbarBtn && toolbarBtn.classList.contains('active')) {
        window.loadToolbarCustomizer();
    }
};
// --- THEME TOGGLE ENGINE END ---

// --- TOOLBAR DISCOVERY ---
/**
 * Data Handoff: Toolbar Discovery
 * Build 3.9.2: Logic injection for [name]_light.svg based on active data-theme.
 */
window.loadToolbarCustomizer = async function() {
    const grid = document.getElementById('toolbar-customizer-grid');
    if(!grid) return;
    
    grid.innerHTML = '<p style="color:var(--mf-gold); font-size:0.7rem; padding:5px;">Syncing Matrix...</p>';

    // --- SIGNPOST: THEME DETECTION ---
    const isLightMode = document.documentElement.getAttribute('data-theme') === 'light';

    try {
        const res = await fetch('/run_tool_logic/settings/get_discovery');
        const data = await res.json();
        
        if (!data.layout || data.layout.length === 0) {
            grid.innerHTML = '<p class="error-text">Engine Error: toolbar_layout.json empty.</p>';
            return;
        }

        let tableHtml = `<table class="meta-table" style="border-spacing:0; display:table !important;">
            <thead>
                <tr style="text-align:left; border-bottom:1px solid #444;">
                    <th style="padding:4px 8px; font-size:0.8rem; color:var(--mf-gold); letter-spacing:1px;">Show</th>
                    <th style="padding:4px 8px; font-size:0.8rem; color:var(--mf-gold); letter-spacing:1px;">Tool NAME</th>
                    <th style="padding:4px 8px; font-size:0.8rem; color:var(--mf-gold); text-align:center; letter-spacing:1px;">Order</th>
                </tr>
            </thead>
            <tbody>`;

        let rows = "";
        const coreTools = ["dashboard", "settings"];
        let visibleCounter = 1;

        data.layout.forEach((entry) => {
            if (coreTools.includes(entry.id)) return;

            try {
                const tool = data.manifests[entry.id];
                const name = tool ? tool.name : `UNKNOWN (${entry.id})`;
                const checked = entry.visible ? 'checked' : '';
                const locked = (tool && tool.required) ? 'disabled checked' : '';

                // --- SIGNPOST: DYNAMIC ASSET SELECTION ---
                let iconFile = tool.icon || 'default.svg';
                if (isLightMode) {
                    iconFile = iconFile.replace('.svg', '_light.svg');
                }
                const iconPath = `/tool_asset/${entry.id}/${iconFile}`;

                rows += `<tr style="border-bottom:1px solid #222;">
                    <td style="padding:4px 8px;"><input type="checkbox" class="tool-toggle" data-id="${entry.id}" ${checked} ${locked} style="width:14px; height:14px; cursor:pointer;"></td>
                    <td style="padding:4px 8px; font-size:0.75rem; font-weight:bold; color:#ccc; display:flex; align-items:center; gap:10px;">
                        <img src="${iconPath}" style="width:16px; height:16px;">
                        <span>${name}</span>
                    </td>
                    <td style="padding:4px 8px; text-align:center;">
                        <input type="number" class="tool-order" data-id="${entry.id}" value="${visibleCounter}" 
                               style="width:35px; height:18px; background:#000; color:var(--mf-gold); border:1px solid #444; text-align:center; font-size:0.7rem; font-weight:bold; border-radius:2px;">
                    </td>
                </tr>`;
                visibleCounter++;
            } catch (innerError) {
                console.error("METAFORGE DIAGNOSTIC: Row Failure", innerError);
            }
        });

        grid.innerHTML = tableHtml + rows + '</tbody></table>';

    } catch (e) {
        grid.innerHTML = `<p class="error-text">Discovery Bridge Failure: ${e.message}</p>`;
    }
};

// --- TOOLBAR DISCOVERY END ---

// --- TOOLBAR LAYOUT ---
/**
 * Persistence: Save Toolbar Layout
 * Build 3.8: Normalizes user input back to index-safe layout.
 */
window.saveToolbarLayout = async function() {
    const status = document.getElementById('save-status');
    const orderInputs = Array.from(document.querySelectorAll('.tool-order'));
    
    const userLayout = orderInputs.map(input => {
        const tid = input.getAttribute('data-id');
        const toggle = document.querySelector(`.tool-toggle[data-id="${tid}"]`);
        return {
            id: tid,
            order: parseInt(input.value) || 99,
            visible: toggle ? toggle.checked : true
        };
    });

    const finalLayout = [
        { id: "dashboard", visible: true },
        ...userLayout.sort((a, b) => a.order - b.order).map(i => ({ id: i.id, visible: i.visible })),
        { id: "settings", visible: true }
    ];

    try {
        const response = await fetch('/run_tool_logic/settings/save_toolbar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(finalLayout)
        });
        const result = await response.json();
        if (result.status === 'success') {
            status.innerHTML = "<span style='color:var(--mf-gold); font-size:0.7rem;'>✓ Matrix Re-aligned.</span>";
            setTimeout(() => { location.reload(); }, 1000);
        }
    } catch (e) {
        status.innerHTML = `<span class="error-text">Save Failure: ${e.message}</span>`;
    }
};

// --- TOOLBAR LAYOUT END ---

// --- DATA HANDOFF ---
/**
 * Data Handoff: API Config
 */
window.loadAPIConfig = async function() {
    const container = document.getElementById('api-form-container');
    if(!container) return;
    try {
        const res = await fetch('/run_tool_logic/settings/get_env');
        const data = await res.json();
        let html = '<table class="meta-table" style="width:100%;"><tbody>';
        for (const [key, value] of Object.entries(data)) {
            html += `<tr style="border-bottom:1px solid #222;">
                <td style="padding:4px 8px; color:var(--mf-gold); font-size:0.65rem; font-weight:bold;">${key}</td>
                <td style="padding:4px 8px;"><input type="text" class="env-input" data-key="${key}" value="${value}" style="width:95%; background:#111; color:#fff; border:1px solid #444; font-size:0.7rem; padding:2px 5px;"></td>
            </tr>`;
        }
        container.innerHTML = html + '</tbody></table>';
    } catch (e) { container.innerHTML = `<p class="error-text">Bridge Error: ${e.message}</p>`; }
};

/**
 * Data Handoff: Help Aggregator
 */
window.aggregateHelpFiles = async function() {
    const container = document.getElementById('help-aggregator');
    if(!container) return;
    try {
        const res = await fetch('/run_tool_logic/settings/get_help_docs');
        const docs = await res.json();
        let html = "";
        docs.forEach(doc => {
            html += `<details style="margin-bottom:5px; border:1px solid #333; padding:2px; background:#1a1a1a;">
                <summary style="color:var(--mf-gold); cursor:pointer; font-weight:bold; font-size:0.7rem; padding:2px 5px;">${doc.name}</summary>
                <div style="padding:8px 12px; color:#ddd; font-size:0.7rem; line-height:1.3;">${doc.html}</div>
            </details>`;
        });
        container.innerHTML = html || "<p class='gray-text' style='font-size:0.7rem;'>No help files found.</p>";
    } catch (e) { container.innerHTML = `<p class="error-text">Bridge Error: ${e.message}</p>`; }
};

// --- DATA HANDOFF END ---

// --- SAVE ENVIRONMENT ---
/**
 * Persistence: Save Environment
 */
window.saveSettings = async function() {
    const status = document.getElementById('save-status');
    const inputs = document.querySelectorAll('.env-input');
    const config = {};
    inputs.forEach(i => config[i.getAttribute('data-key')] = i.value);

    try {
        const response = await fetch('/run_tool_logic/settings/save_env', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const result = await response.json();
        status.innerHTML = result.status === 'success' ? "<span style='color:var(--mf-gold); font-size:0.7rem;'>✓ Configuration Saved</span>" : "<span class='error-text'>Save Error</span>";
        setTimeout(() => { status.innerHTML = ""; }, 2000);
    } catch (e) { status.innerHTML = "Bridge Error"; }
};

// --- SAVE ENVIRONMENT END ---
// --- SETTINGS ENGINE: CORE LOGIC END ---

// --- AUTO-INITIALIZATION ENGINE ---
(function() {
    const initSettings = () => {
        const toolbarBtn = document.getElementById('sub-nav-toolbar');
        if (toolbarBtn && toolbarBtn.classList.contains('active')) {
            window.loadToolbarCustomizer();
        }
    };
    if (document.readyState === 'complete') {
        setTimeout(initSettings, 250);
    } else {
        window.addEventListener('load', () => setTimeout(initSettings, 250));
    }
})();
// --- AUTO-INITIALIZATION END ---