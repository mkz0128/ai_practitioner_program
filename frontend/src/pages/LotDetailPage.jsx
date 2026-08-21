import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { lots } from "../data/auctionData.js";
import { asset } from "../utils/assets.js";

export default function LotDetailPage() {
  const { lotId } = useParams();
  const navigate = useNavigate();
  const lot = lots.find((item) => item.id === lotId);
  if (!lot) return <Navigate to="/" replace />;
  const facts = [
    ["拍賣行", lot.house],
    ["拍賣年份", lot.year],
    ["估價範圍", lot.price],
    ["拍品類別", lot.category],
  ];

  return (
    <main className="detail-page" id="top">
      <button
        className="back-button"
        type="button"
        onClick={() => navigate(-1)}
      >
        <img src={asset("back.svg")} alt="" /> 返回搜尋結果
      </button>
      <div className="detail-layout">
        <section className="detail-art-column" aria-label="拍品圖片與來源">
          <div className="detail-image">
            <img src={lot.image} alt={`${lot.artist}《${lot.title}》`} />
          </div>
          <p className="lot-number">Lot {lot.lotNumber || "—"}</p>
          <div className="source-card">
            <span>資料來源</span>
            <strong>{lot.source || `${lot.house} ${lot.year}`}</strong>
          </div>
        </section>
        <section className="detail-content" aria-labelledby="lot-title">
          <p className="detail-category">{lot.category}</p>
          <h1 id="lot-title">{lot.title}</h1>
          <p className="detail-byline">
            {lot.artist} · {lot.era}
          </p>
          <dl className="fact-grid">
            {facts.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <div className="locked-insights">
            {["最終成交價", "完整拍賣紀錄（歷年）", "市場趨勢分析"].map(
              (label) => (
                <section className="insight-card" key={label}>
                  <header>
                    <span>{label}</span>
                    <img src={asset("lock.svg")} alt="需要訂閱" />
                  </header>
                  <i />
                  <i />
                </section>
              ),
            )}
          </div>
          <Link
            className="gold-button detail-subscribe"
            to="/subscribe"
            state={{ from: `/lots/${lot.id}` }}
          >
            <img src={asset("subscribe-lock.svg")} alt="" /> 訂閱以解鎖完整資訊
          </Link>
        </section>
      </div>
    </main>
  );
}
