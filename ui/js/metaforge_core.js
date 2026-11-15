// --- START OF FILE [D:\MetaForge Suite\ui\js\metaforge_core.js] ---
/**
 * MetaForge Master Logic (V.Core)
 * Orchestration Engine. Build 4.9.3: Modern Event Delegation & Sanitization.
 * Accessibility: WCAG 2.2 AA | COGA 4.3.1
 */

// --- GLOBAL UTILITIES ---

window.metaforge = window.metaforge || {};

window.checkMetaForgeBridge = function() {
    if (!window.pywebview || !window.pywebview.api) return false;
    return true;
};

// Real bug fixed here (John, 2026-07-13): plain <a target="_blank">
// links don't reliably open a real browser tab from inside a pywebview
// window -- there's no OS-level "new tab" concept for pywebview to hand
// off to. Routes through the main window's own js_api bridge instead
// (see ui/app.py's MetaForgeAPI.open_external_url, which calls Python's
// webbrowser.open()). Falls back to a plain window.open() only if the
// bridge genuinely isn't available yet, so a link never becomes
// completely inert while the page is still loading.
window.metaforge.openExternalLink = function(url) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.open_external_url) {
        window.pywebview.api.open_external_url(url);
    } else {
        window.open(url, '_blank');
    }
};

window.applyThemeFile = function(themeFileName) {
    const themeLink = document.getElementById('mf-theme-stylesheet');
    if (!themeLink) return;
    themeLink.href = `/ui/css/${themeFileName}?v=${new Date().getTime()}`;
    const themeName = themeFileName.replace('_theme.css', '');
    document.documentElement.setAttribute('data-theme', themeName);
};

window.initializeMetaForgeBranding = async function() {
    try {
        const response = await fetch('/run_tool_logic/settings/get_prefs');
        if (response.ok) {
            const prefs = await response.json();
            document.documentElement.setAttribute('data-theme', prefs.theme_file ? prefs.theme_file.replace('_theme.css', '') : 'dark');
            if (prefs.theme_file) window.applyThemeFile(prefs.theme_file);
            window.mfApplyToolbarLabels(prefs.toolbar_labels === true);
            const mainLogo = document.getElementById('mf-main-logo');
            if (mainLogo && prefs.theme_file) {
                mainLogo.src = (prefs.theme_file.includes('light')) ? '/ui/images/logo_blue.svg' : '/ui/images/logo.svg';
            }
        }
    } catch (e) { console.warn("Branding Boot Error"); }
};

// Suppresses the native right-click context menu on the main app shell only
// (John, 2026-07-13). AreDefaultContextMenusEnabled had to go back on
// app-wide to restore Ctrl+F (see ui/app.py's webview.start(debug=True))
// -- that's a pywebview/WebView2 setting with no per-window granularity,
// so this page-level JS listener is the only way to keep the main
// window's own look-and-feel while still allowing the right-click menu
// on other windows (the verify window's docked overlay in particular
// wants it available for standard page interaction on whatever external
// source site is loaded there). This file only ever loads in the main
// window's shell page, never in a companion window, so scope is
// automatic -- nothing else needs to opt in or out.
document.addEventListener('contextmenu', function(e) { e.preventDefault(); });

// --- ENGINE: MODE SWITCHER ---

window.mfSwitchMode = function(mode) {
    // v2: the current tool is marked with aria-current="page" (announced as
    // "current page"), styled from that attribute so the visual and the
    // accessible state can't disagree. The 1.x aria-pressed is removed:
    // these are navigation buttons, not on/off toggles.
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.remove('active');
        el.removeAttribute('aria-current');
        el.removeAttribute('aria-pressed');
    });
    const activeEl = document.getElementById('mode-' + mode);
    if (activeEl) {
        activeEl.classList.add('active');
        activeEl.setAttribute('aria-current', 'page');
    }
    window.loadTool(mode);
};

// v2 toolbar: one delegated listener for every tool button (no inline handlers).
document.addEventListener('click', function(e) {
    const btn = e.target.closest('.mf-toolbar [data-mode]');
    if (btn) window.mfSwitchMode(btn.dataset.mode);
});

// v2 toolbar names as tooltips (labels off): WCAG 1.4.13 requires they can be
// dismissed without moving the pointer or focus. Esc hides them until the
// pointer or focus moves to another toolbar button.
(function() {
    let dismissedOn = null;
    const toolbar = () => document.querySelector('.mf-toolbar');
    document.addEventListener('keydown', function(e) {
        const bar = toolbar();
        if (e.key !== 'Escape' || !bar) return;
        const over = bar.querySelector('.nav-item:hover') || (bar.contains(document.activeElement) ? document.activeElement : null);
        if (over) { bar.classList.add('mf-tips-dismissed'); dismissedOn = over; }
    });
    const reset = function(e) {
        const bar = toolbar();
        const item = e.target.closest && e.target.closest('.nav-item');
        if (bar && item && item !== dismissedOn) { bar.classList.remove('mf-tips-dismissed'); dismissedOn = null; }
    };
    document.addEventListener('pointerover', reset);
    document.addEventListener('focusin', reset);
})();

// v2 rail tooltips (collapsed rail): the name label is position:fixed, so it
// can't be clipped by the scrolling tool list. Place it just to the right of
// its button, vertically centred, whenever the button is hovered or focused,
// and again if the list scrolls or the window resizes while it's showing.
(function() {
    let current = null;
    function place(btn) {
        const label = btn && btn.querySelector('.mf-nav-label');
        if (!label) return;
        const r = btn.getBoundingClientRect();
        label.style.setProperty('--tip-x', `${Math.round(r.right + 10)}px`);
        label.style.setProperty('--tip-y', `${Math.round(r.top + r.height / 2)}px`);
        current = btn;
    }
    const pick = (e) => {
        const btn = e.target.closest && e.target.closest('.mf-toolbar .nav-item');
        if (btn) place(btn);
    };
    document.addEventListener('pointerover', pick);
    document.addEventListener('focusin', pick);
    const refresh = () => { if (current && current.isConnected) place(current); };
    document.addEventListener('scroll', refresh, true);   // capture: catches the rail's own scroll
    window.addEventListener('resize', refresh);
})();

// v2: tool names in the rail. ONE saved preference (toolbar_labels in
// preferences.json, default off) switched three ways: the >> / << button at
// the top of the rail, Ctrl+B anywhere, and Settings > "Show names under
// toolbar icons". mfApplyToolbarLabels keeps all three in sync.
window.mfApplyToolbarLabels = function(on) {
    if (on) document.documentElement.setAttribute('data-toolbar-labels', 'on');
    else document.documentElement.removeAttribute('data-toolbar-labels');
    const toggle = document.getElementById('mf-rail-toggle');
    if (toggle) {
        toggle.setAttribute('aria-expanded', String(!!on));
        toggle.title = (on ? 'Hide tool names' : 'Show tool names') + ' (Ctrl+B)';
    }
    const box = document.getElementById('pref-toolbar-labels');   // Settings, when open
    if (box) box.checked = !!on;
};

/** Apply AND save. Resolves to true if saved, false if only applied. */
window.mfSetToolbarLabels = async function(on) {
    window.mfApplyToolbarLabels(on);
    try {
        const res = await fetch('/run_tool_logic/settings/save_prefs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ toolbar_labels: !!on })
        });
        const result = await res.json();
        return result.status === 'success';
    } catch (e) {
        console.warn('MetaForge: toolbar_labels not saved', e);
        return false;
    }
};

window.mfToggleToolbarLabels = function() {
    return window.mfSetToolbarLabels(!document.documentElement.hasAttribute('data-toolbar-labels'));
};

document.addEventListener('click', function(e) {
    if (e.target.closest('#mf-rail-toggle')) window.mfToggleToolbarLabels();
});

// Ctrl+B toggles tool names from anywhere (not while editing rich text, and
// not with Alt/Shift/Win, so other shortcuts are untouched).
document.addEventListener('keydown', function(e) {
    if (!e.ctrlKey || e.altKey || e.shiftKey || e.metaKey || e.key.toLowerCase() !== 'b') return;
    if (e.target && e.target.isContentEditable) return;
    e.preventDefault();
    window.mfToggleToolbarLabels();
});

/**
 * ENGINE: WORKFLOW ORCHESTRATOR (Build 4.9.3)
 * Allows autonomous tools to trigger a global mode switch with context passing.
 */
window.mfAdvanceWorkflow = function(targetToolId, contextPath = null) {
    console.log(`%c METAFORGE: Advancing workflow to ${targetToolId}... `, 'background: #cc9900; color: #000; font-weight: bold;');
    
    if (contextPath) {
        console.log(`METAFORGE: Path context cached for next tool: ${contextPath}`);
        window.mf_context_path = contextPath;
    }

    // Trigger the mode switch which loads the target tool
    window.mfSwitchMode(targetToolId);
};

// --- ENGINE: SHARED HELP DIALOG (v2, 2026-11-13) ---
/**
 * One Help dialog for every tool (replaces the 8 per-tool help panels).
 * Each tool's standard header has:
 *   <button type="button" class="mf-help-btn" data-mf-help="tool_id"
 *           data-mf-help-name="Tool Name">Help</button>
 * and the single click listener below opens that tool's help.mfi in the
 * native <dialog> in index.html. No per-tool help code is needed: the
 * browser handles Esc, click-outside, focus containment and focus return.
 */
window.MFHelp = {
    open: async function(toolId, toolName) {
        const dialog = document.getElementById('mf-help-dialog');
        const title = document.getElementById('mf-help-title');
        const body = document.getElementById('mf-help-body');
        if (!dialog || !title || !body) return;

        title.textContent = `Help: ${toolName || toolId}`;
        try {
            const response = await fetch(`/tool_asset/${encodeURIComponent(toolId)}/help.mfi?v=${Date.now()}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            // help.mfi is MetaForge's own local documentation file, not user or
            // remote data, so it is inserted as HTML.
            body.innerHTML = await response.text();
        } catch (err) {
            body.textContent = "Help for this tool isn't available yet.";
        }
        body.scrollTop = 0;
        if (!dialog.open) dialog.showModal();
    }
};

document.addEventListener('click', function(e) {
    const trigger = e.target.closest('[data-mf-help]');
    if (trigger) window.MFHelp.open(trigger.dataset.mfHelp, trigger.dataset.mfHelpName);
});

// --- ENGINE: TOOL LOADER ---

/**
 * Modular Tool Loader with Lifecycle Synchronization and Event Cleanup.
 */
window.loadTool = async function(toolId) {
    const stage = document.getElementById('mfi-content');
    if (!stage) return;

    // Track the currently active tool ID to manage cleanup scoping
    const previousToolId = window.metaforge_current_tool;
    
    // Lifecycle Event: Fire teardown hook if the outgoing tool namespace exposed one
    if (previousToolId && window.metaforge && window.metaforge[previousToolId]) {
        const prevNamespace = window.metaforge[previousToolId];
        if (typeof prevNamespace.destroy === 'function') {
            console.log(`METAFORGE: Tearing down Lifecycle for ${previousToolId}`);
            try {
                prevNamespace.destroy();
            } catch (err) {
                console.error(`MetaForge Teardown Error inside ${previousToolId}:`, err);
            }
        }
    }
    
    // Bridge Lifecycle: Abort previous event listeners
    if (window.metaforge.bridge) {
        window.metaforge.bridge.teardown();
        window.metaforge.bridge.init();
    }

    try {
        const response = await fetch(`/get_tool/${toolId}?v=${new Date().getTime()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        stage.innerHTML = await response.text();
        
        // Update global tracking context to the new module ID
        window.metaforge_current_tool = toolId;

        const scriptId = `script-${toolId}`;
        let script = document.getElementById(scriptId);

        const initTool = () => {
            setTimeout(() => {
                // Focus Management
                const heading = stage.querySelector('h1.main') || stage.querySelector('h1');
                if (heading) { heading.setAttribute('tabindex', '-1'); heading.focus(); }
                
                // --- INTEGRATION: Common Component Initialization ---
                if (window.metaforge.ui && typeof window.metaforge.ui.initCommonComponents === 'function') {
                    window.metaforge.ui.initCommonComponents();
                }

                // Build 4.9.3: Physical Lifecycle Handshake
                const toolNamespace = window.metaforge ? window.metaforge[toolId] : null;
                if (toolNamespace && typeof toolNamespace.init === 'function') {
                    console.log(`METAFORGE: Synchronizing Lifecycle for ${toolId}`);
                    toolNamespace.init();
                }

                // Specialized Settings Handler
                if (toolId === 'settings' && typeof window.showSettingsPanel === 'function') {
                    window.showSettingsPanel('personalization');
                }
            }, 30); // 30ms paint guard
        };

        if (!script) {
            script = document.createElement('script');
            script.id = scriptId;
            script.type = 'text/javascript';
            script.src = `/tool_asset/${toolId}/${toolId}.js?v=${new Date().getTime()}`;
            script.onload = initTool;
            document.head.appendChild(script);
        } else {
            initTool();
        }
        
    } catch (error) {
        console.error("MetaForge Load Error:", error);
        stage.innerHTML = `<div style="color:var(--status-error); padding: 20px;">⚠️ Failed to load tool: ${toolId}</div>`;
    }
};

// --- SHARED CUSTOM SCROLLBAR (John's report, 2026-08-11) ---
// See layout.css section 10 for the CSS half and the full history of
// why native ::-webkit-scrollbar-button was abandoned. A tool marks up
// its scrollable target plus a sibling .mf-custom-scrollbar block (real
// button/track/thumb divs, aria-controls pointing at the target's id) --
// no per-tool JS needed at all. initCommonComponents() below calls
// autoAttachAll() on every tool load (see loadTool()'s existing call to
// it, further up this file), which finds and wires every
// .mf-custom-scrollbar on the page automatically.
window.MFScrollbar = {
    attach: function(bar) {
        if (typeof bar === 'string') bar = document.getElementById(bar);
        if (!bar || bar.dataset.mfWired) return;

        const targetId = bar.getAttribute('aria-controls');
        const target = targetId ? document.getElementById(targetId) : null;
        const btns = bar.querySelectorAll('.mf-scroll-btn');
        const track = bar.querySelector('.mf-scroll-track');
        const thumb = bar.querySelector('.mf-scroll-thumb');
        const upBtn = btns[0], downBtn = btns[1];
        if (!target || !upBtn || !downBtn || !track || !thumb) return;
        bar.dataset.mfWired = 'true';

        const sync = () => {
            const scrollable = target.scrollHeight - target.clientHeight;
            if (scrollable <= 1) {
                thumb.style.display = 'none';
                upBtn.disabled = true; downBtn.disabled = true;
                upBtn.style.opacity = '0.4'; downBtn.style.opacity = '0.4';
                return;
            }
            thumb.style.display = 'block';
            upBtn.disabled = false; downBtn.disabled = false;
            upBtn.style.opacity = '1'; downBtn.style.opacity = '1';

            const trackHeight = track.clientHeight;
            const visibleRatio = target.clientHeight / target.scrollHeight;
            const thumbHeight = Math.max(trackHeight * visibleRatio, 20);
            const maxThumbTop = trackHeight - thumbHeight;
            const scrollRatio = target.scrollTop / scrollable;
            const thumbTop = maxThumbTop * scrollRatio;

            thumb.style.height = thumbHeight + 'px';
            thumb.style.top = thumbTop + 'px';
            bar.setAttribute('aria-valuenow', Math.round(scrollRatio * 100));
        };

        upBtn.addEventListener('click', () => target.scrollBy({ top: -40, behavior: 'smooth' }));
        downBtn.addEventListener('click', () => target.scrollBy({ top: 40, behavior: 'smooth' }));

        track.addEventListener('click', (e) => {
            if (e.target !== track) return;
            const clickY = e.clientY - track.getBoundingClientRect().top;
            const direction = clickY < thumb.offsetTop ? -1 : 1;
            target.scrollBy({ top: direction * target.clientHeight, behavior: 'smooth' });
        });

        thumb.addEventListener('mousedown', (e) => {
            e.preventDefault();
            const startY = e.clientY;
            const startScrollTop = target.scrollTop;
            const scrollable = target.scrollHeight - target.clientHeight;
            const trackSpace = track.clientHeight - thumb.clientHeight;
            thumb.classList.add('dragging');

            const onMove = (moveEvt) => {
                if (trackSpace <= 0 || scrollable <= 0) return;
                const deltaY = moveEvt.clientY - startY;
                target.scrollTop = startScrollTop + (deltaY / trackSpace) * scrollable;
            };
            const onUp = () => {
                thumb.classList.remove('dragging');
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });

        target.addEventListener('scroll', sync);
        window.addEventListener('resize', sync);

        // Auto-resync on any content change -- rows added/removed,
        // streamed console output, etc. -- rather than requiring each
        // tool to remember to call a sync function at every mutation
        // point (the exact pattern that had to be manually hunted down
        // per-tool in the three original hand-built implementations).
        new MutationObserver(sync).observe(target, { childList: true, subtree: true, characterData: true });

        sync();
    },

    autoAttachAll: function() {
        document.querySelectorAll('.mf-custom-scrollbar').forEach(el => this.attach(el));
    }
};

window.metaforge.ui = window.metaforge.ui || {};
window.metaforge.ui.initCommonComponents = function() {
    window.MFScrollbar.autoAttachAll();
};

// --- ENGINE: SHARED ANNOUNCER (v2, Phase 0.3) ---
// One polite and one assertive live region for the whole app (both live in
// index.html, outside <main>). Tools never put aria-live on their own
// output: a run's Activity log can add hundreds of lines, and reading every
// one aloud would bury what matters. MFEvents announces only steps, errors,
// warnings and the finish; the full log stays readable on demand.
window.MFAnnounce = function(message, { urgent = false } = {}) {
    const region = document.getElementById(urgent ? 'mf-announcer-urgent' : 'mf-announcer');
    if (!region || !message) return;
    // Clear, then set on the next frame, so repeating the same message
    // (e.g. two identical errors) is still spoken.
    region.textContent = '';
    requestAnimationFrame(() => { region.textContent = message; });
};

// --- ENGINE: EVENT STREAM RENDERER (v2, Phase 0.3) ---
// Reads an NDJSON event stream from common/mf_events.py run_stream() and
// draws it into a tool's Activity log. One line = one complete JSON event,
// so nothing can be split mid-tag across network reads (the 1.x bug).
//   kinds  : step, info, detail, success, warning, error, done -> drawn here
//            (text only, via textContent: nothing from a file name or an
//            error message can ever be parsed as HTML)
//            html  -> legacy 1.x engine output, inserted as before until
//                     that engine is converted
//            signal -> not drawn; handed to opts.onSignal(name, data)
// The same events are written to the album's MetaForge.log server-side.
window.MFEvents = {
    // Hidden prefixes so the kind isn't conveyed by colour/glyph alone.
    LABEL: { error: 'Error: ', warning: 'Warning: ' },
    MARK:  { success: '✓', warning: '!', error: '✕', done: '✓', track: '✓' },

    /** Draws one event into `log`. Returns the new row (or null). */
    render: function(log, ev) {
        if (!log || !ev) return null;
        if (ev.kind === 'html') {
            log.insertAdjacentHTML('beforeend', ev.html);
            return log.lastElementChild;
        }
        const row = document.createElement('div');
        // `ok: true` on any event adds a ✓ in the mark column (e.g. the
        // final "Scrubbed 11 of 11 files" detail line) without changing
        // its kind or indent.
        row.className = `mf-ev mf-ev-${ev.kind}${ev.ok ? ' mf-ev-ok' : ''}`;

        const time = document.createElement('span');
        time.className = 'mf-ev-time';
        time.textContent = ev.time || '';
        row.append(time);

        const mark = document.createElement('span');
        mark.className = 'mf-ev-mark';
        mark.setAttribute('aria-hidden', 'true');
        mark.textContent = this.MARK[ev.kind] || (ev.ok ? '✓' : '');
        row.append(mark);

        const body = document.createElement('span');
        body.className = 'mf-ev-text';

        // "track": one entry per file. File name is the headline; what
        // was done to it sits on a quieter line underneath.
        if (ev.kind === 'track') {
            const file = document.createElement('span');
            file.className = 'mf-ev-track-file';
            file.textContent = ev.file || '';
            body.append(file);
            // Optional structured details: lines of [label, value] pairs
            // (Intelli-Tagger's per-track results). Nothing is truncated;
            // pairs wrap. Without details, the plain text line is shown.
            if (Array.isArray(ev.details) && ev.details.length) {
                ev.details.forEach((line) => {
                    // Outer span clips; inner span is pulled left by one
                    // separator width, so the "·" in front of whichever pair
                    // starts a (wrapped) line is clipped away.
                    const row = document.createElement('span');
                    row.className = 'mf-ev-track-did mf-ev-pairs';
                    const inner = document.createElement('span');
                    inner.className = 'mf-ev-pairs-in';
                    row.append(inner);
                    line.forEach(([label, value]) => {
                        const pair = document.createElement('span');
                        pair.className = 'mf-ev-pair';
                        const k = document.createElement('span');
                        k.className = 'mf-ev-pair-k';
                        k.textContent = label;
                        const v = document.createElement('span');
                        v.className = 'mf-ev-pair-v';
                        v.textContent = value;
                        pair.append(k, ' ', v);
                        inner.append(pair);
                    });
                    body.append(row);
                });
            } else {
                const did = document.createElement('span');
                did.className = 'mf-ev-track-did';
                did.textContent = ev.text || '';
                body.append(did);
            }
            row.append(body);
            log.append(row);
            return row;
        }

        if (this.LABEL[ev.kind]) {
            const label = document.createElement('span');
            label.className = 'mf-visually-hidden';
            label.textContent = this.LABEL[ev.kind];
            body.append(label);
        }
        body.append(ev.text || '');
        if (ev.file) {
            const file = document.createElement('span');
            file.className = 'mf-ev-file';
            file.textContent = ev.file;
            body.append(' ', file);
        }
        row.append(body);
        log.append(row);
        return row;
    },

    /** Speaks steps, errors, warnings and the finish; everything else stays in the log. */
    announce: function(ev) {
        if (ev.kind === 'step' || ev.kind === 'done') window.MFAnnounce(ev.text);
        else if (ev.kind === 'error' || ev.kind === 'warning') {
            // Warnings carry the "source kept" safety alerts: always spoken.
            window.MFAnnounce(`${this.LABEL[ev.kind]}${ev.text}${ev.file ? ` (${ev.file})` : ''}`);
        }
    },

    /**
     * Consume a fetch() Response.
     *   opts.log      : the Activity log element
     *   opts.onSignal : (name, data) => {} for progress, art_ready, ...
     * Resolves when the stream ends. Throws on an HTTP error.
     */
    read: async function(response, { log, onSignal } = {}) {
        if (!response.ok) throw new Error(`the server answered ${response.status} ${response.statusText}`);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let pending = '';

        const handle = (line) => {
            if (!line.trim()) return;
            let ev;
            try { ev = JSON.parse(line); }
            catch { ev = { kind: 'info', text: line }; }   // never drop output
            if (ev.kind === 'signal') { onSignal?.(ev.name, ev.data || {}); return; }
            // Keep following the newest line only if the reader was already
            // at the bottom; don't yank them away from something they
            // scrolled up to read.
            const atBottom = log && (log.scrollHeight - log.scrollTop - log.clientHeight < 24);
            this.render(log, ev);
            this.announce(ev);
            if (atBottom) log.scrollTop = log.scrollHeight;
        };

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            pending += decoder.decode(value, { stream: true });
            const lines = pending.split('\n');
            pending = lines.pop();   // the last piece may be incomplete
            lines.forEach(handle);
        }
        handle(pending + decoder.decode());
    }
};

// --- CENTRALIZED EVENT DELEGATION & SANITIZATION ---

function setupGlobalNavigationListeners() {
    document.addEventListener('click', (event) => {
        const targetNav = event.target.closest('.nav-item, .settings-btn');
        if (!targetNav) return;

        const elementId = targetNav.id || '';
        if (elementId.startsWith('mode-')) {
            event.preventDefault();
            const targetMode = elementId.substring(5);
            if (targetMode) {
                window.mfSwitchMode(targetMode);
            }
        }
    });
}

// --- AUTO-START TRIGGER ---

document.addEventListener('DOMContentLoaded', () => {
    window.initializeMetaForgeBranding();
    setupGlobalNavigationListeners();
    setTimeout(() => { window.mfSwitchMode('dashboard'); }, 150);
});
// --- END OF FILE [D:\MetaForge Suite\ui\js\metaforge_core.js] ---