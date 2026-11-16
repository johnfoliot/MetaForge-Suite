/* --- START OF FILE unpack_convert.js --- */
/**
 * ======================================================================
 * MetaForge Logic Bridge: Unpack & Convert
 * Build 8.2.2: Removed stray Intelli-Tagger path reference in run().
 * Role: Transitions path context to Step 2 (MusicBrainz IDs).
 * Accessibility: WCAG 2.2 AA | COGA 4.5.10 (Feedback Loops)
 * ======================================================================
 */

console.log("METAFORGE: unpack_convert.js Build 8.2.2 active...");

window.metaforge = window.metaforge || {};
window.metaforge.unpack_convert = {
    lastTrigger: null,
    observer: null,

    // Filing Category lock: lives here on the module object, NOT on the
    // DOM, because navigating to another tool and back fully destroys and
    // recreates this tool's DOM (see setupReentryWatcher/init below) --
    // only module-level state survives that round trip.
    categoryLocked: false,
    lockedCategoryValue: "",
    artistLocked: false,
    lockedArtistValue: "",

    toTitleCase: function(str) {
        if (!str) return "";
        return str.toLowerCase().split(' ').map(word => {
            return word.charAt(0).toUpperCase() + word.slice(1);
        }).join(' ');
    },

    /**
     * Directive XIX: SPA Re-entry Protocol
     * Physically synchronizes UI with .env state using 10ms Paint Guard.
     */
    init: function() {
        const toolHeader = document.getElementById('unpack-header');
        if (!toolHeader) return;

        if (toolHeader.getAttribute('data-synced') === 'true') return;
        toolHeader.setAttribute('data-synced', 'true');
        this.wireForm();

        setTimeout(async () => {
            const enhancedPanel = document.getElementById('enhanced-section');
            const select = document.getElementById('upk-category');
            const consentGate = document.getElementById('upk-consent-gate');
            const fieldset = document.getElementById('upk-fieldset');

            if (!fieldset) return;
            fieldset.disabled = false;
            
            try {
                const res = await fetch(`/run_tool_logic/unpack_convert/get_interview_data?t=${Date.now()}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                
                const data = await res.json();
                
                // v2: the library type is no longer shown here (John,
                // 2026-11-13: it's a set-and-forget setting, changed in
                // Settings); it only decides whether Filing Category shows.
                if (data.policy === "ENHANCED") {
                    if (enhancedPanel) enhancedPanel.hidden = false;
                    this.populateSelect(select, data.categories);
                    if (select) {
                        select.required = true;
                        select.setAttribute('aria-required', 'true');
                    }
                    // Restore the lock from disk (John's report, 2026-08-11:
                    // the previous in-memory-only version reset on a full
                    // app restart) -- only trust a non-empty persisted
                    // value, an empty string means "not locked."
                    if (data.locked_category) {
                        this.categoryLocked = true;
                        this.lockedCategoryValue = data.locked_category;
                    } else {
                        this.categoryLocked = false;
                        this.lockedCategoryValue = "";
                    }
                    this.applyCategoryLockState();
                } else {
                    if (enhancedPanel) enhancedPanel.hidden = true;
                }

                // Restore the Filing Artist lock the same way Filing
                // Category's is restored just above -- persisted to disk
                // so it survives navigating away to another tool and back,
                // which fully rebuilds this DOM.
                if (data.locked_artist) {
                    this.artistLocked = true;
                    this.lockedArtistValue = data.locked_artist;
                } else {
                    this.artistLocked = false;
                    this.lockedArtistValue = "";
                }
                this.applyArtistLockState();

                // v2 (2026-11-16): a folder handed over by YouTube to MP3
                // (mfAdvanceWorkflow) fills in the path, and the album and
                // artist it was saved under; a locked Filing Artist stays.
                if (window.mf_context_path) {
                    const pathIn = document.getElementById('upk-path');
                    if (pathIn) pathIn.value = window.mf_context_path;
                    const meta = window.mf_context_album;
                    if (meta) {
                        const albumIn = document.getElementById('upk-album');
                        const artistIn = document.getElementById('upk-artist');
                        if (albumIn && meta.album) albumIn.value = meta.album;
                        if (artistIn && meta.artist && !this.artistLocked) artistIn.value = meta.artist;
                    }
                    window.mf_context_path = null;
                    window.mf_context_album = null;
                }

                if (data.stored_consent === true) {
                    if (consentGate) consentGate.hidden = true;
                    const consentCheckbox = document.getElementById('upk-consent');
                    if (consentCheckbox) consentCheckbox.checked = true;
                } else {
                    if (consentGate) consentGate.hidden = false;
                    const consentCheckbox = document.getElementById('upk-consent');
                    if (consentCheckbox) consentCheckbox.checked = false;
                }

                this.validate();

            } catch (e) {
                console.error("METAFORGE: Sync Failure:", e);
                if (toolHeader) toolHeader.removeAttribute('data-synced');
            }
        }, 10);
    },

    /**
     * v2: wiring that used to be inline onclick/oninput attributes. The
     * Start button is the form's submit button, so Enter in any field
     * starts the run (CLAUDE.md: Enter submits); it stays disabled, and so
     * Enter does nothing, until every required field is filled in.
     */
    wireForm: function() {
        const form = document.getElementById('unpacker-interview-form');
        if (!form || form.dataset.wired) return;
        form.dataset.wired = 'true';

        form.addEventListener('submit', (e) => {
            e.preventDefault();
            if (!document.getElementById('upk-start-btn')?.disabled) this.run();
        });
        form.addEventListener('input', () => this.validate());
        form.addEventListener('change', () => this.validate());
        document.getElementById('upk-browse-btn')?.addEventListener('click', () => this.pickFolder());
        document.getElementById('upk-artist-lock')?.addEventListener('click', () => this.toggleArtistLock());
        document.getElementById('upk-category-lock')?.addEventListener('click', () => this.toggleCategoryLock());
    },

    setupReentryWatcher: function() {
        if (this.observer) this.observer.disconnect();

        const stage = document.getElementById('mfi-content');
        if (!stage) {
            setTimeout(() => this.setupReentryWatcher(), 100);
            return;
        }

        this.observer = new MutationObserver((mutations) => {
            for (let mutation of mutations) {
                if (mutation.addedNodes.length > 0) {
                    if (document.getElementById('unpack-header')) {
                        this.init();
                        break;
                    }
                }
            }
        });

        this.observer.observe(stage, { childList: true, subtree: false });
    },

    validate: function() {
        const btn = document.getElementById('upk-start-btn');
        const artist = document.getElementById('upk-artist')?.value.trim();
        const album = document.getElementById('upk-album')?.value.trim();
        const path = document.getElementById('upk-path')?.value.trim();
        const consent = document.getElementById('upk-consent')?.checked;
        const catIn = document.getElementById('upk-category');
        
        const isCatReady = catIn?.required ? (catIn.value !== "") : true;

        if (btn) {
            const isReady = (artist && album && path && consent && isCatReady);
            btn.disabled = !isReady;   // look comes from the shared button:disabled style
        }
    },

    /**
     * v2 cover step (Phase 0.3, as in the mock-up). A real radio group in a
     * <form>: one native radio per image, Enter or "Confirm cover" submits.
     * Built with the DOM API, so a file name can never break the markup
     * (1.x pasted names into onclick="..." strings, so an apostrophe in a
     * file name broke the click).
     */
    loadArtGallery: async function() {
        const path = document.getElementById('upk-path').value;
        const consoleBox = document.getElementById('unpacker-console');
        if (!consoleBox) return;

        let images = [];
        try {
            const res = await fetch(`/run_tool_logic/unpack_convert/get_art_gallery?path=${encodeURIComponent(path)}`);
            images = await res.json();
        } catch (err) {
            window.MFEvents.render(consoleBox, { kind: 'error', text: `The cover images couldn't be loaded: ${err.message}` });
            window.MFAnnounce(`Error: the cover images couldn't be loaded`);
            return;
        }
        if (!images.length) return;

        const el = (tag, cls, text) => {
            const n = document.createElement(tag);
            if (cls) n.className = cls;
            if (text !== undefined) n.textContent = text;
            return n;
        };

        const form = el('form', 'mf-cover-picker');
        form.id = 'upk-cover-step';
        form.innerHTML = `
            <fieldset>
                <legend>Pick the front cover. It is saved as <span class="mf-ev-file">folder.jpg</span> at 500 × 500 and added to every track.</legend>
                <div class="mf-cover-grid"></div>
                <div class="mf-cover-actions">
                    <p id="upk-cover-hint">Choose a cover to continue.</p>
                    <button type="submit" class="mf-button-gold-fixed" id="upk-confirm-cover" disabled aria-describedby="upk-cover-hint">Confirm cover</button>
                </div>
            </fieldset>`;
        const grid = form.querySelector('.mf-cover-grid');
        const hint = form.querySelector('#upk-cover-hint');
        const confirmBtn = form.querySelector('#upk-confirm-cover');

        images.forEach((img) => {
            const tile = el('label', 'mf-cover');
            const radio = el('input');
            radio.type = 'radio';
            radio.name = 'upk-cover';
            radio.value = img.filename;
            radio.dataset.size = `${img.width} × ${img.height} px`;
            radio.dataset.thumb = img.data;

            const pic = el('img');
            pic.alt = '';                      // the label text names the image
            pic.src = img.data;

            // Sighted: "600 × 600 px". Screen readers: "600 by 600 pixels".
            const size = el('span', 'mf-cover-size');
            const seen = el('span', '', radio.dataset.size);
            seen.setAttribute('aria-hidden', 'true');
            size.append(seen, el('span', 'mf-visually-hidden', `${img.width} by ${img.height} pixels`));

            const sel = el('span', 'mf-cover-sel', 'Selected');
            sel.setAttribute('aria-hidden', 'true');   // the radio's own checked state says it

            tile.append(radio, pic, el('span', 'mf-cover-name', img.filename), size, sel);
            grid.append(tile);

            radio.addEventListener('change', () => {
                confirmBtn.disabled = false;
                hint.textContent = `Selected: ${img.filename} (${radio.dataset.size}). Confirm to apply it.`;
            });
        });

        form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.confirmCover(form);
        });

        consoleBox.append(form);
        this.setProgressLabel('Step 4: waiting for you to choose a cover');
        // The run has paused for a decision and focus is stranded on the
        // disabled Start button, so take the user to the new step's first
        // choice (focusing a radio doesn't select it).
        grid.querySelector('input')?.focus();
    },

    confirmCover: async function(form) {
        const path = document.getElementById('upk-path').value;
        const consoleBox = document.getElementById('unpacker-console');
        const choice = form?.querySelector('input[name="upk-cover"]:checked');
        if (!choice) return;

        const fieldset = form.querySelector('fieldset');
        const btn = form.querySelector('#upk-confirm-cover');
        const chosenAt = new Date().toLocaleTimeString('en-GB', { hour12: false });
        fieldset.disabled = true;
        btn.textContent = 'Adding the cover…';

        // Streaming, not a single blocking JSON response (John's report,
        // 2026-08-14): the per-track embed loop shows live progress.
        let finalized = false;
        let hadError = false;

        try {
            const res = await fetch('/run_tool_logic/unpack_convert/finalize_art', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path, filename: choice.value })
            });

            // v2: events + signals via MFEvents; the "ready for tagging"
            // line comes from the server (and so is in MetaForge.log too).
            await window.MFEvents.read(res, {
                log: consoleBox,
                onSignal: (name) => {
                    if (name === 'finalize_done') finalized = true;
                    if (name === 'finalize_error') hadError = true;
                }
            });

            if (finalized && !hadError) {
                // The picker becomes a one-line record of the choice, in
                // place, so the log still reads in order.
                const row = window.MFEvents.render(consoleBox, {
                    kind: 'success', text: 'Cover chosen', file: choice.value, time: chosenAt
                });
                const thumb = document.createElement('img');
                thumb.className = 'mf-ev-thumb';
                thumb.alt = '';
                thumb.src = choice.dataset.thumb;
                row.querySelector('.mf-ev-text').prepend(thumb);
                form.replaceWith(row);
                this.showHandoff(path);
            } else {
                // Real failure (bad image, disk error...): keep the picker
                // usable so the user can retry or pick another image.
                fieldset.disabled = false;
                btn.textContent = 'Confirm cover';
                btn.focus();
            }
        } catch (err) {
            window.MFEvents.render(consoleBox, { kind: 'error', text: `The cover couldn't be applied: ${err.message}` });
            window.MFAnnounce(`Error: the cover couldn't be applied: ${err.message}`, { urgent: true });
            fieldset.disabled = false;
            btn.textContent = 'Confirm cover';
            btn.focus();
        } finally {
            const mainFieldset = document.getElementById('upk-fieldset');
            if (mainFieldset) mainFieldset.disabled = false;
        }
    },

    /**
     * v2 Next-step bar (shared .mf-handoff): shown when the run is
     * finished. Focus goes to Continue, because the control the user last
     * used (Start or Confirm cover) is now disabled or gone.
     */
    showHandoff: function(path) {
        const bar = document.getElementById('upk-handoff');
        const btn = document.getElementById('upk-continue-btn');
        if (!bar || !btn) return;
        const albumPath = path || document.getElementById('upk-path').value.trim();
        btn.onclick = () => window.mfAdvanceWorkflow('musicbrainz_id', albumPath);
        bar.hidden = false;
        this.setProgressLabel('Finished');
        btn.focus();
    },

    hideHandoff: function() {
        const bar = document.getElementById('upk-handoff');
        if (bar) bar.hidden = true;
    },

    setProgressLabel: function(text) {
        const label = document.getElementById('upk-progress-label');
        if (label) label.innerText = text;
        document.getElementById('upk-progress-container')?.setAttribute('aria-valuetext', text);
    },

    updateProgress: function(phase, current, total) {
        const fill = document.getElementById('upk-progress-fill');
        const label = document.getElementById('upk-progress-label');
        const container = document.getElementById('upk-progress-container');
        
        const phaseNum = parseInt(phase) || 1;
        const curNum = parseInt(current) || 0;
        const totNum = Math.max(parseInt(total) || 1, 1);

        const phasePercent = Math.round((curNum / totNum) * 100);
        let globalPercent = (phaseNum === 1) ? (curNum / totNum) * 50 : 50 + ((curNum / totNum) * 50);
        globalPercent = Math.min(Math.max(globalPercent, 0), 100);

        const actionText = (phaseNum === 1) ? "Unpacking" : "Converting";

        if (fill) fill.style.width = `${globalPercent}%`;
        const status = `${actionText}: ${curNum} of ${totNum} (${phasePercent}%)`;
        if (label) label.innerText = status;
        if (container) {
            container.setAttribute('aria-valuenow', Math.round(globalPercent));
            container.setAttribute('aria-valuetext', status);
        }
    },

    /**
     * Reapplies persisted lock state to the Filing Category select/button
     * after they've been freshly rebuilt (either by init()'s re-entry
     * path, or by populateSelect() rebuilding the option list). Safe to
     * call even when nothing is locked -- it's a no-op in that case.
     */
    applyCategoryLockState: function() {
        const select = document.getElementById('upk-category');
        const btn = document.getElementById('upk-category-lock');
        if (!select || !btn) return;

        if (!this.categoryLocked) {
            select.disabled = false;
            btn.classList.remove('locked');
            btn.setAttribute('aria-pressed', 'false');
            btn.setAttribute('aria-label', 'Lock Filing Category so it stays set for the next album');
            btn.title = 'Lock Filing Category';
            return;
        }

        select.value = this.lockedCategoryValue;
        if (select.value !== this.lockedCategoryValue) {
            // The remembered category no longer exists in the freshly
            // fetched list (e.g. taxonomy changed) -- don't silently lock
            // to a value that isn't really selected. Fail open, not
            // open-but-wrong.
            this.categoryLocked = false;
            this.lockedCategoryValue = "";
            select.disabled = false;
            btn.classList.remove('locked');
            btn.setAttribute('aria-pressed', 'false');
            return;
        }

        select.disabled = true;
        btn.classList.add('locked');
        btn.setAttribute('aria-pressed', 'true');
        btn.setAttribute('aria-label', 'Unlock Filing Category');
        btn.title = 'Unlock Filing Category';
    },

    toggleCategoryLock: function() {
        const select = document.getElementById('upk-category');
        if (!select) return;

        if (this.categoryLocked) {
            this.categoryLocked = false;
            this.lockedCategoryValue = "";
        } else {
            if (!select.value) {
                // Nothing to lock yet -- use the select's own native
                // required-field validation bubble rather than inventing
                // a new status-toast mechanism this tool doesn't have.
                select.focus();
                select.reportValidity();
                return;
            }
            this.categoryLocked = true;
            this.lockedCategoryValue = select.value;
        }

        this.applyCategoryLockState();
        this.validate();

        // Persist to disk (not just this session's memory) -- fire and
        // forget, same "don't block the UI on a settings write" pattern
        // the consent checkbox already uses. An empty string clears the
        // lock server-side too.
        fetch('/run_tool_logic/unpack_convert/set_locked_category', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category: this.lockedCategoryValue })
        }).catch(err => console.error("METAFORGE: Failed to persist category lock:", err));
    },

    /**
     * Filing Artist lock -- same pattern and reasoning as
     * applyCategoryLockState() above, just for a text input instead of a
     * select. No "value no longer exists" check needed here (that was
     * specific to the category select's fixed option list); a locked
     * artist name is always valid to reapply as-is.
     */
    applyArtistLockState: function() {
        const input = document.getElementById('upk-artist');
        const btn = document.getElementById('upk-artist-lock');
        if (!input || !btn) return;

        if (!this.artistLocked) {
            input.disabled = false;
            btn.classList.remove('locked');
            btn.setAttribute('aria-pressed', 'false');
            btn.setAttribute('aria-label', 'Lock Filing Artist so it stays set for the next album');
            btn.title = 'Lock Filing Artist';
            return;
        }

        input.value = this.lockedArtistValue;
        input.disabled = true;
        btn.classList.add('locked');
        btn.setAttribute('aria-pressed', 'true');
        btn.setAttribute('aria-label', 'Unlock Filing Artist');
        btn.title = 'Unlock Filing Artist';
    },

    toggleArtistLock: function() {
        const input = document.getElementById('upk-artist');
        if (!input) return;

        if (this.artistLocked) {
            this.artistLocked = false;
            this.lockedArtistValue = "";
        } else {
            if (!input.value.trim()) {
                // Nothing to lock yet -- same native validation-bubble
                // approach as toggleCategoryLock().
                input.focus();
                input.reportValidity();
                return;
            }
            this.artistLocked = true;
            this.lockedArtistValue = input.value.trim();
        }

        this.applyArtistLockState();
        this.validate();

        fetch('/run_tool_logic/unpack_convert/set_locked_artist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist: this.lockedArtistValue })
        }).catch(err => console.error("METAFORGE: Failed to persist artist lock:", err));
    },

    populateSelect: function(select, items) {
        if (!select) return;
        const cur = select.value;
        select.innerHTML = '<option value="">-- Select Category --</option>';
        items.forEach(c => { 
            const o = document.createElement('option'); o.value = c; o.innerText = c; select.appendChild(o); 
        });
        if (cur) select.value = cur;
    },

    pickFolder: async function() {
        const path = await window.pywebview?.api?.select_folder();
        if (path) { 
            const pathIn = document.getElementById('upk-path');
            if (pathIn) pathIn.value = path; 
            this.validate(); 
        }
    },

    /**
     * Build 8.2.1 Fix: Reordered DOM update sequence to ensure triggers follow visual text.
     */
    run: async function() {
        const consoleBox = document.getElementById('unpacker-console');
        const btn = document.getElementById('upk-start-btn');
        const fieldset = document.getElementById('upk-fieldset');
        const fill = document.getElementById('upk-progress-fill');
        const label = document.getElementById('upk-progress-label');

        if (btn) btn.disabled = true;
        if (fieldset) fieldset.disabled = true;
        
        if (fill) fill.style.width = '0%';
        if (label) label.innerText = 'Starting Unpack & Convert...';
        if (consoleBox) consoleBox.replaceChildren();
        // No explicit scrollbar sync needed here -- MFScrollbar's
        // MutationObserver (metaforge_core.js) auto-detects this console
        // reset and resyncs the shared custom scrollbar itself.

        document.getElementById('upk-cover-step')?.remove();
        this.hideHandoff();

        // Build 8.2.2 (2026-10-01 review): this used to check
        // Intelli-Tagger's #it-path first -- a stray cross-tool reference.
        // This tool's own path field is the only source of truth here.
        const path = document.getElementById('upk-path').value.trim();
        const payload = {
            artist: document.getElementById('upk-artist').value.trim(),
            album: document.getElementById('upk-album').value.trim(),
            path: path,
            category: document.getElementById('upk-category')?.value || "",
            remember: document.getElementById('upk-remember').checked,
            normalization: document.getElementById('upk-norm').checked
        };

        try {
            const res = await fetch('/run_tool_logic/unpack_convert/run_unpack', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            // v2 (Phase 0.3): the engines send events, not HTML. MFEvents
            // (metaforge_core.js) draws them and hands the control signals
            // here; the 1.x hidden-marker scanning (PROGRESS / ART_READY /
            // "ready for tagging." text matches) is gone.
            let hasArtReady = false;
            await window.MFEvents.read(res, {
                log: consoleBox,
                onSignal: (name, data) => {
                    if (name === 'progress') {
                        this.updateProgress(data.phase, data.current, data.total);
                    } else if (name === 'art_ready' && !hasArtReady) {
                        hasArtReady = true;
                        this.loadArtGallery();
                    } else if (name === 'handoff_ready') {
                        this.showHandoff(path);
                    }
                }
            });

            if (!hasArtReady && fieldset) {
                fieldset.disabled = false;
            }

        } catch (err) {
            window.MFEvents.render(consoleBox, { kind: 'error', text: `The run stopped: ${err.message}` });
            window.MFAnnounce(`Error: the run stopped: ${err.message}`, { urgent: true });
            if (fieldset) fieldset.disabled = false;
        } finally {
            this.validate(); 
        }
    },


    // Custom scrollbar for #unpacker-console is no longer wired here --
    // it now uses the shared MFScrollbar utility (metaforge_core.js),
    // auto-attached via unpack_convert.mfi's .mf-custom-scrollbar markup.
};

window.metaforge.unpack_convert.init();
window.metaforge.unpack_convert.setupReentryWatcher();

// --- END OF FILE unpack_convert.js ---
