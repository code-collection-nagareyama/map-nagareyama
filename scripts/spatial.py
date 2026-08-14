# -*- coding: utf-8 -*-
"""地名（字）・駅・バス停・施設ポイントを実データ値から抽出し、
地図選択から知識グラフを引けるようにする空間レイヤーを構築する。
"""
import collections, io, json, os, re, zipfile
import extract_columns as EX

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, 'data', 'derived')

LAT_COL = re.compile(r'^(緯度|lat|latitude|stop_lat|y)$', re.I)
LON_COL = re.compile(r'^(経度|lon|lng|longitude|stop_lon|x)$', re.I)
NAME_COL = re.compile(r'^(名称|施設名|名前|stop_name|公園名|店舗名|拠点名|投票所名)$')
ADDR_COL = re.compile(r'^(所在地|住所|方書|location)$')
KANA_COL = re.compile(r'^(名称_?カナ|よみ|ふりがな)$')
STATION_COL = re.compile(r'(隣接駅|最寄.?駅|アクセス（最寄り駅）)')
LINE_COL = re.compile(r'^(路線|線名|route_long_name)$')

# 流山市に実在する鉄道駅（データ中の出現から確定させるための参照リスト）
KNOWN_LINES = {
    'つくばエクスプレス': ['南流山駅', '流山セントラルパーク駅', '流山おおたかの森駅'],
    '東武アーバンパークライン': ['初石駅', '流山おおたかの森駅', '豊四季駅', '江戸川台駅', '運河駅'],
    '流鉄流山線': ['流山駅', '平和台駅', '鰭ヶ崎駅', '小金城趾駅'],
    'JR武蔵野線': ['南流山駅'],
}
# 市外だが最寄駅として回答に現れる隣接駅
ADJACENT = ['北小金駅', '南柏駅', '柏の葉キャンパス駅', '柏駅', '梅郷駅', '流山セントラルパーク駅']
ALL_STATIONS = sorted({s for v in KNOWN_LINES.values() for s in v} | set(ADJACENT),
                      key=len, reverse=True)
LINES_OF = collections.defaultdict(list)
for _ln, _ss in KNOWN_LINES.items():
    for _s in _ss:
        LINES_OF[_s].append(_ln)


def read_rows(path, limit=100000):
    """ファイルの全行を (columns, rows) で返す。"""
    ext = os.path.splitext(path)[1].lower()
    out = []
    if ext == '.csv':
        raw = io.open(path, 'rb').read()
        txt, enc = EX.decode(raw)
        import csv as _csv
        rows = list(_csv.reader(io.StringIO(txt, newline='')))
        out.append((None, rows))
    elif ext in ('.xlsx', '.xlsm', '.xls'):
        magic = io.open(path, 'rb').read(4)
        if magic[:2] == b'PK':
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(io.open(path, 'rb').read()),
                                        read_only=True, data_only=True)
            for ws in wb.worksheets:
                rows = [list(r) for i, r in
                        enumerate(ws.iter_rows(values_only=True)) if i < limit]
                out.append((ws.title, rows))
            wb.close()
        else:
            import xlrd
            data, _ = EX._xls_bytes(path)
            bk = xlrd.open_workbook(file_contents=data)
            for sh in bk.sheets():
                out.append((sh.name, [sh.row_values(i)
                                      for i in range(min(sh.nrows, limit))]))
    return out


def clean(v):
    return EX.clean(v)


def load_aza():
    """字（あざ）マスタを読み込む。"""
    p = os.path.join(ROOT, r'data\raw\c_18_その他の情報\039_流山市内字（あざ）一覧表'
                           r'\070303-shinai-aza.csv')
    aza = []
    for _, rows in read_rows(p):
        hdr = [clean(c) for c in rows[0]]
        for r in rows[1:]:
            r = [clean(c) for c in r]
            if r and r[0]:
                aza.append(dict(name=r[0], kana=r[1] if len(r) > 1 else ''))
    return aza


NOISE_STATION = re.compile(
    r'^(無回答|その他|利用していない|不明|該当なし|-|‐|―|0|\d+)駅$')
STN_PREFIX = re.compile(r'^(JR|ＪＲ|TX|ＴＸ|つくばエクスプレス線?|東武アーバンパークライン|'
                        r'東武野田線|流鉄流山線|流山電鉄|流鉄)\s*')
STN_SUFFIX = re.compile(r'[<＜(（].*?[>＞)）]')


def canon_station(s):
    """『南流山駅＜ＪＲ＞駅』『TX 南流山駅』等を正規の駅名に寄せる。

    アンケート選択肢由来のノイズ（無回答・その他等）は None を返す。
    """
    s = clean(s)
    if not s:
        return None
    s = STN_SUFFIX.sub('', s)
    s = re.sub(r'駅+$', '', s)
    s = STN_PREFIX.sub('', s).strip()
    s = re.sub(r'\s+', '', s)
    if not s:
        return None
    name = s + '駅'
    if NOISE_STATION.match(name):
        return None
    if s.endswith('線'):          # 『武蔵野線』等は路線名であって駅名ではない
        return None
    # 正式名の一部（『おおたかの森』→『流山おおたかの森駅』）も正規名に寄せる
    for canon in ALL_STATIONS:
        base = canon[:-1]
        if base in s or (len(s) >= 4 and s in base):
            return canon
    if len(s) > 12 or re.search(r'[0-9０-９]', s):
        return None
    return name


TOWN_RE = re.compile(r'^([^\d０-９]+?)(?=[\d０-９]|丁目|$)')


def extract_town(addr):
    """『平和台1-1-1』『おおたかの森東2-5-3』から町名を取り出す。"""
    a = norm_addr(addr)
    if not a:
        return None
    m = TOWN_RE.match(a)
    if not m:
        return None
    t = m.group(1).strip('　 ・')
    t = re.sub(r'(大字|字)', '', t)
    if not t or len(t) > 12:
        return None
    return t


def norm_addr(a):
    a = clean(a)
    a = re.sub(r'^.*?流山市', '', a)
    a = a.replace('ケ', 'ヶ').replace('ガ', 'ヶ')
    return a


def match_place(addr, names_sorted):
    """住所文字列から最長一致する字名を返す。"""
    a = norm_addr(addr)
    if not a:
        return None
    for n in names_sorted:
        nn = n.replace('ケ', 'ヶ').replace('ガ', 'ヶ')
        if a.startswith(nn):
            return n
    for n in names_sorted:
        nn = n.replace('ケ', 'ヶ').replace('ガ', 'ヶ')
        if nn in a:
            return n
    return None


def to_float(v):
    try:
        f = float(str(v).strip())
        return f
    except Exception:
        return None


def main():
    cols_data = json.load(io.open(os.path.join(HERE, 'columns.json'), encoding='utf-8'))
    aza = load_aza()
    aza_names = sorted({a['name'] for a in aza}, key=len, reverse=True)
    kana_of = {a['name']: a['kana'] for a in aza}
    print('字マスタ:', len(aza_names))

    features = []       # 地物ポイント
    stations = collections.defaultdict(lambda: dict(lines=set(), sources=set(), pts=[]))
    seen_files = set()

    for rec in cols_data:
        path = os.path.join(ROOT, rec['path'])
        if rec['path'] in seen_files or not rec['tables']:
            continue
        seen_files.add(rec['path'])
        has_geo = any(any(LAT_COL.match(c) for c in t['columns']) and
                      any(LON_COL.match(c) for c in t['columns']) for t in rec['tables'])
        has_stn = any(any(STATION_COL.search(c) for c in t['columns']) for t in rec['tables'])
        if not (has_geo or has_stn):
            continue
        if rec['ext'] == '.zip':
            continue
        try:
            sheets = read_rows(path)
        except Exception as exc:                       # noqa: BLE001
            print('  read err', rec['path'], repr(exc)[:80])
            continue

        for t in rec['tables']:
            hi = t['header_row']
            cols = t['columns']
            target = None
            for name, rows in sheets:
                if t.get('sheet') in (None, name) and hi < len(rows):
                    target = rows
                    break
            if target is None:
                continue
            hdr = [clean(c) for c in target[hi]]
            ix = {}
            for j, h in enumerate(hdr):
                if LAT_COL.match(h) and 'lat' not in ix:
                    ix['lat'] = j
                elif LON_COL.match(h) and 'lon' not in ix:
                    ix['lon'] = j
                elif NAME_COL.match(h) and 'name' not in ix:
                    ix['name'] = j
                elif ADDR_COL.match(h) and 'addr' not in ix:
                    ix['addr'] = j
                elif KANA_COL.match(h) and 'kana' not in ix:
                    ix['kana'] = j
                elif STATION_COL.search(h) and 'stn' not in ix:
                    ix['stn'] = j
                elif LINE_COL.match(h) and 'line' not in ix:
                    ix['line'] = j
            for row in target[hi + 1:]:
                row = [clean(c) for c in row]
                if not any(row):
                    continue
                lat = to_float(row[ix['lat']]) if 'lat' in ix and ix['lat'] < len(row) else None
                lon = to_float(row[ix['lon']]) if 'lon' in ix and ix['lon'] < len(row) else None
                # x/y 列は経度/緯度の順が逆のことがあるため値域で補正
                if lat is not None and lon is not None:
                    if 138 < lat < 141 and 34 < lon < 37:
                        lat, lon = lon, lat
                    if not (35.7 < lat < 36.1 and 139.7 < lon < 140.1):
                        lat = lon = None
                nm = row[ix['name']] if 'name' in ix and ix['name'] < len(row) else ''
                ad = row[ix['addr']] if 'addr' in ix and ix['addr'] < len(row) else ''
                st = row[ix['stn']] if 'stn' in ix and ix['stn'] < len(row) else ''
                ln = row[ix['line']] if 'line' in ix and ix['line'] < len(row) else ''
                if st:
                    for s in re.split(r'[、,／/・]', st):
                        cs = canon_station(s)
                        if not cs:
                            continue
                        stations[cs]['sources'].add(rec['dataset'])
                        if ln:
                            stations[cs]['lines'].add(ln)
                        if lat and lon:
                            stations[cs]['pts'].append((lat, lon))
                if lat and lon and (nm or ad):
                    features.append(dict(
                        name=nm, kana=row[ix['kana']] if 'kana' in ix and ix['kana'] < len(row) else '',
                        address=ad, lat=lat, lon=lon, place=None,
                        station=canon_station(st) if st else None,
                        dataset=rec['dataset'], dataset_index=rec['dataset_index'],
                        category=rec['category_label'], path=rec['path']))

    # --- ガゼッティア統合 --------------------------------------------------
    # (1) 字マスタ (2) 住所から抽出した町名 (3) 表中の字名カラムの実値
    origin = collections.defaultdict(set)
    for n in aza_names:
        origin[n].add('字一覧表')

    town_count = collections.Counter()
    for f in features:
        t = extract_town(f['address'])
        if t:
            town_count[t] += 1
    for t, c in town_count.items():
        if c >= 2 or t in origin:            # 1件のみの町名は誤抽出の恐れ
            origin[t].add('住所')

    AZA_COL = re.compile(r'^(字\s*名|町丁字?名?|大字名?)$')
    for rec in cols_data:
        for t in rec['tables']:
            if not any(AZA_COL.match(c) for c in t['columns']):
                continue
            try:
                sheets = read_rows(os.path.join(ROOT, rec['path']))
            except Exception:
                continue
            for name, rows in sheets:
                if t.get('sheet') not in (None, name) or t['header_row'] >= len(rows):
                    continue
                hdr = [clean(c) for c in rows[t['header_row']]]
                js = [j for j, h in enumerate(hdr) if AZA_COL.match(h)]
                for row in rows[t['header_row'] + 1:]:
                    for j in js:
                        if j < len(row):
                            v = clean(row[j])
                            if v and 1 < len(v) <= 12 and not re.search(r'[0-9０-９]', v) \
                                    and v not in ('総数', '合計', '計', '字名'):
                                origin[v].add('町丁字別人口')

    all_names = sorted(origin, key=len, reverse=True)
    for f in features:
        f['place'] = match_place(f['address'], all_names) if f['address'] else None
    print('ガゼッティア: %d件（字一覧%d / 住所由来%d / 人口表由来%d）'
          % (len(all_names),
             sum(1 for v in origin.values() if '字一覧表' in v),
             sum(1 for v in origin.values() if '住所' in v),
             sum(1 for v in origin.values() if '町丁字別人口' in v)))

    # --- GTFS バス停 ---
    gtfs = os.path.join(ROOT, r'data\raw\c_03_道路・交通\900_流山ぐりーんバス GTFSデータ\feed.zip')
    bus_stops, bus_routes = [], []
    if os.path.exists(gtfs):
        z = zipfile.ZipFile(gtfs)
        import csv as _csv
        txt, _ = EX.decode(z.read('stops.txt'))
        for r in _csv.DictReader(io.StringIO(txt, newline='')):
            la, lo = to_float(r.get('stop_lat')), to_float(r.get('stop_lon'))
            if la and lo:
                bus_stops.append(dict(stop_id=r.get('stop_id'), name=r.get('stop_name'),
                                      lat=la, lon=lo,
                                      place=match_place(r.get('stop_name') or '', all_names)))
        txt, _ = EX.decode(z.read('routes.txt'))
        for r in _csv.DictReader(io.StringIO(txt, newline='')):
            bus_routes.append(dict(route_id=r.get('route_id'),
                                   short=r.get('route_short_name'),
                                   long=r.get('route_long_name')))

    # --- 字ごとの集約 ---
    by_place = collections.defaultdict(lambda: dict(features=[], datasets=set()))
    for f in features:
        if f['place']:
            by_place[f['place']]['features'].append(f)
            by_place[f['place']]['datasets'].add((f['dataset_index'], f['dataset']))
    for b in bus_stops:
        if b['place']:
            by_place[b['place']]['datasets'].add((900, '流山ぐりーんバス　GTFSデータ'))

    places = []
    for name in sorted(origin):
        d = by_place.get(name)
        pts = [(f['lat'], f['lon']) for f in (d['features'] if d else [])]
        c = None
        if pts:
            c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        places.append(dict(
            name=name, kana=kana_of.get(name, ''), sources=sorted(origin[name]),
            centroid=dict(lat=round(c[0], 6), lon=round(c[1], 6)) if c else None,
            n_features=len(pts),
            datasets=sorted([dict(index=i, name=n) for i, n in
                             (d['datasets'] if d else set())], key=lambda x: x['index'])))

    st_out = []
    for s, v in sorted(stations.items()):
        pts = v['pts']
        c = None
        if pts:
            c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        lines = sorted(set(v['lines']) | set(LINES_OF.get(s, [])))
        st_out.append(dict(name=s, lines=lines,
                           approx_centroid=dict(lat=round(c[0], 6), lon=round(c[1], 6)) if c else None,
                           n_source_points=len(pts), sources=sorted(v['sources'])))

    print('features: %d (字判定済 %d) | 駅 %d | バス停 %d | 字with地物 %d'
          % (len(features), sum(1 for f in features if f['place']),
             len(st_out), len(bus_stops), sum(1 for p in places if p['n_features'])))
    return aza, places, features, st_out, bus_stops, bus_routes


if __name__ == '__main__':
    main()
