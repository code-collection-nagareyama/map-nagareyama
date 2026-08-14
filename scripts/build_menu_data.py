# -*- coding: utf-8 -*-
"""地図の表示データを web/public/data/ に生成する。

生成物:
  map_layers.json     地図のレイヤーカタログ（分類・表示形式・件数・出所）
  map_points.geojson  地図に出す点を1本に束ねたもの（layer で絞り込む）
"""
import collections, glob, io, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OUT = os.path.join(ROOT, 'web', 'public', 'data')
VIZ = os.path.join(ROOT, 'data', 'derived')
SPATIAL_CANDIDATES = [
    os.path.join(ROOT, 'data', 'derived', 'spatial'),
    os.path.join(ROOT, 'data', 'graph', 'spatial'),
]

# 地物から重心が取れない駅の参考座標（公開地図の駅位置の近似）
STATION_FALLBACK = {
    '流山セントラルパーク駅': dict(lat=35.83833, lon=139.92528),
    '北小金駅': dict(lat=35.8408, lon=139.9083),
}


def spatial_path(*parts):
    for base in SPATIAL_CANDIDATES:
        p = os.path.join(base, *parts)
        if os.path.exists(p):
            return p
    return os.path.join(SPATIAL_CANDIDATES[0], *parts)


def find_gtfs_zip():
    pats = [
        os.path.join(ROOT, 'data', 'raw', '**', 'feed.zip'),
        os.path.join(ROOT, 'data', 'json', '**', 'feed.zip'),
        os.path.join(ROOT, 'data', 'external', 'gtfs', '*.zip'),
    ]
    found = []
    for pat in pats:
        found.extend(glob.glob(pat, recursive=True))
    return found[0] if found else None


def gtfs_bus_stops():
    """ぐりーんバス GTFS からバス停座標を直接読む。"""
    import csv
    import zipfile
    zpath = find_gtfs_zip()
    if not zpath:
        return []
    out = []
    with zipfile.ZipFile(zpath) as zf:
        raw = zf.read('stops.txt').decode('utf-8-sig')
        for r in csv.DictReader(io.StringIO(raw)):
            if str(r.get('location_type') or '0') not in ('0', ''):
                continue
            try:
                lon = float(r['stop_lon'])
                lat = float(r['stop_lat'])
            except Exception:                              # noqa: BLE001
                continue
            if not (35.7 < lat < 36.1 and 139.7 < lon < 140.1):
                continue
            out.append(dict(
                name=r.get('stop_name') or r.get('stop_id'),
                address='', tel='', lat=lat, lon=lon,
                dataset='流山ぐりーんバス GTFS',
                detail={'stop_id': r.get('stop_id') or ''},
            ))
    return out


def load_stations():
    """stations.json + 欠損座標のフォールバック。"""
    p = spatial_path('stations.json')
    out = []
    if os.path.exists(p):
        for s in load(p):
            c = s.get('approx_centroid') or STATION_FALLBACK.get(s.get('name'))
            if not c:
                continue
            src = '駅（座標は近似）'
            if not s.get('approx_centroid') and s.get('name') in STATION_FALLBACK:
                src = '駅（参考座標）'
            out.append(dict(
                name=s['name'], address='', tel='',
                lat=c['lat'], lon=c['lon'], dataset=src,
                detail={'路線': '・'.join(s.get('lines') or [])},
            ))
    # stations.json に無いフォールバック駅も足す
    have = {r['name'] for r in out}
    for nm, c in STATION_FALLBACK.items():
        if nm not in have:
            out.append(dict(
                name=nm, address='', tel='', lat=c['lat'], lon=c['lon'],
                dataset='駅（参考座標）', detail={},
            ))
    return out


def carry_osm_from_existing(feats, catalog):
    """poi.geojson が無いとき、既存 map_points の OSM レイヤを引き継ぐ。"""
    prev = os.path.join(OUT, 'map_points.geojson')
    prev_cat = os.path.join(OUT, 'map_layers.json')
    if not os.path.exists(prev) or not os.path.exists(prev_cat):
        return
    old = load(prev)
    old_cat = load(prev_cat)
    osm_ids = {L['id'] for L in old_cat.get('layers', []) if L.get('group') == 'osm'}
    if not osm_ids:
        return
    n = 0
    for f in old['features']:
        if f.get('properties', {}).get('layer') in osm_ids:
            feats.append(f)
            n += 1
    for L in old_cat['layers']:
        if L.get('group') == 'osm':
            catalog.append(L)
    print('  OSM近隣施設（既存データから継承） %d 点 / %d 種' % (n, len(osm_ids)))

# ---- 地図レイヤーの定義 ---------------------------------------------------
# group: 画面のサブタブ / kind: plot(点) | heat(密度)
LAYERS = [
    dict(id='shelter',   label='避難所・避難場所', group='bousai', kind='plot',
         ds=[71], color='#e4572e', icon='◆'),
    dict(id='well',      label='災害用井戸',       group='bousai', kind='plot',
         ds=[72], color='#3b8ea5', icon='●'),
    dict(id='suiri',     label='消防水利（密度）', group='bousai', kind='heat',
         ds=[68], color='#2f6690', icon='·'),
    dict(id='aed',       label='AED設置場所',      group='bousai', kind='plot',
         ds=[88], color='#d81159', icon='＋', special='aed'),
    dict(id='bousai_shisetsu', label='消防・防災施設', group='bousai', kind='plot',
         ds=[83], color='#a63d40', icon='■'),

    dict(id='park',      label='公園',             group='kurashi', kind='plot',
         ds=[84], color='#4c9f70', icon='●'),
    dict(id='toilet',    label='公衆トイレ',       group='kurashi', kind='plot',
         ds=[85], color='#6b9ac4', icon='○'),
    dict(id='bunkazai',  label='文化財',           group='kurashi', kind='plot',
         ds=[244], color='#b07d62', icon='▲'),
    dict(id='shisetsu',  label='公共施設（全て）', group='kurashi', kind='plot',
         ds=[6], color='#5c6672', icon='■'),
    dict(id='kosodate',  label='子育て施設',       group='kurashi', kind='plot',
         ds=[74, 32, 34], color='#f4a259', icon='●'),
    dict(id='fukushi',   label='福祉・介護',       group='kurashi', kind='plot',
         ds=[75, 14], color='#8f5c9e', icon='●'),
    dict(id='iryo',      label='医療機関',         group='kurashi', kind='plot',
         ds=[10, 9, 12], color='#c1666b', icon='＋'),

    dict(id='chuurin',   label='駐輪場',           group='kotsu', kind='plot',
         ds=[47], color='#2a9d8f', icon='◇'),
    dict(id='busstop',   label='バス停',           group='kotsu', kind='plot',
         ds=[], color='#457b9d', icon='·', special='bus'),
    dict(id='station',   label='鉄道駅',           group='kotsu', kind='plot',
         ds=[], color='#1d3557', icon='◎', special='station'),
    dict(id='toohyo',    label='投票所',           group='kurashi', kind='plot',
         ds=[190], color='#7b8794', icon='□'),
]


def load(p):
    return json.load(io.open(p, encoding='utf-8'))


def to_deg(v):
    """十進度に直す。

    消防水利データは度分秒を DD.MMSSsss で詰めた形式（035.5250923 = 35°52'50.9"）
    で配布されているため、十進度として範囲外なら度分秒として解釈する。
    """
    try:
        f = float(str(v).strip())
    except Exception:                                  # noqa: BLE001
        return None
    if 35.7 < f < 36.1 or 139.7 < f < 140.1:
        return f
    s = '%011.7f' % f                                  # 035.5250923
    m = re.match(r'^(\d{2,3})\.(\d{2})(\d{2})(\d*)$', s)
    if m:
        d, mi, se, frac = m.groups()
        sec = float('%s.%s' % (se, frac or '0'))
        dec = int(d) + int(mi) / 60.0 + sec / 3600.0
        if 35.7 < dec < 36.1 or 139.7 < dec < 140.1:
            return dec
    return f


def jfiles(pat):
    return sorted(glob.glob(os.path.join(ROOT, 'data', 'json', pat), recursive=True))


def points_of(ds_index):
    """データセット番号から座標つきレコードを取り出す。"""
    out = []
    for p in jfiles('**/%03d_*/*.json' % ds_index):
        o = load(p)
        raw = o['source']['path']
        ds = re.search(r'/\d+_([^/]+)/', raw)
        ds = ds.group(1) if ds else ''
        for sh in o['sheets']:
            head = sh['rows'][sh['header_row']] if sh['header_row'] < len(sh['rows']) else []
            ix = {}
            for j, h in enumerate(head):
                hh = re.sub(r'\s+|※', '', str(h or ''))
                # 「緯度（槽）（座標）」のような接尾辞つきも拾う
                if re.match(r'^(緯度|lat|latitude|y)', hh, re.I) and 'lat' not in ix:
                    ix['lat'] = j
                elif re.match(r'^(経度|lon|lng|longitude|x)', hh, re.I) and 'lon' not in ix:
                    ix['lon'] = j
                elif re.match(
                        r'^(名称|施設の名称|施設名|公園名|投票所名|投票所|拠点名|事業所名|店舗名|名前)',
                        hh) and 'name' not in ix:
                    ix['name'] = j
                elif re.match(r'^(所在地|住所|設置施設の所在地)', hh) and 'addr' not in ix:
                    ix['addr'] = j
                elif re.match(r'^(電話番号|電話)', hh) and 'tel' not in ix:
                    ix['tel'] = j
                elif re.match(r'^種別$', hh) and 'kind' not in ix:
                    ix['kind'] = j

            body = sh['rows'][sh['header_row'] + 1:]
            if 'lat' not in ix or 'lon' not in ix:
                # 見出しが無い/名前が違う配布物があるため、値域から座標列を推定する
                sample = body[:60] or sh['rows'][:60]
                cand_lat, cand_lon = [], []
                width = max((len(r) for r in sample), default=0)
                for j in range(width):
                    vals = []
                    for r in sample:
                        if j < len(r):
                            d = to_deg(r[j])
                            if d is not None:
                                vals.append(d)
                    if len(vals) < max(2, len(sample) * 0.3):
                        continue
                    if all(35.7 < v < 36.1 for v in vals):
                        cand_lat.append(j)
                    elif all(139.7 < v < 140.1 for v in vals):
                        cand_lon.append(j)
                if cand_lat and cand_lon:
                    ix['lat'], ix['lon'] = cand_lat[0], cand_lon[0]
                    # 見出し行も実データなら本体に含める
                    if sh['header_row'] == 0 and not any(
                            isinstance(v, str) and v in ('緯度', '経度')
                            for v in head):
                        body = sh['rows']
                    if 'name' not in ix:
                        for j in range(width):
                            if j in (ix['lat'], ix['lon']):
                                continue
                            vs = [r[j] for r in sample if j < len(r) and r[j]]
                            if vs and all(isinstance(v, str) for v in vs):
                                ix['name'] = j
                                break
            if 'lat' not in ix or 'lon' not in ix:
                continue
            for r in body:
                lat = to_deg(r[ix['lat']] if ix['lat'] < len(r) else None)
                lon = to_deg(r[ix['lon']] if ix['lon'] < len(r) else None)
                if lat is None or lon is None:
                    continue
                if 138 < lat < 141 and 34 < lon < 37:
                    lat, lon = lon, lat
                if not (35.7 < lat < 36.1 and 139.7 < lon < 140.1):
                    continue
                g = lambda k: (r[ix[k]] if k in ix and ix[k] < len(r) else '')  # noqa: E731
                # 見出し以外の列も詳細として持たせる（施設の詳細情報表示用）
                detail = {}
                for j, h in enumerate(head):
                    hh = re.sub(r'\s+', ' ', str(h or '')).strip()
                    if not hh or j in ix.values() or j >= len(r):
                        continue
                    v = r[j]
                    if v not in (None, ''):
                        detail[hh] = v
                name = str(g('name') or '').strip()
                if not name:
                    # 消防水利など名称列が無いデータは「種別」を表示名にする
                    name = str(g('kind') or detail.get('種別') or '').strip()
                out.append(dict(name=name, address=g('addr'),
                                tel=g('tel'), lat=lat, lon=lon, dataset=ds,
                                detail=detail))
    return out


def aed_points(known):
    """AEDは配布データに座標が無いため、施設名で既知の施設座標に突合する。"""
    idx = {}
    for r in known:
        nm = re.sub(r'\s+|　', '', str(r['name'] or ''))
        if nm:
            idx.setdefault(nm, r)
    out, miss = [], 0
    for r in points_rows(88):
        nm = re.sub(r'\s+|　', '', str(r.get('name') or ''))
        hit = idx.get(nm)
        if not hit:
            hit = next((v for k, v in idx.items() if nm and (nm in k or k in nm)), None)
        if not hit:
            miss += 1
            continue
        d = dict(r)
        d.update(lat=hit['lat'], lon=hit['lon'],
                 dataset='AED設置場所（座標は施設名突合）')
        out.append(d)
    print('    AED 突合 %d / 未突合 %d' % (len(out), miss))
    return out


def points_rows(ds_index):
    """座標が無いデータセットの行を（名称・住所・詳細つきで）取り出す。"""
    out = []
    for p in jfiles('**/%03d_*/*.json' % ds_index):
        o = load(p)
        for sh in o['sheets']:
            hr = sh['header_row']
            head = sh['rows'][hr] if hr < len(sh['rows']) else []
            hh = [re.sub(r'\s+|※', '', str(h or '')) for h in head]
            ni = next((j for j, h in enumerate(hh) if '名称' in h or '施設' in h), None)
            ai = next((j for j, h in enumerate(hh) if '所在地' in h or '住所' in h), None)
            if ni is None:
                continue
            for r in sh['rows'][hr + 1:]:
                if ni >= len(r) or not r[ni]:
                    continue
                detail = {}
                for j, h in enumerate(head):
                    lab = re.sub(r'\s+', ' ', str(h or '')).strip()
                    if lab and j < len(r) and r[j] not in (None, '') and j != ni:
                        detail[lab] = r[j]
                out.append(dict(name=r[ni], address=(r[ai] if ai is not None
                                                     and ai < len(r) else ''),
                                tel='', lat=None, lon=None, detail=detail))
        break
    return out


def build_map():
    feats, catalog = [], []
    known = []
    for L in LAYERS:
        pts = []
        if L.get('special') == 'bus':
            p = spatial_path('bus_stops.geojson')
            if os.path.exists(p):
                for f in load(p)['features']:
                    c = f['geometry']['coordinates']
                    pts.append(dict(name=f['properties'].get('name'), address='',
                                    tel='', lat=c[1], lon=c[0],
                                    dataset='流山ぐりーんバス GTFS', detail={}))
            if not pts:
                pts = gtfs_bus_stops()
        elif L.get('special') == 'aed':
            pts = aed_points(known)
        elif L.get('special') == 'station':
            pts = load_stations()
        else:
            seen = set()
            for d in L['ds']:
                for r in points_of(d):
                    k = (r['name'], round(r['lat'], 6), round(r['lon'], 6))
                    if k in seen:
                        continue
                    seen.add(k)
                    pts.append(r)
        known.extend(pts)
        for r in pts:
            feats.append(dict(type='Feature',
                              geometry=dict(type='Point',
                                            coordinates=[round(r['lon'], 6),
                                                         round(r['lat'], 6)]),
                              properties=dict(layer=L['id'], name=r['name'],
                                              address=r['address'], tel=r['tel'],
                                              dataset=r['dataset'],
                                              detail=r['detail'])))
        catalog.append(dict(id=L['id'], label=L['label'], group=L['group'],
                            kind=L['kind'], color=L['color'], icon=L['icon'],
                            count=len(pts)))
        print('  %-18s %4d点' % (L['label'], len(pts)))
    # --- OpenStreetMap の生活利便施設（公園は市ODの「公園」と重複するため除外） ---
    osm_p = os.path.join(ROOT, 'data', 'external', 'osm', 'poi.geojson')
    if os.path.exists(osm_p):
        osm = load(osm_p)
        by_label = collections.defaultdict(list)
        for f in osm['features']:
            lab = f['properties'].get('label') or ''
            if '公園' in lab:
                continue
            by_label[lab].append(f)
        palette = ['#e07a5f', '#81b29a', '#f2cc8f', '#3d5a80', '#98c1d9',
                   '#ee6c4d', '#a8dadc', '#cdb4db', '#ffb4a2', '#b5838d',
                   '#8ecae6', '#219ebc', '#ffb703', '#fb8500', '#adb5bd',
                   '#6d6875', '#84a59d']
        for i, (lab, fs) in enumerate(sorted(by_label.items(),
                                             key=lambda x: -len(x[1]))):
            lid = 'osm_%d' % i
            color = palette[i % len(palette)]
            for f in fs:
                pr = f['properties']
                feats.append(dict(type='Feature', geometry=f['geometry'],
                                  properties=dict(
                                      layer=lid, name=pr.get('name'),
                                      address=pr.get('addr', ''), tel='',
                                      dataset='OpenStreetMap (ODbL)',
                                      detail={k: v for k, v in pr.items()
                                              if k in ('brand', 'operator',
                                                       'opening_hours', 'kind',
                                                       'osm_id') and v})))
            # 件数が多い生活利便は密度ヒート、少ない種別は点表示
            kind = 'heat' if len(fs) >= 90 else 'plot'
            label = ('%s（密度）' % lab) if kind == 'heat' else lab
            catalog.append(dict(id=lid, label=label, group='osm', kind=kind,
                                color=color, icon='·', count=len(fs)))
        print('  OSM近隣施設 %d 種 / %d 点（公園除く）' % (
            len(by_label), sum(len(v) for v in by_label.values())))
    else:
        carry_osm_from_existing(feats, catalog)

    json.dump(dict(type='FeatureCollection', features=feats),
              io.open(os.path.join(OUT, 'map_points.geojson'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    json.dump(dict(groups=[dict(id='bunpu', label='分布・利便性'),
                           dict(id='bousai', label='防災'),
                           dict(id='kurashi', label='くらしの施設'),
                           dict(id='kotsu', label='交通'),
                           dict(id='osm', label='近隣施設（OSM）')],
                   layers=catalog,
                   hazard_note='洪水浸水想定・土砂災害警戒はハザードマップポータルの'
                               '公式タイル。町丁字境界はe-Stat（人口は境界属性の2020年）。'
                               'バス利便性・バス停本数は流山ぐりーんバスGTFSのみ'
                               '（民間路線バスは含まない。セントラルパーク駅周辺は停留所なし）。'
                               '消防水利は消火基盤密度の目安'
                               '（出動回数の地区別公開ではない）。点は市オープンデータ'
                               '（鉄道駅座標のみ一部近似）。近隣施設はOSM（公園除く）。',
                   osm_attribution='近隣施設は © OpenStreetMap contributors (ODbL)。'
                                   '公園(OSM)は市ODの公園と重複するため未掲載。'),
              io.open(os.path.join(OUT, 'map_layers.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    return len(feats)


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    print('地図レイヤー:')
    n = build_map()
    print('  合計 %d 点' % n)


if __name__ == '__main__':
    main()
