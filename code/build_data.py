#!/usr/bin/env python3
"""Build the page's embedded data (work/site-data.json) and the reusable KB export
(/mnt/c/Users/mille/transcripts/scripts/marathon-men-kb.json) from the canonical kb/*.json.
Deterministic: no network, no agents. Run after merge.py."""
import json, re, datetime, collections, os

ROOT = '/home/rmiller/podscribe/map'
OUT_KB = '/mnt/c/Users/mille/transcripts/scripts/marathon-men-kb.json'
kb = lambda n: json.load(open(f'{ROOT}/kb/{n}.json'))
ents, rels, evs, claims, srcs, queue = (kb(n) for n in ['entities', 'relations', 'events', 'claims', 'sources', 'queue'])
# ranked claim ids for the "What the episodes add" list, chosen by the lead after verification
BOMBS = f'{ROOT}/work/bombshells.json'
curated = json.load(open(BOMBS)) if os.path.exists(BOMBS) else []

SPOTIFY = {220: '5H4vhwj5Et8xOqjibGjyzI', 221: '4K6BXGfHqmkm90pMas3tT5', 223: '6A2gd9ROULkcZebWQOaLKf'}
CLUSTERS = {
  'c0': 'Official story & background', 'c1': 'FBI informants & the FBI–Tamerlan contact', 'c2': 'FSB warning, watchlists & oversight',
  'c3': '2012 Dagestan trip', 'c4': 'Uncle Ruslan, Fuller & the family network', 'c5': 'Waltham murders & Todashev',
  'c6': 'Bombing day to the boat', 'c7': 'Morley, the gun & Run This Town', 'c8': 'Friends, Katherine Russell & the interrogation',
  'c9': 'Trial & appeals', 'c10': 'Media & books', 'c11': 'Drug "meta-group" theory',
}
STATUS_RANK = {'ESTABLISHED': 0, 'REPORTED': 1, 'DISPUTED': 2, 'CONTRADICTED': 3, 'PODCAST-ONLY': 4, 'SPECULATION': 5}
clusters_of = lambda tags: sorted({t for t in (tags or []) if re.fullmatch(r'c\d+', t)}, key=lambda t: int(t[1:]))
src_ids = {s['id'] for s in srcs}

def cited(c):
    return bool(c.get('podcast_refs')) or any(e.get('source_id') in src_ids for e in (c.get('evidence_for') or []) + (c.get('evidence_against') or []))

live = [c for c in claims if not c.get('retracted') and cited(c)]
dropped = [c['id'] for c in claims if not c.get('retracted') and not cited(c)]
cid = {c['id'] for c in live}

def ref(r):
    t = int(r.get('t_seconds') or 0)
    return {'ep': r.get('ep'), 't': t, 'sp': r.get('speaker') or '', 'q': r.get('quote') or ''}

C = []
for c in live:
    C.append({
        'id': c['id'], 'text': c['text'], 'st': c['status'], 'by': c.get('said_by') or '',
        'refs': [ref(r) for r in c.get('podcast_refs') or [] if r.get('ep') in SPOTIFY],
        'for': [{'s': e['source_id'], 'n': e.get('note') or ''} for e in c.get('evidence_for') or [] if e.get('source_id') in src_ids],
        'against': [{'s': e['source_id'], 'n': e.get('note') or ''} for e in c.get('evidence_against') or [] if e.get('source_id') in src_ids],
        'score': c.get('bombshell_score') or 0, 'why': c.get('why_it_matters') or '', 'about': c.get('about') or [],
        'cl': clusters_of(c.get('tags')), 'joke': c.get('joke_risk') or 'none', 'note': c.get('research_note') or '',
        'slip': 'slip' in (c.get('tags') or []), 'off': 'official-summary' in (c.get('tags') or []), 'th': c.get('theory_id') or '',
    })

# claims per entity/event, used for node clusters, episodes and the "official story" filter
about = collections.defaultdict(list)
for c in C:
    for a in c['about']: about[a].append(c)
official_status = ('ESTABLISHED', 'REPORTED')
def is_official(node_id, source_ids):
    return bool(source_ids) or any(c['st'] in official_status and c['for'] for c in about[node_id])

ent_ids = {e['id'] for e in ents}
# an entity with no claims or sources of its own still belongs on the page when a cited link names it
in_cited_rel = {x for r in rels if r.get('claim_ids') or r.get('source_ids') for x in (r['from'], r['to'])}
E = []
for e in ents:
    cs = about[e['id']]
    has_ref = bool(cs) or bool(e.get('podcast_refs')) or bool(e.get('source_ids')) or e['id'] in in_cited_rel
    if not has_ref: continue
    E.append({
        'id': e['id'], 'type': e['type'], 'name': e['name'], 'aliases': e.get('aliases') or [], 'summary': e.get('summary') or '',
        'cl': clusters_of(e.get('tags')) or sorted({k for c in cs for k in c['cl']}, key=lambda t: int(t[1:])),
        'eps': sorted({r['ep'] for c in cs for r in c['refs']} | set(e.get('episodes') or [])),
        'lat': e.get('lat'), 'lon': e.get('lon'), 'geo': e.get('geo_precision') or '', 'geonote': e.get('geo_note') or '',
        'src': [s for s in e.get('source_ids') or [] if s in src_ids], 'off': is_official(e['id'], e.get('source_ids')),
        'nclaims': len(cs), 'dates': e.get('dates') or {},
    })
MONTHS = 'January February March April May June July August September October November December'.split()
def pretty_date(d, prec):
    """'2015-03-04/2015-04-08' -> '4 March – 8 April 2015'; month/year precision kept; '~' for approximate."""
    if not d: return 'Date unknown'
    def one(x):
        p = x.split('-')
        if len(p) == 3: return f'{int(p[2])} {MONTHS[int(p[1]) - 1]} {p[0]}'
        if len(p) == 2: return f'{MONTHS[int(p[1]) - 1]} {p[0]}'
        return p[0]
    try:
        parts = [one(x.strip()) for x in d.split('/')]
    except (ValueError, IndexError):
        return d
    if len(parts) == 2 and parts[0].split()[-1] == parts[1].split()[-1]: parts[0] = ' '.join(parts[0].split()[:-1])
    return ('~' if prec == 'approx' else '') + ' – '.join(parts)

# every timeline event is also a graph node, so claims, places and people can link to it (the trial, jury selection, ...)
ent_set = {e['id'] for e in E}
for v in evs:
    if v['id'] in ent_set: continue
    cs = about[v['id']]
    cl = [x for x in v.get('claim_ids') or [] if x in cid]
    if not cs and not cl and not v.get('source_ids'): continue
    place = next((e['name'] for e in ents if e['id'] == v.get('place_id')), '')
    E.append({'id': v['id'], 'type': 'event', 'name': v['title'], 'aliases': v.get('aliases') or [],
              'summary': ' · '.join(x for x in [pretty_date(v.get('date'), v.get('precision')), place] if x),
              'cl': clusters_of(v.get('tags')) or sorted({k for c in cs for k in c['cl']}, key=lambda t: int(t[1:])),
              'eps': sorted({r['ep'] for c in cs for r in c['refs']}), 'lat': None, 'lon': None, 'geo': '', 'geonote': '',
              'src': [x for x in v.get('source_ids') or [] if x in src_ids], 'off': is_official(v['id'], v.get('source_ids')),
              'nclaims': max(len(cs), len(cl)), 'dates': {'active': v.get('date') or ''}})
node_ids = {e['id'] for e in E}

R = []
for r in rels:
    if r['from'] not in node_ids or r['to'] not in node_ids: continue
    cl = [x for x in r.get('claim_ids') or [] if x in cid]
    ss = [s for s in r.get('source_ids') or [] if s in src_ids]
    if not cl and not ss: continue
    st = min((STATUS_RANK[c['st']] for c in C if c['id'] in cl), default=0 if ss else 4)
    R.append({'st': [k for k, v in STATUS_RANK.items() if v == st][0], 'id': r['id'], 'from': r['from'], 'to': r['to'], 'kind': r['kind'], 'label': r.get('label') or r['kind'],
              'start': r.get('start') or '', 'end': r.get('end') or '', 'claims': cl, 'src': ss,
              'off': bool(ss) or any(c['st'] in official_status for c in C if c['id'] in cl)})

# Derived links, each backed by the claims or sources that justify it (the graph otherwise only shows relation records):
#  - an event node and the place it happened; an entity and the place it is located in
#  - two items named together in the same claims ("co"; w = number of shared claims)
import itertools
have = {frozenset((r['from'], r['to'])) for r in R}
ev_by_id = {v['id']: v for v in evs}
for e in ents:
    if e['id'] not in node_ids: continue
    v = ev_by_id.get(e['id'])
    places = ([v['place_id']] if v and v.get('place_id') else []) + (e.get('location_ids') or [])
    for pl in places:
        if pl in node_ids and pl != e['id'] and frozenset((e['id'], pl)) not in have:
            have.add(frozenset((e['id'], pl)))
            cl = [x for x in ((v or {}).get('claim_ids') or []) if x in cid][:12]
            ss = [x for x in ((v or {}).get('source_ids') or []) + (e.get('source_ids') or []) if x in src_ids][:6]
            if not cl: cl = [c['id'] for c in about[e['id']] if pl in c['about']][:12]
            if cl or ss:
                R.append({'id': f'drv-{e["id"]}--at--{pl}', 'from': e['id'], 'to': pl, 'kind': 'took_place_at' if v else 'located_in',
                          'label': 'took place at' if v else 'located in', 'start': '', 'end': '', 'claims': cl, 'src': ss, 'off': bool(ss), 'derived': True})
for v in evs:
    if v['id'] not in node_ids: continue
    for who in v.get('participants') or []:
        if who in node_ids and frozenset((who, v['id'])) not in have:
            have.add(frozenset((who, v['id'])))
            R.append({'id': f'drv-{who}--in--{v["id"]}', 'from': who, 'to': v['id'], 'kind': 'involved_in', 'label': 'named in this event',
                      'start': '', 'end': '', 'claims': [x for x in v.get('claim_ids') or [] if x in cid][:12],
                      'src': [x for x in v.get('source_ids') or [] if x in src_ids][:6], 'off': bool(v.get('source_ids')), 'derived': True})

# every link carries the strongest status among the claims behind it (a sourced link with no claims counts as established)
cst = {c['id']: c['st'] for c in C}
for r in R:
    if 'st' not in r:
        ranks = [STATUS_RANK[cst[x]] for x in r['claims'] if x in cst]
        r['st'] = min(ranks, key=lambda v: v) if ranks else (0 if r['src'] else 4)
        r['st'] = [k for k, v in STATUS_RANK.items() if v == r['st']][0]

def parse_date(d):
    """'2013-04-15' | '2013-04' | '2013' | 'a/b' -> (start, end) ISO day strings, or None."""
    if not d: return None
    parts = d.split('/')
    def lo(p):
        p = p.strip(); m = re.fullmatch(r'(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?', p)
        if not m: return None
        return f"{m[1]}-{m[2] or '01'}-{m[3] or '01'}"
    def hi(p):
        p = p.strip(); m = re.fullmatch(r'(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?', p)
        if not m: return None
        if m[3]: return p
        if m[2]: return f"{m[1]}-{m[2]}-28"
        return f"{m[1]}-12-31"
    a = lo(parts[0]); b = hi(parts[-1])
    return (a, b) if a and b else None

V, undated = [], []
for v in evs:
    cl = [x for x in v.get('claim_ids') or [] if x in cid] + [c['id'] for c in about[v['id']] if c['id'] not in (v.get('claim_ids') or [])]
    ss = [s for s in v.get('source_ids') or [] if s in src_ids]
    if not cl and not ss: continue
    rng = parse_date(v.get('date') or '')
    if not rng: undated.append(v['id']); continue
    clus = clusters_of(v.get('tags')) or sorted({k for c in C if c['id'] in cl for k in c['cl']}, key=lambda t: int(t[1:]))
    V.append({'id': v['id'], 'title': v['title'], 'date': v['date'], 'start': rng[0], 'end': rng[1], 'prec': v.get('precision') or 'approx',
              'place': v.get('place_id') if v.get('place_id') in node_ids else '', 'who': [p for p in v.get('participants') or [] if p in node_ids],
              'claims': cl, 'src': ss, 'cl': clus or ['c0'], 'note': v.get('date_note') or '',
              'off': bool(ss) or any(c['st'] in official_status for c in C if c['id'] in cl)})
V.sort(key=lambda v: v['start'])

# researched theories (work/factcheck/theories-researched-*.json): the debate around each speculation, shown on its claims
import glob
TH = []
for f in sorted(glob.glob(f'{ROOT}/work/factcheck/theories-researched-*.json')):
    for t in json.load(open(f)):
        keep = lambda L: [x for x in (L or []) if x.get('source_id') in src_ids]
        TH.append({'id': t['id'], 'title': t.get('title', ''), 'verdict': t.get('verdict', ''), 'status': t.get('status', 'SPECULATION'),
                   'premises': [{'text': x.get('text', ''), 'finding': x.get('finding', 'unclear'), 's': x.get('source_id') if x.get('source_id') in src_ids else '', 'n': x.get('note', '')} for x in t.get('premises') or []],
                   'pro': [{'who': x.get('who', ''), 'claim': x.get('claim', ''), 's': x['source_id'], 'tier': x.get('tier', '')} for x in keep(t.get('proponents'))],
                   'for': [{'s': x['source_id'], 'n': x.get('note', '')} for x in keep(t.get('evidence_for'))],
                   'against': [{'s': x['source_id'], 'n': x.get('note', '')} for x in keep(t.get('evidence_against'))],
                   'official': [{'s': x['source_id'], 'n': x.get('note', '')} for x in keep(t.get('official'))]})
th_src = {x['s'] for t in TH for k in ('pro', 'for', 'against', 'official') for x in t[k]} | {x['s'] for t in TH for x in t['premises'] if x['s']}
used_src = th_src | {s for c in C for e in c['for'] + c['against'] for s in [e['s']]} | {s for e in E for s in e['src']} | {s for v in V for s in v['src']} | {s for r in R for s in r['src']}
S = [{'id': s['id'], 'title': s.get('title') or '', 'pub': s.get('publisher') or '', 'author': s.get('author') or '', 'date': s.get('date') or '',
      'url': s.get('url') or '', 'tier': s.get('tier') or 'D', 'notes': s.get('notes') or '', 'verified': s.get('verified'),
      'n': sum(1 for c in C for e in c['for'] + c['against'] if e['s'] == s['id'])}
     for s in srcs if s['id'] in used_src]

counts = {
  'claims_by_status': dict(collections.Counter(c['st'] for c in C)), 'entities_by_type': dict(collections.Counter(e['type'] for e in E)),
  'sources_by_tier': dict(collections.Counter(s['tier'] for s in S)), 'events': len(V), 'relations': len(R),
  'open_questions': sum(1 for q in queue if q.get('status') in (None, '', 'open')),
}
site = {
  'built': datetime.date.today().isoformat(), 'spotify': SPOTIFY, 'clusters': CLUSTERS, 'counts': counts,
  'official': [c['id'] for c in sorted((c for c in C if c['off']), key=lambda c: c['id'])],
  'bombshells': [b for b in curated if b in cid],
  'entities': E, 'relations': R, 'events': V, 'claims': C, 'sources': S, 'theories': TH,
}
if os.path.exists(f'{ROOT}/work/basemap.json'):  # vector basemap from basemap.py (tiles are blocked in the Artifact viewer)
    site['base'] = json.load(open(f'{ROOT}/work/basemap.json'))
if os.path.exists(f'{ROOT}/work/photos.json'):  # freely licensed lead photos from photos.py; files are published next to the page
    ids = {e['id'] for e in E} | {v['id'] for v in V}
    site['photos'] = {k: v for k, v in json.load(open(f'{ROOT}/work/photos.json')).items() if k in ids}
if os.path.exists(f'{ROOT}/work/conclusions.json'):  # the Findings tab: hand-written analysis whose evidence ids must all exist
    site['conclusions'] = json.load(open(f'{ROOT}/work/conclusions.json'))
    known = cid | {e['id'] for e in E} | {v['id'] for v in V} | {t['id'] for t in TH}
    gone = [r for lv in site['conclusions']['levels'] for it in lv['items'] for r in it['refs'] if r not in known]
    if gone: print('conclusions cite ids no longer on the page:', gone)
if os.path.exists(f'{ROOT}/work/memorial.json'):  # the Start page's 'In memory' section: names and summaries come from the entities
    site['memorial'] = json.load(open(f'{ROOT}/work/memorial.json'))
    gone = [i for g in site['memorial']['groups'] for i in g['ids'] + [g.get('event')] if i and i not in {e['id'] for e in E} | {v['id'] for v in V}]
    if gone: print('memorial names ids no longer on the page:', gone)
TX = '/mnt/c/Users/mille/transcripts/scripts/TrueAnon {} Marathon Men (Part {}).txt'
site['tx'] = {}  # the episode transcripts, for the page's transcript reader: [[start second, speaker, text], ...]
for ep, part in ((220, 1), (221, 2), (223, 3)):
    turns = []
    for m in re.finditer(r'^([A-Z][A-Z .\'-]+?)  \[(\d+(?::\d\d){1,2})\]\n(.*?)(?=\n\n[A-Z][A-Z .\'-]+?  \[|\Z)', open(TX.format(ep, part)).read(), re.M | re.S):
        t = 0
        for x in m[2].split(':'): t = t * 60 + int(x)
        turns.append([t, m[1].title(), re.sub(r'\s*\n\s*', ' ', m[3]).strip()])
    site['tx'][ep] = turns
json.dump(site, open(f'{ROOT}/work/site-data.json', 'w'), ensure_ascii=False, separators=(',', ':'))
json.dump({'built': site['built'], 'entities': ents, 'relations': rels, 'events': evs, 'claims': claims, 'sources': srcs, 'queue': queue},
          open(OUT_KB, 'w'), ensure_ascii=False, indent=1)

print(json.dumps(counts, indent=1))
print(f'nodes {len(E)}  edges {len(R)}  timeline {len(V)} (undated, left off: {len(undated)})  sources {len(S)}  bombshells {len(site["bombshells"])}')
print(f'claims dropped for having no citation: {len(dropped)}')
missing = [b for b in curated if b not in cid]
if missing: print('curated bombshells not found:', missing)
