import React, { useState, useEffect, useCallback } from "react";
import {
  getPostgresStatus,
  togglePostgres,
  getPostgresResources,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  HardDrive,
  Cpu,
  MemoryStick,
  Database,
  Activity,
  RefreshCw,
  Power,
  PowerOff,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Loader2,
  Server,
  Gauge,
  Users,
  BarChart3,
} from "lucide-react";
import { toast } from "sonner";

export default function PostgresControl() {
  const [status, setStatus] = useState(null);
  const [resources, setResources] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await getPostgresStatus();
      setStatus(res.data);
    } catch (err) {
      console.error("Failed to fetch PostgreSQL status:", err);
    }
  }, []);

  const fetchResources = useCallback(async () => {
    try {
      const res = await getPostgresResources();
      setResources(res.data);
    } catch (err) {
      console.error("Failed to fetch resources:", err);
    }
  }, []);

  const fetchAll = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([fetchStatus(), fetchResources()]);
    setRefreshing(false);
    setLoading(false);
  }, [fetchStatus, fetchResources]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchAll, 10000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchAll]);

  const handleToggle = async () => {
    const action = status?.running ? "stop" : "start";
    const confirmMsg = action === "stop"
      ? "Are you sure you want to stop PostgreSQL? Active connections will be terminated."
      : "Start PostgreSQL database?";

    if (action === "stop" && !window.confirm(confirmMsg)) return;

    setToggling(true);
    try {
      const res = await togglePostgres(action);
      const data = res.data;
      if (data.success) {
        toast.success(data.message);
      } else {
        toast.error(data.message || `Failed to ${action} PostgreSQL`);
      }
      // Wait a moment for the process to change state
      setTimeout(fetchAll, 2000);
    } catch (err) {
      toast.error(`Failed to ${action} PostgreSQL: ${err.message}`);
    } finally {
      setToggling(false);
    }
  };

  const formatUptime = (seconds) => {
    if (!seconds) return "N/A";
    const days = Math.floor(seconds / 86400);
    const hrs = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (days > 0) return `${days}d ${hrs}h ${mins}m`;
    if (hrs > 0) return `${hrs}h ${mins}m`;
    return `${mins}m`;
  };

  const formatBytes = (bytes) => {
    if (!bytes) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    let val = bytes;
    while (val >= 1024 && i < units.length - 1) {
      val /= 1024;
      i++;
    }
    return `${val.toFixed(1)} ${units[i]}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="w-8 h-8 animate-spin text-[#3B82F6]" />
        <span className="ml-3 text-[#A1A1AA]">Loading PostgreSQL status...</span>
      </div>
    );
  }

  const isRunning = status?.running || false;
  const isReachable = status?.reachable || false;
  const cpu = resources?.cpu || {};
  const memory = resources?.memory || {};
  const storage = resources?.storage || {};
  const connections = resources?.connections || {};
  const pool = resources?.pool || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <HardDrive className="w-7 h-7 text-[#3B82F6]" />
            PostgreSQL Control Panel
          </h1>
          <p className="text-sm text-[#A1A1AA] mt-1">
            Monitor and control your local PostgreSQL database instance
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-[#A1A1AA]">
            Auto-refresh
            <Switch
              checked={autoRefresh}
              onCheckedChange={setAutoRefresh}
            />
          </label>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchAll}
            disabled={refreshing}
          >
            <RefreshCw className={`w-4 h-4 mr-1 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Status & Toggle Card */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Power Control */}
        <Card className="bg-[#18181B] border-[#27272A] lg:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-white text-lg flex items-center gap-2">
              <Power className="w-5 h-5" />
              Database Control
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-col items-center gap-4 py-4">
              {/* Status Indicator */}
              <div className={`w-24 h-24 rounded-full flex items-center justify-center border-4 ${
                isRunning && isReachable
                  ? "border-green-500/30 bg-green-500/10"
                  : isRunning
                    ? "border-yellow-500/30 bg-yellow-500/10"
                    : "border-red-500/30 bg-red-500/10"
              }`}>
                {isRunning && isReachable ? (
                  <CheckCircle2 className="w-12 h-12 text-green-500" />
                ) : isRunning ? (
                  <AlertTriangle className="w-12 h-12 text-yellow-500" />
                ) : (
                  <XCircle className="w-12 h-12 text-red-500" />
                )}
              </div>

              <div className="text-center">
                <Badge
                  variant={isRunning ? "default" : "destructive"}
                  className={isRunning && isReachable
                    ? "bg-green-500/20 text-green-400 border-green-500/30"
                    : isRunning
                      ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
                      : ""
                  }
                >
                  {isRunning && isReachable ? "Running" : isRunning ? "Running (Unreachable)" : "Stopped"}
                </Badge>
                {status?.uptime_seconds && (
                  <p className="text-xs text-[#A1A1AA] mt-2">
                    Uptime: {formatUptime(status.uptime_seconds)}
                  </p>
                )}
              </div>

              {/* Toggle Button */}
              <Button
                onClick={handleToggle}
                disabled={toggling}
                variant={isRunning ? "destructive" : "default"}
                className={`w-full max-w-[200px] ${
                  !isRunning ? "bg-green-600 hover:bg-green-700" : ""
                }`}
              >
                {toggling ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : isRunning ? (
                  <PowerOff className="w-4 h-4 mr-2" />
                ) : (
                  <Power className="w-4 h-4 mr-2" />
                )}
                {toggling
                  ? (isRunning ? "Stopping..." : "Starting...")
                  : (isRunning ? "Stop Database" : "Start Database")
                }
              </Button>
            </div>

            {/* Version */}
            {status?.version && (
              <div className="text-xs text-[#A1A1AA] bg-[#09090B] rounded p-3 font-mono break-all">
                {status.version.substring(0, 80)}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Quick Stats */}
        <Card className="bg-[#18181B] border-[#27272A] lg:col-span-2">
          <CardHeader className="pb-3">
            <CardTitle className="text-white text-lg flex items-center gap-2">
              <Gauge className="w-5 h-5" />
              Resource Overview
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {/* CPU */}
              <ResourceCard
                icon={<Cpu className="w-5 h-5 text-blue-400" />}
                label="CPU Usage"
                value={cpu.available ? `${cpu.percentage}%` : "N/A"}
                subtext={cpu.available ? `${cpu.process_count} processes` : "Unavailable"}
                percentage={cpu.available ? cpu.percentage : 0}
                color="blue"
              />

              {/* RAM */}
              <ResourceCard
                icon={<MemoryStick className="w-5 h-5 text-purple-400" />}
                label="RAM Usage"
                value={memory.available ? `${memory.rss_mb} MB` : "N/A"}
                subtext={memory.available ? `${memory.percentage}% of system` : "Unavailable"}
                percentage={memory.available ? memory.percentage : 0}
                color="purple"
              />

              {/* Storage */}
              <ResourceCard
                icon={<Database className="w-5 h-5 text-emerald-400" />}
                label="DB Storage"
                value={storage.database_size || "N/A"}
                subtext={storage.available
                  ? `${storage.disk_free_gb} GB free`
                  : "Unavailable"
                }
                percentage={storage.disk_usage_pct || 0}
                color="emerald"
              />

              {/* Connections */}
              <ResourceCard
                icon={<Users className="w-5 h-5 text-amber-400" />}
                label="Connections"
                value={connections.available
                  ? `${connections.total} / ${connections.max_connections}`
                  : "N/A"
                }
                subtext={connections.available
                  ? `${connections.active} active, ${connections.idle} idle`
                  : "Unavailable"
                }
                percentage={connections.available && connections.max_connections
                  ? (connections.total / connections.max_connections * 100)
                  : 0
                }
                color="amber"
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Detailed Tabs */}
      {isRunning && isReachable && (
        <Tabs defaultValue="storage" className="space-y-4">
          <TabsList className="bg-[#18181B] border border-[#27272A]">
            <TabsTrigger value="storage">Storage Details</TabsTrigger>
            <TabsTrigger value="connections">Connections</TabsTrigger>
            <TabsTrigger value="pool">Connection Pool</TabsTrigger>
          </TabsList>

          {/* Storage Details */}
          <TabsContent value="storage">
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader>
                <CardTitle className="text-white text-lg flex items-center gap-2">
                  <Database className="w-5 h-5 text-emerald-400" />
                  Table Storage Breakdown
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {/* Disk overview */}
                  <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 mb-4">
                    <StatBox label="Total Disk" value={`${storage.disk_total_gb || 0} GB`} />
                    <StatBox label="Disk Used" value={`${storage.disk_used_gb || 0} GB`} />
                    <StatBox label="Disk Free" value={`${storage.disk_free_gb || 0} GB`} />
                    <StatBox label="DB Size" value={storage.database_size || "N/A"} />
                  </div>

                  {/* Per-table breakdown */}
                  {storage.tables && Object.keys(storage.tables).length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-[#27272A] text-[#A1A1AA]">
                            <th className="text-left py-2 px-3">Table</th>
                            <th className="text-right py-2 px-3">Rows</th>
                            <th className="text-right py-2 px-3">Data Size</th>
                            <th className="text-right py-2 px-3">Index Size</th>
                            <th className="text-right py-2 px-3">Total Size</th>
                            <th className="py-2 px-3 w-32">Usage</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(storage.tables)
                            .sort((a, b) => (b[1].total_bytes || 0) - (a[1].total_bytes || 0))
                            .map(([name, info]) => {
                              const pct = storage.database_size_bytes
                                ? ((info.total_bytes || 0) / storage.database_size_bytes * 100)
                                : 0;
                              return (
                                <tr key={name} className="border-b border-[#27272A]/50 hover:bg-[#27272A]/30">
                                  <td className="py-2 px-3 text-white font-mono text-xs">{name}</td>
                                  <td className="py-2 px-3 text-right text-[#A1A1AA]">
                                    {(info.row_count || 0).toLocaleString()}
                                  </td>
                                  <td className="py-2 px-3 text-right text-[#A1A1AA]">{info.data_size}</td>
                                  <td className="py-2 px-3 text-right text-[#A1A1AA]">{info.index_size}</td>
                                  <td className="py-2 px-3 text-right text-white font-medium">{info.total_size}</td>
                                  <td className="py-2 px-3">
                                    <div className="flex items-center gap-2">
                                      <Progress value={pct} className="h-2 flex-1" />
                                      <span className="text-xs text-[#A1A1AA] w-10 text-right">
                                        {pct.toFixed(1)}%
                                      </span>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-[#A1A1AA] text-sm">No table data available</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Connections Details */}
          <TabsContent value="connections">
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader>
                <CardTitle className="text-white text-lg flex items-center gap-2">
                  <Users className="w-5 h-5 text-amber-400" />
                  Active Connections
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                  <StatBox label="Active" value={connections.active || 0} color="green" />
                  <StatBox label="Idle" value={connections.idle || 0} color="blue" />
                  <StatBox label="Idle in Transaction" value={connections.idle_in_transaction || 0} color="yellow" />
                  <StatBox label="Max Allowed" value={connections.max_connections || 0} />
                </div>

                {/* By state */}
                {connections.connections_by_state && Object.keys(connections.connections_by_state).length > 0 && (
                  <div className="mb-4">
                    <h4 className="text-sm font-medium text-[#A1A1AA] mb-2">By State</h4>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(connections.connections_by_state).map(([state, count]) => (
                        <Badge key={state} variant="outline" className="text-xs">
                          {state}: {count}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* By database */}
                {connections.connections_by_database && Object.keys(connections.connections_by_database).length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-[#A1A1AA] mb-2">By Database</h4>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(connections.connections_by_database).map(([db, count]) => (
                        <Badge key={db} variant="outline" className="text-xs">
                          {db}: {count}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Pool Details */}
          <TabsContent value="pool">
            <Card className="bg-[#18181B] border-[#27272A]">
              <CardHeader>
                <CardTitle className="text-white text-lg flex items-center gap-2">
                  <Activity className="w-5 h-5 text-blue-400" />
                  asyncpg Connection Pool
                </CardTitle>
              </CardHeader>
              <CardContent>
                {pool.available ? (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <StatBox label="Pool Size" value={pool.size || 0} />
                    <StatBox label="Min Size" value={pool.min_size || 0} />
                    <StatBox label="Max Size" value={pool.max_size || 0} />
                    <StatBox label="Idle" value={pool.idle || 0} color="green" />
                  </div>
                ) : (
                  <p className="text-[#A1A1AA] text-sm">
                    Connection pool is not available. PostgreSQL may not be connected.
                  </p>
                )}

                {memory.shared_buffers_mb && (
                  <div className="mt-4 p-3 bg-[#09090B] rounded border border-[#27272A]">
                    <span className="text-xs text-[#A1A1AA]">Shared Buffers: </span>
                    <span className="text-sm text-white font-mono">{memory.shared_buffers_mb}</span>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}

      {/* Schema Info Card */}
      <Card className="bg-[#18181B] border-[#27272A]">
        <CardHeader>
          <CardTitle className="text-white text-lg flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-[#3B82F6]" />
            Database Schema (14 Tables)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {[
              { name: "prices_daily", desc: "OHLCV + delivery data", fields: "18 columns" },
              { name: "derived_metrics_daily", desc: "Return, range, volume metrics", fields: "13 columns" },
              { name: "technical_indicators", desc: "SMA, RSI, MACD, Ichimoku, etc.", fields: "27 columns" },
              { name: "ml_features_daily", desc: "Volatility, momentum, ML features", fields: "22 columns" },
              { name: "risk_metrics", desc: "Beta, Sharpe, drawdown, etc.", fields: "10 columns" },
              { name: "valuation_daily", desc: "P/E, P/B, EV/EBITDA, yields", fields: "19 columns" },
              { name: "fundamentals_quarterly", desc: "Income, balance sheet, cash flow, ratios", fields: "55 columns" },
              { name: "shareholding_quarterly", desc: "Promoter, FII, DII holdings", fields: "12 columns" },
              { name: "corporate_actions", desc: "Dividends, splits, bonuses, events", fields: "15 columns" },
              { name: "macro_indicators", desc: "CPI, repo rate, commodity prices", fields: "9 columns" },
              { name: "derivatives_daily", desc: "F&O: futures OI, options, PCR, IV", fields: "16 columns" },
              { name: "intraday_metrics", desc: "Hourly RSI, VWAP, VIX", fields: "8 columns" },
              { name: "weekly_metrics", desc: "Weekly crossovers, Google Trends", fields: "6 columns" },
              { name: "schema_migrations", desc: "Migration version tracking", fields: "4 columns" },
            ].map((table) => (
              <div
                key={table.name}
                className="p-3 bg-[#09090B] rounded border border-[#27272A] hover:border-[#3B82F6]/30 transition-colors"
              >
                <p className="text-white text-sm font-mono font-medium">{table.name}</p>
                <p className="text-[#A1A1AA] text-xs mt-1">{table.desc}</p>
                <Badge variant="outline" className="text-xs mt-2">{table.fields}</Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ResourceCard({ icon, label, value, subtext, percentage, color }) {
  const colorMap = {
    blue: "bg-blue-500",
    purple: "bg-purple-500",
    emerald: "bg-emerald-500",
    amber: "bg-amber-500",
    green: "bg-green-500",
    red: "bg-red-500",
  };

  return (
    <div className="p-4 bg-[#09090B] rounded-lg border border-[#27272A]">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-xs text-[#A1A1AA] font-medium">{label}</span>
      </div>
      <p className="text-xl font-bold text-white">{value}</p>
      <p className="text-xs text-[#71717A] mt-1">{subtext}</p>
      {typeof percentage === "number" && percentage > 0 && (
        <div className="mt-2">
          <Progress
            value={Math.min(percentage, 100)}
            className="h-1.5"
          />
        </div>
      )}
    </div>
  );
}

function StatBox({ label, value, color }) {
  const colorMap = {
    green: "text-green-400",
    blue: "text-blue-400",
    yellow: "text-yellow-400",
    red: "text-red-400",
  };

  return (
    <div className="p-3 bg-[#09090B] rounded border border-[#27272A]">
      <p className="text-xs text-[#A1A1AA]">{label}</p>
      <p className={`text-lg font-bold mt-1 ${color ? colorMap[color] : "text-white"}`}>
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>
    </div>
  );
}
