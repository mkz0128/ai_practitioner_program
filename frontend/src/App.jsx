import { useMemo, useState } from "react";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";

const asset = (name) => `${import.meta.env.BASE_URL}figma-assets/${name}`;

const categories = [
  "全部",
  "水墨花鳥",
  "山水",
  "水墨",
  "人物",
  "陶瓷",
  "書法",
  "玉器",
];
const suggestions = [
  "齊白石蝦圖 1940 年代",
  "宋代青瓷 300 萬以上",
  "張大千潑墨山水",
];
const steps = [
  "1. 瀏覽拍品",
  "2. AI 搜尋",
  "3. 查看結果",
  "4. 拍品詳情",
  "5. 訂閱解鎖",
];

const plans = [
  {
    name: "基礎版",
    price: "299",
    features: ["每月 50 次 AI 搜尋", "近 5 年成交價查詢", "基礎市場行情"],
    unavailable: ["完整歷年拍賣紀錄", "趨勢分析報告"],
  },
  {
    name: "專業版",
    price: "799",
    popular: true,
    features: [
      "無限次 AI 搜尋",
      "完整歷年成交紀錄",
      "市場趨勢分析",
      "藝術家深度報告",
      "匯出 PDF 報告",
    ],
  },
  {
    name: "典藏版",
    price: "2,499",
    features: [
      "包含所有專業版功能",
      "優先 AI 回應速度",
      "月度市場策展通訊",
      "個人收藏追蹤管理",
      "專屬藏家社群",
      "專人客服支援",
    ],
  },
];

const lots = [
  {
    title: "花鳥四屏",
    artist: "吳昌碩",
    era: "民國初期",
    category: "水墨花鳥",
    price: "NT$ 38 萬–NT$ 48 萬",
    house: "中國嘉德",
    year: "2022",
    image: asset("artwork-3.jpeg"),
  },
  {
    title: "山水長卷",
    artist: "張大千",
    era: "1960 年代",
    category: "山水",
    price: "NT$ 120 萬–NT$ 180 萬",
    house: "蘇富比香港",
    year: "2021",
    image: asset("artwork-2.jpeg"),
    locked: true,
  },
  {
    title: "荷花冊頁",
    artist: "齊白石",
    era: "1940 年代",
    category: "水墨花鳥",
    price: "NT$ 85 萬–NT$ 120 萬",
    house: "保利拍賣",
    year: "2023",
    image: asset("artwork-4.jpeg"),
  },
  {
    title: "簾馬圖",
    artist: "徐悲鴻",
    era: "1935 年",
    category: "水墨",
    price: "NT$ 250 萬–NT$ 350 萬",
    house: "佳士得香港",
    year: "2022",
    image: asset("artwork-6.jpeg"),
  },
  {
    title: "仕女圖",
    artist: "改琦",
    era: "清代",
    category: "人物",
    price: "NT$ 28 萬–NT$ 38 萬",
    house: "羅芙奧",
    year: "2021",
    image: asset("artwork-7.jpeg"),
  },
  {
    title: "青花纏枝梅瓶",
    artist: "宋代官窯",
    era: "宋代",
    category: "陶瓷",
    price: "NT$ 480 萬–NT$ 600 萬",
    house: "佳士得香港",
    year: "2020",
    image: asset("artwork-5.jpeg"),
    locked: true,
  },
  {
    title: "青花龍紋大瓶",
    artist: "清乾隆",
    era: "清代乾隆",
    category: "陶瓷",
    price: "NT$ 320 萬–NT$ 450 萬",
    house: "蘇富比香港",
    year: "2023",
    image: asset("artwork-8.jpeg"),
    locked: true,
  },
  {
    title: "山水立軸",
    artist: "傅抱石",
    era: "1950 年代",
    category: "山水",
    price: "NT$ 45 萬–NT$ 62 萬",
    house: "中國嘉德",
    year: "2023",
    image: asset("artwork-3.jpeg"),
  },
];

export default function App() {
  const [category, setCategory] = useState("全部");
  const [query, setQuery] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedPlan, setSelectedPlan] = useState("專業版");
  const location = useLocation();
  const navigate = useNavigate();
  const isSubscribePage = location.pathname === "/subscribe";

  const visibleLots = useMemo(() => {
    const normalized = searchTerm.trim().toLowerCase();
    return lots.filter((lot) => {
      const categoryMatches = category === "全部" || lot.category === category;
      const text =
        `${lot.title} ${lot.artist} ${lot.era} ${lot.category}`.toLowerCase();
      return categoryMatches && (!normalized || text.includes(normalized));
    });
  }, [category, searchTerm]);

  const runSearch = (value = query) => setSearchTerm(value);

  return (
    <div className="auction-site">
      <header className="topbar">
        <Link className="wordmark" to="/" aria-label="典藏志首頁">
          <span>典</span>
          <strong>典藏志</strong>
        </Link>
        <Link
          className="gold-button subscribe"
          to="/subscribe"
          state={{ from: location.pathname }}
        >
          訂閱方案
        </Link>
      </header>

      <nav className="journey" aria-label="使用流程">
        {steps.map((step, index) => (
          <span
            className={
              (!isSubscribePage && index === 0) ||
              (isSubscribePage && index === steps.length - 1)
                ? "active"
                : ""
            }
            key={step}
          >
            {step}
            {index < steps.length - 1 && (
              <img src={asset("chevron.svg")} alt="" />
            )}
          </span>
        ))}
      </nav>

      <Routes>
        <Route path="/" element={<main id="top">
          <section className="hero" aria-labelledby="hero-title">
            <img
              className="hero-art"
              src={asset("landscape.jpeg")}
              alt="中國山水畫長卷"
            />
            <div className="hero-content">
              <p className="kicker">古典藝術拍賣平台</p>
              <h1 id="hero-title">以 AI 探索藝術市場</h1>
              <p className="hero-copy">
                用自然語言搜尋歷年拍賣紀錄，AI
                自動辨識藝術家、年代、類別與價格條件
              </p>
              <form
                className="searchbar"
                onSubmit={(event) => {
                  event.preventDefault();
                  runSearch();
                }}
              >
                <label>
                  <img src={asset("search.svg")} alt="" />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="例：民國吳昌碩花鳥，預算 50 萬以內..."
                  />
                  <img src={asset("sparkle.svg")} alt="AI" />
                </label>
                <button className="gold-button" type="submit">
                  AI 搜尋
                </button>
              </form>
              <div className="prompt-chips">
                {suggestions.map((suggestion) => (
                  <button
                    type="button"
                    onClick={() => {
                      setQuery(suggestion);
                      runSearch(suggestion);
                    }}
                    key={suggestion}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="lot-section" aria-label="拍品瀏覽">
            <div className="filters">
              <img src={asset("filter.svg")} alt="篩選" />
              {categories.map((item) => (
                <button
                  type="button"
                  className={item === category ? "selected" : ""}
                  onClick={() => setCategory(item)}
                  key={item}
                >
                  {item}
                </button>
              ))}
              <span>{visibleLots.length} 件拍品</span>
            </div>
            <div className="lot-grid">
              {visibleLots.map((lot) => (
                <article
                  className="lot-card"
                  tabIndex="0"
                  key={`${lot.title}-${lot.year}`}
                >
                  <div className="lot-image">
                    <img
                      src={lot.image}
                      alt={`${lot.artist}《${lot.title}》`}
                    />
                    <span className="lot-tag">{lot.category}</span>
                    {lot.locked && (
                      <span className="locked">
                        <img src={asset("lock.svg")} alt="" />
                        訂閱查看成交價
                      </span>
                    )}
                  </div>
                  <div className="lot-details">
                    <h2>{lot.title}</h2>
                    <p>
                      {lot.artist} · {lot.era}
                    </p>
                    <strong>{lot.price}</strong>
                    <footer>
                      <span>{lot.house}</span>
                      <span>{lot.year}</span>
                    </footer>
                  </div>
                </article>
              ))}
            </div>
            {!visibleLots.length && (
              <div className="empty">
                <strong>未找到符合條件的拍品</strong>
                <button
                  type="button"
                  onClick={() => {
                    setQuery("");
                    setSearchTerm("");
                    setCategory("全部");
                  }}
                >
                  清除搜尋條件
                </button>
              </div>
            )}
          </section>
        </main>} />
        <Route path="/subscribe" element={<main className="subscribe-page" id="top">
          <button
            className="back-button"
            type="button"
            onClick={() => navigate(location.state?.from || "/")}
          >
            <img src={asset("back.svg")} alt="" /> 返回
          </button>
          <header className="subscribe-intro">
            <p>
              <img src={asset("crown.svg")} alt="" /> 訂閱方案
            </p>
            <h1>解鎖完整市場資訊</h1>
            <span>
              訂閱後解鎖歷年拍賣成交價與市場分析，讓 AI 協助您深入理解藝術市場
            </span>
          </header>
          <div className="plan-grid">
            {plans.map((plan) => {
              const selected = selectedPlan === plan.name;
              return (
                <button
                  className={`plan-card ${selected ? "selected" : ""}`}
                  type="button"
                  onClick={() => setSelectedPlan(plan.name)}
                  key={plan.name}
                >
                  {plan.popular && <span className="popular">最受歡迎</span>}
                  <div className="plan-name">
                    <strong>{plan.name}</strong>
                    {selected ? (
                      <img src={asset("check.svg")} alt="已選取" />
                    ) : (
                      <i />
                    )}
                  </div>
                  <div className="price">
                    NT$ <strong>{plan.price}</strong> <small>/ 月</small>
                  </div>
                  <ul>
                    {plan.features.map((feature) => (
                      <li key={feature}>
                        <img src={asset("check.svg")} alt="" />
                        {feature}
                      </li>
                    ))}
                    {plan.unavailable?.map((feature) => (
                      <li className="unavailable" key={feature}>
                        <img src={asset("x.svg")} alt="" />
                        {feature}
                      </li>
                    ))}
                  </ul>
                </button>
              );
            })}
          </div>
          <div className="subscribe-action">
            <button className="gold-button" type="button">
              <img src={asset("subscribe-lock.svg")} alt="" />
              立即訂閱 {selectedPlan}
            </button>
            <p>可隨時取消訂閱 · 付款資料加密保護</p>
          </div>
        </main>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
