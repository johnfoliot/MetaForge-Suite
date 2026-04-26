// --- SETTINGS UI LOGIC ---
/**
 * Settings Tool Engine. Build 5.1.5: Clean Class-Based UI Generation.
 * Removed inline style overrides to respect Global Layout Engine.
 */

// --- PANEL NAVIGATION ---

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
    
    if(target) {
        target.style.display = 'block';
        setTimeout(() => {
            let focusTarget = null;
            switch(panelId) {
                case 'personalization': focusTarget = target.querySelector('.sub-nav-btn.active'); break;
                case 'api-keys': focusTarget = target.querySelector('.env-input'); break;
                case 'help': focusTarget = target.querySelector('summary'); break;
                case 'updates': focusTarget = target.querySelector('h2'); break;
                default: focusTarget = target.querySelector('h2');
            }
            if (focusTarget) {
                if (!focusTarget.hasAttribute('tabindex')) focusTarget.setAttribute('tabindex', '-1');
                focusTarget.focus();
            }
        }, 10);
    }

    if(panelId === 'api-keys') window.loadAPIConfig();
    if(panelId === 'help') window.aggregateHelpFiles();
    if(panelId === 'updates') window.runBinaryAudit();
    if(panelId === 'personalization') {
        const activeSub = document.querySelector('.sub-nav-btn.active');
        if (activeSub && activeSub.id === 'sub-nav-theme') window.loadThemeSwitcher();
        if (activeSub && activeSub.id === 'sub-nav-toolbar') window.loadToolbarCustomizer();
        if (activeSub && activeSub.id === 'sub-nav-taxonomy') window.loadTaxonomyEditor();
    }
};

window.showSubPanel = function(subId, element) {
    document.querySelectorAll('.sub-nav-btn').forEach(btn => btn.classList.remove('active'));
    if(element) element.classList.add('active');

    document.querySelectorAll('.personalization-sub-panel').forEach(p => p.style.display = 'none');
    const target = document.getElementById('sub-panel-' + subId);
    
    if(target) {
        target.style.display = 'block';
        setTimeout(() => {
            const subHeader = target.querySelector('h2');
            if (subHeader) {
                if (!subHeader.hasAttribute('tabindex')) subHeader.setAttribute('tabindex', '-1');
                subHeader.focus();
            }
        }, 10);
    }

    if (subId === 'theme') window.loadThemeSwitcher();
    if (subId === 'toolbar') window.loadToolbarCustomizer();
    if (subId === 'taxonomy') window.loadTaxonomyEditor();
};

// --- THEME ENGINE ---

window.loadThemeSwitcher = async function() {
    const grid = document.getElementById('theme-selector-grid');
    if (!grid) return;

    grid.innerHTML = '<p class="tool_notes">Auditing colour palettes...</p>';

    const labelMap = {
        '--bg-main': 'background colour',
        '--bg-stage': 'main stage colour',
        '--mf-gold': 'branding colour',
        '--text-output': 'text colour',
        '--text-message': 'message colour',
        '--status-success': 'success message',
        '--status-error': 'error message',
        '--input-foreground': 'form input-foreground',
        '--input-background': 'form input-background'
    };

    try {
        const res = await fetch('/run_tool_logic/settings/get_themes');
        const themes = await res.json();

        if (!themes || themes.length === 0) {
            grid.innerHTML = '<p class="error-text">No theme fragments discovered.</p>';
            return;
        }

        let html = '';
        themes.forEach(theme => {
            let paletteHtml = '<div style="display: flex; flex-direction: column; gap: 4px; text-align: left;">';
            for (const [varName, label] of Object.entries(labelMap)) {
                const hex = theme.palette[varName] || '#333';
                paletteHtml += `
                    <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px;">
                        <span class="data-text" style="font-size: 0.65rem; color: var(--text-message);">${label}:</span>
                        <div class="mf-swatch" style="background: ${hex}; width: 14px; height: 14px; border: 1px solid rgba(255,255,255,0.1);"></div>
                    </div>`;
            }
            paletteHtml += '</div>';

            html += `
                <div role="button" 
                     tabindex="0" 
                     class="mf-selection-card" 
                     onclick="window.previewThemeFile('${theme.file}')" 
                     onkeydown="if(event.key==='Enter'||event.key===' ') window.previewThemeFile('${theme.file}')">
                    <h4 class="data-text" style="color: var(--mf-gold); border-bottom: 1px solid var(--bg-accent); margin-bottom: 8px; padding-bottom: 4px;">${theme.name}</h4>
                    ${paletteHtml}
                </div>`;
        });
        grid.innerHTML = html;
    } catch (e) { grid.innerHTML = `<p class="error-text">Discovery Failure: ${e.message}</p>`; }
};

window.previewThemeFile = function(themeFile) {
    if (typeof window.applyThemeFile === 'function') {
        window.applyThemeFile(themeFile);
    }
    const mainLogo = document.getElementById('mf-main-logo');
    if (mainLogo) {
        mainLogo.src = (themeFile.includes('light')) ? '/ui/images/logo_blue.svg' : '/ui/images/logo.svg';
    }
    document.getElementById('save-status').innerHTML = `<span style="color:var(--mf-gold); font-size:0.75rem;">Previewing [${themeFile}]. Click Commit to save.</span>`;
};

window.saveThemePreference = async function() {
    const themeLink = document.getElementById('mf-theme-stylesheet');
    const themeFile = themeLink.href.split('/').pop().split('?')[0];
    try {
        const response = await fetch('/run_tool_logic/settings/save_prefs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ "theme_file": themeFile })
        });
        const result = await response.json();
        if (result.status === 'success') {
            document.getElementById('save-status').innerHTML = "✓ Theme preference committed.";
            setTimeout(() => { document.getElementById('save-status').innerHTML = ""; }, 3000);
        }
    } catch (e) { console.error("Save Error:", e); }
};

// --- TOOLBAR CUSTOMIZER ---

window.loadToolbarCustomizer = async function() {
    const grid = document.getElementById('toolbar-customizer-grid');
    if(!grid) return;
    try {
        const res = await fetch('/run_tool_logic/settings/get_discovery');
        const data = await res.json();
        let html = `<table class="meta-table"><thead><tr style="text-align:left; color:var(--mf-gold); border-bottom:1px solid var(--bg-accent);"><th style="padding:4px 8px;">Show</th><th style="padding:4px 8px;">Tool</th><th style="padding:4px 8px; text-align:center;">Order</th></tr></thead><tbody>`;
        data.layout.forEach((entry) => {
            if (["dashboard", "settings"].includes(entry.id)) return;
            const tool = data.manifests[entry.id];
            const iconPath = `/tool_asset/${entry.id}/${tool.icon || 'default.svg'}`;
            // Removed inline widths and backgrounds; using global classes instead
            html += `<tr style="border-bottom:1px solid var(--bg-main);">
                <td style="padding:4px 8px;"><input type="checkbox" class="tool-toggle" data-id="${entry.id}" ${entry.visible ? 'checked' : ''} ${(tool && tool.required) ? 'disabled checked' : ''}></td>
                <td style="padding:4px 8px; display:flex; align-items:center; gap:10px;"><div class="mf-icon-mask" style="-webkit-mask-image: url('${iconPath}'); mask-image: url('${iconPath}'); width:16px; height:16px; background-color: var(--mf-gold);"></div><span class="data-text">${tool ? tool.name : entry.id}</span></td>
                <td style="padding:4px 8px; text-align:center;"><input type="number" class="tool-order" data-id="${entry.id}" value="${entry.order || 99}"></td>
            </tr>`;
        });
        grid.innerHTML = html + '</tbody></table>';
    } catch (e) { console.error(e); }
};

window.saveToolbarLayout = async function() {
    const status = document.getElementById('save-status');
    const orderInputs = Array.from(document.querySelectorAll('.tool-order'));
    const userLayout = orderInputs.map(input => {
        const tid = input.getAttribute('data-id');
        const toggle = document.querySelector(`.tool-toggle[data-id="${tid}"]`);
        return { id: tid, userOrder: parseInt(input.value) || 99, visible: toggle ? toggle.checked : true };
    });
    userLayout.sort((a, b) => { if (a.userOrder !== b.userOrder) return a.userOrder - b.userOrder; return a.id.localeCompare(b.id); });
    const finalLayout = [{ id: "dashboard", visible: true }, ...userLayout.map((item, index) => ({ id: item.id, visible: item.visible, order: index + 1 })), { id: "settings", visible: true }];
    try {
        const res = await fetch('/run_tool_logic/settings/save_toolbar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(finalLayout) });
        const result = await res.json();
        if (result.status === 'success') { status.innerHTML = "<span style='color:var(--mf-gold);'>✓ Matrix re-aligned.</span>"; setTimeout(() => { location.reload(); }, 1000); }
    } catch (e) { console.error(e); }
};

// --- REMAINING ENGINES ---

window.runBinaryAudit = async function() {
    const container = document.getElementById('binary-audit-container');
    if(!container) return;
    container.innerHTML = '<p class="tool_notes">Checking files and dependencies...</p>';
    try {
        const res = await fetch('/run_tool_logic/settings/check_binaries');
        const results = await res.json();
        let html = `<table class="meta-table"><thead><tr style="text-align:left; color:var(--mf-gold); border-bottom:1px solid var(--bg-accent);"><th style="padding:8px;">Component</th><th style="padding:8px;">Version</th><th style="padding:8px; text-align:center;">Status</th></tr></thead><tbody>`;
        results.forEach(bin => {
            const sc = bin.status === 'ok' ? 'var(--status-success)' : 'var(--status-error)';
            html += `<tr style="border-bottom:1px solid var(--bg-main);"><td class="data-text" style="padding:8px;">${bin.name}</td><td class="data-text" style="padding:8px;">${bin.version}</td><td class="data-text" style="padding:8px; text-align:center; color:${sc}; font-weight:bold;">${bin.status.toUpperCase()}</td></tr>`;
        });
        container.innerHTML = html + '</tbody></table>';
    } catch (e) { console.error(e); }
};

window.loadTaxonomyEditor = async function() {
    const container = document.getElementById('taxonomy-manager-container');
    if(!container) return;
    try {
        const res = await fetch('/run_tool_logic/settings/get_taxonomy');
        window.taxonomy_state = await res.json();
        window.renderTaxonomyUI();
    } catch (e) { console.error(e); }
};

window.renderTaxonomyUI = function() {
    const container = document.getElementById('taxonomy-manager-container');
    const parents = Object.keys(window.taxonomy_state).sort();
    let html = `<div style="display: flex; gap: 20px; min-height: 450px;"><section style="width: 35%; border-right: 1px solid var(--bg-accent); overflow-y: auto; padding-right: 10px;" aria-labelledby="mf-taxonomy-genre-label"><h2 id="mf-taxonomy-genre-label" style="color: var(--text-output); font-size: 1.5rem; margin: 0 0 15px 0; border-bottom: 1px solid var(--bg-accent);">Genre</h2><ul role="listbox" aria-labelledby="mf-taxonomy-genre-label" style="list-style:none; padding:0;">${parents.map(p => `<li role="option" tabindex="0" class="taxonomy-item ${window.active_parent === p ? 'active' : ''}" aria-selected="${window.active_parent === p}" onclick="window.selectTaxonomyParent('${p}')" onkeydown="if(event.key==='Enter'||event.key===' ') window.selectTaxonomyParent('${p}')">${p}</li>`).join('')}</ul><div style="margin-top:20px; border-top: 1px solid var(--bg-accent); padding-top: 10px;"><label class="data-text" for="new-parent-name" style="display:block;">Add category</label><input type="text" id="new-parent-name" class="mf-input" placeholder="New Genre..." style="margin-bottom: 5px;"><button class="mf-button-gold-fixed" onclick="window.addTaxonomyParent()">Add genre</button></div></section><section style="flex: 2; overflow-y: auto;" aria-labelledby="mf-taxonomy-subgenre-label"><h2 id="mf-taxonomy-subgenre-label" style="color: var(--text-output); font-size: 1.5rem; margin: 0 0 15px 0; border-bottom: 1px solid var(--bg-accent);">Sub-genre</h2><div id="sub-genre-controls">${window.renderSubGenreControls()}</div></section></div>`;
    container.innerHTML = html;
};

window.renderSubGenreControls = function() {
    if (!window.active_parent) return '<p class="tool_notes">Select a genre to manage its sub-taxonomies.</p>';
    const subs = window.taxonomy_state[window.active_parent] || [];
    return `<h3 class="data-text" style="margin-bottom:15px; font-size: 1rem; color: var(--mf-gold);">Editing: ${window.active_parent}</h3><ul style="list-style:none; padding:0;">${subs.map((s, idx) => `<li style="display:flex; gap:10px; margin-bottom:8px; align-items:center;"><label class="data-text" for="sub-genre-${idx}" style="min-width: 8rem;">Edit name</label><input type="text" id="sub-genre-${idx}" class="mf-input sub-genre-input" value="${s}" onchange="window.updateSubGenre(${idx}, this.value)" style="flex:1;"><button class="mf-btn-danger" onclick="window.removeSubGenre(${idx})">×</button></li>`).join('')}</ul><div style="margin-top:20px; padding-top: 15px; border-top: 1px solid var(--bg-accent); display:flex; gap:10px; align-items:center;"><label class="data-text" for="new-sub-name" style="min-width: 8rem;">New sub-genre</label><input type="text" id="new-sub-name" class="mf-input" placeholder="Name..."><button class="mf-button-gold-fixed" onclick="window.addSubGenre()">Add</button></div><div style="margin-top:30px; display:flex; gap:10px; align-items:center;"><button class="mf-btn-danger" onclick="window.removeParentGenre()">Delete category</button><button class="mf-button-gold-fixed" style="margin-top:0;" onclick="window.commitTaxonomy()">Commit taxonomy changes</button></div>`;
};

window.loadAPIConfig = async function() {
    const container = document.getElementById('api-form-container');
    if(!container) return;
    try {
        const res = await fetch('/run_tool_logic/settings/get_env');
        const data = await res.json();
        let html = '<table class="meta-table"><tbody>';
        for (const [key, value] of Object.entries(data)) {
            html += `<tr style="border-bottom:1px solid var(--bg-main);"><td style="padding:4px 8px; color:var(--mf-gold); font-size:0.75rem; font-weight:bold;">${key}</td><td style="padding:4px 8px;"><input type="text" class="env-input" data-key="${key}" value="${value}" style="width:100%;"></td></tr>`;
        }
        container.innerHTML = html + '</tbody></table>';
    } catch (e) { console.error(e); }
};

window.saveSettings = async function() {
    const status = document.getElementById('save-status');
    const inputs = document.querySelectorAll('.env-input');
    const config = {};
    inputs.forEach(i => config[i.getAttribute('data-key')] = i.value);
    try {
        const res = await fetch('/run_tool_logic/settings/save_env', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
        const result = await res.json();
        if (result.status === 'success') { status.innerHTML = "<span style='color:var(--mf-gold);'>✓ Config saved.</span>"; setTimeout(() => { status.innerHTML = ""; }, 2000); }
    } catch (e) { status.innerHTML = "Error"; }
};

window.aggregateHelpFiles = async function() {
    const container = document.getElementById('help-aggregator');
    if(!container) return;
    try {
        const res = await fetch('/run_tool_logic/settings/get_help_docs');
        const docs = await res.json();
        let html = "";
        docs.forEach(doc => {
            html += `<details style="margin-bottom:5px; border:1px solid var(--bg-accent); padding:2px; background:var(--bg-main);"><summary style="color:var(--mf-gold); cursor:pointer; font-weight:bold; font-size:0.75rem; padding:2px 5px;">${doc.name}</summary><div style="padding:8px 12px; color:var(--text-message); font-size:0.8rem; line-height:1.3;">${doc.html}</div></details>`;
        });
        container.innerHTML = html || "No help docs found.";
    } catch (e) { console.error(e); }
};

// --- SETTINGS UI LOGIC END ---