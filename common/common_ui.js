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
    window.metaforge.ui = UI;
})();
// --- END OF FILE [D:\MetaForge Suite\common\common_ui.js] ---