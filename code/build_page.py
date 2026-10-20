#!/usr/bin/env python3
"""Build the single-file Marathon Men map page.

Reads page/template.html and work/site-data.json, escapes "</" in the JSON so it cannot close the
<script> tag, substitutes __DATA__, and writes the page next to the transcripts.
Dev convenience: if the template still contains /*__APP_JS__*/ or /*__LEAFLET_CSS__*/ markers and
page/app.js or page/leaflet.css exist, those are inlined too.
"""
import json, pathlib, shutil, sys

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATE = HERE / "page" / "template.html"
DATA = HERE / "work" / "site-data.json"
OUT = pathlib.Path("/mnt/c/Users/mille/transcripts/scripts/marathon-men-map.html")


def main() -> int:
    html = TEMPLATE.read_text(encoding="utf-8")
    for marker, name in (("/*__APP_JS__*/", "app.js"), ("/*__LEAFLET_CSS__*/", "leaflet.css")):
        f = HERE / "page" / name
        if marker in html and f.exists():
            html = html.replace(marker, f.read_text(encoding="utf-8").replace("</script", "<\\/script"))
    raw = DATA.read_text(encoding="utf-8")
    json.loads(raw)  # fail early if the data is not valid JSON
    payload = raw.replace("</", "<\\/")
    if "__DATA__" not in html:
        print("template has no __DATA__ placeholder", file=sys.stderr)
        return 1
    html = html.replace("__DATA__", payload, 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    # photos referenced by the data live in img/ next to the page
    photos = json.loads(raw).get("photos") or {}
    if photos:
        dst = OUT.parent / "img"
        dst.mkdir(exist_ok=True)
        for v in photos.values():
            shutil.copy2(HERE / "page" / v["file"], dst / pathlib.Path(v["file"]).name)
        print(f"copied {len(photos)} photos to {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
