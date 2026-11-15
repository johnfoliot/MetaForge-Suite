# Publishing a MetaForge Studio release

`deploy/updates.json` on GitHub's **main** branch is what every installed copy reads when you choose
Settings > Check for updates (`tools/settings/engines/update_engine.py`). An update is announced, with a
link to its GitHub release page; you download it yourself (an installer comes later).

## Release steps (e.g. 2.0.1)

1. Set the version in `common/version.py`: `APP_VERSION = "2.0.1"`.
2. Commit, merge to `main`, and create the GitHub release (tag `v2.0.1`) with its download.
3. Replace `deploy/updates.json` on `main` with:

```json
{
    "schema_version": 3,
    "latest_version": "2.0.1",
    "released": "YYYY-MM-DD",
    "priority": "optional",
    "title": "MetaForge Studio 2.0.1",
    "notes": "Plain text: what's new. Shown as text, never as HTML.",
    "url": "https://github.com/johnfoliot/MetaForge-Suite/releases/tag/v2.0.1"
}
```

4. Check from an older build: Settings > Check for updates should offer 2.0.1. From the new build it
   should say you're up to date.

## Rules the checker enforces

- **Version order is real:** `2.0.0-dev` < `2.0.0` < `2.0.1` < `2.10.0`. Only a strictly newer
  `latest_version` is offered.
- **`priority: "required"`** can't be dismissed. `"optional"` can be ("don't tell me about this
  version again"); a later version is still announced.
- **`url` must be an `https://github.com/...` link**; anything else is not shown.
- **`notes` and `title` are plain text.**

## Testing without publishing

`python dev\use_update_test.py update_available` (or `up_to_date`, `required_update`, `unsafe_link`,
`offline`) makes the checker read a local scenario file instead of GitHub; the screen shows "Test mode".
`python dev\use_update_test.py off` returns to the real check.
