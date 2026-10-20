#!/usr/bin/env python3
"""Verify proposed common-knowledge links (work/common/proposed-*.jsonl) against Wikipedia, then write the survivors as
cited relations to kb/inbox/zz-common.jsonl. A link is kept only if the named article (fetched via the MediaWiki API,
cached in work/common/wiki/) mentions the other entity by name or alias. Failures go to work/common/rejected.txt."""
import json, glob, os, re, time, unicodedata, urllib.error, urllib.parse, urllib.request

ROOT = '/home/rmiller/podscribe/map'
WIKI = f'{ROOT}/work/common/wiki'
os.makedirs(WIKI, exist_ok=True)
UA = {'User-Agent': 'marathon-men-map/1.0 (personal research page; link verification)'}
ents = {e['id']: e for e in json.load(open(f'{ROOT}/kb/entities.json'))}
events = {v['id']: v for v in json.load(open(f'{ROOT}/kb/events.json'))}
aliases = json.load(open(f'{ROOT}/kb/aliases.json'))

def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()

def names(i):
    """Ways an article might name this entity: name, aliases, the part before a comma or parenthesis, a person's surname."""
    e = ents.get(i) or {}
    v = events.get(i) or {}
    out = {e.get('name') or v.get('title') or ''} | set(e.get('aliases') or []) | set(v.get('aliases') or [])
    for n in list(out):
        out.add(re.split(r'[,(]', n)[0])
        out.add(n.replace('U.S. ', 'United States ').replace('U.S.', 'United States'))
    if e.get('type') == 'person' and e.get('name'):
        parts = re.sub(r'\(.*?\)', '', e['name']).split()
        if len(parts) >= 2 and len(parts[-1]) >= 4: out.add(parts[-1])
    return {norm(n) for n in out if len(norm(n)) >= 3}

def article(title):
    path = f'{WIKI}/{re.sub(r"[^A-Za-z0-9]+", "_", title)[:120]}.json'
    if not os.path.exists(path):
        q = urllib.parse.urlencode({'action': 'query', 'prop': 'extracts|info', 'explaintext': 1, 'inprop': 'url',
                                    'titles': title, 'format': 'json', 'redirects': 1})
        req = urllib.request.Request(f'https://en.wikipedia.org/w/api.php?{q}', headers=UA)
        for attempt in range(6):   # Wikipedia rate-limits bursts: back off and retry
            try:
                with urllib.request.urlopen(req, timeout=60) as r: data = json.load(r)
                break
            except urllib.error.HTTPError as ex:
                if ex.code != 429 or attempt == 5: raise
                time.sleep(5 * 2 ** attempt)
        json.dump(data, open(path, 'w'))
        time.sleep(1.0)
    page = next(iter(json.load(open(path))['query']['pages'].values()))
    if 'missing' in page: return None, None, None
    return page.get('title'), page.get('fullurl'), norm(page.get('extract') or '')

props = [json.loads(l) for f in sorted(glob.glob(f'{ROOT}/work/common/proposed-*.jsonl')) for l in open(f) if l.strip()]
# links this script added on an earlier run are in relations.json too; don't let them count as "already linked"
OUT = f'{ROOT}/kb/inbox/zz-common.jsonl'
mine = {json.loads(l)['id'] for l in open(OUT) if '"relation"' in l} if os.path.exists(OUT) else set()
have = {frozenset((r['from'], r['to'])) for r in json.load(open(f'{ROOT}/kb/relations.json')) if r['id'] not in mine}
kept, rejected, sources = [], [], {}
for p in props:
    a, b = aliases.get(p['from'], p['from']), aliases.get(p['to'], p['to'])
    if a not in ents and a not in events or b not in ents and b not in events or a == b:
        rejected.append((p, 'unknown id')); continue
    if frozenset((a, b)) in have:
        rejected.append((p, 'already linked')); continue
    try:
        title, url, text = article(p['wiki'])
    except Exception as ex:
        rejected.append((p, f'fetch failed: {ex}')); continue
    if not text:
        rejected.append((p, 'no such article')); continue
    other = b if p.get('wiki_side', 'from') == 'from' else a
    # self-evident containment: one name includes the other ("FBI Boston field office" part_of "FBI")
    contained = p['kind'] in ('part_of', 'located_in') and any(re.search(r'\b' + re.escape(n) + r'\b', x)
                    for n in names(b) for x in names(a))
    if not contained and not any(re.search(r'\b' + re.escape(n) + r'\b', text) for n in names(other)):
        rejected.append((p, f'article "{title}" does not name {other}')); continue
    sid = 'src-wikipedia-' + re.sub(r'[^a-z0-9]+', '-', norm(title)).strip('-')
    sources[sid] = {'op': 'source', 'id': sid, 'title': f'{title} (Wikipedia)', 'publisher': 'Wikipedia', 'author': '', 'date': '',
                    'url': url, 'tier': 'C', 'notes': 'Opened 2026-10-20 by script; used for common-knowledge links (the article names both ends).'}
    have.add(frozenset((a, b)))
    kept.append({'op': 'relation', 'id': f'rel-{a}--{p["kind"]}--{b}', 'from': a, 'to': b, 'kind': p['kind'], 'label': p['label'],
                 'start': '', 'end': '', 'claim_ids': [], 'source_ids': [sid], 'common_knowledge': True})

with open(OUT, 'w') as f:
    for o in list(sources.values()) + kept: f.write(json.dumps(o) + '\n')
with open(f'{ROOT}/work/common/rejected.txt', 'w') as f:
    for p, why in rejected: f.write(f'{why} | {p["from"]} -{p["kind"]}-> {p["to"]} ({p.get("wiki")})\n')
print(f'proposed {len(props)}  kept {len(kept)}  rejected {len(rejected)}  articles {len(sources)}')
