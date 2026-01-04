"""CLI for AI photo analysis."""
import asyncio
import logging
import os
import sys
from pathlib import Path

import click
import psycopg2
from psycopg2.extras import DictCursor

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from etl.ai_evaluator import (
    PhotoAnalyzer,
    BatchProcessor,
    CostOptimizer,
    AnalysisStrategy,
    AIProvider,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

LOGGER = logging.getLogger(__name__)


def get_db_connection():
    """Get database connection."""
    dsn = os.getenv("PG_DSN") or (
        f"postgresql://{os.getenv('PG_USER', 'realuser')}:"
        f"{os.getenv('PG_PASS', 'strongpass')}@"
        f"{os.getenv('PG_HOST', 'localhost')}:"
        f"{os.getenv('PG_PORT', '5432')}/"
        f"{os.getenv('PG_DB', 'realdb')}"
    )
    return psycopg2.connect(dsn)


@click.group()
def cli():
    """AI photo analysis CLI."""
    pass


@cli.command()
@click.option("--strategy", type=click.Choice(["all", "important", "new"]), default="important")
@click.option("--limit", type=int, help="Limit number of listings to analyze")
@click.option("--provider", type=click.Choice(["openai", "anthropic"]), default="openai")
@click.option("--detail", type=click.Choice(["low", "high"]), default="low")
def estimate(strategy: str, limit: int, provider: str, detail: str):
    """Estimate cost for AI analysis."""
    
    click.echo("=" * 80)
    click.echo("💰 COST ESTIMATION")
    click.echo("=" * 80)
    
    # Get listing count
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if strategy == "all":
                query = "SELECT COUNT(*) FROM listings WHERE is_active = TRUE"
            elif strategy == "important":
                query = """
                SELECT COUNT(*) FROM listings 
                WHERE is_active = TRUE 
                    AND (price > 15000000 
                         OR price / area_total > 250000 
                         OR price / area_total < 150000)
                """
            elif strategy == "new":
                query = """
                SELECT COUNT(*) FROM listings 
                WHERE is_active = TRUE 
                    AND first_seen > NOW() - INTERVAL '1 day'
                """
            
            cur.execute(query)
            count = cur.fetchone()[0]
            
            if limit:
                count = min(count, limit)
    finally:
        conn.close()
    
    # Calculate cost
    optimizer = CostOptimizer(AnalysisStrategy(strategy))
    cost_per_photo = 0.00425 if provider == "openai" and detail == "low" else 0.01275
    
    estimate = optimizer.estimate_cost(
        count,
        photos_per_listing=1,
        cost_per_photo=cost_per_photo,
    )
    
    click.echo(f"\nStrategy: {strategy}")
    click.echo(f"Provider: {provider}")
    click.echo(f"Detail: {detail}")
    click.echo(f"\nListings to analyze: {estimate['listings_count']:,}")
    click.echo(f"Total photos: {estimate['total_photos']:,}")
    click.echo(f"Cost per photo: ${estimate['cost_per_photo']:.5f}")
    click.echo(f"Total cost: ${estimate['total_cost_usd']:.2f}")
    click.echo(f"Estimated time: {estimate['estimated_time_hours']:.1f} hours")
    click.echo("=" * 80)


@cli.command()
@click.option("--strategy", type=click.Choice(["all", "important", "new"]), default="important")
@click.option("--limit", type=int, help="Limit number of listings")
@click.option("--provider", type=click.Choice(["openai", "anthropic"]), default="openai")
@click.option("--dry-run", is_flag=True, help="Dry run (don't actually analyze)")
def analyze(strategy: str, limit: int, provider: str, dry_run: bool):
    """Run AI analysis on listings."""
    
    click.echo("=" * 80)
    click.echo("🤖 AI PHOTO ANALYSIS")
    click.echo("=" * 80)
    
    # Get listings with photos
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            # Get listings that need analysis
            query = """
            SELECT 
                l.id AS listing_id,
                lph.photo_url,
                l.price,
                l.area_total,
                EXTRACT(EPOCH FROM (NOW() - l.first_seen)) / 86400 AS days_ago
            FROM listings l
            JOIN listing_photos lph ON l.id = lph.listing_id
            LEFT JOIN listing_condition_ratings lcr ON l.id = lcr.listing_id
            WHERE l.is_active = TRUE
                AND lph.is_main = TRUE
                AND lcr.id IS NULL  -- Not yet analyzed
            """
            
            # Add strategy filter
            if strategy == "important":
                query += """ AND (
                    l.price > 15000000 
                    OR l.price / l.area_total > 250000 
                    OR l.price / l.area_total < 150000
                )"""
            elif strategy == "new":
                query += " AND l.first_seen > NOW() - INTERVAL '1 day'"
            
            if limit:
                query += f" LIMIT {limit}"
            
            cur.execute(query)
            listings = cur.fetchall()
    finally:
        conn.close()
    
    if not listings:
        click.echo("⚠️ No listings found for analysis")
        return
    
    click.echo(f"\nFound {len(listings)} listings to analyze")
    
    if dry_run:
        click.echo("\n🔍 DRY RUN - would analyze:")
        for i, listing in enumerate(listings[:10], 1):
            click.echo(f"  {i}. Listing {listing['listing_id']}: {listing['photo_url'][:60]}...")
        if len(listings) > 10:
            click.echo(f"  ... and {len(listings) - 10} more")
        return
    
    # Confirm
    if not click.confirm(f"\nAnalyze {len(listings)} listings?"):
        click.echo("Aborted.")
        return
    
    # Process
    listings_with_photos = [
        (row['listing_id'], row['photo_url'])
        for row in listings
    ]
    
    processor = BatchProcessor(
        provider=AIProvider(provider),
        batch_size=50,
        concurrency=10,
        detail="low",
    )
    
    click.echo("\n🚀 Starting analysis...\n")
    
    # Run async
    stats = asyncio.run(processor.process_listings(listings_with_photos))
    
    # Results
    click.echo("\n" + "=" * 80)
    click.echo("📊 ANALYSIS COMPLETE")
    click.echo("=" * 80)
    click.echo(f"Analyzed: {stats.total_analyzed}")
    click.echo(f"Errors: {len(stats.errors)}")
    click.echo(f"Total cost: ${stats.total_cost_usd:.2f}")
    click.echo(f"Avg cost: ${stats.avg_cost():.4f}")
    click.echo(f"Total time: {stats.total_time_sec / 60:.1f} minutes")
    click.echo(f"Avg time: {stats.avg_time():.1f}s per listing")
    click.echo("=" * 80)


if __name__ == "__main__":
    cli()

