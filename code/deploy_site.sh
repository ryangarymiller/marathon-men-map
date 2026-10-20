#!/bin/bash
# Publish the built map to GitHub Pages: copies the page (as index.html) and its photos into site/, commits and pushes.
# The site is public but asks search engines not to index it (robots meta tag in the page + robots.txt here).
set -euo pipefail
MAP=/home/rmiller/podscribe/map
OUT=/mnt/c/Users/mille/transcripts/scripts
SITE=$MAP/site
mkdir -p "$SITE/img"
cp "$MAP/work/site-index.html" "$SITE/index.html"   # same page minus the embedded vector basemap
rsync -a --delete "$OUT/img/" "$SITE/img/"
printf 'User-agent: *\nDisallow: /\n' > "$SITE/robots.txt"
# raw files: episode transcripts, the knowledge-base export and the pipeline code (user asked for all three on the site)
mkdir -p "$SITE/transcripts" "$SITE/data" "$SITE/code/page"
cp "$MAP/work/basemap-site.json" "$SITE/data/basemap.json"   # fetched only if street tiles fail
T="$OUT/TrueAnon"
cp "$T 220 Marathon Men (Part 1).txt" "$SITE/transcripts/ep220-marathon-men-part-1.txt"
cp "$T 221 Marathon Men (Part 2).txt" "$SITE/transcripts/ep221-marathon-men-part-2.txt"
cp "$T 223 Marathon Men (Part 3).txt" "$SITE/transcripts/ep223-marathon-men-part-3.txt"
cp "$T Marathon Men - complete series.txt" "$SITE/transcripts/marathon-men-complete-series.txt"
cp "$T 220 Marathon Men (Part 1).pdf" "$SITE/transcripts/ep220-marathon-men-part-1.pdf"
cp "$T 221 Marathon Men (Part 2).pdf" "$SITE/transcripts/ep221-marathon-men-part-2.pdf"
cp "$T 223 Marathon Men (Part 3).pdf" "$SITE/transcripts/ep223-marathon-men-part-3.pdf"
cp "$T 220 Marathon Men (Part 1) - sample 15-25 min.pdf" "$SITE/transcripts/ep220-sample-15-25-min.pdf"
cp "$OUT/marathon-men-kb.json" "$SITE/data/marathon-men-kb.json"
cp "$MAP"/{merge,build_data,build_page,basemap,verify_common,photos}.py "$MAP/deploy_site.sh" "$MAP"/{INSTRUCTIONS,SPEC,STYLE_SHEET,FRONTEND}.md "$SITE/code/"
cp "$MAP/page/template.html" "$SITE/code/page/template.html"
touch "$SITE/.nojekyll"
cd "$SITE"
git add -A
if git diff --cached --quiet; then echo "nothing to deploy"; exit 0; fi
git commit -q -m "Update map ($(date +%F))" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018fFNhpDPR2GDYHPUykn4PK"
git push -q origin main
echo "deployed: $(git log -1 --format=%h)"
