"""
HTML Report Generator Module
Генерация брендированных HTML-отчётов об оценке недвижимости.
"""

import os
import uuid
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from jinja2 import Environment, FileSystemLoader
import psycopg2
from psycopg2.extras import RealDictCursor


# Configuration
BASE_URL = os.getenv("REPORT_BASE_URL", "https://rating.ourdocs.org")
REPORTS_DIR = os.getenv("REPORTS_DIR", "/home/ubuntu/realestate/web/static/reports")
REPORT_EXPIRY_DAYS = int(os.getenv("REPORT_EXPIRY_DAYS", "5"))


# Database connection
def get_db_connection():
    """Get database connection."""
    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")
    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)


def ensure_reports_table():
    """Create reports table if not exists."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS valuation_reports (
            id SERIAL PRIMARY KEY,
            report_uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
            cian_id BIGINT,
            address TEXT NOT NULL,
            area_total REAL NOT NULL,
            rooms INTEGER,
            floor INTEGER,
            total_floors INTEGER,

            seller_price REAL,
            interest_price REAL NOT NULL,
            interest_price_per_sqm REAL NOT NULL,
            market_price_low REAL,
            market_price_high REAL,

            report_data JSONB NOT NULL,
            html_content TEXT,

            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP,

            telegram_user_id BIGINT,
            telegram_chat_id BIGINT
        );

        CREATE INDEX IF NOT EXISTS idx_reports_uuid ON valuation_reports(report_uuid);
        CREATE INDEX IF NOT EXISTS idx_reports_cian_id ON valuation_reports(cian_id);
        CREATE INDEX IF NOT EXISTS idx_reports_created ON valuation_reports(created_at DESC);
    """)
    conn.commit()
    cur.close()
    conn.close()


class HTMLReportGenerator:
    """Generator for branded HTML valuation reports."""

    def __init__(self):
        # Template directory
        template_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'web', 'templates', 'reports'
        )
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True
        )

        # Ensure table exists
        try:
            ensure_reports_table()
        except Exception as e:
            print(f"Warning: Could not create reports table: {e}")

    def generate_report(
        self,
        # Object info
        address: str,
        area_total: float,
        rooms: Optional[int] = None,
        floor: Optional[int] = None,
        total_floors: Optional[int] = None,
        district: Optional[str] = None,
        metro: Optional[str] = None,
        cian_id: Optional[int] = None,
        seller_price: Optional[float] = None,

        # Rosreestr data
        rosreestr_deals: Optional[List[Dict]] = None,

        # CIAN analogs
        cian_analogs: Optional[List[Dict]] = None,
        cian_filter_description: Optional[str] = None,

        # Statistics
        analogs_count: Optional[int] = None,
        avg_area: Optional[float] = None,
        avg_price_per_sqm: float = 0,
        median_price_per_sqm: float = 0,
        min_price_per_sqm: float = 0,
        max_price_per_sqm: float = 0,

        # BOTTOM-3 calculation
        bottom3_analogs: Optional[List[Dict]] = None,
        bottom3_prices: Optional[List[float]] = None,
        bottom3_avg: float = 0,
        bargain_percent: int = 7,

        # Final prices
        interest_price: float = 0,
        interest_price_per_sqm: float = 0,
        market_price_low: Optional[float] = None,
        market_price_high: Optional[float] = None,
        market_price: Optional[float] = None,
        market_price_per_sqm: Optional[float] = None,

        # Separate source statistics
        rosreestr_count: int = 0,
        rosreestr_median: float = 0,
        cian_count: int = 0,
        cian_median: float = 0,

        # Investment costs (fixed)
        cost_notary: float = 50000,
        cost_duty: float = 4000,
        cost_pip: Optional[float] = None,  # auto-calc: area × 1500
        cost_agent: float = 200000,
        cost_registrar: float = 25000,
        cost_kontur: float = 4000,
        fixed_costs: Optional[float] = None,

        # Investment costs (dynamic)
        has_dynamic_costs: bool = False,
        cost_renovation: Optional[float] = None,
        renovation_per_sqm: float = 50000,
        cost_foreman: float = 100000,
        cost_eviction: Optional[float] = None,
        dynamic_costs: float = 0,
        total_costs: Optional[float] = None,

        # Investment target
        target_monthly_rate: float = 4,  # 4% в месяц
        project_months: int = 3,
        min_profit: float = 1000000,
        tax_rate: float = 6,
        target_profit: Optional[float] = None,
        target_profit_gross: Optional[float] = None,

        # Filter criteria
        filter_criteria: Optional[List[str]] = None,

        # Methodology
        methodology: Optional[List[Dict]] = None,

        # Telegram info
        telegram_user_id: Optional[int] = None,
        telegram_chat_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate HTML report and save to database.

        Returns:
            Dict with report_uuid, report_url, html_content
        """
        # Generate report UUID and URLs
        report_uuid = str(uuid.uuid4())
        report_url = f"/r/{report_uuid}"
        report_url_full = f"{BASE_URL}/r/{report_uuid}"
        expires_at = datetime.now() + timedelta(days=REPORT_EXPIRY_DAYS)

        report_date = datetime.now().strftime("%d %B %Y г.").replace(
            "January", "января"
        ).replace("February", "февраля").replace("March", "марта"
        ).replace("April", "апреля").replace("May", "мая"
        ).replace("June", "июня").replace("July", "июля"
        ).replace("August", "августа").replace("September", "сентября"
        ).replace("October", "октября").replace("November", "ноября"
        ).replace("December", "декабря")

        # Auto-calculate investment parameters
        if cost_pip is None:
            cost_pip = area_total * 1500

        if fixed_costs is None:
            fixed_costs = cost_notary + cost_duty + cost_pip + cost_agent + cost_registrar + cost_kontur

        if total_costs is None:
            total_costs = fixed_costs + dynamic_costs

        # Calculate market price if not provided
        if market_price is None:
            market_price = median_price_per_sqm * area_total
        if market_price_per_sqm is None:
            market_price_per_sqm = median_price_per_sqm

        # Calculate target profit
        total_rate = (target_monthly_rate * project_months) / 100  # e.g., 0.12 for 12%
        if target_profit is None:
            target_profit = market_price * total_rate / (1 + total_rate)
            target_profit = max(target_profit, min_profit)

        # Gross profit (before tax)
        if target_profit_gross is None:
            target_profit_gross = target_profit / (1 - tax_rate / 100)

        # Calculate interest price if not provided
        if interest_price == 0:
            interest_price = market_price - total_costs - target_profit_gross
        if interest_price_per_sqm == 0:
            interest_price_per_sqm = interest_price / area_total

        # Default methodology with investment logic
        if not methodology:
            methodology = [
                {
                    "title": "Источники данных",
                    "description": "Росреестр (без торга — совершённые сделки) + ЦИАН (−7% торг — предложения)"
                },
                {
                    "title": "Исключён старый фонд",
                    "description": "квартиры в домах до 1990 года нерелевантны для современного жилья"
                },
                {
                    "title": f"Целевая доходность {target_monthly_rate}%/мес",
                    "description": f"чистая прибыль {target_monthly_rate * project_months}% за {project_months} мес. после уплаты налога {tax_rate}%"
                },
                {
                    "title": f"Расходы на сделку",
                    "description": f"фиксированные {fixed_costs/1000:.0f}т + ПИП {cost_pip/1000:.0f}т = {total_costs/1000:.0f}т ₽"
                }
            ]

        # Default filter criteria
        if not filter_criteria:
            filter_criteria = [
                f"{rooms or 'Все'}-комнатные квартиры",
                f"Площадь {int(area_total * 0.85)}-{int(area_total * 1.15)} м²",
                "Современные дома (2000+)",
                district or "Москва"
            ]

        # Render template
        template = self.env.get_template('valuation_report.html')
        html_content = template.render(
            # Meta
            report_id=report_uuid[:8].upper(),
            report_date=report_date,
            cian_id=cian_id,

            # Object
            address=address,
            area_total=area_total,
            rooms=rooms,
            floor=floor,
            total_floors=total_floors,
            district=district,
            metro=metro,
            seller_price=seller_price,

            # Data sources
            rosreestr_deals=rosreestr_deals or [],
            cian_analogs=cian_analogs or [],
            cian_filter_description=cian_filter_description,

            # Statistics
            analogs_count=analogs_count or len(cian_analogs or []) + len([d for d in (rosreestr_deals or []) if not d.get('excluded')]),
            avg_area=avg_area or area_total,
            avg_price_per_sqm=avg_price_per_sqm,
            median_price_per_sqm=median_price_per_sqm,
            min_price_per_sqm=min_price_per_sqm,
            max_price_per_sqm=max_price_per_sqm,

            # Filter criteria
            filter_criteria=filter_criteria,

            # BOTTOM-3
            bottom3_analogs=bottom3_analogs or [],
            bottom3_prices=bottom3_prices or [],
            bottom3_avg=bottom3_avg,
            bargain_percent=bargain_percent,

            # Final prices
            interest_price=interest_price,
            interest_price_per_sqm=interest_price_per_sqm,
            market_price=market_price,
            market_price_per_sqm=market_price_per_sqm,
            market_price_low=market_price_low or (median_price_per_sqm * area_total * 0.95),
            market_price_high=market_price_high or (median_price_per_sqm * area_total * 1.05),

            # Source statistics
            rosreestr_count=rosreestr_count,
            rosreestr_median=rosreestr_median,
            cian_count=cian_count,
            cian_median=cian_median,

            # Investment costs
            cost_notary=cost_notary,
            cost_duty=cost_duty,
            cost_pip=cost_pip,
            cost_agent=cost_agent,
            cost_registrar=cost_registrar,
            cost_kontur=cost_kontur,
            fixed_costs=fixed_costs,
            has_dynamic_costs=has_dynamic_costs,
            cost_renovation=cost_renovation,
            renovation_per_sqm=renovation_per_sqm,
            cost_foreman=cost_foreman,
            cost_eviction=cost_eviction,
            dynamic_costs=dynamic_costs,
            total_costs=total_costs,

            # Investment targets
            target_monthly_rate=target_monthly_rate,
            project_months=project_months,
            min_profit=min_profit,
            tax_rate=tax_rate,
            target_profit=target_profit,
            target_profit_gross=target_profit_gross,

            # Methodology
            methodology=methodology,

            # URLs for buttons
            report_url_full=report_url_full,
        )

        # Prepare report data for storage
        report_data = {
            "address": address,
            "area_total": area_total,
            "rooms": rooms,
            "floor": floor,
            "total_floors": total_floors,
            "district": district,
            "metro": metro,
            "cian_id": cian_id,
            "seller_price": seller_price,
            "rosreestr_deals": rosreestr_deals,
            "cian_analogs": cian_analogs,
            "statistics": {
                "analogs_count": analogs_count,
                "avg_area": avg_area,
                "avg_price_per_sqm": avg_price_per_sqm,
                "median_price_per_sqm": median_price_per_sqm,
                "min_price_per_sqm": min_price_per_sqm,
                "max_price_per_sqm": max_price_per_sqm,
            },
            "bottom3": {
                "analogs": bottom3_analogs,
                "prices": bottom3_prices,
                "avg": bottom3_avg,
                "bargain_percent": bargain_percent,
            },
            "result": {
                "interest_price": interest_price,
                "interest_price_per_sqm": interest_price_per_sqm,
                "market_price_low": market_price_low,
                "market_price_high": market_price_high,
            },
            "methodology": methodology,
            "filter_criteria": filter_criteria,
        }

        # Save HTML to disk
        html_file_path = None
        try:
            os.makedirs(REPORTS_DIR, exist_ok=True)
            html_filename = f"{report_uuid}.html"
            html_file_path = os.path.join(REPORTS_DIR, html_filename)
            with open(html_file_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"Report saved to: {html_file_path}")
        except Exception as e:
            print(f"Error saving report to disk: {e}")

        # Save to database
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO valuation_reports (
                    report_uuid, cian_id, address, area_total, rooms, floor, total_floors,
                    seller_price, interest_price, interest_price_per_sqm,
                    market_price_low, market_price_high,
                    report_data, html_content,
                    expires_at,
                    telegram_user_id, telegram_chat_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                RETURNING id
            """, (
                report_uuid, cian_id, address, area_total, rooms, floor, total_floors,
                seller_price, interest_price, interest_price_per_sqm,
                market_price_low, market_price_high,
                json.dumps(report_data, ensure_ascii=False, default=str),
                html_content,
                expires_at,
                telegram_user_id, telegram_chat_id
            ))

            report_id = cur.fetchone()['id']
            conn.commit()
            cur.close()
            conn.close()

        except Exception as e:
            print(f"Error saving report to database: {e}")
            report_id = None

        return {
            "report_uuid": report_uuid,
            "report_id": report_id,
            "report_url": report_url,
            "report_url_full": report_url_full,
            "html_file_path": html_file_path,
            "html_content": html_content,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now().isoformat(),
        }

    def get_report_by_uuid(self, report_uuid: str) -> Optional[Dict]:
        """Get report by UUID."""
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            cur.execute("""
                SELECT * FROM valuation_reports
                WHERE report_uuid = %s
            """, (report_uuid,))

            result = cur.fetchone()
            cur.close()
            conn.close()

            if result:
                return dict(result)
            return None

        except Exception as e:
            print(f"Error getting report: {e}")
            return None

    def get_report_html(self, report_uuid: str) -> Optional[str]:
        """Get HTML content by UUID."""
        report = self.get_report_by_uuid(report_uuid)
        if report:
            return report.get('html_content')
        return None


# Singleton instance
_generator = None

def get_generator() -> HTMLReportGenerator:
    """Get singleton generator instance."""
    global _generator
    if _generator is None:
        _generator = HTMLReportGenerator()
    return _generator


def generate_valuation_report(**kwargs) -> Dict[str, Any]:
    """Convenience function to generate report."""
    return get_generator().generate_report(**kwargs)


def get_report_by_uuid(report_uuid: str) -> Optional[Dict]:
    """Convenience function to get report."""
    return get_generator().get_report_by_uuid(report_uuid)


def get_report_html(report_uuid: str) -> Optional[str]:
    """Convenience function to get report HTML."""
    return get_generator().get_report_html(report_uuid)


def generate_combined_report(
    lat: float,
    lon: float,
    address: str,
    area_total: float,
    rooms: Optional[int] = None,
    floor: Optional[int] = None,
    total_floors: Optional[int] = None,
    building_year: Optional[int] = None,
    cian_id: Optional[int] = None,
    seller_price: Optional[float] = None,
    district: Optional[str] = None,
    metro: Optional[str] = None,
    telegram_user_id: Optional[int] = None,
    telegram_chat_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate HTML report using combined Rosreestr + CIAN valuation.

    This is the recommended method for generating reports as it:
    - Uses both Rosreestr (completed transactions) and CIAN (listings)
    - Applies correct bargain: 0% for Rosreestr, 7% for CIAN
    - Calculates proper investment metrics

    Returns:
        Dict with report_uuid, report_url, html_content
    """
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    from etl.valuation import get_combined_estimate

    # Get combined valuation
    combined = get_combined_estimate(
        lat=lat,
        lon=lon,
        area_total=area_total,
        rooms=rooms,
        floor=floor,
        total_floors=total_floors,
        building_year=building_year
    )

    # Calculate investment parameters
    market_price = combined['market_price']
    market_price_per_sqm = combined['market_price_per_sqm']

    # Investment costs
    cost_notary = 50000
    cost_duty = 4000
    cost_pip = area_total * 1500
    cost_agent = 200000
    cost_registrar = 25000
    cost_kontur = 4000
    fixed_costs = cost_notary + cost_duty + cost_pip + cost_agent + cost_registrar + cost_kontur

    # Target profit (4%/month for 3 months)
    target_monthly_rate = 4
    project_months = 3
    min_profit = 1000000
    tax_rate = 6

    total_rate = (target_monthly_rate * project_months) / 100  # 0.12
    target_profit = market_price * total_rate / (1 + total_rate)
    target_profit = max(target_profit, min_profit)
    target_profit_gross = target_profit / (1 - tax_rate / 100)

    # Interest price
    interest_price = market_price - fixed_costs - target_profit_gross
    interest_price_per_sqm = interest_price / area_total

    # Prepare rosreestr_deals for template
    rosreestr_deals = combined.get('rosreestr_deals', [])

    # Prepare cian_analogs for template
    cian_analogs = combined.get('cian_analogs', [])

    # Generate report
    return generate_valuation_report(
        address=address,
        area_total=area_total,
        rooms=rooms,
        floor=floor,
        total_floors=total_floors,
        district=district,
        metro=metro,
        cian_id=cian_id,
        seller_price=seller_price,

        # Data sources
        rosreestr_deals=rosreestr_deals,
        cian_analogs=cian_analogs,

        # Statistics
        rosreestr_count=combined['rosreestr_count'],
        rosreestr_median=combined['rosreestr_median_psm'] or 0,
        cian_count=combined['cian_count'],
        cian_median=combined['cian_median_psm'] or 0,

        # Prices
        median_price_per_sqm=market_price_per_sqm,
        market_price=market_price,
        market_price_per_sqm=market_price_per_sqm,
        market_price_low=combined['price_range_low'],
        market_price_high=combined['price_range_high'],

        interest_price=interest_price,
        interest_price_per_sqm=interest_price_per_sqm,

        # Investment parameters
        cost_notary=cost_notary,
        cost_duty=cost_duty,
        cost_pip=cost_pip,
        cost_agent=cost_agent,
        cost_registrar=cost_registrar,
        cost_kontur=cost_kontur,
        fixed_costs=fixed_costs,

        target_monthly_rate=target_monthly_rate,
        project_months=project_months,
        min_profit=min_profit,
        tax_rate=tax_rate,
        target_profit=target_profit,
        target_profit_gross=target_profit_gross,

        # Telegram
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id,
    )
