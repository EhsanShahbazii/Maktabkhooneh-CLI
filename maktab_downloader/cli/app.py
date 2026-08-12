import asyncio
import json
from pathlib import Path
from typing import List, Optional
import typer
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from maktab_downloader.auth.cookies import CookieManager
from maktab_downloader.config import settings
from maktab_downloader.crawler.syncer import MetadataSyncer
from maktab_downloader.crawler.catalog_syncer import CatalogSyncer
from maktab_downloader.crawler.reviews_syncer import ReviewsSyncer
from maktab_downloader.db.database import db_instance
from maktab_downloader.db.repository import repo_instance
from maktab_downloader.downloader.file_downloader import ResourceDownloader
from maktab_downloader.downloader.size_checker import SizeInspector
from maktab_downloader.network.client import MaktabClient
from maktab_downloader.utils.console import (
    console,
    print_banner,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from maktab_downloader.utils.helpers import format_bytes, format_duration

from maktab_downloader.telegram.client import TelegramManager
from maktab_downloader.telegram.uploader import CourseTelegramUploader
from maktab_downloader.telegram.bot import TelegramBotService

app = typer.Typer(
    name="maktab",
    help="Maktabkhooneh Automated Downloader, Metadata Scraper & Telegram Uploader CLI",
    add_completion=False,
)

telegram_app = typer.Typer(
    name="telegram",
    help="Telegram Course Streaming & Uploader (with strict host storage limits)",
)
app.add_typer(telegram_app, name="telegram")


@app.callback()
def main_callback():
    """Maktabkhooneh CLI toolkit by Ehsan Shahbazi."""
    pass


@app.command()
def auth(
    sessionid: Optional[str] = typer.Option(None, "--sessionid", help="Maktabkhooneh sessionid cookie"),
    csrftoken: Optional[str] = typer.Option(None, "--csrftoken", help="Maktabkhooneh csrftoken"),
    cookie_string: Optional[str] = typer.Option(None, "--cookie", help="Full raw cookie string"),
    browser: Optional[str] = typer.Option("chrome", "--browser", "-b", help="Browser to extract cookies from (chrome/brave/firefox/edge/safari)"),
):
    """Check or configure authentication session."""
    print_banner()
    cm = CookieManager(
        cookie_string=cookie_string,
        sessionid=sessionid,
        csrftoken=csrftoken,
        browser=browser,
    )

    client = MaktabClient(cookie_manager=cm)

    async def _run():
        print_info("Testing authentication with Maktabkhooneh servers...")
        res = await client.verify_auth()
        if res.get("authenticated"):
            print_success(f"Authentication verified successfully! Found {res.get('count', 0)} enrolled courses in your account.")
        else:
            print_error(f"Authentication check failed: {res.get('error')}")
            print_info("Tip: You can extract cookies from your browser or set MAKTAB_COOKIE_STRING in .env file.")
        await client.close()

    asyncio.run(_run())


@app.command()
def sync(
    course_id: Optional[int] = typer.Option(None, "--course-id", "-c", help="Sync a specific course ID only"),
    concurrency: int = typer.Option(5, "--concurrency", "-j", help="Concurrent request limit"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh already synced units"),
    all_courses: bool = typer.Option(False, "--all-courses", help="Attempt to sync outlines for non-enrolled catalog courses as well"),
    browser: Optional[str] = typer.Option(None, "--browser", "-b", help="Browser to extract cookies from"),
    sessionid: Optional[str] = typer.Option(None, "--sessionid", help="Maktabkhooneh sessionid cookie"),
    csrftoken: Optional[str] = typer.Option(None, "--csrftoken", help="Maktabkhooneh csrftoken"),
):
    """Crawl & sync enrolled courses, outlines, chapters, units, and video links into SQLite."""
    print_banner()
    cm = CookieManager(sessionid=sessionid, csrftoken=csrftoken, browser=browser)
    client = MaktabClient(cookie_manager=cm)
    syncer = MetadataSyncer(client=client, concurrency=concurrency)

    async def _run():
        await syncer.sync_all(course_id=course_id, force_refresh=force, enrolled_only=not all_courses)
        await client.close()

    asyncio.run(_run())


@app.command(name="search")
def search_catalog(
    query: str = typer.Option("-", "--query", "-q", help="Search keyword (or '-' for all)"),
    max_pages: Optional[int] = typer.Option(None, "--max-pages", "-p", help="Maximum catalog pages to fetch"),
    types: List[str] = typer.Option(["MAKTAB", "PLUS", "HAMAYESH"], "--type", "-t", help="Course types (MAKTAB, PLUS, HAMAYESH)"),
    browser: Optional[str] = typer.Option(None, "--browser", "-b", help="Browser to extract cookies from"),
):
    """Search and crawl public catalog courses into SQLite database."""
    print_banner()
    cm = CookieManager(browser=browser)
    client = MaktabClient(cookie_manager=cm)
    syncer = CatalogSyncer(client=client)

    async def _run():
        await syncer.search_and_sync_catalog(query=query, types=types, max_pages=max_pages)
        await client.close()

    asyncio.run(_run())


@app.command(name="landing")
def sync_landings(
    course_id: Optional[int] = typer.Option(None, "--course-id", "-c", help="Sync specific course landing metadata"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh existing landing details"),
    concurrency: int = typer.Option(5, "--concurrency", "-j", help="Concurrent workers"),
    browser: Optional[str] = typer.Option(None, "--browser", "-b", help="Browser to extract cookies from"),
):
    """Sync rich public landing page metadata (learning goals, topics, prerequisites, HTML descriptions)."""
    print_banner()
    cm = CookieManager(browser=browser)
    client = MaktabClient(cookie_manager=cm)
    syncer = CatalogSyncer(client=client, concurrency=concurrency)

    async def _run():
        await syncer.sync_landing_details(course_id=course_id, force_refresh=force)
        await client.close()

    asyncio.run(_run())


@app.command(name="enroll")
def enroll_course(
    course_id: Optional[int] = typer.Option(None, "--course-id", "-c", help="Course ID to register/enroll into"),
    bulk: bool = typer.Option(False, "--bulk", help="Bulk enroll in all available catalog courses"),
    max_courses: int = typer.Option(30, "--max", help="Max courses to bulk enroll"),
    browser: Optional[str] = typer.Option(None, "--browser", "-b", help="Browser to extract cookies from"),
):
    """Register and enroll into a course (or bulk enroll into discovered catalog courses)."""
    print_banner()
    cm = CookieManager(browser=browser)
    client = MaktabClient(cookie_manager=cm)
    syncer = CatalogSyncer(client=client)

    async def _run():
        if bulk:
            await syncer.bulk_enroll(max_courses=max_courses)
        elif course_id:
            res = await syncer.check_actions_and_enroll(course_id)
            if res.get("success"):
                print_success(res.get("message", "Enrolled successfully!"))
            else:
                print_error(res.get("error", "Enrollment failed."))
        else:
            print_warning("Please provide --course-id <id> or --bulk")
        await client.close()

    asyncio.run(_run())


@app.command(name="reviews")
def sync_reviews(
    course_id: Optional[int] = typer.Option(None, "--course-id", "-c", help="Course ID to collect student reviews for"),
    enrolled_only: bool = typer.Option(False, "--enrolled-only", help="Only sync reviews for enrolled courses"),
    concurrency: int = typer.Option(5, "--concurrency", "-j", help="Concurrent review workers"),
    browser: Optional[str] = typer.Option(None, "--browser", "-b", help="Browser to extract cookies from"),
):
    """Crawl and store student reviews, ratings, and instructor replies into SQLite."""
    print_banner()
    cm = CookieManager(browser=browser)
    client = MaktabClient(cookie_manager=cm)
    syncer = ReviewsSyncer(client=client, concurrency=concurrency)

    async def _run():
        await syncer.sync_all_reviews(course_id=course_id, enrolled_only=enrolled_only)
        await client.close()

    asyncio.run(_run())


@app.command(name="download")
def download(
    course_id: Optional[int] = typer.Option(None, "--course-id", "-c", help="Download specific course ID only"),
    quality: str = typer.Option("1080p", "--quality", "-q", help="Preferred quality (1080p, 720p, 480p, best, worst, all)"),
    output_dir: Path = typer.Option(Path("downloads"), "--output", "-o", help="Target output directory"),
    concurrency: int = typer.Option(3, "--concurrency", "-j", help="Concurrent downloads limit"),
    include_completed: bool = typer.Option(False, "--all", help="Re-download already completed files"),
    browser: Optional[str] = typer.Option(None, "--browser", "-b", help="Browser to extract cookies from"),
):
    """Download course videos, attachments, and subtitles."""
    print_banner()
    cm = CookieManager(browser=browser)
    client = MaktabClient(cookie_manager=cm)
    downloader = ResourceDownloader(client=client, download_dir=output_dir, concurrency=concurrency)

    async def _run():
        await downloader.download_course_resources(
            course_id=course_id,
            preferred_quality=quality,
            include_completed=include_completed,
        )
        await client.close()

    asyncio.run(_run())


@app.command(name="size")
def check_size(
    course_id: Optional[int] = typer.Option(None, "--course-id", "-c", help="Inspect size for a specific course ID"),
    quality: str = typer.Option("1080p", "--quality", "-q", help="Preferred quality (1080p, 720p, 480p, best, worst, all)"),
    concurrency: int = typer.Option(10, "--concurrency", "-j", help="Concurrent inspection workers"),
    browser: Optional[str] = typer.Option(None, "--browser", "-b", help="Browser to extract cookies from"),
):
    """Inspect total download size across courses without downloading files (HTTP HEAD / Range)."""
    print_banner()
    cm = CookieManager(browser=browser)
    client = MaktabClient(cookie_manager=cm)
    inspector = SizeInspector(client=client, concurrency=concurrency)

    async def _run():
        result = await inspector.inspect_course_sizes(course_id=course_id, preferred_quality=quality)
        await client.close()

        if result["total_items"] == 0:
            print_warning("No resources found. Run `maktab sync` first!")
            return

        courses = await repo_instance.get_all_courses()
        if course_id:
            courses = [c for c in courses if c["id"] == course_id]

        table = Table(title=f"📊 Estimated Download Sizes [{quality}]", border_style="cyan")
        table.add_column("Course ID", style="cyan", justify="right")
        table.add_column("Course Title", style="bold white")
        table.add_column("Units", justify="center")
        table.add_column("Total Size", style="bold green", justify="right")

        for c in courses:
            c_stats = await repo_instance.get_course_size_stats(course_id=c["id"], preferred_quality=quality)
            table.add_row(
                str(c["id"]),
                str(c["title"]),
                str(c_stats["total_items"]),
                format_bytes(c_stats["total_bytes"]),
            )

        console.print(table)
        print_success(f"Total size across {len(courses)} course(s): [bold green]{result['formatted_size']}[/bold green] ({result['inspected_items']}/{result['total_items']} items calculated)")

    asyncio.run(_run())


@app.command(name="list")
def list_courses(
    enrolled_only: bool = typer.Option(False, "--enrolled-only", help="Show only enrolled courses"),
):
    """List all synced courses, catalog items, reviews and download stats from SQLite database."""
    print_banner()

    async def _run():
        await db_instance.init_db()
        courses = await repo_instance.get_all_courses(enrolled_only=enrolled_only)
        stats = await repo_instance.get_db_stats()

        if not courses:
            print_warning("No courses found in database yet. Run `maktab sync` or `maktab search` first!")
            return

        table = Table(title="🎓 Synced Maktabkhooneh Courses", border_style="cyan")
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Title", style="bold white")
        table.add_column("Publisher / Org", style="magenta")
        table.add_column("Enrolled", justify="center")
        table.add_column("Chapters", justify="center")
        table.add_column("Units", justify="center")
        table.add_column("Reviews", justify="center")
        table.add_column("Videos", justify="center")
        table.add_column("Est. Size", justify="right", style="yellow")
        table.add_column("Progress", style="green", justify="right")

        for c in courses:
            org_name = c["publisher_name"] or c["organization_name"] or "-"
            enrolled_badge = "[green]✓ Yes[/green]" if c["is_enrolled"] else "[dim]No[/dim]"
            progress_pct = f"{c['progress']:.1f}%" if c["progress"] is not None else "0.0%"
            videos_status = f"{c['downloaded_resources_count']}/{c['total_resources_count']}"
            c_stats = await repo_instance.get_course_size_stats(course_id=c["id"], preferred_quality="1080p")
            size_label = format_bytes(c_stats["total_bytes"]) if c_stats["total_bytes"] > 0 else "-"

            table.add_row(
                str(c["id"]),
                str(c["title"]),
                str(org_name),
                enrolled_badge,
                str(c["actual_chapters_count"]),
                str(c["actual_units_count"]),
                str(c["actual_reviews_count"]),
                videos_status,
                size_label,
                progress_pct,
            )

        console.print(table)
        console.print(
            f"\n[dim]Summary: {stats['courses']} Courses ({stats['courses_enrolled']} Enrolled) | {stats['chapters']} Chapters | "
            f"{stats['units_synced']}/{stats['units_total']} Units Synced | "
            f"{stats['reviews_total']} Reviews | "
            f"{stats['resources_downloaded']}/{stats['resources_total']} Videos Downloaded[/dim]\n"
        )

    asyncio.run(_run())


@app.command()
def info(
    course_id: int = typer.Argument(..., help="Course ID to inspect"),
    inspect_sizes: bool = typer.Option(False, "--calc-size", "-s", help="Calculate exact remote file sizes via HTTP"),
    show_reviews: bool = typer.Option(False, "--reviews", "-r", help="Display top reviews for this course"),
):
    """Show detailed hierarchy of chapters, units, landing details, and video streams for a course."""
    print_banner()

    async def _run():
        await db_instance.init_db()
        course = await repo_instance.get_course_by_id(course_id)
        if not course:
            print_error(f"Course with ID {course_id} not found in database.")
            return

        if inspect_sizes:
            client = MaktabClient()
            inspector = SizeInspector(client=client)
            await inspector.inspect_course_sizes(course_id=course_id, preferred_quality="all")
            await client.close()

        tree = Tree(f"[bold cyan]Course: {course['title']} [ID: {course['id']}][/bold cyan]")
        
        # Details branch
        details_branch = tree.add("[bold green]📋 Course Overview & Landing Info[/bold green]")
        if course["level"]:
            details_branch.add(f"[dim]Level: {course['level']} | Duration: {course['course_effort_time'] or '-'} | Students: {course['no_of_students']}[/dim]")
        if course["learning_goals_json"]:
            try:
                goals = json.loads(course["learning_goals_json"])
                if goals:
                    goals_node = details_branch.add("[cyan]Learning Goals:[/cyan]")
                    for g in goals[:4]:
                        goals_node.add(f"[dim]• {g}[/dim]")
            except Exception:
                pass

        chapters = await repo_instance.get_chapters_for_course(course_id)

        for ch in chapters:
            ch_branch = tree.add(f"[bold yellow]Chapter {ch['order_num']}: {ch['title']}[/bold yellow]")
            units = await repo_instance.get_units_for_chapter(ch["id"])

            for u in units:
                duration_str = format_duration(u["duration"])
                u_branch = ch_branch.add(f"[white]Unit {u['order_num']}: {u['title']} ({duration_str})[/white]")
                resources = await repo_instance.get_resources_for_unit(u["id"])

                for r in resources:
                    total_b = r["total_bytes"] or (int(r["size_mb"] * 1024 * 1024) if r["size_mb"] else None)
                    size_str = format_bytes(total_b) if total_b else "size unknown"
                    status_emoji = "✓" if r["download_status"] == "completed" else "○"
                    u_branch.add(f"[dim]{status_emoji} [{r['quality']}] {r['display_title'] or r['quality_display']} ({size_str})[/dim]")

        if show_reviews:
            reviews = await repo_instance.get_reviews_for_course(course_id)
            if reviews:
                rev_branch = tree.add(f"[bold magenta]⭐ Student Reviews ({len(reviews)})[/bold magenta]")
                for rev in reviews[:5]:
                    stars = "★" * rev["rate"] + "☆" * (5 - rev["rate"])
                    reviewer = rev["user_full_name"] or "Student"
                    rev_branch.add(f"[yellow]{stars}[/yellow] [bold]{reviewer}:[/bold] [dim]{rev['review_description'][:80]}...[/dim]")

        console.print(tree)

    asyncio.run(_run())


@app.command()
def export(
    output_file: Path = typer.Option(Path("maktab_export.json"), "--output", "-o", help="Output JSON file path"),
    course_id: Optional[int] = typer.Option(None, "--course-id", "-c", help="Export specific course ID"),
    include_reviews: bool = typer.Option(True, "--reviews/--no-reviews", help="Include student reviews in export"),
):
    """Export SQLite database records into a JSON dump."""
    print_banner()

    async def _run():
        await db_instance.init_db()
        courses = await repo_instance.get_all_courses()
        export_data = []

        for c in courses:
            if course_id and c["id"] != course_id:
                continue

            c_dict = dict(c)
            c_dict["chapters"] = []
            chapters = await repo_instance.get_chapters_for_course(c["id"])

            for ch in chapters:
                ch_dict = dict(ch)
                ch_dict["units"] = []
                units = await repo_instance.get_units_for_chapter(ch["id"])

                for u in units:
                    u_dict = dict(u)
                    u_dict["resources"] = [dict(r) for r in await repo_instance.get_resources_for_unit(u["id"])]
                    ch_dict["units"].append(u_dict)

                c_dict["chapters"].append(ch_dict)

            if include_reviews:
                reviews = await repo_instance.get_reviews_for_course(c["id"])
                c_dict["reviews"] = [dict(r) for r in reviews]

            export_data.append(c_dict)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        print_success(f"Exported data for {len(export_data)} courses to [cyan]{output_file}[/cyan]")

    asyncio.run(_run())


# -----------------------------------------------------------------
# Telegram Commands
# -----------------------------------------------------------------
@telegram_app.command(name="start")
def start_telegram_bot(
    target_chat: Optional[str] = typer.Option(None, "--target", "-t", help="Target channel / chat (e.g. @channel or 'me')"),
    max_storage_mb: float = typer.Option(2048.0, "--max-storage", "-m", help="Host storage limit in MB (default: 2048 MB = 2GB)"),
    api_id: Optional[int] = typer.Option(None, "--api-id", help="Telegram API ID"),
    api_hash: Optional[str] = typer.Option(None, "--api-hash", help="Telegram API Hash"),
    bot_token: Optional[str] = typer.Option(None, "--bot-token", help="Telegram Bot Token (optional)"),
):
    """Start Telegram listener for /maktab <start> <end> and /upload <course_id> commands."""
    print_banner()
    tg_manager = TelegramManager(api_id=api_id, api_hash=api_hash, bot_token=bot_token)
    bot_service = TelegramBotService(
        telegram_manager=tg_manager,
        target_chat=target_chat,
        max_storage_mb=max_storage_mb,
    )

    async def _run():
        await bot_service.start()

    asyncio.run(_run())


@telegram_app.command(name="upload")
def upload_course_telegram(
    course_id: int = typer.Argument(..., help="Course ID to download and upload to Telegram"),
    target_chat: str = typer.Option("me", "--target", "-t", help="Target channel / group / chat (e.g. @channel or 'me')"),
    quality: str = typer.Option("1080p", "--quality", "-q", help="Preferred video quality (1080p, 720p, 480p)"),
    max_storage_mb: float = typer.Option(2048.0, "--max-storage", "-m", help="Maximum temporary host storage in MB"),
    api_id: Optional[int] = typer.Option(None, "--api-id", help="Telegram API ID"),
    api_hash: Optional[str] = typer.Option(None, "--api-hash", help="Telegram API Hash"),
    bot_token: Optional[str] = typer.Option(None, "--bot-token", help="Telegram Bot Token (optional)"),
    browser: Optional[str] = typer.Option(None, "--browser", "-b", help="Browser to extract Maktab cookies from"),
):
    """Download single course and upload to Telegram with automatic local file cleanup."""
    print_banner()
    cm = CookieManager(browser=browser)
    client = MaktabClient(cookie_manager=cm)
    tg_manager = TelegramManager(api_id=api_id, api_hash=api_hash, bot_token=bot_token)
    uploader = CourseTelegramUploader(
        telegram_manager=tg_manager,
        maktab_client=client,
        target_chat=target_chat,
        max_storage_mb=max_storage_mb,
        preferred_quality=quality,
    )

    async def _run():
        await uploader.upload_course(course_id=course_id)
        await client.close()
        await tg_manager.close()

    asyncio.run(_run())


@telegram_app.command(name="upload-range")
def upload_course_range_telegram(
    start_index: int = typer.Argument(..., help="Start course ID or 1-based index in database"),
    end_index: int = typer.Argument(..., help="End course ID or 1-based index in database"),
    target_chat: str = typer.Option("me", "--target", "-t", help="Target channel / group / chat (e.g. @channel or 'me')"),
    quality: str = typer.Option("1080p", "--quality", "-q", help="Preferred video quality (1080p, 720p, 480p)"),
    max_storage_mb: float = typer.Option(2048.0, "--max-storage", "-m", help="Maximum temporary host storage in MB"),
    api_id: Optional[int] = typer.Option(None, "--api-id", help="Telegram API ID"),
    api_hash: Optional[str] = typer.Option(None, "--api-hash", help="Telegram API Hash"),
    bot_token: Optional[str] = typer.Option(None, "--bot-token", help="Telegram Bot Token (optional)"),
    browser: Optional[str] = typer.Option(None, "--browser", "-b", help="Browser to extract Maktab cookies from"),
):
    """Sequentially download and upload a range of courses to Telegram (like /maktab <start> <end>)."""
    print_banner()
    cm = CookieManager(browser=browser)
    client = MaktabClient(cookie_manager=cm)
    tg_manager = TelegramManager(api_id=api_id, api_hash=api_hash, bot_token=bot_token)
    uploader = CourseTelegramUploader(
        telegram_manager=tg_manager,
        maktab_client=client,
        target_chat=target_chat,
        max_storage_mb=max_storage_mb,
        preferred_quality=quality,
    )

    async def _run():
        await uploader.upload_course_range(start_index=start_index, end_index=end_index)
        await client.close()
        await tg_manager.close()

    asyncio.run(_run())


if __name__ == "__main__":
    app()
