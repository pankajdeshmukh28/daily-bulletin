"""Build the publishable dashboard.html: pulls fresh data from Turso and
substitutes it into scripts/dashboard_template.html.

    .venv/bin/python scripts/render_dashboard.py
    # -> writes dashboard.html next to the template; publish that file.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_dashboard_data import build

HERE = Path(__file__).resolve().parent


def main():
    data = build()
    # Escape "</script" so a stray occurrence in thesis text can't break out
    # of the embedding <script type="application/json"> tag.
    payload = json.dumps(data, default=str).replace("</script", "<\\/script")
    template = (HERE / "dashboard_template.html").read_text()
    if "__DASHBOARD_DATA__" not in template:
        raise RuntimeError("template missing __DASHBOARD_DATA__ placeholder")
    out = template.replace("__DASHBOARD_DATA__", payload)
    out_path = HERE / "dashboard.html"
    out_path.write_text(out)
    print(f"wrote {out_path} ({len(out)} bytes, generated_at={data['generated_at']})")


if __name__ == "__main__":
    main()
