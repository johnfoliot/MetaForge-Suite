/* --- START OF FILE unpack_convert.js --- */
/**
 * ======================================================================
 * MetaForge Logic Bridge: Unpack & Convert
 * Build 8.2.1: Workflow Handoff Ordering Fix.
 * Role: Transitions path context to Step 2 (MusicBrainz IDs).
 * Accessibility: WCAG 2.2 AA | COGA 4.5.10 (Feedback Loops)
 * ======================================================================
 */

console.log("METAFORGE: unpack_convert.js Build 8.2.1 active...");

window.metaforge = window.metaforge || {};
window.metaforge.unpack_convert = {
    lastTrigger: null,
    selectedArtFile: null,
    observer: null,

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

        setTimeout(async () => {
            const progLabel = document.getElementById('upk-progress-label');
            const enhancedPanel = document.getElementById('enhanced-section');
            const select = document.getElementById('upk-category');
            const consentGate = document.getElementById('upk-consent-gate');
            const fieldset = document.getElementById('upk-fieldset');

            if (!progLabel) return;
            if (fieldset) fieldset.disabled = false;
            
            try {
                const res = await fetch(`/run_tool_logic/unpack_convert/get_interview_data?t=${Date.now()}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                
                const data = await res.json();
                
                if (progLabel) {
                    const formattedPolicy = this.toTitleCase(data.policy);
                    progLabel.innerText = `📚 Library Type: ${formattedPolicy}`;
                }

                if (data.policy === "ENHANCED") {
                    if (enhancedPanel) enhancedPanel.style.display = 'flex';
                    this.populateSelect(select, data.categories);
                    if (select) {
                        select.required = true;
                        select.setAttribute('aria-required', 'true');
                    }
                } else {
                    if (enhancedPanel) enhancedPanel.style.display = 'none';
                }

                if (data.stored_consent === true) {
                    if (consentGate) consentGate.style.display = 'none';
                    const consentCheckbox = document.getElementById('upk-consent');
                    if (consentCheckbox) consentCheckbox.checked = true;
                } else {
                    if (consentGate) consentGate.style.display = 'flex';
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
            btn.disabled = !isReady;
            btn.style.opacity = isReady ? "1" : "0.5";
        }
    },

    loadArtGallery: async function() {
        const path = document.getElementById('upk-path').value;
        const consoleBox = document.getElementById('unpacker-console');
        if (!consoleBox) return;

        try {
            const res = await fetch(`/run_tool_logic/unpack_convert/get_art_gallery?path=${encodeURIComponent(path)}`);
            const images = await res.json();
            if (images.length === 0) return;

            let galleryHTML = `
                <div id="upk-step4-wrapper" style="margin-top:20px; border-top:2px solid var(--bg-accent); padding-top:15px;">
                    <div class="status-api">🖼️ Step 4: Album Cover Selection</div>
                    <div class="data-text" style="margin-bottom:10px;">Select the primary image to promote as folder.jpg</div>
                    <div id="upk-art-gallery" class="art-selection-grid">
            `;

            images.forEach((img, idx) => {
                galleryHTML += `
                    <div class="art-card" onclick="metaforge.unpack_convert.selectArt('${img.filename}', ${idx})" id="art-card-${idx}" tabindex="0" onkeydown="if(event.key==='Enter' || event.key===' ') { event.preventDefault(); metaforge.unpack_convert.selectArt('${img.filename}', ${idx}); }">
                        <div class="art-preview" style="background-image: url('${img.data}')"></div>
                        <div class="art-meta" title="${img.filename}">${img.filename}</div>
                        <div class="art-meta" style="color:var(--mf-gold)">${img.width} x ${img.height}</div>
                        <div class="art-selector-row">
                            <input type="radio" name="art-choice" class="art-radio" id="radio-${idx}" 
                                   aria-label="Select ${img.filename}, ${img.width} by ${img.height} pixels"
                                   onchange="metaforge.unpack_convert.handleRadioChange(${idx})">
                            <label for="radio-${idx}" class="art-meta">Select</label>
                        </div>
                    </div>
                `;
            });

            galleryHTML += `
                    </div>
                    <div style="text-align: right; margin-top: 10px; padding-bottom: 20px;">
                        <button id="upk-confirm-art-btn" class="mf-button-gold-fixed upk-confirm-art-btn" onclick="metaforge.unpack_convert.confirmCover()" disabled>
                            Confirm Cover
                        </button>
                    </div>
                </div>
            `;

            consoleBox.insertAdjacentHTML('beforeend', galleryHTML);
            consoleBox.scrollTop = consoleBox.scrollHeight;
        } catch (err) {
            console.error("METAFORGE: Art Gallery Error:", err);
        }
    },

    selectArt: function(filename, index) {
        this.selectedArtFile = filename;
        const btn = document.getElementById('upk-confirm-art-btn');
        if (btn) btn.disabled = false;

        document.querySelectorAll('.art-card').forEach(card => card.classList.remove('selected'));
        document.querySelectorAll('.art-radio').forEach(radio => radio.checked = false);

        const selectedCard = document.getElementById(`art-card-${index}`);
        const selectedRadio = document.getElementById(`radio-${index}`);
        if (selectedCard) selectedCard.classList.add('selected');
        if (selectedRadio) selectedRadio.checked = true;
    },

    handleRadioChange: function(index) {
        const selectedCard = document.getElementById(`art-card-${index}`);
        if (!selectedCard) return;
        const title = selectedCard.querySelector('.art-meta[title]')?.title;
        if (title) this.selectArt(title, index);
    },

    confirmCover: async function() {
        const path = document.getElementById('upk-path').value;
        const btn = document.getElementById('upk-confirm-art-btn');
        const consoleBox = document.getElementById('unpacker-console');
        const albumName = document.getElementById('upk-album').value;

        if (!this.selectedArtFile) return;
        if (btn) btn.disabled = true;

        try {
            const res = await fetch('/run_tool_logic/unpack_convert/finalize_art', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path, filename: this.selectedArtFile })
            });
            const result = await res.json();

            if (result.status === "success") {
                const step4Wrapper = document.getElementById('upk-step4-wrapper');
                if (step4Wrapper) {
                    step4Wrapper.style.opacity = "0.5";
                    step4Wrapper.style.pointerEvents = "none";
                }

                const finalMessage = `
                    <div class="status-success" style="margin-top:10px; font-size:.8rem; overflow:hidden;">
                        <div>
                            Processing Complete: <span style="color:var(--mf-gold); font-weight:bold;">${albumName}</span> has been processed and is ready for the next step.
                        </div>
                    </div>
                `;
                consoleBox.insertAdjacentHTML('beforeend', finalMessage);
                this.injectHandoffButton(path);
                consoleBox.scrollTop = consoleBox.scrollHeight;
            }
        } catch (err) {
            if (consoleBox) consoleBox.insertAdjacentHTML('beforeend', `<div class="status-error">❌ Promotion Error: ${err.message}</div>`);
        } finally {
            const fieldset = document.getElementById('upk-fieldset');
            if (fieldset) fieldset.disabled = false;
        }
    },

    /**
     * Workflow Orchestration: Injects the Hand-off trigger.
     * Build 8.2.1: Logic refined to ensure button always appends to end of current log stack.
     */
    injectHandoffButton: function(passedPath) {
        const consoleBox = document.getElementById('unpacker-console');
        if (!consoleBox || document.getElementById('upk-handoff-gate')) return;

        const path = passedPath || document.getElementById('upk-path').value.trim();
        const escapedPath = path.replace(/\\/g, "\\\\");

        const handoffHTML = `
            <div id="upk-handoff-gate" style="margin-top: 20px; text-align: right; border-top: 1px solid var(--bg-accent); padding-top: 15px;">
                <button class="mf-button-gold-fixed" onclick="window.mfAdvanceWorkflow('musicbrainz_id', '${escapedPath}')">
                    Continue to: MusicBrainzIDs
                </button>
            </div>
        `;
        consoleBox.insertAdjacentHTML('beforeend', handoffHTML);
        consoleBox.scrollTop = consoleBox.scrollHeight;
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
        if (label) label.innerText = `${actionText} | ${curNum}/${totNum} (${phasePercent}%)`;
        if (container) container.setAttribute('aria-valuenow', Math.round(globalPercent));
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
        if (consoleBox) consoleBox.innerHTML = '<div class="status-api">Initializing...</div>';
        
        const step4Wrapper = document.getElementById('upk-step4-wrapper');
        if (step4Wrapper) step4Wrapper.remove();

        const path = document.getElementById('it-path')?.value.trim() || document.getElementById('upk-path').value.trim();
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

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let hasArtReady = false;

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value);
                
                // 1. Process Metadata / Non-DOM updates
                const progMatch = chunk.match(/<!-- PROGRESS:(\d+):(\d+):(\d+) -->/);
                if (progMatch) this.updateProgress(progMatch[1], progMatch[2], progMatch[3]);

                // 2. Commit chunk to DOM (This must happen first to ensure correct vertical ordering)
                if (consoleBox) {
                    consoleBox.insertAdjacentHTML('beforeend', chunk);
                }

                // 3. Evaluate Workflow Triggers based on cumulative state
                if (chunk.includes('<!-- ART_READY -->')) {
                    hasArtReady = true;
                    this.loadArtGallery();
                }

                if (chunk.includes('ready for tagging.')) {
                     this.injectHandoffButton(path);
                }
                
                if (consoleBox) {
                    consoleBox.scrollTop = consoleBox.scrollHeight;
                }
            }

            if (!hasArtReady && fieldset) {
                fieldset.disabled = false;
            }

        } catch (err) { 
            if (consoleBox) consoleBox.insertAdjacentHTML('beforeend', `<div class="status-error">FAIL: ${err.message}</div>`); 
            if (fieldset) fieldset.disabled = false;
        } finally { 
            this.validate(); 
        }
    },

    openHelp: async function() {
        const panel = document.getElementById('upk-help-panel');
        const body = document.getElementById('upk-help-body');
        const title = document.getElementById('upk-panel-title');
        this.lastTrigger = document.activeElement;
        if (!panel || !body) return;
        try {
            const response = await fetch('/tool_asset/unpack_convert/help.mfi');
            const html = await response.text();
            body.innerHTML = html;
            panel.style.display = 'flex';
            setTimeout(() => { if (title) { title.setAttribute('tabindex', '-1'); title.focus(); } }, 20);
        } catch (err) { body.innerHTML = `<p style="color:red; padding:15px;">Error: ${err.message}</p>`; panel.style.display = 'flex'; }
    },

    closeHelp: function() {
        const panel = document.getElementById('upk-help-panel');
        if (panel) { panel.style.display = 'none'; if (this.lastTrigger) this.lastTrigger.focus(); }
    }
};

window.metaforge.unpack_convert.init();
window.metaforge.unpack_convert.setupReentryWatcher();

// --- END OF FILE unpack_convert.js ---