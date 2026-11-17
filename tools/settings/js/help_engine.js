// --- START OF FILE help_engine.js ---
/**
 * Settings > Help files. v2 (2026-11-15): DOM-built <details> per tool.
 * The help bodies are the tools' own local help.mfi files (trusted, shipped
 * with MetaForge), so they're inserted as HTML; tool names are text.
 */
(function () {
    const S = window.metaforge.settings;
    S.help = {
        load: async function () {
            const box = document.getElementById('help-aggregator');
            if (!box) return;
            try {
                const docs = await (await fetch('/run_tool_logic/settings/get_help_docs')).json();
                if (!Array.isArray(docs) || !docs.length) {
                    box.replaceChildren(Object.assign(document.createElement('p'), { className: 'set-hint', textContent: 'No help files were found.' }));
                    return;
                }
                box.replaceChildren(...docs.map(d => {
                    const det = document.createElement('details');
                    const sum = document.createElement('summary');
                    sum.textContent = d.name;
                    const body = document.createElement('div');
                    // mf-help-doc: the same styling as the Help dialog (ui/css/help.css)
                    body.className = 'set-help-body mf-help-doc';
                    body.innerHTML = d.html;
                    if (window.MFHelp) window.MFHelp.prepare(body);
                    det.append(sum, body);
                    return det;
                }));
            } catch (e) {
                box.replaceChildren(Object.assign(document.createElement('p'), { className: 'set-status is-error', textContent: `The help files couldn't be loaded: ${e.message}` }));
            }
        }
    };
})();
// --- END OF FILE help_engine.js ---
