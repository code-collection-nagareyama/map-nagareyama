# -*- coding: utf-8 -*-
"""地図データを最初から作り直す。

    python scripts/build_all.py            # 全部
    python scripts/build_all.py --skip-raw # data/raw が既にある前提で再生成だけ

段階:
  1. download          流山市オープンデータを data/raw に取得（約545MB・時間がかかる）
  2. convert           Excel/CSV を data/json に変換
  3. boundaries        e-Stat 町丁字境界（人口・世帯つき）
  4. school_districts  国土数値情報 小/中学校区
  5. hazards           ハザードタイルのメタと避難所
  6. osm_poi           OSM の生活利便施設（Overpass API）
  7. spatial           バス停・駅の座標レイヤー
  8. menu_data         map_points.geojson / map_layers.json
  9. access_grid       バス利便性150mグリッド
 10. map_overlays      バス停本数バブル、map_layers の密度指定
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

RAW_STEPS = [
    ('download', 'download.py'),
    ('convert', 'convert_to_json.py'),
]
STEPS = [
    ('boundaries', 'fetch_boundaries.py'),
    ('school_districts', 'fetch_school_districts.py'),
    ('hazards', 'fetch_hazards.py'),
    ('osm_poi', 'fetch_osm_poi.py'),
    ('spatial', 'export_spatial.py'),
    ('menu_data', 'build_menu_data.py'),
    ('access_grid', 'build_access_grid.py'),
    ('map_overlays', 'build_map_overlays.py'),
]


def run(label, script):
    print('\n===== %s (%s) =====' % (label, script), flush=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, script)])
    if r.returncode:
        raise SystemExit('%s が失敗しました (exit %d)' % (script, r.returncode))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-raw', action='store_true',
                    help='data/raw と data/json の再取得・再変換を飛ばす')
    a = ap.parse_args()
    steps = (STEPS if a.skip_raw else RAW_STEPS + STEPS)
    for label, script in steps:
        run(label, script)
    print('\n完了。web/public/data/ を確認してください。')


if __name__ == '__main__':
    main()
