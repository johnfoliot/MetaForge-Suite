# MetaForge Suite — Claude Code instructions

## Web UI work: always use `modern-web-guidance`

Use the `modern-web-guidance` skill before writing or changing any user-facing markup, CSS or client-side JS. That includes HTML generated inside Python files (engine log output, f-string templates), not just `.html`/`.css`/`.js` files. Pay particular attention to accessibility (WCAG, COGA).

**Desktop only:** MetaForge is a desktop tool with a minimum window width of 1240px. Don't design or test phone/tablet layouts; do make sure everything fits at 1240px. Height matters too: John runs Windows at ~150% scaling, and his maximised window measures an effective **1280×668** viewport (1920×1080 at 150%, minus the taskbar and title bar), so test layouts at 1280×668. The app shell doesn't scroll as a whole; regions that can outgrow the window (like the left rail's tool list) must scroll on their own, and each such region is `position: relative` so hidden screen-reader text (`.mf-visually-hidden`) inside it can't escape and make the page scroll.

**Larger text beats a tidy fit:** users who enlarge their text take precedence over fitting the screen at the default size. Never shrink type or rely on a fixed fit. Test every reworked screen at 1280×668 with the root font size at 100%, 150% and 200%: the page must not scroll, the primary action stays reachable, and a focused field is never hidden behind pinned content (WCAG 1.4.4, 1.4.10, 2.4.11).

**Enter submits (native-app feel):** any group of fields that ends in an action button must run that action when Enter is pressed in a field. Use a real `<form>` with the action button as `type="submit"` and handle the `submit` event (`preventDefault()`); every other button in the group is `type="button"`. No per-field Enter key handlers.

**Brand colour:** `#CC9900` is the ONLY gold. Never introduce an alternative gold (lighter, darker or "adjusted for contrast"), in any theme, including for focus rings or warning colours. Where gold would fail WCAG contrast, a theme pivots to another colour (the light theme uses blue `#1a2fb5`) instead of a different gold. `#CC9900` may still be used as a fill behind dark text. **The logo** is the 3-D MetaForge logo: generated from `ui/images/logo_master.png` in the theme's logo colour (`tools/settings/engines/logo_engine.py`), or a theme's own hand-made `logo.png`. Never replace it with a text wordmark.

**Themes** are folders in `ui/themes/<id>/` (`manifest.json`, colours-only `theme.css`, `logo.png`), found automatically like tools; themes users make live in `%APPDATA%\MetaForge\themes\<id>\`. A theme with a second gold or a broken file is refused; one below the contrast guidelines is only an advisory, offered when the user turns on "Also show themes that don't meet contrast guidelines". Built-in themes must pass.

**Browser Support:** MetaForge runs only in WebView2 (evergreen Chromium) and is meant to stay fully self-contained. Chromium-supported features may be used without cross-browser fallbacks or polyfills. No CDN or external runtime dependencies; any library must be vendored locally.
