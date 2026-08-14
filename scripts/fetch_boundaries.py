# -*- coding: utf-8 -*-
"""e-Stat 2020年国勢調査 小地域（町丁・字等）境界を取得し、流山市分を
GeoJSON にして data/graph/viz/boundaries.geojson へ出力する。

出典: 政府統計の総合窓口(e-Stat) 統計地理情報システム
      「小地域 国勢調査 2020年 町丁・字等（JGD2011）世界測地系緯度経度・Shapefile」
      https://www.e-stat.go.jp/gis/statmap-search?type=2

千葉県全域の zip を一度だけダウンロードし（約数十MB・data/external に保存）、
CITY_NAME='流山市' のポリゴンのみ抽出する。座標は小数5桁に丸める。
"""
import io
import json
import os
import re
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, 'data', 'external', 'estat_boundaries')
OUT = os.path.join(ROOT, 'data', 'derived')
WEB = os.path.join(ROOT, 'web', 'public', 'data')

URL = ('https://www.e-stat.go.jp/gis/statmap-search/data'
       '?dlserveyId=A002005212020&code=12&coordSys=1&format=shape'
       '&downloadType=5&datum=2011')
ZIP_PATH = os.path.join(EXT_DIR, 'A002005212020_12_chiba.zip')

KANJI_NUM = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
             '六': '6', '七': '7', '八': '8', '九': '9', '十': '10'}
ZEN2HAN = str.maketrans('０１２３４５６７８９', '0123456789')


def canon_place(name):
    """字名を正規形に寄せる（丁目の漢数字→算用数字、大字除去、ヶ統一）。"""
    s = re.sub(r'\s', '', str(name or ''))
    if not s:
        return ''
    s = s.translate(ZEN2HAN)
    s = re.sub(r'^(千葉県)?流山市', '', s)
    s = re.sub(r'^大字', '', s)
    s = s.replace('ケ', 'ヶ').replace('ガ', 'ヶ')

    def _num(m):
        t = m.group(1)
        if t in KANJI_NUM:
            return KANJI_NUM[t] + '丁目'
        return m.group(0)
    s = re.sub(r'(.)丁目', _num, s)
    return s


def download():
    os.makedirs(EXT_DIR, exist_ok=True)
    if os.path.exists(ZIP_PATH) and os.path.getsize(ZIP_PATH) > 1_000_000:
        print('cached:', ZIP_PATH)
        return
    print('downloading e-Stat boundary zip (Chiba)...')
    req = urllib.request.Request(URL, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'})
    with urllib.request.urlopen(req, timeout=300) as r, open(ZIP_PATH, 'wb') as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    print('saved:', ZIP_PATH, os.path.getsize(ZIP_PATH), 'bytes')


def extract_nagareyama():
    import shapefile  # pyshp
    with zipfile.ZipFile(ZIP_PATH) as z:
        names = z.namelist()
        shp = next(n for n in names if n.endswith('.shp'))
        base = shp[:-4]
        rdr = shapefile.Reader(
            shp=io.BytesIO(z.read(base + '.shp')),
            dbf=io.BytesIO(z.read(base + '.dbf')),
            shx=io.BytesIO(z.read(base + '.shx')),
            encoding='cp932')
        fields = [f[0] for f in rdr.fields[1:]]
        print('fields:', fields)
        feats = []
        for sr in rdr.iterShapeRecords():
            rec = dict(zip(fields, sr.record))
            if str(rec.get('CITY_NAME', '')).strip() != '流山市':
                continue
            geo = sr.shape.__geo_interface__
            geo = _round_geo(geo)
            s_name = str(rec.get('S_NAME', '') or '').strip()
            feats.append({
                'type': 'Feature',
                'geometry': geo,
                'properties': {
                    'key': str(rec.get('KEY_CODE', '')),
                    'name': s_name,
                    'place': canon_place(s_name),
                    'area_m2': round(float(rec.get('AREA', 0) or 0)),
                    'pop2020': int(rec.get('JINKO', 0) or 0),
                    'households2020': int(rec.get('SETAI', 0) or 0),
                },
            })
    return feats


def _round_geo(geo, nd=5):
    def rec(c):
        if isinstance(c, (list, tuple)):
            if c and isinstance(c[0], (int, float)):
                return [round(c[0], nd), round(c[1], nd)]
            return [rec(x) for x in c]
        return c
    return {'type': geo['type'], 'coordinates': rec(geo['coordinates'])}


def main():
    download()
    feats = extract_nagareyama()
    print('nagareyama polygons:', len(feats))
    for d in (OUT, WEB):
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, 'boundaries.geojson')
        with io.open(out, 'w', encoding='utf-8') as f:
            json.dump({'type': 'FeatureCollection',
                       'source': '政府統計の総合窓口(e-Stat) 2020年国勢調査 小地域境界（加工済）',
                       'features': feats}, f, ensure_ascii=False,
                      separators=(',', ':'))
        print('wrote:', out, os.path.getsize(out), 'bytes')
    names = sorted({f['properties']['place'] for f in feats})
    print('distinct place names:', len(names))
    print('sample:', names[:10])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
