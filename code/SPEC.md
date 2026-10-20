# Marathon Men map: shared spec for every agent

Project root: `/home/rmiller/podscribe/map/`. Full brief: `INSTRUCTIONS.md` (read sections 3 and 4 at least).
Name spellings: `STYLE_SHEET.md` (canonical; record variants as `aliases`).

## Files
- `kb/inbox/<agent-name>.jsonl`: YOUR ONLY WRITE TARGET in kb/ (append, one JSON object per line). Never edit
  another agent's inbox or the canonical files (unless you are the Curator).
- Canonical (Curator only): `kb/entities.json`, `kb/relations.json`, `kb/events.json`, `kb/claims.json`,
  `kb/sources.json`, `kb/aliases.json` (alias/duplicate id -> canonical id), `kb/queue.json`.
- Transcript halves with turn numbers and seconds: `work/ep220a.txt` … `work/ep223b.txt`
  (header lines look like `[ep220 turn 12 t=754s (0:12:34) Brace]`). Full JSON: `/home/rmiller/podscribe/work/ep2xx/edited.json`.
- Read the canonical files + `kb/queue.json` before you start, and reuse existing IDs (check `kb/aliases.json`).
  Use `jq`/python to search them rather than reading huge files whole.

## Inbox record format (every line has an `op`)
```
{"op":"entity","id":"person-tamerlan-tsarnaev","type":"person|org|place|event|document|media|object","name":"...",
 "aliases":[],"summary":"neutral 1-3 sentences, no accusations","dates":{"born":"","died":"","active":""},
 "location_ids":[],"tags":["c5"],"episodes":[220],"lat":null,"lon":null,"source_ids":[],"podcast_refs":[...]}
{"op":"relation","id":"rel-<from>--<kind>--<to>","from":"<entity id>","to":"<entity id>","kind":"family|met|employed_by|informant_for|investigated|owned|attended|killed|funded|member_of|lived_at|friend_of|roommate_of|represented|prosecuted|judged|wrote_about|located_in|...",
 "label":"short human label","start":"","end":"","claim_ids":[],"source_ids":[]}
{"op":"event","id":"event-<slug>-<year>","title":"...","date":"2011-09-11 | 2011-09 | 2011 | 2011-09-11/2011-09-12","precision":"day|month|year|approx",
 "place_id":"place-...","participants":[],"claim_ids":[],"source_ids":[],"tags":["c5"],"date_note":"conflicts etc."}
{"op":"claim","id":"claim-<ep>-<t_seconds>-<slug>" (podcast) or "claim-src-<slug>" (outside),"text":"one checkable statement",
 "status":"ESTABLISHED|REPORTED|DISPUTED|PODCAST-ONLY|SPECULATION|CONTRADICTED","said_by":"Brace|Liz|Ben|Howie|GUEST|<source id>",
 "podcast_refs":[{"ep":220,"t_seconds":754,"speaker":"Liz","quote":"exact words from transcript, <=40 words"}],
 "evidence_for":[{"source_id":"src-...","note":"what it says, with page/section"}],"evidence_against":[...],
 "bombshell_score":0-5,"why_it_matters":"...","about":["<entity/event ids>"],"tags":["c5"],"joke_risk":"none|low|high"}
{"op":"source","id":"src-<publisher>-<slug>","title":"","publisher":"","author":"","date":"","url":"","tier":"A|B|C|D","notes":""}
{"op":"update_claim","id":"<existing claim id>","set":{"status":"..."},"add_evidence_for":[...],"add_evidence_against":[...],"note":"why"}
{"op":"update_entity","id":"<existing id>","set":{...},"add_aliases":[]}
{"op":"lead","cluster":"c1..c12 or new","text":"what to research and why","refs":[...]}
{"op":"conflict","ids":[...],"text":"what conflicts"}
```

## Rules (short form; INSTRUCTIONS.md section 3 is authoritative)
- Every claim cites: podcast ref (ep + t_seconds + speaker + quote) and/or a source with a URL. No citation, no claim.
- Status from the podcast alone is PODCAST-ONLY (stated as fact) or SPECULATION (theory/inference). Only outside
  sources can raise it to REPORTED/ESTABLISHED/DISPUTED/CONTRADICTED. D-tier alone never reaches REPORTED/ESTABLISHED.
- Tiers: A court/official record · B major outlet or published book · C regional/independent journalism · D blogs/forums/social/fringe.
- Never invent dates, URLs, places. Leave empty and say so. Only cite URLs you actually loaded or that a search result
  showed you; note in `notes` if you only saw a snippet.
- Jokes/bits/sarcasm are not claims. Speaker factual slips get a claim noting the slip (tag `slip`), not new lore.
- Victims named respectfully. Private uncharged people: no addresses/contacts, no guilt beyond sources; accusations live in claims only.
- bombshell_score: 0 background · 1-2 minor detail · 3 notable, absent from the usual account · 4 major new angle · 5 central "crazy new lore".
- GUEST speaker = Ben or Howie (unidentified); keep "GUEST" unless the text makes it certain.

## Clusters (tags)
c0 official story/background · c1 FBI informants & entrapment context, FBI contact with Tamerlan · c2 FSB warning, TIDE/TECS, IG report, hearings ·
c3 2012 Dagestan trip, Plotnikov, Nidal, Kartashov/Union of the Just, Jamestown/Fund for the Caucasus ·
c4 Ruslan Tsarni, CCIO, Graham Fuller, USAID contractors, Daniloffs, Baiev, Herlihy, 410 Norfolk St, Lipson, family ·
c5 Waltham 2011 murders, Madarati, drugs/informant angle, Todashev killing, Miraliev ·
c6 bombing day, JFK Library fire, Saudi student, Collier, Dun Meng, Watertown, boat, Boston Strong ·
c7 Morley case, the gun's path, Silva, Sagai, Wai Kru · c8 friends, Katherine Russell, hospital interrogation/Miranda ·
c9 trial & appeals · c10 media & books · c11+ new clusters (add via `lead`).
