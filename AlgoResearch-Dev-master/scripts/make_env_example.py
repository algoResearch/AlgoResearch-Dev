#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / ".env"
DST = ROOT / ".env.example"

def truthy(s: str) -> bool:
    return s.strip().lower() in {"1", "true", "yes", "on"}

def placeholder(key: str, val: str) -> str:
    k = key.upper()
    if any(x in k for x in ("SECRET", "KEY", "PASSWORD", "TOKEN", "API_KEY")):
        return "CHANGEME"
    if k.endswith("_URL"):
        return "http://localhost/"
    if re.fullmatch(r".*(_USE_TLS|_USE_SSL|_EAGER|DEBUG|USE_INMEMORY_CHANNELS)$", k):
        return "1" if truthy(val) else "0"
    if k.endswith("_PORT") and val.strip().isdigit():
        return val.strip()
    return ""  # default to empty for everything else

# Parse lines like:
#   KEY=VAL
#   export KEY=VAL
#   KEY = "VAL"
LINE_RE = re.compile(
    r"""^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<val>.*?)\s*$"""
)

def main() -> int:
    # Allow optional path to .env (first arg)
    src = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else SRC
    dst = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else DST

    if not src.exists():
        print(f"ERROR: {src} not found", file=sys.stderr)
        return 1

    out_lines: list[str] = []
    for raw in src.read_text(encoding="utf-8").splitlines():
        # Preserve comments and blank lines verbatim
        if not raw.strip() or raw.lstrip().startswith("#"):
            out_lines.append(raw)
            continue

        m = LINE_RE.match(raw)
        if not m:
            # Keep unrecognized lines as-is (rare edge cases)
            out_lines.append(raw)
            continue

        key, val = m.group("key"), m.group("val")

        # Strip surrounding quotes if present to interpret booleans/ports
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val_eval = val[1:-1]
        else:
            val_eval = val

        out_lines.append(f"{key}={placeholder(key, val_eval)}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"Wrote {dst.relative_to(ROOT)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())