"""
One-off (John approved 2026-11-16): clean up the AcoustID waiting lists.
  - split paths that 1.x glued together (missing final newline)
  - drop duplicates
  - move paths that no longer exist to not_found.txt
Dry run by default; `--apply` backs up data/acoustid first, then writes.

    python dev\\acoustid_queue_cleanup.py            (dry run)
    python dev\\acoustid_queue_cleanup.py --apply
"""
import importlib.util
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from common import config_handler  # noqa: E402

spec = importlib.util.spec_from_file_location("acoustid", ROOT / "tools" / "acoustid" / "acoustid.py")
aid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aid)


def main(apply):
    folder = aid._dir()
    report = []
    keep, gone = {}, []
    for name in ("pending", "history"):
        f = aid._file(name)
        raw = [l for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.exists() else []
        clean = aid.normalise(raw)
        parts = [len(aid._JOINED.split(l.strip())) for l in raw]
        glued = sum(1 for n in parts if n > 1)
        missing = [p for p in clean if not Path(p).exists()]
        keep[name] = [p for p in clean if Path(p).exists()]
        gone += missing
        report.append(f"{f.name}: {len(raw)} lines, {glued} glued, {sum(parts) - len(clean)} duplicates, "
                      f"{len(missing)} not found -> keeps {len(keep[name])}")
    print("\n".join(report))
    for p in gone:
        print("  not found:", p)
    if not apply:
        print("\nDry run: nothing written. Add --apply to write.")
        return
    backup = Path(config_handler.APPDATA_MF) / "backups" / "acoustid" / datetime.now().strftime("%Y-%m-%d %H%M%S queue cleanup")
    shutil.copytree(folder, backup)
    aid.write_list("pending", keep["pending"])
    aid.write_list("history", keep["history"])
    aid.write_list("not_found", aid.normalise(aid.read_list("not_found") + gone))
    print(f"\nWritten. Backup: {backup}")


if __name__ == "__main__":
    main("--apply" in sys.argv)
