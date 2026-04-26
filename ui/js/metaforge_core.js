// --- LOGIC BRIDGE ---
/**
 * MetaForge Master Logic (V.Core)
 * Orchestration Engine. Build 4.8.1: Hardened Theme & Asset Routing.
 */

// --- GLOBAL UTILITIES ---

/**
 * Global Guard: Verifies the Python Bridge (pywebview) is initialized.
 */
window.checkMetaForgeBridge = function() {
    if (!window.pywebview || !window.pywebview.api) return false;
    return true;
};

/**
 * THE THEME ENGINE: Physically swaps the Skin CSS file.
 * Build 4.8.1: Hardened path resolution and cache busting.
 */
window.applyThemeFile = function(themeFileName) {
    const themeLink = document.getElementById('mf-theme-stylesheet');
    if (!themeLink) {
        console.error("MetaForge Error: mf-theme-stylesheet link tag missing.");
        return;
    }

    // Physically swap the href. Path is relative to the webserver root.
    themeLink.href = `/ui/css/${themeFileName}?v=${new Date().getTime()}`;
    
    // Set data-theme attribute for legacy CSS selectors
    const themeName = themeFileName.replace('_theme.css', '');
    document.documentElement.setAttribute('data-theme', themeName);
    
    console.log(`MetaForge: Theme switched to [${themeName}]`);
};

/**
 * Initializer: Fetches user preferences and boots the branding.
 */
window.initializeMetaForgeBranding = async function() {
    try {
        const response = await fetch('/run_tool_logic/settings/get_prefs');
        if (response.ok) {
            const prefs = await response.json();
            
            // 1. Apply Saved Theme File
            if (prefs.theme_file) {
                window.applyThemeFile(prefs.theme_file);
            }

            // 2. Apply Physical Logo Swap based on theme name
            const mainLogo = document.getElementById('mf-main-logo');
            if (mainLogo && prefs.theme_file) {
                mainLogo.src = (prefs.theme_file.includes('light')) ? '/ui/images/logo_blue.svg' : '/ui/images/logo.svg';
            }
        }
    } catch (e) {
        console.warn("Branding Boot: Preferences file not yet initialized.");
    }
};

// --- GLOBAL UTILITIES END ---


// --- ENGINE: MODE SWITCHER ---

/**
 * Global UI Mode Switcher: Renamed to prevent recursion loops.
 */
window.mfSwitchMode = function(mode) {
    console.log(`MetaForge Engine: Loading [${mode}]`);
    
    const items = document.querySelectorAll('.nav-item, .settings-btn');
    items.forEach(el => {
        el.classList.remove('active');
        el.setAttribute('aria-pressed', 'false');
    });
    
    const activeEl = document.getElementById('mode-' + mode);
    if(activeEl) {
        activeEl.classList.add('active');
        activeEl.setAttribute('aria-pressed', 'true');
    }

    window.loadTool(mode);
};

// --- ENGINE: MODE SWITCHER END ---


// --- ENGINE: TOOL LOADER ---

/**
 * Modular Tool Loader: physically injects .mfi fragments.
 */
window.loadTool = async function(toolId) {
    const stage = document.getElementById('mfi-content');
    if (!stage) return;

    try {
        const response = await fetch(`/get_tool/${toolId}?v=${new Date().getTime()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        stage.innerHTML = await response.text();

        // 1. Dynamic Script Injection
        const scriptId = `script-${toolId}`;
        if (!document.getElementById(scriptId)) {
            const script = document.createElement('script');
            script.id = scriptId;
            script.src = `/tool_asset/${toolId}/${toolId}.js?v=${new Date().getTime()}`;
            script.type = 'text/javascript';
            document.head.appendChild(script);
        }

        // 2. --- STAGE HANDOFF FOCUS GUARD (Directive II.3) ---
        setTimeout(() => {
            const heading = stage.querySelector('h1.main') || stage.querySelector('h1');
            if (heading) {
                heading.setAttribute('tabindex', '-1');
                heading.focus();
            }
            
            // Post-load initialization for settings tool
            if (toolId === 'settings' && typeof window.showSettingsPanel === 'function') {
                window.showSettingsPanel('personalization');
            }
        }, 10);
        
    } catch (error) {
        console.error("MetaForge Load Error:", error);
        stage.innerHTML = `<div style="color:var(--status-error); padding: 20px;">⚠️ Failed to load tool: ${toolId}</div>`;
    }
};

// --- ENGINE: TOOL LOADER END ---


// --- AUTO-START TRIGGER ---

/**
 * Main Entry Point: Bootstrap sequence.
 */
document.addEventListener('DOMContentLoaded', () => {
    // 1. Boot Theme and Branding
    window.initializeMetaForgeBranding();

    // 2. Boot Dashboard with Focus Guard
    setTimeout(() => {
        if (typeof window.mfSwitchMode === 'function') {
            window.mfSwitchMode('dashboard');
        }
    }, 150);
});

// --- AUTO-START TRIGGER END ---