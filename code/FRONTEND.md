# Front-end spec: Marathon Men map

Build ONE self-contained HTML file: `/mnt/c/Users/mille/transcripts/scripts/marathon-men-map.html`.
Data: embed `/home/rmiller/podscribe/map/work/site-data.json` verbatim inside `<script type="application/json" id="data">`
(a build step `build_page.py` does the embedding; the page reads it with JSON.parse). Do not hand-copy data into the page.
Read INSTRUCTIONS.md section 7 for the original brief; this file is the authoritative spec.

## Must work well on BOTH desktop and phone (user requirement)
- Phone (360–430 px wide): single column, 16 px side gutters, no horizontal page scroll, tap targets ≥ 44 px,
  bottom tab bar (6 tabs, icon + short label) or a scrollable top tab strip; the detail panel opens as a full-height
  bottom sheet with a clear close button and back-button support (history state).
- Desktop (≥ 1024 px): top tab bar; Web and Map views use the full viewport with the detail panel as a right-side
  drawer (~400 px) that does not cover the graph; tables use the width (more columns visible).
- Tablet in between: sensible fallbacks. Test at 411×839 (the user's phone: 1440×2938 px at DPR 3.5), 375×812, 768×1024 and 1440×900 before declaring done.
- Light and dark themes (prefers-color-scheme), color tokens on :root. Body has an explicit background.
- Fast: lazy-init the graph/map only when their tab is first opened; graph physics stabilizes then stops.

## Libraries (cdnjs only, exact pinned versions)
- vis-network 9.1.9 (`https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/standalone/umd/vis-network.min.js`)
- Leaflet 1.9.4 (css + js from cdnjs), OpenStreetMap tiles.
- No other dependencies. No framework needed.

## Status system (same colors and badges everywhere; legend visible on every view, collapsible on phone)
| status | look |
|---|---|
| ESTABLISHED | solid green badge |
| REPORTED | solid blue badge |
| DISPUTED | amber badge, half-filled icon |
| CONTRADICTED | red badge, strike-through icon |
| PODCAST-ONLY | grey outline badge, microphone icon |
| SPECULATION | purple DASHED outline badge, italic text, "?" icon |
Speculation must look different from established fact at a glance (dashed + italic). Meet WCAG AA contrast in both themes.
Source tiers A–D get small square chips (A darkest).

## Views (tabs)
1. **Start here**: 2-minute read. "How to read this" (3 lines), "Last built" date (data.built), status legend.
   "The official story": the `data.official` claims in order (strip the "Official story N:" prefix), each with its badge.
   "What the episodes add": `data.bombshells` in order, one line each with status badge, score dots (0–5) and a tap-through
   to the claim detail. Counts strip (claims by status, entities, sources).
2. **Web**: vis-network graph of entities (color by type, shape by type), edges styled by relation kind group
   (family = solid thick; informant_for/investigated/killed = red dashed; employed_by/member_of/funded = solid thin;
   met/friend_of/roommate_of = dotted; other = thin grey). Filters: episode (220/221/223), cluster (data.clusters),
   claim status, and a toggle "Official story only" (entities/relations with off=true) vs "Everything".
   Search box (matches name + aliases, case/diacritic-insensitive) that focuses the node. Default view should not be a
   hairball: start with nodes having nclaims ≥ 3 plus their links, with a "show all" control. Tap a node → detail panel.
3. **Timeline**: swimlanes per cluster, horizontal on desktop (zoom/pan with buttons and wheel/pinch), vertical list
   grouped by year on phone. Each item shows date precision (day / month / year / approx as "~") and its status mix.
   Tap → event detail (claims, place, participants, sources). Range roughly 1986–2026.
4. **Map**: Leaflet pins for entities of type place with lat/lon; pin style by geo precision (exact/street solid,
   city hollow, region/country large faint circle). Tap → what happened there (events with place = this id, claims
   about it) with dates. Fit to Boston area by default with a "World" button (Dagestan, Kyrgyzstan, Orlando, D.C.).
5. **Claims**: searchable, filterable table (status, cluster, episode, speaker, min score). Desktop: table with columns
   status | claim | said by | episode link | sources. Phone: cards. Sort by score or by episode time.
6. **Sources**: list with tier chip, publisher, date, link (opens new tab), how many claims cite it, verified mark.

## Detail panel (node / event / claim)
- Entity: name, type, aliases, summary, clusters, episodes; its relations (tap to jump); every claim about it grouped
  by status with badges; sources.
- Claim: text with badge and score; "said by"; each podcast ref as a quote + "▶ Listen at 1:02:31" link to
  `https://open.spotify.com/episode/<data.spotify[ep]>?t=<t>` (open in new tab); evidence for / against with source
  title, tier chip, note, link; research note; slip / joke-risk flags shown as small notes.
- Real-people rule: never display anything not in the data; accusations appear only as claims with their status.

## Accessibility & polish
- Keyboard navigable tabs and panel (Esc closes). Visible focus. aria-labels on icon buttons.
- URL hash deep links: `#claim=<id>`, `#node=<id>`, `#tab=<name>` so a claim can be shared.
- Title: "Marathon Men Map". Footer: "Built <date> from TrueAnon eps 220/221/223 + sources; every item cites a timestamp or a source."
