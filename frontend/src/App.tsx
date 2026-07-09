import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import PortfolioPage from "./pages/PortfolioPage";
import WatchlistPage from "./pages/WatchlistPage";
import ProfileDetailPage from "./pages/ProfileDetailPage";
import AnalyzePage from "./pages/AnalyzePage";
import DecisionsPage from "./pages/DecisionsPage";
import DecisionDetailPage from "./pages/DecisionDetailPage";
import MorningPage from "./pages/MorningPage";
import WeeklyPage from "./pages/WeeklyPage";
import MemoryPage from "./pages/MemoryPage";
import AutomationPage from "./pages/AutomationPage";
import BacktestPage from "./pages/BacktestPage";
import RunsPage from "./pages/RunsPage";
import RunDetailPage from "./pages/RunDetailPage";
import ComparePage from "./pages/ComparePage";
import DataPage from "./pages/DataPage";
import ParamsPage from "./pages/ParamsPage";
import GuidePage from "./pages/GuidePage";
import ModelLabPage from "./pages/ModelLabPage";
import PipelineBakeoffPage from "./pages/PipelineBakeoffPage";
import OptionsScannerPage from "./pages/OptionsScannerPage";
import OptionsPositionsPage from "./pages/OptionsPositionsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* Guide (cross-cutting) */}
        <Route path="/guide" element={<GuidePage />} />
        {/* Portfolio section */}
        <Route path="/" element={<PortfolioPage />} />
        <Route path="/watchlist" element={<WatchlistPage />} />
        <Route path="/watchlist/:symbol" element={<ProfileDetailPage />} />
        <Route path="/automation" element={<AutomationPage />} />
        {/* AI Analysis section */}
        <Route path="/analyze" element={<AnalyzePage />} />
        <Route path="/decisions" element={<DecisionsPage />} />
        <Route path="/decisions/:symbol/:date" element={<DecisionDetailPage />} />
        <Route path="/morning" element={<MorningPage />} />
        <Route path="/weekly" element={<WeeklyPage />} />
        <Route path="/memory" element={<MemoryPage />} />
        <Route path="/model-lab" element={<ModelLabPage />} />
        <Route path="/pipeline-test" element={<PipelineBakeoffPage />} />
        {/* Options section */}
        <Route path="/options" element={<OptionsScannerPage />} />
        <Route path="/options/positions" element={<OptionsPositionsPage />} />
        {/* Backtesting section */}
        <Route path="/backtest" element={<BacktestPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunDetailPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/data" element={<DataPage />} />
        <Route path="/params" element={<ParamsPage />} />
      </Route>
    </Routes>
  );
}
