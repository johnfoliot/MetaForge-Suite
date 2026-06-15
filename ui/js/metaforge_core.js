// --- START OF FILE [D:\MetaForge Suite\ui\js\metaforge_core.js] ---
/**
 * MetaForge Master Logic (V.Core)
 * Orchestration Engine. Build 4.9.3: Modern Event Delegation & Sanitization.
 * Accessibility: WCAG 2.2 AA | COGA 4.3.1
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

/**
 * ENGINE: WORKFLOW ORCHESTRATOR (Build 4.9.3)
 * Allows autonomous tools to trigger a global mode switch with context passing.
 */
window.mfAdvanceWorkflow = function(targetToolId, contextPath = null) {
    console.log(`%c METAFORGE: Advancing workflow to ${targetToolId}... `, 'background: #cc9900; color: #000; font-weight: bold;');
    
    if (contextPath) {
        console.log(`METAFORGE: Path context cached for next tool: ${contextPath}`);
        window.mf_context_path = contextPath;
    }

    // Trigger the mode switch which loads the target tool
    window.mfSwitchMode(targetToolId);
};

// --- ENGINE: TOOL LOADER ---

/**
 * Modular Tool Loader with Lifecycle Synchronization and Event Cleanup.
 */
window.loadTool = async function(toolId) {
    const stage = document.getElementById('mfi-content');
    if (!stage) return;

    // Track the currently active tool ID to manage cleanup scoping
    const previousToolId = window.metaforge_current_tool;
    
    // Lifecycle Event: Fire teardown hook if the outgoing tool namespace exposed one
    if (previousToolId && window.metaforge && window.metaforge[previousToolId]) {
        const prevNamespace = window.metaforge[previousToolId];
        if (typeof prevNamespace.destroy === 'function') {
            console.log(`METAFORGE: Tearing down Lifecycle for ${previousToolId}`);
            try {
                prevNamespace.destroy();
            } catch (err) {
                console.error(`MetaForge Teardown Error inside ${previousToolId}:`, err);
            }
        }
    }
    
    // Bridge Lifecycle: Abort previous event listeners
    if (window.metaforge.bridge) {
        window.metaforge.bridge.teardown();
        window.metaforge.bridge.init();
    }

    try {
        const response = await fetch(`/get_tool/${toolId}?v=${new Date().getTime()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        stage.innerHTML = await response.text();
        
        // Update global tracking context to the new module ID
        window.metaforge_current_tool = toolId;

        const scriptId = `script-${toolId}`;
        let script = document.getElementById(scriptId);

        const initTool = () => {
            setTimeout(() => {
                // Focus Management
                const heading = stage.querySelector('h1.main') || stage.querySelector('h1');
                if (heading) { heading.setAttribute('tabindex', '-1'); heading.focus(); }
                
                // --- INTEGRATION: Common Component Initialization ---
                if (window.metaforge.ui && typeof window.metaforge.ui.initCommonComponents === 'function') {
                    window.metaforge.ui.initCommonComponents();
                }

                // Build 4.9.3: Physical Lifecycle Handshake
                const toolNamespace = window.metaforge ? window.metaforge[toolId] : null;
                if (toolNamespace && typeof toolNamespace.init === 'function') {
                    console.log(`METAFORGE: Synchronizing Lifecycle for ${toolId}`);
                    toolNamespace.init();
                }

                // Specialized Settings Handler
                if (toolId === 'settings' && typeof window.showSettingsPanel === 'function') {
                    window.showSettingsPanel('personalization');
                }
            }, 30); // 30ms paint guard
        };

        if (!script) {
            script = document.createElement('script');
            script.id = scriptId;
            script.type = 'text/javascript';
            script.src = `/tool_asset/${toolId}/${toolId}.js?v=${new Date().getTime()}`;
            script.onload = initTool;
            document.head.appendChild(script);
        } else {
            initTool();
        }
        
    } catch (error) {
        console.error("MetaForge Load Error:", error);
        stage.innerHTML = `<div style="color:var(--status-error); padding: 20px;">⚠️ Failed to load tool: ${toolId}</div>`;
    }
};

// --- CENTRALIZED EVENT DELEGATION & SANITIZATION ---

function setupGlobalNavigationListeners() {
    document.addEventListener('click', (event) => {
        const targetNav = event.target.closest('.nav-item, .settings-btn');
        if (!targetNav) return;

        const elementId = targetNav.id || '';
        if (elementId.startsWith('mode-')) {
            event.preventDefault();
            const targetMode = elementId.substring(5);
            if (targetMode) {
                window.mfSwitchMode(targetMode);
            }
        }
    });
}

// --- AUTO-START TRIGGER ---

document.addEventListener('DOMContentLoaded', () => {
    window.initializeMetaForgeBranding();
    setupGlobalNavigationListeners();
    setTimeout(() => { window.mfSwitchMode('dashboard'); }, 150);
});
// --- END OF FILE [D:\MetaForge Suite\ui\js\metaforge_core.js] ---