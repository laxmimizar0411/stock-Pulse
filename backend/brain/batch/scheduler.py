"""
Batch Scheduler — Lightweight async task scheduler for Stock Pulse Brain.

Replaces Apache Airflow for development environments. Provides:
  - DAG-like task definitions with dependencies
  - Scheduled execution (cron-like intervals)
  - Job tracking and history
  - Manual trigger support via API

In production, these DAGs are ported to Airflow with minimal changes.

Usage:
    scheduler = BatchScheduler()
    scheduler.register_dag("daily_bhavcopy", dag_daily_bhavcopy, schedule="17:00")
    await scheduler.start()
    await scheduler.trigger_dag("daily_bhavcopy")
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger("brain.batch.scheduler")

IST = timezone(timedelta(hours=5, minutes=30))


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class DagRun:
    """Record of a single DAG execution."""

    def __init__(self, dag_name: str, trigger: str = "manual"):
        self.id = str(uuid.uuid4())[:8]
        self.dag_name = dag_name
        self.trigger = trigger  # "manual" | "scheduled"
        self.status = JobStatus.PENDING
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.duration_s: Optional[float] = None
        self.result: Any = None
        self.error: Optional[str] = None
        self.tasks_completed: int = 0
        self.tasks_total: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dag_name": self.dag_name,
            "trigger": self.trigger,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_s": self.duration_s,
            "tasks_completed": self.tasks_completed,
            "tasks_total": self.tasks_total,
            "error": self.error,
        }


class DagDefinition:
    """Definition of a batch DAG."""

    def __init__(
        self,
        name: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
        schedule_time: Optional[str] = None,
        description: str = "",
        enabled: bool = True,
    ):
        """
        Args:
            name: Unique DAG name.
            handler: Async function to execute.
            schedule_time: Time in HH:MM format (IST) for daily execution.
            description: Human-readable description.
            enabled: Whether this DAG is active.
        """
        self.name = name
        self.handler = handler
        self.schedule_time = schedule_time
        self.description = description
        self.enabled = enabled
        self.last_run: Optional[DagRun] = None
        self.run_count = 0
        self.success_count = 0
        self.fail_count = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "schedule_time": self.schedule_time,
            "description": self.description,
            "enabled": self.enabled,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "last_run": self.last_run.to_dict() if self.last_run else None,
        }


class BatchScheduler:
    """
    Lightweight batch scheduler for Brain DAGs.

    Runs as an asyncio background task within the FastAPI process.
    Checks every 60 seconds if a scheduled DAG should run.
    """

    def __init__(self):
        self._dags: Dict[str, DagDefinition] = {}
        self._history: List[DagRun] = []
        self._max_history = 100
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._context: Dict[str, Any] = {}  # Shared context (db, etc.)

    def set_context(self, **kwargs):
        """Set shared context available to all DAGs (e.g., db connection)."""
        self._context.update(kwargs)

    def register_dag(
        self,
        name: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
        schedule_time: Optional[str] = None,
        description: str = "",
        enabled: bool = True,
    ):
        """Register a DAG definition."""
        self._dags[name] = DagDefinition(
            name=name,
            handler=handler,
            schedule_time=schedule_time,
            description=description,
            enabled=enabled,
        )
        logger.info("Registered DAG: %s (schedule: %s)", name, schedule_time or "manual")

    async def start(self):
        """Start the background scheduler loop."""
        if self._running:
            return
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Batch scheduler started with %d DAGs", len(self._dags))

    async def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Batch scheduler stopped")

    async def trigger_dag(self, dag_name: str, **kwargs) -> Optional[DagRun]:
        """Manually trigger a DAG execution."""
        dag = self._dags.get(dag_name)
        if not dag:
            logger.error("DAG not found: %s", dag_name)
            return None

        return await self._execute_dag(dag, trigger="manual", **kwargs)

    async def _execute_dag(self, dag: DagDefinition, trigger: str = "scheduled", **kwargs) -> DagRun:
        """Execute a single DAG run."""
        run = DagRun(dag.name, trigger=trigger)
        run.status = JobStatus.RUNNING
        run.started_at = datetime.now(IST)

        logger.info("Starting DAG: %s (trigger: %s)", dag.name, trigger)

        try:
            # Pass context + any extra kwargs to the handler
            merged_kwargs = {**self._context, **kwargs}
            result = await dag.handler(**merged_kwargs)
            run.status = JobStatus.SUCCESS
            run.result = result
            dag.success_count += 1
            logger.info("DAG %s completed successfully", dag.name)
        except Exception as e:
            run.status = JobStatus.FAILED
            run.error = str(e)
            dag.fail_count += 1
            logger.exception("DAG %s failed: %s", dag.name, e)

        run.completed_at = datetime.now(IST)
        run.duration_s = (run.completed_at - run.started_at).total_seconds()
        dag.run_count += 1
        dag.last_run = run

        # Track history
        self._history.append(run)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        return run

    async def _scheduler_loop(self):
        """Background loop that checks and triggers scheduled DAGs."""
        _last_triggered: Dict[str, str] = {}  # dag_name -> last trigger date

        while self._running:
            try:
                now = datetime.now(IST)
                current_time = now.strftime("%H:%M")
                current_date = now.strftime("%Y-%m-%d")

                for dag in self._dags.values():
                    if not dag.enabled or not dag.schedule_time:
                        continue

                    # Check if it's time to run and hasn't run today
                    if current_time == dag.schedule_time:
                        last_date = _last_triggered.get(dag.name)
                        if last_date != current_date:
                            _last_triggered[dag.name] = current_date
                            asyncio.create_task(self._execute_dag(dag, trigger="scheduled"))

                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Scheduler loop error")
                await asyncio.sleep(60)

    def get_status(self) -> dict:
        """Get scheduler status."""
        return {
            "running": self._running,
            "total_dags": len(self._dags),
            "enabled_dags": sum(1 for d in self._dags.values() if d.enabled),
            "dags": {name: dag.to_dict() for name, dag in self._dags.items()},
        }

    def get_history(self, limit: int = 20) -> List[dict]:
        """Get recent DAG run history."""
        return [run.to_dict() for run in reversed(self._history[-limit:])]

    async def health_check(self) -> dict:
        """Health check for the scheduler."""
        return {
            "status": "healthy" if self._running else "stopped",
            "running": self._running,
            "total_dags": len(self._dags),
            "total_runs": sum(d.run_count for d in self._dags.values()),
            "total_failures": sum(d.fail_count for d in self._dags.values()),
        }
