import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { generateReport, searchStocks, downloadPdfReport } from "@/lib/api";
import { cn, formatCurrency, getVerdictColor, getScoreColor, getApiErrorMessage } from "@/lib/utils";
import {
  FileText,
  Search,
  X,
  TrendingUp,
  BarChart3,
  Briefcase,
  Sparkles,
  Download,
} from "lucide-react";
import { toast } from "sonner";

const REPORT_TYPES = [
  {
    id: "single_stock",
    title: "Single Stock Report",
    description: "Comprehensive analysis report for one stock",
    icon: FileText,
    color: "text-[#3B82F6]",
    bgColor: "bg-[#3B82F6]/10",
  },
  {
    id: "comparison",
    title: "Stock Comparison",
    description: "Compare 2-5 stocks side by side",
    icon: BarChart3,
    color: "text-green-500",
    bgColor: "bg-green-500/10",
  },
  {
    id: "portfolio_health",
    title: "Portfolio Health",
    description: "Analyze your portfolio health and diversification",
    icon: Briefcase,
    color: "text-purple-500",
    bgColor: "bg-purple-500/10",
  },
];

function ReportTypeCard({ type, selected, onSelect }) {
  return (
    <Card
      className={cn(
        "bg-[#18181B] border-[#27272A] cursor-pointer transition-all",
        selected ? "border-[#3B82F6] ring-1 ring-[#3B82F6]" : "hover:border-[#3B82F6]/50"
      )}
      onClick={onSelect}
      data-testid={`report-type-${type.id}`}
    >
      <CardContent className="p-6">
        <div className={cn("w-10 h-10 rounded-sm flex items-center justify-center mb-3", type.bgColor)}>
          <type.icon className={cn("w-5 h-5", type.color)} />
        </div>
        <h3 className="font-semibold mb-1">{type.title}</h3>
        <p className="text-sm text-muted-foreground">{type.description}</p>
      </CardContent>
    </Card>
  );
}

function SymbolBadge({ stock, onRemove }) {
  return (
    <Badge variant="secondary" className="flex items-center gap-1 px-3 py-1">
      <span className="font-mono">{stock.symbol}</span>
      <button onClick={onRemove} className="ml-1 hover:text-red-500">
        <X className="w-3 h-3" />
      </button>
    </Badge>
  );
}

function SingleStockReport({ data }) {
  if (!data) return null;

  const analysisVerdict = data.analysis?.verdict || "N/A";
  const ltScore = data.analysis?.long_term_score || 0;
  const stScore = data.analysis?.short_term_score || 0;
  const confidenceLevel = data.analysis?.confidence_level || "N/A";

  return (
    <div className="space-y-6">
      <Card className="bg-[#18181B] border-[#27272A]">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl font-heading">
                {data.symbol} - {data.name}
              </CardTitle>
              <CardDescription>
                {data.sector} • {data.industry}
              </CardDescription>
            </div>
            <Badge className={cn("text-lg px-4 py-1", getVerdictColor(analysisVerdict))}>
              {analysisVerdict}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div>
              <p className="text-sm text-muted-foreground">Current Price</p>
              <p className="text-2xl font-mono font-bold">
                {formatCurrency(data.current_price)}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Long-Term Score</p>
              <p className={cn("text-2xl font-mono font-bold", getScoreColor(ltScore))}>
                {Math.round(ltScore)}/100
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Short-Term Score</p>
              <p className={cn("text-2xl font-mono font-bold", getScoreColor(stScore))}>
                {Math.round(stScore)}/100
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Confidence</p>
              <p className="text-2xl font-bold">{confidenceLevel}</p>
            </div>
          </div>

          {data.llm_insight && (
            <div className="bg-[#27272A] rounded-sm p-4 mt-4">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles className="w-4 h-4 text-[#3B82F6]" />
                <span className="font-medium">AI Analysis</span>
              </div>
              <div className="text-sm whitespace-pre-wrap">{data.llm_insight}</div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ComparisonReport({ data }) {
  if (!data || data.length === 0) return null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-[#27272A]">
            <th className="text-left py-3 px-4">Metric</th>
            {data.map((stock) => (
              <th key={stock.symbol} className="text-center py-3 px-4 font-mono">
                {stock.symbol}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-[#27272A]">
            <td className="py-3 px-4 text-muted-foreground">Price</td>
            {data.map((stock) => (
              <td key={stock.symbol} className="text-center py-3 px-4 font-mono">
                {formatCurrency(stock.current_price)}
              </td>
            ))}
          </tr>
          <tr className="border-b border-[#27272A]">
            <td className="py-3 px-4 text-muted-foreground">LT Score</td>
            {data.map((stock) => {
              const score = stock.analysis?.long_term_score || 0;
              return (
                <td
                  key={stock.symbol}
                  className={cn("text-center py-3 px-4 font-mono font-bold", getScoreColor(score))}
                >
                  {Math.round(score)}
                </td>
              );
            })}
          </tr>
          <tr className="border-b border-[#27272A]">
            <td className="py-3 px-4 text-muted-foreground">Verdict</td>
            {data.map((stock) => {
              const verdict = stock.analysis?.verdict || "N/A";
              return (
                <td key={stock.symbol} className="text-center py-3 px-4">
                  <Badge className={cn("text-xs", getVerdictColor(verdict))}>{verdict}</Badge>
                </td>
              );
            })}
          </tr>
          <tr className="border-b border-[#27272A]">
            <td className="py-3 px-4 text-muted-foreground">ROE</td>
            {data.map((stock) => (
              <td key={stock.symbol} className="text-center py-3 px-4 font-mono">
                {stock.fundamentals?.roe || 0}%
              </td>
            ))}
          </tr>
          <tr className="border-b border-[#27272A]">
            <td className="py-3 px-4 text-muted-foreground">P/E Ratio</td>
            {data.map((stock) => (
              <td key={stock.symbol} className="text-center py-3 px-4 font-mono">
                {stock.valuation?.pe_ratio || 0}
              </td>
            ))}
          </tr>
          <tr className="border-b border-[#27272A]">
            <td className="py-3 px-4 text-muted-foreground">Debt/Equity</td>
            {data.map((stock) => (
              <td key={stock.symbol} className="text-center py-3 px-4 font-mono">
                {stock.fundamentals?.debt_to_equity || 0}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function PortfolioHealthReport({ data }) {
  if (!data) return null;

  const recommendations = data.recommendations || [];
  const portfolioValue = data.portfolio?.current_value || 0;
  const portfolioPL = data.portfolio?.total_profit_loss || 0;

  return (
    <div className="space-y-4">
      <Card className="bg-[#18181B] border-[#27272A]">
        <CardHeader>
          <CardTitle>Portfolio Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Total Value</p>
              <p className="text-2xl font-mono font-bold">{formatCurrency(portfolioValue)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Total P&L</p>
              <p className={cn("text-2xl font-mono font-bold", portfolioPL >= 0 ? "text-green-500" : "text-red-500")}>
                {formatCurrency(portfolioPL)}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Diversification</p>
              <p className="text-2xl font-bold">{data.diversification_score || 0}/100</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Risk Level</p>
              <Badge
                className={cn(
                  data.risk_assessment === "HIGH"
                    ? "bg-red-500/10 text-red-500"
                    : data.risk_assessment === "MODERATE"
                      ? "bg-yellow-500/10 text-yellow-500"
                      : "bg-green-500/10 text-green-500"
                )}
              >
                {data.risk_assessment || "N/A"}
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="bg-[#18181B] border-[#27272A]">
        <CardHeader>
          <CardTitle>Recommendations</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2">
            {recommendations.map((rec, i) => (
              <li key={i} className="flex items-start gap-2">
                <TrendingUp className="w-4 h-4 text-[#3B82F6] mt-0.5" />
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

export default function Reports() {
  const [selectedType, setSelectedType] = useState(null);
  const [symbols, setSymbols] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);

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

  const addSymbol = (stock) => {
    const exists = symbols.find((s) => s.symbol === stock.symbol);
    if (!exists) {
      setSymbols([...symbols, stock]);
    }
    setSearchQuery("");
    setSearchResults([]);
  };

  const removeSymbol = (symbol) => {
    setSymbols(symbols.filter((s) => s.symbol !== symbol));
  };

  const handleGenerateReport = async () => {
    if (!selectedType) {
      toast.error("Please select a report type");
      return;
    }

    if ((selectedType === "single_stock" || selectedType === "comparison") && symbols.length === 0) {
      toast.error("Please add at least one stock");
      return;
    }

    if (selectedType === "comparison" && symbols.length < 2) {
      toast.error("Please add at least 2 stocks for comparison");
      return;
    }

    setLoading(true);
    try {
      const response = await generateReport({
        report_type: selectedType,
        symbols: symbols.map((s) => s.symbol),
      });
      setReport(response.data);
      toast.success("Report generated successfully");
    } catch (error) {
      console.error("Failed to generate report:", error);
      toast.error(getApiErrorMessage(error, "Failed to generate report"));
    } finally {
      setLoading(false);
    }
  };

  const resetReport = () => {
    setReport(null);
    setSelectedType(null);
    setSymbols([]);
  };

  const needsStockSelection = selectedType === "single_stock" || selectedType === "comparison";
  const maxSymbols = selectedType === "single_stock" ? 1 : 5;
  const canAddMore = symbols.length < maxSymbols;

  return (
    <div className="space-y-6" data-testid="reports">
      <div>
        <h1 className="text-3xl font-bold font-heading tracking-tight">Reports</h1>
        <p className="text-muted-foreground">Generate detailed analysis reports</p>
      </div>

      {!report ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {REPORT_TYPES.map((type) => (
              <ReportTypeCard
                key={type.id}
                type={type}
                selected={selectedType === type.id}
                onSelect={() => setSelectedType(type.id)}
              />
            ))}
          </div>

          {needsStockSelection && (
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium">
                  {selectedType === "single_stock" ? "Select Stock" : "Select Stocks (2-5)"}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {symbols.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {symbols.map((stock) => (
                      <SymbolBadge
                        key={stock.symbol}
                        stock={stock}
                        onRemove={() => removeSymbol(stock.symbol)}
                      />
                    ))}
                  </div>
                )}

                {canAddMore && (
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      placeholder="Search stocks..."
                      className="pl-10 bg-background"
                      value={searchQuery}
                      onChange={(e) => handleSearch(e.target.value)}
                      data-testid="report-search-input"
                    />
                    {searchResults.length > 0 && (
                      <div className="absolute top-full left-0 right-0 mt-1 bg-[#18181B] border border-[#27272A] rounded-sm shadow-lg z-10 max-h-48 overflow-auto">
                        {searchResults.map((stock) => (
                          <button
                            key={stock.symbol}
                            className="w-full px-3 py-2 text-left hover:bg-[#27272A] flex justify-between"
                            onClick={() => addSymbol(stock)}
                          >
                            <span className="font-mono font-semibold">{stock.symbol}</span>
                            <span className="text-muted-foreground">{stock.name}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          <Button
            size="lg"
            onClick={handleGenerateReport}
            disabled={loading || !selectedType}
            data-testid="generate-report-btn"
          >
            {loading ? "Generating..." : "Generate Report"}
          </Button>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold font-heading">
                {report.report_type === "single_stock" && "Stock Analysis Report"}
                {report.report_type === "comparison" && "Stock Comparison Report"}
                {report.report_type === "portfolio_health" && "Portfolio Health Report"}
              </h2>
              <p className="text-sm text-muted-foreground">
                Generated on {new Date(report.generated_at).toLocaleString()}
              </p>
            </div>
            <Button variant="outline" onClick={resetReport} data-testid="new-report-btn">
              New Report
            </Button>
            <Button
              variant="default"
              onClick={async () => {
                try {
                  toast.info("Generating PDF...");
                  await downloadPdfReport({
                    report_type: report.report_type,
                    symbols: report.report_type === "portfolio_health" ? [] : symbols.map(s => s.symbol),
                  });
                  toast.success("PDF downloaded!");
                } catch (error) {
                  console.error("PDF download error:", error);
                  toast.error(getApiErrorMessage(error, "Failed to download PDF"));
                }
              }}
              data-testid="download-pdf-btn"
            >
              <Download className="w-4 h-4 mr-2" />
              Download PDF
            </Button>
          </div>

          {report.report_type === "single_stock" && <SingleStockReport data={report.data} />}
          {report.report_type === "comparison" && <ComparisonReport data={report.data} />}
          {report.report_type === "portfolio_health" && <PortfolioHealthReport data={report.data} />}
        </div>
      )}
    </div>
  );
}
