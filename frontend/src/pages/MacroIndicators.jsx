import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import {
    Globe,
    DollarSign,
    Droplets,
    Gem,
    TrendingUp,
    TrendingDown,
    RefreshCw,
    BarChart3,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { getTimeseriesMacroIndicators } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/utils";
import {
    LineChart, Line, AreaChart, Area, XAxis, YAxis, Tooltip,
    ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";

const ChartTooltip = ({ active, payload, label }) => {
    if (!active || !payload || !payload.length) return null;
    return (
        <div className="bg-[#18181B] border border-[#27272A] rounded-sm px-3 py-2 shadow-lg">
            <p className="text-xs text-muted-foreground mb-1">{label}</p>
            {payload.map((entry, i) => (
                <p key={i} className="text-sm font-mono" style={{ color: entry.color }}>
                    {entry.name}: {typeof entry.value === "number" ? entry.value.toFixed(2) : entry.value}
                </p>
            ))}
        </div>
    );
};

function MetricCard({ title, value, unit, icon: Icon, color, change }) {
    const isPositive = change > 0;
    return (
        <Card className="bg-[#18181B] border-[#27272A]">
            <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-sm text-muted-foreground">{title}</p>
                        <p className="text-2xl font-bold text-white font-mono">
                            {value !== null && value !== undefined ? `${value.toFixed(2)}` : "—"}
                            {unit && <span className="text-sm text-muted-foreground ml-1">{unit}</span>}
                        </p>
                        {change !== null && change !== undefined && (
                            <div className={`flex items-center gap-1 text-xs mt-1 ${isPositive ? "text-green-500" : "text-red-500"}`}>
                                {isPositive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                                {Math.abs(change).toFixed(2)}%
                            </div>
                        )}
                    </div>
                    <Icon className={`w-8 h-8 ${color}`} />
                </div>
            </CardContent>
        </Card>
    );
}

export default function MacroIndicators() {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        try {
            setLoading(true);
            const res = await getTimeseriesMacroIndicators({ limit: 90 });
            const rows = res.data?.data || [];
            // Sort oldest first for charting
            setData([...rows].reverse());
        } catch (err) {
            console.error("Error fetching macro indicators:", err);
            toast.error(getApiErrorMessage(err, "Failed to load macro indicators"));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    const latest = data.length > 0 ? data[data.length - 1] : null;
    const prev = data.length > 1 ? data[data.length - 2] : null;

    const pctChange = (curr, old) => {
        if (!curr || !old || old === 0) return null;
        return ((curr - old) / Math.abs(old)) * 100;
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                        <Globe className="w-8 h-8 text-blue-500" />
                        Macro Indicators
                    </h1>
                    <p className="text-muted-foreground mt-1">
                        Track key economic indicators, currencies, and commodity prices
                    </p>
                </div>
                <Button onClick={fetchData} variant="outline" disabled={loading}>
                    <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                    Refresh
                </Button>
            </div>

            {loading && data.length === 0 ? (
                <div className="text-center py-16 text-muted-foreground">Loading macro indicators...</div>
            ) : data.length === 0 ? (
                <Card className="bg-[#18181B] border-[#27272A]">
                    <CardContent className="py-16 text-center">
                        <Globe className="w-12 h-12 mx-auto text-muted-foreground/50 mb-4" />
                        <h3 className="text-lg font-medium text-white mb-2">No macro data available</h3>
                        <p className="text-muted-foreground mb-4">
                            Run the macro indicators job first: POST /api/jobs/run/macro-indicators
                        </p>
                    </CardContent>
                </Card>
            ) : (
                <>
                    {/* Summary Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        <MetricCard
                            title="USD/INR Rate"
                            value={latest?.usdinr_rate}
                            unit=""
                            icon={DollarSign}
                            color="text-green-500/50"
                            change={pctChange(latest?.usdinr_rate, prev?.usdinr_rate)}
                        />
                        <MetricCard
                            title="Brent Crude"
                            value={latest?.crude_brent_price}
                            unit="USD"
                            icon={Droplets}
                            color="text-orange-500/50"
                            change={pctChange(latest?.crude_brent_price, prev?.crude_brent_price)}
                        />
                        <MetricCard
                            title="Gold Price"
                            value={latest?.gold_price}
                            unit="USD"
                            icon={Gem}
                            color="text-yellow-500/50"
                            change={pctChange(latest?.gold_price, prev?.gold_price)}
                        />
                        <MetricCard
                            title="Copper Price"
                            value={latest?.copper_price}
                            unit="USD"
                            icon={BarChart3}
                            color="text-cyan-500/50"
                            change={pctChange(latest?.copper_price, prev?.copper_price)}
                        />
                    </div>

                    {/* USD/INR Chart */}
                    <Card className="bg-[#18181B] border-[#27272A]">
                        <CardHeader>
                            <CardTitle className="text-white flex items-center gap-2">
                                <DollarSign className="w-5 h-5 text-green-500" />
                                USD/INR Exchange Rate
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ResponsiveContainer width="100%" height={300}>
                                <AreaChart data={data}>
                                    <defs>
                                        <linearGradient id="colorUsd" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#22C55E" stopOpacity={0.3} />
                                            <stop offset="95%" stopColor="#22C55E" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                                    <XAxis dataKey="date" tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                    <YAxis
                                        tick={{ fill: "#A1A1AA", fontSize: 11 }}
                                        domain={["auto", "auto"]}
                                    />
                                    <Tooltip content={<ChartTooltip />} />
                                    <Area
                                        type="monotone"
                                        dataKey="usdinr_rate"
                                        name="USD/INR"
                                        stroke="#22C55E"
                                        fill="url(#colorUsd)"
                                        strokeWidth={2}
                                    />
                                </AreaChart>
                            </ResponsiveContainer>
                        </CardContent>
                    </Card>

                    {/* Commodity Prices Chart */}
                    <Card className="bg-[#18181B] border-[#27272A]">
                        <CardHeader>
                            <CardTitle className="text-white flex items-center gap-2">
                                <Droplets className="w-5 h-5 text-orange-500" />
                                Commodity Prices
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ResponsiveContainer width="100%" height={350}>
                                <LineChart data={data}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                                    <XAxis dataKey="date" tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                    <YAxis tick={{ fill: "#A1A1AA", fontSize: 11 }} />
                                    <Tooltip content={<ChartTooltip />} />
                                    <Legend
                                        wrapperStyle={{ color: "#A1A1AA", fontSize: 12 }}
                                    />
                                    <Line
                                        type="monotone"
                                        dataKey="crude_brent_price"
                                        name="Brent Crude (USD)"
                                        stroke="#F97316"
                                        strokeWidth={2}
                                        dot={false}
                                    />
                                    <Line
                                        type="monotone"
                                        dataKey="gold_price"
                                        name="Gold (USD)"
                                        stroke="#EAB308"
                                        strokeWidth={2}
                                        dot={false}
                                    />
                                    <Line
                                        type="monotone"
                                        dataKey="copper_price"
                                        name="Copper (USD)"
                                        stroke="#06B6D4"
                                        strokeWidth={2}
                                        dot={false}
                                    />
                                    {latest?.steel_price && (
                                        <Line
                                            type="monotone"
                                            dataKey="steel_price"
                                            name="Steel (USD)"
                                            stroke="#8B5CF6"
                                            strokeWidth={2}
                                            dot={false}
                                        />
                                    )}
                                </LineChart>
                            </ResponsiveContainer>
                        </CardContent>
                    </Card>

                    {/* RBI Rates & Inflation (if data exists) */}
                    {(latest?.rbi_repo_rate || latest?.cpi_inflation) && (
                        <Card className="bg-[#18181B] border-[#27272A]">
                            <CardHeader>
                                <CardTitle className="text-white">RBI Policy & Inflation</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                                    {latest?.rbi_repo_rate && (
                                        <div className="p-4 rounded-lg bg-[#09090B] border border-[#27272A]">
                                            <p className="text-sm text-muted-foreground">Repo Rate</p>
                                            <p className="text-xl font-bold text-white font-mono">{latest.rbi_repo_rate.toFixed(2)}%</p>
                                        </div>
                                    )}
                                    {latest?.cpi_inflation && (
                                        <div className="p-4 rounded-lg bg-[#09090B] border border-[#27272A]">
                                            <p className="text-sm text-muted-foreground">CPI Inflation</p>
                                            <p className="text-xl font-bold text-white font-mono">{latest.cpi_inflation.toFixed(2)}%</p>
                                        </div>
                                    )}
                                    {latest?.iip_growth && (
                                        <div className="p-4 rounded-lg bg-[#09090B] border border-[#27272A]">
                                            <p className="text-sm text-muted-foreground">IIP Growth</p>
                                            <p className="text-xl font-bold text-white font-mono">{latest.iip_growth.toFixed(2)}%</p>
                                        </div>
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Data Table */}
                    <Card className="bg-[#18181B] border-[#27272A]">
                        <CardHeader>
                            <CardTitle className="text-white">Historical Data</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b border-[#27272A]">
                                            <th className="text-left py-2 px-3 text-muted-foreground">Date</th>
                                            <th className="text-right py-2 px-3 text-muted-foreground">USD/INR</th>
                                            <th className="text-right py-2 px-3 text-muted-foreground">Brent Crude</th>
                                            <th className="text-right py-2 px-3 text-muted-foreground">Gold</th>
                                            <th className="text-right py-2 px-3 text-muted-foreground">Copper</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {[...data].reverse().slice(0, 30).map((row, i) => (
                                            <tr key={i} className="border-b border-[#27272A]/50 hover:bg-[#27272A]/30">
                                                <td className="py-2 px-3 text-white font-mono text-xs">{row.date}</td>
                                                <td className="py-2 px-3 text-right text-white font-mono">{row.usdinr_rate?.toFixed(2) ?? "—"}</td>
                                                <td className="py-2 px-3 text-right text-white font-mono">{row.crude_brent_price?.toFixed(2) ?? "—"}</td>
                                                <td className="py-2 px-3 text-right text-white font-mono">{row.gold_price?.toFixed(2) ?? "—"}</td>
                                                <td className="py-2 px-3 text-right text-white font-mono">{row.copper_price?.toFixed(2) ?? "—"}</td>
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
