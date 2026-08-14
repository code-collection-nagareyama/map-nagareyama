import { useEffect, useId, useState } from 'react';
import type { AppPanel } from './appPanel';
import FacilityMap from './components/FacilityMap';

export default function App() {
  const menuId = useId();
  const [menuOpen, setMenuOpen] = useState(false);
  const [panel, setPanel] = useState<AppPanel | null>(() =>
    typeof window === 'undefined' ||
    window.matchMedia('(min-width: 901px)').matches
      ? 'layers'
      : null,
  );

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 901px)');
    const sync = () => {
      if (mq.matches) setPanel((p) => p ?? 'layers');
    };
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (menuOpen) {
        setMenuOpen(false);
        return;
      }
      setPanel(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  const selectPanel = (next: AppPanel) => {
    setPanel((p) => (p === next ? null : next));
    setMenuOpen(false);
  };

  return (
    <div className="app">
      <header className="header">
        <button
          type="button"
          className="menu-btn"
          aria-label="メニュー"
          aria-expanded={menuOpen}
          aria-controls={menuId}
          onClick={() => setMenuOpen((v) => !v)}
        >
          <span className="menu-btn-bars" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        </button>
        <div className="brand">
          流山マップ
          <small>流山市オープンデータの地図表示</small>
        </div>
        {menuOpen && (
          <>
            <button
              type="button"
              className="menu-backdrop"
              aria-label="メニューを閉じる"
              onClick={() => setMenuOpen(false)}
            />
            <nav id={menuId} className="app-menu" aria-label="アプリメニュー">
              <button
                type="button"
                className="app-menu-item"
                aria-current={panel === 'layers' ? 'page' : undefined}
                onClick={() => selectPanel('layers')}
              >
                地図の表示
              </button>
              <button
                type="button"
                className="app-menu-item"
                aria-current={panel === 'guide' ? 'page' : undefined}
                onClick={() => selectPanel('guide')}
              >
                データの説明
              </button>
            </nav>
          </>
        )}
      </header>
      <main className="main">
        <FacilityMap panel={panel} onClosePanel={() => setPanel(null)} />
      </main>
    </div>
  );
}
