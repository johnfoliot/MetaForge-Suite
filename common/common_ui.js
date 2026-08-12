// --- START OF FILE [D:\MetaForge Suite\common\common_ui.js] ---
/**
 * MetaForge Suite: common/common_ui.js
 * Standardized UI Service Layer.
 */
(function() {
    'use strict';
    window.metaforge = window.metaforge || {};

    const UI = {
        /**
         * Initializes a help modal with scoped cleanup.
         */
        initHelpModal: function(panelId) {
            const panel = document.getElementById(panelId);
            const closeBtn = panel ? panel.querySelector('.mf-panel-close') : null;
            
            if (panel && closeBtn) {
                // Use a standard reference to avoid anonymous function binding issues
                closeBtn.onclick = () => { panel.style.display = 'none'; };
                console.log(`MetaForge UI: Help Modal [${panelId}] initialized.`);
            }
        },

        /**
         * Standardized File Picker invocation via Bridge
         */
        openFilePicker: async function(callback) {
            if (!window.metaforge.bridge) {
                console.error("MetaForge Error: Bridge service unreachable.");
                return;
            }
            try {
                const res = await window.metaforge.bridge.invoke('select_folder', {});
                if (res?.path && typeof callback === 'function') {
                    callback(res.path, res.manifest || {});
                }
            } catch (err) {
                console.error("MetaForge UI: File Picker invocation failed.", err);
            }
        }
    };
    // Merge, not overwrite -- metaforge_core.js (loaded before this file,
    // see ui/html/index.html) already attaches
    // window.metaforge.ui.initCommonComponents there. A plain `= UI`
    // here silently wiped that out on every page load (no error, since
    // loadTool()'s own call site just checks `typeof ... === 'function'`
    // and no-ops if missing) -- MFScrollbar.autoAttachAll() never ran,
    // so every custom scrollbar rendered with correct CSS but zero
    // event wiring: buttons did nothing, and the thumb never got a real
    // height/position from sync() (John's report, 2026-08-11, both the
    // "buttons don't do anything" and the collapsed-looking thumb in his
    // screenshots trace back to this one line).
    window.metaforge.ui = Object.assign(window.metaforge.ui || {}, UI);
})();
// --- END OF FILE [D:\MetaForge Suite\common\common_ui.js] ---