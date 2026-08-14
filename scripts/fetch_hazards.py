# -*- coding: utf-8 -*-
"""ハザード関連レイヤを data/graph/viz と web/public/data 向けに用意する。

1. 市ODの避難所CSV → shelters.geojson
2. 洪水浸水想定・土砂警戒 — 外部取得を試み、失敗時は空FC＋注記
   （出典・ライセンスは About に記載）
"""
import csv
import glob
import io
import json
import os
import re
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VIZ = os.path.join(ROOT, 'data', 'derived')
EXT = os.path.join(ROOT, 'data', 'external', 'hazards')
WEB = os.path.join(ROOT, 'web', 'public', 'data')

sys.path.insert(0, HERE)
from fetch_boundaries import canon_place  # noqa: E402

# 流山市 bbox（おおよそ）
BBOX = (139.85, 35.80, 139.98, 35.95)  # minlon, minlat, maxlon, maxlat


def _dump(name, obj):
    os.makedirs(VIZ, exist_ok=True)
    os.makedirs(WEB, exist_ok=True)
    payload = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    for d in (VIZ, WEB):
        p = os.path.join(d, name)
        with io.open(p, 'w', encoding='utf-8') as f:
            f.write(payload)
    print('wrote %-28s %8.1f KB' % (name, len(payload.encode('utf-8')) / 1024))
    return os.path.join(VIZ, name)


def _in_bbox(lon, lat):
    return BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]


def build_shelters():
    paths = glob.glob(os.path.join(
        ROOT, r'data\raw\c_05_*\071_*\*.csv'))
    if not paths:
        print('  shelters: CSV missing')
        return None
    path = paths[0]
    # encoding
    raw = io.open(path, 'rb').read()
    for enc in ('utf-8-sig', 'cp932'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode('cp932', 'replace')
    rows = list(csv.reader(io.StringIO(text)))
    hdr = rows[0]
    # normalize header
    hmap = {h.strip(): i for i, h in enumerate(hdr)}

    def col(*cands):
        for c in cands:
            if c in hmap:
                return hmap[c]
        for c in cands:
            for h, i in hmap.items():
                if c in h:
                    return i
        return None

    ci_name = col('名称', '施設名')
    ci_addr = col('住所', '所在地')
    ci_lat = col('緯度')
    ci_lon = col('経度')
    hazard_cols = {}
    for key in ('洪水', '高潮', '地震', '土砂災害', '大規模な火事'):
        ci = col(key)
        if ci is not None:
            hazard_cols[key] = ci
    ci_cap = col('避難所_収容可能人員', '収容可能人員')

    feats = []
    for r in rows[1:]:
        if ci_name is None or ci_name >= len(r):
            continue
        name = r[ci_name].strip()
        if not name:
            continue
        try:
            lat = float(r[ci_lat]); lon = float(r[ci_lon])
        except (TypeError, ValueError, IndexError):
            continue
        hazards = [k for k, i in hazard_cols.items()
                   if i < len(r) and str(r[i]).strip() in ('1', '○', '〇', 'あり')]
        place = canon_place(r[ci_addr]) if ci_addr is not None and ci_addr < len(r) else ''
        # 住所から町名抽出（簡易）
        addr = r[ci_addr] if ci_addr is not None and ci_addr < len(r) else ''
        m = re.search(r'流山市(.+?)(\d|$)', addr)
        place_guess = canon_place(m.group(1)) if m else place
        cap = None
        if ci_cap is not None and ci_cap < len(r):
            try:
                cap = int(float(str(r[ci_cap]).replace(',', '')))
            except (ValueError, TypeError):
                pass
        feats.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
            'properties': {
                'name': name,
                'address': addr,
                'place': place_guess,
                'hazards': hazards,
                'capacity': cap,
            },
        })
    fc = {
        'type': 'FeatureCollection',
        'source': '流山市オープンデータ 避難所・避難場所',
        'features': feats,
    }
    _dump('shelters.geojson', fc)
    print('  shelters:', len(feats))
    return fc


def _empty_fc(source, note):
    return {
        'type': 'FeatureCollection',
        'source': source,
        'note': note,
        'features': [],
    }


def _clip_geojson(fc):
    """簡易 bbox クリップ（頂点が1つでも域内なら残す）。"""
    out = []
    for f in fc.get('features', []):
        g = f.get('geometry') or {}
        coords = g.get('coordinates')
        if not coords:
            continue
        flat = []

        def walk(c):
            if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
                flat.append(c[:2])
            elif isinstance(c, (list, tuple)):
                for x in c:
                    walk(x)
        walk(coords)
        if any(_in_bbox(lon, lat) for lon, lat in flat):
            # 座標を丸める
            def roundc(c):
                if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
                    return [round(float(c[0]), 5), round(float(c[1]), 5)] + list(c[2:])
                if isinstance(c, (list, tuple)):
                    return [roundc(x) for x in c]
                return c
            nf = dict(f)
            nf['geometry'] = dict(g)
            nf['geometry']['coordinates'] = roundc(coords)
            out.append(nf)
    return out


def _load_geojson_zip(zpath):
    """zip 内の .geojson / .json を結合して FeatureCollection にする。"""
    feats = []
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist()
                 if n.lower().endswith(('.geojson', '.json')) and not n.endswith('/')]
        # 想定最大規模を優先
        names.sort(key=lambda n: (0 if '想定最大' in n or 'max' in n.lower()
                                  or 'A31a' in n else 1, n))
        for n in names:
            try:
                obj = json.loads(z.read(n).decode('utf-8'))
            except Exception:
                continue
            if obj.get('type') == 'FeatureCollection':
                feats.extend(obj.get('features') or [])
            elif obj.get('type') == 'Feature':
                feats.append(obj)
    return feats


def fetch_flood():
    """国土数値情報 洪水浸水想定区域（千葉県 GeoJSON）を取得し流山市 bbox でクリップ。"""
    os.makedirs(EXT, exist_ok=True)
    note = ('洪水浸水想定の面データ自動取得に失敗。'
            '避難所の「洪水」適合フラグと市ハザードマップPDFを参照。'
            '手動で data/external/hazards/flood.geojson を置けば再実行で取り込む。')
    manual = os.path.join(EXT, 'flood.geojson')
    if os.path.exists(manual):
        fc = json.load(io.open(manual, encoding='utf-8'))
        fc['features'] = _clip_geojson(fc)
        _dump('hazards_flood.geojson', fc)
        print('  flood: %d features (manual)' % len(fc['features']))
        return fc

    # 千葉県・洪水予報河川等（約50MB）+ その他河川（約13MB）
    base = 'https://nlftp.mlit.go.jp/ksj/gml/data/A31/'
    zips = [
        ('A31a-25_12_10_GEOJSON.zip', '洪水予報河川･水位周知河川'),
        ('A31a-25_12_20_GEOJSON.zip', 'その他の河川'),
    ]
    all_feats = []
    for fname, label in zips:
        zpath = os.path.join(EXT, fname)
        url = base + fname
        try:
            if not (os.path.exists(zpath) and os.path.getsize(zpath) > 1_000_000):
                print('  downloading flood', fname, '...')
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; OpenViewNagareyama/1.0)'})
                with urllib.request.urlopen(req, timeout=600) as r, open(zpath, 'wb') as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                print('  saved', zpath, os.path.getsize(zpath))
            feats = _load_geojson_zip(zpath)
            for ft in feats:
                ft.setdefault('properties', {})['layer'] = label
            all_feats.extend(feats)
            print('  raw features from %s: %d' % (fname, len(feats)))
        except Exception as e:
            print('  flood fetch fail %s:' % fname, e)

    if all_feats:
        fc = {
            'type': 'FeatureCollection',
            'source': '国土数値情報 洪水浸水想定区域データ（千葉県・CC BY 4.0）',
            'note': '流山市 bbox でクリップ。想定最大規模を優先して読み込み。',
            'features': _clip_geojson({'features': all_feats}),
        }
        _dump('hazards_flood.geojson', fc)
        print('  flood clipped:', len(fc['features']))
        return fc
    fc = _empty_fc('（未取得）洪水浸水想定', note)
    _dump('hazards_flood.geojson', fc)
    return fc


def fetch_dosha():
    note = ('土砂災害警戒区域の面データは外部配信形式の制約により自動取得できなかった。'
            '避難所の「土砂災害」適合フラグを参照。'
            '手動で data/external/hazards/dosha.geojson を置けば再実行で取り込む。')
    manual = os.path.join(EXT, 'dosha.geojson')
    if os.path.exists(manual):
        fc = json.load(io.open(manual, encoding='utf-8'))
        fc['features'] = _clip_geojson(fc)
        _dump('hazards_dosha.geojson', fc)
        print('  dosha: %d features (manual)' % len(fc['features']))
        return fc
    fc = _empty_fc('（未取得）土砂災害警戒区域', note)
    _dump('hazards_dosha.geojson', fc)
    return fc


def write_raster_meta():
    """重ねるハザードマップ（地理院）のラスタタイル定義。

    国土数値情報 GeoJSON の直リンクはアンケート必須の許諾フォームがあり
    自動化できないため、公式オープンデータタイルを主表示に使う。
    """
    base = 'https://disaportaldata.gsi.go.jp/raster'
    meta = {
        'note': 'ハザードマップポータルサイト配信タイル（オープンデータ）。'
                '避難所ポイントは市OD。ポリゴンGeoJSONは任意で external/hazards に配置可。',
        'attribution': 'ハザードマップポータルサイト',
        'legend_guide': {
            'label': '浸水深の見方（浸水ナビ FAQ）',
            'url': 'https://suiboumap.gsi.go.jp/faq.html',
        },
        'order': [
            'flood',
            'flood_l1',
            'flood_duration',
            'kaoku_hanran',
            'kaoku_kagan',
            'dosha',
        ],
        'layers': {
            'flood': {
                'label': '洪水浸水想定（想定最大規模）',
                'tiles': [f'{base}/01_flood_l2_shinsuishin_data/{{z}}/{{x}}/{{y}}.png'],
                'opacity': 0.55,
                'legend': None,
            },
            'flood_l1': {
                'label': '洪水浸水想定（計画規模）',
                'tiles': [
                    f'{base}/01_flood_l1_shinsuishin_newlegend_data/{{z}}/{{x}}/{{y}}.png'
                ],
                'opacity': 0.55,
                'legend': None,
            },
            'flood_duration': {
                'label': '浸水継続時間（想定最大規模）',
                'tiles': [f'{base}/01_flood_l2_keizoku_data/{{z}}/{{x}}/{{y}}.png'],
                'opacity': 0.55,
                'legend': None,
            },
            'kaoku_hanran': {
                'label': '家屋倒壊等氾濫想定（氾濫流）',
                'tiles': [
                    f'{base}/01_flood_l2_kaokutoukai_hanran_data/{{z}}/{{x}}/{{y}}.png'
                ],
                'opacity': 0.5,
                'legend': None,
            },
            'kaoku_kagan': {
                'label': '家屋倒壊等氾濫想定（河岸侵食）',
                'tiles': [
                    f'{base}/01_flood_l2_kaokutoukai_kagan_data/{{z}}/{{x}}/{{y}}.png'
                ],
                'opacity': 0.5,
                'legend': None,
            },
            'dosha': {
                'label': '土砂災害警戒区域（急傾斜地）',
                'tiles': [f'{base}/05_kyukeishakeikaikuiki/{{z}}/{{x}}/{{y}}.png'],
                'opacity': 0.55,
                'legend': None,
            },
        },
    }
    _dump('hazards_raster.json', meta)
    return meta


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    build_shelters()
    fetch_flood()
    fetch_dosha()
    write_raster_meta()


if __name__ == '__main__':
    main()
