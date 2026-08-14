# 流山マップ

流山市のオープンデータを地図に重ねて見るための単機能アプリ。
`data-nagareyama` の「地図で見る」機能だけを切り出したもの。

表示できるもの:

- **施設の点** — 避難所・災害用井戸・AED・公園・公衆トイレ・文化財・公共施設・子育て・福祉・医療・駐輪場・バス停・鉄道駅・投票所
- **近隣施設（OSM）** — 飲食店・コンビニ・スーパー・診療所など（件数の多い種別は密度ヒートマップ）
- **学区** — 小学校区 / 中学校区のポリゴン
- **ハザード** — 洪水浸水想定・浸水継続時間・家屋倒壊等氾濫想定・土砂災害警戒区域（国のハザードマップポータルの公式タイル）
- **分布・利便性** — バス利便性150mグリッド、バス停本数バブル、町丁字人口の塗り分け、消防水利/公園/子育て施設の密度

## 構成

```
web/                Vite + React + MapLibre GL + deck.gl のフロントエンド
  src/components/FacilityMap.tsx   地図本体（レイヤ切替・凡例・ポップアップ）
  public/data/                     アプリが fetch する完成データ（コミット済み）
scripts/            データ生成のパイプライン（Python）
data/derived/       パイプラインの中間生成物（gitignore）
data/raw/           流山市オープンデータの原本（gitignore・約545MB）
```

## 動かす

```bash
npm install --prefix web
```

```bash
npm run dev --prefix web
```

`web/public/data/` は生成済みのものをコミットしてあるので、
表示するだけならデータパイプラインを動かす必要はない。

本番ビルドは `npm run build --prefix web`（出力は `web/dist/`）。
`vite.config.ts` の `base: './'` により、静的ホスティングにそのまま置ける。

## データを作り直す

```bash
pip install -r requirements.txt
```

```bash
python scripts/build_all.py
```

段階は次のとおり。`--skip-raw` を付けると 1・2 を飛ばす。

| # | スクリプト | 生成物 | 取得元 |
|---|---|---|---|
| 1 | `download.py` | `data/raw/` | 流山市オープンデータカタログ |
| 2 | `convert_to_json.py` | `data/json/` | （1 の Excel/CSV を UTF-8 JSON 化） |
| 3 | `fetch_boundaries.py` | `boundaries.geojson` | e-Stat 2020年国勢調査 小地域境界 |
| 4 | `fetch_school_districts.py` | `school_districts_{elem,junior}.geojson` | 国土数値情報 A27 / A32（2023） |
| 5 | `fetch_hazards.py` | `hazards_raster.json` ほか | ハザードマップポータル |
| 6 | `fetch_osm_poi.py` | `data/external/osm/poi.geojson` | OpenStreetMap Overpass API |
| 7 | `export_spatial.py` | `data/derived/spatial/` | （2 からバス停・駅の座標を抽出） |
| 8 | `build_menu_data.py` | `map_points.geojson` / `map_layers.json` | （2・6・7 を統合） |
| 9 | `build_access_grid.py` | `access_grid.json` | （GTFS からバス利便性グリッドを算出） |
| 10 | `build_map_overlays.py` | `bus_stop_freq.geojson` | （GTFS から停留所別の平日出発本数） |

3〜6 は外部サイトへの取得なので、1・2 が無くても単体で動く。
8〜10 は `data/json/`（＝1・2）が必要。

`export_spatial.py` は地図が使わないファイル（字・施設の一覧など）も
`data/derived/spatial/` に出すが、地図が読むのは `bus_stops.geojson` と
`stations.json` の2つだけ。

## 出典

- 流山市オープンデータ — [カタログサイト](https://www.city.nagareyama.chiba.jp/opendata/1042063/1042065.html)。データセットごとに CC BY / CC BY-NC-ND
- 政府統計の総合窓口(e-Stat) — 2020年国勢調査 小地域（町丁・字等）境界。人口・世帯数は境界属性
- 国土数値情報（国土交通省） — 小学校区(A27)・中学校区(A32) 2023。**参考表示であり、最新の通学指定は市の公式情報を確認すること**
- ハザードマップポータルサイト — 洪水・土砂の公式タイル
- OpenStreetMap contributors — 近隣施設（ODbL）。公園は市オープンデータと重複するため未掲載
- 背景地図 — [CARTO](https://carto.com/attributions) Positron / OpenStreetMap

鉄道駅の座標は一部近似。消防車の出動回数は地区別に公開されていないため、
消火活動の基盤密度の目安として消防水利を表示している。
