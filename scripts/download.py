# -*- coding: utf-8 -*-
"""流山市オープンデータを全件取得し、カテゴリごとのディレクトリに格納する。

再実行可能（既に取得済みで同サイズのファイルはスキップ）。
"""
import io, json, os, re, shutil, sys, time, urllib.parse
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'raw')
CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'catalog.json')
LOG = os.path.join(ROOT, 'download.log')

WIN_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {'CON', 'PRN', 'AUX', 'NUL'} | {'COM%d' % i for i in range(1, 10)} \
    | {'LPT%d' % i for i in range(1, 10)}


def safe(name, limit=80):
    """Windows で安全なパス構成要素に変換する。"""
    name = WIN_BAD.sub('_', (name or '').strip())
    name = name.replace('\u3000', ' ')
    name = re.sub(r'\s+', ' ', name).strip()
    if len(name) > limit:
        name = name[:limit].rstrip()
    name = name.rstrip('. ')
    if name.upper().split('.')[0] in RESERVED:
        name = '_' + name
    return name or '_'


def log(msg):
    line = time.strftime('%Y-%m-%d %H:%M:%S ') + msg
    print(line, flush=True)
    with io.open(LOG, 'a', encoding='utf-8') as fh:
        fh.write(line + '\n')


SIZE_RE = re.compile(r'^([\d.,]+)\s*(KB|MB|GB|BYTES|B)$', re.I)
MULT = {'KB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3, 'B': 1, 'BYTES': 1}


def expected_bytes(text):
    m = SIZE_RE.match((text or '').strip())
    if not m:
        return None
    return float(m.group(1).replace(',', '')) * MULT[m.group(2).upper()]


def plausible(actual, declared):
    """公称サイズは丸められているため 15% + 2KB の許容幅で判定。"""
    if declared is None:
        return actual > 0
    return abs(actual - declared) <= max(declared * 0.15, 2048)


def fetch(session, url, dest, declared):
    if os.path.exists(dest) and plausible(os.path.getsize(dest), declared):
        return 'skip', os.path.getsize(dest)
    tmp = dest + '.part'
    last = None
    for attempt in range(1, 4):
        try:
            with session.get(url, timeout=120, stream=True) as r:
                r.raise_for_status()
                with io.open(tmp, 'wb') as fh:
                    for chunk in r.iter_content(65536):
                        fh.write(chunk)
            os.replace(tmp, dest)
            return 'ok', os.path.getsize(dest)
        except Exception as exc:                      # noqa: BLE001
            last = exc
            if os.path.exists(tmp):
                os.remove(tmp)
            if attempt < 3:
                time.sleep(2 * attempt)
    raise last


def main():
    cat = json.load(io.open(CATALOG, encoding='utf-8'))
    datasets, master = cat['datasets'], cat['master']
    categories = master['categories']

    session = requests.Session()
    session.headers['User-Agent'] = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) opendata-archiver/1.0')

    if not os.path.isdir(OUT):
        os.makedirs(OUT)

    by_cat = {}
    for ds in datasets:
        for code in ds.get('category') or ['c_00']:
            by_cat.setdefault(code, []).append(ds)

    seen = {}          # url -> already-downloaded local path (重複DL回避)
    manifest = []
    stats = dict(ok=0, skip=0, copy=0, fail=0, bytes=0)

    for code in sorted(by_cat):
        label = categories.get(code, 'その他')
        cdir = os.path.join(OUT, '%s_%s' % (code, safe(label, 60)))
        if not os.path.isdir(cdir):
            os.makedirs(cdir)
        items = by_cat[code]
        log('=== %s %s : %d データセット ===' % (code, label, len(items)))

        for ds in items:
            ddir = os.path.join(
                cdir, '%03d_%s' % (ds['index'], safe(ds.get('name') or ds['page_title'])))
            if not os.path.isdir(ddir):
                os.makedirs(ddir)

            meta = dict(ds)
            meta['category_labels'] = [categories.get(c, c) for c in ds.get('category') or []]
            meta['license_label'] = master['licenses'].get(ds.get('license'), ds.get('license'))
            json.dump(meta, io.open(os.path.join(ddir, 'dataset.json'), 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=1)

            used = set()
            for f in ds.get('files') or []:
                url = f['file_path']
                base = urllib.parse.unquote(
                    os.path.basename(urllib.parse.urlparse(url).path)) or 'file'
                base = safe(base, 100)
                stem, ext = os.path.splitext(base)
                n = 1
                while base.lower() in used:
                    n += 1
                    base = '%s_%d%s' % (stem, n, ext)
                used.add(base.lower())
                dest = os.path.join(ddir, base)
                declared = expected_bytes(f.get('file_size'))

                row = dict(category=code, category_label=label, dataset_index=ds['index'],
                           dataset_name=ds.get('name'), page_title=ds.get('page_title'),
                           page_url=ds.get('url'), file_label=f.get('file_label'),
                           format=f.get('file_name'), declared_size=f.get('file_size'),
                           url=url, path=os.path.relpath(dest, ROOT))
                try:
                    if url in seen and os.path.exists(seen[url]):
                        if not (os.path.exists(dest)
                                and os.path.getsize(dest) == os.path.getsize(seen[url])):
                            shutil.copyfile(seen[url], dest)
                        status, size = 'copy', os.path.getsize(dest)
                    else:
                        status, size = fetch(session, url, dest, declared)
                        seen[url] = dest
                        if status == 'ok':
                            time.sleep(0.3)          # サーバ負荷に配慮
                    stats[status] += 1
                    stats['bytes'] += size
                    row.update(status=status, bytes=size)
                    if status == 'ok':
                        log('  [%s] %s (%d bytes)' % (status, row['path'], size))
                except Exception as exc:             # noqa: BLE001
                    stats['fail'] += 1
                    row.update(status='fail', bytes=0, error=repr(exc)[:300])
                    log('  [FAIL] %s <- %s : %r' % (row['path'], url, exc))
                manifest.append(row)

        json.dump(dict(category=code, label=label, dataset_count=len(items),
                       datasets=[dict(index=d['index'], name=d.get('name'),
                                      page_title=d.get('page_title'), url=d.get('url'),
                                      files=len(d.get('files') or [])) for d in items]),
                  io.open(os.path.join(cdir, '_category.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)

    json.dump(manifest, io.open(os.path.join(ROOT, 'manifest.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    import csv
    with io.open(os.path.join(ROOT, 'manifest.csv'), 'w', encoding='utf-8-sig', newline='') as fh:
        cols = ['category', 'category_label', 'dataset_index', 'dataset_name', 'page_title',
                'file_label', 'format', 'declared_size', 'bytes', 'status', 'path', 'url',
                'page_url']
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(manifest)

    log('完了: 取得%(ok)d / スキップ%(skip)d / 複製%(copy)d / 失敗%(fail)d' % stats)
    log('合計 %.1f MB' % (stats['bytes'] / 1024 ** 2))
    return 1 if stats['fail'] else 0


if __name__ == '__main__':
    sys.exit(main())
