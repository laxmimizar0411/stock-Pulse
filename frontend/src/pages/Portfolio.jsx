import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AllocationPieChart } from "@/components/Charts";
import MetricCard from "@/components/MetricCard";
import { getPortfolio, addToPortfolio, removeFromPortfolio, searchStocks } from "@/lib/api";
import { cn, formatCurrency, formatPercent, getChangeColor, getApiErrorMessage } from "@/lib/utils";
import {
  Briefcase,
  Plus,
  Trash2,
  TrendingUp,
  TrendingDown,
  Search,
  PieChart,
  BarChart3,
  Wallet,
} from "lucide-react";
import { toast } from "sonner";

function HoldingRow({ holding, onRemove, onNavigate }) {
  return (
    <TableRow className="border-[#27272A] cursor-pointer hover:bg-[#27272A]/50">
      <TableCell onClick={onNavigate}>
        <div>
          <span className="font-mono font-semibold">{holding.symbol}</span>
          <p className="text-xs text-muted-foreground">{holding.sector}</p>
        </div>
      </TableCell>
      <TableCell className="text-right font-mono">{holding.quantity}</TableCell>
      <TableCell className="text-right font-mono">
        {formatCurrency(holding.avg_buy_price)}
      </TableCell>
      <TableCell className="text-right font-mono">
        {formatCurrency(holding.current_price)}
      </TableCell>
      <TableCell className="text-right">
        <div className={getChangeColor(holding.profit_loss)}>
          <p className="font-mono">{formatCurrency(holding.profit_loss)}</p>
          <p className="text-xs">{formatPercent(holding.profit_loss_percent)}</p>
        </div>
      </TableCell>
      <TableCell>
        <Button
          variant="ghost"
          size="icon"
          className="text-muted-foreground hover:text-red-500"
          onClick={onRemove}
          data-testid={`remove-holding-${holding.symbol}`}
        >
          <Trash2 className="w-4 h-4" />
        </Button>
      </TableCell>
    </TableRow>
  );
}

function SectorItem({ sector }) {
  return (
    <div className="flex justify-between items-center text-sm">
      <span className="text-muted-foreground">{sector.sector}</span>
      <span className="font-mono">{sector.percent.toFixed(1)}%</span>
    </div>
  );
}

export default function Portfolio() {
  const navigate = useNavigate();
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [selectedStock, setSelectedStock] = useState(null);
  const [quantity, setQuantity] = useState("");
  const [avgPrice, setAvgPrice] = useState("");
  const [buyDate, setBuyDate] = useState("");

  useEffect(() => {
    fetchPortfolio();
  }, []);

  const fetchPortfolio = async () => {
    try {
      const response = await getPortfolio();
      setPortfolio(response.data);
    } catch (error) {
      console.error("Failed to fetch portfolio:", error);
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

  const selectStock = (stock) => {
    setSelectedStock(stock);
    setSearchQuery("");
    setSearchResults([]);
  };

  const handleAddHolding = async () => {
    if (!selectedStock || !quantity || !avgPrice) {
      toast.error("Please fill all required fields");
      return;
    }

    try {
      await addToPortfolio({
        symbol: selectedStock.symbol,
        name: selectedStock.name,
        quantity: parseInt(quantity),
        avg_buy_price: parseFloat(avgPrice),
        buy_date: buyDate || new Date().toISOString().split("T")[0],
      });
      toast.success(`${selectedStock.symbol} added to portfolio`);
      setAddDialogOpen(false);
      resetForm();
      fetchPortfolio();
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Failed to add holding"));
    }
  };

  const handleRemove = async (symbol) => {
    try {
      await removeFromPortfolio(symbol);
      toast.success(`${symbol} removed from portfolio`);
      fetchPortfolio();
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Failed to remove holding"));
    }
  };

  const resetForm = () => {
    setSelectedStock(null);
    setQuantity("");
    setAvgPrice("");
    setBuyDate("");
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  const holdings = portfolio?.holdings || [];
  const sectorAllocation = portfolio?.sector_allocation || [];
  const hasHoldings = holdings.length > 0;

  return (
    <div className="space-y-6" data-testid="portfolio">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight">Portfolio</h1>
          <p className="text-muted-foreground">Track your investments</p>
        </div>

        <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
          <DialogTrigger asChild>
            <Button data-testid="add-holding-btn">
              <Plus className="w-4 h-4 mr-2" />
              Add Holding
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-[#18181B] border-[#27272A]">
            <DialogHeader>
              <DialogTitle>Add Holding</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              {!selectedStock ? (
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    placeholder="Search stocks..."
                    className="pl-10 bg-background"
                    value={searchQuery}
                    onChange={(e) => handleSearch(e.target.value)}
                    data-testid="portfolio-search-input"
                  />
                  {searchResults.length > 0 && (
                    <div className="absolute top-full left-0 right-0 mt-1 bg-[#18181B] border border-[#27272A] rounded-sm shadow-lg z-10 max-h-48 overflow-auto">
                      {searchResults.map((stock) => (
                        <button
                          key={stock.symbol}
                          className="w-full px-3 py-2 text-left hover:bg-[#27272A] flex justify-between"
                          onClick={() => selectStock(stock)}
                        >
                          <span className="font-mono font-semibold">{stock.symbol}</span>
                          <span className="text-muted-foreground">{stock.name}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="bg-[#27272A] p-3 rounded-sm flex justify-between items-center">
                  <div>
                    <span className="font-mono font-semibold">{selectedStock.symbol}</span>
                    <span className="text-muted-foreground ml-2">{selectedStock.name}</span>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setSelectedStock(null)}>
                    Change
                  </Button>
                </div>
              )}

              {selectedStock && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label>Quantity*</Label>
                      <Input
                        type="number"
                        placeholder="100"
                        value={quantity}
                        onChange={(e) => setQuantity(e.target.value)}
                        className="bg-background"
                        data-testid="quantity-input"
                      />
                    </div>
                    <div>
                      <Label>Avg Buy Price (₹)*</Label>
                      <Input
                        type="number"
                        placeholder="1500.00"
                        value={avgPrice}
                        onChange={(e) => setAvgPrice(e.target.value)}
                        className="bg-background"
                        data-testid="avg-price-input"
                      />
                    </div>
                  </div>
                  <div>
                    <Label>Buy Date</Label>
                    <Input
                      type="date"
                      value={buyDate}
                      onChange={(e) => setBuyDate(e.target.value)}
                      className="bg-background"
                    />
                  </div>
                  <Button className="w-full" onClick={handleAddHolding} data-testid="confirm-add-btn">
                    Add to Portfolio
                  </Button>
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          title="Total Invested"
          value={formatCurrency(portfolio?.total_invested || 0)}
          icon={Wallet}
        />
        <MetricCard
          title="Current Value"
          value={formatCurrency(portfolio?.current_value || 0)}
          icon={Briefcase}
        />
        <MetricCard
          title="Total P&L"
          value={formatCurrency(portfolio?.total_profit_loss || 0)}
          changePercent={portfolio?.total_profit_loss_percent}
          icon={portfolio?.total_profit_loss >= 0 ? TrendingUp : TrendingDown}
        />
        <MetricCard
          title="XIRR"
          value={`${(portfolio?.xirr || 0).toFixed(2)}%`}
          icon={BarChart3}
        />
      </div>

      {!hasHoldings ? (
        <Card className="bg-[#18181B] border-[#27272A]">
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Briefcase className="w-12 h-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground mb-4">No holdings yet</p>
            <Button onClick={() => setAddDialogOpen(true)}>Add your first holding</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="bg-[#18181B] border-[#27272A] lg:col-span-2">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Holdings</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="border-[#27272A]">
                      <TableHead>Stock</TableHead>
                      <TableHead className="text-right">Qty</TableHead>
                      <TableHead className="text-right">Avg Price</TableHead>
                      <TableHead className="text-right">Current</TableHead>
                      <TableHead className="text-right">P&L</TableHead>
                      <TableHead></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {holdings.map((holding) => (
                      <HoldingRow
                        key={holding.symbol}
                        holding={holding}
                        onRemove={() => handleRemove(holding.symbol)}
                        onNavigate={() => navigate(`/analyzer?symbol=${holding.symbol}`)}
                      />
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-[#18181B] border-[#27272A]">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <PieChart className="w-4 h-4" />
                Sector Allocation
              </CardTitle>
            </CardHeader>
            <CardContent>
              <AllocationPieChart data={sectorAllocation} height={200} />
              <div className="mt-4 space-y-2">
                {sectorAllocation.map((sector) => (
                  <SectorItem key={sector.sector} sector={sector} />
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
