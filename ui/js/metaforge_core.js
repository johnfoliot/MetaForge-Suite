/**
 * MetaForge Master Logic (V.Core)
 * Orchestration Engine. Build 4.8.0: Monolithic Stability.
 */

// --- GLOBAL UTILITIES ---

/**
 * Global Guard
 */
window.checkMetaForgeBridge = function() {
    if (!window.pywebview || !window.pywebview.api) return false;
    return true;
};

/**
 * Initializer: Fetches preferences and sets branding.
 */
window.initializeMetaForgeBranding = async function() {
    try {
        const response = await fetch('/run_tool_logic/settings/get_prefs');
        if (response.ok) {
            const prefs = await response.json();
            // Set the theme attribute for CSS selectors
            document.documentElement.setAttribute('data-theme', prefs.theme || 'dark');
            
            // Branding Logo Swap logic
            const mainLogo = document.getElementById('mf-main-logo');
            if (mainLogo) {
                mainLogo.src = (prefs.theme === 'light') ? '/ui/images/logo_blue.svg' : '/ui/images/logo.svg';
            }
        }
    } catch (e) {
        console.warn("Branding Boot: Using default.");
    }
};

// --- ENGINE: MODE SWITCHER ---

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

// --- ENGINE: TOOL LOADER ---

window.loadTool = async function(toolId) {
    const stage = document.getElementById('mfi-content');
    if (!stage) return;

    try {
        const response = await fetch(`/get_tool/${toolId}?v=${new Date().getTime()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        stage.innerHTML = await response.text();

        const scriptId = `script-${toolId}`;
        if (!document.getElementById(scriptId)) {
            const script = document.createElement('script');
            script.id = scriptId;
            script.src = `/tool_asset/${toolId}/${toolId}.js?v=${new Date().getTime()}`;
            script.type = 'text/javascript';
            document.head.appendChild(script);
        }

        setTimeout(() => {
            const heading = stage.querySelector('h1.main') || stage.querySelector('h1');
            if (heading) {
                heading.setAttribute('tabindex', '-1');
                heading.focus();
            }
            if (toolId === 'settings' && typeof window.showSettingsPanel === 'function') {
                window.showSettingsPanel('personalization');
            }
        }, 10);
        
    } catch (error) {
        console.error("MetaForge Load Error:", error);
        stage.innerHTML = `<div style="color:var(--status-error); padding: 20px;">⚠️ Failed to load tool: ${toolId}</div>`;
    }
};

// --- AUTO-START TRIGGER ---

document.addEventListener('DOMContentLoaded', () => {
    window.initializeMetaForgeBranding();

    setTimeout(() => {
        window.mfSwitchMode('dashboard');
    }, 150);
});