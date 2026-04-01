import React, { useState, useEffect, useCallback } from "react";
import {
  Brain,
  Activity,
  Database,
  Server,
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Zap,
  BarChart3,
  GitBranch,
  HardDrive,
  Radio,
  Layers,
  ChevronRight,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

function StatusBadge({ status }) {
  const styles = {
    healthy: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    ready: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    running: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    connected: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    success: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    degraded: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    stub_mode: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    local_fallback: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    stopped: "bg-red-500/20 text-red-400 border-red-500/30",
    failed: "bg-red-500/20 text-red-400 border-red-500/30",
    not_initialized: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
    pending: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  };

  const style = styles[status] || styles.not_initialized;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${style}`}>
      {status === "healthy" || status === "ready" || status === "running" || status === "connected" || status === "success" ? (
        <CheckCircle2 className="w-3 h-3" />
      ) : status === "degraded" || status === "stub_mode" || status === "local_fallback" ? (
        <AlertTriangle className="w-3 h-3" />
      ) : status === "failed" || status === "stopped" ? (
        <XCircle className="w-3 h-3" />
      ) : null}
      {status.replace(/_/g, " ").toUpperCase()}
    </span>
  );
}

function SubsystemCard({ name, icon: Icon, data, children }) {
  const status = data?.status || "not_initialized";
  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-5 hover:border-zinc-700 transition-colors">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-zinc-800">
            <Icon className="w-4 h-4 text-zinc-300" />
          </div>
          <h3 className="text-sm font-semibold text-zinc-200">{name}</h3>
        </div>
        <StatusBadge status={status} />
      </div>
      {children}
    </div>
  );
}

function MetricItem({ label, value, unit }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className="text-sm font-mono text-zinc-300">
        {value}
        {unit && <span className="text-zinc-500 ml-0.5">{unit}</span>}
      </span>
    </div>
  );
}

export default function BrainDashboard() {
  const [health, setHealth] = useState(null);
  const [batchStatus, setBatchStatus] = useState(null);
  const [batchHistory, setBatchHistory] = useState([]);
  const [featureStatus, setFeatureStatus] = useState(null);
  const [kafkaTopics, setKafkaTopics] = useState(null);
  const [phase1Summary, setPhase1Summary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [triggeringDag, setTriggeringDag] = useState(null);
  const [computingSymbol, setComputingSymbol] = useState("");
  const [computeResult, setComputeResult] = useState(null);
  const [computeLoading, setComputeLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    try {
      const [healthRes, batchRes, historyRes, featureRes, topicsRes, summaryRes] = await Promise.allSettled([
        fetch(`${API_URL}/api/brain/health`),
        fetch(`${API_URL}/api/brain/batch/status`),
        fetch(`${API_URL}/api/brain/batch/history?limit=10`),
        fetch(`${API_URL}/api/brain/features/status`),
        fetch(`${API_URL}/api/brain/kafka/topics`),
        fetch(`${API_URL}/api/brain/phase1/summary`),
      ]);

      if (healthRes.status === "fulfilled" && healthRes.value.ok) setHealth(await healthRes.value.json());
      if (batchRes.status === "fulfilled" && batchRes.value.ok) setBatchStatus(await batchRes.value.json());
      if (historyRes.status === "fulfilled" && historyRes.value.ok) {
        const data = await historyRes.value.json();
        setBatchHistory(data.history || []);
      }
      if (featureRes.status === "fulfilled" && featureRes.value.ok) setFeatureStatus(await featureRes.value.json());
      if (topicsRes.status === "fulfilled" && topicsRes.value.ok) setKafkaTopics(await topicsRes.value.json());
      if (summaryRes.status === "fulfilled" && summaryRes.value.ok) setPhase1Summary(await summaryRes.value.json());
    } catch (err) {
      console.error("Error fetching brain data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 30000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const triggerDag = async (dagName) => {
    setTriggeringDag(dagName);
    try {
      const res = await fetch(`${API_URL}/api/brain/batch/trigger/${dagName}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const data = await res.json();
      if (data.success) {
        toast.success(`DAG "${dagName}" completed successfully`);
      } else {
        toast.error(`DAG "${dagName}" failed: ${data.run?.error || "Unknown error"}`);
      }
      await fetchAll();
    } catch (err) {
      toast.error(`Error triggering DAG: ${err.message}`);
    } finally {
      setTriggeringDag(null);
    }
  };

  const computeFeatures = async () => {
    if (!computingSymbol.trim()) return;
    setComputeLoading(true);
    setComputeResult(null);
    try {
      const res = await fetch(`${API_URL}/api/brain/features/${computingSymbol.trim().toUpperCase()}?compute=true`);
      const data = await res.json();
      setComputeResult(data);
      toast.success(`Computed ${data.feature_count || 0} features for ${computingSymbol.toUpperCase()}`);
    } catch (err) {
      toast.error(`Error computing features: ${err.message}`);
    } finally {
      setComputeLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-violet-500 animate-spin" />
          <p className="text-zinc-500 text-sm">Loading Brain Dashboard...</p>
        </div>
      </div>
    );
  }

  const uptime = health?.uptime_seconds ? Math.floor(health.uptime_seconds) : 0;
  const uptimeStr = uptime > 3600 ? `${Math.floor(uptime / 3600)}h ${Math.floor((uptime % 3600) / 60)}m` : uptime > 60 ? `${Math.floor(uptime / 60)}m ${uptime % 60}s` : `${uptime}s`;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-3 rounded-xl bg-gradient-to-br from-violet-600 to-purple-700 shadow-lg shadow-violet-900/30">
            <Brain className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">Brain Dashboard</h1>
            <p className="text-sm text-zinc-500">
              Phase 1 — Data Foundation & Event Infrastructure
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900 border border-zinc-800 rounded-lg">
            <Clock className="w-3.5 h-3.5 text-zinc-500" />
            <span className="text-xs text-zinc-400">Uptime: {uptimeStr}</span>
          </div>
          <StatusBadge status={health?.status || "stopped"} />
          <button
            onClick={fetchAll}
            className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Overall Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { label: "Brain Version", value: health?.brain_version || "N/A", icon: Zap, color: "text-violet-400" },
          { label: "Features Registered", value: featureStatus?.registered_features || 0, icon: BarChart3, color: "text-emerald-400" },
          { label: "DAGs Active", value: batchStatus?.enabled_dags || 0, icon: GitBranch, color: "text-blue-400" },
          { label: "Kafka Topics", value: kafkaTopics?.total_topics || 0, icon: Radio, color: "text-amber-400" },
          { label: "Features Computed", value: health?.stats?.features_computed || 0, icon: Layers, color: "text-cyan-400" },
        ].map((stat) => (
          <div key={stat.label} className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <stat.icon className={`w-4 h-4 ${stat.color}`} />
              <span className="text-xs text-zinc-500">{stat.label}</span>
            </div>
            <span className="text-xl font-bold text-zinc-100">{stat.value}</span>
          </div>
        ))}
      </div>

      {/* Subsystems Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Feature Pipeline */}
        <SubsystemCard
          name="Feature Pipeline"
          icon={BarChart3}
          data={health?.subsystems?.feature_pipeline}
        >
          <div className="divide-y divide-zinc-800">
            <MetricItem label="Registered Features" value={featureStatus?.registered_features || 0} />
            <MetricItem label="Categories" value={(featureStatus?.categories || []).length} />
            <MetricItem label="Total Computations" value={featureStatus?.stats?.total_computations || 0} />
            <MetricItem label="Cached Symbols" value={featureStatus?.stats?.cached_symbols || 0} />
          </div>
          {featureStatus?.categories && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {featureStatus.categories.map((cat) => (
                <span key={cat} className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-violet-500/10 text-violet-400 border border-violet-500/20">
                  {cat}
                </span>
              ))}
            </div>
          )}
        </SubsystemCard>

        {/* Kafka */}
        <SubsystemCard
          name="Kafka Event Bus"
          icon={Radio}
          data={health?.subsystems?.kafka}
        >
          <div className="divide-y divide-zinc-800">
            <MetricItem label="Mode" value={health?.subsystems?.kafka?.mode === "stub" ? "Stub" : "Live"} />
            <MetricItem label="Topics Defined" value={kafkaTopics?.total_topics || 0} />
            <MetricItem label="Messages Produced" value={health?.subsystems?.kafka?.stats?.messages_produced || 0} />
            <MetricItem label="Messages Consumed" value={health?.subsystems?.kafka?.stats?.messages_consumed || 0} />
          </div>
        </SubsystemCard>

        {/* Feature Store */}
        <SubsystemCard
          name="Feature Store"
          icon={Database}
          data={health?.subsystems?.feature_store}
        >
          <div className="divide-y divide-zinc-800">
            <MetricItem label="Mode" value={health?.subsystems?.feature_store?.mode || "mongodb_fallback"} />
            <MetricItem label="Writes" value={health?.subsystems?.feature_store?.stats?.writes || 0} />
            <MetricItem label="Reads" value={health?.subsystems?.feature_store?.stats?.reads || 0} />
            <MetricItem label="Cache Hits" value={health?.subsystems?.feature_store?.stats?.cache_hits || 0} />
          </div>
        </SubsystemCard>

        {/* Storage */}
        <SubsystemCard
          name="Storage Layer"
          icon={HardDrive}
          data={health?.subsystems?.storage}
        >
          <div className="divide-y divide-zinc-800">
            <MetricItem label="Mode" value={health?.subsystems?.storage?.mode || "N/A"} />
            <MetricItem label="Uploads" value={health?.subsystems?.storage?.stats?.uploads || 0} />
            <MetricItem label="Downloads" value={health?.subsystems?.storage?.stats?.downloads || 0} />
            <MetricItem label="Errors" value={health?.subsystems?.storage?.stats?.errors || 0} />
          </div>
        </SubsystemCard>

        {/* Data Quality */}
        <SubsystemCard
          name="Data Quality"
          icon={CheckCircle2}
          data={health?.subsystems?.data_quality}
        >
          <div className="divide-y divide-zinc-800">
            <MetricItem label="Checks Run" value={health?.stats?.data_quality_checks || 0} />
            <MetricItem label="Engine" value="OHLCV Integrity" />
          </div>
          <p className="text-xs text-zinc-500 mt-2">
            Validates OHLCV bars, circuit limits, volume anomalies
          </p>
        </SubsystemCard>

        {/* Batch Scheduler */}
        <SubsystemCard
          name="Batch Scheduler"
          icon={Clock}
          data={health?.subsystems?.batch_scheduler}
        >
          <div className="divide-y divide-zinc-800">
            <MetricItem label="Total DAGs" value={batchStatus?.total_dags || 0} />
            <MetricItem label="Enabled" value={batchStatus?.enabled_dags || 0} />
            <MetricItem label="Total Runs" value={health?.subsystems?.batch_scheduler?.total_runs || 0} />
            <MetricItem label="Failures" value={health?.subsystems?.batch_scheduler?.total_failures || 0} />
          </div>
        </SubsystemCard>
      </div>

      {/* Batch DAGs */}
      <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <GitBranch className="w-5 h-5 text-blue-400" />
            <h2 className="text-lg font-semibold text-zinc-200">Batch DAGs</h2>
          </div>
          <span className="text-xs text-zinc-500">Post-market data pipelines</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800">
                <th className="text-left py-2 px-3 text-xs text-zinc-500 font-medium">DAG Name</th>
                <th className="text-left py-2 px-3 text-xs text-zinc-500 font-medium">Schedule (IST)</th>
                <th className="text-left py-2 px-3 text-xs text-zinc-500 font-medium">Runs</th>
                <th className="text-left py-2 px-3 text-xs text-zinc-500 font-medium">Last Run</th>
                <th className="text-left py-2 px-3 text-xs text-zinc-500 font-medium">Status</th>
                <th className="text-right py-2 px-3 text-xs text-zinc-500 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {batchStatus?.dags &&
                Object.entries(batchStatus.dags).map(([name, dag]) => (
                  <tr key={name} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                    <td className="py-2.5 px-3 font-medium text-zinc-200">{dag.name}</td>
                    <td className="py-2.5 px-3 text-zinc-400 font-mono text-xs">{dag.schedule_time || "Manual"}</td>
                    <td className="py-2.5 px-3 text-zinc-400">
                      <span className="text-emerald-400">{dag.success_count}</span>
                      {dag.fail_count > 0 && (
                        <span className="text-red-400 ml-1">/ {dag.fail_count} failed</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-xs text-zinc-500">
                      {dag.last_run ? (
                        <span>
                          {new Date(dag.last_run.completed_at).toLocaleTimeString()} ({dag.last_run.duration_s?.toFixed(1)}s)
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-2.5 px-3">
                      {dag.last_run ? (
                        <StatusBadge status={dag.last_run.status} />
                      ) : (
                        <span className="text-xs text-zinc-500">Not run</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <button
                        onClick={() => triggerDag(name)}
                        disabled={triggeringDag === name}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 border border-blue-600/30 disabled:opacity-50 transition-colors"
                      >
                        {triggeringDag === name ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Play className="w-3 h-3" />
                        )}
                        Run
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Run History */}
      {batchHistory.length > 0 && (
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="w-5 h-5 text-emerald-400" />
            <h2 className="text-lg font-semibold text-zinc-200">Run History</h2>
          </div>
          <div className="space-y-2">
            {batchHistory.map((run) => (
              <div
                key={run.id}
                className="flex items-center justify-between py-2 px-3 rounded-lg bg-zinc-800/40 hover:bg-zinc-800/60"
              >
                <div className="flex items-center gap-3">
                  <StatusBadge status={run.status} />
                  <span className="text-sm text-zinc-300 font-medium">{run.dag_name}</span>
                  <span className="text-xs text-zinc-500">{run.trigger}</span>
                </div>
                <div className="flex items-center gap-4 text-xs text-zinc-500">
                  {run.duration_s && <span>{run.duration_s.toFixed(2)}s</span>}
                  <span>{run.started_at ? new Date(run.started_at).toLocaleString() : "—"}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Feature Compute */}
      <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Layers className="w-5 h-5 text-cyan-400" />
          <h2 className="text-lg font-semibold text-zinc-200">Feature Compute</h2>
        </div>
        <div className="flex items-center gap-3 mb-4">
          <input
            type="text"
            value={computingSymbol}
            onChange={(e) => setComputingSymbol(e.target.value.toUpperCase())}
            placeholder="Enter symbol (e.g. RELIANCE)"
            className="flex-1 px-3 py-2 text-sm bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
            onKeyDown={(e) => e.key === "Enter" && computeFeatures()}
          />
          <button
            onClick={computeFeatures}
            disabled={computeLoading || !computingSymbol.trim()}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-violet-600 text-white hover:bg-violet-500 disabled:opacity-50 transition-colors"
          >
            {computeLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            Compute
          </button>
        </div>

        {computeResult && (
          <div className="bg-zinc-800/50 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-zinc-200">{computeResult.symbol}</span>
              <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-500">{computeResult.feature_count} features</span>
                <span className="text-xs text-zinc-500">{computeResult.source}</span>
              </div>
            </div>
            {computeResult.features && Object.keys(computeResult.features).length > 0 ? (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 max-h-60 overflow-y-auto">
                {Object.entries(computeResult.features).map(([key, value]) => (
                  <div key={key} className="flex flex-col py-1">
                    <span className="text-[10px] text-zinc-500 truncate">{key}</span>
                    <span className="text-xs font-mono text-zinc-300">
                      {value === null ? "—" : typeof value === "number" ? value.toFixed(4) : String(value)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-zinc-500">No features computed. YFinance may be unavailable in this environment.</p>
            )}
          </div>
        )}
      </div>

      {/* Kafka Topics */}
      {kafkaTopics?.topics && (
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Radio className="w-5 h-5 text-amber-400" />
            <h2 className="text-lg font-semibold text-zinc-200">Kafka Topics ({kafkaTopics.total_topics})</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {kafkaTopics.topics.map((topic) => (
              <div
                key={topic.name}
                className="flex items-start gap-2 p-3 rounded-lg bg-zinc-800/40 hover:bg-zinc-800/60 transition-colors"
              >
                <ChevronRight className="w-3.5 h-3.5 text-amber-400 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-xs font-medium text-zinc-300">{topic.name}</p>
                  <p className="text-[10px] text-zinc-500 mt-0.5">{topic.description}</p>
                  <div className="flex gap-2 mt-1">
                    <span className="text-[10px] text-zinc-600">P: {topic.partitions}</span>
                    <span className="text-[10px] text-zinc-600">{topic.compression}</span>
                    <span className="text-[10px] text-zinc-600">{topic.retention_hours}h</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
