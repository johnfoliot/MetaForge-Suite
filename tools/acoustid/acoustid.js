// --- ACOUSTID TOOL LOGIC ---

window.runAcoustIDTask = async function(taskType) {
    if (!window.checkMetaForgeBridge()) return;

    const consoleBox = document.getElementById('acoustid-console');
    if (!consoleBox) return;

    consoleBox.innerHTML = `<div style="color:#cc9900;">🛰️ Initializing AcoustID ${taskType}...</div>`;

    try {
        const response = await fetch(`/run_tool_logic/acoustid?task=${taskType}`);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            const text = decoder.decode(value);
            consoleBox.innerHTML += `<div>${text}</div>`;
            consoleBox.scrollTop = consoleBox.scrollHeight;
        }
    } catch (err) {
        console.error("AcoustID Error:", err);
    }
};
// --- ACOUSTID TOOL LOGIC END ---