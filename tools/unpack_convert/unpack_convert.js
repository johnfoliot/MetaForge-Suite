// --- UNPACKER TOOL LOGIC ---
/**
 * Unified Unpacker: Strictly adheres to the Bridge Guard and Python API.
 * Replaces old fetch-based folder picking with the direct bridge method.
 */
window.runUnpacker = async function() {
    // 1. Mandatory Bridge Guard (Cookbook Rule)
    if (!window.checkMetaForgeBridge()) return;

    try {
        // 2. Launch Native OS Picker via the Bridge API
        // This 'await' is critical; it forces the engine to wait for the user's input.
        const path = await window.pywebview.api.select_folder();
        
        // 3. Exit gracefully if user cancels the picker or closes the window
        if (!path) {
            console.log("Unpacker: Folder selection cancelled.");
            return;
        }

        const consoleBox = document.getElementById('unpacker-console');
        if (consoleBox) {
            consoleBox.innerHTML = `<div style="color:#cc9900;">🚀 Starting Unpack sequence for: ${path}</div>`;
        }

        // 4. Execution via Flask Route
        const res = await fetch(`/run_tool_logic/unpack?path=${encodeURIComponent(path)}`);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            const text = decoder.decode(value);
            if (consoleBox) {
                consoleBox.innerHTML += `<div>${text}</div>`;
                // Mandatory Auto-scroll (Cookbook Phase 3)
                consoleBox.scrollTop = consoleBox.scrollHeight;
            }
        }
    } catch (err) {
        console.error("MetaForge Bridge Error:", err);
        const consoleBox = document.getElementById('unpacker-console');
        if (consoleBox) {
            consoleBox.innerHTML += `<div style="color:#ff4444; font-weight:bold;">❌ BRIDGE EXECUTION ERROR: ${err.message}</div>`;
        }
    }
};
// --- UNPACKER TOOL LOGIC END ---