import FacilityMap from './components/FacilityMap';

export default function App() {
  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          流山マップ
          <small>流山市オープンデータの地図表示</small>
        </div>
      </header>
      <main className="main">
        <FacilityMap />
      </main>
    </div>
  );
}
