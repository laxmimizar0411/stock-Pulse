import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import {
    Activity,
    TrendingUp,
    TrendingDown,
    RefreshCw,
    Search,
    Gauge,
    BarChart3,
    Zap,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { getTimeseriesIntraday } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/utils";
import {
    LineChart, Line, AreaChart, Area, XAxis, YAxis, Tooltip,
    ResponsiveContainer, CartesianGrid, Legend, ComposedChart, Bar,
} from "recharts";

const ChartTooltip = ({ active, payload, label }) => {
    if (!active || !payload || !payload.length) return null;
    return (
        <div className="bg-[#18181B] border border-[#27272A] rounded-sm px-3 py-2 shadow-lg">
            <p className="text-xs text-muted-foreground mb-1">{label}</p>
            {payload.map((entry, i) => (
                <p key={i} className="text-sm font-mono" style={{ color: entry.color }}>
                    {entry.name}: {typeof entry.value === "number" ? entry.value.toFixed(2) : entry.value ?? "—"}
                </p>
            ))}
        </div>
    );
};

const POPULAR_SYMBOLS = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "SBIN", "ICICIBANK", "ITC"];

function getRsiColor(val) {
    if (val == null) return "text-muted-foreground";
    if (val >= 70) return "text-red-400";
    if (val <= 30) return "text-green-400";
    return "text-yellow-400";
}

function getRsiLabel(val) {
    if (val == null) return "—";
    if (val >= 70) return "Overbought";
    if (val <= 30) return "Oversold";
    return "Neutral";
}

function getAdLabel(val) {
    if (val == null) return "—";
    if (val > 1.5) return "Strong Bullish";
    if (val > 1) return "Bullish";
    if (val > 0.7) return "Bearish";
    return "Strong Bearish";
}

export default function IntradayMetrics() {
    const [symbol, setSymbol] = useState("RELIANCE");
    const [searchInput, setSearchInput] = useState("RELIANCE");
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchData = async (sym) => {
        try {
            setLoading(true);
            const res = await getTimeseriesIntraday(sym, { limit: 60 });
            const rows = res.data?.data || [];
            // Add display date from timestamp and sort oldest first
            const processed = rows.map((r) => ({
                ...r,
                display_date: r.timestamp ? r.timestamp.split("T")[0] : "",
            }));
            setData([...processed].reverse());
        } catch (err) {
            console.error("Error fetching intraday metrics:", err);
            toast.error(getApiErrorMessage(err, `Failed to load intraday data for ${sym}`));
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

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-4">
                <div>
                    <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                        <Activity className="w-8 h-8 text-cyan-500" />
                        Intraday Metrics
                    </h1>
                    <p className="text-muted-foreground mt-1">
                        RSI, MACD, VWAP, Advance/Decline ratio, and India VIX snapshots
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
                                className={symbol === sym ? "bg-cyan-600 hover:bg-cyan-700" : ""}
                            >
                                {sym}
                            </Button>
                        ))}
                    </div>
                </CardContent>
            </Card>

            {loading && data.length === 0 ? (
                <div className="text-center py-16 text-muted-foreground">Loading intraday metrics for {symbol}...</div>
            ) : data.length === 0 ? (
                <Card className="bg-[#18181B] border-[#27272A]">
                    <CardContent className="py-16 text-center">
                        <Activity className="w-12 h-12 mx-auto text-muted-foreground/50 mb-4" />
                        <h3 className="text-lg font-medium text-white mb-2">No intraday data for {symbol}</h3>
                        <p className="text-muted-foreground">
                            Run the intraday metrics job first: POST /api/jobs/run/intraday-metrics
                        </p>
                    </CardContent>
                </Card>
            ) : (
                <>
                    {/* Summary Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        <Card className="bg-[#18181B] border-[#27272A]">
                            <CardContent className="pt-6">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-sm text-muted-foreground">RSI (14)</p>
                                        <p className={`text-2xl font-bold font-mono ${getRsiColor(latest?.rsi_hourly)}`}>
                                            {latest?.rsi_hourly?.toFixed(1) ?? "—"}
                                        </p>
                                        <Badge className={`mt-1 ${latest?.rsi_hourly >= 70 ? "bg-red-500/20 text-red-400" : latest?.rsi_hourly <= 30 ? "bg-green-500/20 text-green-400" : "bg-yellow-500/20 text-yellow-400"}`}>
                                            {getRsiLabel(latest?.rsi_hourly)}
                                        </Badge>
                                    </div>
                                    <Gauge className="w-8 h-8 text-cyan-500/50" />
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="bg-[#18181B] border-[#27272A]">
                            <CardContent className="pt-6">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-sm text-muted-foreground">MACD</p>
                                        <p className={`text-2xl font-bold font-mono ${(latest?.macd_crossover_hourly ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                                            {latest?.macd_crossover_hourly?.toFixed(2) ?? "—"}
                                        </p>
                                        <Badge className={`mt-1 ${(latest?.macd_crossover_hourly ?? 0) >= 0 ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"}`}>
                                            {(latest?.macd_crossover_hourly ?? 0) >= 0 ? "Bullish" : "Bearish"}
                                        </Badge>
                                    </div>
                                    <Zap className="w-8 h-8 text-yellow-500/50" />
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="bg-[#18181B] border-[#27272A]">
                            <CardContent className="pt-6">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-sm text-muted-foreground">VWAP</p>
                                        <p className="text-2xl font-bold text-white font-mono">
                                            {latest?.vwap_intraday ? `₹${latest.vwap_intraday.toLocaleString()}` : "—"}
                                        </p>
                                    </div>
                                    <BarChart3 className="w-8 h-8 text-blue-500/50" />
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="bg-[#18181B] border-[#27272A]">
                            <CardContent className="pt-6">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-sm text-muted-foreground">Advance/Decline</p>
                                        <p className={`text-2xl font-bold font-mono ${(latest?.advance_decline_ratio ?? 0) >= 1 ? "text-green-400" : "text-red-400"}`}>
                                            {latest?.advance_decline_ratio?.toFixed(2) ?? "—"}
                                        </p>
                                        <p className="text-xs text-muted-foreground mt-1">
                                            {getAdLabel(latest?.advance_decline_ratio)}
                                        </p>
                                    </div>
                                    <TrendingUp className="w-8 h-8 text-green-500/50" />
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    {/* India VIX Card (if available) */}
                    {latest?.india_vix && (
                        <Card className="bg-[#18181B] border-[#27272A]">
                            <CardContent className="pt-6">
                                <div className="flex items-center gap-4">
                                    <Activity className="w-6 h-6 text-orange-500" />
                                    <div>
                                        <p className="text-sm text-muted-foreground">India VIX (Fear Index)</p>
                                        <p className="text-3xl font-bold text-white font-mono">{latest.india_vix.toFixed(2)}</p>
                                    </div>
                                    <Badge className={`ml-4 ${latest.india_vix > 20 ? "bg-red-500/20 text-red-400" : latest.india_vix > 15 ? "bg-yellow-500/20 text-yellow-400" : "bg-green-500/20 text-green-400"}`}>
                                        {latest.india_vix > 20 ? "High Fear" : latest.india_vix > 15 ? "Moderate" : "Low Fear"}
                                    </Badge>
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* RSI Chart */}
                    <Card className="bg-[#18181B] border-[#27272A]">
                        <CardHeader>
                            <CardTitle className="text-white">RSI (14) Trend</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ResponsiveContainer width="100%" height={280}>
                                <AreaChart data={data}>
                                    <defs>
                                        <linearGradient id="colorRsi" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#06B6D4" stopOpacity={0.3} />
                                            <stop offset="95%" stopColor="#06B6D4" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                                    <XAxis dataKey="display_date" tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                    <YAxis tick={{ fill: "#A1A1AA", fontSize: 11 }} domain={[0, 100]} />
                                    <Tooltip content={<ChartTooltip />} />
                                    {/* Overbought / oversold reference lines */}
                                    <Area type="monotone" dataKey="rsi_hourly" name="RSI" stroke="#06B6D4" fill="url(#colorRsi)" strokeWidth={2} />
                                </AreaChart>
                            </ResponsiveContainer>
                            <div className="flex justify-center gap-6 mt-2 text-xs text-muted-foreground">
                                <span className="text-red-400">Overbought (&gt;70)</span>
                                <span className="text-yellow-400">Neutral (30-70)</span>
                                <span className="text-green-400">Oversold (&lt;30)</span>
                            </div>
                        </CardContent>
                    </Card>

                    {/* MACD Chart */}
                    <Card className="bg-[#18181B] border-[#27272A]">
                        <CardHeader>
                            <CardTitle className="text-white">MACD Trend</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ResponsiveContainer width="100%" height={280}>
                                <ComposedChart data={data}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                                    <XAxis dataKey="display_date" tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                    <YAxis tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                    <Tooltip content={<ChartTooltip />} />
                                    <Bar
                                        dataKey="macd_crossover_hourly"
                                        name="MACD"
                                        fill="#3B82F6"
                                        opacity={0.6}
                                    />
                                </ComposedChart>
                            </ResponsiveContainer>
                        </CardContent>
                    </Card>

                    {/* VWAP + A/D Ratio Charts */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <Card className="bg-[#18181B] border-[#27272A]">
                            <CardHeader>
                                <CardTitle className="text-white">VWAP Trend</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ResponsiveContainer width="100%" height={250}>
                                    <LineChart data={data}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                                        <XAxis dataKey="display_date" tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                        <YAxis tick={{ fill: "#A1A1AA", fontSize: 11 }} domain={["auto", "auto"]} />
                                        <Tooltip content={<ChartTooltip />} />
                                        <Line type="monotone" dataKey="vwap_intraday" name="VWAP" stroke="#3B82F6" strokeWidth={2} dot={false} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </CardContent>
                        </Card>

                        <Card className="bg-[#18181B] border-[#27272A]">
                            <CardHeader>
                                <CardTitle className="text-white">Advance/Decline Ratio</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ResponsiveContainer width="100%" height={250}>
                                    <AreaChart data={data}>
                                        <defs>
                                            <linearGradient id="colorAd" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor="#22C55E" stopOpacity={0.3} />
                                                <stop offset="95%" stopColor="#22C55E" stopOpacity={0} />
                                            </linearGradient>
                                        </defs>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                                        <XAxis dataKey="display_date" tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                        <YAxis tick={{ fill: "#A1A1AA", fontSize: 11 }} domain={[0, "auto"]} />
                                        <Tooltip content={<ChartTooltip />} />
                                        <Area type="monotone" dataKey="advance_decline_ratio" name="A/D Ratio" stroke="#22C55E" fill="url(#colorAd)" strokeWidth={2} />
                                    </AreaChart>
                                </ResponsiveContainer>
                                <p className="text-xs text-muted-foreground mt-2 text-center">
                                    Above 1.0 = more advances than declines (bullish breadth)
                                </p>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Data Table */}
                    <Card className="bg-[#18181B] border-[#27272A]">
                        <CardHeader>
                            <CardTitle className="text-white">Recent Snapshots — {symbol}</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b border-[#27272A]">
                                            <th className="text-left py-2 px-2 text-muted-foreground">Date</th>
                                            <th className="text-right py-2 px-2 text-muted-foreground">RSI</th>
                                            <th className="text-right py-2 px-2 text-muted-foreground">MACD</th>
                                            <th className="text-right py-2 px-2 text-muted-foreground">VWAP</th>
                                            <th className="text-right py-2 px-2 text-muted-foreground">A/D Ratio</th>
                                            <th className="text-right py-2 px-2 text-muted-foreground">VIX</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {[...data].reverse().slice(0, 20).map((row, i) => (
                                            <tr key={i} className="border-b border-[#27272A]/50 hover:bg-[#27272A]/30">
                                                <td className="py-2 px-2 text-white font-mono text-xs">{row.display_date}</td>
                                                <td className={`py-2 px-2 text-right font-mono ${getRsiColor(row.rsi_hourly)}`}>
                                                    {row.rsi_hourly?.toFixed(1) ?? "—"}
                                                </td>
                                                <td className={`py-2 px-2 text-right font-mono ${(row.macd_crossover_hourly ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                                                    {row.macd_crossover_hourly?.toFixed(2) ?? "—"}
                                                </td>
                                                <td className="py-2 px-2 text-right text-white font-mono">
                                                    {row.vwap_intraday ? `₹${row.vwap_intraday.toLocaleString()}` : "—"}
                                                </td>
                                                <td className={`py-2 px-2 text-right font-mono ${(row.advance_decline_ratio ?? 0) >= 1 ? "text-green-400" : "text-red-400"}`}>
                                                    {row.advance_decline_ratio?.toFixed(2) ?? "—"}
                                                </td>
                                                <td className="py-2 px-2 text-right text-white font-mono">
                                                    {row.india_vix?.toFixed(2) ?? "—"}
                                                </td>
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
