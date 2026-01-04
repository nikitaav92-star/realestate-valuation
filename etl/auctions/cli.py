"""
CLI for auction lots collection.

Usage:
    python -m etl.auctions.cli collect --source fssp --city Москва
    python -m etl.auctions.cli stats
    python -m etl.auctions.cli list --source bankrupt --limit 20
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import Optional

import click

from .models import AuctionSource
from . import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_parser(source: str):
    """Get parser instance for source type."""
    source_map = {
        'fssp': 'etl.auctions.parsers.fssp_parser',
        'bankrupt': 'etl.auctions.parsers.fedresurs_parser',
        'bank_pledge': 'etl.auctions.parsers.bank_parser',
        'dgi_moscow': 'etl.auctions.parsers.dgi_parser',
    }

    if source not in source_map:
        raise ValueError(f"Unknown source: {source}. Available: {list(source_map.keys())}")

    # Try to import parser
    try:
        module_name = source_map[source]
        module = __import__(module_name, fromlist=['Parser'])
        return module.Parser()
    except ImportError as e:
        logger.warning(f"Parser for {source} not implemented yet: {e}")
        # Return mock parser for testing
        from .base_parser import MockAuctionParser
        mock = MockAuctionParser()
        mock.source_type = AuctionSource(source)
        mock.platform_name = f"Mock {source}"
        return mock


@click.group()
def cli():
    """Auction lots collection CLI."""
    pass


@cli.command()
@click.option('--source', '-s', type=click.Choice(['fssp', 'bankrupt', 'bank_pledge', 'dgi_moscow', 'all']),
              default='all', help='Auction source to collect from')
@click.option('--city', '-c', default='Москва', help='City to filter')
@click.option('--max-pages', '-p', default=10, help='Max pages to fetch')
@click.option('--dry-run', is_flag=True, help='Do not save to database')
def collect(source: str, city: str, max_pages: int, dry_run: bool):
    """Collect auction lots from sources."""

    async def _collect():
        sources = ['fssp', 'bankrupt', 'bank_pledge', 'dgi_moscow'] if source == 'all' else [source]

        total_collected = 0
        total_skipped = 0

        for src in sources:
            logger.info(f"Collecting from {src}...")

            try:
                parser = get_parser(src)

                async with parser:
                    lots = await parser.collect(city=city, max_pages=max_pages)

                logger.info(f"{src}: Found {len(lots)} valid lots")

                if not dry_run and lots:
                    conn = await db.get_connection()
                    try:
                        for lot in lots:
                            lot_id = await db.upsert_lot(conn, lot)
                            logger.debug(f"Saved lot {lot.external_id} -> id={lot_id}")

                            # Record initial price in history
                            if lot.current_price:
                                await db.record_price_history(
                                    conn, lot_id,
                                    float(lot.current_price),
                                    "current"
                                )

                        total_collected += len(lots)
                    finally:
                        await conn.close()
                else:
                    total_collected += len(lots)
                    if dry_run:
                        logger.info(f"[DRY RUN] Would save {len(lots)} lots")

            except Exception as e:
                logger.error(f"Error collecting from {src}: {e}")
                continue

        logger.info(f"Total collected: {total_collected} lots")

    asyncio.run(_collect())


@cli.command()
@click.option('--source', '-s', type=click.Choice(['fssp', 'bankrupt', 'bank_pledge', 'dgi_moscow']),
              help='Filter by source')
@click.option('--city', '-c', help='Filter by city')
@click.option('--limit', '-l', default=20, help='Number of lots to show')
@click.option('--offset', '-o', default=0, help='Offset for pagination')
def list(source: Optional[str], city: Optional[str], limit: int, offset: int):
    """List active auction lots."""

    async def _list():
        conn = await db.get_connection()
        try:
            lots = await db.get_active_lots(conn, source, city, limit, offset)

            if not lots:
                click.echo("No active lots found")
                return

            click.echo(f"\n{'='*80}")
            click.echo(f"Active Auction Lots ({len(lots)} shown)")
            click.echo(f"{'='*80}\n")

            for lot in lots:
                click.echo(f"ID: {lot['id']} | {lot['source_type'].upper()}")
                click.echo(f"  Лот: {lot['lot_number'] or 'N/A'}")
                click.echo(f"  {lot['title'] or 'Без названия'}")
                click.echo(f"  Адрес: {lot['address'] or 'N/A'}")
                click.echo(f"  Площадь: {lot['area_total'] or 'N/A'} м² | Комнат: {lot['rooms'] or 'N/A'}")
                click.echo(f"  Цена: {lot['current_price']:,.0f} ₽" if lot['current_price'] else "  Цена: N/A")
                if lot.get('discount_from_market'):
                    click.echo(f"  Дисконт от рынка: {lot['discount_from_market']:.1f}%")
                click.echo(f"  Дата торгов: {lot['auction_date']}")
                click.echo(f"  Ссылка: {lot['source_url'] or 'N/A'}")
                click.echo()

        finally:
            await conn.close()

    asyncio.run(_list())


@cli.command()
def stats():
    """Show auction statistics."""

    async def _stats():
        conn = await db.get_connection()
        try:
            stats = await db.get_stats(conn)

            click.echo(f"\n{'='*60}")
            click.echo("AUCTION STATISTICS")
            click.echo(f"{'='*60}\n")

            totals = stats['totals']
            click.echo(f"Total lots:     {totals['total'] or 0:,}")
            click.echo(f"Active lots:    {totals['active'] or 0:,}")
            click.echo(f"Completed:      {totals['completed'] or 0:,}")
            if totals['avg_price']:
                click.echo(f"Avg price:      {totals['avg_price']:,.0f} ₽")
            if totals['avg_price_per_sqm']:
                click.echo(f"Avg price/m²:   {totals['avg_price_per_sqm']:,.0f} ₽")

            click.echo(f"\n{'='*60}")
            click.echo("BY SOURCE")
            click.echo(f"{'='*60}\n")

            for row in stats['by_source']:
                click.echo(f"{row['source_type']:15} | {row['status']:12} | {row['count']:,} lots")

        finally:
            await conn.close()

    asyncio.run(_stats())


@cli.command()
@click.option('--lot-id', '-l', type=int, help='Specific lot ID to compare')
@click.option('--all', 'compare_all', is_flag=True, help='Compare all active lots')
def compare_market(lot_id: Optional[int], compare_all: bool):
    """Compare auction prices with market values."""

    async def _compare():
        # Import valuation API
        try:
            from api.v1.valuation import estimate_price
        except ImportError:
            click.echo("Valuation API not available")
            return

        conn = await db.get_connection()
        try:
            if lot_id:
                lots = [await db.get_lot_by_id(conn, lot_id)]
                lots = [l for l in lots if l]
            elif compare_all:
                lots = await db.get_active_lots(conn, limit=1000)
            else:
                click.echo("Specify --lot-id or --all")
                return

            if not lots:
                click.echo("No lots found")
                return

            click.echo(f"Comparing {len(lots)} lots with market prices...\n")

            for lot in lots:
                if not lot['lat'] or not lot['lon'] or not lot['area_total']:
                    click.echo(f"Lot {lot['id']}: Missing coordinates or area, skipping")
                    continue

                try:
                    # Get market estimate
                    result = await estimate_price(
                        lat=float(lot['lat']),
                        lon=float(lot['lon']),
                        area_total=float(lot['area_total']),
                        rooms=lot['rooms'] or 1,
                    )

                    market_price = result.get('estimated_price')
                    if market_price and lot['current_price']:
                        discount = ((market_price - float(lot['current_price'])) / market_price) * 100

                        # Save comparison
                        from .models import AuctionMarketComparison
                        comparison = AuctionMarketComparison(
                            lot_id=lot['id'],
                            market_price_estimate=market_price,
                            market_price_per_sqm=result.get('estimated_price_per_sqm'),
                            estimation_method=result.get('method_used'),
                            estimation_confidence=result.get('confidence'),
                            discount_from_market=discount,
                            comparables_count=result.get('comparables_count'),
                        )
                        await db.update_market_comparison(conn, lot['id'], comparison)

                        click.echo(
                            f"Lot {lot['id']}: "
                            f"Auction {lot['current_price']:,.0f} ₽ vs "
                            f"Market {market_price:,.0f} ₽ = "
                            f"Discount {discount:.1f}%"
                        )

                except Exception as e:
                    click.echo(f"Lot {lot['id']}: Error - {e}")

        finally:
            await conn.close()

    asyncio.run(_compare())


@cli.command()
def init_db():
    """Initialize auctions database schema."""

    async def _init():
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'db', 'schema_auctions.sql'
        )

        if not os.path.exists(schema_path):
            click.echo(f"Schema file not found: {schema_path}")
            return

        with open(schema_path) as f:
            schema_sql = f.read()

        conn = await db.get_connection()
        try:
            await conn.execute(schema_sql)
            click.echo("Auctions database schema initialized successfully!")
        except Exception as e:
            click.echo(f"Error initializing schema: {e}")
        finally:
            await conn.close()

    asyncio.run(_init())


if __name__ == '__main__':
    cli()
