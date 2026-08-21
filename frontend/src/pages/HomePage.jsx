import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import LotCard from "../components/LotCard.jsx";
import { categories, lots, suggestions } from "../data/auctionData.js";
import { asset } from "../utils/assets.js";

export default function HomePage() {
  const navigate = useNavigate();
  const [category, setCategory] = useState("全部");
  const [query, setQuery] = useState("");
  const visibleLots = useMemo(() => {
    return lots.filter(
      (lot) => category === "全部" || lot.category === category,
    );
  }, [category]);
  const runAiSearch = (value = query) => {
    const question = value.trim();
    if (!question) return;
    navigate("/research", { state: { initialQuestion: question } });
  };
  const clearSearch = () => {
    setQuery("");
    setCategory("全部");
  };

  return (
    <main id="top">
      <section className="hero" aria-labelledby="hero-title">
        <img
          className="hero-art"
          src={asset("landscape.png")}
          alt="中國山水畫長卷"
        />
        <div className="hero-content">
          <p className="kicker">古典藝術拍賣平台</p>
          <h1 id="hero-title">以 AI 探索藝術市場</h1>
          <p className="hero-copy">
            用自然語言搜尋歷年拍賣紀錄，AI 自動辨識藝術家、年代、類別與價格條件
          </p>
          <form
            className="searchbar"
            onSubmit={(event) => {
              event.preventDefault();
              runAiSearch();
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
                  runAiSearch(suggestion);
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
            <LotCard lot={lot} key={lot.id} />
          ))}
        </div>
        {!visibleLots.length && (
          <div className="empty">
            <strong>未找到符合條件的拍品</strong>
            <button type="button" onClick={clearSearch}>
              清除搜尋條件
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
