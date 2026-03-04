import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Database, Server, HardDrive, RefreshCw, ChevronRight, Search,
  AlertTriangle, CheckCircle2, XCircle, Shield, ShieldOff, Trash2,
  Activity, Eye, Settings, FileText, ArrowUpDown, ChevronDown,
  BarChart3, Layers, Clock, Zap, Info, ExternalLink, Filter, X,
  Plus, Edit3, Save, List, Briefcase, Bell, Download, Play,
  HelpCircle, Terminal, GitCompare, Sun, Moon, Archive,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "../components/ui/table";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "../components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../components/ui/select";
import { Switch } from "../components/ui/switch";
import { Label } from "../components/ui/label";
import { ScrollArea } from "../components/ui/scroll-area";
import { Separator } from "../components/ui/separator";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line,
} from "recharts";
import {
  getDatabaseOverview, getDatabaseHealth, getDataFlow, getThresholdAlerts,
  getMongoCollections, getCollectionSample, getCollectionSchema, deleteCollectionDocument,
  getPgTables, getTableSample, getTableSchema,
  getRedisKeys, getDatabaseActivity, getDatabaseErrors, getErrorTrend,
  getDatabaseSettings, updateDatabaseSettings,
  getAuditLog, writeAuditLog, getCacheStats, flushCache,
  getWatchlist, addToWatchlist, updateWatchlistItem, removeFromWatchlist,
  getPortfolio, addToPortfolio, updatePortfolioHolding, removeFromPortfolio,
  getAlerts, createAlert, updateAlert, deleteAlert,
  exportCollection, exportTable,
  executeMongoQuery, executePgQuery, triggerBackup,
  recordSizeSnapshot, getSizeHistory, compareCollections,
} from "../lib/api";
import { toast } from "sonner";

// ============================================================
//  Constants
// ============================================================

const DELETABLE_COLLECTIONS_SET = new Set([
  "watchlist", "portfolio", "alerts", "news_articles",
  "backtest_results", "extraction_log", "pipeline_jobs", "quality_reports",
]);

const ID_FIELD_PRIORITY = ["symbol", "alert_id", "id", "article_id", "backtest_id", "job_id"];

function deriveIdField(doc) {
  for (const field of ID_FIELD_PRIORITY) {
    if (doc[field] != null) return field;
  }
  const keys = Object.keys(doc);
  return keys.length > 0 ? keys[0] : null;
}

// ============================================================
//  Helper components
// ============================================================

function StatusBadge({ status }) {
  const map = {
    connected: { color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30", label: "Connected" },
    healthy: { color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30", label: "Healthy" },
    degraded: { color: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30", label: "Degraded" },
    fallback: { color: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30", label: "Fallback" },
    error: { color: "bg-red-500/20 text-red-400 border-red-500/30", label: "Error" },
    not_initialized: { color: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30", label: "Not Initialized" },
    unavailable: { color: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30", label: "Unavailable" },
  };
  const s = map[status] || map.unavailable;
  return <Badge variant="outline" className={`${s.color} text-xs`}>{s.label}</Badge>;
}

function MetricBox({ label, value, sub, icon: Icon }) {
  return (
    <div className="bg-zinc-800/50 rounded-lg p-3 border border-zinc-700/50">
      <div className="flex items-center gap-2 text-zinc-400 text-xs mb-1">
        {Icon && <Icon className="h-3.5 w-3.5" />}
        {label}
      </div>
      <div className="text-lg font-semibold font-mono text-zinc-100">{value ?? "N/A"}</div>
      {sub && <div className="text-xs text-zinc-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function Pagination({ page, totalPages, onPageChange }) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center gap-2 mt-3">
      <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        Prev
      </Button>
      <span className="text-xs text-zinc-400">
        Page {page} of {totalPages}
      </span>
      <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
        Next
      </Button>
    </div>
  );
}

function SectionLoading() {
  return (
    <div className="flex items-center justify-center py-12 text-zinc-500">
      <RefreshCw className="h-5 w-5 animate-spin mr-2" /> Loading...
    </div>
  );
}

function SectionError({ message, onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-zinc-400 gap-3">
      <AlertTriangle className="h-6 w-6 text-yellow-500" />
      <p className="text-sm">{message || "Failed to load data"}</p>
      {onRetry && <Button size="sm" variant="outline" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

// ============================================================
//  Main Component
// ============================================================

export default function DatabaseDashboard() {
  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [overview, setOverview] = useState(null);
  const [health, setHealth] = useState(null);
  const [settings, setSettings] = useState(null);
  const [thresholdAlerts, setThresholdAlerts] = useState([]);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(true);
  const [wsStatus, setWsStatus] = useState("disconnected");
  const [wsPulse, setWsPulse] = useState(null);
  const wsRef = useRef(null);

  // WebSocket connection for real-time dashboard updates
  useEffect(() => {
    const backendUrl = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
    const wsUrl = backendUrl.replace(/^http/, "ws") + "/ws/dashboard";
    let ws;
    let reconnectTimer;

    function connect() {
      try {
        ws = new WebSocket(wsUrl);
        wsRef.current = ws;
        ws.onopen = () => setWsStatus("connected");
        ws.onmessage = (e) => {
          try { setWsPulse(JSON.parse(e.data)); } catch {}
        };
        ws.onclose = () => {
          setWsStatus("disconnected");
          reconnectTimer = setTimeout(connect, 5000);
        };
        ws.onerror = () => setWsStatus("error");
      } catch { setWsStatus("error"); }
    }
    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, []);

  // Fetch core data
  const fetchCoreData = useCallback(async (showToast = false) => {
    try {
      setRefreshing(true);
      const [ovRes, hlRes, stRes, taRes] = await Promise.all([
        getDatabaseOverview().catch(() => ({ data: null })),
        getDatabaseHealth().catch(() => ({ data: null })),
        getDatabaseSettings().catch(() => ({ data: null })),
        getThresholdAlerts().catch(() => ({ data: { alerts: [] } })),
      ]);
      if (ovRes.data) setOverview(ovRes.data);
      if (hlRes.data) setHealth(hlRes.data);
      if (stRes.data) setSettings(stRes.data);
      if (taRes.data) setThresholdAlerts(taRes.data.alerts || []);
      setLastRefresh(new Date());
      if (showToast) toast.success("Dashboard refreshed");
    } catch (err) {
      toast.error("Failed to refresh dashboard");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchCoreData(); }, [fetchCoreData]);

  // Auto-refresh
  useEffect(() => {
    const interval = (settings?.auto_refresh_interval || 30) * 1000;
    const timer = setInterval(() => fetchCoreData(), interval);
    return () => clearInterval(timer);
  }, [settings, fetchCoreData]);

  if (loading) return <SectionLoading />;

  const mongo = overview?.mongodb || {};
  const pg = overview?.postgresql || {};
  const redis = overview?.redis || {};

  const themeClass = darkMode ? "" : "db-dashboard-light";

  return (
    <div className={`space-y-6 ${themeClass}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold font-heading tracking-tight flex items-center gap-2">
            <Database className="h-6 w-6 text-blue-500" />
            Database Dashboard
            {/* WS status indicator */}
            <span className={`inline-block h-2 w-2 rounded-full ${
              wsStatus === "connected" ? "bg-emerald-400" : wsStatus === "error" ? "bg-red-400" : "bg-zinc-500"
            }`} title={`WebSocket: ${wsStatus}`} />
          </h1>
          <p className="text-sm text-zinc-400 mt-1">
            Complete database visibility, monitoring, and management
            {wsPulse?.recent_errors_5m > 0 && (
              <span className="text-red-400 ml-2">({wsPulse.recent_errors_5m} errors in 5m)</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {lastRefresh && (
            <span className="text-xs text-zinc-500">
              Updated {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <Button size="sm" variant="ghost" onClick={() => setHelpOpen(true)} title="Help">
            <HelpCircle className="h-4 w-4" />
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setDarkMode(!darkMode)} title="Toggle theme">
            {darkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => fetchCoreData(true)}
            disabled={refreshing}
          >
            <RefreshCw className={`h-4 w-4 mr-1 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <SafeModeToggle settings={settings} onUpdate={setSettings} />
        </div>
      </div>

      {/* Threshold alerts banner */}
      {thresholdAlerts.length > 0 && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
          <div className="flex items-center gap-2 text-yellow-400 text-sm font-medium mb-1">
            <AlertTriangle className="h-4 w-4" /> Threshold Alerts
          </div>
          {thresholdAlerts.map((a, i) => (
            <div key={i} className="text-xs text-yellow-300/80 ml-6">{a.message}</div>
          ))}
        </div>
      )}

      {/* Health status cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <HealthCard
          title="MongoDB"
          icon={Database}
          status={mongo.status}
          metrics={[
            { label: "Collections", value: mongo.collections_count },
            { label: "Documents", value: mongo.total_documents?.toLocaleString() },
            { label: "Data Size", value: mongo.size?.data_size_mb ? `${mongo.size.data_size_mb} MB` : "N/A" },
          ]}
        />
        <HealthCard
          title="PostgreSQL"
          icon={HardDrive}
          status={pg.status}
          metrics={[
            { label: "Tables", value: pg.tables_count },
            { label: "Total Rows", value: pg.total_rows?.toLocaleString() },
            { label: "Pool", value: pg.pool ? `${pg.pool.size - pg.pool.free_size}/${pg.pool.size}` : "N/A" },
          ]}
        />
        <HealthCard
          title="Redis"
          icon={Zap}
          status={redis.status}
          metrics={[
            { label: "Keys", value: redis.key_count?.toLocaleString() },
            { label: "Hit Rate", value: redis.hit_rate != null ? `${redis.hit_rate}%` : "N/A" },
            { label: "Memory", value: redis.memory_used || "N/A" },
          ]}
        />
      </div>

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-zinc-800/80 border border-zinc-700/50 flex-wrap">
          <TabsTrigger value="overview"><Layers className="h-3.5 w-3.5 mr-1" />Overview</TabsTrigger>
          <TabsTrigger value="data-mgmt"><Edit3 className="h-3.5 w-3.5 mr-1" />Data Management</TabsTrigger>
          <TabsTrigger value="mongodb"><Database className="h-3.5 w-3.5 mr-1" />MongoDB</TabsTrigger>
          <TabsTrigger value="postgresql"><HardDrive className="h-3.5 w-3.5 mr-1" />PostgreSQL</TabsTrigger>
          <TabsTrigger value="redis"><Zap className="h-3.5 w-3.5 mr-1" />Redis</TabsTrigger>
          <TabsTrigger value="activity"><Activity className="h-3.5 w-3.5 mr-1" />Activity</TabsTrigger>
          <TabsTrigger value="query"><Terminal className="h-3.5 w-3.5 mr-1" />Query</TabsTrigger>
          <TabsTrigger value="tools"><Archive className="h-3.5 w-3.5 mr-1" />Tools</TabsTrigger>
          <TabsTrigger value="settings"><Settings className="h-3.5 w-3.5 mr-1" />Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab overview={overview} health={health} />
        </TabsContent>
        <TabsContent value="data-mgmt">
          <DataManagementTab safeMode={settings?.safe_mode} />
        </TabsContent>
        <TabsContent value="mongodb">
          <MongoDBTab safeMode={settings?.safe_mode} />
        </TabsContent>
        <TabsContent value="postgresql">
          <PostgreSQLTab />
        </TabsContent>
        <TabsContent value="redis">
          <RedisTab />
        </TabsContent>
        <TabsContent value="activity">
          <ActivityTab />
        </TabsContent>
        <TabsContent value="query">
          <QueryPlaygroundTab />
        </TabsContent>
        <TabsContent value="tools">
          <ToolsTab />
        </TabsContent>
        <TabsContent value="settings">
          <SettingsTab settings={settings} onUpdate={setSettings} />
        </TabsContent>
      </Tabs>

      {/* Help Panel Dialog */}
      <HelpPanel open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}

// ============================================================
//  Health Card
// ============================================================

function HealthCard({ title, icon: Icon, status, metrics }) {
  return (
    <Card className="bg-zinc-900/50 border-zinc-800">
      <CardContent className="pt-4 pb-3 px-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-blue-400" />
            <span className="font-medium text-sm">{title}</span>
          </div>
          <StatusBadge status={status} />
        </div>
        <div className="grid grid-cols-3 gap-2">
          {metrics.map((m, i) => (
            <div key={i} className="text-center">
              <div className="text-xs text-zinc-500">{m.label}</div>
              <div className="text-sm font-mono font-semibold">{m.value ?? "-"}</div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ============================================================
//  Safe Mode Toggle
// ============================================================

function SafeModeToggle({ settings, onUpdate }) {
  const safeMode = settings?.safe_mode ?? true;

  const toggle = async () => {
    try {
      const res = await updateDatabaseSettings({ safe_mode: !safeMode });
      onUpdate(res.data);
      toast.success(`Safe Mode ${!safeMode ? "enabled" : "disabled"}`);
    } catch {
      toast.error("Failed to update safe mode");
    }
  };

  return (
    <div className="flex items-center gap-2">
      {safeMode ? (
        <Shield className="h-4 w-4 text-emerald-400" />
      ) : (
        <ShieldOff className="h-4 w-4 text-yellow-400" />
      )}
      <span className="text-xs text-zinc-400">Safe</span>
      <Switch checked={safeMode} onCheckedChange={toggle} />
    </div>
  );
}

// ============================================================
//  Overview Tab
// ============================================================

function OverviewTab({ overview, health }) {
  const [dataFlow, setDataFlow] = useState(null);
  const [flowLoading, setFlowLoading] = useState(true);

  useEffect(() => {
    getDataFlow()
      .then((r) => setDataFlow(r.data))
      .catch(() => {})
      .finally(() => setFlowLoading(false));
  }, []);

  const mongo = overview?.mongodb || {};
  const pg = overview?.postgresql || {};

  return (
    <div className="space-y-6 mt-4">
      {/* Storage Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* MongoDB Collections */}
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Database className="h-4 w-4 text-blue-400" />
              MongoDB Collections
            </CardTitle>
          </CardHeader>
          <CardContent>
            {mongo.collections ? (
              <div className="space-y-1.5">
                {Object.entries(mongo.collections).map(([name, info]) => (
                  <div key={name} className="flex items-center justify-between text-xs">
                    <span className="text-zinc-300 font-mono">{name}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-500">{info.documents?.toLocaleString()} docs</span>
                      {info.ttl && <Badge variant="outline" className="text-[10px] border-yellow-500/30 text-yellow-400">TTL {info.ttl}</Badge>}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-zinc-500">No data available</p>
            )}
          </CardContent>
        </Card>

        {/* PostgreSQL Tables */}
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <HardDrive className="h-4 w-4 text-emerald-400" />
              PostgreSQL Tables
            </CardTitle>
          </CardHeader>
          <CardContent>
            {pg.tables ? (
              <div className="space-y-1.5">
                {Object.entries(pg.tables).map(([name, info]) => (
                  <div key={name} className="flex items-center justify-between text-xs">
                    <span className="text-zinc-300 font-mono">{name}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-zinc-500">{info.rows?.toLocaleString()} rows</span>
                      <span className="text-zinc-600">{info.size}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-zinc-500">Not initialized</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Storage Usage Chart */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-cyan-400" />
            Storage Usage
          </CardTitle>
        </CardHeader>
        <CardContent>
          <StorageChart mongodb={mongo} postgresql={pg} />
        </CardContent>
      </Card>

      {/* Data Flow */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <ArrowUpDown className="h-4 w-4 text-purple-400" />
            Data Flow
          </CardTitle>
        </CardHeader>
        <CardContent>
          {flowLoading ? (
            <SectionLoading />
          ) : dataFlow ? (
            <div className="space-y-4">
              <p className="text-xs text-zinc-400">{dataFlow.description}</p>
              <div className="flex flex-wrap gap-2 items-center justify-center">
                {dataFlow.stages?.map((stage, i) => (
                  <React.Fragment key={i}>
                    <div className="bg-zinc-800 border border-zinc-700 rounded-lg p-3 text-center min-w-[140px]">
                      <div className="text-[10px] text-zinc-500 mb-1">Stage {stage.stage}</div>
                      <div className="text-xs font-medium text-zinc-200">{stage.name}</div>
                      <div className="text-[10px] text-zinc-500 mt-1 max-w-[160px]">{stage.description}</div>
                    </div>
                    {i < dataFlow.stages.length - 1 && (
                      <ChevronRight className="h-4 w-4 text-zinc-600 flex-shrink-0" />
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-zinc-500">Could not load data flow</p>
          )}
        </CardContent>
      </Card>

      {/* System Info */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Server className="h-4 w-4 text-orange-400" />
            Connections & System
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <div className="text-xs text-zinc-400 mb-2 font-medium">MongoDB</div>
              <div className="space-y-1 text-xs">
                <div className="flex justify-between"><span className="text-zinc-500">Status</span><StatusBadge status={health?.mongodb?.status} /></div>
                <div className="flex justify-between"><span className="text-zinc-500">Database</span><span className="font-mono text-zinc-300">{health?.mongodb?.database || "N/A"}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Collections</span><span className="font-mono">{health?.mongodb?.collections_count || 0}</span></div>
              </div>
            </div>
            <div>
              <div className="text-xs text-zinc-400 mb-2 font-medium">PostgreSQL</div>
              <div className="space-y-1 text-xs">
                <div className="flex justify-between"><span className="text-zinc-500">Status</span><StatusBadge status={health?.postgresql?.status} /></div>
                <div className="flex justify-between"><span className="text-zinc-500">Pool Total</span><span className="font-mono">{pg.pool?.size ?? "N/A"}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Pool Free</span><span className="font-mono">{pg.pool?.free_size ?? "N/A"}</span></div>
              </div>
            </div>
            <div>
              <div className="text-xs text-zinc-400 mb-2 font-medium">Redis</div>
              <div className="space-y-1 text-xs">
                <div className="flex justify-between"><span className="text-zinc-500">Status</span><StatusBadge status={health?.redis?.status} /></div>
                <div className="flex justify-between"><span className="text-zinc-500">Backend</span><span className="font-mono text-zinc-300">{health?.redis?.backend || "N/A"}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Memory</span><span className="font-mono">{health?.redis?.memory_used || "N/A"}</span></div>
              </div>
            </div>
          </div>
          <Separator className="my-3 bg-zinc-800" />
          <div className="text-xs text-zinc-500 flex items-center gap-1">
            <Info className="h-3 w-3" />
            Current access: single user (you). Authentication can be added later.
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ============================================================
//  MongoDB Tab
// ============================================================

function MongoDBTab({ safeMode }) {
  const [collections, setCollections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [viewMode, setViewMode] = useState("sample"); // sample | schema
  const [sample, setSample] = useState(null);
  const [schema, setSchema] = useState(null);
  const [samplePage, setSamplePage] = useState(1);
  const [searchTerm, setSearchTerm] = useState("");
  const [deleteDialog, setDeleteDialog] = useState(null);

  useEffect(() => {
    getMongoCollections()
      .then((r) => setCollections(r.data.collections || []))
      .catch(() => toast.error("Failed to load collections"))
      .finally(() => setLoading(false));
  }, []);

  const loadSample = useCallback(async (name, page = 1) => {
    try {
      const r = await getCollectionSample(name, page);
      setSample(r.data);
      setSamplePage(page);
    } catch {
      toast.error("Failed to load sample");
    }
  }, []);

  const loadSchema = useCallback(async (name) => {
    try {
      const r = await getCollectionSchema(name);
      setSchema(r.data);
    } catch {
      toast.error("Failed to load schema");
    }
  }, []);

  const selectCollection = (name) => {
    setSelected(name);
    setViewMode("sample");
    setSample(null);
    setSchema(null);
    loadSample(name, 1);
  };

  const handleDelete = async () => {
    if (!deleteDialog) return;
    try {
      await deleteCollectionDocument(
        deleteDialog.collection,
        deleteDialog.idField,
        deleteDialog.idValue
      );
      toast.success("Document deleted");
      setDeleteDialog(null);
      if (selected) loadSample(selected, samplePage);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Delete failed");
    }
  };

  if (loading) return <SectionLoading />;

  const filteredCollections = collections.filter((c) =>
    c.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="mt-4 grid grid-cols-1 lg:grid-cols-4 gap-4">
      {/* Collection list */}
      <div className="lg:col-span-1">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Collections</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <Input
              placeholder="Search..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="h-8 text-xs mb-2 bg-zinc-800 border-zinc-700"
            />
            {filteredCollections.map((c) => (
              <button
                key={c.name}
                onClick={() => selectCollection(c.name)}
                className={`w-full text-left px-3 py-2 rounded-md text-xs transition-colors ${
                  selected === c.name
                    ? "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                    : "hover:bg-zinc-800 text-zinc-300"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono">{c.name}</span>
                  <span className="text-zinc-500">{c.documents}</span>
                </div>
                {c.ttl && <div className="text-[10px] text-yellow-500 mt-0.5">TTL: {c.ttl}</div>}
              </button>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Detail panel */}
      <div className="lg:col-span-3">
        {!selected ? (
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="flex flex-col items-center justify-center py-16 text-zinc-500">
              <Database className="h-8 w-8 mb-3" />
              <p className="text-sm">Select a collection to view its data</p>
            </CardContent>
          </Card>
        ) : (
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-mono">{selected}</CardTitle>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant={viewMode === "sample" ? "default" : "outline"}
                    onClick={() => { setViewMode("sample"); if (!sample) loadSample(selected); }}
                  >
                    <Eye className="h-3.5 w-3.5 mr-1" />Data
                  </Button>
                  <Button
                    size="sm"
                    variant={viewMode === "schema" ? "default" : "outline"}
                    onClick={() => { setViewMode("schema"); if (!schema) loadSchema(selected); }}
                  >
                    <Layers className="h-3.5 w-3.5 mr-1" />Schema
                  </Button>
                </div>
              </div>
              {/* Collection meta */}
              {collections.find((c) => c.name === selected) && (
                <div className="text-xs text-zinc-500 mt-1 space-y-0.5">
                  <p>{collections.find((c) => c.name === selected)?.description}</p>
                  <p>
                    <span className="text-zinc-600">Sources: </span>
                    {collections.find((c) => c.name === selected)?.sources?.join(", ")}
                  </p>
                  <p>
                    <span className="text-zinc-600">Consumers: </span>
                    {collections.find((c) => c.name === selected)?.consumers?.join(", ")}
                  </p>
                </div>
              )}
            </CardHeader>
            <CardContent>
              {viewMode === "sample" && sample && (
                <>
                  <div className="text-xs text-zinc-500 mb-2">
                    {sample.total} documents total
                  </div>
                  <ScrollArea className="max-h-[500px]">
                    <div className="space-y-2">
                      {sample.documents?.map((doc, i) => (
                        <div key={i} className="bg-zinc-800/70 rounded p-3 text-xs font-mono relative group">
                          <pre className="text-zinc-300 whitespace-pre-wrap break-all max-h-40 overflow-auto">
                            {JSON.stringify(doc, null, 2)}
                          </pre>
                          {/* Delete button - show for all docs in deletable collections */}
                          {DELETABLE_COLLECTIONS_SET.has(selected) && (() => {
                            const idField = deriveIdField(doc);
                            const idValue = idField ? doc[idField] : null;
                            if (!idField || !idValue) return null;
                            return (
                              <button
                                onClick={() =>
                                  setDeleteDialog({
                                    collection: selected,
                                    idField,
                                    idValue: String(idValue),
                                    preview: JSON.stringify(doc, null, 2).substring(0, 200),
                                  })
                                }
                                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30"
                                title="Delete document"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            );
                          })()}
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                  <Pagination
                    page={sample.page}
                    totalPages={sample.total_pages}
                    onPageChange={(p) => loadSample(selected, p)}
                  />
                </>
              )}
              {viewMode === "sample" && !sample && <SectionLoading />}

              {viewMode === "schema" && schema && (
                <div className="space-y-4">
                  <div>
                    <h4 className="text-xs font-medium text-zinc-400 mb-2">Fields (inferred from {schema.sample_count} documents)</h4>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-1">
                      {Object.entries(schema.fields || {}).map(([field, types]) => (
                        <div key={field} className="bg-zinc-800/70 rounded px-2 py-1.5 text-xs">
                          <span className="font-mono text-zinc-300">{field}</span>
                          <span className="text-zinc-600 ml-1">({Array.isArray(types) ? types.join(", ") : types})</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  {schema.indexes && (
                    <div>
                      <h4 className="text-xs font-medium text-zinc-400 mb-2">Indexes</h4>
                      <div className="space-y-1">
                        {Object.entries(schema.indexes).map(([name, info]) => (
                          <div key={name} className="text-xs bg-zinc-800/50 rounded px-2 py-1.5">
                            <span className="font-mono text-zinc-300">{name}</span>
                            {info.unique && <Badge variant="outline" className="ml-2 text-[10px] border-emerald-500/30 text-emerald-400">unique</Badge>}
                            {info.sparse && <Badge variant="outline" className="ml-1 text-[10px] border-yellow-500/30 text-yellow-400">sparse</Badge>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {schema.validator && (
                    <div>
                      <h4 className="text-xs font-medium text-zinc-400 mb-2">JSON Schema Validator</h4>
                      <pre className="bg-zinc-800/70 rounded p-3 text-xs font-mono text-zinc-300 whitespace-pre-wrap max-h-60 overflow-auto">
                        {JSON.stringify(schema.validator, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
              {viewMode === "schema" && !schema && <SectionLoading />}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Delete confirmation dialog */}
      <Dialog open={!!deleteDialog} onOpenChange={() => setDeleteDialog(null)}>
        <DialogContent className="bg-zinc-900 border-zinc-800">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-400">
              <Trash2 className="h-4 w-4" /> Confirm Delete
            </DialogTitle>
            <DialogDescription>
              {safeMode && (
                <span className="text-yellow-400 text-xs flex items-center gap-1 mb-2">
                  <Shield className="h-3 w-3" /> Safe Mode is ON - please confirm this action
                </span>
              )}
              <span className="block mt-1">
                Delete document from <span className="font-mono text-zinc-300">{deleteDialog?.collection}</span> where{" "}
                <span className="font-mono text-zinc-300">{deleteDialog?.idField} = {deleteDialog?.idValue}</span>?
              </span>
            </DialogDescription>
          </DialogHeader>
          {deleteDialog?.preview && (
            <pre className="text-xs font-mono text-zinc-400 bg-zinc-800/50 rounded p-2 max-h-32 overflow-auto">
              {deleteDialog.preview}
            </pre>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialog(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ============================================================
//  PostgreSQL Tab
// ============================================================

function PostgreSQLTab() {
  const [tables, setTables] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [viewMode, setViewMode] = useState("sample");
  const [sample, setSample] = useState(null);
  const [schema, setSchema] = useState(null);

  useEffect(() => {
    getPgTables()
      .then((r) => setTables(r.data.tables || []))
      .catch(() => toast.error("Failed to load tables"))
      .finally(() => setLoading(false));
  }, []);

  const loadSample = async (name, page = 1) => {
    try {
      const r = await getTableSample(name, page);
      setSample(r.data);
    } catch {
      toast.error("Failed to load sample");
    }
  };

  const loadSchema = async (name) => {
    try {
      const r = await getTableSchema(name);
      setSchema(r.data);
    } catch {
      toast.error("Failed to load schema");
    }
  };

  const selectTable = (name) => {
    setSelected(name);
    setViewMode("sample");
    setSample(null);
    setSchema(null);
    loadSample(name, 1);
  };

  if (loading) return <SectionLoading />;
  if (tables.length === 0) return <SectionError message="PostgreSQL not initialized or no tables found" />;

  return (
    <div className="mt-4 grid grid-cols-1 lg:grid-cols-4 gap-4">
      {/* Table list */}
      <div className="lg:col-span-1">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Tables</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {tables.map((t) => (
              <button
                key={t.name}
                onClick={() => selectTable(t.name)}
                className={`w-full text-left px-3 py-2 rounded-md text-xs transition-colors ${
                  selected === t.name
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    : "hover:bg-zinc-800 text-zinc-300"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono">{t.name}</span>
                  <span className="text-zinc-500">{t.rows?.toLocaleString()}</span>
                </div>
                <div className="text-[10px] text-zinc-500 mt-0.5">{t.size}</div>
              </button>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Detail */}
      <div className="lg:col-span-3">
        {!selected ? (
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="flex flex-col items-center justify-center py-16 text-zinc-500">
              <HardDrive className="h-8 w-8 mb-3" />
              <p className="text-sm">Select a table to view its data</p>
            </CardContent>
          </Card>
        ) : (
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-mono">{selected}</CardTitle>
                <div className="flex gap-2">
                  <Button size="sm" variant={viewMode === "sample" ? "default" : "outline"} onClick={() => { setViewMode("sample"); if (!sample) loadSample(selected); }}>
                    <Eye className="h-3.5 w-3.5 mr-1" />Data
                  </Button>
                  <Button size="sm" variant={viewMode === "schema" ? "default" : "outline"} onClick={() => { setViewMode("schema"); if (!schema) loadSchema(selected); }}>
                    <Layers className="h-3.5 w-3.5 mr-1" />Schema
                  </Button>
                </div>
              </div>
              {tables.find((t) => t.name === selected) && (
                <div className="text-xs text-zinc-500 mt-1 space-y-0.5">
                  <p>{tables.find((t) => t.name === selected)?.description}</p>
                  <p>
                    <span className="text-zinc-600">Sources: </span>
                    {tables.find((t) => t.name === selected)?.sources?.join(", ")}
                  </p>
                  <p>
                    <span className="text-zinc-600">Consumers: </span>
                    {tables.find((t) => t.name === selected)?.consumers?.join(", ")}
                  </p>
                  <p>
                    <span className="text-zinc-600">Primary Key: </span>
                    <span className="font-mono text-zinc-400">{tables.find((t) => t.name === selected)?.primary_key}</span>
                  </p>
                </div>
              )}
            </CardHeader>
            <CardContent>
              {viewMode === "sample" && sample && (
                <>
                  <div className="text-xs text-zinc-500 mb-2">{sample.total} rows total (read-only)</div>
                  <ScrollArea className="max-h-[500px]">
                    {sample.documents?.length > 0 ? (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            {Object.keys(sample.documents[0]).map((col) => (
                              <TableHead key={col} className="text-xs font-mono whitespace-nowrap">{col}</TableHead>
                            ))}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {sample.documents.map((row, i) => (
                            <TableRow key={i}>
                              {Object.values(row).map((val, j) => (
                                <TableCell key={j} className="text-xs font-mono py-1.5 whitespace-nowrap">
                                  {val === null ? <span className="text-zinc-600">null</span> : String(val).substring(0, 50)}
                                </TableCell>
                              ))}
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    ) : (
                      <p className="text-xs text-zinc-500 py-4 text-center">No data in this table</p>
                    )}
                  </ScrollArea>
                  <Pagination page={sample.page} totalPages={sample.total_pages} onPageChange={(p) => loadSample(selected, p)} />
                </>
              )}
              {viewMode === "sample" && !sample && <SectionLoading />}

              {viewMode === "schema" && schema && (
                <div className="space-y-4">
                  <div>
                    <h4 className="text-xs font-medium text-zinc-400 mb-2">Columns ({schema.columns?.length})</h4>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="text-xs">Column</TableHead>
                          <TableHead className="text-xs">Type</TableHead>
                          <TableHead className="text-xs">Nullable</TableHead>
                          <TableHead className="text-xs">Default</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {schema.columns?.map((col) => (
                          <TableRow key={col.name}>
                            <TableCell className="text-xs font-mono py-1.5">{col.name}</TableCell>
                            <TableCell className="text-xs text-zinc-400">{col.type}{col.max_length ? `(${col.max_length})` : ""}</TableCell>
                            <TableCell className="text-xs">{col.nullable ? "YES" : "NO"}</TableCell>
                            <TableCell className="text-xs text-zinc-500 font-mono">{col.default || "-"}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                  {schema.indexes?.length > 0 && (
                    <div>
                      <h4 className="text-xs font-medium text-zinc-400 mb-2">Indexes ({schema.indexes.length})</h4>
                      {schema.indexes.map((idx) => (
                        <div key={idx.name} className="text-xs bg-zinc-800/50 rounded px-2 py-1.5 mb-1 font-mono text-zinc-300">
                          {idx.name}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {viewMode === "schema" && !schema && <SectionLoading />}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

// ============================================================
//  Redis Tab
// ============================================================

function RedisTab() {
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [prefix, setPrefix] = useState("");
  const [cacheStats, setCacheStats] = useState(null);

  const fetchKeys = useCallback(async (p = "") => {
    setLoading(true);
    try {
      const [kRes, sRes] = await Promise.all([
        getRedisKeys(p),
        getCacheStats(),
      ]);
      setKeys(kRes.data.keys || []);
      setCacheStats(sRes.data);
    } catch {
      toast.error("Failed to load Redis data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchKeys(); }, [fetchKeys]);

  const handleFlush = async () => {
    if (!window.confirm("Flush all cache entries? This will clear all cached data.")) return;
    try {
      await flushCache();
      toast.success("Cache flushed");
      fetchKeys(prefix);
    } catch {
      toast.error("Flush failed");
    }
  };

  // Group keys by prefix
  const grouped = {};
  keys.forEach((k) => {
    const parts = k.key.split(":");
    const grp = parts.length > 1 ? parts[0] + ":" : "(root)";
    if (!grouped[grp]) grouped[grp] = [];
    grouped[grp].push(k);
  });

  return (
    <div className="mt-4 space-y-4">
      {/* Stats */}
      {cacheStats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <MetricBox label="Backend" value={cacheStats.backend || "N/A"} icon={Server} />
          <MetricBox label="Hit Rate" value={cacheStats.hit_rate_percent != null ? `${cacheStats.hit_rate_percent}%` : "N/A"} icon={BarChart3} />
          <MetricBox label="Hits / Misses" value={`${cacheStats.hits || 0} / ${cacheStats.misses || 0}`} icon={Activity} />
          <MetricBox label="Keys" value={cacheStats.key_count?.toLocaleString()} icon={Database} />
          <MetricBox label="Memory" value={cacheStats.memory_used || "N/A"} icon={HardDrive} />
        </div>
      )}

      {/* Search & Actions */}
      <div className="flex gap-2">
        <Input
          placeholder="Filter by prefix (e.g. price:)"
          value={prefix}
          onChange={(e) => setPrefix(e.target.value)}
          className="h-8 text-xs bg-zinc-800 border-zinc-700 max-w-xs"
        />
        <Button size="sm" variant="outline" onClick={() => fetchKeys(prefix)}>
          <Search className="h-3.5 w-3.5 mr-1" />Search
        </Button>
        <Button size="sm" variant="outline" className="text-red-400 border-red-500/30 hover:bg-red-500/10" onClick={handleFlush}>
          <Trash2 className="h-3.5 w-3.5 mr-1" />Flush Cache
        </Button>
      </div>

      {/* Keys */}
      {loading ? (
        <SectionLoading />
      ) : keys.length === 0 ? (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="py-8 text-center text-zinc-500 text-sm">
            No Redis keys found{prefix ? ` matching "${prefix}"` : ""}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {Object.entries(grouped).map(([grp, grpKeys]) => (
            <Card key={grp} className="bg-zinc-900/50 border-zinc-800">
              <CardHeader className="py-2 px-4">
                <CardTitle className="text-xs flex items-center justify-between">
                  <span className="font-mono text-blue-400">{grp}</span>
                  <Badge variant="outline" className="text-[10px]">{grpKeys.length} keys</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="space-y-1">
                  {grpKeys.slice(0, 20).map((k) => (
                    <div key={k.key} className="flex items-center justify-between text-xs bg-zinc-800/40 rounded px-2 py-1.5">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-mono text-zinc-300 truncate max-w-[300px]">{k.key}</span>
                        <Badge variant="outline" className="text-[10px] flex-shrink-0">{k.type}</Badge>
                      </div>
                      <div className="flex items-center gap-3 flex-shrink-0">
                        {k.ttl && <span className="text-zinc-500 text-[10px]">TTL: {k.ttl}s</span>}
                        {k.value_preview && k.value_preview !== "(hidden - potentially sensitive)" && (
                          <span className="text-zinc-500 text-[10px] truncate max-w-[200px]" title={k.value_preview}>
                            {k.value_preview.substring(0, 60)}
                          </span>
                        )}
                        {k.value_preview === "(hidden - potentially sensitive)" && (
                          <span className="text-yellow-500/60 text-[10px]">hidden</span>
                        )}
                        {k.length != null && <span className="text-zinc-500 text-[10px]">{k.length} items</span>}
                        {k.members != null && <span className="text-zinc-500 text-[10px]">{k.members} members</span>}
                        {k.fields != null && <span className="text-zinc-500 text-[10px]">{k.fields} fields</span>}
                      </div>
                    </div>
                  ))}
                  {grpKeys.length > 20 && (
                    <p className="text-[10px] text-zinc-600 text-center">...and {grpKeys.length - 20} more</p>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================================
//  Activity Tab (Activity + Errors + Audit Log)
// ============================================================

// Compute ISO date string N days ago
function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function ActivityTab() {
  const [subTab, setSubTab] = useState("activity");
  const [activity, setActivity] = useState([]);
  const [errors, setErrors] = useState([]);
  const [errorTrend, setErrorTrend] = useState([]);
  const [auditLog, setAuditLog] = useState(null);
  const [auditPage, setAuditPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");

  // Activity filters
  const [activityCollFilter, setActivityCollFilter] = useState("all");
  const [activityStatusFilter, setActivityStatusFilter] = useState("all");

  // Date range preset
  const [dateRange, setDateRange] = useState("all"); // all | 1 | 7 | 30

  // Audit log filters
  const [auditActionFilter, setAuditActionFilter] = useState("");
  const [auditStoreFilter, setAuditStoreFilter] = useState("");
  const [auditCollFilter, setAuditCollFilter] = useState("");

  const fetchActivityData = useCallback(async () => {
    setLoading(true);
    const since = dateRange !== "all" ? daysAgo(parseInt(dateRange)) : null;
    try {
      await Promise.all([
        getDatabaseActivity(200, null, since).then((r) => setActivity(r.data.activity || [])).catch(() => {}),
        getDatabaseErrors(100, since).then((r) => setErrors(r.data.errors || [])).catch(() => {}),
        getErrorTrend(dateRange !== "all" ? parseInt(dateRange) : 7).then((r) => setErrorTrend(r.data.trend || [])).catch(() => {}),
      ]);
    } finally {
      setLoading(false);
    }
  }, [dateRange]);

  useEffect(() => { fetchActivityData(); }, [fetchActivityData]);

  const loadAuditLog = useCallback(async (page = 1, filters = {}) => {
    try {
      const r = await getAuditLog(page, 50, filters);
      setAuditLog(r.data);
      setAuditPage(page);
    } catch {
      toast.error("Failed to load audit log");
    }
  }, []);

  useEffect(() => {
    if (subTab === "audit") {
      const filters = {};
      if (auditActionFilter) filters.action = auditActionFilter;
      if (auditStoreFilter) filters.store = auditStoreFilter;
      if (auditCollFilter) filters.collection_or_table = auditCollFilter;
      loadAuditLog(1, filters);
    }
  }, [subTab, auditActionFilter, auditStoreFilter, auditCollFilter, loadAuditLog]);

  if (loading) return <SectionLoading />;

  const statusColor = (s) => {
    if (!s) return "text-zinc-500";
    if (["success", "completed"].includes(s)) return "text-emerald-400";
    if (["failed", "error"].includes(s)) return "text-red-400";
    if (["running", "pending"].includes(s)) return "text-yellow-400";
    return "text-zinc-400";
  };

  const filteredActivity = activity.filter((a) => {
    if (searchTerm && !a.summary?.toLowerCase().includes(searchTerm.toLowerCase())) return false;
    if (activityCollFilter !== "all" && a.collection !== activityCollFilter) return false;
    if (activityStatusFilter !== "all") {
      if (activityStatusFilter === "success" && !["success", "completed"].includes(a.status)) return false;
      if (activityStatusFilter === "failed" && !["failed", "error"].includes(a.status)) return false;
      if (activityStatusFilter === "running" && !["running", "pending"].includes(a.status)) return false;
    }
    return true;
  });
  const filteredErrors = errors.filter((e) =>
    !searchTerm || e.message?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="mt-4 space-y-4">
      <Tabs value={subTab} onValueChange={setSubTab}>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <TabsList className="bg-zinc-800/80 border border-zinc-700/50">
            <TabsTrigger value="activity">
              <Activity className="h-3.5 w-3.5 mr-1" />Activity
              <Badge variant="outline" className="ml-1.5 text-[10px]">{activity.length}</Badge>
            </TabsTrigger>
            <TabsTrigger value="errors">
              <XCircle className="h-3.5 w-3.5 mr-1" />Errors
              <Badge variant="outline" className="ml-1.5 text-[10px] border-red-500/30 text-red-400">{errors.length}</Badge>
            </TabsTrigger>
            <TabsTrigger value="audit">
              <FileText className="h-3.5 w-3.5 mr-1" />Audit Log
            </TabsTrigger>
          </TabsList>
          <Input
            placeholder="Search..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="h-8 text-xs bg-zinc-800 border-zinc-700 max-w-[200px]"
          />
        </div>

        <TabsContent value="activity">
          {/* Activity filters */}
          <div className="flex gap-2 mb-3 flex-wrap">
            <Select value={dateRange} onValueChange={setDateRange}>
              <SelectTrigger className="w-[130px] h-8 text-xs bg-zinc-800 border-zinc-700">
                <SelectValue placeholder="Date Range" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Time</SelectItem>
                <SelectItem value="1">Last 24h</SelectItem>
                <SelectItem value="7">Last 7 Days</SelectItem>
                <SelectItem value="30">Last 30 Days</SelectItem>
              </SelectContent>
            </Select>
            <Select value={activityCollFilter} onValueChange={setActivityCollFilter}>
              <SelectTrigger className="w-[160px] h-8 text-xs bg-zinc-800 border-zinc-700">
                <SelectValue placeholder="Collection" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Collections</SelectItem>
                <SelectItem value="pipeline_jobs">Pipeline Jobs</SelectItem>
                <SelectItem value="extraction_log">Extraction Log</SelectItem>
                <SelectItem value="audit_log">Audit Log</SelectItem>
              </SelectContent>
            </Select>
            <Select value={activityStatusFilter} onValueChange={setActivityStatusFilter}>
              <SelectTrigger className="w-[140px] h-8 text-xs bg-zinc-800 border-zinc-700">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="success">Success</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
                <SelectItem value="running">Running</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="pt-4">
              {filteredActivity.length === 0 ? (
                <p className="text-center text-zinc-500 text-sm py-8">No recent activity</p>
              ) : (
                <ScrollArea className="max-h-[600px]">
                  <div className="space-y-1">
                    {filteredActivity.map((a, i) => (
                      <div key={i} className="flex items-start gap-3 px-3 py-2 rounded hover:bg-zinc-800/50 text-xs">
                        <div className={`mt-0.5 ${statusColor(a.status)}`}>
                          {a.status === "success" || a.status === "completed" ? (
                            <CheckCircle2 className="h-3.5 w-3.5" />
                          ) : a.status === "failed" || a.status === "error" ? (
                            <XCircle className="h-3.5 w-3.5" />
                          ) : (
                            <Clock className="h-3.5 w-3.5" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-zinc-300">{a.summary}</div>
                          <div className="text-zinc-600 text-[10px] mt-0.5">
                            {a.timestamp} | {a.collection}
                          </div>
                        </div>
                        <Badge variant="outline" className="text-[10px] flex-shrink-0">{a.type}</Badge>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="errors">
          {/* Error trend chart */}
          {errorTrend.length > 0 && (
            <Card className="bg-zinc-900/50 border-zinc-800 mb-3">
              <CardHeader className="pb-1">
                <CardTitle className="text-xs text-zinc-400">Error Trend (Last 7 Days)</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={150}>
                  <BarChart data={errorTrend}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#71717A" }} tickFormatter={(v) => v.slice(5)} />
                    <YAxis tick={{ fontSize: 10, fill: "#71717A" }} allowDecimals={false} />
                    <Tooltip
                      contentStyle={{ background: "#18181B", border: "1px solid #27272A", borderRadius: 8, fontSize: 12 }}
                      labelStyle={{ color: "#A1A1AA" }}
                    />
                    <Bar dataKey="errors" fill="#EF4444" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="pt-4">
              {filteredErrors.length === 0 ? (
                <div className="flex flex-col items-center py-8 text-zinc-500">
                  <CheckCircle2 className="h-6 w-6 text-emerald-500 mb-2" />
                  <p className="text-sm">No recent errors</p>
                </div>
              ) : (
                <ScrollArea className="max-h-[600px]">
                  <div className="space-y-2">
                    {filteredErrors.map((e, i) => (
                      <div key={i} className="bg-red-500/5 border border-red-500/10 rounded-lg px-3 py-2 text-xs">
                        <div className="flex items-center gap-2 mb-1">
                          <XCircle className="h-3.5 w-3.5 text-red-400" />
                          <span className="text-red-300 font-medium">{e.message}</span>
                        </div>
                        <div className="text-zinc-600 text-[10px] ml-5">
                          {e.timestamp} | {e.collection} | {e.type}
                        </div>
                        {e.details?.errors && e.details.errors.length > 0 && (
                          <div className="ml-5 mt-1 text-zinc-500 text-[10px]">
                            {e.details.errors.slice(0, 3).map((err, j) => (
                              <div key={j}>{err}</div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="audit">
          {/* Audit log filters */}
          <div className="flex gap-2 mb-3 flex-wrap">
            <Select value={auditActionFilter || "all"} onValueChange={(v) => setAuditActionFilter(v === "all" ? "" : v)}>
              <SelectTrigger className="w-[130px] h-8 text-xs bg-zinc-800 border-zinc-700">
                <SelectValue placeholder="Action" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Actions</SelectItem>
                <SelectItem value="create">Create</SelectItem>
                <SelectItem value="update">Update</SelectItem>
                <SelectItem value="delete">Delete</SelectItem>
              </SelectContent>
            </Select>
            <Select value={auditStoreFilter || "all"} onValueChange={(v) => setAuditStoreFilter(v === "all" ? "" : v)}>
              <SelectTrigger className="w-[130px] h-8 text-xs bg-zinc-800 border-zinc-700">
                <SelectValue placeholder="Store" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Stores</SelectItem>
                <SelectItem value="mongodb">MongoDB</SelectItem>
                <SelectItem value="postgresql">PostgreSQL</SelectItem>
                <SelectItem value="redis">Redis</SelectItem>
              </SelectContent>
            </Select>
            <Input
              placeholder="Collection/Table..."
              value={auditCollFilter}
              onChange={(e) => setAuditCollFilter(e.target.value)}
              className="h-8 text-xs bg-zinc-800 border-zinc-700 max-w-[180px]"
            />
          </div>
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="pt-4">
              {!auditLog ? (
                <SectionLoading />
              ) : auditLog.entries?.length === 0 ? (
                <p className="text-center text-zinc-500 text-sm py-8">No audit log entries yet</p>
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Time</TableHead>
                        <TableHead className="text-xs">Action</TableHead>
                        <TableHead className="text-xs">Store</TableHead>
                        <TableHead className="text-xs">Collection/Table</TableHead>
                        <TableHead className="text-xs">Record ID</TableHead>
                        <TableHead className="text-xs">Initiator</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {auditLog.entries.map((entry, i) => (
                        <TableRow key={i}>
                          <TableCell className="text-xs text-zinc-400 whitespace-nowrap">{entry.timestamp}</TableCell>
                          <TableCell className="text-xs">
                            <Badge
                              variant="outline"
                              className={`text-[10px] ${
                                entry.action === "delete"
                                  ? "border-red-500/30 text-red-400"
                                  : entry.action === "create"
                                  ? "border-emerald-500/30 text-emerald-400"
                                  : "border-blue-500/30 text-blue-400"
                              }`}
                            >
                              {entry.action}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs font-mono">{entry.store}</TableCell>
                          <TableCell className="text-xs font-mono">{entry.collection_or_table}</TableCell>
                          <TableCell className="text-xs font-mono">{entry.record_id}</TableCell>
                          <TableCell className="text-xs text-zinc-500">{entry.initiator}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <Pagination
                    page={auditLog.page}
                    totalPages={auditLog.total_pages}
                    onPageChange={(p) => {
                      const filters = {};
                      if (auditActionFilter) filters.action = auditActionFilter;
                      if (auditStoreFilter) filters.store = auditStoreFilter;
                      if (auditCollFilter) filters.collection_or_table = auditCollFilter;
                      loadAuditLog(p, filters);
                    }}
                  />
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ============================================================
//  Settings Tab
// ============================================================

function SettingsTab({ settings, onUpdate }) {
  const [localSettings, setLocalSettings] = useState(settings || {});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (settings) setLocalSettings(settings);
  }, [settings]);

  const saveSettings = async () => {
    setSaving(true);
    try {
      const res = await updateDatabaseSettings(localSettings);
      onUpdate(res.data);
      toast.success("Settings saved");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const thresholds = localSettings.alert_thresholds || {};

  return (
    <div className="mt-4 space-y-4 max-w-2xl">
      {/* General */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">General Settings</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm">Safe Mode</Label>
              <p className="text-xs text-zinc-500">Require confirmation for destructive actions</p>
            </div>
            <Switch
              checked={localSettings.safe_mode ?? true}
              onCheckedChange={(v) => setLocalSettings((s) => ({ ...s, safe_mode: v }))}
            />
          </div>
          <Separator className="bg-zinc-800" />
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm">Auto-Refresh Interval</Label>
              <p className="text-xs text-zinc-500">Dashboard data refresh interval (seconds)</p>
            </div>
            <Input
              type="number"
              min={15}
              max={300}
              value={localSettings.auto_refresh_interval || 30}
              onChange={(e) => setLocalSettings((s) => ({ ...s, auto_refresh_interval: parseInt(e.target.value) || 30 }))}
              className="w-20 h-8 text-xs bg-zinc-800 border-zinc-700 text-center"
            />
          </div>
          <Separator className="bg-zinc-800" />
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm">Default Page Size</Label>
              <p className="text-xs text-zinc-500">Number of rows/documents per page</p>
            </div>
            <Input
              type="number"
              min={10}
              max={100}
              value={localSettings.default_page_size || 25}
              onChange={(e) => setLocalSettings((s) => ({ ...s, default_page_size: parseInt(e.target.value) || 25 }))}
              className="w-20 h-8 text-xs bg-zinc-800 border-zinc-700 text-center"
            />
          </div>
        </CardContent>
      </Card>

      {/* Alert Thresholds */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-yellow-400" />
            Alert Thresholds
          </CardTitle>
          <p className="text-xs text-zinc-500">Set limits to receive warnings when exceeded</p>
        </CardHeader>
        <CardContent className="space-y-3">
          <ThresholdRow
            label="MongoDB Data Size (GB)"
            value={thresholds.mongo_size_warn_gb}
            onChange={(v) =>
              setLocalSettings((s) => ({
                ...s,
                alert_thresholds: { ...s.alert_thresholds, mongo_size_warn_gb: v },
              }))
            }
          />
          <ThresholdRow
            label="PostgreSQL Data Size (GB)"
            value={thresholds.pg_size_warn_gb}
            onChange={(v) =>
              setLocalSettings((s) => ({
                ...s,
                alert_thresholds: { ...s.alert_thresholds, pg_size_warn_gb: v },
              }))
            }
          />
          <ThresholdRow
            label="Redis Memory (MB)"
            value={thresholds.redis_memory_warn_mb}
            onChange={(v) =>
              setLocalSettings((s) => ({
                ...s,
                alert_thresholds: { ...s.alert_thresholds, redis_memory_warn_mb: v },
              }))
            }
          />
          <ThresholdRow
            label="Connection Pool Usage (%)"
            value={thresholds.connection_pool_warn_pct}
            onChange={(v) =>
              setLocalSettings((s) => ({
                ...s,
                alert_thresholds: { ...s.alert_thresholds, connection_pool_warn_pct: v },
              }))
            }
          />
          <ThresholdRow
            label="Error Rate (per hour)"
            value={thresholds.error_rate_warn_per_hour}
            onChange={(v) =>
              setLocalSettings((s) => ({
                ...s,
                alert_thresholds: { ...s.alert_thresholds, error_rate_warn_per_hour: v },
              }))
            }
          />
        </CardContent>
      </Card>

      {/* Save */}
      <Button onClick={saveSettings} disabled={saving} className="w-full">
        {saving ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-2" />}
        Save Settings
      </Button>
    </div>
  );
}

function ThresholdRow({ label, value, onChange }) {
  return (
    <div className="flex items-center justify-between">
      <Label className="text-xs text-zinc-400">{label}</Label>
      <Input
        type="number"
        min={0}
        step="any"
        value={value ?? ""}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        className="w-24 h-7 text-xs bg-zinc-800 border-zinc-700 text-center"
      />
    </div>
  );
}

// ============================================================
//  Storage Chart (for Overview)
// ============================================================

function StorageChart({ mongodb, postgresql }) {
  const chartData = [];

  // MongoDB collections
  if (mongodb?.collections) {
    Object.entries(mongodb.collections).forEach(([name, info]) => {
      chartData.push({ name, documents: info.documents || 0, type: "MongoDB" });
    });
  }

  // PostgreSQL tables
  if (postgresql?.tables) {
    Object.entries(postgresql.tables).forEach(([name, info]) => {
      chartData.push({ name, documents: info.rows || 0, type: "PostgreSQL" });
    });
  }

  if (chartData.length === 0) {
    return <p className="text-xs text-zinc-500 text-center py-4">No storage data available</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
        <XAxis
          dataKey="name"
          tick={{ fontSize: 9, fill: "#71717A" }}
          angle={-30}
          textAnchor="end"
          height={60}
        />
        <YAxis tick={{ fontSize: 10, fill: "#71717A" }} />
        <Tooltip
          contentStyle={{ background: "#18181B", border: "1px solid #27272A", borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: "#A1A1AA" }}
          formatter={(value, name) => [value.toLocaleString(), "Documents/Rows"]}
        />
        <Bar dataKey="documents" fill="#3B82F6" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

// ============================================================
//  Data Management Tab (CRUD for Watchlist, Portfolio, Alerts)
// ============================================================

const WATCHLIST_FIELDS = [
  { key: "symbol", label: "Symbol", editable: false, required: true },
  { key: "name", label: "Name", editable: true },
  { key: "target_price", label: "Target Price", editable: true, type: "number" },
  { key: "stop_loss", label: "Stop Loss", editable: true, type: "number" },
  { key: "notes", label: "Notes", editable: true },
];

const PORTFOLIO_FIELDS = [
  { key: "symbol", label: "Symbol", editable: false, required: true },
  { key: "name", label: "Name", editable: true },
  { key: "quantity", label: "Quantity", editable: true, type: "number" },
  { key: "avg_buy_price", label: "Avg Buy Price", editable: true, type: "number" },
  { key: "buy_date", label: "Buy Date", editable: true },
  { key: "sector", label: "Sector", editable: true },
];

const ALERT_FIELDS = [
  { key: "symbol", label: "Symbol", editable: false, required: true },
  { key: "alert_type", label: "Type", editable: true },
  { key: "condition", label: "Condition", editable: true },
  { key: "threshold", label: "Threshold", editable: true, type: "number" },
  { key: "status", label: "Status", editable: true },
  { key: "message", label: "Message", editable: true },
];

function DataManagementTab({ safeMode }) {
  const [section, setSection] = useState("watchlist");

  return (
    <div className="mt-4 space-y-4">
      <Tabs value={section} onValueChange={setSection}>
        <TabsList className="bg-zinc-800/80 border border-zinc-700/50">
          <TabsTrigger value="watchlist">
            <List className="h-3.5 w-3.5 mr-1" />Watchlist
          </TabsTrigger>
          <TabsTrigger value="portfolio">
            <Briefcase className="h-3.5 w-3.5 mr-1" />Portfolio
          </TabsTrigger>
          <TabsTrigger value="alerts">
            <Bell className="h-3.5 w-3.5 mr-1" />Alerts
          </TabsTrigger>
        </TabsList>

        <TabsContent value="watchlist">
          <CrudSection
            title="Watchlist"
            fields={WATCHLIST_FIELDS}
            fetchFn={getWatchlist}
            addFn={addToWatchlist}
            updateFn={(symbol, updates) => updateWatchlistItem(symbol, updates)}
            deleteFn={(symbol) => removeFromWatchlist(symbol)}
            idField="symbol"
            safeMode={safeMode}
            dataExtractor={(res) => res.data.watchlist || res.data || []}
          />
        </TabsContent>
        <TabsContent value="portfolio">
          <CrudSection
            title="Portfolio"
            fields={PORTFOLIO_FIELDS}
            fetchFn={getPortfolio}
            addFn={addToPortfolio}
            updateFn={(symbol, updates) => updatePortfolioHolding(symbol, updates)}
            deleteFn={(symbol) => removeFromPortfolio(symbol)}
            idField="symbol"
            safeMode={safeMode}
            dataExtractor={(res) => res.data.portfolio || res.data.holdings || res.data || []}
          />
        </TabsContent>
        <TabsContent value="alerts">
          <CrudSection
            title="Alerts"
            fields={ALERT_FIELDS}
            fetchFn={() => getAlerts()}
            addFn={createAlert}
            updateFn={(id, updates) => updateAlert(id, updates)}
            deleteFn={(id) => deleteAlert(id)}
            idField="alert_id"
            altIdField="id"
            safeMode={safeMode}
            dataExtractor={(res) => res.data.alerts || res.data || []}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ============================================================
//  CRUD Section (reusable for Watchlist, Portfolio, Alerts)
// ============================================================

function CrudSection({ title, fields, fetchFn, addFn, updateFn, deleteFn, idField, altIdField, safeMode, dataExtractor }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingRow, setEditingRow] = useState(null); // index of row being edited
  const [editValues, setEditValues] = useState({});
  const [addDialog, setAddDialog] = useState(false);
  const [addValues, setAddValues] = useState({});
  const [deleteDialog, setDeleteDialog] = useState(null);
  const [saving, setSaving] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  const fetchData = useCallback(async () => {
    try {
      const res = await fetchFn();
      const data = dataExtractor(res);
      setItems(Array.isArray(data) ? data : []);
    } catch {
      toast.error(`Failed to load ${title}`);
    } finally {
      setLoading(false);
    }
  }, [fetchFn, dataExtractor, title]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const getItemId = (item) => item[idField] || (altIdField && item[altIdField]);

  const collectionName = title.toLowerCase();

  const handleAdd = async () => {
    setSaving(true);
    try {
      await addFn(addValues);
      toast.success(`${title} item added`);
      writeAuditLog({
        action: "create", store: "mongodb", collection_or_table: collectionName,
        record_id: addValues[idField] || addValues.symbol || "new",
        new_value: addValues,
      }).catch(() => {});
      setAddDialog(false);
      setAddValues({});
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || `Failed to add to ${title}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveEdit = async (item, idx) => {
    setSaving(true);
    try {
      const id = getItemId(item);
      const updates = { ...editValues };
      // Convert numeric fields
      fields.forEach((f) => {
        if (f.type === "number" && updates[f.key] !== undefined) {
          updates[f.key] = Number(updates[f.key]);
        }
      });
      await updateFn(id, updates);
      toast.success("Updated successfully");
      writeAuditLog({
        action: "update", store: "mongodb", collection_or_table: collectionName,
        record_id: String(id), new_value: updates,
      }).catch(() => {});
      setEditingRow(null);
      setEditValues({});
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Update failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteDialog) return;
    setSaving(true);
    try {
      const id = getItemId(deleteDialog);
      await deleteFn(id);
      toast.success("Deleted successfully");
      writeAuditLog({
        action: "delete", store: "mongodb", collection_or_table: collectionName,
        record_id: String(id), previous_value: deleteDialog,
      }).catch(() => {});
      setDeleteDialog(null);
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Delete failed");
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (idx, item) => {
    setEditingRow(idx);
    const vals = {};
    fields.filter((f) => f.editable).forEach((f) => {
      vals[f.key] = item[f.key] ?? "";
    });
    setEditValues(vals);
  };

  const filteredItems = items.filter((item) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return fields.some((f) => String(item[f.key] ?? "").toLowerCase().includes(term));
  });

  if (loading) return <SectionLoading />;

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2">
        <Input
          placeholder={`Search ${title}...`}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="h-8 text-xs bg-zinc-800 border-zinc-700 max-w-[250px]"
        />
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={fetchData}>
            <RefreshCw className="h-3.5 w-3.5 mr-1" />Refresh
          </Button>
          <Button size="sm" onClick={() => setAddDialog(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" />Add
          </Button>
        </div>
      </div>

      {/* Items table */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="pt-4">
          {filteredItems.length === 0 ? (
            <div className="flex flex-col items-center py-8 text-zinc-500">
              <Database className="h-6 w-6 mb-2" />
              <p className="text-sm">No {title.toLowerCase()} items found</p>
            </div>
          ) : (
            <ScrollArea className="max-h-[600px]">
              <Table>
                <TableHeader>
                  <TableRow>
                    {fields.map((f) => (
                      <TableHead key={f.key} className="text-xs whitespace-nowrap">{f.label}</TableHead>
                    ))}
                    <TableHead className="text-xs w-[100px]">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredItems.map((item, idx) => (
                    <TableRow key={getItemId(item) || idx}>
                      {fields.map((f) => (
                        <TableCell key={f.key} className="text-xs py-1.5">
                          {editingRow === idx && f.editable ? (
                            <Input
                              type={f.type || "text"}
                              value={editValues[f.key] ?? ""}
                              onChange={(e) => setEditValues((v) => ({ ...v, [f.key]: e.target.value }))}
                              className="h-7 text-xs bg-zinc-800 border-zinc-600 w-full min-w-[80px]"
                            />
                          ) : (
                            <span className="font-mono text-zinc-300">
                              {item[f.key] != null ? String(item[f.key]).substring(0, 50) : <span className="text-zinc-600">-</span>}
                            </span>
                          )}
                        </TableCell>
                      ))}
                      <TableCell className="text-xs py-1.5">
                        <div className="flex gap-1">
                          {editingRow === idx ? (
                            <>
                              <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => handleSaveEdit(item, idx)} disabled={saving}>
                                <Save className="h-3.5 w-3.5 text-emerald-400" />
                              </Button>
                              <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => { setEditingRow(null); setEditValues({}); }}>
                                <X className="h-3.5 w-3.5 text-zinc-400" />
                              </Button>
                            </>
                          ) : (
                            <>
                              <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => startEdit(idx, item)}>
                                <Edit3 className="h-3.5 w-3.5 text-blue-400" />
                              </Button>
                              <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setDeleteDialog(item)}>
                                <Trash2 className="h-3.5 w-3.5 text-red-400" />
                              </Button>
                            </>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </ScrollArea>
          )}
          <div className="text-xs text-zinc-500 mt-2">{filteredItems.length} items</div>
        </CardContent>
      </Card>

      {/* Add dialog */}
      <Dialog open={addDialog} onOpenChange={setAddDialog}>
        <DialogContent className="bg-zinc-900 border-zinc-800">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Plus className="h-4 w-4 text-blue-400" /> Add to {title}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {fields.map((f) => (
              <div key={f.key}>
                <Label className="text-xs text-zinc-400">{f.label}{f.required && " *"}</Label>
                <Input
                  type={f.type || "text"}
                  value={addValues[f.key] ?? ""}
                  onChange={(e) => setAddValues((v) => ({ ...v, [f.key]: e.target.value }))}
                  className="h-8 text-xs bg-zinc-800 border-zinc-700 mt-1"
                  placeholder={f.label}
                />
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddDialog(false)}>Cancel</Button>
            <Button onClick={handleAdd} disabled={saving}>
              {saving ? <RefreshCw className="h-4 w-4 mr-1 animate-spin" /> : <Plus className="h-4 w-4 mr-1" />}
              Add
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete dialog */}
      <Dialog open={!!deleteDialog} onOpenChange={() => setDeleteDialog(null)}>
        <DialogContent className="bg-zinc-900 border-zinc-800">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-400">
              <Trash2 className="h-4 w-4" /> Confirm Delete
            </DialogTitle>
            <DialogDescription>
              {safeMode && (
                <span className="text-yellow-400 text-xs flex items-center gap-1 mb-2">
                  <Shield className="h-3 w-3" /> Safe Mode is ON
                </span>
              )}
              <span className="block mt-1">
                Delete <span className="font-mono text-zinc-300">{deleteDialog && getItemId(deleteDialog)}</span> from {title}?
              </span>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialog(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete} disabled={saving}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ============================================================
//  Query Playground Tab
// ============================================================

function QueryPlaygroundTab() {
  const [queryType, setQueryType] = useState("mongodb");
  // MongoDB
  const [mongoCollection, setMongoCollection] = useState("");
  const [mongoQuery, setMongoQuery] = useState("{}");
  const [mongoLimit, setMongoLimit] = useState(50);
  // PostgreSQL
  const [pgSql, setPgSql] = useState("SELECT * FROM prices_daily LIMIT 10");
  const [pgLimit, setPgLimit] = useState(50);
  // Results
  const [results, setResults] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [collections, setCollections] = useState([]);

  useEffect(() => {
    getMongoCollections()
      .then((r) => setCollections(r.data.collections || []))
      .catch(() => {});
  }, []);

  const runQuery = async () => {
    setRunning(true);
    setError(null);
    setResults(null);
    try {
      if (queryType === "mongodb") {
        let parsed;
        try {
          parsed = JSON.parse(mongoQuery);
        } catch {
          setError("Invalid JSON query");
          setRunning(false);
          return;
        }
        const r = await executeMongoQuery(mongoCollection, parsed, mongoLimit);
        setResults(r.data);
      } else {
        const r = await executePgQuery(pgSql, pgLimit);
        setResults(r.data);
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Query execution failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="mt-4 space-y-4">
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Terminal className="h-4 w-4 text-purple-400" />
            Query Playground
            <Badge variant="outline" className="text-[10px] border-yellow-500/30 text-yellow-400">Read-Only</Badge>
          </CardTitle>
          <p className="text-xs text-zinc-500">Execute read-only queries against your databases</p>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Database selector */}
          <Tabs value={queryType} onValueChange={setQueryType}>
            <TabsList className="bg-zinc-800/80 border border-zinc-700/50">
              <TabsTrigger value="mongodb"><Database className="h-3.5 w-3.5 mr-1" />MongoDB</TabsTrigger>
              <TabsTrigger value="postgresql"><HardDrive className="h-3.5 w-3.5 mr-1" />PostgreSQL</TabsTrigger>
            </TabsList>

            <TabsContent value="mongodb" className="space-y-3 mt-3">
              <div className="flex gap-2">
                <Select value={mongoCollection} onValueChange={setMongoCollection}>
                  <SelectTrigger className="w-[200px] h-8 text-xs bg-zinc-800 border-zinc-700">
                    <SelectValue placeholder="Select collection" />
                  </SelectTrigger>
                  <SelectContent>
                    {collections.map((c) => (
                      <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  type="number"
                  min={1}
                  max={200}
                  value={mongoLimit}
                  onChange={(e) => setMongoLimit(parseInt(e.target.value) || 50)}
                  className="w-20 h-8 text-xs bg-zinc-800 border-zinc-700"
                  placeholder="Limit"
                />
              </div>
              <textarea
                value={mongoQuery}
                onChange={(e) => setMongoQuery(e.target.value)}
                className="w-full h-28 bg-zinc-800 border border-zinc-700 rounded-md p-3 text-xs font-mono text-zinc-300 resize-y focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder='{"symbol": "RELIANCE"}'
              />
              <p className="text-[10px] text-zinc-600">
                MongoDB find() query as JSON. Only read operations allowed. Write operators ($set, $delete, etc.) are blocked.
              </p>
            </TabsContent>

            <TabsContent value="postgresql" className="space-y-3 mt-3">
              <div className="flex gap-2">
                <Input
                  type="number"
                  min={1}
                  max={200}
                  value={pgLimit}
                  onChange={(e) => setPgLimit(parseInt(e.target.value) || 50)}
                  className="w-20 h-8 text-xs bg-zinc-800 border-zinc-700"
                  placeholder="Limit"
                />
              </div>
              <textarea
                value={pgSql}
                onChange={(e) => setPgSql(e.target.value)}
                className="w-full h-28 bg-zinc-800 border border-zinc-700 rounded-md p-3 text-xs font-mono text-zinc-300 resize-y focus:outline-none focus:ring-1 focus:ring-emerald-500"
                placeholder="SELECT * FROM prices_daily WHERE symbol = 'RELIANCE' LIMIT 10"
              />
              <p className="text-[10px] text-zinc-600">
                Only SELECT statements allowed. Queries run in a read-only transaction.
              </p>
            </TabsContent>
          </Tabs>

          <Button onClick={runQuery} disabled={running || (queryType === "mongodb" && !mongoCollection)} size="sm">
            {running ? <RefreshCw className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Play className="h-3.5 w-3.5 mr-1" />}
            Run Query
          </Button>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-xs text-red-400">
          <div className="flex items-center gap-2 font-medium"><XCircle className="h-3.5 w-3.5" /> Error</div>
          <p className="mt-1 font-mono">{error}</p>
        </div>
      )}

      {/* Results */}
      {results && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center justify-between">
              <span>Results</span>
              <span className="text-xs text-zinc-500 font-normal">
                {results.count ?? results.documents?.length ?? 0} documents
                {results.execution_time_ms && ` | ${results.execution_time_ms}ms`}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {(results.documents || results.rows || []).length === 0 ? (
              <p className="text-xs text-zinc-500 text-center py-4">No results</p>
            ) : (
              <ScrollArea className="max-h-[500px]">
                <div className="space-y-2">
                  {(results.documents || results.rows || []).map((doc, i) => (
                    <pre key={i} className="bg-zinc-800/70 rounded p-3 text-xs font-mono text-zinc-300 whitespace-pre-wrap break-all max-h-40 overflow-auto">
                      {JSON.stringify(doc, null, 2)}
                    </pre>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ============================================================
//  Tools Tab (Backup, Size History, Collection Comparison)
// ============================================================

function ToolsTab() {
  const [toolSection, setToolSection] = useState("backup");

  return (
    <div className="mt-4 space-y-4">
      <Tabs value={toolSection} onValueChange={setToolSection}>
        <TabsList className="bg-zinc-800/80 border border-zinc-700/50">
          <TabsTrigger value="backup"><Archive className="h-3.5 w-3.5 mr-1" />Backup</TabsTrigger>
          <TabsTrigger value="size-history"><BarChart3 className="h-3.5 w-3.5 mr-1" />Size History</TabsTrigger>
          <TabsTrigger value="compare"><GitCompare className="h-3.5 w-3.5 mr-1" />Compare</TabsTrigger>
          <TabsTrigger value="export"><Download className="h-3.5 w-3.5 mr-1" />Export</TabsTrigger>
        </TabsList>

        <TabsContent value="backup"><BackupTool /></TabsContent>
        <TabsContent value="size-history"><SizeHistoryTool /></TabsContent>
        <TabsContent value="compare"><ComparisonTool /></TabsContent>
        <TabsContent value="export"><ExportTool /></TabsContent>
      </Tabs>
    </div>
  );
}

function BackupTool() {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);

  const handleBackup = async () => {
    if (!window.confirm("Trigger a MongoDB backup now?")) return;
    setRunning(true);
    setResult(null);
    try {
      const r = await triggerBackup();
      setResult(r.data);
      toast.success("Backup completed");
    } catch (err) {
      setResult({ status: "error", error: err.response?.data?.detail || "Backup failed" });
      toast.error("Backup failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card className="bg-zinc-900/50 border-zinc-800 mt-3">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Archive className="h-4 w-4 text-orange-400" />
          Database Backup
        </CardTitle>
        <p className="text-xs text-zinc-500">Trigger a MongoDB backup using the backup script</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button onClick={handleBackup} disabled={running} size="sm">
          {running ? <RefreshCw className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Archive className="h-3.5 w-3.5 mr-1" />}
          {running ? "Running Backup..." : "Trigger Backup"}
        </Button>
        {result && (
          <div className={`rounded-lg p-3 text-xs ${result.status === "error" ? "bg-red-500/10 border border-red-500/30" : "bg-emerald-500/10 border border-emerald-500/30"}`}>
            <div className="flex items-center gap-2 font-medium mb-1">
              {result.status === "error" ? (
                <><XCircle className="h-3.5 w-3.5 text-red-400" /><span className="text-red-400">Failed</span></>
              ) : (
                <><CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /><span className="text-emerald-400">Success</span></>
              )}
            </div>
            {result.error && <p className="text-red-300 font-mono">{result.error}</p>}
            {result.output && <pre className="text-zinc-300 font-mono whitespace-pre-wrap max-h-40 overflow-auto">{result.output}</pre>}
            {result.backup_path && <p className="text-zinc-400 mt-1">Path: <span className="font-mono">{result.backup_path}</span></p>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SizeHistoryTool() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const r = await getSizeHistory(days);
      setData(r.data || []);
    } catch {
      toast.error("Failed to load size history");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  const handleRecordSnapshot = async () => {
    try {
      await recordSizeSnapshot();
      toast.success("Size snapshot recorded");
      fetchHistory();
    } catch {
      toast.error("Failed to record snapshot");
    }
  };

  return (
    <Card className="bg-zinc-900/50 border-zinc-800 mt-3">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-cyan-400" />
          Storage Size History
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2 items-center">
          <Select value={String(days)} onValueChange={(v) => setDays(parseInt(v))}>
            <SelectTrigger className="w-[130px] h-8 text-xs bg-zinc-800 border-zinc-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Last 7 Days</SelectItem>
              <SelectItem value="30">Last 30 Days</SelectItem>
              <SelectItem value="90">Last 90 Days</SelectItem>
            </SelectContent>
          </Select>
          <Button size="sm" variant="outline" onClick={handleRecordSnapshot}>
            <Plus className="h-3.5 w-3.5 mr-1" />Record Snapshot
          </Button>
        </div>

        {loading ? (
          <SectionLoading />
        ) : data.length === 0 ? (
          <p className="text-xs text-zinc-500 text-center py-8">No size history data yet. Click "Record Snapshot" to start tracking.</p>
        ) : (
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#71717A" }} tickFormatter={(v) => v.slice(5)} />
              <YAxis tick={{ fontSize: 10, fill: "#71717A" }} />
              <Tooltip
                contentStyle={{ background: "#18181B", border: "1px solid #27272A", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#A1A1AA" }}
              />
              <Line type="monotone" dataKey="mongo_docs" stroke="#3B82F6" name="MongoDB Docs" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="pg_rows" stroke="#10B981" name="PG Rows" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}

function ComparisonTool() {
  const [colA, setColA] = useState("");
  const [colB, setColB] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [collections, setCollections] = useState([]);

  useEffect(() => {
    getMongoCollections()
      .then((r) => setCollections(r.data.collections || []))
      .catch(() => {});
  }, []);

  const handleCompare = async () => {
    if (!colA || !colB) { toast.error("Select two collections"); return; }
    setLoading(true);
    setResult(null);
    try {
      const r = await compareCollections(colA, colB);
      setResult(r.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Comparison failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="bg-zinc-900/50 border-zinc-800 mt-3">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <GitCompare className="h-4 w-4 text-violet-400" />
          Collection Comparison
        </CardTitle>
        <p className="text-xs text-zinc-500">Compare schema and stats of two MongoDB collections</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2 items-center flex-wrap">
          <Select value={colA} onValueChange={setColA}>
            <SelectTrigger className="w-[180px] h-8 text-xs bg-zinc-800 border-zinc-700">
              <SelectValue placeholder="Collection A" />
            </SelectTrigger>
            <SelectContent>
              {collections.map((c) => (
                <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-xs text-zinc-500">vs</span>
          <Select value={colB} onValueChange={setColB}>
            <SelectTrigger className="w-[180px] h-8 text-xs bg-zinc-800 border-zinc-700">
              <SelectValue placeholder="Collection B" />
            </SelectTrigger>
            <SelectContent>
              {collections.map((c) => (
                <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size="sm" onClick={handleCompare} disabled={loading || !colA || !colB}>
            {loading ? <RefreshCw className="h-3.5 w-3.5 mr-1 animate-spin" /> : <GitCompare className="h-3.5 w-3.5 mr-1" />}
            Compare
          </Button>
        </div>

        {result && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
            {[result.a, result.b].map((col, i) => (
              <div key={i} className="bg-zinc-800/50 rounded-lg p-3 border border-zinc-700/50">
                <h4 className="text-xs font-medium text-zinc-300 mb-2 font-mono">{col?.name || (i === 0 ? colA : colB)}</h4>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between"><span className="text-zinc-500">Documents</span><span className="font-mono">{col?.document_count?.toLocaleString()}</span></div>
                  <div className="flex justify-between"><span className="text-zinc-500">Fields</span><span className="font-mono">{col?.field_count}</span></div>
                </div>
                {col?.fields && (
                  <div className="mt-2 space-y-0.5">
                    {Object.entries(col.fields).map(([field, types]) => (
                      <div key={field} className="text-[10px] flex justify-between">
                        <span className="font-mono text-zinc-400">{field}</span>
                        <span className="text-zinc-600">{Array.isArray(types) ? types.join(", ") : types}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {result.common_fields && (
              <div className="md:col-span-2 bg-zinc-800/30 rounded-lg p-3 border border-zinc-700/30">
                <h4 className="text-xs font-medium text-zinc-400 mb-1">Common Fields: {result.common_fields.length}</h4>
                <div className="flex flex-wrap gap-1">
                  {result.common_fields.map((f) => (
                    <Badge key={f} variant="outline" className="text-[10px]">{f}</Badge>
                  ))}
                </div>
                {result.unique_to_a?.length > 0 && (
                  <div className="mt-2">
                    <span className="text-[10px] text-zinc-500">Only in {colA}: </span>
                    {result.unique_to_a.map((f) => (
                      <Badge key={f} variant="outline" className="text-[10px] border-blue-500/30 text-blue-400 ml-1">{f}</Badge>
                    ))}
                  </div>
                )}
                {result.unique_to_b?.length > 0 && (
                  <div className="mt-1">
                    <span className="text-[10px] text-zinc-500">Only in {colB}: </span>
                    {result.unique_to_b.map((f) => (
                      <Badge key={f} variant="outline" className="text-[10px] border-emerald-500/30 text-emerald-400 ml-1">{f}</Badge>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ExportTool() {
  const [exportType, setExportType] = useState("mongodb");
  const [target, setTarget] = useState("");
  const [format, setFormat] = useState("json");
  const [limit, setLimit] = useState(5000);
  const [exporting, setExporting] = useState(false);
  const [collections, setCollections] = useState([]);
  const [tables, setTables] = useState([]);

  useEffect(() => {
    getMongoCollections().then((r) => setCollections(r.data.collections || [])).catch(() => {});
    getPgTables().then((r) => setTables(r.data.tables || [])).catch(() => {});
  }, []);

  const handleExport = async () => {
    if (!target) { toast.error("Select a target"); return; }
    setExporting(true);
    try {
      const r = exportType === "mongodb"
        ? await exportCollection(target, format, limit)
        : await exportTable(target, format, limit);

      const data = r.data;
      let content, mimeType, ext;

      if (format === "csv") {
        const headers = (data.headers || []).join(",");
        const rows = (data.rows || []).map((row) => row.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(","));
        content = [headers, ...rows].join("\n");
        mimeType = "text/csv";
        ext = "csv";
      } else {
        content = JSON.stringify(data.documents || data, null, 2);
        mimeType = "application/json";
        ext = "json";
      }

      const blob = new Blob([content], { type: mimeType });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${target}_export.${ext}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      toast.success(`Exported ${target} as ${format.toUpperCase()}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Export failed");
    } finally {
      setExporting(false);
    }
  };

  return (
    <Card className="bg-zinc-900/50 border-zinc-800 mt-3">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Download className="h-4 w-4 text-blue-400" />
          Export Data
        </CardTitle>
        <p className="text-xs text-zinc-500">Export collection or table data as JSON or CSV</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2 flex-wrap items-center">
          <Select value={exportType} onValueChange={(v) => { setExportType(v); setTarget(""); }}>
            <SelectTrigger className="w-[140px] h-8 text-xs bg-zinc-800 border-zinc-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="mongodb">MongoDB</SelectItem>
              <SelectItem value="postgresql">PostgreSQL</SelectItem>
            </SelectContent>
          </Select>
          <Select value={target} onValueChange={setTarget}>
            <SelectTrigger className="w-[200px] h-8 text-xs bg-zinc-800 border-zinc-700">
              <SelectValue placeholder="Select target" />
            </SelectTrigger>
            <SelectContent>
              {(exportType === "mongodb" ? collections : tables).map((item) => (
                <SelectItem key={item.name} value={item.name}>{item.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={format} onValueChange={setFormat}>
            <SelectTrigger className="w-[100px] h-8 text-xs bg-zinc-800 border-zinc-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="json">JSON</SelectItem>
              <SelectItem value="csv">CSV</SelectItem>
            </SelectContent>
          </Select>
          <Input
            type="number"
            min={1}
            max={10000}
            value={limit}
            onChange={(e) => setLimit(parseInt(e.target.value) || 5000)}
            className="w-24 h-8 text-xs bg-zinc-800 border-zinc-700"
            placeholder="Limit"
          />
          <Button size="sm" onClick={handleExport} disabled={exporting || !target}>
            {exporting ? <RefreshCw className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Download className="h-3.5 w-3.5 mr-1" />}
            Export
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ============================================================
//  Help Panel
// ============================================================

function HelpPanel({ open, onClose }) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="bg-zinc-900 border-zinc-800 max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <HelpCircle className="h-5 w-5 text-blue-400" />
            Database Dashboard Help
          </DialogTitle>
          <DialogDescription>Quick reference for all dashboard features</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 text-xs text-zinc-300">
          <HelpSection title="Overview Tab" icon={Layers}>
            Displays storage summary across MongoDB, PostgreSQL, and Redis. Shows collection/table sizes,
            data flow pipeline stages, and connection details. Storage chart visualizes document/row counts.
          </HelpSection>
          <HelpSection title="Data Management" icon={Edit3}>
            Full CRUD operations for Watchlist, Portfolio, and Alerts. Click the Edit icon to inline-edit
            a row, or use the Add button to create new entries. Audit logging is automatic for all changes.
          </HelpSection>
          <HelpSection title="MongoDB / PostgreSQL" icon={Database}>
            Browse collections and tables. View sample data (paginated) or inferred schema with indexes.
            Delete individual documents from deletable collections (hover to reveal delete button).
          </HelpSection>
          <HelpSection title="Redis" icon={Zap}>
            View all cache keys grouped by prefix. See cache hit/miss stats. Use Flush Cache to clear
            all entries (requires confirmation).
          </HelpSection>
          <HelpSection title="Activity Tab" icon={Activity}>
            Recent database activity, errors with trend chart, and full audit log. Filter by date range
            (24h/7d/30d), collection, and status. Audit log supports action/store/collection filters.
          </HelpSection>
          <HelpSection title="Query Playground" icon={Terminal}>
            Execute read-only queries. MongoDB: JSON find queries on any collection. PostgreSQL: SELECT-only
            SQL statements. All queries run in read-only mode for safety.
          </HelpSection>
          <HelpSection title="Tools" icon={Archive}>
            <strong>Backup:</strong> Trigger MongoDB backup on demand.{" "}
            <strong>Size History:</strong> Track storage growth over time with daily snapshots.{" "}
            <strong>Compare:</strong> Side-by-side schema comparison of two collections.{" "}
            <strong>Export:</strong> Download data as JSON or CSV.
          </HelpSection>
          <HelpSection title="Settings" icon={Settings}>
            Configure Safe Mode (confirmation for destructive ops), auto-refresh interval, page size,
            and alert thresholds for storage, memory, connection pool, and error rate.
          </HelpSection>
          <Separator className="bg-zinc-800" />
          <div className="text-zinc-500">
            <strong className="text-zinc-400">Safe Mode:</strong> When enabled, destructive actions (delete, flush, backup) require
            explicit confirmation. Toggle via the shield icon in the header.
          </div>
          <div className="text-zinc-500">
            <strong className="text-zinc-400">WebSocket:</strong> The green dot in the header indicates a live WebSocket connection
            pushing real-time error counts and threshold alerts every 10 seconds.
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function HelpSection({ title, icon: Icon, children }) {
  return (
    <div>
      <h4 className="text-sm font-medium text-zinc-200 flex items-center gap-2 mb-1">
        <Icon className="h-3.5 w-3.5 text-blue-400" />
        {title}
      </h4>
      <p className="text-zinc-400 ml-5">{children}</p>
    </div>
  );
}
