import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import StockAnalyzer from "@/pages/StockAnalyzer";
import Screener from "@/pages/Screener";
import Watchlist from "@/pages/Watchlist";
import Portfolio from "@/pages/Portfolio";
import NewsHub from "@/pages/NewsHub";
import Reports from "@/pages/Reports";
import Alerts from "@/pages/Alerts";
import Backtest from "@/pages/Backtest";
import DataPipeline from "@/pages/DataPipeline";
import DatabaseDashboard from "@/pages/DatabaseDashboard";
import PostgresControl from "@/pages/PostgresControl";

function App() {
  return (
    <div className="App dark">
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/analyzer" element={<StockAnalyzer />} />
            <Route path="/screener" element={<Screener />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/news" element={<NewsHub />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/data-pipeline" element={<DataPipeline />} />
            <Route path="/db-dashboard" element={<DatabaseDashboard />} />
            <Route path="/pg-control" element={<PostgresControl />} />
          </Routes>
        </Layout>
      </BrowserRouter>
      <Toaster
        position="bottom-right"
        theme="dark"
        toastOptions={{
          style: {
            background: '#18181B',
            border: '1px solid #27272A',
            color: '#FAFAFA',
          },
        }}
      />
    </div>
  );
}

export default App;
