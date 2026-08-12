// --- START OF FILE [D:\MetaForge Suite\ui\js\metaforge_core.js] ---
/**
 * MetaForge Master Logic (V.Core)
 * Orchestration Engine. Build 4.9.3: Modern Event Delegation & Sanitization.
 * Accessibility: WCAG 2.2 AA | COGA 4.3.1
 */

// --- GLOBAL UTILITIES ---

window.metaforge = window.metaforge || {};

window.checkMetaForgeBridge = function() {
    if (!window.pywebview || !window.pywebview.api) return false;
    return true;
};

// Real bug fixed here (John, 2026-07-13): plain <a target="_blank">
// links don't reliably open a real browser tab from inside a pywebview
// window -- there's no OS-level "new tab" concept for pywebview to hand
// off to. Routes through the main window's own js_api bridge instead
// (see ui/app.py's MetaForgeAPI.open_external_url, which calls Python's
// webbrowser.open()). Falls back to a plain window.open() only if the
// bridge genuinely isn't available yet, so a link never becomes
// completely inert while the page is still loading.
window.metaforge.openExternalLink = function(url) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.open_external_url) {
        window.pywebview.api.open_external_url(url);
    } else {
        window.open(url, '_blank');
    }
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

// Suppresses the native right-click context menu on the main app shell only
// (John, 2026-07-13). AreDefaultContextMenusEnabled had to go back on
// app-wide to restore Ctrl+F (see ui/app.py's webview.start(debug=True))
// -- that's a pywebview/WebView2 setting with no per-window granularity,
// so this page-level JS listener is the only way to keep the main
// window's own look-and-feel while still allowing the right-click menu
// on other windows (the verify window's docked overlay in particular
// wants it available for standard page interaction on whatever external
// source site is loaded there). This file only ever loads in the main
// window's shell page, never in a companion window, so scope is
// automatic -- nothing else needs to opt in or out.
document.addEventListener('contextmenu', function(e) { e.preventDefault(); });

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

// --- SHARED CUSTOM SCROLLBAR (John's report, 2026-08-11) ---
// See layout.css section 10 for the CSS half and the full history of
// why native ::-webkit-scrollbar-button was abandoned. A tool marks up
// its scrollable target plus a sibling .mf-custom-scrollbar block (real
// button/track/thumb divs, aria-controls pointing at the target's id) --
// no per-tool JS needed at all. initCommonComponents() below calls
// autoAttachAll() on every tool load (see loadTool()'s existing call to
// it, further up this file), which finds and wires every
// .mf-custom-scrollbar on the page automatically.
window.MFScrollbar = {
    attach: function(bar) {
        if (typeof bar === 'string') bar = document.getElementById(bar);
        if (!bar || bar.dataset.mfWired) return;

        const targetId = bar.getAttribute('aria-controls');
        const target = targetId ? document.getElementById(targetId) : null;
        const btns = bar.querySelectorAll('.mf-scroll-btn');
        const track = bar.querySelector('.mf-scroll-track');
        const thumb = bar.querySelector('.mf-scroll-thumb');
        const upBtn = btns[0], downBtn = btns[1];
        if (!target || !upBtn || !downBtn || !track || !thumb) return;
        bar.dataset.mfWired = 'true';

        const sync = () => {
            const scrollable = target.scrollHeight - target.clientHeight;
            if (scrollable <= 1) {
                thumb.style.display = 'none';
                upBtn.disabled = true; downBtn.disabled = true;
                upBtn.style.opacity = '0.4'; downBtn.style.opacity = '0.4';
                return;
            }
            thumb.style.display = 'block';
            upBtn.disabled = false; downBtn.disabled = false;
            upBtn.style.opacity = '1'; downBtn.style.opacity = '1';

            const trackHeight = track.clientHeight;
            const visibleRatio = target.clientHeight / target.scrollHeight;
            const thumbHeight = Math.max(trackHeight * visibleRatio, 20);
            const maxThumbTop = trackHeight - thumbHeight;
            const scrollRatio = target.scrollTop / scrollable;
            const thumbTop = maxThumbTop * scrollRatio;

            thumb.style.height = thumbHeight + 'px';
            thumb.style.top = thumbTop + 'px';
            bar.setAttribute('aria-valuenow', Math.round(scrollRatio * 100));
        };

        upBtn.addEventListener('click', () => target.scrollBy({ top: -40, behavior: 'smooth' }));
        downBtn.addEventListener('click', () => target.scrollBy({ top: 40, behavior: 'smooth' }));

        track.addEventListener('click', (e) => {
            if (e.target !== track) return;
            const clickY = e.clientY - track.getBoundingClientRect().top;
            const direction = clickY < thumb.offsetTop ? -1 : 1;
            target.scrollBy({ top: direction * target.clientHeight, behavior: 'smooth' });
        });

        thumb.addEventListener('mousedown', (e) => {
            e.preventDefault();
            const startY = e.clientY;
            const startScrollTop = target.scrollTop;
            const scrollable = target.scrollHeight - target.clientHeight;
            const trackSpace = track.clientHeight - thumb.clientHeight;
            thumb.classList.add('dragging');

            const onMove = (moveEvt) => {
                if (trackSpace <= 0 || scrollable <= 0) return;
                const deltaY = moveEvt.clientY - startY;
                target.scrollTop = startScrollTop + (deltaY / trackSpace) * scrollable;
            };
            const onUp = () => {
                thumb.classList.remove('dragging');
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });

        target.addEventListener('scroll', sync);
        window.addEventListener('resize', sync);

        // Auto-resync on any content change -- rows added/removed,
        // streamed console output, etc. -- rather than requiring each
        // tool to remember to call a sync function at every mutation
        // point (the exact pattern that had to be manually hunted down
        // per-tool in the three original hand-built implementations).
        new MutationObserver(sync).observe(target, { childList: true, subtree: true, characterData: true });

        sync();
    },

    autoAttachAll: function() {
        document.querySelectorAll('.mf-custom-scrollbar').forEach(el => this.attach(el));
    }
};

window.metaforge.ui = window.metaforge.ui || {};
window.metaforge.ui.initCommonComponents = function() {
    window.MFScrollbar.autoAttachAll();
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