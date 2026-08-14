# -*- coding: utf-8 -*-
"""流山市域の OpenStreetMap POI を Overpass API から取得する。

市のオープンデータには無い生活利便施設（店舗・病院・学校・銀行など）を
ペルソナ対話や地図の「近隣施設」として使うため。
OSM は ODbL で、出典表示すれば利用できる。

    python scripts/fetch_osm_poi.py

出力: data/external/osm/poi.geojson
      web/public/data/osm_poi.geojson（表示用の軽量版）
"""
import io, json, os, time
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, 'data', 'external', 'osm')
WEB = os.path.join(ROOT, 'web', 'public', 'data')

ENDPOINT = 'https://overpass-api.de/api/interpreter'
AREA = '35.82,139.86,35.95,139.96'          # 流山市を含む矩形（南,西,北,東）

# 生活実感に効くものに絞る（全POIを取ると量が多く、用途も薄いため）
KINDS = [
    ('shop', 'supermarket', 'スーパー'),
    ('shop', 'convenience', 'コンビニ'),
    ('shop', 'bakery', 'パン屋'),
    ('shop', 'drugstore', 'ドラッグストア'),
    ('amenity', 'pharmacy', '薬局'),
    ('amenity', 'hospital', '病院'),
    ('amenity', 'clinic', '診療所'),
    ('amenity', 'kindergarten', '幼稚園・保育園'),
    ('amenity', 'school', '学校'),
    ('amenity', 'library', '図書館'),
    ('amenity', 'bank', '銀行'),
    ('amenity', 'post_office', '郵便局'),
    ('amenity', 'cafe', 'カフェ'),
    ('amenity', 'restaurant', '飲食店'),
    ('amenity', 'fuel', 'ガソリンスタンド'),
    ('leisure', 'park', '公園(OSM)'),
    ('leisure', 'sports_centre', 'スポーツ施設'),
]


def build_query():
    parts = []
    for k, v, _ in KINDS:
        for t in ('node', 'way'):
            parts.append('%s["%s"="%s"](%s);' % (t, k, v, AREA))
    return '[out:json][timeout:180];(%s);out center tags;' % ''.join(parts)


def main():
    for d in (EXT, WEB):
        if not os.path.isdir(d):
            os.makedirs(d)
    q = build_query()
    print('Overpass に問い合わせ中（%d 種別）…' % len(KINDS))
    last = None
    for attempt in range(1, 4):
        try:
            r = requests.post(ENDPOINT, data={'data': q}, timeout=240,
                              headers={'User-Agent': 'nagareyama-opendata-viz/1.0'})
            r.raise_for_status()
            js = r.json()
            break
        except Exception as exc:                       # noqa: BLE001
            last = exc
            print('  失敗 %d/3: %r' % (attempt, exc))
            time.sleep(8 * attempt)
    else:
        raise SystemExit('Overpass から取得できませんでした: %r' % last)

    label = {(k, v): lb for k, v, lb in KINDS}
    feats = []
    for el in js.get('elements', []):
        tags = el.get('tags') or {}
        lat = el.get('lat') or (el.get('center') or {}).get('lat')
        lon = el.get('lon') or (el.get('center') or {}).get('lon')
        if lat is None or lon is None:
            continue
        kind = None
        for k, v, _ in KINDS:
            if tags.get(k) == v:
                kind = (k, v)
                break
        if not kind:
            continue
        feats.append(dict(
            type='Feature',
            geometry=dict(type='Point', coordinates=[round(lon, 6), round(lat, 6)]),
            properties=dict(
                osm_id='%s/%s' % (el.get('type'), el.get('id')),
                kind='%s=%s' % kind, label=label[kind],
                name=tags.get('name') or tags.get('name:ja') or '(名称なし)',
                brand=tags.get('brand', ''), operator=tags.get('operator', ''),
                opening_hours=tags.get('opening_hours', ''),
                addr=' '.join(filter(None, [
                    tags.get('addr:city', ''), tags.get('addr:neighbourhood', ''),
                    tags.get('addr:block_number', ''), tags.get('addr:housenumber', '')])),
            )))
    gj = dict(type='FeatureCollection',
              attribution='© OpenStreetMap contributors (ODbL)',
              retrieved=time.strftime('%Y-%m-%d'),
              features=feats)
    json.dump(gj, io.open(os.path.join(EXT, 'poi.geojson'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    json.dump(gj, io.open(os.path.join(WEB, 'osm_poi.geojson'), 'w', encoding='utf-8'),
              ensure_ascii=False)

    import collections
    c = collections.Counter(f['properties']['label'] for f in feats)
    print('取得 %d 件' % len(feats))
    for k, v in c.most_common():
        print('  %-16s %4d' % (k, v))


if __name__ == '__main__':
    main()
