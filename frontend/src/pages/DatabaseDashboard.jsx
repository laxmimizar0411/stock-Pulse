import React, { useState, useEffect, useCallback } from "react";
import {
  Database, Server, HardDrive, RefreshCw, ChevronRight, Search,
  AlertTriangle, CheckCircle2, XCircle, Shield, ShieldOff, Trash2,
  Activity, Eye, Settings, FileText, ArrowUpDown, ChevronDown,
  BarChart3, Layers, Clock, Zap, Info, ExternalLink, Filter, X,
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
  getDatabaseOverview, getDatabaseHealth, getDataFlow, getThresholdAlerts,
  getMongoCollections, getCollectionSample, getCollectionSchema, deleteCollectionDocument,
  getPgTables, getTableSample, getTableSchema,
  getRedisKeys, getDatabaseActivity, getDatabaseErrors,
  getDatabaseSettings, updateDatabaseSettings,
  getAuditLog, getCacheStats, flushCache,
} from "../lib/api";
import { toast } from "sonner";

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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold font-heading tracking-tight flex items-center gap-2">
            <Database className="h-6 w-6 text-blue-500" />
            Database Dashboard
          </h1>
          <p className="text-sm text-zinc-400 mt-1">
            Complete database visibility, monitoring, and management
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-xs text-zinc-500">
              Updated {lastRefresh.toLocaleTimeString()}
            </span>
          )}
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
        <TabsList className="bg-zinc-800/80 border border-zinc-700/50">
          <TabsTrigger value="overview"><Layers className="h-3.5 w-3.5 mr-1" />Overview</TabsTrigger>
          <TabsTrigger value="mongodb"><Database className="h-3.5 w-3.5 mr-1" />MongoDB</TabsTrigger>
          <TabsTrigger value="postgresql"><HardDrive className="h-3.5 w-3.5 mr-1" />PostgreSQL</TabsTrigger>
          <TabsTrigger value="redis"><Zap className="h-3.5 w-3.5 mr-1" />Redis</TabsTrigger>
          <TabsTrigger value="activity"><Activity className="h-3.5 w-3.5 mr-1" />Activity</TabsTrigger>
          <TabsTrigger value="settings"><Settings className="h-3.5 w-3.5 mr-1" />Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab overview={overview} health={health} />
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
        <TabsContent value="settings">
          <SettingsTab settings={settings} onUpdate={setSettings} />
        </TabsContent>
      </Tabs>
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
                          {/* Delete button */}
                          {(doc.symbol || doc.id || doc.job_id) && (
                            <button
                              onClick={() =>
                                setDeleteDialog({
                                  collection: selected,
                                  idField: doc.symbol ? "symbol" : doc.id ? "id" : "job_id",
                                  idValue: doc.symbol || doc.id || doc.job_id,
                                  preview: JSON.stringify(doc, null, 2).substring(0, 200),
                                })
                              }
                              className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30"
                              title="Delete document"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          )}
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

function ActivityTab() {
  const [subTab, setSubTab] = useState("activity");
  const [activity, setActivity] = useState([]);
  const [errors, setErrors] = useState([]);
  const [auditLog, setAuditLog] = useState(null);
  const [auditPage, setAuditPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    Promise.all([
      getDatabaseActivity(100).then((r) => setActivity(r.data.activity || [])).catch(() => {}),
      getDatabaseErrors(50).then((r) => setErrors(r.data.errors || [])).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  const loadAuditLog = useCallback(async (page = 1) => {
    try {
      const r = await getAuditLog(page, 50);
      setAuditLog(r.data);
      setAuditPage(page);
    } catch {
      toast.error("Failed to load audit log");
    }
  }, []);

  useEffect(() => {
    if (subTab === "audit" && !auditLog) loadAuditLog(1);
  }, [subTab, auditLog, loadAuditLog]);

  if (loading) return <SectionLoading />;

  const statusColor = (s) => {
    if (!s) return "text-zinc-500";
    if (["success", "completed"].includes(s)) return "text-emerald-400";
    if (["failed", "error"].includes(s)) return "text-red-400";
    if (["running", "pending"].includes(s)) return "text-yellow-400";
    return "text-zinc-400";
  };

  const filteredActivity = activity.filter((a) =>
    a.summary?.toLowerCase().includes(searchTerm.toLowerCase())
  );
  const filteredErrors = errors.filter((e) =>
    e.message?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="mt-4 space-y-4">
      <Tabs value={subTab} onValueChange={setSubTab}>
        <div className="flex items-center justify-between">
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
                    onPageChange={(p) => loadAuditLog(p)}
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
