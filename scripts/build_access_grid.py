# -*- coding: utf-8 -*-
"""バス利便性の 150m グリッド access_grid.json を生成する。

各セルのスコアは、半径1.2km内の停留所について
    Σ(平日出発本数 × exp(-距離/320m))
で、徒歩圏の便数がどれだけ効いてくるかを表す。
（data-nagareyama の build_viz.py から地図に必要な部分を切り出したもの）

出力: data/derived/access_grid.json, web/public/data/access_grid.json
前提: fetch_boundaries.py（境界）と download.py（GTFS の feed.zip）が済んでいること
"""
import collections
import csv
import glob
import io
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DERIVED = os.path.join(ROOT, 'data', 'derived')
WEB = os.path.join(ROOT, 'web', 'public', 'data')


def dump(name, obj):
    for d in (DERIVED, WEB):
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with io.open(p, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
        print('wrote %-28s %8.1f KB' % (p, os.path.getsize(p) / 1024))


def read_gtfs():
    pats = [
        os.path.join(ROOT, 'data', 'raw', '**', 'feed.zip'),
        os.path.join(ROOT, 'data', 'external', 'gtfs', '*.zip'),
    ]
    paths = []
    for pat in pats:
        paths += glob.glob(pat, recursive=True)
    if not paths:
        raise SystemExit('GTFS feed.zip が見つかりません。先に download.py を実行してください')
    import zipfile
    z = zipfile.ZipFile(paths[0])

    def tbl(name):
        with z.open(name) as f:
            return list(csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig')))
    return {n: tbl(n + '.txt') for n in ('stops', 'trips', 'stop_times', 'calendar')}


def point_in_poly(lon, lat, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and \
                lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def build_access_grid(gtfs):
    bpath = os.path.join(DERIVED, 'boundaries.geojson')
    if not os.path.exists(bpath):
        bpath = os.path.join(WEB, 'boundaries.geojson')
    b = json.load(io.open(bpath, encoding='utf-8'))
    polys = []   # (bbox, outer_ring)
    for f in b['features']:
        g = f['geometry']
        rings = [g['coordinates'][0]] if g['type'] == 'Polygon' else \
                [p[0] for p in g['coordinates']]
        for r in rings:
            xs = [c[0] for c in r]
            ys = [c[1] for c in r]
            polys.append(((min(xs), min(ys), max(xs), max(ys)), r))
    minx = min(p[0][0] for p in polys)
    miny = min(p[0][1] for p in polys)
    maxx = min(1000.0, max(p[0][2] for p in polys))
    maxy = max(p[0][3] for p in polys)

    # 平日の停留所別出発本数
    weekday = [c['service_id'] for c in gtfs['calendar'] if c.get('monday') == '1']
    wtrips = {t['trip_id'] for t in gtfs['trips'] if t['service_id'] in weekday}
    deps = collections.Counter(r['stop_id'] for r in gtfs['stop_times']
                               if r['trip_id'] in wtrips)
    stop_pts = [(float(s['stop_lat']), float(s['stop_lon']),
                 deps.get(s['stop_id'], 0), s['stop_name'])
                for s in gtfs['stops'] if deps.get(s['stop_id'], 0) > 0]

    cell = 150.0
    ky = 110950.0
    kx = math.cos(math.radians((miny + maxy) / 2)) * 111320.0
    dlat = cell / ky
    dlon = cell / kx
    pts = []
    lat = miny + dlat / 2
    while lat < maxy:
        lon = minx + dlon / 2
        while lon < maxx:
            ok = any(bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3] and
                     point_in_poly(lon, lat, ring) for bb, ring in polys)
            if ok:
                best_d, best_deps, score = float('inf'), 0, 0.0
                for sla, slo, dp, _nm in stop_pts:
                    dx = (slo - lon) * kx
                    dy = (sla - lat) * ky
                    d = math.sqrt(dx * dx + dy * dy)
                    if d < best_d:
                        best_d, best_deps = d, dp
                    if d < 1200:
                        score += dp * math.exp(-d / 320.0)
                pts.append([round(lon, 5), round(lat, 5), round(score, 1),
                            int(best_d), best_deps])
            lon += dlon
        lat += dlat
    dump('access_grid.json', {
        'cell_m': cell,
        'note': '各セル: [経度,緯度,アクセススコア,最寄バス停距離m,その停留所の平日出発本数]。'
                'スコア=Σ(平日出発本数×exp(-距離/320m)) 半径1.2km',
        'points': pts,
    })
    print('  access grid: %d cells' % len(pts))


def main():
    build_access_grid(read_gtfs())


if __name__ == '__main__':
    main()
