// --- START OF FILE tiles/progress/tile.js ---
// Dashboard tile: How much is tagged? (v2, 2026-11-16)
// Registers { render, detail, scanProgress } with the Dashboard; `kit` is
// the Dashboard's helper set (see dashboard.js).
window.metaforge.dashboardTiles.progress = {
    render(t, d, kit) {
        const { h, fmt } = kit;
        const cats = d.categories;
        const scanned = d.disk_total !== null && d.disk_total !== undefined;
        t.body.append(scanned
            ? h('p', { class: 'db-muted' }, h('span', { class: 'db-big' }, fmt(d.tagged_total)),
                ` of ${fmt(d.disk_total)} tracks on disk (${Math.round(100 * d.tagged_total / Math.max(1, d.disk_total))}%). Each bar's length is the tracks on disk; the filled part is tagged.`)
            : h('p', { class: 'db-muted' }, h('span', { class: 'db-big' }, fmt(d.tagged_total)),
                ' tracks tagged. Files on disk haven’t been counted yet.'));
        const top = cats.slice(0, 5);
        if (scanned) {
            const max = Math.max(1, ...top.map((c) => c.on_disk || 0));
            t.body.append(h('ul', { class: 'db-bars' }, top.map((c) => h('li', {},
                h('span', {}, c.name),
                h('span', { class: 'db-track', 'aria-hidden': 'true', style: { '--len': `${100 * (c.on_disk || 0) / max}%` } },
                    h('span', { class: 'db-fill', style: { '--done': `${Math.min(100, 100 * c.tagged / Math.max(1, c.on_disk || 0))}%` } })),
                h('span', { class: 'db-num' }, c.on_disk ? `${fmt(c.tagged)} of ${fmt(c.on_disk)}` : `${fmt(c.tagged)} tagged`)))));
        } else {
            t.body.append(h('ul', { class: 'db-list' }, top.map((c) =>
                h('li', {}, h('span', {}, c.name), h('span', { class: 'db-n' }, `${fmt(c.tagged)} tagged`)))));
        }
        this.note = h('span', { class: 'db-muted' });
        this.rescan = kit.button(scanned ? 'Rescan' : 'Count files on disk', () => kit.scan.start(), true);
        this.idle = `${d.scanned_at ? `On disk: counted ${kit.day(d.scanned_at)}.` : 'On disk: not counted yet.'} ${top.length} of ${cats.length} categories shown.`;
        t.footer.append(this.note, this.rescan, kit.button('Open', () => kit.openDetail('progress')));
        this.scanProgress(d.scan, kit);
        if (d.scan?.running) kit.scan.watch();
    },

    /** Called by the Dashboard while the disk count runs (and once on render). */
    scanProgress(s, kit) {
        if (!this.note?.isConnected) return;
        this.note.classList.toggle('db-error', Boolean(s?.error));
        this.rescan.disabled = Boolean(s?.running);
        this.note.textContent = s?.running ? `Counting files on disk… ${kit.fmt(s.files)} so far.`
            : s?.error ? `Error: the count stopped. ${s.error}` : this.idle;
    },

    detail(body, d, kit) {
        const { h, fmt } = kit;
        const byFolder = h('table', { class: 'db-table' },
            h('caption', { class: 'mf-visually-hidden' }, 'Tracks tagged and on disk, by category folder'),
            h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Category folder'), h('th', { scope: 'col', class: 'db-n' }, 'Tagged'),
                h('th', { scope: 'col', class: 'db-n' }, 'On disk'), h('th', { scope: 'col', class: 'db-n' }, 'Done'))),
            h('tbody', {}, d.categories.map((c) => h('tr', {}, h('td', {}, c.name), h('td', { class: 'db-n' }, fmt(c.tagged)),
                h('td', { class: 'db-n' }, c.on_disk ? fmt(c.on_disk) : '–'),
                h('td', { class: 'db-n' }, c.on_disk ? `${Math.round(100 * c.tagged / c.on_disk)}%` : '–')))));
        const byGenre = h('table', { class: 'db-table', hidden: true },
            h('caption', { class: 'mf-visually-hidden' }, 'Tagged tracks by genre, with sub-genres'),
            h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Genre'), h('th', { scope: 'col', class: 'db-n' }, 'Tagged'),
                h('th', { scope: 'col' }, 'Sub-genres'))),
            h('tbody', {}, d.genres.map((g) => h('tr', {}, h('td', {}, g.genre), h('td', { class: 'db-n' }, fmt(g.tracks)),
                h('td', { class: 'db-sub' }, g.subs.map((s) => `${s.name} ${fmt(s.tracks)}`).join(' · '))))));
        const pick = (e) => { byFolder.hidden = e.target.value !== 'folder'; byGenre.hidden = e.target.value !== 'genre'; };
        body.append(
            h('fieldset', { class: 'db-view' }, h('legend', {}, 'Count by'),
                h('label', {}, h('input', { type: 'radio', name: 'db-view', value: 'folder', checked: true, onchange: pick }), 'Category folder (tagged and on disk)'),
                h('label', {}, h('input', { type: 'radio', name: 'db-view', value: 'genre', onchange: pick }), 'Tagged genre')),
            d.disk_total ? null : h('p', { class: 'db-muted' }, 'On disk: not counted yet. Use “Count files on disk” on the tile.'),
            byFolder, byGenre);
    }
};
