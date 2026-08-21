import { Link, Outlet, useLocation } from "react-router-dom";
import { steps } from "../data/auctionData.js";
import { asset } from "../utils/assets.js";

function getActiveStep(pathname) {
  if (pathname === "/research") return 1;
  if (pathname.startsWith("/lots/")) return 3;
  if (pathname === "/subscribe") return 4;
  return 0;
}

export default function AuctionLayout() {
  const location = useLocation();
  const activeStep = getActiveStep(location.pathname);

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
          <span className={index === activeStep ? "active" : ""} key={step}>
            {step}
            {index < steps.length - 1 && (
              <img src={asset("chevron.svg")} alt="" />
            )}
          </span>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
