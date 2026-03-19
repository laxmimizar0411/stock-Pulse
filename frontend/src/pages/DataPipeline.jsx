import React, { useState, useEffect, useCallback } from "react";
import {
  getPipelineStatus,
  runPipelineExtraction,
  startPipelineScheduler,
  stopPipelineScheduler,
  getPipelineJobs,
  getPipelineLogs,
  getPipelineMetrics,
  getPipelineHistory,
  testDhanAPI,
  getDefaultSymbols,
  getSymbolCategories
} from "@/lib/api";
import { toast } from "sonner";
import { 
  RefreshCw, 
  Play, 
  Pause, 
  Activity, 
  Database, 
  Clock, 
  AlertTriangle, 
  CheckCircle, 
  XCircle,
  TrendingUp,
  BarChart3,
  Zap,
  Server,
  Timer,
  List,
  FileText,
  ArrowRight,
  Loader2,
  Settings,
  AlertCircle,
  Layers
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

// Status Badge Component
const StatusBadge = ({ status }) => {
  const statusConfig = {
    idle: { color: "bg-gray-500", label: "Idle" },
    running: { color: "bg-blue-500", label: "Running", pulse: true },
    scheduled: { color: "bg-green-500", label: "Scheduled" },
    paused: { color: "bg-yellow-500", label: "Paused" },
    error: { color: "bg-red-500", label: "Error" },
    success: { color: "bg-green-500", label: "Success" },
    partial_success: { color: "bg-yellow-500", label: "Partial" },
    failed: { color: "bg-red-500", label: "Failed" },
    pending: { color: "bg-gray-400", label: "Pending" },
    unavailable: { color: "bg-red-600", label: "Unavailable" }
  };
  
  const config = statusConfig[status] || statusConfig.idle;
  
  return (
    <Badge 
      className={cn(
        "text-xs px-2 py-1",
        config.color,
        config.pulse && "animate-pulse"
      )}
    >
      {config.label}
    </Badge>
  );
};

// Metric Card Component
const MetricCard = ({ title, value, icon: Icon, description, trend, trendUp }) => (
  <Card className="bg-[#18181B] border-[#27272A]">
    <CardContent className="p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[#A1A1AA] text-xs uppercase tracking-wider">{title}</p>
          <p className="text-2xl font-bold text-white mt-1">{value}</p>
          {description && (
            <p className="text-xs text-[#71717A] mt-1">{description}</p>
          )}
        </div>
        <div className="flex flex-col items-end">
          <Icon className="w-8 h-8 text-[#3B82F6]" />
          {trend !== undefined && (
            <span className={cn(
              "text-xs mt-2",
              trendUp ? "text-green-500" : "text-red-500"
            )}>
              {trendUp ? "↑" : "↓"} {trend}%
            </span>
          )}
        </div>
      </div>
    </CardContent>
  </Card>
);

export default function DataPipeline() {
  const [status, setStatus] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [history, setHistory] = useState([]);
  const [logs, setLogs] = useState([]);
  const [symbolCategories, setSymbolCategories] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Fetch all data
  const fetchData = useCallback(async () => {
    try {
      const [statusRes, metricsRes, jobsRes, historyRes, logsRes, symbolsRes] = await Promise.all([
        getPipelineStatus().catch(e => ({ data: null })),
        getPipelineMetrics().catch(e => ({ data: null })),
        getPipelineJobs(10).catch(e => ({ data: { jobs: [] } })),
        getPipelineHistory(20).catch(e => ({ data: { history: [] } })),
        getPipelineLogs(50).catch(e => ({ data: { logs: [] } })),
        getSymbolCategories().catch(e => getDefaultSymbols().catch(e => ({ data: { symbols: [] } })))
      ]);
      
      setStatus(statusRes.data);
      setMetrics(metricsRes.data);
      setJobs(jobsRes.data?.jobs || []);
      setHistory(historyRes.data?.history || []);
      setLogs(logsRes.data?.logs || []);
      setSymbolCategories(symbolsRes.data);
    } catch (error) {
      console.error("Error fetching pipeline data:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch and auto-refresh
  useEffect(() => {
    fetchData();
    
    let interval;
    if (autoRefresh) {
      interval = setInterval(fetchData, 10000); // Refresh every 10 seconds
    }
    
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [fetchData, autoRefresh]);

  // Run extraction manually
  const handleRunExtraction = async () => {
    setActionLoading(true);
    try {
      const response = await runPipelineExtraction();
      toast.success("Extraction job started", {
        description: `Job ID: ${response.data?.job?.job_id}`
      });
      fetchData();
    } catch (error) {
      toast.error("Failed to start extraction", {
        description: error.response?.data?.detail || error.message
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Start scheduler
  const handleStartScheduler = async () => {
    setActionLoading(true);
    try {
      await startPipelineScheduler(30);
      toast.success("Scheduler started", {
        description: "Extraction will run every 30 minutes"
      });
      fetchData();
    } catch (error) {
      toast.error("Failed to start scheduler", {
        description: error.response?.data?.detail || error.message
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Stop scheduler
  const handleStopScheduler = async () => {
    setActionLoading(true);
    try {
      await stopPipelineScheduler();
      toast.success("Scheduler stopped");
      fetchData();
    } catch (error) {
      toast.error("Failed to stop scheduler", {
        description: error.response?.data?.detail || error.message
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Test API
  const handleTestAPI = async () => {
    setActionLoading(true);
    setTestResult(null);
    try {
      const response = await testDhanAPI("RELIANCE");
      setTestResult(response.data);
      if (response.data?.success) {
        toast.success("API test successful", {
          description: `Latency: ${response.data?.latency_ms?.toFixed(2)}ms`
        });
      } else {
        toast.error("API test failed", {
          description: response.data?.error || "Unknown error"
        });
      }
    } catch (error) {
      setTestResult({ success: false, error: error.message });
      toast.error("API test failed", {
        description: error.response?.data?.detail || error.message
      });
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-[#3B82F6]" />
      </div>
    );
  }

  const pipelineMetrics = status?.metrics || {};
  const apiMetrics = status?.extractor_metrics || {};
  const isSchedulerRunning = status?.is_running;
  const pipelineStatus = status?.status || "unavailable";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <Database className="w-8 h-8 text-[#3B82F6]" />
            Data Pipeline Monitor
          </h1>
          <p className="text-[#A1A1AA] mt-1">
            Monitor and manage stock data extraction from Dhan API
          </p>
        </div>
        
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={cn(autoRefresh && "border-green-500 text-green-500")}
          >
            <RefreshCw className={cn("w-4 h-4 mr-2", autoRefresh && "animate-spin")} />
            {autoRefresh ? "Auto-Refresh On" : "Auto-Refresh Off"}
          </Button>
          
          <Button
            variant="outline"
            size="sm"
            onClick={fetchData}
            disabled={actionLoading}
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Pipeline Status Card */}
      <Card className="bg-gradient-to-r from-[#18181B] to-[#1F1F23] border-[#27272A]">
        <CardContent className="p-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className={cn(
                "w-4 h-4 rounded-full",
                pipelineStatus === "running" ? "bg-blue-500 animate-pulse" :
                pipelineStatus === "scheduled" ? "bg-green-500" :
                pipelineStatus === "error" ? "bg-red-500" : "bg-gray-500"
              )} />
              <div>
                <h2 className="text-xl font-semibold text-white">Pipeline Status</h2>
                <div className="flex items-center gap-2 mt-1">
                  <StatusBadge status={pipelineStatus} />
                  {status?.current_job && (
                    <Badge variant="outline" className="text-blue-400 border-blue-400">
                      Job Running
                    </Badge>
                  )}
                </div>
              </div>
            </div>
            
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={handleTestAPI}
                disabled={actionLoading}
                variant="outline"
                className="border-purple-500 text-purple-400 hover:bg-purple-500/10"
              >
                {actionLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Zap className="w-4 h-4 mr-2" />}
                Test API
              </Button>
              
              <Button
                onClick={handleRunExtraction}
                disabled={actionLoading || pipelineStatus === "running"}
                className="bg-[#3B82F6] hover:bg-[#2563EB]"
              >
                {actionLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
                Run Extraction
              </Button>
              
              {isSchedulerRunning ? (
                <Button
                  onClick={handleStopScheduler}
                  disabled={actionLoading}
                  variant="destructive"
                >
                  <Pause className="w-4 h-4 mr-2" />
                  Stop Scheduler
                </Button>
              ) : (
                <Button
                  onClick={handleStartScheduler}
                  disabled={actionLoading}
                  className="bg-green-600 hover:bg-green-700"
                >
                  <Play className="w-4 h-4 mr-2" />
                  Start Scheduler
                </Button>
              )}
            </div>
          </div>
          
          {/* Current Job Progress */}
          {status?.current_job && (
            <div className="mt-4 p-4 bg-[#09090B] rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-[#A1A1AA]">Current Job: {status.current_job.job_id}</span>
                <span className="text-sm text-white">
                  {status.current_job.processed_symbols}/{status.current_job.total_symbols} symbols
                </span>
              </div>
              <Progress value={status.current_job.progress_percent} className="h-2" />
            </div>
          )}
        </CardContent>
      </Card>

      {/* API Test Result */}
      {testResult && (
        <Card className={cn(
          "border-2",
          testResult.success ? "border-green-500 bg-green-500/10" : "border-red-500 bg-red-500/10"
        )}>
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              {testResult.success ? (
                <CheckCircle className="w-6 h-6 text-green-500 mt-0.5" />
              ) : (
                <XCircle className="w-6 h-6 text-red-500 mt-0.5" />
              )}
              <div className="flex-1">
                <h3 className="font-semibold text-white">
                  API Test {testResult.success ? "Successful" : "Failed"}
                </h3>
                {testResult.success ? (
                  <div className="mt-2 text-sm text-[#A1A1AA]">
                    <p>Latency: <span className="text-white font-mono">{testResult.latency_ms?.toFixed(2)}ms</span></p>
                    {testResult.data && (
                      <p className="mt-1">
                        Symbol: <span className="text-white">{testResult.data.symbol}</span> | 
                        Last Price: <span className="text-white">₹{testResult.data.last_price}</span>
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="mt-1 text-sm text-red-400">{testResult.error || testResult.message}</p>
                )}
              </div>
              <Button variant="ghost" size="sm" onClick={() => setTestResult(null)}>
                <XCircle className="w-4 h-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Key Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          title="Total Jobs"
          value={pipelineMetrics.total_jobs_run || 0}
          icon={Activity}
          description={`${pipelineMetrics.successful_jobs || 0} successful`}
        />
        <MetricCard
          title="Success Rate"
          value={`${pipelineMetrics.job_success_rate || 0}%`}
          icon={CheckCircle}
          description="Job completion rate"
        />
        <MetricCard
          title="Data Completeness"
          value={`${pipelineMetrics.data_completeness_percent || 0}%`}
          icon={Database}
          description={`${pipelineMetrics.received_daily_symbols || 0}/${pipelineMetrics.expected_daily_symbols || 0} symbols`}
        />
        <MetricCard
          title="Avg Duration"
          value={`${(pipelineMetrics.avg_job_duration_seconds || 0).toFixed(1)}s`}
          icon={Timer}
          description="Per extraction job"
        />
      </div>

      {/* API Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          title="API Requests"
          value={apiMetrics.total_requests || 0}
          icon={Server}
          description={`${apiMetrics.successful_requests || 0} successful`}
        />
        <MetricCard
          title="API Success Rate"
          value={`${apiMetrics.success_rate || 0}%`}
          icon={TrendingUp}
        />
        <MetricCard
          title="Avg Latency"
          value={`${(apiMetrics.avg_latency_ms || 0).toFixed(0)}ms`}
          icon={Zap}
          description={`Min: ${(apiMetrics.min_latency_ms || 0).toFixed(0)}ms / Max: ${(apiMetrics.max_latency_ms || 0).toFixed(0)}ms`}
        />
        <MetricCard
          title="Retries"
          value={apiMetrics.retry_count || 0}
          icon={RefreshCw}
          description={`${apiMetrics.rate_limit_hits || 0} rate limits`}
        />
      </div>

      {/* Tabs for Jobs, Logs, and Data */}
      <Tabs defaultValue="jobs" className="w-full">
        <TabsList className="bg-[#18181B] border border-[#27272A]">
          <TabsTrigger value="jobs" className="data-[state=active]:bg-[#3B82F6]">
            <BarChart3 className="w-4 h-4 mr-2" />
            Jobs ({jobs.length})
          </TabsTrigger>
          <TabsTrigger value="history" className="data-[state=active]:bg-[#3B82F6]">
            <Clock className="w-4 h-4 mr-2" />
            History ({history.length})
          </TabsTrigger>
          <TabsTrigger value="logs" className="data-[state=active]:bg-[#3B82F6]">
            <FileText className="w-4 h-4 mr-2" />
            Logs ({logs.length})
          </TabsTrigger>
          <TabsTrigger value="symbols" className="data-[state=active]:bg-[#3B82F6]">
            <Layers className="w-4 h-4 mr-2" />
            Symbols ({symbolCategories?.total_symbols || 0})
          </TabsTrigger>
        </TabsList>

        {/* Jobs Tab */}
        <TabsContent value="jobs" className="mt-4">
          <Card className="bg-[#18181B] border-[#27272A]">
            <CardHeader className="pb-2">
              <CardTitle className="text-white text-lg">Recent Extraction Jobs</CardTitle>
              <CardDescription>View the status and results of recent extraction jobs</CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[400px]">
                {jobs.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-[#A1A1AA]">
                    <Database className="w-12 h-12 mb-4 opacity-50" />
                    <p>No extraction jobs yet</p>
                    <p className="text-sm mt-1">Run an extraction to see jobs here</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {jobs.map((job) => (
                      <div
                        key={job.job_id}
                        className="p-4 bg-[#09090B] rounded-lg border border-[#27272A] hover:border-[#3B82F6]/50 transition-colors"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <StatusBadge status={job.status} />
                            <span className="font-mono text-sm text-white">{job.job_id}</span>
                          </div>
                          <span className="text-xs text-[#A1A1AA]">
                            {job.created_at ? new Date(job.created_at).toLocaleString() : 'N/A'}
                          </span>
                        </div>
                        <div className="mt-2 flex items-center gap-4 text-sm text-[#A1A1AA]">
                          <span>
                            <span className="text-green-500">{job.successful_symbols}</span> / {job.total_symbols} successful
                          </span>
                          {job.failed_symbols > 0 && (
                            <span className="text-red-500">{job.failed_symbols} failed</span>
                          )}
                          {job.duration_seconds && (
                            <span>Duration: {job.duration_seconds.toFixed(1)}s</span>
                          )}
                        </div>
                        {job.progress_percent < 100 && job.status === "running" && (
                          <Progress value={job.progress_percent} className="h-1 mt-2" />
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history" className="mt-4">
          <Card className="bg-[#18181B] border-[#27272A]">
            <CardHeader className="pb-2">
              <CardTitle className="text-white text-lg">Job History</CardTitle>
              <CardDescription>Complete history of extraction jobs</CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[400px]">
                {history.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-[#A1A1AA]">
                    <Clock className="w-12 h-12 mb-4 opacity-50" />
                    <p>No history available</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {history.map((item, index) => (
                      <div
                        key={item.job_id || index}
                        className="p-3 bg-[#09090B] rounded-lg flex items-center justify-between"
                      >
                        <div className="flex items-center gap-3">
                          {item.status === "success" ? (
                            <CheckCircle className="w-4 h-4 text-green-500" />
                          ) : item.status === "partial_success" ? (
                            <AlertCircle className="w-4 h-4 text-yellow-500" />
                          ) : (
                            <XCircle className="w-4 h-4 text-red-500" />
                          )}
                          <div>
                            <span className="font-mono text-sm text-white">{item.job_id}</span>
                            <p className="text-xs text-[#A1A1AA]">
                              {item.successful_symbols || 0}/{item.total_symbols || 0} symbols
                            </p>
                          </div>
                        </div>
                        <span className="text-xs text-[#A1A1AA]">
                          {item.completed_at ? new Date(item.completed_at).toLocaleString() : 'N/A'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Logs Tab */}
        <TabsContent value="logs" className="mt-4">
          <Card className="bg-[#18181B] border-[#27272A]">
            <CardHeader className="pb-2">
              <CardTitle className="text-white text-lg">Pipeline Logs</CardTitle>
              <CardDescription>Event logs and error tracking</CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[400px]">
                {logs.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-[#A1A1AA]">
                    <FileText className="w-12 h-12 mb-4 opacity-50" />
                    <p>No logs available</p>
                  </div>
                ) : (
                  <div className="space-y-1 font-mono text-sm">
                    {logs.map((log, index) => (
                      <div
                        key={index}
                        className={cn(
                          "p-2 rounded flex items-start gap-2",
                          log.event_type?.includes("error") || log.event_type?.includes("failed")
                            ? "bg-red-500/10 text-red-400"
                            : log.event_type?.includes("success") || log.event_type?.includes("completed")
                            ? "bg-green-500/10 text-green-400"
                            : "bg-[#09090B] text-[#A1A1AA]"
                        )}
                      >
                        <span className="text-xs text-[#71717A] whitespace-nowrap">
                          {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : 'N/A'}
                        </span>
                        <span className="text-xs uppercase font-semibold min-w-[120px]">
                          {log.event_type}
                        </span>
                        <span className="text-xs flex-1">
                          {log.job_id && <span className="text-blue-400">[{log.job_id}]</span>}
                          {log.error && <span className="text-red-400 ml-1">{log.error}</span>}
                          {log.symbol_count && <span className="ml-1">{log.symbol_count} symbols</span>}
                          {log.successful !== undefined && (
                            <span className="ml-1">
                              {log.successful} ok / {log.failed} failed
                            </span>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Symbols Tab */}
        <TabsContent value="symbols" className="mt-4">
          <Card className="bg-[#18181B] border-[#27272A]">
            <CardHeader className="pb-2">
              <CardTitle className="text-white text-lg">Tracked Symbols</CardTitle>
              <CardDescription>
                {symbolCategories?.total_symbols || 0} symbols configured for extraction across 3 categories
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                {/* NIFTY 50 */}
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <Badge className="bg-blue-600">NIFTY 50</Badge>
                    <span className="text-sm text-[#A1A1AA]">
                      {symbolCategories?.nifty_50?.count || 0} stocks
                    </span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
                    {symbolCategories?.nifty_50?.symbols?.map((symbol) => (
                      <div
                        key={symbol}
                        className="p-2 bg-blue-500/10 rounded text-center border border-blue-500/30 hover:border-blue-500 transition-colors"
                      >
                        <span className="font-mono text-xs text-white">{symbol}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* NIFTY Next 50 */}
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <Badge className="bg-purple-600">NIFTY Next 50</Badge>
                    <span className="text-sm text-[#A1A1AA]">
                      {symbolCategories?.nifty_next_50?.count || 0} stocks
                    </span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
                    {symbolCategories?.nifty_next_50?.symbols?.map((symbol) => (
                      <div
                        key={symbol}
                        className="p-2 bg-purple-500/10 rounded text-center border border-purple-500/30 hover:border-purple-500 transition-colors"
                      >
                        <span className="font-mono text-xs text-white">{symbol}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Mid & Small Caps */}
                {symbolCategories?.mid_small_caps?.count > 0 && (
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <Badge className="bg-green-600">Mid & Small Caps</Badge>
                      <span className="text-sm text-[#A1A1AA]">
                        {symbolCategories?.mid_small_caps?.count || 0} stocks
                      </span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
                      {symbolCategories?.mid_small_caps?.symbols?.map((symbol) => (
                        <div
                          key={symbol}
                          className="p-2 bg-green-500/10 rounded text-center border border-green-500/30 hover:border-green-500 transition-colors"
                        >
                          <span className="font-mono text-xs text-white">{symbol}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Missing/Delayed Data Section */}
      {(pipelineMetrics.missing_symbols_count > 0 || pipelineMetrics.delayed_symbols_count > 0) && (
        <Card className="bg-[#18181B] border-yellow-500/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-white text-lg flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-yellow-500" />
              Data Quality Alerts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid md:grid-cols-2 gap-4">
              {pipelineMetrics.missing_symbols_count > 0 && (
                <div className="p-4 bg-red-500/10 rounded-lg border border-red-500/30">
                  <h4 className="font-semibold text-red-400 mb-2">
                    Missing Data ({pipelineMetrics.missing_symbols_count} symbols)
                  </h4>
                  <div className="flex flex-wrap gap-1">
                    {pipelineMetrics.missing_symbols?.slice(0, 10).map((s) => (
                      <Badge key={s} variant="outline" className="text-red-400 border-red-400/50">
                        {s}
                      </Badge>
                    ))}
                    {pipelineMetrics.missing_symbols_count > 10 && (
                      <Badge variant="outline" className="text-red-400 border-red-400/50">
                        +{pipelineMetrics.missing_symbols_count - 10} more
                      </Badge>
                    )}
                  </div>
                </div>
              )}
              
              {pipelineMetrics.delayed_symbols_count > 0 && (
                <div className="p-4 bg-yellow-500/10 rounded-lg border border-yellow-500/30">
                  <h4 className="font-semibold text-yellow-400 mb-2">
                    Delayed Data ({pipelineMetrics.delayed_symbols_count} symbols)
                  </h4>
                  <div className="flex flex-wrap gap-1">
                    {pipelineMetrics.delayed_symbols?.slice(0, 10).map((s) => (
                      <Badge key={s} variant="outline" className="text-yellow-400 border-yellow-400/50">
                        {s}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recent Errors */}
      {apiMetrics.recent_errors?.length > 0 && (
        <Card className="bg-[#18181B] border-red-500/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-white text-lg flex items-center gap-2">
              <XCircle className="w-5 h-5 text-red-500" />
              Recent API Errors
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[200px]">
              <div className="space-y-2">
                {apiMetrics.recent_errors.map((error, index) => (
                  <div
                    key={index}
                    className="p-3 bg-red-500/10 rounded-lg text-sm"
                  >
                    <div className="flex justify-between">
                      <span className="font-mono text-red-400">{error.symbol || 'Unknown'}</span>
                      <span className="text-xs text-[#A1A1AA]">
                        {error.timestamp ? new Date(error.timestamp).toLocaleString() : 'N/A'}
                      </span>
                    </div>
                    <p className="text-red-300 mt-1">{error.error}</p>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
