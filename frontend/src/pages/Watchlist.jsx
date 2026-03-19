import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { getWatchlist, addToWatchlist, removeFromWatchlist, updateWatchlistItem, searchStocks } from "@/lib/api";
import { cn, formatCurrency, formatPercent, getVerdictColor, getScoreColor, getApiErrorMessage } from "@/lib/utils";
import { Star, Plus, Trash2, Edit, TrendingUp, TrendingDown, Search, Bell, Target } from "lucide-react";
import { toast } from "sonner";

export default function Watchlist() {
  const navigate = useNavigate();
  const [watchlist, setWatchlist] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);

  useEffect(() => {
    fetchWatchlist();
  }, []);

  const fetchWatchlist = async () => {
    try {
      const response = await getWatchlist();
      setWatchlist(response.data);
    } catch (error) {
      console.error("Failed to fetch watchlist:", error);
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

  const handleAddStock = async (stock) => {
    try {
      await addToWatchlist({
        symbol: stock.symbol,
        name: stock.name,
      });
      toast.success(`${stock.symbol} added to watchlist`);
      setAddDialogOpen(false);
      setSearchQuery("");
      setSearchResults([]);
      fetchWatchlist();
    } catch (error) {
      if (error.response?.status === 400) {
        toast.info("Already in watchlist");
      } else {
        toast.error(getApiErrorMessage(error, "Failed to add to watchlist"));
      }
    }
  };

  const handleRemove = async (symbol) => {
    try {
      await removeFromWatchlist(symbol);
      toast.success(`${symbol} removed from watchlist`);
      fetchWatchlist();
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Failed to remove from watchlist"));
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48" />
        <div className="grid gap-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="watchlist">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight">Watchlist</h1>
          <p className="text-muted-foreground">Track your favorite stocks</p>
        </div>

        <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
          <DialogTrigger asChild>
            <Button data-testid="add-to-watchlist-btn">
              <Plus className="w-4 h-4 mr-2" />
              Add Stock
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-[#18181B] border-[#27272A]">
            <DialogHeader>
              <DialogTitle>Add to Watchlist</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search stocks..."
                  className="pl-10 bg-background"
                  value={searchQuery}
                  onChange={(e) => handleSearch(e.target.value)}
                  data-testid="watchlist-search-input"
                />
              </div>
              {searchResults.length > 0 && (
                <div className="max-h-64 overflow-auto space-y-1">
                  {searchResults.map((stock) => (
                    <button
                      key={stock.symbol}
                      className="w-full px-3 py-2 text-left hover:bg-[#27272A] rounded-sm flex justify-between items-center"
                      onClick={() => handleAddStock(stock)}
                      data-testid={`add-stock-${stock.symbol}`}
                    >
                      <div>
                        <span className="font-mono font-semibold">{stock.symbol}</span>
                        <span className="text-muted-foreground ml-2">{stock.name}</span>
                      </div>
                      <Plus className="w-4 h-4 text-muted-foreground" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {watchlist.length === 0 ? (
        <Card className="bg-[#18181B] border-[#27272A]">
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Star className="w-12 h-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground mb-4">Your watchlist is empty</p>
            <Button onClick={() => setAddDialogOpen(true)}>Add your first stock</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {watchlist.map((item) => (
            <Card
              key={item.symbol}
              className="bg-[#18181B] border-[#27272A] hover:border-[#3B82F6]/50 transition-colors"
              data-testid={`watchlist-item-${item.symbol}`}
            >
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div
                    className="flex-1 cursor-pointer"
                    onClick={() => navigate(`/analyzer?symbol=${item.symbol}`)}
                  >
                    <div className="flex items-center gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-lg">{item.symbol}</span>
                          {item.verdict && (
                            <Badge className={cn("text-xs", getVerdictColor(item.verdict))}>
                              {item.verdict}
                            </Badge>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground">{item.name}</p>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-6">
                    {item.current_price && (
                      <div className="text-right">
                        <p className="font-mono text-lg font-semibold">
                          {formatCurrency(item.current_price)}
                        </p>
                        <p
                          className={cn(
                            "font-mono text-sm flex items-center justify-end gap-1",
                            item.price_change_percent >= 0 ? "text-green-500" : "text-red-500"
                          )}
                        >
                          {item.price_change_percent >= 0 ? (
                            <TrendingUp className="w-3 h-3" />
                          ) : (
                            <TrendingDown className="w-3 h-3" />
                          )}
                          {formatPercent(item.price_change_percent)}
                        </p>
                      </div>
                    )}

                    {item.score && (
                      <div className="text-right">
                        <p className="text-xs text-muted-foreground">Score</p>
                        <p className={cn("font-mono text-lg font-bold", getScoreColor(item.score))}>
                          {Math.round(item.score)}
                        </p>
                      </div>
                    )}

                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-muted-foreground hover:text-red-500"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRemove(item.symbol);
                        }}
                        data-testid={`remove-${item.symbol}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </div>

                {(item.target_price || item.stop_loss || item.notes) && (
                  <div className="mt-3 pt-3 border-t border-[#27272A] flex flex-wrap gap-4 text-sm">
                    {item.target_price && (
                      <div className="flex items-center gap-1 text-green-500">
                        <Target className="w-3 h-3" />
                        Target: {formatCurrency(item.target_price)}
                      </div>
                    )}
                    {item.stop_loss && (
                      <div className="flex items-center gap-1 text-red-500">
                        <Bell className="w-3 h-3" />
                        Stop Loss: {formatCurrency(item.stop_loss)}
                      </div>
                    )}
                    {item.notes && (
                      <span className="text-muted-foreground">{item.notes}</span>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
