# -*- coding: utf-8 -*-
"""地図の分布オーバーレイ用データを生成する。

生成物:
  bus_stop_freq.geojson  ぐりーんバス等 GTFS の平日停留所別出発本数
  map_layers.json の一部 kind を密度表示向けに更新（既存ファイルを直接編集）
"""
from __future__ import annotations

import collections
import csv
import glob
import io
import json
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(ROOT, "web", "public", "data")
VIZ = os.path.join(ROOT, "data", "derived")


def load(p):
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def find_gtfs_zip():
    pats = [
        os.path.join(ROOT, "data", "raw", "**", "feed.zip"),
        os.path.join(ROOT, "data", "json", "**", "feed.zip"),
    ]
    found = []
    for pat in pats:
        found.extend(glob.glob(pat, recursive=True))
    return found[0] if found else None


def read_gtfs_csv(zf: zipfile.ZipFile, name: str):
    raw = zf.read(name)
    # strip BOM
    text = raw.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def weekday_service_ids(calendar_rows):
    ids = set()
    for r in calendar_rows:
        # monday..friday
        if all(r.get(d, "0") == "1" for d in ("monday", "tuesday", "wednesday", "thursday", "friday")):
            ids.add(r["service_id"])
        elif sum(int(r.get(d, "0") or 0) for d in ("monday", "tuesday", "wednesday", "thursday", "friday")) >= 3:
            ids.add(r["service_id"])
    return ids


def build_bus_freq():
    zpath = find_gtfs_zip()
    if not zpath:
        raise SystemExit("GTFS feed.zip not found")
    with zipfile.ZipFile(zpath) as zf:
        names = set(zf.namelist())
        stops = read_gtfs_csv(zf, "stops.txt")
        stop_times = read_gtfs_csv(zf, "stop_times.txt")
        trips = read_gtfs_csv(zf, "trips.txt")
        calendar = read_gtfs_csv(zf, "calendar.txt") if "calendar.txt" in names else []
    svc = weekday_service_ids(calendar)
    if not svc:
        # fall back: all services
        svc = {t["service_id"] for t in trips}
    weekday_trips = {t["trip_id"] for t in trips if t["service_id"] in svc}
    # count departures per stop (use departure_time; first stop may have empty arrival)
    counts = collections.Counter()
    for st in stop_times:
        if st["trip_id"] not in weekday_trips:
            continue
        sid = st["stop_id"]
        # count each stop touch as a departure opportunity
        counts[sid] += 1
    feats = []
    for s in stops:
        # skip stations if location_type==1
        if str(s.get("location_type") or "0") not in ("0", ""):
            continue
        sid = s["stop_id"]
        n = int(counts.get(sid, 0))
        try:
            lon = float(s["stop_lon"])
            lat = float(s["stop_lat"])
        except Exception:
            continue
        if not (139.7 < lon < 140.1 and 35.7 < lat < 36.1):
            continue
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "name": s.get("stop_name") or sid,
                    "stop_id": sid,
                    "weekday_deps": n,
                    "layer": "bus_freq",
                },
            }
        )
    feats.sort(key=lambda f: -f["properties"]["weekday_deps"])
    fc = {
        "type": "FeatureCollection",
        "features": feats,
        "note": "GTFS平日サービスに属する便の stop_times 件数（停留所別）。ぐりーんバス等。",
        "source": os.path.relpath(zpath, ROOT).replace("\\", "/"),
    }
    return fc


def patch_map_layers():
    path = os.path.join(PUB, "map_layers.json")
    cat = load(path)
    heat_ids = {
        "suiri",
        "park",
        "kosodate",
        "fukushi",
        "busstop",
        "osm_0",
        "osm_1",
        "osm_2",
        "osm_5",
    }
    # add dual-mode via kind_modes? keep simple: change dense to heat
    labels = {
        "suiri": "消防水利（密度）",
        "park": "公園（密度）",
        "kosodate": "子育て施設（密度）",
        "fukushi": "福祉・介護（密度）",
        "busstop": "バス停（密度）",
        "osm_0": "飲食店（密度）",
        "osm_1": "コンビニ（密度）",
        "osm_2": "幼稚園・保育園（密度）",
        "osm_5": "スーパー（密度）",
    }
    for L in cat["layers"]:
        if L["id"] in heat_ids:
            L["kind"] = "heat"
            if L["id"] in labels:
                L["label"] = labels[L["id"]]
    # ensure distribution group exists for UI note (overlays are code-side)
    if not any(g["id"] == "bunpu" for g in cat["groups"]):
        cat["groups"].insert(0, {"id": "bunpu", "label": "分布・利便性"})
    cat["hazard_note"] = (
        "洪水浸水想定・土砂災害警戒はハザードマップポータルの公式タイル。"
        "町丁字境界はe-Stat（人口は境界属性の2020年国勢調査）。"
        "バス利便性はGTFS由来の150mグリッド。"
        "消防水利は消火活動の基盤密度の目安（出動回数の地区別公開ではない）。"
        "点は市オープンデータ（鉄道駅座標のみ一部近似）。近隣施設はOSM（公園除く）。"
    )
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(cat, f, ensure_ascii=False, indent=1)
        f.write("\n")
    viz = os.path.join(VIZ, "map_layers.json")
    if os.path.isdir(VIZ):
        with io.open(viz, "w", encoding="utf-8") as f:
            json.dump(cat, f, ensure_ascii=False, indent=1)
            f.write("\n")
    print("patched map_layers", path)


def main():
    fc = build_bus_freq()
    for dest in (PUB, VIZ):
        os.makedirs(dest, exist_ok=True)
        path = os.path.join(dest, "bus_stop_freq.geojson")
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(fc, f, ensure_ascii=False)
            f.write("\n")
        print("wrote", path, "features", len(fc["features"]), "max", fc["features"][0]["properties"]["weekday_deps"] if fc["features"] else 0)
    patch_map_layers()


if __name__ == "__main__":
    main()
