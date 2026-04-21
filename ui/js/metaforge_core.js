/**
 * MetaForge Master Logic (V.Core)
 * The Application Shell: Handles orchestration, navigation, and global utilities.
 * Tool-specific business logic must be siloed in /tools/[tool_id]/[tool_id].js.
 */

// --- GLOBAL UTILITIES ---

/**
 * Global Guard: Verifies the Python Bridge (pywebview) is initialized.
 */
window.checkMetaForgeBridge = function() {
    if (!window.pywebview || !window.pywebview.api) {
        console.error("MetaForge Error: Python Bridge (pywebview.api) is not initialized.");
        const consoleDiv = document.querySelector('[id$="Console"]') || document.querySelector('[id$="-console"]') || document.querySelector('.console-scroll');
        if (consoleDiv) {
            consoleDiv.innerHTML = '<div style="color:#ff0000; font-weight:bold;">🔥 SYSTEM ERROR: Python connection not initialized. Please restart the app.</div>';
        }
        return false;
    }
    return true;
};

/**
 * THE UNIVERSAL PICKER: A standardized wrapper for the Python Bridge.
 */
window.getFolderPath = async function() {
    if (!window.checkMetaForgeBridge()) return null;
    try {
        const path = await window.pywebview.api.select_folder();
        return path || null;
    } catch (err) {
        console.error("MetaForge Shell: Global Folder Picker failed", err);
        return null;
    }
};

// --- GLOBAL UTILITIES END ---

// --- ENGINE: MODE SWITCHER ---

/**
 * Standard UI Mode Switcher
 */
window.switchMode = function(mode) {
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

    if (typeof loadTool === 'function') {
        loadTool(mode);
    }
};

// --- ENGINE: MODE SWITCHER END ---

// --- NO EDITS BEYOND THIS POINT - TOOL LOADER MUST COME LAST ---

// --- ENGINE: TOOL LOADER ---

/**
 * Modular Tool Loader
 */
async function loadTool(toolId) {
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

        if (toolId === 'settings' && typeof window.showSettingsPanel === 'function') {
            window.showSettingsPanel('personalization');
        }
        
    } catch (error) {
        console.error("MetaForge Load Error:", error);
        stage.innerHTML = `<div style="color:#ff0000; padding: 20px;">⚠️ Failed to load tool: ${toolId}</div>`;
    }
}

/**
 * AUTO-START TRIGGER: Boots the Dashboard on initial launch.
 */
document.addEventListener('DOMContentLoaded', () => {
    // Small delay to ensure the bridge and CSS variables are fully parsed
    setTimeout(() => {
        window.switchMode('dashboard');
    }, 100);
});

// --- ENGINE: TOOL LOADER END ---