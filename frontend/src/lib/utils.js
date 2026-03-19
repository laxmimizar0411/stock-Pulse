import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value, currency = "INR") {
  if (value === null || value === undefined) return "--";
  
  if (Math.abs(value) >= 10000000) {
    return `₹${(value / 10000000).toFixed(2)} Cr`;
  } else if (Math.abs(value) >= 100000) {
    return `₹${(value / 100000).toFixed(2)} L`;
  }
  
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined) return "--";
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatPercent(value) {
  if (value === null || value === undefined) return "--";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function getScoreColor(score) {
  if (score >= 70) return "text-green-500";
  if (score >= 40) return "text-yellow-500";
  return "text-red-500";
}

export function getScoreBgColor(score) {
  if (score >= 70) return "bg-green-500";
  if (score >= 40) return "bg-yellow-500";
  return "bg-red-500";
}

export function getChangeColor(value) {
  if (value > 0) return "text-green-500";
  if (value < 0) return "text-red-500";
  return "text-muted-foreground";
}

export function getVerdictColor(verdict) {
  const colors = {
    "STRONG BUY": "text-green-400 bg-green-500/10",
    "BUY": "text-green-500 bg-green-500/10",
    "HOLD": "text-yellow-500 bg-yellow-500/10",
    "AVOID": "text-orange-500 bg-orange-500/10",
    "STRONG AVOID": "text-red-500 bg-red-500/10",
  };
  return colors[verdict] || "text-muted-foreground bg-muted";
}

export function getSentimentColor(sentiment) {
  const colors = {
    "POSITIVE": "text-green-500",
    "NEGATIVE": "text-red-500",
    "NEUTRAL": "text-muted-foreground",
  };
  return colors[sentiment] || "text-muted-foreground";
}

export function truncateText(text, maxLength) {
  if (!text) return "";
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + "...";
}

export function formatErrorMessage(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;

  if (Array.isArray(value)) {
    return value
      .map((item) => formatErrorMessage(item))
      .filter(Boolean)
      .join(" | ");
  }

  if (typeof value === "object") {
    if (typeof value.error === "string") {
      const prefix = value.symbol ? `${value.symbol}: ` : "";
      return `${prefix}${value.error}`;
    }
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }

  return String(value);
}

export function getApiErrorMessage(error, fallback = "Something went wrong") {
  const detail = formatErrorMessage(error?.response?.data?.detail);
  if (detail) return detail;

  const responseError = formatErrorMessage(error?.response?.data?.error);
  if (responseError) return responseError;

  const message = formatErrorMessage(error?.message);
  if (message) return message;

  return fallback;
}
