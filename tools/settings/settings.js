// --- START OF FILE settings.js ---
/**
 * Settings Tool Hub (V.Core - Build 5.3.13)
 * Handles Namespace Initialization, Sequential Boot Loading, and Panel Navigation.
 * Adheres to MetaForge Production Directive IV.2 (Hub & Spoke Architecture).
 * Build 5.3.13: Implemented Boot-Lock to prevent duplicate script loading.
 */

// --- 1. NAMESPACE INITIALIZATION (Immediate) ---
window.metaforge = window.metaforge || {};
window.metaforge.settings = window.metaforge.settings || {
    state: {
        activeParentGenre: null,
        taxonomy: {}
    },
    booted: false,
    booting: null // Boot Lock Promise
};

/**
 * Sequential Boot Loader (Directive IV.2)
 * Physically injects the mini-engines from the /js/ subdirectory.
 * Hardened to prevent race-condition duplicate loading.
 */
window.metaforge.settings.boot = async function() {
    // If already booted, exit
    if (window.metaforge.settings.booted) return true;
    
    // If a boot is currently in progress, return the existing promise
    if (window.metaforge.settings.booting) return window.metaforge.settings.booting;

    // Create the boot promise (The Lock)
    window.metaforge.settings.booting = (async () => {
        const toolRoot = "/tool_asset/settings/js";
        const engines = [
            "api_engine.js",
            "theme_engine.js",
            "audit_engine.js",
            "help_engine.js",
            "toolbar_engine.js",
            "taxonomy_engine.js",
            "update_engine.js"
        ];

        try {
            for (const engine of engines) {
                await new Promise((resolve, reject) => {
                    const script = document.createElement('script');
                    script.src = `${toolRoot}/${engine}?v=${new Date().getTime()}`;
                    script.type = 'text/javascript';
                    script.onload = resolve;
                    script.onerror = () => {
                        console.error(`MetaForge: Failed to load engine ${engine}`);
                        resolve(); 
                    };
                    document.head.appendChild(script);
                });
            }
            window.metaforge.settings.booted = true;
            console.log("MetaForge Settings: Spoke engines synchronized.");
            return true;
        } catch (e) {
            console.error("MetaForge Settings Boot Error:", e);
            return false;
        } finally {
            window.metaforge.settings.booting = null;
        }
    })();

    return window.metaforge.settings.booting;
};

// --- 2. PANEL NAVIGATION ---

/**
 * Master Panel Switcher
 */
window.showSettingsPanel = async function(panelId, element) {
    // Wait for boot lock to clear
    await window.metaforge.settings.boot();

    document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
    if(element) element.classList.add('active');

    document.querySelectorAll('.settings-panel').forEach(el => el.style.display = 'none');
    const target = document.getElementById('panel-' + panelId);
    
    if(target) {
        target.style.display = 'block';
        
        // Directive II.3: Focus Handoff Guard (10ms)
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

    // Logic delegation
    if(panelId === 'api-keys' && window.metaforge.settings.api) window.metaforge.settings.api.load();
    if(panelId === 'help' && window.metaforge.settings.help) window.metaforge.settings.help.load();
    
    if(panelId === 'personalization') {
        const activeSub = document.querySelector('.sub-nav-btn.active');
        if (activeSub) {
            const subId = activeSub.id.replace('sub-nav-', '');
            window.showSubPanel(subId, activeSub);
        }
    }
};

/**
 * Sub-Panel Switcher
 */
window.showSubPanel = async function(subId, element) {
    await window.metaforge.settings.boot();

    document.querySelectorAll('.sub-nav-btn').forEach(btn => btn.classList.remove('active'));
    if(element) element.classList.add('active');

    document.querySelectorAll('.personalization-sub-panel').forEach(p => p.style.display = 'none');
    const target = document.getElementById('sub-panel-' + subId);
    
    if(target) {
        target.style.display = 'block';
        
        // Focus Handoff
        setTimeout(() => {
            const subHeader = target.querySelector('h2');
            if (subHeader) {
                if (!subHeader.hasAttribute('tabindex')) subHeader.setAttribute('tabindex', '-1');
                subHeader.focus();
            }
        }, 10);
    }

    // Mini-Engine Execution
    if (subId === 'theme' && window.metaforge.settings.themes) window.metaforge.settings.themes.load();
    if (subId === 'toolbar' && window.metaforge.settings.toolbar) window.metaforge.settings.toolbar.load();
    if (subId === 'taxonomy' && window.metaforge.settings.taxonomy) window.metaforge.settings.taxonomy.load();
};

// --- 3. AUTO-START ---
(async () => {
    await window.metaforge.settings.boot();
    window.showSettingsPanel('personalization');
})();

// --- SETTINGS UI LOGIC END ---
// --- END OF FILE settings.js ---