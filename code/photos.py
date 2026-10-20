#!/usr/bin/env python3
"""Find a freely licensed lead photo for map items that have their own Wikipedia article, download a small thumbnail to
page/img/, and record the credit in work/photos.json (id -> file, Commons page, author, licence, article).

An item gets a photo only when its own article is found: the article title must match the item's name or an alias, it
must not be a disambiguation page, and its intro must share at least two distinctive words with the item's summary (so
'Ed Davis' the police commissioner doesn't pick up a basketball player). Private people have no article, so they get
nothing. Victims and survivors are left out on purpose (EXCLUDE). Review work/photos-review.txt after a run;
work/photos-reject.json pins ids that matched the wrong article. Wikipedia rate-limits single lookups hard, so titles go
50 to a request. Cache: work/photos-cache/."""
import json, os, re, time, unicodedata, urllib.error, urllib.parse, urllib.request

ROOT = '/home/rmiller/podscribe/map'
CACHE = f'{ROOT}/work/photos-cache'
IMG = f'{ROOT}/page/img'
os.makedirs(CACHE, exist_ok=True); os.makedirs(IMG, exist_ok=True)
UA = {'User-Agent': 'marathon-men-map/1.0 (personal research page; photo credits kept)'}
TYPES = {'person', 'place', 'org', 'event', 'media'}
EXCLUDE = {  # victims and survivors of the bombing, Collier, the Waltham murders and Watertown
    'person-krystle-campbell', 'person-lingzi-lu', 'person-martin-richard', 'person-bill-richard', 'person-sean-collier',
    'person-jeff-bauman', 'person-dennis-simmonds', 'person-richard-donohue', 'person-brendan-mess', 'person-erik-weissman',
    'person-raphael-teken', 'person-dun-meng'}
REJECT = set(json.load(open(f'{ROOT}/work/photos-reject.json'))) if os.path.exists(f'{ROOT}/work/photos-reject.json') else set()
STOP = set('the a an of and or in on at to for by with from as is was were be been his her their its this that who which '
           'per said says also after before during into over about than not but one two three later first new former '
           'american united states boston massachusetts'.split())

def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()

def words(s): return {w for w in norm(s).split() if len(w) > 3 and w not in STOP}

def api(params, key):
    path = f'{CACHE}/{key}.json'
    if os.path.exists(path): return json.load(open(path))
    params = dict(params); host = params.pop('_host')
    body = urllib.parse.urlencode(dict(params, format='json', formatversion=2)).encode()
    for attempt in range(7):
        try:
            req = urllib.request.Request(f'https://{host}/w/api.php', data=body, headers=UA)  # POST: 50 titles overflow a URL
            with urllib.request.urlopen(req, timeout=90) as r: data = json.load(r)
            break
        except urllib.error.HTTPError as ex:
            if ex.code != 429 or attempt == 6: raise
            time.sleep(10 * 2 ** attempt)
    json.dump(data, open(path, 'w'))
    return data

def batch(titles, host, params, tag):
    """One API call per 50 titles (the API limit), cached per batch; returns {asked title: page}.
    Extracts come back for at most 20 pages per call, so those requests use batches of 20."""
    n = 20 if 'extracts' in params.get('prop', '') else 50
    out = {}
    for k in range(0, len(titles), n):
        chunk = titles[k:k + n]
        key = f'{tag}_{k // n}_{len(chunk)}_{sum(map(ord, "|".join(chunk))) % 10**8}'
        cont, pages, fix = {}, {}, {}
        while True:  # follow 'continue' so every page in the batch gets its extract and image
            d = api(dict(params, titles='|'.join(chunk), _host=host, **cont), key + ('_' + '_'.join(cont.values()) if cont else ''))
            q = d.get('query') or {}
            for m in (q.get('normalized') or []) + (q.get('redirects') or []): fix[m['from']] = m['to']
            for pg in q.get('pages') or []: pages.setdefault(pg['title'], {}).update({k2: v for k2, v in pg.items() if v not in (None, '')})
            if 'continue' not in d: break
            cont = {k2: str(v) for k2, v in d['continue'].items()}
            time.sleep(1.0)
        for t in chunk:
            u = t
            for _ in range(3): u = fix.get(u, u)
            if u in pages: out[t] = pages[u]
        time.sleep(1.0)
    return out

APARAMS = {'action': 'query', 'redirects': 1, 'prop': 'pageimages|extracts|pageprops|info', 'piprop': 'thumbnail|name',
           'pithumbsize': 240, 'pilicense': 'free', 'pilimit': 50, 'exintro': 1, 'explaintext': 1, 'exlimit': 20, 'inprop': 'url'}

site = json.load(open(f'{ROOT}/work/site-data.json'))
todo = []
for e in site['entities']:
    if e['type'] not in TYPES or e['id'] in EXCLUDE or e['id'] in REJECT: continue
    cands = [e['name']] + (e.get('aliases') or [])
    cands += [re.split(r'[,(]', n)[0].strip() for n in cands]
    todo.append((e, [c for c in dict.fromkeys(cands) if len(c) > 3 and '|' not in c]))
pages = batch(sorted({c for _, cs in todo for c in cs}), 'en.wikipedia.org', APARAMS, 'a')
picked = []
for e, cs in todo:
    for c in cs:
        p = pages.get(c)
        if not p or p.get('missing') or 'disambiguation' in (p.get('pageprops') or {}): continue
        shared = words(e.get('summary') or '') & words(p.get('extract') or '')
        if len(shared) >= 2 or (e['type'] == 'place' and norm(p['title']) == norm(c)):
            if 'thumbnail' in p: picked.append((e, p, sorted(shared)[:6]))
            break
files = batch(sorted({'File:' + p['pageimage'] for _, p, _ in picked}), 'commons.wikimedia.org',
              {'action': 'query', 'prop': 'imageinfo', 'iiprop': 'extmetadata|url'}, 'f')
out, review = {}, []
for e, page, why in picked:
    i = e['id']
    ii = ((files.get('File:' + page['pageimage']) or {}).get('imageinfo') or [{}])[0]
    em = ii.get('extmetadata') or {}
    clean = lambda k: re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', (em.get(k) or {}).get('value') or '')).strip()
    lic, artist = clean('LicenseShortName'), clean('Artist') or 'Unknown author'
    if not lic: continue
    ext = os.path.splitext(urllib.parse.urlparse(page['thumbnail']['source']).path)[1].lower() or '.jpg'  # the URL carries utm tracking params
    fn = f'{i}{ext}'
    if not os.path.exists(f'{IMG}/{fn}'):
        req = urllib.request.Request(page['thumbnail']['source'], headers=UA)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as r: open(f'{IMG}/{fn}', 'wb').write(r.read())
                break
            except urllib.error.HTTPError as ex:
                if ex.code != 429 or attempt == 4: raise
                time.sleep(5 * 2 ** attempt)
        time.sleep(0.5)
    out[i] = {'file': f'img/{fn}', 'w': page['thumbnail']['width'], 'h': page['thumbnail']['height'],
              'credit': f'{artist[:80]} · {lic}', 'page': ii.get('descriptionurl') or '', 'article': page.get('fullurl') or ''}
    review.append(f"{i:55} -> {page['title']:45} | {lic:14} | shared: {', '.join(why)}")

json.dump(out, open(f'{ROOT}/work/photos.json', 'w'), indent=1)
open(f'{ROOT}/work/photos-review.txt', 'w').write('\n'.join(review) + '\n')
size = sum(os.path.getsize(f'{IMG}/{os.path.basename(v["file"])}') for v in out.values())
print(f'candidates {len(todo)}  articles found {len(pages)}  photos {len(out)}  ({size // 1024} KB)  review: work/photos-review.txt')
