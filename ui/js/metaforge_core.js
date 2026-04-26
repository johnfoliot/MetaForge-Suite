// --- LOGIC BRIDGE ---
/**
 * MetaForge Master Logic (V.Core)
 * Orchestration Engine. Build 4.8.2: Asynchronous Script Guard.
 */

// --- GLOBAL UTILITIES ---

window.checkMetaForgeBridge = function() {
    if (!window.pywebview || !window.pywebview.api) return false;
    return true;
};

window.applyThemeFile = function(themeFileName) {
    const themeLink = document.getElementById('mf-theme-stylesheet');
    if (!themeLink) return;
    themeLink.href = `/ui/css/${themeFileName}?v=${new Date().getTime()}`;
    const themeName = themeFileName.replace('_theme.css', '');
    document.documentElement.setAttribute('data-theme', themeName);
};

window.initializeMetaForgeBranding = async function() {
    try {
        const response = await fetch('/run_tool_logic/settings/get_prefs');
        if (response.ok) {
            const prefs = await response.json();
            document.documentElement.setAttribute('data-theme', prefs.theme_file ? prefs.theme_file.replace('_theme.css', '') : 'dark');
            if (prefs.theme_file) window.applyThemeFile(prefs.theme_file);
            const mainLogo = document.getElementById('mf-main-logo');
            if (mainLogo && prefs.theme_file) {
                mainLogo.src = (prefs.theme_file.includes('light')) ? '/ui/images/logo_blue.svg' : '/ui/images/logo.svg';
            }
        }
    } catch (e) { console.warn("Branding Boot Error"); }
};

// --- ENGINE: MODE SWITCHER ---

window.mfSwitchMode = function(mode) {
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

// --- ENGINE: TOOL LOADER ---

/**
 * Modular Tool Loader with Script Guard.
 */
window.loadTool = async function(toolId) {
    const stage = document.getElementById('mfi-content');
    if (!stage) return;

    try {
        const response = await fetch(`/get_tool/${toolId}?v=${new Date().getTime()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        stage.innerHTML = await response.text();

        // 1. DYNAMIC SCRIPT INJECTION WITH ONLOAD GUARD
        const scriptId = `script-${toolId}`;
        let script = document.getElementById(scriptId);

        const initTool = () => {
            setTimeout(() => {
                const heading = stage.querySelector('h1.main') || stage.querySelector('h1');
                if (heading) { heading.setAttribute('tabindex', '-1'); heading.focus(); }
                
                // Initialize Settings specifically if it's the target
                if (toolId === 'settings' && typeof window.showSettingsPanel === 'function') {
                    window.showSettingsPanel('personalization');
                }
            }, 20);
        };

        if (!script) {
            script = document.createElement('script');
            script.id = scriptId;
            script.type = 'text/javascript';
            script.src = `/tool_asset/${toolId}/${toolId}.js?v=${new Date().getTime()}`;
            // IMPORTANT: Wait for script to be "Live" before calling its functions
            script.onload = initTool;
            document.head.appendChild(script);
        } else {
            // Script already exists, just initialize
            initTool();
        }
        
    } catch (error) {
        console.error("MetaForge Load Error:", error);
        stage.innerHTML = `<div style="color:var(--status-error); padding: 20px;">⚠️ Failed to load tool: ${toolId}</div>`;
    }
};

// --- AUTO-START TRIGGER ---

document.addEventListener('DOMContentLoaded', () => {
    window.initializeMetaForgeBranding();
    setTimeout(() => { window.mfSwitchMode('dashboard'); }, 150);
});
// --- LOGIC BRIDGE END ---