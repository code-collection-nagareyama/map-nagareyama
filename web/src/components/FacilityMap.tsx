import { useEffect, useMemo, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { ScatterplotLayer, GeoJsonLayer, GridCellLayer } from '@deck.gl/layers';
import { HeatmapLayer } from '@deck.gl/aggregation-layers';
import type { PickingInfo, Layer } from '@deck.gl/core';

interface LayerDef {
  id: string;
  label: string;
  group: string;
  kind: 'plot' | 'heat';
  color: string;
  icon: string;
  count: number;
}
interface AccessGrid {
  cell_m: number;
  note?: string;
  points: number[][];
}
interface BusFreqProps {
  name: string;
  stop_id: string;
  weekday_deps: number;
  layer: string;
}
interface BoundProps {
  key?: string;
  name?: string;
  place?: string;
  area_m2?: number;
  pop2020?: number;
  households2020?: number;
}
interface LayerCatalog {
  groups: { id: string; label: string }[];
  layers: LayerDef[];
  hazard_note: string;
  osm_attribution?: string;
}
interface PointProps {
  layer: string;
  name: string;
  address: string;
  tel: string;
  dataset: string;
  detail: Record<string, string | number>;
}
interface HazardLayerDef {
  label: string;
  tiles: string[];
  opacity: number;
  legend: string | null;
}
interface HazardsRaster {
  attribution: string;
  order?: string[];
  legend_guide?: { label: string; url: string };
  layers: Record<string, HazardLayerDef>;
}
interface DistrictProps {
  name: string;
  kind: 'elem' | 'junior';
  address?: string;
  source?: string;
}
interface TipInfo {
  title: string;
  sub?: string;
  meta?: string;
  x: number;
  y: number;
}

const hex2rgb = (h: string): [number, number, number] => [
  parseInt(h.slice(1, 3), 16),
  parseInt(h.slice(3, 5), 16),
  parseInt(h.slice(5, 7), 16),
];

/** Carto Positron（薄い背景で施設・色分けが読みやすい） */
const BASE_STYLE = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';

export default function FacilityMap() {
  const holder = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const deckRef = useRef<MapboxOverlay | null>(null);

  const [catalog, setCatalog] = useState<LayerCatalog | null>(null);
  const [points, setPoints] = useState<GeoJSON.FeatureCollection | null>(null);
  const [boundaries, setBoundaries] = useState<GeoJSON.FeatureCollection | null>(null);
  const [elemDistricts, setElemDistricts] =
    useState<GeoJSON.FeatureCollection | null>(null);
  const [juniorDistricts, setJuniorDistricts] =
    useState<GeoJSON.FeatureCollection | null>(null);
  const [hazardsMeta, setHazardsMeta] = useState<HazardsRaster | null>(null);
  const [on, setOn] = useState<Set<string>>(new Set());
  const [sel, setSel] = useState<PointProps | null>(null);
  const [tip, setTip] = useState<TipInfo | null>(null);
  const [hazardOn, setHazardOn] = useState<Set<string>>(new Set());
  const [showElemDistrict, setShowElemDistrict] = useState(true);
  const [showJuniorDistrict, setShowJuniorDistrict] = useState(false);
  const [accessGrid, setAccessGrid] = useState<AccessGrid | null>(null);
  const [busFreq, setBusFreq] = useState<GeoJSON.FeatureCollection | null>(null);
  const [showBusAccess, setShowBusAccess] = useState(false);
  const [showBusBubble, setShowBusBubble] = useState(false);
  const [showPopDensity, setShowPopDensity] = useState(false);
  const [showSuiriHeat, setShowSuiriHeat] = useState(false);
  const [showParkHeat, setShowParkHeat] = useState(false);
  const [showKosodateHeat, setShowKosodateHeat] = useState(false);
  /** スマホではレイヤパネルを閉じた状態から始める */
  const [layersOpen, setLayersOpen] = useState(
    () =>
      typeof window === 'undefined' ||
      window.matchMedia('(min-width: 901px)').matches,
  );

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 901px)');
    const sync = () => {
      if (mq.matches) setLayersOpen(true);
    };
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, []);

  const hazardKeys = useMemo(() => {
    if (!hazardsMeta) return [] as string[];
    const keys = hazardsMeta.order?.length
      ? hazardsMeta.order
      : Object.keys(hazardsMeta.layers);
    return keys.filter((k) => hazardsMeta.layers[k]);
  }, [hazardsMeta]);

  useEffect(() => {
    fetch('data/map_layers.json').then((r) => r.json()).then(setCatalog);
    fetch('data/map_points.geojson').then((r) => r.json()).then(setPoints);
    fetch('data/boundaries.geojson')
      .then((r) => (r.ok ? r.json() : null))
      .then(setBoundaries)
      .catch(() => setBoundaries(null));
    fetch('data/school_districts_elem.geojson')
      .then((r) => (r.ok ? r.json() : null))
      .then(setElemDistricts)
      .catch(() => setElemDistricts(null));
    fetch('data/school_districts_junior.geojson')
      .then((r) => (r.ok ? r.json() : null))
      .then(setJuniorDistricts)
      .catch(() => setJuniorDistricts(null));
    fetch('data/hazards_raster.json')
      .then((r) => (r.ok ? r.json() : null))
      .then(setHazardsMeta)
      .catch(() => setHazardsMeta(null));
    fetch('data/access_grid.json')
      .then((r) => (r.ok ? r.json() : null))
      .then(setAccessGrid)
      .catch(() => setAccessGrid(null));
    fetch('data/bus_stop_freq.geojson')
      .then((r) => (r.ok ? r.json() : null))
      .then(setBusFreq)
      .catch(() => setBusFreq(null));
  }, []);

  useEffect(() => {
    if (!holder.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: holder.current,
      style: BASE_STYLE,
      center: [139.9235, 35.8664],
      zoom: 12.2,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({}), 'top-right');
    const deck = new MapboxOverlay({ interleaved: false, layers: [] });
    map.on('load', () => {
      map.addControl(deck);
    });
    mapRef.current = map;
    deckRef.current = deck;
    return () => {
      map.remove();
      mapRef.current = null;
      deckRef.current = null;
    };
  }, []);

  // ハザードラスタのソース追加と表示切替
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !hazardsMeta) return;
    const sync = () => {
      for (const key of hazardKeys) {
        const conf = hazardsMeta.layers[key];
        if (!conf) continue;
        const id = `hazard-${key}`;
        const layerId = `${id}-layer`;
        if (!map.getSource(id)) {
          map.addSource(id, {
            type: 'raster',
            tiles: conf.tiles,
            tileSize: 256,
            attribution: hazardsMeta.attribution,
          });
          map.addLayer({
            id: layerId,
            type: 'raster',
            source: id,
            paint: { 'raster-opacity': conf.opacity ?? 0.55 },
            layout: { visibility: 'none' },
          });
        } else {
          const src = map.getSource(id) as maplibregl.RasterTileSource | undefined;
          if (src && 'setTiles' in src) {
            (src as { setTiles: (t: string[]) => void }).setTiles(conf.tiles);
          }
        }
        if (!map.getLayer(layerId)) continue;
        map.setLayoutProperty(
          layerId,
          'visibility',
          hazardOn.has(key) ? 'visible' : 'none',
        );
        map.setPaintProperty(layerId, 'raster-opacity', conf.opacity ?? 0.55);
      }
    };
    if (map.isStyleLoaded()) sync();
    else map.once('load', sync);
  }, [hazardsMeta, hazardKeys, hazardOn]);

  const toggleHazard = (key: string) => {
    setHazardOn((prev) => {
      const n = new Set(prev);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });
  };

  const byLayer = useMemo(() => {
    const m = new Map<string, GeoJSON.Feature[]>();
    points?.features.forEach((f) => {
      const k = (f.properties as PointProps).layer;
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(f);
    });
    return m;
  }, [points]);

  const accessMax = useMemo(() => {
    if (!accessGrid?.points?.length) return 1;
    let m = 1;
    for (const p of accessGrid.points) m = Math.max(m, p[2] || 0);
    return m;
  }, [accessGrid]);

  /** 町丁字人口（2020）を人数の多さで段階色分けするための閾値・色 */
  const popScale = useMemo(() => {
    const vals =
      boundaries?.features
        .map((f) => (f.properties as BoundProps)?.pop2020 ?? 0)
        .filter((n) => n > 0)
        .sort((a, b) => a - b) ?? [];
    const q = (p: number) => {
      if (!vals.length) return 0;
      const i = Math.min(vals.length - 1, Math.floor((vals.length - 1) * p));
      return vals[i];
    };
    // 5段階（人数が多いほど濃い緑）。0人は別色
    const breaks = [q(0.2), q(0.4), q(0.6), q(0.8)];
    const colors: [number, number, number, number][] = [
      [236, 242, 230, 175],
      [186, 214, 170, 195],
      [120, 176, 118, 205],
      [56, 132, 82, 215],
      [22, 88, 52, 225],
    ];
    const zero: [number, number, number, number] = [220, 220, 216, 120];
    const colorOf = (pop: number): [number, number, number, number] => {
      if (pop <= 0) return zero;
      if (pop <= breaks[0]) return colors[0];
      if (pop <= breaks[1]) return colors[1];
      if (pop <= breaks[2]) return colors[2];
      if (pop <= breaks[3]) return colors[3];
      return colors[4];
    };
    const labels = [
      { swatch: '#ecf2e6', text: `1〜${breaks[0].toLocaleString()}人` },
      {
        swatch: '#bad6aa',
        text: `${(breaks[0] + 1).toLocaleString()}〜${breaks[1].toLocaleString()}人`,
      },
      {
        swatch: '#78b076',
        text: `${(breaks[1] + 1).toLocaleString()}〜${breaks[2].toLocaleString()}人`,
      },
      {
        swatch: '#388452',
        text: `${(breaks[2] + 1).toLocaleString()}〜${breaks[3].toLocaleString()}人`,
      },
      {
        swatch: '#165834',
        text: `${(breaks[3] + 1).toLocaleString()}人以上`,
      },
      { swatch: '#dcdcd8', text: '0人・データなし' },
    ];
    return { colorOf, labels, max: vals[vals.length - 1] ?? 0 };
  }, [boundaries]);

  const busDepMax = useMemo(() => {
    let m = 1;
    busFreq?.features.forEach((f) => {
      const n = (f.properties as BusFreqProps)?.weekday_deps ?? 0;
      if (n > m) m = n;
    });
    return m;
  }, [busFreq]);

  useEffect(() => {
    if (!deckRef.current || !catalog) return;
    const layers: Layer[] = [];
    if (boundaries) {
      layers.push(
        new GeoJsonLayer({
          id: 'bounds',
          data: boundaries,
          stroked: true,
          filled: true,
          getFillColor: (f: GeoJSON.Feature) => {
            if (!showPopDensity) return [120, 140, 160, 18];
            const pop = (f.properties as BoundProps)?.pop2020 ?? 0;
            return popScale.colorOf(pop);
          },
          getLineColor: showPopDensity
            ? [40, 70, 50, 160]
            : [120, 140, 160, 110],
          lineWidthMinPixels: showPopDensity ? 1 : 0.7,
          pickable: showPopDensity,
          autoHighlight: showPopDensity,
          updateTriggers: {
            getFillColor: [showPopDensity, popScale],
            getLineColor: showPopDensity,
          },
          onHover: (info: PickingInfo) => {
            if (!showPopDensity) return;
            const f = info.object as GeoJSON.Feature | undefined;
            if (f && info.x != null && info.y != null) {
              const p = f.properties as BoundProps;
              setTip({
                title: p.name || p.place || '（町丁字）',
                sub: `人口 ${(p.pop2020 ?? 0).toLocaleString()}人（2020年国勢調査）`,
                meta: p.households2020
                  ? `世帯 ${p.households2020.toLocaleString()}`
                  : undefined,
                x: info.x,
                y: info.y,
              });
            } else {
              setTip(null);
            }
          },
        }),
      );
    }
    if (showBusAccess && accessGrid) {
      layers.push(
        new GridCellLayer({
          id: 'bus-access',
          data: accessGrid.points,
          cellSize: accessGrid.cell_m,
          extruded: false,
          getPosition: (d: number[]) => [d[0], d[1]] as [number, number],
          getFillColor: (d: number[]) => {
            const t = Math.pow((d[2] || 0) / accessMax, 0.4);
            return [
              Math.round(235 - 190 * t),
              Math.round(225 - 115 * t),
              Math.round(200 - 130 * t),
              Math.round(55 + 150 * t),
            ] as [number, number, number, number];
          },
          pickable: true,
          onHover: (info: PickingInfo) => {
            const d = info.object as number[] | undefined;
            if (d && info.x != null && info.y != null) {
              setTip({
                title: 'バス利便性スコア',
                sub: `スコア ${d[2]?.toFixed?.(1) ?? d[2]} · 最寄バス停 ${Math.round(d[3] ?? 0)}m`,
                meta: `最寄停留所の平日出発 約${d[4] ?? 0}本`,
                x: info.x,
                y: info.y,
              });
            } else {
              setTip(null);
            }
          },
        }),
      );
    }
    if (showBusBubble && busFreq) {
      layers.push(
        new ScatterplotLayer({
          id: 'bus-bubble',
          data: busFreq.features,
          getPosition: (f: GeoJSON.Feature) =>
            (f.geometry as GeoJSON.Point).coordinates as [number, number],
          getFillColor: [40, 110, 140, 170],
          getLineColor: [255, 255, 255, 220],
          stroked: true,
          lineWidthMinPixels: 1,
          radiusUnits: 'meters',
          radiusMinPixels: 3,
          radiusMaxPixels: 28,
          getRadius: (f: GeoJSON.Feature) => {
            const n = (f.properties as BusFreqProps).weekday_deps || 0;
            return 40 + 220 * Math.sqrt(n / busDepMax);
          },
          pickable: true,
          onHover: (info: PickingInfo) => {
            const f = info.object as GeoJSON.Feature | undefined;
            if (f && info.x != null && info.y != null) {
              const p = f.properties as BusFreqProps;
              setTip({
                title: p.name || 'バス停',
                sub: `平日の発着目安 ${p.weekday_deps.toLocaleString()} 回`,
                meta: 'GTFS（ぐりーんバス等）',
                x: info.x,
                y: info.y,
              });
            } else {
              setTip(null);
            }
          },
        }),
      );
    }
    const pushHeat = (id: string, layerId: string, radius = 34) => {
      const feats = byLayer.get(layerId) ?? [];
      if (!feats.length) return;
      layers.push(
        new HeatmapLayer({
          id: id,
          data: feats,
          getPosition: (f: GeoJSON.Feature) =>
            (f.geometry as GeoJSON.Point).coordinates as [number, number],
          getWeight: 1,
          radiusPixels: radius,
          intensity: 1.05,
          threshold: 0.05,
        }),
      );
    };
    if (showSuiriHeat) pushHeat('h-suiri-overlay', 'suiri', 36);
    if (showParkHeat) pushHeat('h-park-overlay', 'park', 40);
    if (showKosodateHeat) pushHeat('h-kosodate-overlay', 'kosodate', 38);
    const districtHover = (info: PickingInfo, kindLabel: string) => {
      const f = info.object as GeoJSON.Feature | undefined;
      if (f && info.x != null && info.y != null) {
        const p = f.properties as DistrictProps;
        setTip({
          title: p.name || '（名称なし）',
          sub: kindLabel,
          meta: p.address || p.source,
          x: info.x,
          y: info.y,
        });
      } else {
        setTip(null);
      }
    };
    if (showElemDistrict && elemDistricts) {
      layers.push(
        new GeoJsonLayer({
          id: 'school-elem',
          data: elemDistricts,
          stroked: true,
          filled: true,
          getFillColor: [32, 128, 96, 48],
          getLineColor: [24, 110, 82, 210],
          lineWidthMinPixels: 1.4,
          pickable: true,
          autoHighlight: true,
          highlightColor: [32, 128, 96, 90],
          onHover: (info: PickingInfo) => districtHover(info, '小学校区'),
        }),
      );
    }
    if (showJuniorDistrict && juniorDistricts) {
      layers.push(
        new GeoJsonLayer({
          id: 'school-junior',
          data: juniorDistricts,
          stroked: true,
          filled: true,
          getFillColor: [48, 88, 168, 42],
          getLineColor: [36, 72, 150, 210],
          lineWidthMinPixels: 1.4,
          pickable: true,
          autoHighlight: true,
          highlightColor: [48, 88, 168, 90],
          onHover: (info: PickingInfo) => districtHover(info, '中学校区'),
        }),
      );
    }
    catalog.layers.forEach((L) => {
      if (!on.has(L.id)) return;
      const feats = byLayer.get(L.id) ?? [];
      const rgb = hex2rgb(L.color);
      if (L.kind === 'heat') {
        layers.push(
          new HeatmapLayer({
            id: 'h-' + L.id,
            data: feats,
            getPosition: (f: GeoJSON.Feature) =>
              (f.geometry as GeoJSON.Point).coordinates as [number, number],
            getWeight: 1,
            radiusPixels: 34,
            intensity: 1,
            threshold: 0.06,
          }),
        );
      } else {
        layers.push(
          new ScatterplotLayer({
            id: 'p-' + L.id,
            data: feats,
            getPosition: (f: GeoJSON.Feature) =>
              (f.geometry as GeoJSON.Point).coordinates as [number, number],
            getFillColor: [...rgb, 210] as [number, number, number, number],
            getLineColor: [255, 255, 255, 220],
            lineWidthMinPixels: 1,
            stroked: true,
            radiusMinPixels: 4,
            radiusMaxPixels: 11,
            getRadius: 40,
            pickable: true,
            autoHighlight: true,
            highlightColor: [44, 110, 73, 90],
            onHover: (info: PickingInfo) => {
              const f = info.object as GeoJSON.Feature | undefined;
              if (f && info.x != null && info.y != null) {
                const p = f.properties as PointProps;
                setTip({
                  title: p.name || '（名称なし）',
                  sub: p.address,
                  meta: [p.tel && `TEL ${p.tel}`, p.dataset]
                    .filter(Boolean)
                    .join(' · '),
                  x: info.x,
                  y: info.y,
                });
              } else {
                setTip(null);
              }
            },
            onClick: (info: PickingInfo) => {
              const f = info.object as GeoJSON.Feature | undefined;
              if (f) setSel(f.properties as PointProps);
            },
          }),
        );
      }
    });
    deckRef.current.setProps({
      layers,
      getCursor: ({ isHovering }: { isHovering: boolean }) =>
        isHovering ? 'pointer' : 'grab',
    });
  }, [
    catalog,
    byLayer,
    on,
    boundaries,
    elemDistricts,
    juniorDistricts,
    showElemDistrict,
    showJuniorDistrict,
    showBusAccess,
    showBusBubble,
    showPopDensity,
    showSuiriHeat,
    showParkHeat,
    showKosodateHeat,
    accessGrid,
    busFreq,
    accessMax,
    popScale,
    busDepMax,
  ]);

  const toggle = (id: string) =>
    setOn((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const total = useMemo(
    () =>
      catalog
        ? catalog.layers
            .filter((L) => on.has(L.id))
            .reduce((a, L) => a + L.count, 0)
        : 0,
    [catalog, on],
  );

  return (
    <div className={'split map-split' + (layersOpen ? ' layers-open' : '')}>
      <button
        type="button"
        className="map-layers-toggle"
        aria-expanded={layersOpen}
        aria-controls="map-layers-panel"
        onClick={() => setLayersOpen((v) => !v)}
      >
        {layersOpen ? 'レイヤを閉じる' : 'レイヤ・表示設定'}
      </button>
      {layersOpen && (
        <button
          type="button"
          className="map-layers-backdrop"
          aria-label="レイヤパネルを閉じる"
          onClick={() => setLayersOpen(false)}
        />
      )}
      <aside id="map-layers-panel" className="side">
        <h2>地図で見る</h2>

        <div className="lgroup">
          <h3>学区を重ねる</h3>
          <label className="chk">
            <input
              type="checkbox"
              checked={showElemDistrict}
              onChange={(e) => setShowElemDistrict(e.target.checked)}
              disabled={!elemDistricts}
            />
            <span className="swatch" style={{ background: '#208060' }} />
            小学校区
            <small>{elemDistricts?.features.length ?? 0}</small>
          </label>
          <label className="chk">
            <input
              type="checkbox"
              checked={showJuniorDistrict}
              onChange={(e) => setShowJuniorDistrict(e.target.checked)}
              disabled={!juniorDistricts}
            />
            <span className="swatch" style={{ background: '#3058a8' }} />
            中学校区
            <small>{juniorDistricts?.features.length ?? 0}</small>
          </label>
          <p className="note">
            国土数値情報（2023）の参考表示です。最新の通学指定は市の公式情報を確認してください。
          </p>
        </div>

        <div className="lgroup">
          <h3>分布・利便性</h3>
          <label className="chk">
            <input
              type="checkbox"
              checked={showBusAccess}
              onChange={(e) => setShowBusAccess(e.target.checked)}
              disabled={!accessGrid}
            />
            <span className="swatch" style={{ background: '#2a6f6f' }} />
            バス利便性（グリッド）
            <small>{accessGrid?.points.length?.toLocaleString() ?? 0}</small>
          </label>
          <label className="chk">
            <input
              type="checkbox"
              checked={showBusBubble}
              onChange={(e) => setShowBusBubble(e.target.checked)}
              disabled={!busFreq}
            />
            <span className="swatch" style={{ background: '#286e8c' }} />
            バス停本数（バブル）
            <small>{busFreq?.features.length ?? 0}</small>
          </label>
          <label className="chk">
            <input
              type="checkbox"
              checked={showPopDensity}
              onChange={(e) => setShowPopDensity(e.target.checked)}
              disabled={!boundaries}
            />
            <span className="swatch" style={{ background: '#388452' }} />
            人口（町丁字・人数）
            <small>{boundaries?.features.length ?? 0}</small>
          </label>
          {showPopDensity && (
            <div className="pop-legend" aria-label="人口の凡例">
              <div className="pop-legend-title">人数が多いほど濃い緑</div>
              {popScale.labels.map((L) => (
                <div key={L.text} className="pop-legend-row">
                  <span className="swatch" style={{ background: L.swatch }} />
                  <span>{L.text}</span>
                </div>
              ))}
              <p className="note" style={{ marginTop: 4 }}>
                町丁字界の塗り分け（国勢調査2020）。ホバーで町丁字名と人数。
              </p>
            </div>
          )}
          <label className="chk">
            <input
              type="checkbox"
              checked={showSuiriHeat}
              onChange={(e) => setShowSuiriHeat(e.target.checked)}
              disabled={!byLayer.get('suiri')?.length}
            />
            <span className="swatch" style={{ background: '#2f6690' }} />
            消防水利密度（消火基盤）
            <small>{byLayer.get('suiri')?.length?.toLocaleString() ?? 0}</small>
          </label>
          <label className="chk">
            <input
              type="checkbox"
              checked={showParkHeat}
              onChange={(e) => setShowParkHeat(e.target.checked)}
              disabled={!byLayer.get('park')?.length}
            />
            <span className="swatch" style={{ background: '#4c9f70' }} />
            公園密度
            <small>{byLayer.get('park')?.length?.toLocaleString() ?? 0}</small>
          </label>
          <label className="chk">
            <input
              type="checkbox"
              checked={showKosodateHeat}
              onChange={(e) => setShowKosodateHeat(e.target.checked)}
              disabled={!byLayer.get('kosodate')?.length}
            />
            <span className="swatch" style={{ background: '#f4a259' }} />
            子育て施設密度
            <small>{byLayer.get('kosodate')?.length?.toLocaleString() ?? 0}</small>
          </label>
          <p className="note">
            バス利便性は停留所距離と平日便数から算出した150mグリッドです。
            消防車の出動回数は地区別座標が公開されていないため、消火の基盤密度として消防水利を表示しています。
            飲食店・コンビニ等は下の「近隣施設」で密度ヒートマップにできます。
          </p>
        </div>

        <div className="lgroup">
          <h3>ハザードマップを重ねる</h3>
          {hazardKeys.map((key) => {
            const L = hazardsMeta!.layers[key];
            return (
              <label key={key} className="chk">
                <input
                  type="checkbox"
                  checked={hazardOn.has(key)}
                  onChange={() => toggleHazard(key)}
                />
                {L.label}
              </label>
            );
          })}
          <p className="note">
            国のハザードマップポータルの公式タイルです。複数を同時に重ねられます。
            {hazardsMeta?.legend_guide && (
              <>
                {' '}
                <a
                  href={hazardsMeta.legend_guide.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {hazardsMeta.legend_guide.label}
                </a>
              </>
            )}
          </p>
        </div>

        {catalog?.groups.map((g) => {
          if (g.id === 'bunpu') return null;
          const ls = catalog.layers.filter(
            (L) =>
              L.group === g.id &&
              !(L.group === 'osm' && L.label.includes('公園')),
          );
          if (!ls.length) return null;
          return (
            <div key={g.id} className="lgroup">
              <h3>{g.label}</h3>
              {ls.map((L) => (
                <label key={L.id} className="chk">
                  <input
                    type="checkbox"
                    checked={on.has(L.id)}
                    onChange={() => toggle(L.id)}
                  />
                  <span className="swatch" style={{ background: L.color }} />
                  {L.label}
                  <small>
                    {L.count.toLocaleString()}
                    {L.kind === 'heat' ? '・密度' : ''}
                  </small>
                </label>
              ))}
            </div>
          );
        })}
        <p className="note">表示中 {total.toLocaleString()} 点</p>
        {catalog?.osm_attribution && (
          <p className="note">{catalog.osm_attribution}</p>
        )}
        <p className="note">
          背景地図 ©{' '}
          <a href="https://carto.com/attributions" target="_blank" rel="noreferrer">
            CARTO
          </a>
          {' · '}
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
            OpenStreetMap
          </a>
          {hazardOn.size > 0 && (
            <>
              {' · '}
              {hazardsMeta?.attribution ?? 'ハザードマップポータルサイト'}
            </>
          )}
          {(showElemDistrict || showJuniorDistrict) && (
            <>
              {' · '}
              国土数値情報（小学校区・中学校区）
            </>
          )}
          {(showBusAccess || showBusBubble) && <>{' · '}GTFS（バス）</>}
          {showPopDensity && <>{' · '}国勢調査2020（境界属性）</>}
        </p>
      </aside>

      <div className="mapwrap">
        <div ref={holder} className="map" />
        {tip && !sel && (
          <div className="map-tip" style={{ left: tip.x, top: tip.y }}>
            <strong>{tip.title}</strong>
            {tip.sub && <div className="tip-addr">{tip.sub}</div>}
            {tip.meta && <div className="tip-meta">{tip.meta}</div>}
          </div>
        )}
        {sel && (
          <div className="popup">
            <button className="close" onClick={() => setSel(null)}>
              ×
            </button>
            <h3>{sel.name}</h3>
            {sel.address && <p className="addr">{sel.address}</p>}
            {sel.tel && <p className="addr">TEL {sel.tel}</p>}
            <table className="detail">
              <tbody>
                {Object.entries(sel.detail ?? {})
                  .slice(0, 18)
                  .map(([k, v]) => (
                    <tr key={k}>
                      <th>{k}</th>
                      <td>{String(v)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
            <p className="src">出所: {sel.dataset}</p>
          </div>
        )}
      </div>
    </div>
  );
}
