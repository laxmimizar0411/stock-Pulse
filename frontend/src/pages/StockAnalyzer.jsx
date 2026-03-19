import React, { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import ScoreCard, { ScoreBar } from "@/components/ScoreCard";
import { PriceChart, VolumeChart, ScoreRadarChart } from "@/components/Charts";
import { StatRow } from "@/components/MetricCard";
import { getStock, getLLMInsight, addToWatchlist, searchStocks } from "@/lib/api";
import {
  cn,
  formatCurrency,
  formatPercent,
  formatNumber,
  getVerdictColor,
  getChangeColor,
  getApiErrorMessage,
} from "@/lib/utils";
import {
  TrendingUp,
  TrendingDown,
  Star,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Sparkles,
  Search,
  ArrowUp,
  ArrowDown,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

export default function StockAnalyzer() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [symbol, setSymbol] = useState(searchParams.get("symbol") || "");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [stock, setStock] = useState(null);
  const [loading, setLoading] = useState(false);
  const [llmInsight, setLlmInsight] = useState(null);
  const [llmLoading, setLlmLoading] = useState(false);

  useEffect(() => {
    if (symbol) {
      fetchStock(symbol);
    }
  }, [symbol]);

  useEffect(() => {
    const urlSymbol = searchParams.get("symbol");
    if (urlSymbol && urlSymbol !== symbol) {
      setSymbol(urlSymbol);
    }
  }, [searchParams, symbol]);

  const fetchStock = async (sym) => {
    setLoading(true);
    setLlmInsight(null);
    try {
      const response = await getStock(sym);
      setStock(response.data);
    } catch (error) {
      console.error("Failed to fetch stock:", error);
      toast.error(getApiErrorMessage(error, "Stock not found"));
      setStock(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (query) => {
    setSearchQuery(query);
    if (query.length < 1) {
      setSearchResults([]);
      return;
    }
    try {
      const response = await searchStocks(query);
      setSearchResults(response.data);
    } catch (error) {
      console.error("Search failed:", error);
    }
  };

  const selectStock = (sym) => {
    setSearchQuery("");
    setSearchResults([]);
    setSymbol(sym);
    navigate(`/analyzer?symbol=${sym}`);
  };

  const fetchLLMInsight = async () => {
    if (!stock) return;
    setLlmLoading(true);
    try {
      const response = await getLLMInsight(stock.symbol, "full");
      setLlmInsight(response.data.insight);
    } catch (error) {
      console.error("Failed to fetch LLM insight:", error);
      toast.error(getApiErrorMessage(error, "Failed to generate AI insights"));
    } finally {
      setLlmLoading(false);
    }
  };

  const handleAddToWatchlist = async () => {
    if (!stock) return;
    try {
      await addToWatchlist({
        symbol: stock.symbol,
        name: stock.name,
      });
      toast.success(`${stock.symbol} added to watchlist`);
    } catch (error) {
      if (error.response?.status === 400) {
        toast.info("Already in watchlist");
      } else {
        toast.error(getApiErrorMessage(error, "Failed to add to watchlist"));
      }
    }
  };

  if (!symbol && !loading) {
    return (
      <div className="space-y-6" data-testid="stock-analyzer-empty">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight">Stock Analyzer</h1>
          <p className="text-muted-foreground">Deep-dive analysis with AI-powered insights</p>
        </div>

        <Card className="bg-[#18181B] border-[#27272A]">
          <CardContent className="p-6">
            <div className="relative max-w-md mx-auto">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search for a stock (e.g., RELIANCE, TCS)"
                className="pl-10 bg-background"
                value={searchQuery}
                onChange={(e) => handleSearch(e.target.value)}
                data-testid="analyzer-search-input"
              />
              {searchResults.length > 0 && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-[#18181B] border border-[#27272A] rounded-sm shadow-lg z-10">
                  {searchResults.map((result) => (
                    <button
                      key={result.symbol}
                      className="w-full px-4 py-2 text-left hover:bg-[#27272A] flex justify-between items-center"
                      onClick={() => selectStock(result.symbol)}
                      data-testid={`search-result-${result.symbol}`}
                    >
                      <div>
                        <span className="font-mono font-semibold">{result.symbol}</span>
                        <span className="text-muted-foreground ml-2">{result.name}</span>
                      </div>
                      <span className="text-xs text-muted-foreground">{result.sector}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <p className="text-center text-muted-foreground mt-4">
              Enter a stock symbol to begin analysis
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (loading) {
    return <AnalyzerSkeleton />;
  }

  if (!stock) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Stock not found</p>
      </div>
    );
  }

  const { analysis, ml_prediction, fundamentals, valuation, technicals, shareholding } = stock;

  return (
    <div className="space-y-6" data-testid="stock-analyzer">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-4xl font-bold font-heading tracking-tight">{stock.symbol}</h1>
            <Badge className={cn("text-sm", getVerdictColor(analysis?.verdict))}>
              {analysis?.verdict || "ANALYZING"}
            </Badge>
          </div>
          <p className="text-muted-foreground">{stock.name}</p>
          <div className="flex items-center gap-2 mt-1 text-sm text-muted-foreground">
            <span>{stock.sector}</span>
            <span>•</span>
            <span>{stock.industry}</span>
            <span>•</span>
            <span>{stock.market_cap_category} Cap</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleAddToWatchlist}
            data-testid="add-watchlist-btn"
          >
            <Star className="w-4 h-4 mr-1" />
            Add to Watchlist
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchStock(symbol)}
            data-testid="refresh-btn"
          >
            <RefreshCw className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Price & Scores Row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Price Card */}
        <Card className="bg-[#18181B] border-[#27272A] md:col-span-2">
          <CardContent className="p-6">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground mb-1">Current Price</p>
                <p className="text-4xl font-bold font-mono">
                  {formatCurrency(stock.current_price)}
                </p>
                <div
                  className={cn(
                    "flex items-center gap-2 mt-2",
                    getChangeColor(stock.price_change_percent)
                  )}
                >
                  {stock.price_change_percent >= 0 ? (
                    <ArrowUp className="w-4 h-4" />
                  ) : (
                    <ArrowDown className="w-4 h-4" />
                  )}
                  <span className="font-mono">
                    {formatCurrency(Math.abs(stock.price_change))} (
                    {formatPercent(stock.price_change_percent)})
                  </span>
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs text-muted-foreground">52W Range</p>
                <p className="font-mono text-sm">
                  {formatCurrency(technicals?.low_52_week)} - {formatCurrency(technicals?.high_52_week)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Score Cards */}
        <Card className="bg-[#18181B] border-[#27272A]">
          <CardContent className="p-4 flex items-center justify-center">
            <ScoreCard
              label="Long-Term Score"
              score={analysis?.long_term_score || 0}
              subtitle={`Confidence: ${analysis?.confidence_level || "N/A"}`}
              size="large"
            />
          </CardContent>
        </Card>

        <Card className="bg-[#18181B] border-[#27272A]">
          <CardContent className="p-4 flex items-center justify-center">
            <ScoreCard
              label="Short-Term Score"
              score={analysis?.short_term_score || 0}
              subtitle={ml_prediction?.price_direction_short || ""}
              size="large"
            />
          </CardContent>
        </Card>
      </div>

      {/* Price Chart */}
      <Card className="bg-[#18181B] border-[#27272A]">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Price Chart (90 Days)</CardTitle>
        </CardHeader>
        <CardContent>
          <PriceChart data={stock.price_history} height={300} showAxis />
          <VolumeChart data={stock.price_history} height={80} />
        </CardContent>
      </Card>

      {/* Main Analysis Tabs */}
      <Tabs defaultValue="fundamental" className="space-y-4">
        <TabsList className="bg-[#18181B] border border-[#27272A]">
          <TabsTrigger value="fundamental" data-testid="tab-fundamental">Fundamentals</TabsTrigger>
          <TabsTrigger value="technical" data-testid="tab-technical">Technicals</TabsTrigger>
          <TabsTrigger value="valuation" data-testid="tab-valuation">Valuation</TabsTrigger>
          <TabsTrigger value="checklist" data-testid="tab-checklist">Checklist</TabsTrigger>
          <TabsTrigger value="scenarios" data-testid="tab-scenarios">Scenarios</TabsTrigger>
        </TabsList>

        {/* Fundamental Tab */}
        <TabsContent value="fundamental" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Revenue & Growth */}
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Revenue & Growth</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                <StatRow label="Revenue (TTM)" value={formatCurrency(fundamentals?.revenue_ttm * 100000)} />
                <StatRow label="Revenue Growth (YoY)" value={`${fundamentals?.revenue_growth_yoy}%`} />
                <StatRow label="Net Profit" value={formatCurrency(fundamentals?.net_profit * 100000)} />
                <StatRow label="EPS" value={`₹${fundamentals?.eps}`} />
              </CardContent>
            </Card>

            {/* Profitability */}
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Profitability</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                <StatRow label="Gross Margin" value={`${fundamentals?.gross_margin}%`} />
                <StatRow label="Operating Margin" value={`${fundamentals?.operating_margin}%`} />
                <StatRow label="Net Profit Margin" value={`${fundamentals?.net_profit_margin}%`} />
                <StatRow label="ROE" value={`${fundamentals?.roe}%`} />
                <StatRow label="ROA" value={`${fundamentals?.roa}%`} />
                <StatRow label="ROIC" value={`${fundamentals?.roic}%`} />
              </CardContent>
            </Card>

            {/* Debt & Cash Flow */}
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Debt & Cash Flow</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                <StatRow label="Debt/Equity" value={fundamentals?.debt_to_equity} />
                <StatRow label="Interest Coverage" value={`${fundamentals?.interest_coverage}x`} />
                <StatRow label="Free Cash Flow" value={formatCurrency(fundamentals?.free_cash_flow * 100000)} />
                <StatRow label="Current Ratio" value={fundamentals?.current_ratio} />
                <StatRow label="Quick Ratio" value={fundamentals?.quick_ratio} />
              </CardContent>
            </Card>

            {/* Shareholding */}
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Shareholding Pattern</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                <StatRow label="Promoter Holding" value={`${shareholding?.promoter_holding}%`} />
                <StatRow label="FII Holding" value={`${shareholding?.fii_holding}%`} />
                <StatRow label="DII Holding" value={`${shareholding?.dii_holding}%`} />
                <StatRow label="Public Holding" value={`${shareholding?.public_holding}%`} />
                <StatRow
                  label="Promoter Pledging"
                  value={`${shareholding?.promoter_pledging}%`}
                  className={shareholding?.promoter_pledging > 20 ? "text-red-500" : ""}
                />
              </CardContent>
            </Card>

            {/* Score Breakdown */}
            <Card className="bg-[#18181B] border-[#27272A] md:col-span-2">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Score Breakdown</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-8">
                  <div className="space-y-3">
                    <ScoreBar label="Fundamental" score={analysis?.score_breakdown?.fundamental_score || 0} />
                    <ScoreBar label="Valuation" score={analysis?.score_breakdown?.valuation_score || 0} />
                    <ScoreBar label="Technical" score={analysis?.score_breakdown?.technical_score || 0} />
                    <ScoreBar label="Quality" score={analysis?.score_breakdown?.quality_score || 0} />
                    <ScoreBar label="Risk" score={analysis?.score_breakdown?.risk_score || 0} />
                  </div>
                  <ScoreRadarChart data={analysis?.score_breakdown} height={200} />
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Technical Tab */}
        <TabsContent value="technical" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Moving Averages</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                <StatRow
                  label="50-Day SMA"
                  value={formatCurrency(technicals?.sma_50)}
                  subvalue={stock.current_price > technicals?.sma_50 ? "Above" : "Below"}
                />
                <StatRow
                  label="200-Day SMA"
                  value={formatCurrency(technicals?.sma_200)}
                  subvalue={stock.current_price > technicals?.sma_200 ? "Above" : "Below"}
                />
              </CardContent>
            </Card>

            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Momentum Indicators</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                <StatRow
                  label="RSI (14)"
                  value={technicals?.rsi_14}
                  subvalue={
                    technicals?.rsi_14 < 30
                      ? "Oversold"
                      : technicals?.rsi_14 > 70
                        ? "Overbought"
                        : "Neutral"
                  }
                />
                <StatRow label="MACD" value={formatNumber(technicals?.macd)} />
                <StatRow label="MACD Signal" value={formatNumber(technicals?.macd_signal)} />
              </CardContent>
            </Card>

            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Support & Resistance</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                <StatRow label="Resistance" value={formatCurrency(technicals?.resistance_level)} />
                <StatRow label="Support" value={formatCurrency(technicals?.support_level)} />
                <StatRow label="Bollinger Upper" value={formatCurrency(technicals?.bollinger_upper)} />
                <StatRow label="Bollinger Lower" value={formatCurrency(technicals?.bollinger_lower)} />
              </CardContent>
            </Card>

            {/* ML Prediction */}
            <Card className="bg-[#18181B] border-[#27272A] md:col-span-3">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-[#3B82F6]" />
                  ML Predictions
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                  <div className="text-center">
                    <p className="text-xs text-muted-foreground mb-1">Price Direction</p>
                    <Badge
                      className={cn(
                        ml_prediction?.price_direction_short === "UP"
                          ? "bg-green-500/10 text-green-500"
                          : ml_prediction?.price_direction_short === "DOWN"
                            ? "bg-red-500/10 text-red-500"
                            : "bg-muted text-muted-foreground"
                      )}
                    >
                      {ml_prediction?.price_direction_short || "N/A"}
                    </Badge>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-muted-foreground mb-1">Confidence</p>
                    <p className="font-mono">
                      {((ml_prediction?.price_direction_probability || 0) * 100).toFixed(0)}%
                    </p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-muted-foreground mb-1">Volatility (5D)</p>
                    <p className="font-mono">{ml_prediction?.volatility_forecast || 0}%</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-muted-foreground mb-1">Anomaly Score</p>
                    <p className="font-mono">{ml_prediction?.anomaly_score || 0}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-muted-foreground mb-1">Sentiment</p>
                    <p className="font-mono">{ml_prediction?.sentiment_score?.toFixed(2) || 0}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Valuation Tab */}
        <TabsContent value="valuation" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Valuation Ratios</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                <StatRow label="P/E Ratio" value={valuation?.pe_ratio} />
                <StatRow label="PEG Ratio" value={valuation?.peg_ratio} />
                <StatRow label="P/B Ratio" value={valuation?.pb_ratio} />
                <StatRow label="P/S Ratio" value={valuation?.ps_ratio} />
                <StatRow label="EV/EBITDA" value={valuation?.ev_ebitda} />
                <StatRow label="Dividend Yield" value={`${valuation?.dividend_yield}%`} />
              </CardContent>
            </Card>

            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Market Data</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                <StatRow label="Market Cap" value={formatCurrency(valuation?.market_cap)} />
                <StatRow label="Avg Volume (20D)" value={formatNumber(technicals?.volume_avg_20, 0)} />
                <StatRow label="52W High" value={formatCurrency(technicals?.high_52_week)} />
                <StatRow label="52W Low" value={formatCurrency(technicals?.low_52_week)} />
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Checklist Tab */}
        <TabsContent value="checklist" className="space-y-4">
          {/* Investment Checklists Summary */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Short-Term Checklist Summary Card */}
            <Card className={cn(
              "bg-[#18181B] border-2",
              analysis?.investment_checklists?.short_term?.summary?.verdict === "PASS"
                ? "border-green-500/50"
                : analysis?.investment_checklists?.short_term?.summary?.verdict === "FAIL"
                  ? "border-red-500/50"
                  : "border-yellow-500/50"
            )}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    📋 Short-Term Checklist
                    <Badge variant="outline" className="text-xs">1-6 months</Badge>
                  </CardTitle>
                  <Badge
                    className={cn(
                      "text-xs",
                      analysis?.investment_checklists?.short_term?.summary?.verdict === "PASS"
                        ? "bg-green-500/20 text-green-400"
                        : analysis?.investment_checklists?.short_term?.summary?.verdict === "FAIL"
                          ? "bg-red-500/20 text-red-400"
                          : "bg-yellow-500/20 text-yellow-400"
                    )}
                  >
                    {analysis?.investment_checklists?.short_term?.summary?.verdict || "N/A"}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-4 mb-4">
                  <div className="text-center">
                    <p className="text-3xl font-bold font-mono text-green-400">
                      {analysis?.investment_checklists?.short_term?.summary?.passed || 0}
                    </p>
                    <p className="text-xs text-muted-foreground">Passed</p>
                  </div>
                  <div className="text-center">
                    <p className="text-3xl font-bold font-mono text-red-400">
                      {analysis?.investment_checklists?.short_term?.summary?.failed || 0}
                    </p>
                    <p className="text-xs text-muted-foreground">Failed</p>
                  </div>
                  <div className="text-center flex-1">
                    <p className="text-3xl font-bold font-mono">
                      {analysis?.investment_checklists?.short_term?.summary?.score || 0}%
                    </p>
                    <p className="text-xs text-muted-foreground">Score</p>
                  </div>
                </div>
                {analysis?.investment_checklists?.short_term?.summary?.deal_breaker_failures > 0 && (
                  <div className="bg-red-500/10 border border-red-500/30 rounded-md p-2 mb-3">
                    <p className="text-xs text-red-400 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" />
                      {analysis?.investment_checklists?.short_term?.summary?.deal_breaker_failures} Deal-Breaker(s) Failed
                    </p>
                  </div>
                )}
                <ScrollArea className="h-[280px] pr-4">
                  <div className="space-y-2">
                    {(analysis?.investment_checklists?.short_term?.checklist || []).map((item, idx) => (
                      <div
                        key={idx}
                        className={cn(
                          "p-2 rounded-md border",
                          item.passed
                            ? "bg-green-500/5 border-green-500/20"
                            : item.is_deal_breaker
                              ? "bg-red-500/10 border-red-500/30"
                              : "bg-red-500/5 border-red-500/20"
                        )}
                      >
                        <div className="flex items-start gap-2">
                          {item.passed ? (
                            <CheckCircle className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                          ) : (
                            <XCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                          )}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] font-mono text-muted-foreground">{item.id}</span>
                              {item.is_deal_breaker && (
                                <Badge variant="destructive" className="text-[9px] px-1 py-0">DEAL-BREAKER</Badge>
                              )}
                            </div>
                            <p className="text-xs font-medium leading-tight">{item.criterion}</p>
                            <p className="text-[10px] text-muted-foreground mt-0.5">{item.value}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>

            {/* Long-Term Checklist Summary Card */}
            <Card className={cn(
              "bg-[#18181B] border-2",
              analysis?.investment_checklists?.long_term?.summary?.verdict === "PASS"
                ? "border-green-500/50"
                : analysis?.investment_checklists?.long_term?.summary?.verdict === "FAIL"
                  ? "border-red-500/50"
                  : "border-yellow-500/50"
            )}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    📋 Long-Term Checklist
                    <Badge variant="outline" className="text-xs">3-10+ years</Badge>
                  </CardTitle>
                  <Badge
                    className={cn(
                      "text-xs",
                      analysis?.investment_checklists?.long_term?.summary?.verdict === "PASS"
                        ? "bg-green-500/20 text-green-400"
                        : analysis?.investment_checklists?.long_term?.summary?.verdict === "FAIL"
                          ? "bg-red-500/20 text-red-400"
                          : "bg-yellow-500/20 text-yellow-400"
                    )}
                  >
                    {analysis?.investment_checklists?.long_term?.summary?.verdict || "N/A"}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-4 mb-4">
                  <div className="text-center">
                    <p className="text-3xl font-bold font-mono text-green-400">
                      {analysis?.investment_checklists?.long_term?.summary?.passed || 0}
                    </p>
                    <p className="text-xs text-muted-foreground">Passed</p>
                  </div>
                  <div className="text-center">
                    <p className="text-3xl font-bold font-mono text-red-400">
                      {analysis?.investment_checklists?.long_term?.summary?.failed || 0}
                    </p>
                    <p className="text-xs text-muted-foreground">Failed</p>
                  </div>
                  <div className="text-center flex-1">
                    <p className="text-3xl font-bold font-mono">
                      {analysis?.investment_checklists?.long_term?.summary?.score || 0}%
                    </p>
                    <p className="text-xs text-muted-foreground">Score</p>
                  </div>
                </div>
                {analysis?.investment_checklists?.long_term?.summary?.deal_breaker_failures > 0 && (
                  <div className="bg-red-500/10 border border-red-500/30 rounded-md p-2 mb-3">
                    <p className="text-xs text-red-400 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" />
                      {analysis?.investment_checklists?.long_term?.summary?.deal_breaker_failures} Deal-Breaker(s) Failed
                    </p>
                  </div>
                )}
                <ScrollArea className="h-[280px] pr-4">
                  <div className="space-y-2">
                    {(analysis?.investment_checklists?.long_term?.checklist || []).map((item, idx) => (
                      <div
                        key={idx}
                        className={cn(
                          "p-2 rounded-md border",
                          item.passed
                            ? "bg-green-500/5 border-green-500/20"
                            : item.is_deal_breaker
                              ? "bg-red-500/10 border-red-500/30"
                              : "bg-red-500/5 border-red-500/20"
                        )}
                      >
                        <div className="flex items-start gap-2">
                          {item.passed ? (
                            <CheckCircle className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                          ) : (
                            <XCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                          )}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] font-mono text-muted-foreground">{item.id}</span>
                              {item.is_deal_breaker && (
                                <Badge variant="destructive" className="text-[9px] px-1 py-0">DEAL-BREAKER</Badge>
                              )}
                            </div>
                            <p className="text-xs font-medium leading-tight">{item.criterion}</p>
                            <p className="text-[10px] text-muted-foreground mt-0.5">{item.value}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>
          </div>

          {/* Deal Breakers, Strengths & Risks Row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Deal Breakers */}
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-500" />
                  Deal Breaker Checks (D1-D10)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[200px] pr-2">
                  <div className="space-y-2">
                    {(analysis?.deal_breakers || []).map((db, idx) => (
                      <div
                        key={idx}
                        className={cn(
                          "flex items-start gap-2 p-2 rounded-sm",
                          db.triggered ? "bg-red-500/10" : "bg-green-500/5"
                        )}
                      >
                        {db.triggered ? (
                          <XCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                        ) : (
                          <CheckCircle className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                        )}
                        <div className="min-w-0">
                          <p className="text-xs">{db.description}</p>
                          <p className="text-[10px] text-muted-foreground">
                            Value: {typeof db.value === 'number' ? db.value?.toFixed(2) : db.value} | Threshold: {db.threshold}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>

            {/* Key Strengths */}
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-green-500" />
                  Key Strengths
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {(analysis?.top_strengths || []).map((strength, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-sm">
                      <CheckCircle className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                      <span className="text-xs">{strength}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            {/* Key Risks */}
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <TrendingDown className="w-4 h-4 text-red-500" />
                  Key Risks
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {(analysis?.top_risks || []).map((risk, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-sm">
                      <AlertTriangle className="w-4 h-4 text-yellow-500 mt-0.5 flex-shrink-0" />
                      <span className="text-xs">{risk}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Scenarios Tab */}
        <TabsContent value="scenarios" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Bull Case */}
            <Card className="bg-[#18181B] border-green-500/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2 text-green-500">
                  <TrendingUp className="w-4 h-4" />
                  Bull Case
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-muted-foreground">Target Price</p>
                    <p className="font-mono text-xl text-green-500">
                      {formatCurrency(analysis?.bull_case?.target_price)}
                    </p>
                    <p className="text-sm text-green-500">
                      +{analysis?.bull_case?.upside_percent}% upside
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Probability</p>
                    <p className="font-mono">{analysis?.bull_case?.probability}%</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Catalysts</p>
                    <ul className="text-sm space-y-1">
                      {(analysis?.bull_case?.catalysts || []).map((c, i) => (
                        <li key={i} className="text-muted-foreground">• {c}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Base Case */}
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Base Case</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-muted-foreground">Fair Value</p>
                    <p className="font-mono text-xl">
                      {formatCurrency(analysis?.base_case?.target_price)}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      +{analysis?.base_case?.return_percent}% expected
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Probability</p>
                    <p className="font-mono">{analysis?.base_case?.probability}%</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Scenario</p>
                    <p className="text-sm text-muted-foreground">
                      {analysis?.base_case?.scenario}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Bear Case */}
            <Card className="bg-[#18181B] border-red-500/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2 text-red-500">
                  <TrendingDown className="w-4 h-4" />
                  Bear Case
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-muted-foreground">Target Price</p>
                    <p className="font-mono text-xl text-red-500">
                      {formatCurrency(analysis?.bear_case?.target_price)}
                    </p>
                    <p className="text-sm text-red-500">
                      {analysis?.bear_case?.downside_percent}% downside
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Probability</p>
                    <p className="font-mono">{analysis?.bear_case?.probability}%</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Risks</p>
                    <ul className="text-sm space-y-1">
                      {(analysis?.bear_case?.risks || []).map((r, i) => (
                        <li key={i} className="text-muted-foreground">• {r}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      {/* AI Insights Section */}
      <Card className="bg-[#18181B] border-[#27272A]">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#3B82F6]" />
              AI-Powered Analysis
            </CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchLLMInsight}
              disabled={llmLoading}
              data-testid="generate-ai-insight-btn"
            >
              {llmLoading ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                  Generating...
                </>
              ) : (
                "Generate Insights"
              )}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {llmInsight ? (
            <div className="prose prose-invert prose-sm max-w-none">
              <div className="whitespace-pre-wrap text-sm leading-relaxed">{llmInsight}</div>
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">
              Click &quot;Generate Insights&quot; to get AI-powered analysis including investment thesis,
              key factors, and actionable recommendations.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function AnalyzerSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between">
        <div>
          <Skeleton className="h-10 w-32" />
          <Skeleton className="h-5 w-48 mt-2" />
        </div>
        <Skeleton className="h-9 w-32" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Skeleton className="h-32 md:col-span-2" />
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
      <Skeleton className="h-96" />
    </div>
  );
}
