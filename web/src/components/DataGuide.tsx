export default function DataGuide() {
  return (
    <div className="guide">
      <p className="guide-lead">
        地図上の色や点は、公開データをもとにこのアプリ側で加工して表示しています。
        行政が公表している「公式の密度統計」そのものではありません。
      </p>

      <section className="guide-sec">
        <h3>施設の点</h3>
        <p>
          避難所・災害用井戸・AED・公園・公衆トイレ・文化財・公共施設・子育て・福祉・医療・駐輪場・バス停・鉄道駅・投票所などは、
          <a
            href="https://www.city.nagareyama.chiba.jp/opendata/1042063/1042065.html"
            target="_blank"
            rel="noreferrer"
          >
            流山市オープンデータ
          </a>
          の各データセットから座標を取り、地図上の1点として置いています。点をタップすると名称・住所・出典データセット名が出ます。
        </p>
        <p>
          ライセンスはデータセットごとに CC BY または CC BY-NC-ND です。鉄道駅の座標は一部近似です。
        </p>
      </section>

      <section className="guide-sec">
        <h3>近隣施設（OpenStreetMap）</h3>
        <p>
          飲食店・コンビニ・スーパー・診療所などは、OpenStreetMap を Overpass API で取得しています。
          公園は市オープンデータと重複するため OSM 側は載せていません。
        </p>
        <p>
          件数の多い種別は点ではなく密度ヒートマップ（後述）で表示します。データは © OpenStreetMap
          contributors（ODbL）です。
        </p>
      </section>

      <section className="guide-sec">
        <h3>学区</h3>
        <p>
          国土数値情報の小学校区（A27）・中学校区（A32）2023年版のポリゴンを重ねています。
          参考表示であり、最新の通学指定は市の公式情報を確認してください。
        </p>
      </section>

      <section className="guide-sec">
        <h3>ハザード</h3>
        <p>
          洪水浸水想定・浸水継続時間・家屋倒壊等氾濫想定・土砂災害警戒区域は、国の
          <a
            href="https://disaportal.gsi.go.jp/"
            target="_blank"
            rel="noreferrer"
          >
            ハザードマップポータルサイト
          </a>
          が配信する公式タイルを、そのまま地図に重ねています。このアプリが浸水深を再計算しているわけではありません。
        </p>
      </section>

      <section className="guide-sec">
        <h3>バス利便性（グリッド）</h3>
        <p>
          ぐりーんバス等の GTFS（時刻表データ）から、市内を 150m 四方のセルに分けてスコアを付けています。
          各セルの値は、半径 1.2km 以内の停留所について
          「平日の出発本数 × exp(−距離 / 320m)」を足し合わせたものです。近い停留所・便数の多い停留所ほど高くなります。
        </p>
        <p>
          色が濃いほど相対的にバスで動きやすい目安です。乗降実績や遅延は含みません。
        </p>
      </section>

      <section className="guide-sec">
        <h3>バス停本数（バブル）</h3>
        <p>
          同じく GTFS から、停留所ごとの平日出発回数を円の大きさで表しています。ホバーで回数の目安を見られます。
        </p>
      </section>

      <section className="guide-sec">
        <h3>人口（町丁字）</h3>
        <p>
          <a href="https://www.e-stat.go.jp/" target="_blank" rel="noreferrer">
            政府統計の総合窓口（e-Stat）
          </a>
          の 2020年国勢調査 小地域（町丁・字等）境界を使い、境界データに付いている人数で塗り分けています。
          人数が多いほど濃い緑です。段階の区切りは、市内の町丁字人数の分布から分位点で決めています。
        </p>
      </section>

      <section className="guide-sec">
        <h3>密度ヒートマップ</h3>
        <p>
          消防水利・公園・子育て施設、および飲食店・コンビニなどの OSM 施設は、点の位置を
          deck.gl の HeatmapLayer（カーネル密度の可視化）に渡しています。
        </p>
        <ul>
          <li>各点の重みはすべて 1（件数として均等）</li>
          <li>画面上の広がりは半径およそ 34〜40 ピクセル（ズームで見た目の広さは変わる）</li>
          <li>色が強いところは「点が近くに多い」場所の目安</li>
        </ul>
        <p>
          これは表示上のなめらかな密度であり、行政が公表する公式統計や「1k㎡あたり件数」の計算結果ではありません。
          消防車の出動回数は地区別座標が公開されていないため、消火活動の基盤の目安として消防水利の密度を出しています。
        </p>
      </section>

      <section className="guide-sec">
        <h3>現在地ピン</h3>
        <p>
          地図右下の「現在地」を押すと、ブラウザの位置情報 API で端末の位置を取得し、ピンを立てます。
          位置はサーバーへ送りません。拒否や失敗のときはピンを出さず、理由を表示します。
        </p>
      </section>

      <section className="guide-sec">
        <h3>背景地図</h3>
        <p>
          背景は{' '}
          <a href="https://carto.com/attributions" target="_blank" rel="noreferrer">
            CARTO
          </a>{' '}
          Positron と OpenStreetMap です。
        </p>
      </section>
    </div>
  );
}
