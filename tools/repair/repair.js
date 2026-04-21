// --- AUDIO REPAIR TOOL LOGIC ---

window.pickRepairFolder = async function() {
    if (!window.checkMetaForgeBridge()) return; 

    try {
        const path = await window.pywebview.api.select_folder();
        if (path) document.getElementById('targetPath').value = path;
    } catch (err) {
        console.error("Audio Repair: Picker failed", err);
    }
};

window.runRepair = async function() {
    const pathInput = document.getElementById('targetPath');
    const consoleDiv = document.getElementById('repairConsole');
    if (!pathInput || !consoleDiv) return;
    const path = pathInput.value.trim();

    if (!path) {
        consoleDiv.innerHTML = '<div style="color:#ff0000;">⚠️ Valid path required.</div>';
        return;
    }

    try {
        const response = await fetch('/route_audio_repair', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path })
        });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            consoleDiv.innerHTML += decoder.decode(value);
            consoleDiv.scrollTop = consoleDiv.scrollHeight;
        }
    } catch (err) {
        console.error("Repair Error:", err);
    }
};

// --- AUDIO REPAIR TOOL LOGIC END ---