# -*- coding: utf-8 -*-
"""data/raw/ の Excel・CSV を UTF-8 JSON に変換して data/json/ に出力する。

    pip install openpyxl xlrd msoffcrypto-tool
    python scripts/convert_to_json.py

目的:
  - .xls / .xlsx はバイナリで VSCode では開けない
  - .csv の多くは cp932 で、VSCode では文字化けする
  これらを UTF-8 の JSON（BOMなし・ensure_ascii=False）に変換し、
  そのままエディタで読める形にする。

出力形式（1行1レコードで整形するため独自に直列化している）:
  {
   "source": { 元ファイルの情報・エンコーディング・SHA256 },
   "sheets": [ { "name", "header_row", "columns", "n_rows", "rows": [ [...], ... ] } ]
  }

再実行可能。出力が元ファイルより新しければスキップする。
"""
import csv, datetime, hashlib, io, json, os, re, sys, time, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'data', 'raw')
OUT = os.path.join(ROOT, 'data', 'json')

ENCODINGS = ['utf-8-sig', 'cp932', 'utf-8', 'euc-jp']
EXCEL_EXT = {'.xls', '.xlsx', '.xlsm'}
MAX_SCAN = 25          # ヘッダー行推定に使う行数


# ---------------------------------------------------------------- 値の正規化
def norm(v):
    """セル値を JSON で扱える型に落とす。"""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        if v != v or v in (float('inf'), float('-inf')):
            return None
        return int(v) if v.is_integer() else v
    if isinstance(v, int):
        return v
    if isinstance(v, (datetime.datetime,)):
        return v.isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, datetime.time):
        return v.strftime('%H:%M:%S')
    s = str(v).replace('　', ' ')
    return re.sub(r'[ \t]+', ' ', s).strip()


def pick_header(rows):
    """自治体Excel特有の上部タイトル行を避けて見出し行を推定する。"""
    best, best_score = 0, -1e9
    maxfill = max((sum(1 for c in r if c not in (None, '')) for r in rows[:MAX_SCAN]),
                  default=0)
    if not maxfill:
        return 0
    for i, r in enumerate(rows[:MAX_SCAN]):
        cells = [c for c in r if c not in (None, '')]
        if len(cells) < 2:
            continue
        fill = len(cells) / maxfill
        uniq = len(set(map(str, cells))) / len(cells)
        numeric = sum(1 for c in cells if isinstance(c, (int, float))) / len(cells)
        nxt = 0.0
        if i + 1 < len(rows):
            nxt = sum(1 for c in rows[i + 1] if c not in (None, '')) / maxfill
        score = fill * 2 + uniq * 1.5 + nxt * 1.5 - numeric * 3 - i * 0.06
        if score > best_score:
            best_score, best = score, i
    return best


def trim(rows):
    """末尾の空行・空列を落とす。"""
    while rows and all(c in (None, '') for c in rows[-1]):
        rows.pop()
    if not rows:
        return rows
    width = 0
    for r in rows:
        for j in range(len(r) - 1, -1, -1):
            if r[j] not in (None, ''):
                width = max(width, j + 1)
                break
    return [r[:width] for r in rows]


def sheet_obj(name, rows):
    rows = trim([[norm(c) for c in r] for r in rows])
    h = pick_header(rows) if rows else 0
    cols = [c for c in (rows[h] if h < len(rows) else []) if c not in (None, '')]
    return dict(name=name, header_row=h, columns=cols,
                n_rows=len(rows), n_cols=max((len(r) for r in rows), default=0),
                rows=rows)


# ---------------------------------------------------------------- 読み込み
def xls_bytes(path):
    raw = io.open(path, 'rb').read()
    try:
        import msoffcrypto
        f = msoffcrypto.OfficeFile(io.BytesIO(raw))
        if f.is_encrypted():
            buf = io.BytesIO()
            f.load_key(password='VelvetSweatshop')   # Excel既定の書込保護パスワード
            f.decrypt(buf)
            return buf.getvalue(), True
    except Exception:
        pass
    return raw, False


def read_xlsx(data):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        out.append(sheet_obj(ws.title, [list(r) for r in ws.iter_rows(values_only=True)]))
    wb.close()
    return out


def read_xls(data):
    import xlrd
    bk = xlrd.open_workbook(file_contents=data)
    out = []
    for sh in bk.sheets():
        rows = []
        for i in range(sh.nrows):
            row = []
            for j in range(sh.ncols):
                t, v = sh.cell_type(i, j), sh.cell_value(i, j)
                if t == xlrd.XL_CELL_DATE:
                    try:
                        v = xlrd.xldate.xldate_as_datetime(v, bk.datemode)
                    except Exception:
                        pass
                elif t == xlrd.XL_CELL_BOOLEAN:
                    v = bool(v)
                elif t in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                    v = None
                elif t == xlrd.XL_CELL_ERROR:
                    v = None
                row.append(v)
            rows.append(row)
        out.append(sheet_obj(sh.name, rows))
    return out


def decode(raw):
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode('cp932', 'replace'), 'cp932(replace)'


def read_csv_bytes(raw, name):
    txt, enc = decode(raw)
    head = txt[:4000]
    try:
        delim = csv.Sniffer().sniff(head, delimiters=',\t;').delimiter
    except Exception:
        delim = '\t' if head.count('\t') > head.count(',') else ','
    rows = list(csv.reader(io.StringIO(txt, newline=''), delimiter=delim))
    return sheet_obj(name, rows), enc, delim


# ---------------------------------------------------------------- 直列化
def write_json(path, obj):
    """rows を1行1レコードで書き出す（VSCodeで読みやすくするため）。"""
    sheets = obj.pop('sheets')
    parts = ['{', ' "source": %s,' % json.dumps(obj['source'], ensure_ascii=False),
             ' "sheets": [']
    for si, sh in enumerate(sheets):
        rows = sh.pop('rows')
        head = json.dumps(sh, ensure_ascii=False)[:-1]        # 末尾の } を外す
        parts.append('  %s,' % head)
        parts.append('   "rows": [')
        for ri, r in enumerate(rows):
            parts.append('    %s%s' % (json.dumps(r, ensure_ascii=False),
                                       ',' if ri < len(rows) - 1 else ''))
        parts.append('   ]')
        parts.append('  }%s' % (',' if si < len(sheets) - 1 else ''))
        sh['rows'] = rows
    parts.append(' ]')
    parts.append('}')
    io.open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(parts) + '\n')
    obj['sheets'] = sheets


def sha256(path):
    h = hashlib.sha256()
    with io.open(path, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------- 本体
def convert(path, index):
    rel = os.path.relpath(path, SRC)
    ext = os.path.splitext(path)[1].lower()
    dest = os.path.join(OUT, rel + '.json')
    ddir = os.path.dirname(dest)
    if not os.path.isdir(ddir):
        os.makedirs(ddir)
    if os.path.exists(dest) and os.path.getmtime(dest) >= os.path.getmtime(path):
        index.append(dict(source=rel.replace(os.sep, '/'), status='skip',
                          json=os.path.relpath(dest, ROOT).replace(os.sep, '/')))
        return 'skip', None

    src = dict(path='data/raw/' + rel.replace(os.sep, '/'),
               bytes=os.path.getsize(path), sha256=sha256(path))
    sheets, enc = [], None

    # 拡張子は当てにならない（.csv の実体が xlsx、.xls の実体が xlsx 等）。
    # 先頭バイトで実形式を判定する。
    magic = io.open(path, 'rb').read(8)
    is_ole = magic[:4] == b'\xd0\xcf\x11\xe0'
    is_pk = magic[:2] == b'PK'

    if ext in EXCEL_EXT or (ext == '.csv' and (is_pk or is_ole)):
        if is_ole or (ext == '.xls' and not is_pk):
            data, decrypted = xls_bytes(path)
        else:
            data, decrypted = io.open(path, 'rb').read(), False
        real = 'xlsx' if data[:2] == b'PK' else 'xls'
        sheets = read_xlsx(data) if real == 'xlsx' else read_xls(data)
        src.update(format=real, declared_ext=ext, decrypted=decrypted)
        if real != ext.lstrip('.'):
            src['note'] = '配布元の拡張子(%s)と実形式(%s)が一致しない' % (ext, real)
    elif ext == '.csv':
        sh, enc, delim = read_csv_bytes(io.open(path, 'rb').read(),
                                        os.path.basename(path))
        sheets = [sh]
        src.update(format='csv', source_encoding=enc, delimiter=delim)
    elif ext == '.zip':
        with zipfile.ZipFile(path) as z:
            members = [n for n in z.namelist()
                       if os.path.splitext(n)[1].lower() in ('.csv', '.txt')]
            if not members:
                return 'skip-nontable', None
            for n in sorted(members):
                sh, e, d = read_csv_bytes(z.read(n), n)
                sheets.append(sh)
            src.update(format='zip', members=len(members))
    else:
        return 'skip-nontable', None

    obj = dict(source=src, sheets=sheets)
    write_json(dest, obj)
    index.append(dict(source=src['path'], format=src['format'],
                      source_encoding=src.get('source_encoding'),
                      json=os.path.relpath(dest, ROOT).replace(os.sep, '/'),
                      sheets=len(sheets),
                      rows=sum(s['n_rows'] for s in sheets),
                      json_bytes=os.path.getsize(dest), status='ok'))
    return 'ok', dest


def main():
    targets = []
    for d, _, fs in os.walk(SRC):
        for f in fs:
            if os.path.splitext(f)[1].lower() in (EXCEL_EXT | {'.csv', '.zip'}):
                targets.append(os.path.join(d, f))
    targets.sort()
    print('対象 %d ファイル' % len(targets))

    index, stats = [], dict(ok=0, skip=0, nontable=0, fail=0)
    fails = []
    for i, p in enumerate(targets, 1):
        try:
            st, _ = convert(p, index)
            if st == 'ok':
                stats['ok'] += 1
            elif st == 'skip':
                stats['skip'] += 1
            else:
                stats['nontable'] += 1
        except Exception as exc:                       # noqa: BLE001
            stats['fail'] += 1
            fails.append((os.path.relpath(p, SRC), repr(exc)[:180]))
            print('  [FAIL] %s %r' % (os.path.relpath(p, SRC), exc), flush=True)
        if i % 50 == 0:
            print('  %d/%d' % (i, len(targets)), flush=True)

    # 索引は出力ディレクトリを走査して作る。
    # （スキップした分も含めて常に全件を反映させるため）
    index = []
    for d, _, fs in os.walk(OUT):
        for f in sorted(fs):
            if not f.endswith('.json') or f.startswith('_'):
                continue
            p = os.path.join(d, f)
            try:
                o = json.load(io.open(p, encoding='utf-8'))
            except Exception:                          # noqa: BLE001
                continue
            s = o.get('source', {})
            shs = o.get('sheets', [])
            index.append(dict(
                source=s.get('path'), format=s.get('format'),
                source_encoding=s.get('source_encoding'),
                declared_ext=s.get('declared_ext'), note=s.get('note'),
                decrypted=s.get('decrypted'),
                json=os.path.relpath(p, ROOT).replace(os.sep, '/'),
                sheets=len(shs), rows=sum(x.get('n_rows', 0) for x in shs),
                json_bytes=os.path.getsize(p), status='ok'))
    index.sort(key=lambda r: r['source'] or '')

    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    json.dump(index, io.open(os.path.join(OUT, '_index.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    with io.open(os.path.join(OUT, '_index.csv'), 'w', encoding='utf-8-sig',
                 newline='') as fh:
        cols = ['source', 'format', 'source_encoding', 'declared_ext', 'note',
                'decrypted', 'sheets', 'rows', 'json_bytes', 'json', 'status']
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(index)

    total = sum(r.get('json_bytes') or 0 for r in index)
    print('変換 %(ok)d / スキップ %(skip)d / 非表形式 %(nontable)d / 失敗 %(fail)d'
          % stats)
    print('出力合計: %.1f MB' % (total / 1024 ** 2))
    for p, e in fails:
        print('  FAIL', p, e)
    return 1 if stats['fail'] else 0


if __name__ == '__main__':
    sys.exit(main())
