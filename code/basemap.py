#!/usr/bin/env python3
"""Build the inline vector basemap (work/basemap.json) for the page's Leaflet map.
The Artifact viewer blocks external images, so map tiles can't load there; these shapes and labels are embedded instead.
Sources (downloaded once into work/basemap-cache/):
  Natural Earth v5.1.2 (nvkelso/natural-earth-vector): countries 1:50m, states/provinces, populated places, lakes,
  rivers and roads 1:10m; OpenStreetMap via Overpass: Massachusetts town borders and names, eastern-Massachusetts
  coastline, highways and rivers, and Greater Boston ponds and river basins (boston-osm.json from the first version)."""
import json, os

ROOT = '/home/rmiller/podscribe/map'
CACHE = f'{ROOT}/work/basemap-cache'
ne = lambda n: json.load(open(f'{CACHE}/{n}.geojson'))['features']

# Where the story happens: the eastern US (Boston to Orlando and D.C.) and the Caucasus/Central Asia
# (Dagestan, Chechnya, Georgia, Kazakhstan, Kyrgyzstan, Ankara). Roads, rivers and dense labels are kept only here.
FOCUS = [(-90, 24, -66, 48), (26, 35, 82, 52)]
FOCUS_A3 = {'USA', 'RUS', 'KAZ', 'KGZ', 'GEO', 'AZE', 'ARM', 'UZB', 'TJK', 'TKM', 'TUR', 'CAN'}
in_focus = lambda lon, lat: any(a <= lon <= c and b <= lat <= d for a, b, c, d in FOCUS)

def rdp(pts, eps):
    """Ramer-Douglas-Peucker simplification on [lon, lat] points (iterative, so long lines can't hit the recursion limit)."""
    if len(pts) < 3: return pts
    keep = [False] * len(pts); keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        s, e = stack.pop()
        (x1, y1), (x2, y2) = pts[s], pts[e]
        dx, dy = x2 - x1, y2 - y1; n2 = dx * dx + dy * dy
        best, idx = -1.0, 0
        for i in range(s + 1, e):
            px, py = pts[i]
            if n2 == 0: d = (px - x1) ** 2 + (py - y1) ** 2
            else:
                t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / n2))
                d = (px - x1 - t * dx) ** 2 + (py - y1 - t * dy) ** 2
            if d > best: best, idx = d, i
        if best > eps * eps:
            keep[idx] = True; stack += [(s, idx), (idx, e)]
    return [p for p, k in zip(pts, keep) if k]

def clean(line, eps, nd):
    out = [[round(x, nd), round(y, nd)] for x, y in rdp(line, eps)]
    return [p for i, p in enumerate(out) if i == 0 or p != out[i - 1]]

def rings(geom):
    if geom['type'] == 'Polygon': return [geom['coordinates']]
    if geom['type'] == 'MultiPolygon': return geom['coordinates']
    return []

def lines_of(geom):
    if geom['type'] == 'LineString': return [geom['coordinates']]
    if geom['type'] == 'MultiLineString': return geom['coordinates']
    return []

def touches_focus(line):
    return any(in_focus(x, y) for x, y in line[::max(1, len(line) // 8)])

labels = []   # [name, lat, lon, kind, minzoom, rank]  kind: c=country s=state/province p=city t=MA town
def label(n, lat, lon, k, z, r):
    if n: labels.append([n, round(lat, 3), round(lon, 3), k, int(z), round(r, 2)])

# ---------- countries: land fill + names ----------
countries = []
for f in ne('ne_50m_admin_0_countries'):
    p = f['properties']
    polys = []
    for poly in rings(f['geometry']):
        rs = [clean(r, 0.06, 2) for r in poly]
        rs = [r for r in rs if len(r) >= 7]   # drop specks of islands
        if rs: polys.append(rs)
    if polys: countries.append([p['ADM0_A3'], polys])
    label(p['NAME'], p['LABEL_Y'], p['LABEL_X'], 'c', max(2, int(p['MIN_LABEL'])), p['LABELRANK'])

# ---------- states / provinces: borders (focus countries) + names ----------
admin1, usland = [], []   # usland: sharper US state shapes that replace the coarse US outline when zoomed in
NE_STATES = {'Massachusetts', 'Rhode Island', 'New Hampshire', 'Maine', 'Connecticut', 'New York', 'Vermont'}
for f in ne('ne_10m_admin_1_states_provinces'):
    p = f['properties']
    if p.get('adm0_a3') == 'USA':
        e = 0.002 if p.get('name') in NE_STATES else 0.01
        for poly in rings(f['geometry']):
            rs = [clean(r, e, 3 if e > 0.005 else 4) for r in poly]
            rs = [r for r in rs if len(r) >= 4]
            if rs: usland.append(rs)
    if p.get('adm0_a3') not in FOCUS_A3: continue
    for poly in rings(f['geometry']):
        r = clean(poly[0], 0.025, 2)
        if len(r) >= 4 and touches_focus(r): admin1.append(r)
    lat, lon = p.get('latitude'), p.get('longitude')
    if lat is not None and in_focus(lon, lat):
        label(p['name'], lat, lon, 's', 4 if p.get('adm0_a3') in ('USA', 'RUS') else 5, p.get('labelrank') or 5)

# ---------- cities ----------
for f in ne('ne_10m_populated_places_simple'):
    p = f['properties']; lat, lon = p['latitude'], p['longitude']
    z = p.get('min_zoom') or 10
    if in_focus(lon, lat): z = min(z, 9)
    elif z > 5: continue
    label(p['name'], lat, lon, 'p', max(3, z), -(p.get('pop_max') or 0) / 1e6)

# ---------- lakes, rivers, roads (focus regions, plus the largest lakes/rivers worldwide) ----------
lakes = []
for f in ne('ne_10m_lakes'):
    sr = f['properties'].get('scalerank', 9)
    for poly in rings(f['geometry']):
        r = clean(poly[0], 0.01, 3)
        if len(r) >= 4 and (sr <= 2 or (sr <= 7 and touches_focus(r))): lakes.append(r)
rivers = []
for f in ne('ne_10m_rivers_lake_centerlines'):
    sr = f['properties'].get('scalerank', 9)
    for ln in lines_of(f['geometry']):
        r = clean(ln, 0.02, 2)
        if len(r) >= 2 and (sr <= 3 or (sr <= 7 and touches_focus(r))): rivers.append(r)
roads = {'major': [], 'minor': []}
for f in ne('ne_10m_roads'):
    p = f['properties']
    if p.get('type') not in ('Major Highway', 'Secondary Highway', 'Beltway', 'Road'): continue
    for ln in lines_of(f['geometry']):
        if not touches_focus(ln): continue
        r = clean(ln, 0.015, 3)
        if len(r) >= 2: roads['major' if p['type'] in ('Major Highway', 'Beltway') else 'minor'].append(r)

# ---------- Massachusetts (OpenStreetMap) ----------
def osm_ways(path, kinds):
    out = {k: [] for k in kinds}; seen = set(); rels = []
    for el in json.load(open(f'{CACHE}/{path}'))['elements']:
        if el['type'] == 'relation': rels.append(el); continue
        if el['type'] != 'way' or el['id'] in seen or 'geometry' not in el: continue
        seen.add(el['id']); t = el.get('tags', {})
        k = ('coast' if t.get('natural') == 'coastline' else 'river' if t.get('waterway') == 'river'
             else 'water' if t.get('natural') == 'water' else 'road' if t.get('highway') in ('motorway', 'trunk') else 'border')
        if k not in out: continue
        eps, nd = {'road': (0.0015, 3), 'border': (0.0006, 4), 'coast': (0.0007, 4), 'river': (0.0015, 3), 'water': (0.0002, 5)}[k]
        pts = clean([[p['lon'], p['lat']] for p in el['geometry']], eps, nd)
        if len(pts) >= 2: out[k].append(pts)
    return out, rels

ma, rels = osm_ways('ma-towns.json', ['border'])
CORE = {'Boston', 'Cambridge', 'Worcester', 'Springfield', 'Lowell', 'New Bedford', 'Quincy', 'Waltham', 'Watertown'}
LABEL_AT = {'Boston': (42.3555, -71.0605), 'Quincy': (42.2529, -71.0023)}   # bbox centres in the harbor
for el in rels:
    nm = el.get('tags', {}).get('name'); c = el.get('center')
    if not nm or not c: continue
    lat, lon = LABEL_AT.get(nm, (c['lat'], c['lon']))
    label(nm, lat, lon, 't', 8 if nm in CORE else 9, 0 if nm in CORE else 1)
ema, _ = osm_ways('ema-lines.json', ['coast', 'road', 'river'])
inner, _ = osm_ways('boston-osm.json', ['water'])
ma.update(ema); ma['water'] = inner['water']

base = {'countries': countries, 'usland': usland, 'admin1': admin1, 'lakes': lakes, 'rivers': rivers, 'roads': roads, 'ma': ma, 'labels': labels,
        'attribution': '© OpenStreetMap contributors (ODbL) · Natural Earth'}
json.dump(base, open(f'{ROOT}/work/basemap.json', 'w'), separators=(',', ':'))
sz = lambda o: len(json.dumps(o, separators=(',', ':'))) // 1024
print('KB:', {k: sz(v) for k, v in base.items() if k != 'ma'}, {('ma.' + k): sz(v) for k, v in ma.items()},
      f'total {os.path.getsize(ROOT + "/work/basemap.json") // 1024}')
print('labels by kind:', {k: sum(1 for l in labels if l[3] == k) for k in 'cspt'})
