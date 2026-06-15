// --- START OF FILE [D:\MetaForge Suite\common\ui_init.js] ---
/**
 * MetaForge Suite: common/ui_init.js
 * Standardized Lifecycle Initialization for UI Components.
 * Ensures DOM elements exist before attempting bridge registration.
 */

(function() {
    'use strict';

    window.metaforge = window.metaforge || {};

    window.metaforge.ui.initCommonComponents = function() {
        const bridge = window.metaforge.bridge;
        if (!bridge) return;

        // Use a defensive check to ensure DOM elements are present in the current view
        const filePicker = document.getElementById('mf-file-picker');
        const helpModal = document.getElementById('mf-help-trigger');

        // File Picker: Standardized listener registration
        if (filePicker) {
            filePicker.addEventListener('click', async () => {
                await window.metaforge.ui.openFilePicker((path, manifest) => {
                    console.log('MetaForge UI: Path Selected:', path);
                    // Pass results to the current tool's specific handler if it exists
                    if (window.metaforge.onFileSelected) {
                        window.metaforge.onFileSelected(path, manifest);
                    }
                });
            }, { signal: bridge.controller.signal });
        }

        // Help Modal: Standardized listener registration
        if (helpModal) {
            helpModal.addEventListener('click', async () => {
                await bridge.invoke('open_help_modal', { status: 'requested' });
            }, { signal: bridge.controller.signal });
        }
        
        console.log('MetaForge UI: Common components initialized for current lifecycle.');
    };
})();
// --- END OF FILE [D:\MetaForge Suite\common\ui_init.js] ---