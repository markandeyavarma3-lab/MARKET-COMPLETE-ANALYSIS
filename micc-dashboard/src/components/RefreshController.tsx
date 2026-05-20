"use client";
/**
 * RefreshController
 * -----------------
 * Cycle-based auto-refresh: fires ALL fetches, waits for ALL to settle,
 * then counts down REFRESH_INTERVAL seconds, then fires again.
 * No drift. No stale overlapping calls.
 *
 * Usage in page.tsx:
 *   <RefreshController onRefresh={triggerAllFetches} intervalSec={90} />
 */

import { useEffect, useRef, useState, useCallback } from "react";

interface Props {
  onRefresh: () => Promise<void>;
  intervalSec?: number;
  autoStart?: boolean;
}

export default function RefreshController({
  onRefresh,
  intervalSec = 90,
  autoStart = true,
}: Props) {
  const [countdown, setCountdown] = useState(intervalSec);
  const [running,   setRunning]   = useState(false);
  const [paused,    setPaused]    = useState(!autoStart);
  const [lastRefresh, setLastRefresh] = useState<string>("");

  const timerRef    = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countRef    = useRef<ReturnType<typeof setInterval> | null>(null);
  const pausedRef   = useRef(paused);
  pausedRef.current = paused;

  const stopCountdown = useCallback(() => {
    if (timerRef.current)  clearTimeout(timerRef.current);
    if (countRef.current)  clearInterval(countRef.current);
    timerRef.current  = null;
    countRef.current  = null;
  }, []);

  const startCycle = useCallback(async () => {
    if (pausedRef.current) return;
    stopCountdown();
    setRunning(true);
    setCountdown(0);

    try {
      await onRefresh();
    } catch (e) {
      console.error("[RefreshController] fetch error:", e);
    }

    setRunning(false);
    setLastRefresh(new Date().toLocaleTimeString("en-IN", {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }));

    if (pausedRef.current) return;

    // Start countdown
    let remaining = intervalSec;
    setCountdown(remaining);
    countRef.current = setInterval(() => {
      remaining -= 1;
      setCountdown(remaining);
      if (remaining <= 0) {
        clearInterval(countRef.current!);
        countRef.current = null;
      }
    }, 1000);

    timerRef.current = setTimeout(() => {
      startCycle();
    }, intervalSec * 1000);
  }, [onRefresh, intervalSec, stopCountdown]);

  // Auto-start on mount
  useEffect(() => {
    if (autoStart) {
      startCycle();
    }
    return stopCountdown;
  }, []); // eslint-disable-line

  const togglePause = () => {
    const nowPaused = !paused;
    setPaused(nowPaused);
    pausedRef.current = nowPaused;
    if (nowPaused) {
      stopCountdown();
      setRunning(false);
      setCountdown(intervalSec);
    } else {
      startCycle();
    }
  };

  const manualRefresh = () => {
    if (!running) startCycle();
  };

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      fontFamily: "JetBrains Mono, monospace", fontSize: 11,
    }}>
      {lastRefresh && (
        <span style={{ color: "var(--dim)", fontSize: 10 }}>
          last: {lastRefresh}
        </span>
      )}

      {running ? (
        <span style={{ color: "var(--accent)", fontSize: 10 }}>
          FETCHING...
        </span>
      ) : paused ? (
        <span style={{ color: "var(--warn)", fontSize: 10 }}>PAUSED</span>
      ) : (
        <span style={{ color: "var(--dim)", fontSize: 10 }}>
          next in {countdown}s
        </span>
      )}

      <button
        onClick={manualRefresh}
        disabled={running}
        style={{
          background: "none",
          border: "1px solid var(--border)",
          color: running ? "var(--muted)" : "var(--dim)",
          padding: "2px 8px",
          borderRadius: 4,
          cursor: running ? "not-allowed" : "pointer",
          fontFamily: "inherit",
          fontSize: 10,
          transition: "all .15s",
        }}
        title="Refresh now"
      >
        REFRESH
      </button>

      <button
        onClick={togglePause}
        style={{
          background: "none",
          border: "1px solid",
          borderColor: paused ? "var(--warn)" : "var(--border)",
          color: paused ? "var(--warn)" : "var(--dim)",
          padding: "2px 8px",
          borderRadius: 4,
          cursor: "pointer",
          fontFamily: "inherit",
          fontSize: 10,
          transition: "all .15s",
        }}
        title={paused ? "Resume auto-refresh" : "Pause auto-refresh"}
      >
        {paused ? "RESUME" : "PAUSE"}
      </button>
    </div>
  );
}
