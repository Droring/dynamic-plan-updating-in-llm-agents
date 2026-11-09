"""Check local Markdown file links; external URLs and anchors are intentionally not fetched."""
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
files = sorted(ROOT.rglob("*.md"))
missing = []
for file in files:
    text = file.read_text(encoding="utf-8")
    for match in re.finditer(r'!?\[[^\]]*\]\(([^)]+)\)', text):
        raw = match.group(1).strip()
        if raw.startswith("<") and raw.endswith(">"):
            raw = raw[1:-1]
        parsed = urlsplit(raw)
        if parsed.scheme.lower() in {"http", "https", "mailto", "file", "vscode", "data"}:
            continue
        target = unquote(parsed.path).replace("\\", "/")
        if not target:
            continue
        candidate = (file.parent / target).resolve()
        try:
            candidate.relative_to(ROOT.resolve())
        except ValueError:
            missing.append((file.relative_to(ROOT).as_posix(), raw, "target escapes repository"))
            continue
        if not candidate.exists():
            missing.append((file.relative_to(ROOT).as_posix(), raw, "target missing"))

print(f"Markdown files: {len(files)}; missing/unsafe local targets: {len(missing)}")
for source, target, reason in missing:
    print(f"{source}: {target} ({reason})")
if missing:
    raise SystemExit(1)
