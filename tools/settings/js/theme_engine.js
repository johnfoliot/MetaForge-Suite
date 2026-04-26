// --- SETTINGS MINI-ENGINE: theme_engine.js ---
/**
 * Standalone Theme Discovery & Swapper. Build 5.2.2
 * Handles the Canadian Palette Audit and physical CSS link-tag swapping.
 */

window.metaforge.settings.themes = {
    /**
     * Entry Point: Fetches discovered theme fragments from Python.
     */
    load: async function() {
        const grid = document.getElementById('theme-selector-grid');
        if (!grid) return;

        grid.innerHTML = '<p class="tool_notes">Auditing colour palettes...</p>';

        try {
            const res = await fetch('/run_tool_logic/settings/get_themes');
            const themes = await res.json();

            if (!themes || themes.length === 0) {
                grid.innerHTML = '<p class="error-text">No theme fragments discovered.</p>';
                return;
            }

            this.render(themes);
        } catch (e) { 
            grid.innerHTML = `<p class="error-text">Theme discovery failure: ${e.message}</p>`; 
        }
    },

    /**
     * Renders the expert-level palette matrix.
     */
    render: function(themes) {
        const grid = document.getElementById('theme-selector-grid');
        
        // Semantic Canadian Label Map for the Audit
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
                     style="width: 220px;"
                     onclick="metaforge.settings.themes.preview('${theme.file}')" 
                     onkeydown="if(event.key==='Enter'||event.key===' ') metaforge.settings.themes.preview('${theme.file}')">
                    
                    <h4 class="data-text" style="color: var(--mf-gold); border-bottom: 1px solid var(--bg-accent); margin-bottom: 8px; padding-bottom: 4px;">${theme.name}</h4>
                    ${paletteHtml}
                </div>`;
        });
        grid.innerHTML = html;
    },

    /**
     * Visual Preview: Performs physical link-tag swap via the core bridge.
     */
    preview: function(themeFile) {
        // 1. Dispatch to Global Link Swapper in core.js
        if (typeof window.applyThemeFile === 'function') {
            window.applyThemeFile(themeFile);
        }

        // 2. Handle the Branding Logo Swap (Brute Force)
        const mainLogo = document.getElementById('mf-main-logo');
        if (mainLogo) {
            mainLogo.src = (themeFile.includes('light')) ? '/ui/images/logo_blue.svg' : '/ui/images/logo.svg';
        }

        // 3. UI Status Feedback
        const status = document.getElementById('save-status');
        if (status) {
            status.innerHTML = `<span style="color:var(--mf-gold); font-size:0.75rem;">Previewing [${themeFile}]. Click commit to save.</span>`;
        }
    },

    /**
     * Physically commits the selection to preferences.json.
     */
    save: async function() {
        const themeLink = document.getElementById('mf-theme-stylesheet');
        // Extract filename from current active link tag
        const themeFile = themeLink.href.split('/').pop().split('?')[0];
        const status = document.getElementById('save-status');
        
        try {
            const response = await fetch('/run_tool_logic/settings/save_prefs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ "theme_file": themeFile })
            });
            const result = await response.json();
            if (result.status === 'success') {
                status.innerHTML = "<span style='color:var(--status-success); font-size:0.75rem;'>✓ Theme choice physically committed.</span>";
                setTimeout(() => { status.innerHTML = ""; }, 3000);
            }
        } catch (e) { 
            console.error("Theme Save Error:", e); 
        }
    }
};

// --- SETTINGS MINI-ENGINE: theme_engine.js END ---