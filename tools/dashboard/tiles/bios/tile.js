// --- START OF FILE tiles/bios/tile.js ---
// Dashboard tile: Who needs a bio? (v2, 2026-11-16)
// "Build bio" hands the artist to Bio Builder (window.mf_context_artist_id,
// read by biography.js ingestContext), as Database Tools does.
window.metaforge.dashboardTiles.bios = {
    render(t, d, kit) {
        const { h, fmt } = kit;
        t.body.append(
            h('p', { class: 'db-pair' }, h('span', { class: 'db-big' }, fmt(d.primary_count)),
                h('span', { class: 'db-muted' }, `main artists with ${d.primary_min} or more tracks`)),
            h('p', { class: 'db-pair' }, h('span', { class: 'db-big' }, fmt(d.supporting_count)),
                h('span', { class: 'db-muted' }, `session players credited with ${d.supporting_min} or more different artists`)));
        t.footer.append(kit.button('See who', () => kit.openDetail('bios')));
    },

    detail(body, d, kit) {
        const { h, fmt } = kit;
        const buildBio = (a) => kit.button('Build bio', () => {
            kit.closeDetail();
            window.mf_context_artist_id = a.id;
            kit.goTo('biography');
        }, false, { 'aria-label': `Build bio: ${a.name}` });
        const more = (n, shown) => (n > shown ? h('p', { class: 'db-muted' }, `Showing the first ${fmt(shown)}.`) : null);
        const form = h('form', {
            class: 'db-field',
            onsubmit: async (e) => {
                e.preventDefault();
                const dd = await kit.openDetail('bios', { min: form.elements.min.value });
                document.getElementById('db-min')?.focus();
                if (dd) window.MFAnnounce?.(`${fmt(dd.supporting_count)} session players.`);
            }
        },
            h('label', { for: 'db-min' }, 'Credited with at least'),
            h('input', { type: 'number', id: 'db-min', name: 'min', min: '2', max: '50', value: String(d.supporting_min), required: true }),
            h('span', {}, 'different artists'),
            h('button', { type: 'submit', class: 'mf-button-gold-fixed db-btn-quiet' }, 'Update'));
        body.append(
            h('h3', {}, `Main artists with ${d.primary_min} or more tracks (${fmt(d.primary_count)})`),
            h('table', { class: 'db-table' },
                h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Artist'), h('th', { scope: 'col', class: 'db-n' }, 'Tracks'),
                    h('th', { scope: 'col' }, h('span', { class: 'mf-visually-hidden' }, 'Action')))),
                h('tbody', {}, d.primary.map((a) => h('tr', {}, h('td', {}, a.name), h('td', { class: 'db-n' }, fmt(a.tracks)), h('td', {}, buildBio(a)))))),
            more(d.primary_count, d.primary.length),
            h('h3', {}, `Session players (${fmt(d.supporting_count)})`),
            h('p', { class: 'db-muted' }, 'Credited on other artists’ albums, with no tracks of their own here. Ranked by how many different artists they’re credited with.'),
            form,
            h('table', { class: 'db-table' },
                h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Artist'), h('th', { scope: 'col', class: 'db-n' }, 'Different artists'),
                    h('th', { scope: 'col', class: 'db-n' }, 'Credits'), h('th', { scope: 'col' }, h('span', { class: 'mf-visually-hidden' }, 'Action')))),
                h('tbody', {}, d.supporting.map((a) => h('tr', {}, h('td', {}, a.name), h('td', { class: 'db-n' }, fmt(a.artists)),
                    h('td', { class: 'db-n' }, fmt(a.credits)), h('td', {}, buildBio(a)))))),
            more(d.supporting_count, d.supporting.length));
    }
};
