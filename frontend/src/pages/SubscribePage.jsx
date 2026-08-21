import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { plans } from "../data/auctionData.js";
import { asset } from "../utils/assets.js";

export default function SubscribePage() {
  const [selectedPlan, setSelectedPlan] = useState("專業版");
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <main className="subscribe-page" id="top">
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
    </main>
  );
}
