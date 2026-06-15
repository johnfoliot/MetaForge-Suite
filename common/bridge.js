// --- START OF FILE [D:\MetaForge Suite\common\bridge.js] ---
/**
 * MetaForge Suite: common/bridge.js
 * Centralized communication layer for UI-to-Backend event orchestration.
 * Namespace: window.metaforge.bridge
 * Build 8.2.3: Forensic Path Resolution & Backend State Sync
 */

(function() {
    'use strict';

    window.metaforge = window.metaforge || {};
    
    const Bridge = {
        controller: new AbortController(),
        // Establish base host context
        host: 'http://127.0.0.1:5000',
        
        /**
         * Initializes lifecycle management for modules
         */
        init: function() {
            this.controller = new AbortController();
            console.log('MetaForge Bridge: Lifecycle initialized.');
        },

        /**
         * Registers event listeners with automatic cleanup support
         * @param {HTMLElement} element 
         * @param {string} event 
         * @param {Function} handler 
         */
        registerEvent: function(element, event, handler) {
            element.addEventListener(event, handler, { signal: this.controller.signal });
        },

        /**
         * Teardown logic to prevent event listener leakage
         */
        teardown: function() {
            this.controller.abort();
            console.log('MetaForge Bridge: Lifecycle aborted. Listeners cleared.');
        },

        /**
         * Standardized call to backend IO services with absolute path resolution
         * @param {string} endpoint 
         * @param {Object} payload 
         */
        invoke: async function(endpoint, payload) {
            try {
                // Ensure endpoint is treated as an absolute path relative to host
                const url = endpoint.startsWith('/') ? `${this.host}${endpoint}` : `${this.host}/${endpoint}`;
                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);
                return await response.json();
            } catch (error) {
                console.error(`MetaForge Bridge Error [${endpoint}]:`, error);
                throw error;
            }
        }
    };

    window.metaforge.bridge = Bridge;
})();
// --- END OF FILE [D:\MetaForge Suite\common\bridge.js] ---