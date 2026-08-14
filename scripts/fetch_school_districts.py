# -*- coding: utf-8 -*-
"""国土数値情報 小学校区(A27)・中学校区(A32) 2023 から流山市分を取得する。

出典: 国土交通省 国土数値情報ダウンロードサイト
      https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A27-2023.html
      https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A32-2023.html
取得: pygeoapi ミラー（市区町村コード 12220 で抽出）
"""
import io
import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIZ = os.path.join(ROOT, 'data', 'derived')
WEB = os.path.join(ROOT, 'web', 'public', 'data')
EXT = os.path.join(ROOT, 'data', 'external', 'ksj_school_districts')

CITY_CODE = '12220'
BASE = 'https://pygeoapi.glodal-inc.net/collections'
UA = {'User-Agent': 'OpenViewNagareyama/1.0 (school-district fetch)'}


def _round_geo(geo, nd=5):
    def rec(c):
        if isinstance(c, (list, tuple)):
            if c and isinstance(c[0], (int, float)):
                return [round(float(c[0]), nd), round(float(c[1]), nd)]
            return [rec(x) for x in c]
        return c
    return {'type': geo['type'], 'coordinates': rec(geo['coordinates'])}


def _fetch_all(collection, code_key):
    """ページングして全市区分を取得。"""
    feats = []
    offset = 0
    limit = 100
    while True:
        q = urllib.parse.urlencode({
            'f': 'json',
            'limit': limit,
            'offset': offset,
            code_key: CITY_CODE,
        })
        url = f'{BASE}/{collection}/items?{q}'
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read().decode('utf-8'))
        batch = data.get('features') or []
        feats.extend(batch)
        matched = data.get('numberMatched')
        print('  %s offset=%d got=%d matched=%s' % (
            collection, offset, len(batch), matched))
        if not batch:
            break
        offset += len(batch)
        if matched is not None and offset >= int(matched):
            break
        if len(batch) < limit:
            break
    return feats


def _normalize(kind, raw_feats):
    """kind: 'elem' | 'junior'"""
    prefix = 'a27' if kind == 'elem' else 'a32'
    out = []
    for f in raw_feats:
        p = f.get('properties') or {}
        code = str(p.get(f'{prefix}_001') or '')
        if code != CITY_CODE:
            continue
        name = str(p.get(f'{prefix}_004') or '').strip()
        geo = f.get('geometry')
        if not geo or not name:
            continue
        out.append({
            'type': 'Feature',
            'geometry': _round_geo(geo),
            'properties': {
                'name': name,
                'kind': kind,
                'school_code': str(p.get(f'{prefix}_003') or ''),
                'operator': str(p.get(f'{prefix}_002') or ''),
                'address': str(p.get(f'{prefix}_005') or ''),
                'city_code': code,
                'source': '国土数値情報 %s-2023' % (
                    'A27' if kind == 'elem' else 'A32'),
            },
        })
    out.sort(key=lambda x: x['properties']['name'])
    return out


def _dump(name, obj):
    os.makedirs(VIZ, exist_ok=True)
    os.makedirs(WEB, exist_ok=True)
    os.makedirs(EXT, exist_ok=True)
    payload = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    for d in (VIZ, WEB, EXT):
        path = os.path.join(d, name)
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(payload)
    print('wrote %-36s %6.1f KB  features=%d' % (
        name, len(payload.encode('utf-8')) / 1024,
        len(obj.get('features') or [])))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print('fetch elementary (A27)...')
    elem_raw = _fetch_all('A27-23', 'a27_001')
    elem = _normalize('elem', elem_raw)
    print('fetch junior high (A32)...')
    junior_raw = _fetch_all('A32-23', 'a32_001')
    junior = _normalize('junior', junior_raw)

    meta = {
        'note': '国土数値情報 学校区（2023）。参考表示であり最新の通学指定と異なる場合あり。',
        'attribution': '国土数値情報（小学校区・中学校区）',
        'source_pages': {
            'elem': 'https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A27-2023.html',
            'junior': 'https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A32-2023.html',
        },
        'city_code': CITY_CODE,
        'counts': {'elem': len(elem), 'junior': len(junior)},
    }
    _dump('school_districts_meta.json', meta)
    _dump('school_districts_elem.geojson', {
        'type': 'FeatureCollection',
        'features': elem,
    })
    _dump('school_districts_junior.geojson', {
        'type': 'FeatureCollection',
        'features': junior,
    })
    print('names elem:', [f['properties']['name'] for f in elem])
    print('names junior:', [f['properties']['name'] for f in junior])


if __name__ == '__main__':
    main()
