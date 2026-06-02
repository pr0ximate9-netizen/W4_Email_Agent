"""
멀티 에이전트 이메일 어시스턴트 – 메인 진입점.

사용법:
    python main.py                     # 더미 이메일 처리
    EMAIL_SOURCE=gmail python main.py  # 실제 Gmail 처리
    python main.py --stats             # 데이터베이스 통계만 표시
"""

from __future__ import annotations
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from config.settings import get_settings
from core.models import EmailProcessingResult, ProcessingStatus, SpamLabel, PriorityLevel
from agents.supervisor import Supervisor
from agents.aggregator import Aggregator
from integrations.email_sources import get_email_source
from persistence.database import Database

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger   = logging.getLogger("main")
console  = Console()
settings = get_settings()


# Display helpers

SPAM_COLOR    = {"spam": "red", "suspect": "yellow", "not_spam": "green"}
PRIORITY_COLOR = {"critical": "red", "high": "orange3", "medium": "cyan", "low": "dim"}
ACTION_COLOR  = {
    "delete": "red",
    "flag_review": "yellow",
    "auto_reply": "green",
    "forward": "blue",
    "archive": "dim",
    "ignore": "dim",
}
SPAM_LABEL_KOR = {"spam": "스팸", "suspect": "의심", "not_spam": "정상"}
PRIORITY_LABEL_KOR = {"critical": "긴급", "high": "높음", "medium": "보통", "low": "낮음"}
ACTION_LABEL_KOR = {
    "delete": "삭제",
    "flag_review": "검토",
    "auto_reply": "자동응답",
    "forward": "전달",
    "archive": "보관",
    "ignore": "무시",
}


def _result_table(results: list[EmailProcessingResult]) -> Table:
    table = Table(
        title="이메일 처리 결과",
        box=box.ROUNDED,
        highlight=True,
        show_lines=True,
    )
    table.add_column("#",           style="dim",    width=3)
    table.add_column("제목",         style="bold",   max_width=35)
    table.add_column("발신자",                      max_width=28)
    table.add_column("스팸",         justify="center", width=11)
    table.add_column("우선순위",      justify="center", width=10)
    table.add_column("동작",         justify="center", width=13)
    table.add_column("시간(ms)",     justify="right",  width=10)

    for i, r in enumerate(results, 1):
        if r.status == ProcessingStatus.FAILED:
            table.add_row(str(i), "—", "—", "[red]실패[/]", "—", "—",
                          f"{r.processing_time_ms:.0f}")
            continue

        spam_val   = "—"
        prio_val   = "—"
        action_val = "—"

        if r.spam:
            lv = r.spam.label.value
            spam_val = f"[{SPAM_COLOR.get(lv,'white')}]{SPAM_LABEL_KOR.get(lv, lv)}[/]"

        if r.priority:
            lv = r.priority.level.value
            prio_val = f"[{PRIORITY_COLOR.get(lv,'white')}]{PRIORITY_LABEL_KOR.get(lv, lv)}[/]"

        if r.decision:
            av = r.decision.action.value
            action_val = f"[{ACTION_COLOR.get(av,'white')}]{ACTION_LABEL_KOR.get(av, av)}[/]"

        table.add_row(
            str(i),
            f"[b]{r.email_id[:8]}…[/]",  
            "—",
            spam_val,
            prio_val,
            action_val,
            f"{r.processing_time_ms:.0f}",
        )
    return table


def _result_detail(result: EmailProcessingResult, subject: str, sender: str) -> Panel:
    lines = [
        f"[bold]제목:[/bold] {subject}",
        f"[bold]발신자:[/bold] {sender}",
        "",
    ]
    if result.spam:
        s = result.spam
        lines += [
            f"[bold]스팸 분석[/bold]   [{SPAM_COLOR.get(s.label.value,'white')}]{SPAM_LABEL_KOR.get(s.label.value, s.label.value)}[/] "
            f"({s.confidence:.0%})  –  {s.reasoning}",
            f"         지표: {', '.join(s.indicators) or '없음'}",
        ]
    else:
        lines += ["[bold]스팸 분석[/bold] 없음"]

    if result.priority:
        p = result.priority
        lines += [
            f"[bold]우선순위 분석[/bold] [{PRIORITY_COLOR.get(p.level.value,'white')}]{PRIORITY_LABEL_KOR.get(p.level.value, p.level.value)}[/] "
            f"점수={p.score:.1f}  –  {p.reasoning}",
            f"         태그: {', '.join(p.tags) or '없음'}",
        ]
    else:
        lines += ["[bold]우선순위 분석[/bold] 없음"]

    if result.decision:
        d = result.decision
        lines += [
            f"[bold]의사결정[/bold] [{ACTION_COLOR.get(d.action.value,'white')}]{ACTION_LABEL_KOR.get(d.action.value, d.action.value)}[/] "
            f"({d.confidence:.0%})  –  {d.reasoning}",
        ]
    else:
        lines += ["[bold]의사결정[/bold] 없음"]

    if result.auto_reply and result.auto_reply.generated:
        r = result.auto_reply
        lines += [
            "",
            f"[bold]자동 응답[/bold] ({r.tone})",
            f"[dim]제목:[/dim] {r.subject}",
            f"[dim]{r.body[:300]}[/dim]",
        ]
    if result.error:
        lines.append(f"[red]오류: {result.error}[/red]")

    lines.append(f"\n[dim]처리 시간 {result.processing_time_ms:.1f} ms[/dim]")
    return Panel("\n".join(lines), border_style="blue")


# Main pipeline

async def run_pipeline(verbose: bool = False) -> None:
    console.print(Panel.fit(
        "[bold cyan]Multi-Agent Email Assistant[/bold cyan]\n"
        f"Source: [yellow]{settings.email_source}[/yellow]  │  "
        f"Model: [yellow]{settings.openai_model}[/yellow]  │  "
        f"Parallel: [yellow]{settings.parallel_agents}[/yellow]",
        border_style="cyan",
    ))

    # 1)
    source = get_email_source()
    with console.status("[cyan]이메일 가져오는 중…[/cyan]"):
        emails = await source.fetch(max_results=settings.gmail_max_results)
    console.print(f"[green]완료[/green] 총 [bold]{len(emails)}[/bold]개의 이메일을 가져왔습니다")

    if not emails:
        console.print("[yellow]처리할 이메일이 없습니다.[/yellow]")
        return

    # 2)
    db = Database()
    await db.connect()

    supervisor = Supervisor()
    aggregator = Aggregator(supervisor=supervisor)

    async def persist(result: EmailProcessingResult) -> None:

        for email in emails:
            if email.id == result.email_id:
                await db.upsert_email(email)
                break
        await db.save_result(result)

    supervisor.add_hook(persist)

    # 3)
    with console.status("[cyan]에이전트 실행 중…[/cyan]"):
        stats = await aggregator.process_batch(emails)

    # 4) 결론 도출
    if verbose:
        for result in stats.results:
            email = next((e for e in emails if e.id == result.email_id), None)
            subject = email.subject if email else "—"
            sender  = email.sender  if email else "—"
            console.print(_result_detail(result, subject, sender))
    else:
        # 요약 테이블
        table = Table(
            title="이메일 처리 요약",
            box=box.ROUNDED,
            highlight=True,
            show_lines=True,
        )
        table.add_column("#",        style="dim",  width=3)
        table.add_column("제목",      style="bold", max_width=38)
        table.add_column("스팸",      justify="center", width=12)
        table.add_column("우선순위",   justify="center", width=10)
        table.add_column("동작",      justify="center", width=14)
        table.add_column("시간(ms)", justify="right",  width=8)

        for i, result in enumerate(stats.results, 1):
            email = next((e for e in emails if e.id == result.email_id), None)
            subject = email.subject[:36] if email else "—"

            if result.spam:
                spam_val = f"[{SPAM_COLOR.get(result.spam.label.value,'white')}]{SPAM_LABEL_KOR.get(result.spam.label.value, result.spam.label.value)}[/]"
            else:
                spam_val = "없음"

            if result.priority:
                prio_val = f"[{PRIORITY_COLOR.get(result.priority.level.value,'white')}]{PRIORITY_LABEL_KOR.get(result.priority.level.value, result.priority.level.value)}[/]"
            else:
                prio_val = "없음"

            if result.decision:
                action_val = f"[{ACTION_COLOR.get(result.decision.action.value,'white')}]{ACTION_LABEL_KOR.get(result.decision.action.value, result.decision.action.value)}[/]"
            else:
                action_val = "없음"

            status_tag = (
                "[red]실패[/]" if result.status == ProcessingStatus.FAILED else ""
            )
            table.add_row(
                str(i), subject + status_tag,
                spam_val, prio_val, action_val,
                f"{result.processing_time_ms:.0f}",
            )

        console.print(table)

    # 5)
    db_stats = await db.get_stats()
    console.print(
        Panel(
            f"[green]완료:[/green] {stats.completed}  "
            f"[red]실패:[/red] {stats.failed}  "
            f"[yellow]평균 시간:[/yellow] {stats.avg_time_ms:.0f} ms\n"
            f"[dim]DB 통계 – spam={db_stats.get('spam_spam',0)} "
            f"| critical={db_stats.get('priority_critical',0)} "
            f"| total_processed={db_stats.get('total_completed',0)}[/dim]",
            title="배치 요약",
            border_style="green",
        )
    )

    await db.close()


async def show_stats() -> None:
    """DB 통계만 표시합니다."""
    db = Database()
    await db.connect()
    stats = await db.get_stats()
    await db.close()
    console.print(Panel(
        "\n".join(f"  [cyan]{k}:[/cyan] {v}" for k, v in stats.items()),
        title="데이터베이스 통계",
        border_style="cyan",
    ))


# CLI

def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Agent Email Assistant")
    parser.add_argument("--verbose",  "-v", action="store_true",
                        help="이메일별 상세 결과를 출력합니다")
    parser.add_argument("--stats",         action="store_true",
                        help="데이터베이스 통계를 표시하고 종료합니다")
    parser.add_argument("--source",        choices=["dummy", "gmail"],
                        help="이메일 소스를 재정의합니다 (EMAIL_SOURCE 환경변수 우선)")
    args = parser.parse_args()

    if args.source:
        os.environ["EMAIL_SOURCE"] = args.source
        # Reset cached settings
        from config.settings import get_settings
        get_settings.cache_clear()

    if args.stats:
        asyncio.run(show_stats())
    else:
        asyncio.run(run_pipeline(verbose=args.verbose))


if __name__ == "__main__":
    main()
