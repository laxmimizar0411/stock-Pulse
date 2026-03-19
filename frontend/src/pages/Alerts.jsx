import React, { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import {
    Bell,
    Plus,
    Trash2,
    Edit,
    AlertTriangle,
    TrendingUp,
    TrendingDown,
    Activity,
    Clock,
    Check,
    X,
    Target,
    Wifi,
    WifiOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { searchStocks } from "@/lib/api";
import { formatCurrency, getApiErrorMessage } from "@/lib/utils";
import { useWebSocket } from "@/hooks/useWebSocket";

const ALERT_CONDITIONS = [
    { value: "price_above", label: "Price goes above", icon: TrendingUp },
    { value: "price_below", label: "Price goes below", icon: TrendingDown },
    { value: "price_crosses", label: "Price crosses", icon: Activity },
    { value: "percent_change", label: "Daily change exceeds %", icon: AlertTriangle },
];

const ALERT_PRIORITIES = [
    { value: "low", label: "Low", color: "text-gray-400" },
    { value: "medium", label: "Medium", color: "text-yellow-500" },
    { value: "high", label: "High", color: "text-orange-500" },
    { value: "critical", label: "Critical", color: "text-red-500" },
];

export default function Alerts() {
    const [alerts, setAlerts] = useState([]);
    const [notifications, setNotifications] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showCreateDialog, setShowCreateDialog] = useState(false);
    const [editingAlert, setEditingAlert] = useState(null);
    const [searchResults, setSearchResults] = useState([]);
    const [searchQuery, setSearchQuery] = useState("");

    // Form state
    const [formData, setFormData] = useState({
        symbol: "",
        stockName: "",
        condition: "price_above",
        target_value: "",
        priority: "medium",
        message: "",
    });

    // Real-time alert notifications via WebSocket
    const handleAlertNotification = useCallback((alertData) => {
        // Show toast notification
        toast.success(alertData.message || `Alert triggered for ${alertData.symbol}`, {
            duration: 8000,
            description: `${alertData.symbol} at ${formatCurrency(alertData.current_price)}`,
        });
        // Prepend to notifications list
        setNotifications((prev) => [alertData, ...prev].slice(0, 20));
        // Refresh alerts to get updated statuses
        fetchAlerts();
    }, []);

    const { isConnected } = useWebSocket({
        onAlertNotification: handleAlertNotification,
        autoConnect: true,
    });

    useEffect(() => {
        fetchAlerts();
        fetchNotifications();
    }, []);

    const fetchAlerts = async () => {
        try {
            setLoading(true);
            const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/alerts`);
            const data = await response.json();
            setAlerts(data.alerts || []);
        } catch (error) {
            console.error("Error fetching alerts:", error);
            toast.error(getApiErrorMessage(error, "Failed to load alerts"));
        } finally {
            setLoading(false);
        }
    };

    const fetchNotifications = async () => {
        try {
            const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/alerts/notifications/recent`);
            const data = await response.json();
            setNotifications(data || []);
        } catch (error) {
            console.error("Error fetching notifications:", error);
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
            setSearchResults(response.data || []);
        } catch (error) {
            console.error("Search error:", error);
        }
    };

    const selectStock = (stock) => {
        setFormData({
            ...formData,
            symbol: stock.symbol,
            stockName: stock.name,
        });
        setSearchQuery(stock.symbol);
        setSearchResults([]);
    };

    const createAlert = async () => {
        if (!formData.symbol || !formData.target_value) {
            toast.error("Please fill in all required fields");
            return;
        }

        try {
            const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/alerts`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    symbol: formData.symbol,
                    condition: formData.condition,
                    target_value: parseFloat(formData.target_value),
                    priority: formData.priority,
                    message: formData.message || null,
                }),
            });

            if (response.ok) {
                toast.success("Alert created successfully!");
                setShowCreateDialog(false);
                resetForm();
                fetchAlerts();
            } else {
                throw new Error("Failed to create alert");
            }
        } catch (error) {
            console.error("Error creating alert:", error);
            toast.error(getApiErrorMessage(error, "Failed to create alert"));
        }
    };

    const deleteAlert = async (alertId) => {
        try {
            const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/alerts/${alertId}`, {
                method: "DELETE",
            });

            if (response.ok) {
                toast.success("Alert deleted");
                fetchAlerts();
            } else {
                throw new Error("Failed to delete alert");
            }
        } catch (error) {
            console.error("Error deleting alert:", error);
            toast.error(getApiErrorMessage(error, "Failed to delete alert"));
        }
    };

    const resetForm = () => {
        setFormData({
            symbol: "",
            stockName: "",
            condition: "price_above",
            target_value: "",
            priority: "medium",
            message: "",
        });
        setSearchQuery("");
        setSearchResults([]);
    };

    const getConditionIcon = (condition) => {
        const cond = ALERT_CONDITIONS.find((c) => c.value === condition);
        return cond ? cond.icon : Activity;
    };

    const getConditionLabel = (condition) => {
        const cond = ALERT_CONDITIONS.find((c) => c.value === condition);
        return cond ? cond.label : condition;
    };

    const getPriorityColor = (priority) => {
        const pri = ALERT_PRIORITIES.find((p) => p.value === priority);
        return pri ? pri.color : "text-gray-400";
    };

    const getStatusBadge = (status) => {
        switch (status) {
            case "active":
                return <Badge className="bg-green-500/20 text-green-400">Active</Badge>;
            case "triggered":
                return <Badge className="bg-yellow-500/20 text-yellow-400">Triggered</Badge>;
            case "expired":
                return <Badge className="bg-gray-500/20 text-gray-400">Expired</Badge>;
            case "disabled":
                return <Badge className="bg-red-500/20 text-red-400">Disabled</Badge>;
            default:
                return <Badge>{status}</Badge>;
        }
    };

    const activeAlerts = alerts.filter((a) => a.status === "active");
    const triggeredAlerts = alerts.filter((a) => a.status === "triggered");

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                        <Bell className="w-8 h-8 text-blue-500" />
                        Price Alerts
                    </h1>
                    <p className="text-muted-foreground mt-1">
                        Get notified when stocks hit your target prices
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5 text-xs">
                        {isConnected ? (
                            <>
                                <Wifi className="w-3.5 h-3.5 text-green-500" />
                                <span className="text-green-500">Live</span>
                            </>
                        ) : (
                            <>
                                <WifiOff className="w-3.5 h-3.5 text-gray-500" />
                                <span className="text-gray-500">Offline</span>
                            </>
                        )}
                    </div>
                    <Button
                        onClick={() => setShowCreateDialog(true)}
                        className="bg-blue-600 hover:bg-blue-700"
                    >
                        <Plus className="w-4 h-4 mr-2" />
                        Create Alert
                    </Button>
                </div>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card className="bg-[#18181B] border-[#27272A]">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">Total Alerts</p>
                                <p className="text-2xl font-bold text-white">{alerts.length}</p>
                            </div>
                            <Bell className="w-8 h-8 text-blue-500/50" />
                        </div>
                    </CardContent>
                </Card>

                <Card className="bg-[#18181B] border-[#27272A]">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">Active</p>
                                <p className="text-2xl font-bold text-green-500">{activeAlerts.length}</p>
                            </div>
                            <Activity className="w-8 h-8 text-green-500/50" />
                        </div>
                    </CardContent>
                </Card>

                <Card className="bg-[#18181B] border-[#27272A]">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">Triggered</p>
                                <p className="text-2xl font-bold text-yellow-500">{triggeredAlerts.length}</p>
                            </div>
                            <Target className="w-8 h-8 text-yellow-500/50" />
                        </div>
                    </CardContent>
                </Card>

                <Card className="bg-[#18181B] border-[#27272A]">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">Notifications</p>
                                <p className="text-2xl font-bold text-purple-500">{notifications.length}</p>
                            </div>
                            <Clock className="w-8 h-8 text-purple-500/50" />
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Alerts List */}
            <Card className="bg-[#18181B] border-[#27272A]">
                <CardHeader>
                    <CardTitle className="text-white">Your Alerts</CardTitle>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="text-center py-8 text-muted-foreground">Loading alerts...</div>
                    ) : alerts.length === 0 ? (
                        <div className="text-center py-12">
                            <Bell className="w-12 h-12 mx-auto text-muted-foreground/50 mb-4" />
                            <h3 className="text-lg font-medium text-white mb-2">No alerts yet</h3>
                            <p className="text-muted-foreground mb-4">
                                Create your first price alert to get notified when stocks hit your targets
                            </p>
                            <Button onClick={() => setShowCreateDialog(true)}>
                                <Plus className="w-4 h-4 mr-2" />
                                Create Alert
                            </Button>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {alerts.map((alert) => {
                                const ConditionIcon = getConditionIcon(alert.condition);
                                return (
                                    <div
                                        key={alert.id}
                                        className="flex items-center justify-between p-4 rounded-lg bg-[#09090B] border border-[#27272A] hover:border-[#3B82F6]/50 transition-colors"
                                    >
                                        <div className="flex items-center gap-4">
                                            <div className={`p-2 rounded-lg bg-[#27272A]`}>
                                                <ConditionIcon className={`w-5 h-5 ${getPriorityColor(alert.priority)}`} />
                                            </div>
                                            <div>
                                                <div className="flex items-center gap-2">
                                                    <span className="font-semibold text-white">{alert.symbol}</span>
                                                    {getStatusBadge(alert.status)}
                                                </div>
                                                <p className="text-sm text-muted-foreground">
                                                    {getConditionLabel(alert.condition)}{" "}
                                                    <span className="font-mono text-white">
                                                        {formatCurrency(alert.target_value)}
                                                    </span>
                                                </p>
                                                {alert.stock_name && (
                                                    <p className="text-xs text-muted-foreground">{alert.stock_name}</p>
                                                )}
                                            </div>
                                        </div>

                                        <div className="flex items-center gap-2">
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                onClick={() => deleteAlert(alert.id)}
                                                className="text-red-500 hover:text-red-400 hover:bg-red-500/10"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </Button>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Recent Notifications */}
            {notifications.length > 0 && (
                <Card className="bg-[#18181B] border-[#27272A]">
                    <CardHeader>
                        <CardTitle className="text-white">Recent Notifications</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-2">
                            {notifications.slice(0, 5).map((notif, index) => (
                                <div
                                    key={index}
                                    className="flex items-start gap-3 p-3 rounded-lg bg-[#09090B] border border-[#27272A]"
                                >
                                    <Bell className="w-5 h-5 text-yellow-500 mt-0.5" />
                                    <div className="flex-1">
                                        <p className="text-sm text-white">{notif.message}</p>
                                        <p className="text-xs text-muted-foreground mt-1">
                                            {new Date(notif.triggered_at).toLocaleString()}
                                        </p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Create Alert Dialog */}
            <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
                <DialogContent className="bg-[#18181B] border-[#27272A]">
                    <DialogHeader>
                        <DialogTitle className="text-white">Create Price Alert</DialogTitle>
                    </DialogHeader>

                    <div className="space-y-4 py-4">
                        {/* Stock Search */}
                        <div className="space-y-2">
                            <Label>Stock Symbol</Label>
                            <div className="relative">
                                <Input
                                    placeholder="Search for a stock..."
                                    value={searchQuery}
                                    onChange={(e) => handleSearch(e.target.value)}
                                    className="bg-[#09090B]"
                                />
                                {searchResults.length > 0 && (
                                    <div className="absolute top-full left-0 right-0 mt-1 bg-[#18181B] border border-[#27272A] rounded-md shadow-lg z-10 max-h-48 overflow-y-auto">
                                        {searchResults.map((stock) => (
                                            <button
                                                key={stock.symbol}
                                                onClick={() => selectStock(stock)}
                                                className="w-full px-3 py-2 text-left hover:bg-[#27272A] flex justify-between"
                                            >
                                                <span className="font-semibold text-white">{stock.symbol}</span>
                                                <span className="text-sm text-muted-foreground truncate ml-2">
                                                    {stock.name}
                                                </span>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                            {formData.stockName && (
                                <p className="text-xs text-muted-foreground">{formData.stockName}</p>
                            )}
                        </div>

                        {/* Condition */}
                        <div className="space-y-2">
                            <Label>Condition</Label>
                            <Select
                                value={formData.condition}
                                onValueChange={(value) => setFormData({ ...formData, condition: value })}
                            >
                                <SelectTrigger className="bg-[#09090B]">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {ALERT_CONDITIONS.map((cond) => (
                                        <SelectItem key={cond.value} value={cond.value}>
                                            {cond.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        {/* Target Value */}
                        <div className="space-y-2">
                            <Label>
                                {formData.condition === "percent_change" ? "Threshold (%)" : "Target Price (₹)"}
                            </Label>
                            <Input
                                type="number"
                                placeholder={formData.condition === "percent_change" ? "e.g., 5" : "e.g., 1500"}
                                value={formData.target_value}
                                onChange={(e) => setFormData({ ...formData, target_value: e.target.value })}
                                className="bg-[#09090B]"
                            />
                        </div>

                        {/* Priority */}
                        <div className="space-y-2">
                            <Label>Priority</Label>
                            <Select
                                value={formData.priority}
                                onValueChange={(value) => setFormData({ ...formData, priority: value })}
                            >
                                <SelectTrigger className="bg-[#09090B]">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {ALERT_PRIORITIES.map((pri) => (
                                        <SelectItem key={pri.value} value={pri.value}>
                                            <span className={pri.color}>{pri.label}</span>
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        {/* Custom Message */}
                        <div className="space-y-2">
                            <Label>Custom Message (Optional)</Label>
                            <Input
                                placeholder="e.g., Check for entry point"
                                value={formData.message}
                                onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                                className="bg-[#09090B]"
                            />
                        </div>
                    </div>

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
                            Cancel
                        </Button>
                        <Button onClick={createAlert} className="bg-blue-600 hover:bg-blue-700">
                            Create Alert
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
