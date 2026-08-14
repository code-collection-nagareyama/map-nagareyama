# -*- coding: utf-8 -*-
"""全タブularファイルからカラム（見出し行）を抽出して columns.json に出力する。

依存: openpyxl, xlrd
"""
import csv, io, json, os, re, sys, traceback, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'columns.json')
SCAN = 25          # ヘッダー探索のために読む行数
MAX_SHEETS = 30

ENCODINGS = ['utf-8-sig', 'cp932', 'utf-8', 'euc-jp']


def decode(raw):
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode('cp932', 'replace'), 'cp932(replace)'


def clean(v):
    if v is None:
        return ''
    s = str(v).replace('\u3000', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def pick_header(rows):
    """先頭 SCAN 行から見出し行らしい行の index を推定する。

    自治体Excelは上部にタイトル・注記行があるため、
    「非空セル数が多く」「重複が少なく」「数値ばかりでない」行を選ぶ。
    """
    best, best_score = 0, -1e9
    maxfill = max((sum(1 for c in r if c) for r in rows), default=0)
    if maxfill == 0:
        return 0
    for i, r in enumerate(rows[:SCAN]):
        cells = [c for c in r if c]
        fill = len(cells)
        if fill < 2:
            continue
        uniq = len(set(cells)) / fill
        numeric = sum(1 for c in cells if re.fullmatch(r'-?[\d,\.]+%?', c)) / fill
        # 後続行が同程度以上に埋まっていれば見出しらしい
        nxt = 0.0
        if i + 1 < len(rows):
            nxt = sum(1 for c in rows[i + 1] if c) / maxfill
        score = (fill / maxfill) * 2 + uniq * 1.5 + nxt * 1.5 - numeric * 3 - i * 0.06
        if score > best_score:
            best_score, best = score, i
    return best


def from_matrix(rows):
    rows = [[clean(c) for c in r] for r in rows]
    rows = [r for r in rows]
    h = pick_header(rows)
    cols, seen = [], set()
    for j, c in enumerate(rows[h] if h < len(rows) else []):
        if not c:
            continue
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        cols.append(c)
    sample = rows[h + 1] if h + 1 < len(rows) else []
    return h, cols, [s for s in sample if s][:12]


def read_csv_bytes(raw):
    txt, enc = decode(raw)
    try:
        dialect = csv.Sniffer().sniff(txt[:4000], delimiters=',\t;')
        delim = dialect.delimiter
    except Exception:
        delim = '\t' if txt[:2000].count('\t') > txt[:2000].count(',') else ','
    rows = []
    for i, r in enumerate(csv.reader(io.StringIO(txt, newline=''), delimiter=delim)):
        rows.append(r)
        if i > SCAN + 5:
            break
    return rows, enc


def read_xlsx(path_or_fh):
    import openpyxl
    wb = openpyxl.load_workbook(path_or_fh, read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets[:MAX_SHEETS]:
        rows = []
        for i, r in enumerate(ws.iter_rows(values_only=True)):
            rows.append(list(r))
            if i > SCAN + 5:
                break
        out.append((ws.title, rows))
    wb.close()
    return out


def _xls_bytes(path):
    """暗号化(書き込みパスワード保護)された .xls は既定パスワードで復号する。"""
    raw = io.open(path, 'rb').read()
    try:
        import msoffcrypto
        f = msoffcrypto.OfficeFile(io.BytesIO(raw))
        if f.is_encrypted():
            buf = io.BytesIO()
            f.load_key(password='VelvetSweatshop')
            f.decrypt(buf)
            return buf.getvalue(), True
    except Exception:
        pass
    return raw, False


def read_xls(path):
    import xlrd
    data, dec = _xls_bytes(path)
    bk = xlrd.open_workbook(file_contents=data)
    out = []
    for sh in bk.sheets()[:MAX_SHEETS]:
        rows = []
        for i in range(min(sh.nrows, SCAN + 6)):
            rows.append(sh.row_values(i))
        out.append((sh.name, rows))
    return out


def main():
    man = json.load(io.open(os.path.join(ROOT, 'manifest.json'), encoding='utf-8'))
    # url 単位で重複排除（複数カテゴリに複製されているため）
    uniq, seen = [], set()
    for r in man:
        if r['url'] in seen:
            continue
        seen.add(r['url'])
        uniq.append(r)

    results, errors = [], []
    for n, r in enumerate(uniq, 1):
        path = os.path.join(ROOT, r['path'])
        ext = os.path.splitext(path)[1].lower()
        rec = dict(path=r['path'], url=r['url'], category=r['category'],
                   category_label=r['category_label'], dataset=r['dataset_name'],
                   dataset_index=r['dataset_index'], page_title=r['page_title'],
                   file_label=r['file_label'], fmt=r['format'], ext=ext, tables=[])
        try:
            if ext == '.csv' or (ext in ('.txt',) and r['format'] == 'CSV'):
                raw = io.open(path, 'rb').read()
                # 拡張子偽装対策: 実体が Excel の「CSV」が配布されている
                if raw[:2] == b'PK':
                    rec['真の形式'] = 'xlsx'
                    for name, rows in read_xlsx(io.BytesIO(raw)):
                        h, cols, samp = from_matrix(rows)
                        if cols:
                            rec['tables'].append(dict(sheet=name, header_row=h,
                                                      columns=cols, sample=samp))
                elif raw[:4] == b'\xd0\xcf\x11\xe0':
                    rec['真の形式'] = 'xls'
                    for name, rows in read_xls(path):
                        h, cols, samp = from_matrix(rows)
                        if cols:
                            rec['tables'].append(dict(sheet=name, header_row=h,
                                                      columns=cols, sample=samp))
                else:
                    rows, enc = read_csv_bytes(raw)
                    h, cols, samp = from_matrix(rows)
                    rec['encoding'] = enc
                    if cols:
                        rec['tables'].append(dict(sheet=None, header_row=h,
                                                  columns=cols, sample=samp))
            elif ext in ('.xlsx', '.xlsm', '.xls'):
                # 拡張子が実体と一致しない配布物があるためマジックバイトで判定
                magic = io.open(path, 'rb').read(4)
                is_x = magic[:2] == b'PK'
                rec['真の形式'] = 'xlsx' if is_x else 'xls'
                # openpyxl は拡張子で判定するため、実体がxlsxなら BytesIO で渡す
                src = io.BytesIO(io.open(path, 'rb').read()) if is_x else path
                for name, rows in (read_xlsx(src) if is_x else read_xls(src)):
                    h, cols, samp = from_matrix(rows)
                    if cols:
                        rec['tables'].append(dict(sheet=name, header_row=h,
                                                  columns=cols, sample=samp))
            elif ext == '.zip':
                z = zipfile.ZipFile(path)
                rec['zip_entries'] = z.namelist()[:200]
                for nm in z.namelist():
                    e = os.path.splitext(nm)[1].lower()
                    if e == '.csv':
                        rows, enc = read_csv_bytes(z.read(nm))
                        h, cols, samp = from_matrix(rows)
                        if cols:
                            rec['tables'].append(dict(sheet=nm, header_row=h,
                                                      columns=cols, sample=samp))
                    elif e in ('.xlsx', '.xlsm'):
                        for name, rows in read_xlsx(io.BytesIO(z.read(nm))):
                            h, cols, samp = from_matrix(rows)
                            if cols:
                                rec['tables'].append(
                                    dict(sheet='%s!%s' % (nm, name), header_row=h,
                                         columns=cols, sample=samp))
                    elif e == '.txt' and re.search(r'gtfs|feed', path, re.I):
                        rows, enc = read_csv_bytes(z.read(nm))
                        h, cols, samp = from_matrix(rows)
                        if cols:
                            rec['tables'].append(dict(sheet=nm, header_row=0,
                                                      columns=rows[0] if rows else [],
                                                      sample=samp))
            else:
                rec['skipped'] = 'non-tabular'
        except Exception as exc:                       # noqa: BLE001
            rec['error'] = repr(exc)[:200]
            errors.append((r['path'], repr(exc)[:160]))
        results.append(rec)
        if n % 50 == 0:
            print('  %d/%d' % (n, len(uniq)), flush=True)

    json.dump(results, io.open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    tab = sum(1 for r in results if r['tables'])
    print('files:', len(results), '| with tables:', tab, '| errors:', len(errors))
    for p, e in errors[:15]:
        print('  ERR', p, e)


if __name__ == '__main__':
    main()
