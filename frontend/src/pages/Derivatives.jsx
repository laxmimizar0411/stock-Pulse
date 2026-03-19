import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import {
    BarChart3,
    TrendingUp,
    TrendingDown,
    RefreshCw,
    Search,
    Activity,
    PieChart as PieChartIcon,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { getTimeseriesDerivatives } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/utils";
import {
    LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip,
    ResponsiveContainer, CartesianGrid, Legend, ComposedChart, Area,
} from "recharts";

const ChartTooltip = ({ active, payload, label }) => {
    if (!active || !payload || !payload.length) return null;
    return (
        <div className="bg-[#18181B] border border-[#27272A] rounded-sm px-3 py-2 shadow-lg">
            <p className="text-xs text-muted-foreground mb-1">{label}</p>
            {payload.map((entry, i) => (
                <p key={i} className="text-sm font-mono" style={{ color: entry.color }}>
                    {entry.name}: {typeof entry.value === "number" ? entry.value.toLocaleString() : entry.value}
                </p>
            ))}
        </div>
    );
};

const POPULAR_SYMBOLS = ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK", "INFY", "SBIN"];

export default function Derivatives() {
    const [symbol, setSymbol] = useState("NIFTY");
    const [searchInput, setSearchInput] = useState("NIFTY");
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchData = async (sym) => {
        try {
            setLoading(true);
            const res = await getTimeseriesDerivatives(sym, { limit: 90 });
            const rows = res.data?.data || [];
            // Sort oldest first for charting
            setData([...rows].reverse());
        } catch (err) {
            console.error("Error fetching derivatives:", err);
            toast.error(getApiErrorMessage(err, `Failed to load derivatives data for ${sym}`));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(symbol); }, [symbol]);

    const handleSearch = (e) => {
        e.preventDefault();
        if (searchInput.trim()) {
            setSymbol(searchInput.trim().toUpperCase());
        }
    };

    const latest = data.length > 0 ? data[data.length - 1] : null;

    const formatOI = (val) => {
        if (!val) return "—";
        if (val >= 10000000) return (val / 10000000).toFixed(2) + " Cr";
        if (val >= 100000) return (val / 100000).toFixed(2) + " L";
        return val.toLocaleString();
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-4">
                <div>
                    <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                        <BarChart3 className="w-8 h-8 text-purple-500" />
                        Derivatives Analytics
                    </h1>
                    <p className="text-muted-foreground mt-1">
                        Futures OI, Put-Call Ratio, Implied Volatility, and options flow
                    </p>
                </div>
                <Button onClick={() => fetchData(symbol)} variant="outline" disabled={loading}>
                    <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                    Refresh
                </Button>
            </div>

            {/* Symbol Selector */}
            <Card className="bg-[#18181B] border-[#27272A]">
                <CardContent className="pt-6">
                    <form onSubmit={handleSearch} className="flex items-center gap-3 mb-4">
                        <div className="relative flex-1 max-w-xs">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                            <Input
                                placeholder="Enter symbol..."
                                value={searchInput}
                                onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
                                className="pl-9 bg-[#09090B]"
                            />
                        </div>
                        <Button type="submit">Load</Button>
                    </form>
                    <div className="flex flex-wrap gap-2">
                        {POPULAR_SYMBOLS.map((sym) => (
                            <Button
                                key={sym}
                                variant={symbol === sym ? "default" : "outline"}
                                size="sm"
                                onClick={() => { setSearchInput(sym); setSymbol(sym); }}
                                className={symbol === sym ? "bg-purple-600 hover:bg-purple-700" : ""}
                            >
                                {sym}
                            </Button>
                        ))}
                    </div>
                </CardContent>
            </Card>

            {loading && data.length === 0 ? (
                <div className="text-center py-16 text-muted-foreground">Loading derivatives data for {symbol}...</div>
            ) : data.length === 0 ? (
                <Card className="bg-[#18181B] border-[#27272A]">
                    <CardContent className="py-16 text-center">
                        <BarChart3 className="w-12 h-12 mx-auto text-muted-foreground/50 mb-4" />
                        <h3 className="text-lg font-medium text-white mb-2">No derivatives data for {symbol}</h3>
                        <p className="text-muted-foreground">
                            Run the derivatives job first: POST /api/jobs/run/derivatives
                        </p>
                    </CardContent>
                </Card>
            ) : (
                <>
                    {/* Summary Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        <Card className="bg-[#18181B] border-[#27272A]">
                            <CardContent className="pt-6">
                                <p className="text-sm text-muted-foreground">Futures OI</p>
                                <p className="text-2xl font-bold text-white font-mono">{formatOI(latest?.futures_oi)}</p>
                                {latest?.futures_oi_change_pct != null && (
                                    <div className={`flex items-center gap-1 text-xs mt-1 ${latest.futures_oi_change_pct >= 0 ? "text-green-500" : "text-red-500"}`}>
                                        {latest.futures_oi_change_pct >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                                        {Math.abs(latest.futures_oi_change_pct).toFixed(2)}%
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                        <Card className="bg-[#18181B] border-[#27272A]">
                            <CardContent className="pt-6">
                                <p className="text-sm text-muted-foreground">Put-Call Ratio (OI)</p>
                                <p className="text-2xl font-bold text-white font-mono">
                                    {latest?.put_call_ratio_oi?.toFixed(3) ?? "—"}
                                </p>
                                <Badge className={`mt-1 ${(latest?.put_call_ratio_oi ?? 0) > 1 ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"}`}>
                                    {(latest?.put_call_ratio_oi ?? 0) > 1 ? "Bullish" : "Bearish"}
                                </Badge>
                            </CardContent>
                        </Card>
                        <Card className="bg-[#18181B] border-[#27272A]">
                            <CardContent className="pt-6">
                                <p className="text-sm text-muted-foreground">IV (ATM %)</p>
                                <p className="text-2xl font-bold text-white font-mono">
                                    {latest?.iv_atm_pct?.toFixed(2) ?? "—"}%
                                </p>
                                {latest?.iv_percentile_1y != null && (
                                    <p className="text-xs text-muted-foreground mt-1">
                                        1Y Percentile: {latest.iv_percentile_1y.toFixed(1)}%
                                    </p>
                                )}
                            </CardContent>
                        </Card>
                        <Card className="bg-[#18181B] border-[#27272A]">
                            <CardContent className="pt-6">
                                <p className="text-sm text-muted-foreground">Futures Near Price</p>
                                <p className="text-2xl font-bold text-white font-mono">
                                    {latest?.futures_price_near ? `₹${latest.futures_price_near.toLocaleString()}` : "—"}
                                </p>
                                {latest?.futures_basis_pct != null && (
                                    <p className="text-xs text-muted-foreground mt-1">
                                        Basis: {latest.futures_basis_pct.toFixed(2)}%
                                    </p>
                                )}
                            </CardContent>
                        </Card>
                    </div>

                    {/* OI Trend Chart */}
                    <Card className="bg-[#18181B] border-[#27272A]">
                        <CardHeader>
                            <CardTitle className="text-white">Futures Open Interest Trend</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ResponsiveContainer width="100%" height={300}>
                                <ComposedChart data={data}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                                    <XAxis dataKey="date" tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                    <YAxis yAxisId="oi" tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                    <YAxis yAxisId="pct" orientation="right" tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                    <Tooltip content={<ChartTooltip />} />
                                    <Legend wrapperStyle={{ color: "#A1A1AA", fontSize: 12 }} />
                                    <Bar yAxisId="oi" dataKey="futures_oi" name="Futures OI" fill="#8B5CF6" opacity={0.6} />
                                    <Line yAxisId="pct" type="monotone" dataKey="futures_oi_change_pct" name="OI Change %" stroke="#EAB308" strokeWidth={2} dot={false} />
                                </ComposedChart>
                            </ResponsiveContainer>
                        </CardContent>
                    </Card>

                    {/* PCR Chart */}
                    <Card className="bg-[#18181B] border-[#27272A]">
                        <CardHeader>
                            <CardTitle className="text-white">Put-Call Ratio (OI & Volume)</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ResponsiveContainer width="100%" height={300}>
                                <LineChart data={data}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                                    <XAxis dataKey="date" tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                    <YAxis tick={{ fill: "#A1A1AA", fontSize: 11 }} domain={[0, "auto"]} />
                                    <Tooltip content={<ChartTooltip />} />
                                    <Legend wrapperStyle={{ color: "#A1A1AA", fontSize: 12 }} />
                                    <Line type="monotone" dataKey="put_call_ratio_oi" name="PCR (OI)" stroke="#3B82F6" strokeWidth={2} dot={false} />
                                    <Line type="monotone" dataKey="put_call_ratio_volume" name="PCR (Volume)" stroke="#22C55E" strokeWidth={2} dot={false} />
                                    {/* Reference line at 1.0 */}
                                </LineChart>
                            </ResponsiveContainer>
                            <p className="text-xs text-muted-foreground mt-2 text-center">
                                PCR above 1.0 is generally considered bullish (more puts being written)
                            </p>
                        </CardContent>
                    </Card>

                    {/* IV Chart */}
                    {data.some(d => d.iv_atm_pct != null) && (
                        <Card className="bg-[#18181B] border-[#27272A]">
                            <CardHeader>
                                <CardTitle className="text-white">Implied Volatility</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ResponsiveContainer width="100%" height={250}>
                                    <AreaChart data={data}>
                                        <defs>
                                            <linearGradient id="colorIv" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor="#F97316" stopOpacity={0.3} />
                                                <stop offset="95%" stopColor="#F97316" stopOpacity={0} />
                                            </linearGradient>
                                        </defs>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                                        <XAxis dataKey="date" tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                        <YAxis tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                        <Tooltip content={<ChartTooltip />} />
                                        <Area type="monotone" dataKey="iv_atm_pct" name="IV ATM %" stroke="#F97316" fill="url(#colorIv)" strokeWidth={2} />
                                    </AreaChart>
                                </ResponsiveContainer>
                            </CardContent>
                        </Card>
                    )}

                    {/* Data Table */}
                    <Card className="bg-[#18181B] border-[#27272A]">
                        <CardHeader>
                            <CardTitle className="text-white">Recent Data — {symbol}</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b border-[#27272A]">
                                            <th className="text-left py-2 px-2 text-muted-foreground">Date</th>
                                            <th className="text-right py-2 px-2 text-muted-foreground">Futures OI</th>
                                            <th className="text-right py-2 px-2 text-muted-foreground">OI Chg %</th>
                                            <th className="text-right py-2 px-2 text-muted-foreground">Near Price</th>
                                            <th className="text-right py-2 px-2 text-muted-foreground">PCR (OI)</th>
                                            <th className="text-right py-2 px-2 text-muted-foreground">IV ATM</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {[...data].reverse().slice(0, 20).map((row, i) => (
                                            <tr key={i} className="border-b border-[#27272A]/50 hover:bg-[#27272A]/30">
                                                <td className="py-2 px-2 text-white font-mono text-xs">{row.date}</td>
                                                <td className="py-2 px-2 text-right text-white font-mono">{formatOI(row.futures_oi)}</td>
                                                <td className={`py-2 px-2 text-right font-mono ${(row.futures_oi_change_pct ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                                                    {row.futures_oi_change_pct?.toFixed(2) ?? "—"}%
                                                </td>
                                                <td className="py-2 px-2 text-right text-white font-mono">{row.futures_price_near?.toLocaleString() ?? "—"}</td>
                                                <td className="py-2 px-2 text-right text-white font-mono">{row.put_call_ratio_oi?.toFixed(3) ?? "—"}</td>
                                                <td className="py-2 px-2 text-right text-white font-mono">{row.iv_atm_pct?.toFixed(2) ?? "—"}%</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </CardContent>
                    </Card>
                </>
            )}
        </div>
    );
}
