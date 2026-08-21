import { Navigate, Route, Routes } from "react-router-dom";
import AuctionLayout from "./components/AuctionLayout.jsx";
import HomePage from "./pages/HomePage.jsx";
import LotDetailPage from "./pages/LotDetailPage.jsx";
import ResearchPage from "./pages/ResearchPage.jsx";
import SubscribePage from "./pages/SubscribePage.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<AuctionLayout />}>
        <Route index element={<HomePage />} />
        <Route path="research" element={<ResearchPage />} />
        <Route path="lots/:lotId" element={<LotDetailPage />} />
        <Route path="subscribe" element={<SubscribePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
