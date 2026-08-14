# -*- coding: utf-8 -*-
"""空間レイヤーを data/graph/spatial/ に書き出し、グラフ本体にも地名ノードを追加する。

地図上で地区（字）や地点を選択 -> 関連する知識グラフを引ける形にする。
"""
import collections, io, json, math, os
import spatial as SP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'derived')
SDIR = os.path.join(OUT, 'spatial')


def geojson(feats):
    return dict(type='FeatureCollection', features=feats)


def pt(lon, lat, props):
    return dict(type='Feature',
                geometry=dict(type='Point', coordinates=[round(lon, 7), round(lat, 7)]),
                properties=props)


def main():
    aza, places, features, stations, bus_stops, bus_routes = SP.main()
    if not os.path.isdir(SDIR):
        os.makedirs(SDIR)

    # ---------- places ----------
    json.dump(places, io.open(os.path.join(SDIR, 'places.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    json.dump(geojson([pt(p['centroid']['lon'], p['centroid']['lat'],
                          dict(name=p['name'], kana=p['kana'], kind='place',
                               n_features=p['n_features'],
                               n_datasets=len(p['datasets']),
                               sources=p['sources']))
                       for p in places if p['centroid']]),
              io.open(os.path.join(SDIR, 'places.geojson'), 'w', encoding='utf-8'),
              ensure_ascii=False)

    # ---------- features ----------
    json.dump(geojson([pt(f['lon'], f['lat'],
                          dict(name=f['name'], kana=f['kana'], address=f['address'],
                               place=f['place'], station=f['station'], kind='feature',
                               dataset=f['dataset'], dataset_index=f['dataset_index'],
                               category=f['category'], path=f['path']))
                       for f in features]),
              io.open(os.path.join(SDIR, 'features.geojson'), 'w', encoding='utf-8'),
              ensure_ascii=False)

    # ---------- 駅座標の補完 ----------
    # 直接の座標を持たない駅は、駅名を含むバス停／地物の重心で近似する。
    for s in stations:
        if s['approx_centroid']:
            s['centroid_source'] = '駅を隣接駅とする地物の重心'
            continue
        base = s['name'][:-1]
        cands = [(b['lat'], b['lon']) for b in bus_stops if base in (b['name'] or '')]
        src = '駅名を含むバス停の重心'
        if not cands:
            cands = [(f['lat'], f['lon']) for f in features if base in (f['name'] or '')]
            src = '駅名を含む地物の重心'
        if cands:
            s['approx_centroid'] = dict(
                lat=round(sum(c[0] for c in cands) / len(cands), 6),
                lon=round(sum(c[1] for c in cands) / len(cands), 6))
            s['centroid_source'] = '%s (n=%d)' % (src, len(cands))
        else:
            s['centroid_source'] = None
    got = sum(1 for s in stations if s['approx_centroid'])
    print('駅座標: %d/%d 補完済（いずれも近似値）' % (got, len(stations)))

    # ---------- stations / bus ----------
    json.dump(stations, io.open(os.path.join(SDIR, 'stations.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    json.dump(geojson([pt(s['approx_centroid']['lon'], s['approx_centroid']['lat'],
                          dict(name=s['name'], lines=s['lines'], kind='station',
                               centroid_source=s['centroid_source'], approximate=True))
                       for s in stations if s['approx_centroid']]),
              io.open(os.path.join(SDIR, 'stations.geojson'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    json.dump(geojson([pt(b['lon'], b['lat'],
                          dict(name=b['name'], stop_id=b['stop_id'], place=b['place'],
                               kind='bus_stop'))
                       for b in bus_stops]),
              io.open(os.path.join(SDIR, 'bus_stops.geojson'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    json.dump(bus_routes, io.open(os.path.join(SDIR, 'bus_routes.json'), 'w',
                                  encoding='utf-8'), ensure_ascii=False, indent=1)

    # ---------- 空間インデックス（地図選択 -> グラフ） ----------
    prof = {p['index']: p for p in json.load(
        io.open(os.path.join(OUT, 'dataset_profiles.json'), encoding='utf-8'))}
    by_place_feats = collections.defaultdict(list)
    for f in features:
        if f['place']:
            by_place_feats[f['place']].append(f)
    bus_by_place = collections.defaultdict(list)
    for b in bus_stops:
        if b['place']:
            bus_by_place[b['place']].append(b)

    index = {}
    for p in places:
        fs = by_place_feats.get(p['name'], [])
        dss = sorted({f['dataset_index'] for f in fs})
        index[p['name']] = dict(
            name=p['name'], kana=p['kana'], sources=p['sources'],
            centroid=p['centroid'], n_features=len(fs),
            stations_nearby=sorted({f['station'] for f in fs if f['station']}),
            bus_stops=[b['name'] for b in bus_by_place.get(p['name'], [])],
            feature_kinds=sorted(collections.Counter(f['category'] for f in fs)),
            datasets=[dict(index=i, name=prof[i]['name'] if i in prof else '',
                           entities=prof[i]['entities'] if i in prof else [],
                           concepts=[c['label'] for c in prof[i]['concepts']][:12]
                           if i in prof else [])
                      for i in dss],
            features=[dict(name=f['name'], address=f['address'], lat=f['lat'],
                           lon=f['lon'], dataset=f['dataset']) for f in fs][:400],
        )
    json.dump(index, io.open(os.path.join(SDIR, 'place_index.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    # ---------- グラフへの地名ノード追加 ----------
    nodes, edges = [], []
    for p in places:
        nodes.append(dict(id='place:' + p['name'], type='Place', label=p['name'],
                          kana=p['kana'], sources=p['sources'],
                          lat=p['centroid']['lat'] if p['centroid'] else None,
                          lon=p['centroid']['lon'] if p['centroid'] else None,
                          n_features=p['n_features']))
        for d in p['datasets']:
            edges.append(dict(source='place:' + p['name'], rel='APPEARS_IN',
                              target='dataset:%d' % d['index']))
    for s in stations:
        nodes.append(dict(id='station:' + s['name'], type='Station', label=s['name'],
                          lines=s['lines'],
                          lat=s['approx_centroid']['lat'] if s['approx_centroid'] else None,
                          lon=s['approx_centroid']['lon'] if s['approx_centroid'] else None))
        for ln in s['lines']:
            nodes.append(dict(id='line:' + ln, type='Line', label=ln))
            edges.append(dict(source='station:' + s['name'], rel='ON_LINE',
                              target='line:' + ln))
    for b in bus_stops:
        nodes.append(dict(id='busstop:' + str(b['stop_id']), type='BusStop',
                          label=b['name'], lat=b['lat'], lon=b['lon']))
        if b['place']:
            edges.append(dict(source='busstop:' + str(b['stop_id']), rel='IN_PLACE',
                              target='place:' + b['place']))
    # 施設ポイント -> 地名 / 駅
    for i, f in enumerate(features):
        fid = 'feature:%d' % i
        nodes.append(dict(id=fid, type='Feature', label=f['name'] or f['address'],
                          lat=f['lat'], lon=f['lon'], address=f['address'],
                          dataset_index=f['dataset_index']))
        edges.append(dict(source=fid, rel='FROM_DATASET',
                          target='dataset:%d' % f['dataset_index']))
        if f['place']:
            edges.append(dict(source=fid, rel='IN_PLACE', target='place:' + f['place']))
        if f['station']:
            edges.append(dict(source=fid, rel='NEAREST_STATION',
                              target='station:' + f['station']))

    seen = set()
    with io.open(os.path.join(OUT, 'nodes.jsonl'), 'a', encoding='utf-8') as fh:
        for n in nodes:
            if n['id'] in seen:
                continue
            seen.add(n['id'])
            fh.write(json.dumps(n, ensure_ascii=False) + '\n')
    with io.open(os.path.join(OUT, 'edges.jsonl'), 'a', encoding='utf-8') as fh:
        for e in edges:
            fh.write(json.dumps(e, ensure_ascii=False) + '\n')

    print('spatial exported: places=%d stations=%d bus_stops=%d features=%d'
          % (len(places), len(stations), len(bus_stops), len(features)))
    print('graph += nodes %d / edges %d' % (len(seen), len(edges)))
    return places, stations, bus_stops, features


if __name__ == '__main__':
    main()
