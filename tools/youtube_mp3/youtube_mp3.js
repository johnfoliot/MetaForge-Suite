// --- [ YOUTUBE TOOL LOGIC START ] ---
/**
 * YouTube Downloader Engine.
 * Note: This tool does NOT use the Bridge/Picker. It uses a server-side path.
 */
window.runYouTubeDownload = async function() {
    const urlInput = document.getElementById('yt-url');
    const consoleBox = document.getElementById('youtube-console');
    const progressContainer = document.getElementById('yt-progress-container');
    const progressBar = document.getElementById('yt-progress');

    if (!urlInput || !urlInput.value) {
        if (consoleBox) consoleBox.innerHTML = '<div style="color:#ff4444;">⚠️ Please enter a YouTube URL.</div>';
        return;
    }

    const url = urlInput.value;
    if (consoleBox) consoleBox.innerHTML = '';
    if (progressContainer) progressContainer.style.display = 'block';

    try {
        // MUST MATCH MetaForge_Routes.py EXACTLY
        const response = await fetch('/run_tool_logic/youtube', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            const text = decoder.decode(value);
            
            // Execute progress scripts (updateProgress) yielded by Python
            if (text.includes('<script>')) {
                const temp = document.createElement('div');
                temp.innerHTML = text;
                const scripts = temp.querySelectorAll('script');
                scripts.forEach(s => {
                    try { eval(s.innerHTML); } catch(e) { console.error("YT Eval Error", e); }
                });
                
                const cleanText = text.replace(/<script.*?>.*?<\/script>/g, '');
                if (cleanText.trim() && consoleBox) {
                    consoleBox.innerHTML += `<div>${cleanText}</div>`;
                }
            } else {
                if (consoleBox) consoleBox.innerHTML += `<div>${text}</div>`;
            }
            if (consoleBox) consoleBox.scrollTop = consoleBox.scrollHeight;
        }
    } catch (err) {
        console.error("YouTube Download Error:", err);
        if (consoleBox) consoleBox.innerHTML += `<div style="color:#ff4444;">❌ Error: ${err.message}</div>`;
    }
};

window.updateProgress = function(elementId, percent) {
    const bar = document.getElementById(elementId);
    if (bar) bar.style.width = percent + '%';
};
// --- [ YOUTUBE TOOL LOGIC END ] ---