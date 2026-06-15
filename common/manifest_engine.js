// --- START OF FILE [D:\MetaForge Suite\common\manifest_engine.js] ---
/**
 * MetaForge Suite: common/manifest_engine.js
 * Standardized Domain Logic.
 * COGA Requirement: Semantic naming reduces cognitive load across tools.
 */

(function() {
    'use strict';
    window.metaforge = window.metaforge || {};

    window.metaforge.manifest = {
        // Uniform mapping to semantic data classes
        classMap: {
            'album': 'mf-data-album',
            'artist': 'mf-data-artist',
            'path': 'mf-data-path'
        },

        sync: async function(folderPath) {
            const res = await window.metaforge.bridge.invoke('sync_manifest', { path: folderPath });
            return res.manifest || { status: 'new' };
        },

        // Uniform auto-population (COGA-compliant)
        autoPopulate: function(manifestData) {
            Object.keys(this.classMap).forEach(key => {
                if (manifestData[key]) {
                    document.querySelectorAll(`.${this.classMap[key]}`).forEach(input => {
                        input.value = manifestData[key];
                    });
                }
            });
        },

        injectHandoff: function(containerId, nextToolId, label = "Proceed to Next Step") {
            const container = document.getElementById(containerId);
            if (!container) return;
            container.innerHTML = `<button type="button" class="mf-button-gold-fixed" onclick="window.mfAdvanceWorkflow('${nextToolId}')">${label}</button>`;
        }
    };
})();
// --- END OF FILE [D:\MetaForge Suite\common\manifest_engine.js] ---