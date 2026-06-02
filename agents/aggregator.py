"""
Aggregator – processes a batch of emails concurrently.
Uses a semaphore to cap concurrent LLM calls and prevent rate-limiting.
"""

from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field

from core.models import Email, EmailProcessingResult, ProcessingStatus
from agents.supervisor import Supervisor
from config.settings import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class AggregatorStats:
    total:      int = 0
    completed:  int = 0
    failed:     int = 0
    skipped:    int = 0
    avg_time_ms: float = 0.0
    results: list[EmailProcessingResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.completed / self.total if self.total else 0.0


class Aggregator:
    """
    Batch-processes a list of emails through the Supervisor.

    Each email is processed concurrently (up to `max_concurrent` at a time).
    Results are collected and summary statistics are computed.
    """

    def __init__(self, supervisor: Supervisor | None = None) -> None:
        self._supervisor = supervisor or Supervisor()
        self._semaphore  = asyncio.Semaphore(settings.max_concurrent_emails)

    async def process_batch(
        self, emails: list[Email]
    ) -> AggregatorStats:
        """모든 이메일을 처리하고 통계 및 결과를 집계하여 반환합니다."""
        logger.info("Aggregator가 %d개의 이메일 배치를 시작합니다", len(emails))

        tasks = [self._process_one(email) for email in emails]
        results: list[EmailProcessingResult] = await asyncio.gather(*tasks)

        stats = AggregatorStats(total=len(emails))
        total_time = 0.0

        for r in results:
            stats.results.append(r)
            total_time += r.processing_time_ms
            if r.status == ProcessingStatus.COMPLETED:
                stats.completed += 1
            elif r.status == ProcessingStatus.FAILED:
                stats.failed += 1
            else:
                stats.skipped += 1

        if stats.total:
            stats.avg_time_ms = total_time / stats.total

        logger.info(
            "배치 완료 – total=%d completed=%d failed=%d avg=%.1f ms",
            stats.total, stats.completed, stats.failed, stats.avg_time_ms,
        )
        return stats

    async def _process_one(self, email: Email) -> EmailProcessingResult:
        async with self._semaphore:
            return await self._supervisor.process(email)
