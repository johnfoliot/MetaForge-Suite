// --- START OF FILE tiles/health/tile.js ---
// Dashboard tile: What looks wrong? (v2, 2026-11-16)
window.metaforge.dashboardTiles.health = {
    render(t, d, kit) {
        const { h, fmt } = kit;
        t.body.append(h('ul', { class: 'db-list db-list-2' }, d.checks.map((c) => h('li', {},
            h('span', {}, c.label),
            c.count === null ? h('span', { class: 'db-muted' }, 'count files on disk first')
                : h('span', { class: `db-n${c.count ? ' db-warn' : ''}` }, fmt(c.count))))));
        t.footer.append(kit.button('See details', () => kit.openDetail('health')));
    },

    detail(body, d, kit) {
        const { h, fmt } = kit;
        d.checks.forEach((c) => {
            body.append(h('h3', {}, `${c.label} (${c.count === null ? 'not counted yet' : fmt(c.count)})`));
            if (!c.items) { body.append(h('p', { class: 'db-muted' }, 'Count files on disk first (on the “How much is tagged?” tile).')); return; }
            if (!c.items.length) { body.append(h('p', { class: 'db-muted' }, 'None.')); return; }
            const withValue = c.items.some((i) => i.value);
            body.append(h('table', { class: 'db-table' },
                h('tbody', {}, c.items.map((i) => h('tr', {}, h('td', {}, i.item), withValue ? h('td', { class: 'db-n' }, i.value) : null)))));
            if (c.more) body.append(h('p', { class: 'db-muted' }, `…and ${fmt(c.more)} more.`));
        });
    }
};
