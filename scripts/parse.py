import json, re, io, collections, sys

html = io.open('search.html', encoding='utf-8').read()
lines = html.split('\n')

# locate the inline `var open_data = {` block
start = next(i for i, l in enumerate(lines) if l.startswith('var open_data = {'))
end = next(i for i in range(start, len(lines)) if lines[i].startswith('};'))
block = lines[start:end + 1]


def grab(prefix, lineno):
    l = block[lineno]
    assert l.startswith(prefix), l[:60]
    return json.loads(l[len(prefix):].rstrip().rstrip(','))


datasets = grab('datasets: ', 1)
categories = grab('categories: ', 3)
formats = grab('formats: ', 4)
licenses = grab('licenses: ', 5)
groups = grab('groups: ', 6)

data = {'datasets': datasets, 'master': {'categories': categories,
        'formats': formats, 'licenses': licenses, 'groups': groups}}
json.dump(data, io.open('catalog.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)

print('datasets:', len(datasets))
print('total files:', sum(len(d.get('files') or []) for d in datasets))

cnt = collections.Counter()
for d in datasets:
    for c in d.get('category') or ['(none)']:
        cnt[c] += 1
for c in sorted(categories):
    print(' ', c, categories[c], '->', cnt.get(c, 0), 'datasets')
missing = set(cnt) - set(categories)
print('unknown category codes:', missing)

# file extension spread
ext = collections.Counter()
for d in datasets:
    for f in d.get('files') or []:
        ext[f.get('file_name')] += 1
print('formats:', dict(ext))
print('datasets with image-only:', sum(1 for d in datasets if not d.get('files') and d.get('image')))
