import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = axios.create({
  baseURL: `${BACKEND_URL}/api`,
  timeout: 30000,
});

// Market
export const getMarketOverview = () => API.get("/market/overview");

// Stocks
export const getStocks = (params = {}) => API.get("/stocks", { params });
export const getStock = (symbol) => API.get(`/stocks/${symbol}`);
export const getStockAnalysis = (symbol) => API.get(`/stocks/${symbol}/analysis`);
export const getLLMInsight = (symbol, analysisType = "full") =>
  API.post(`/stocks/${symbol}/llm-insight`, { symbol, analysis_type: analysisType });

// Screener
export const screenStocks = (filters) => API.post("/screener", filters);
export const getScreenerPresets = () => API.get("/screener/presets");

// Watchlist
export const getWatchlist = () => API.get("/watchlist");
export const addToWatchlist = (item) => API.post("/watchlist", item);
export const removeFromWatchlist = (symbol) => API.delete(`/watchlist/${symbol}`);
export const updateWatchlistItem = (symbol, updates) => API.put(`/watchlist/${symbol}`, updates);

// Portfolio
export const getPortfolio = () => API.get("/portfolio");
export const addToPortfolio = (holding) => API.post("/portfolio", holding);
export const removeFromPortfolio = (symbol) => API.delete(`/portfolio/${symbol}`);
export const updatePortfolioHolding = (symbol, updates) => API.put(`/portfolio/${symbol}`, updates);

// News
export const getNews = (params = {}) => API.get("/news", { params });
export const getNewsSummary = () => API.get("/news/summary");

// Reports
export const generateReport = (request) => API.post("/reports/generate", request);

// PDF Export
export const downloadPdfReport = async (request) => {
  const response = await API.post("/reports/generate-pdf", request, {
    responseType: "blob",
  });

  // Create download link
  const blob = new Blob([response.data], { type: "application/pdf" });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");

  // Get filename from content-disposition header or use default
  const contentDisposition = response.headers["content-disposition"];
  let filename = "report.pdf";
  if (contentDisposition) {
    const match = contentDisposition.match(/filename=(.+)/);
    if (match) filename = match[1];
  }

  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);

  return response;
};

// Alerts
export const getAlerts = (params = {}) => API.get("/alerts", { params });
export const createAlert = (alert) => API.post("/alerts", alert);
export const getAlert = (alertId) => API.get(`/alerts/${alertId}`);
export const updateAlert = (alertId, updates) => API.put(`/alerts/${alertId}`, updates);
export const deleteAlert = (alertId) => API.delete(`/alerts/${alertId}`);
export const getAlertsSummary = () => API.get("/alerts/summary/stats");
export const getRecentNotifications = () => API.get("/alerts/notifications/recent");
export const checkAlerts = () => API.post("/alerts/check");

// Backtesting
export const getStrategies = () => API.get("/backtest/strategies");
export const getStrategy = (strategyId) => API.get(`/backtest/strategies/${strategyId}`);
export const runBacktest = (config) => API.post("/backtest/run", config);

// Sectors
export const getSectors = () => API.get("/sectors");

// Search
export const searchStocks = (query) => API.get("/search", { params: { q: query } });

// Health
export const healthCheck = () => API.get("/health");

// Data Pipeline
export const getPipelineStatus = () => API.get("/pipeline/status");
export const runPipelineExtraction = (request = {}) => API.post("/pipeline/run", request);
export const startPipelineScheduler = (intervalMinutes = 30) => 
  API.post("/pipeline/scheduler/start", { interval_minutes: intervalMinutes });
export const stopPipelineScheduler = () => API.post("/pipeline/scheduler/stop");
export const getPipelineJobs = (limit = 20) => API.get("/pipeline/jobs", { params: { limit } });
export const getPipelineJob = (jobId) => API.get(`/pipeline/jobs/${jobId}`);
export const getPipelineHistory = (limit = 50) => API.get("/pipeline/history", { params: { limit } });
export const getPipelineLogs = (limit = 100, eventType = null) => 
  API.get("/pipeline/logs", { params: { limit, event_type: eventType } });
export const getPipelineMetrics = () => API.get("/pipeline/metrics");
export const getPipelineDataSummary = () => API.get("/pipeline/data-summary");
export const testGrowAPI = (symbol = "RELIANCE") => API.post("/pipeline/test-api", { symbol });
export const getDefaultSymbols = () => API.get("/pipeline/default-symbols");
export const getSymbolCategories = () => API.get("/pipeline/symbol-categories");
export const addPipelineSymbols = (symbols) => API.post("/pipeline/symbols/add", symbols);
export const removePipelineSymbols = (symbols) => API.post("/pipeline/symbols/remove", symbols);
export const updateSchedulerConfig = (intervalMinutes, autoStart) => 
  API.put("/pipeline/scheduler/config", null, { 
    params: { interval_minutes: intervalMinutes, auto_start: autoStart } 
  });

// Database Dashboard
export const getDatabaseOverview = () => API.get("/database/overview");
export const getDatabaseHealth = () => API.get("/database/health");
export const getDataFlow = () => API.get("/database/data-flow");
export const getThresholdAlerts = () => API.get("/database/threshold-alerts");

// Database Dashboard - MongoDB
export const getMongoCollections = () => API.get("/database/collections");
export const getCollectionSample = (name, page = 1, pageSize = 25) =>
  API.get(`/database/collections/${name}/sample`, { params: { page, page_size: pageSize } });
export const getCollectionSchema = (name) => API.get(`/database/collections/${name}/schema`);
export const deleteCollectionDocument = (name, idField, idValue) =>
  API.delete(`/database/collections/${name}/documents`, { data: { id_field: idField, id_value: idValue } });

// Database Dashboard - PostgreSQL
export const getPgTables = () => API.get("/database/tables");
export const getTableSample = (name, page = 1, pageSize = 25) =>
  API.get(`/database/tables/${name}/sample`, { params: { page, page_size: pageSize } });
export const getTableSchema = (name) => API.get(`/database/tables/${name}/schema`);

// Database Dashboard - Redis
export const getRedisKeys = (prefix = "") => API.get("/database/redis/keys", { params: { prefix } });

// Database Dashboard - Activity & Errors
export const getDatabaseActivity = (limit = 50, collection = null, since = null, until = null) =>
  API.get("/database/activity", { params: { limit, collection, since, until } });
export const getDatabaseErrors = (limit = 50, since = null, until = null) =>
  API.get("/database/errors", { params: { limit, since, until } });
export const getErrorTrend = (days = 7) =>
  API.get("/database/errors/trend", { params: { days } });

// Database Dashboard - Settings
export const getDatabaseSettings = () => API.get("/database/settings");
export const updateDatabaseSettings = (updates) => API.patch("/database/settings", updates);

// Database Dashboard - Audit Log
export const getAuditLog = (page = 1, pageSize = 50, filters = {}) =>
  API.get("/database/audit-log", { params: { page, page_size: pageSize, ...filters } });
export const writeAuditLog = (entry) => API.post("/database/audit-log", entry);

// Cache
export const getCacheStats = () => API.get("/cache/stats");
export const flushCache = () => API.delete("/cache/flush");

// Time-series
export const getTimeseriesStats = () => API.get("/timeseries/stats");

export default API;
