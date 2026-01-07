"""Valuation API endpoints."""

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import json
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from etl.valuation import (
    PropertyFeatures, ValuationRequest, ValuationResponse,
    HybridEngine, BuildingType, BuildingHeight,
    CombinedEngine, get_combined_estimate
)

try:
    from .geocode_helper import (
        find_district_by_coordinates,
        find_building_type_by_coordinates,
        find_building_type_with_sources,
        find_building_info_by_coordinates,
        find_rosreestr_deals_nearby,
        get_building_info_from_dadata,
        geocode_address,
        parse_property_text,
        normalize_address_dadata
    )
except ImportError:
    def find_district_by_coordinates(lat, lon):
        return None
    def find_building_type_by_coordinates(lat, lon, radius_m=200):
        return None
    def find_building_type_with_sources(lat, lon, radius_m=200):
        return None
    def find_building_info_by_coordinates(lat, lon, radius_m=100):
        return None
    def find_rosreestr_deals_nearby(lat, lon, radius_m=2000, max_age_days=365, limit=20):
        return []
    def get_building_info_from_dadata(address):
        return None
    def geocode_address(address):
        return None
    def parse_property_text(text):
        return {'address': text}
    def normalize_address_dadata(address):
        return None

# Import investment calculator
try:
    from .investment_calculator import (
        calculate_interest_price, InvestmentParams, InterestPriceResult
    )
except ImportError:
    print("⚠️  Investment calculator not available")
    calculate_interest_price = None
    InvestmentParams = None

# Import CBR rate module
try:
    from .cbr_rate import get_rate_info, get_key_rate, get_bank_rate
except ImportError:
    print("⚠️  CBR rate module not available")
    def get_rate_info():
        return {'key_rate': 21.0, 'bank_margin': 5.5, 'bank_rate': 26.5, 'cached': False, 'updated_at': None}
    def get_key_rate():
        return 21.0
    def get_bank_rate():
        return 26.5

# Import Claude parser
try:
    from .claude_parser import (
        parse_text, parse_image, parse_cian_url,
        parse_avito_url, parse_yandex_realty_url,
        ParsedPropertyData, enhance_parsed_data
    )
    CLAUDE_PARSER_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Claude parser not available: {e}")
    CLAUDE_PARSER_AVAILABLE = False


app = FastAPI(
    title="Real Estate Valuation API",
    description="KNN-first hybrid valuation system for Moscow real estate",
    version="1.0.0",
    docs_url=None,      # Отключить /docs (Swagger UI)
    redoc_url=None,     # Отключить /redoc
    openapi_url=None    # Отключить /openapi.json
)

# Mount static files
static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global engine instances
engine = HybridEngine()
combined_engine = CombinedEngine()


# === Pydantic Models for API ===

class PropertyInput(BaseModel):
    """Property input for valuation."""
    address: Optional[str] = Field(None, description="Property address for history tracking")
    lat: Optional[float] = Field(None, description="Latitude")
    lon: Optional[float] = Field(None, description="Longitude")
    district_id: Optional[int] = Field(None, description="District ID")

    area_total: float = Field(..., gt=0, description="Total area in sqm")
    rooms: Optional[int] = Field(None, ge=1, le=10, description="Number of rooms")
    floor: Optional[int] = Field(None, ge=1, le=100, description="Floor number")
    total_floors: Optional[int] = Field(None, ge=1, le=100, description="Total floors in building")

    building_type: Optional[str] = Field(None, description="panel, brick, monolithic, block, wood, other")
    building_year: Optional[int] = Field(None, ge=1800, le=2030, description="Year built")

    has_elevator: Optional[bool] = None
    has_parking: Optional[bool] = None

    # Для исключения оцениваемого объекта из аналогов
    exclude_listing_id: Optional[int] = Field(None, description="CIAN listing ID to exclude from comparables")


class ComparableOutput(BaseModel):
    """Comparable property for response."""
    listing_id: int
    url: Optional[str]
    price: float
    price_per_sqm: float
    distance_km: float
    similarity_score: float
    weight: float
    rooms: Optional[int]
    area_total: float


class ValuationOutput(BaseModel):
    """Valuation response."""
    estimated_price: float
    estimated_price_per_sqm: float
    price_range_low: float
    price_range_high: float

    # Рыночная стоимость (медиана по аналогам)
    market_price: Optional[float] = Field(None, description="Рыночная стоимость (медиана)")
    market_price_per_sqm: Optional[float] = Field(None, description="Рыночная стоимость за м²")

    confidence: int
    method_used: str

    grid_weight: float
    knn_weight: float

    # Property characteristics used
    building_type_detected: Optional[str] = Field(None, description="Auto-detected or provided building type")
    building_type_source: Optional[str] = Field(None, description="'auto' or 'manual'")
    building_type_sources: Optional[List[dict]] = Field(None, description="Source listings used for auto-detection")
    district_id: Optional[int] = Field(None, description="Detected district ID")

    # Auto-detected building info
    total_floors_detected: Optional[int] = Field(None, description="Auto-detected floors")
    building_year_detected: Optional[int] = Field(None, description="Auto-detected year")
    building_info_warning: Optional[str] = Field(None, description="Предупреждение если данные не определены")
    
    comparables: Optional[List[ComparableOutput]]
    comparables_count: int

    # Rosreestr deals (actual transactions)
    rosreestr_deals: Optional[List[dict]] = Field(None, description="Сделки Росреестра рядом")
    rosreestr_count: int = Field(0, description="Количество сделок Росреестра")

    # Investment analysis
    interest_price: Optional[float] = Field(None, description="Цена интереса (макс. цена покупки)")
    interest_price_per_sqm: Optional[float] = Field(None, description="Цена интереса за м²")
    expected_profit: Optional[float] = Field(None, description="Ожидаемая прибыль")
    profit_rate: Optional[float] = Field(None, description="% прибыли к вложениям")
    monthly_profit_rate: Optional[float] = Field(None, description="% прибыли в месяц")
    investment_breakdown: Optional[dict] = Field(None, description="Детализация расходов")

    # Valuation ID for history tracking
    valuation_id: Optional[int] = Field(None, description="ID оценки в истории")

    timestamp: datetime


# === API Endpoints ===

@app.get("/")
def root():
    """Serve web interface."""
    static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static", "index.html")
    if os.path.exists(static_path):
        return FileResponse(static_path)
    return {
        "service": "Real Estate Valuation API",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs"
    }


@app.get("/health")
def health():
    """Health check."""
    return {"status": "healthy", "timestamp": datetime.now()}


@app.get("/cbr-rate")
def cbr_rate():
    """
    Получить текущую ключевую ставку ЦБ и банковскую ставку.

    Returns:
        key_rate: Ключевая ставка ЦБ (%)
        bank_margin: Надбавка банка (5.5%)
        bank_rate: Банковская ставка = ЦБ + надбавка (%)
        bank_rate_monthly: Месячная ставка банка (%)
    """
    info = get_rate_info()
    return {
        "key_rate": info['key_rate'],
        "bank_margin": info['bank_margin'],
        "bank_rate": info['bank_rate'],
        "bank_rate_monthly": round(info['bank_rate'] / 12, 2),
        "cached": info.get('cached', False),
        "updated_at": info.get('updated_at')
    }


class CombinedEstimateOutput(BaseModel):
    """Combined valuation output using Rosreestr + CIAN."""
    market_price: float = Field(description="Рыночная цена (комбинированная медиана)")
    market_price_per_sqm: float = Field(description="Цена за м² (комбинированная)")

    rosreestr_median_psm: Optional[float] = Field(None, description="Медиана Росреестра ₽/м²")
    rosreestr_count: int = Field(description="Количество сделок Росреестра")
    cian_median_psm: Optional[float] = Field(None, description="Медиана ЦИАН ₽/м² (с учётом торга 7%)")
    cian_count: int = Field(description="Количество объявлений ЦИАН")

    price_range_low: float = Field(description="Нижняя граница цены")
    price_range_high: float = Field(description="Верхняя граница цены")

    interest_price: Optional[float] = Field(None, description="Цена интереса")
    interest_price_per_sqm: Optional[float] = Field(None, description="Цена интереса за м²")

    confidence: int = Field(description="Уверенность оценки %")
    method_used: str = Field(description="Метод расчёта")

    rosreestr_deals: Optional[List[dict]] = Field(None, description="Сделки Росреестра")
    cian_analogs: Optional[List[dict]] = Field(None, description="Аналоги ЦИАН")

    area_total: float = Field(description="Площадь объекта")
    timestamp: datetime = Field(default_factory=datetime.now)


class ParsePropertyRequest(BaseModel):
    """Request for parsing property description text."""
    text: str = Field(..., description="Текст с описанием объекта")


class ParsePropertyResponse(BaseModel):
    """Response with parsed property data."""
    address: Optional[str] = None
    address_formatted: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    area: Optional[float] = None
    rooms: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    geocode_source: Optional[str] = None
    raw_text: str


@app.post("/parse-property", response_model=ParsePropertyResponse)
def parse_property(request: ParsePropertyRequest):
    """
    Parse property description text and geocode address.

    Extracts: address, area, rooms, floor, total_floors
    Then geocodes address to get coordinates.

    Example input:
    "2-комнатная квартира, 53.6 м2, 15 этаж, Москва, ул. Коцюбинского, дом 10"
    """
    # Parse text
    parsed = parse_property_text(request.text)

    # Geocode address if found
    lat = None
    lon = None
    address_formatted = None
    geocode_source = None

    if parsed.get('address'):
        geo = geocode_address(parsed['address'])
        if geo:
            lat = geo['lat']
            lon = geo['lon']
            address_formatted = geo.get('address_formatted')
            geocode_source = geo.get('source')

    return ParsePropertyResponse(
        address=parsed.get('address'),
        address_formatted=address_formatted,
        lat=lat,
        lon=lon,
        area=parsed.get('area'),
        rooms=parsed.get('rooms'),
        floor=parsed.get('floor'),
        total_floors=parsed.get('total_floors'),
        geocode_source=geocode_source,
        raw_text=request.text
    )


@app.post("/combined-estimate", response_model=CombinedEstimateOutput)
def combined_estimate(
    property_data: PropertyInput,
    k: int = Query(10, ge=1, le=50, description="Number of comparables"),
    max_distance_km: float = Query(5.0, ge=0.5, le=20.0, description="Max search radius")
):
    """
    Combined valuation using Rosreestr + CIAN data.

    Key features:
    - Rosreestr (completed transactions): 0% bargain
    - CIAN (asking prices): 7% bargain applied
    - Weighted average based on sample sizes

    Returns both market price and interest price (investment analysis).
    """
    try:
        if property_data.lat is None or property_data.lon is None:
            raise HTTPException(
                status_code=400,
                detail="Coordinates (lat, lon) are required for combined estimate"
            )

        # Get combined estimate
        result = get_combined_estimate(
            lat=property_data.lat,
            lon=property_data.lon,
            area_total=property_data.area_total,
            rooms=property_data.rooms,
            floor=property_data.floor,
            total_floors=property_data.total_floors,
            building_year=property_data.building_year,
            k=k,
            max_distance_km=max_distance_km
        )

        # Calculate interest price using investment calculator
        interest_price = None
        interest_price_per_sqm = None

        if calculate_interest_price and result['market_price']:
            try:
                interest_result = calculate_interest_price(
                    market_price=result['market_price'],
                    area_total=property_data.area_total,
                    params=InvestmentParams(include_utilities=True)
                )
                interest_price = interest_result.interest_price
                interest_price_per_sqm = interest_result.interest_price_per_sqm
            except Exception as e:
                print(f"Failed to calculate interest price: {e}")

        return CombinedEstimateOutput(
            market_price=result['market_price'],
            market_price_per_sqm=result['market_price_per_sqm'],
            rosreestr_median_psm=result['rosreestr_median_psm'],
            rosreestr_count=result['rosreestr_count'],
            cian_median_psm=result['cian_median_psm'],
            cian_count=result['cian_count'],
            price_range_low=result['price_range_low'],
            price_range_high=result['price_range_high'],
            interest_price=interest_price,
            interest_price_per_sqm=interest_price_per_sqm,
            confidence=result['confidence'],
            method_used=result['method_used'],
            rosreestr_deals=result['rosreestr_deals'],
            cian_analogs=result['cian_analogs'],
            area_total=property_data.area_total,
            timestamp=datetime.now()
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/search-address")
def search_address(q: str = Query(..., min_length=3, description="Address search query")):
    """
    Search for addresses in our database.
    Returns coordinates from existing listings.
    """
    import psycopg2
    from psycopg2.extras import RealDictCursor
    import os
    
    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")
    
    try:
        conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        # Normalize search query
        search = q.strip()
        search = search.replace('пр-т', 'проспект')
        search = search.replace('пр.', 'проспект')
        search = search.replace('ул.', 'улица')
        search = search.replace('д.', '')
        search = search.replace(',', ' ')
        
        # Extract street and house number (ignore corpus/building)
        import re
        # Try to extract "Street Name" + "Number"
        match = re.search(r'([а-яА-Я\s]+(?:проспект|улица|переулок|бульвар|шоссе))\s*,?\s*(\d+)', search, re.IGNORECASE)
        if match:
            street = match.group(1).strip()
            house_num = match.group(2)
            search_pattern = f'%{street}%{house_num}%'
        else:
            search_pattern = f'%{search}%'
        
        # Search in database - try with coordinates first
        cur.execute("""
            SELECT DISTINCT ON (address)
                address,
                lat,
                lon,
                COUNT(*) OVER (PARTITION BY address) as listing_count,
                (lat IS NOT NULL AND lon IS NOT NULL) as has_coords
            FROM listings
            WHERE address ILIKE %s
            ORDER BY address, (lat IS NOT NULL AND lon IS NOT NULL) DESC, last_seen DESC
            LIMIT 10
        """, (search_pattern,))
        
        all_results = cur.fetchall()
        
        # Filter to only return results with coordinates
        results = [r for r in all_results if r['has_coords']]
        
        # If no results with coords, try broader search
        if not results and len(search) > 5:
            # Try searching by street name only (more flexible)
            parts = search.split()
            if len(parts) >= 2:
                street_search = f'%{parts[0]}%{parts[1] if len(parts) > 1 else ""}%'
                cur.execute("""
                    SELECT DISTINCT ON (address)
                        address,
                        lat,
                        lon,
                        COUNT(*) OVER (PARTITION BY address) as listing_count
                    FROM listings
                    WHERE address ILIKE %s
                      AND lat IS NOT NULL
                      AND lon IS NOT NULL
                    ORDER BY address, last_seen DESC
                    LIMIT 10
                """, (street_search,))
                results = cur.fetchall()
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        return {
            "query": q,
            "found": len(results),
            "results": [
                {
                    "address": r['address'],
                    "lat": float(r['lat']),
                    "lon": float(r['lon']),
                    "listing_count": r['listing_count']
                }
                for r in results
            ]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/estimate", response_model=ValuationOutput)
def estimate_property(
    property_data: PropertyInput,
    k: int = Query(10, ge=1, le=50, description="Number of comparables"),
    max_distance_km: float = Query(5.0, ge=0.5, le=20.0, description="Max search radius"),
    max_age_days: int = Query(90, ge=1, le=365, description="Max listing age")
):
    """
    Estimate property price using hybrid KNN + Grid approach.
    
    **Example:**
    ```json
    {
        "lat": 55.7558,
        "lon": 37.6173,
        "area_total": 65.0,
        "rooms": 2,
        "floor": 5,
        "total_floors": 9,
        "building_type": "panel"
    }
    ```
    """
    
    try:
        # Auto-detect district if not provided
        district_id = property_data.district_id
        if not district_id and property_data.lat and property_data.lon:
            district_id = find_district_by_coordinates(property_data.lat, property_data.lon)
        
        # Auto-detect building info (total_floors, building_year, building_type) if not provided
        # Priority: 1) User input, 2) Same building listings (10-50m), 3) Nearby listings (200m), 4) DaData
        building_type_str = property_data.building_type
        building_type_source = "manual" if building_type_str else None
        building_type_sources_list = None
        total_floors = property_data.total_floors
        building_year = property_data.building_year

        if property_data.lat and property_data.lon:
            # Step 1: Try to get ALL building info from same building (small radius 10-50m)
            if not total_floors or not building_year or not building_type_str:
                building_info = find_building_info_by_coordinates(property_data.lat, property_data.lon)
                if building_info:
                    if not total_floors and building_info.get('total_floors'):
                        total_floors = building_info['total_floors']
                        print(f"🏢 Auto-detected total_floors: {total_floors} (confidence: {building_info.get('confidence', 'unknown')})")
                    if not building_year and building_info.get('building_year'):
                        building_year = building_info['building_year']
                        print(f"📅 Auto-detected building_year: {building_year} (confidence: {building_info.get('confidence', 'unknown')})")
                    if not building_type_str and building_info.get('building_type'):
                        building_type_str = building_info['building_type']
                        building_type_source = "auto"
                        print(f"🏗️  Auto-detected building_type from same building: {building_type_str}")

            # Step 2: If building_type still not found, try wider radius (200m)
            if not building_type_str:
                detection_result = find_building_type_with_sources(property_data.lat, property_data.lon)
                if detection_result:
                    building_type_str = detection_result['building_type']
                    building_type_source = "auto_nearby"
                    building_type_sources_list = detection_result.get('sources', [])
                    print(f"🏗️  Auto-detected building_type from nearby: {building_type_str} from {len(building_type_sources_list)} sources")

            # Step 3: Fallback to DaData API if still missing building info
            if (not total_floors or not building_year) and property_data.address:
                dadata_info = get_building_info_from_dadata(property_data.address)
                if dadata_info:
                    if not total_floors and dadata_info.get('total_floors'):
                        total_floors = dadata_info['total_floors']
                        print(f"🏢 DaData total_floors: {total_floors}")
                    if not building_year and dadata_info.get('building_year'):
                        building_year = dadata_info['building_year']
                        print(f"📅 DaData building_year: {building_year}")
                    if not building_type_str and dadata_info.get('building_type'):
                        building_type_str = dadata_info['building_type']
                        building_type_source = "dadata"
                        print(f"🏗️  DaData building_type: {building_type_str}")

        # Convert input to features
        building_type_enum = None
        if building_type_str:
            try:
                building_type_enum = BuildingType(building_type_str.lower())
            except ValueError:
                building_type_enum = BuildingType.OTHER
        
        building_height_enum = None
        if total_floors:
            if total_floors <= 5:
                building_height_enum = BuildingHeight.LOW
            elif total_floors <= 10:
                building_height_enum = BuildingHeight.MEDIUM
            else:
                building_height_enum = BuildingHeight.HIGH

        features = PropertyFeatures(
            lat=property_data.lat,
            lon=property_data.lon,
            district_id=district_id,
            area_total=property_data.area_total,
            rooms=property_data.rooms,
            floor=property_data.floor,
            total_floors=total_floors,  # Use auto-detected if available
            building_type=building_type_enum,
            building_height=building_height_enum,
            building_year=building_year,  # Use auto-detected if available
            has_elevator=property_data.has_elevator,
            has_parking=property_data.has_parking,
            exclude_listing_id=property_data.exclude_listing_id  # Исключить из аналогов
        )
        
        # Create request
        request = ValuationRequest(
            features=features,
            k=k,
            max_distance_km=max_distance_km,
            max_age_days=max_age_days
        )
        
        # Estimate
        result = engine.estimate(request)
        
        # Convert comparables
        comparables_out = []
        if result.knn_estimate:
            for c in result.knn_estimate.comparables:
                comparables_out.append(ComparableOutput(
                    listing_id=c.listing_id,
                    url=c.url,
                    price=c.price,
                    price_per_sqm=c.price_per_sqm,
                    distance_km=c.distance_km,
                    similarity_score=c.similarity_score,
                    weight=c.weight,
                    rooms=c.rooms,
                    area_total=c.area_total
                ))
        
        # Calculate market price (median) from comparables
        market_price = None
        market_price_per_sqm = None
        if result.knn_estimate and result.knn_estimate.comparables:
            prices_per_sqm = sorted([c.price_per_sqm for c in result.knn_estimate.comparables])
            n = len(prices_per_sqm)
            if n > 0:
                median_psm = prices_per_sqm[n // 2] if n % 2 else (prices_per_sqm[n // 2 - 1] + prices_per_sqm[n // 2]) / 2
                market_price_per_sqm = median_psm
                market_price = median_psm * property_data.area_total

        # Check if building info was auto-detected or missing
        building_info_warning = None
        total_floors_detected = total_floors if total_floors != property_data.total_floors else None
        building_year_detected = building_year if building_year != property_data.building_year else None

        if not total_floors and not building_year:
            building_info_warning = "Не удалось определить этажность и год постройки. Укажите вручную для точной оценки."
        elif not total_floors:
            building_info_warning = "Не удалось определить этажность дома. Укажите вручную для точной оценки."
        elif not building_year:
            building_info_warning = "Не удалось определить год постройки. Укажите вручную для точной оценки."

        # Find nearby Rosreestr deals (with building class filtering)
        rosreestr_deals = []
        if property_data.lat and property_data.lon:
            rosreestr_deals = find_rosreestr_deals_nearby(
                lat=property_data.lat,
                lon=property_data.lon,
                radius_m=2000,  # 2km radius
                max_age_days=365,  # 1 year
                limit=15,
                target_year=building_year,  # Filter by building class
                target_floors=total_floors,
                target_area=property_data.area_total
            )
            if rosreestr_deals:
                print(f"📋 Found {len(rosreestr_deals)} Rosreestr deals nearby (filtered by building class)")

        # Calculate interest price (investment analysis)
        interest_price_data = None
        if calculate_interest_price:
            try:
                # Use market_price for investment calculation (more accurate)
                price_for_investment = market_price if market_price else result.estimated_price
                interest_result = calculate_interest_price(
                    market_price=price_for_investment,
                    area_total=property_data.area_total,
                    params=InvestmentParams(include_utilities=True)
                )
                interest_price_data = {
                    "interest_price": interest_result.interest_price,
                    "interest_price_per_sqm": interest_result.interest_price_per_sqm,
                    "expected_profit": interest_result.expected_profit,
                    "profit_rate": interest_result.profit_rate,
                    "monthly_profit_rate": interest_result.monthly_profit_rate,
                    "breakdown": interest_result.cost_breakdown
                }
            except Exception as e:
                print(f"Failed to calculate interest price: {e}")
        
        valuation_output = ValuationOutput(
            estimated_price=result.estimated_price,
            estimated_price_per_sqm=result.estimated_price_per_sqm,
            price_range_low=result.price_range_low,
            price_range_high=result.price_range_high,
            market_price=market_price,
            market_price_per_sqm=market_price_per_sqm,
            confidence=result.confidence,
            method_used=result.method_used,
            grid_weight=result.grid_weight,
            knn_weight=result.knn_weight,
            building_type_detected=building_type_str,
            building_type_source=building_type_source,
            building_type_sources=building_type_sources_list,
            district_id=district_id,
            total_floors_detected=total_floors_detected,
            building_year_detected=building_year_detected,
            building_info_warning=building_info_warning,
            comparables=comparables_out,
            comparables_count=len(comparables_out),
            rosreestr_deals=rosreestr_deals,
            rosreestr_count=len(rosreestr_deals),
            interest_price=interest_price_data["interest_price"] if interest_price_data else None,
            interest_price_per_sqm=interest_price_data["interest_price_per_sqm"] if interest_price_data else None,
            expected_profit=interest_price_data["expected_profit"] if interest_price_data else None,
            profit_rate=interest_price_data["profit_rate"] if interest_price_data else None,
            monthly_profit_rate=interest_price_data["monthly_profit_rate"] if interest_price_data else None,
            investment_breakdown=interest_price_data["breakdown"] if interest_price_data else None,
            timestamp=result.timestamp
        )
        
        # Save valuation history and get valuation_id
        valuation_id = None
        try:
            valuation_id = _save_valuation_history(property_data, valuation_output, building_type_str, building_type_source)
        except Exception as e:
            print(f"Failed to save valuation history: {e}")

        # Update valuation_output with the ID
        valuation_output.valuation_id = valuation_id

        return valuation_output
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


import re

def _normalize_address_regex(address: str) -> str:
    """
    Fallback: нормализовать адрес с помощью regex (если DaData недоступен).

    Удаляет:
    - Префиксы: Москва, г., ул., улица, д., дом, корп., корпус, стр., строение
    - Лишние пробелы
    - Приводит к нижнему регистру
    """
    if not address:
        return ""

    addr = address.lower().strip()

    # Удаляем "москва" и "россия"
    addr = re.sub(r'\bроссия,?\s*', '', addr)
    addr = re.sub(r'\bмосква,?\s*', '', addr)
    addr = re.sub(r'\bг\.?\s*москва,?\s*', '', addr)

    # Удаляем типовые сокращения
    addr = re.sub(r'\bг\.?\s*', '', addr)  # г.
    addr = re.sub(r'\bул\.?\s*', '', addr)  # ул.
    addr = re.sub(r'\bулица\s+', '', addr)  # улица
    addr = re.sub(r'\bпр-?т\.?\s*', '', addr)  # пр-т, прт (проспект)
    addr = re.sub(r'\bпроспект\s+', '', addr)  # проспект
    addr = re.sub(r'\bпр\.?\s+', '', addr)  # пр. (проспект)
    addr = re.sub(r'\bпер\.?\s*', '', addr)  # пер. (переулок)
    addr = re.sub(r'\bпереулок\s+', '', addr)  # переулок
    addr = re.sub(r'\bбул\.?\s*', '', addr)  # бул. (бульвар)
    addr = re.sub(r'\bбульвар\s+', '', addr)  # бульвар
    addr = re.sub(r'\bш\.?\s+', '', addr)  # ш. (шоссе)
    addr = re.sub(r'\bшоссе\s+', '', addr)  # шоссе
    addr = re.sub(r'\bнаб\.?\s*', '', addr)  # наб. (набережная)
    addr = re.sub(r'\bнабережная\s+', '', addr)  # набережная
    addr = re.sub(r'\bд\.?\s*', '', addr)  # д.
    addr = re.sub(r'\bдом\s+', '', addr)  # дом
    addr = re.sub(r'\bкорп\.?\s*', ' к', addr)  # корп. -> к
    addr = re.sub(r'\bкорпус\s+', ' к', addr)  # корпус -> к
    addr = re.sub(r'\bстр\.?\s*', ' с', addr)  # стр. -> с
    addr = re.sub(r'\bстроение\s+', ' с', addr)  # строение -> с
    addr = re.sub(r'\bкв\.?\s*\d+', '', addr)  # кв. 123 - удаляем квартиру

    # Нормализуем пробелы
    addr = re.sub(r'\s+', ' ', addr).strip()

    # Удаляем финальную запятую
    addr = addr.rstrip(',').strip()

    return addr


def normalize_address(address: str) -> str:
    """
    Нормализовать адрес через DaData API с fallback на regex.

    DaData возвращает стандартизированный адрес в формате ФИАС:
    "г Москва, ул Тверская, д 1" -> "г Москва, ул Тверская, д 1"

    Если DaData недоступен - используем regex-нормализацию.
    """
    if not address:
        return ""

    # Пробуем нормализовать через DaData
    dadata_normalized = normalize_address_dadata(address)
    if dadata_normalized:
        return dadata_normalized

    # Fallback на regex
    return _normalize_address_regex(address)


def _save_valuation_history(property_data: PropertyInput, valuation: ValuationOutput, building_type: str, building_type_source: str):
    """Save valuation to history database."""
    import psycopg2
    
    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")
    
    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        
        # Insert valuation history (with interest price and normalized address)
        import json
        address = property_data.address or "Unknown"
        address_normalized = normalize_address(address)

        cur.execute("""
            INSERT INTO valuation_history (
                address, address_normalized, lat, lon, district_id,
                area_total, rooms, floor, total_floors,
                building_type, building_type_source,
                estimated_price, estimated_price_per_sqm,
                price_range_low, price_range_high,
                confidence, method_used,
                comparables_count,
                interest_price, interest_price_per_sqm,
                expected_profit, profit_rate,
                investment_breakdown
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s,
                %s, %s,
                %s, %s,
                %s
            ) RETURNING valuation_id
        """, (
            address,
            address_normalized,
            property_data.lat, property_data.lon, property_data.district_id,
            property_data.area_total, property_data.rooms, property_data.floor, property_data.total_floors,
            building_type, building_type_source,
            valuation.estimated_price, valuation.estimated_price_per_sqm,
            valuation.price_range_low, valuation.price_range_high,
            valuation.confidence, valuation.method_used,
            valuation.comparables_count,
            int(valuation.interest_price) if valuation.interest_price else None,
            float(valuation.interest_price_per_sqm) if valuation.interest_price_per_sqm else None,
            int(valuation.expected_profit) if valuation.expected_profit else None,
            float(valuation.profit_rate) if valuation.profit_rate else None,
            json.dumps(valuation.investment_breakdown) if valuation.investment_breakdown else None
        ))
        
        valuation_id = cur.fetchone()[0]
        
        # Insert comparables
        if valuation.comparables:
            sorted_comps = sorted(valuation.comparables, key=lambda c: c.price_per_sqm)
            for rank, comp in enumerate(sorted_comps, 1):
                cur.execute("""
                    INSERT INTO valuation_comparables (
                        valuation_id, listing_id, url,
                        price, price_per_sqm, area_total, rooms, building_type,
                        distance_km, similarity_score, weight, rank
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                """, (
                    valuation_id, comp.listing_id, comp.url,
                    comp.price, comp.price_per_sqm, comp.area_total, comp.rooms, None,
                    comp.distance_km, comp.similarity_score, comp.weight, rank if rank <= 3 else None
                ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✅ Valuation history saved: ID={valuation_id}")
        return valuation_id
        
    except Exception as e:
        print(f"❌ Failed to save valuation history: {e}")
        if 'conn' in locals():
            conn.rollback()
        return None


@app.get("/history/streets")
def get_history_streets(search: Optional[str] = Query(None, description="Search filter for street name")):
    """Get unique streets with valuation counts, grouped for tree view."""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    import re

    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")

    try:
        conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        # Get all addresses with valuations, grouped by normalized address to avoid duplicates
        if search:
            cur.execute("""
                SELECT
                    COALESCE(address_normalized, address) as address_key,
                    MAX(address) as address,
                    COUNT(*) as valuation_count,
                    MAX(created_at) as last_valuation,
                    MAX(estimated_price) as max_price,
                    MIN(estimated_price) as min_price
                FROM valuation_history
                WHERE address ILIKE %s AND address != 'Unknown'
                GROUP BY COALESCE(address_normalized, address)
                ORDER BY last_valuation DESC
            """, (f'%{search}%',))
        else:
            cur.execute("""
                SELECT
                    COALESCE(address_normalized, address) as address_key,
                    MAX(address) as address,
                    COUNT(*) as valuation_count,
                    MAX(created_at) as last_valuation,
                    MAX(estimated_price) as max_price,
                    MIN(estimated_price) as min_price
                FROM valuation_history
                WHERE address != 'Unknown'
                GROUP BY COALESCE(address_normalized, address)
                ORDER BY last_valuation DESC
            """)

        results = cur.fetchall()
        cur.close()
        conn.close()

        # Group by street
        streets = {}
        for r in results:
            address = r['address']
            # Extract street name (before house number)
            street_match = re.match(r'^([^,\d]+(?:улица|проспект|переулок|бульвар|шоссе|набережная)?)\s*,?\s*(?:д\.?\s*)?(\d+)?', address, re.IGNORECASE)
            if street_match:
                street = street_match.group(1).strip()
            else:
                # Fallback - take first part before comma or number
                parts = re.split(r'[,\d]', address)
                street = parts[0].strip() if parts else address

            if not street:
                street = "Другие адреса"

            if street not in streets:
                streets[street] = {
                    "street": street,
                    "buildings": [],
                    "total_valuations": 0,
                    "last_valuation": None
                }

            streets[street]["buildings"].append({
                "address": address,
                "valuation_count": r['valuation_count'],
                "last_valuation": r['last_valuation'].isoformat() if r['last_valuation'] else None,
                "max_price": float(r['max_price']) if r['max_price'] else None,
                "min_price": float(r['min_price']) if r['min_price'] else None
            })
            streets[street]["total_valuations"] += r['valuation_count']
            if r['last_valuation']:
                if streets[street]["last_valuation"] is None or r['last_valuation'].isoformat() > streets[street]["last_valuation"]:
                    streets[street]["last_valuation"] = r['last_valuation'].isoformat()

        # Sort streets by last valuation
        sorted_streets = sorted(streets.values(), key=lambda x: x['last_valuation'] or '', reverse=True)

        return {
            "total_streets": len(sorted_streets),
            "total_buildings": sum(len(s['buildings']) for s in sorted_streets),
            "total_valuations": sum(s['total_valuations'] for s in sorted_streets),
            "streets": sorted_streets
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history/all")
def get_all_history(
    search: Optional[str] = Query(None, description="Search filter"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """Get all valuation history with search and pagination."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")

    try:
        conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        # Count total
        if search:
            cur.execute("""
                SELECT COUNT(*) FROM valuation_history
                WHERE address ILIKE %s AND address != 'Unknown'
            """, (f'%{search}%',))
        else:
            cur.execute("SELECT COUNT(*) FROM valuation_history WHERE address != 'Unknown'")

        total = cur.fetchone()['count']

        # Get history
        if search:
            cur.execute("""
                SELECT
                    valuation_id, address, lat, lon,
                    area_total, rooms, floor, total_floors,
                    building_type,
                    estimated_price, estimated_price_per_sqm,
                    interest_price, interest_price_per_sqm,
                    expected_profit, profit_rate,
                    confidence, method_used,
                    comparables_count,
                    created_at
                FROM valuation_history
                WHERE address ILIKE %s AND address != 'Unknown'
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (f'%{search}%', limit, offset))
        else:
            cur.execute("""
                SELECT
                    valuation_id, address, lat, lon,
                    area_total, rooms, floor, total_floors,
                    building_type,
                    estimated_price, estimated_price_per_sqm,
                    interest_price, interest_price_per_sqm,
                    expected_profit, profit_rate,
                    confidence, method_used,
                    comparables_count,
                    created_at
                FROM valuation_history
                WHERE address != 'Unknown'
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))

        results = cur.fetchall()
        cur.close()
        conn.close()

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "history": [
                {
                    "valuation_id": r['valuation_id'],
                    "address": r['address'],
                    "lat": float(r['lat']) if r['lat'] else None,
                    "lon": float(r['lon']) if r['lon'] else None,
                    "area_total": float(r['area_total']),
                    "rooms": r['rooms'],
                    "floor": r['floor'],
                    "total_floors": r['total_floors'],
                    "building_type": r['building_type'],
                    "estimated_price": float(r['estimated_price']),
                    "estimated_price_per_sqm": float(r['estimated_price_per_sqm']),
                    "interest_price": float(r['interest_price']) if r['interest_price'] else None,
                    "interest_price_per_sqm": float(r['interest_price_per_sqm']) if r['interest_price_per_sqm'] else None,
                    "expected_profit": float(r['expected_profit']) if r['expected_profit'] else None,
                    "profit_rate": float(r['profit_rate']) if r['profit_rate'] else None,
                    "confidence": r['confidence'],
                    "comparables_count": r['comparables_count'],
                    "created_at": r['created_at'].isoformat()
                }
                for r in results
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history/by-address/{address:path}")
def get_history_by_address(address: str, limit: int = Query(20, ge=1, le=100)):
    """Get valuation history for a specific address with all details."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")

    try:
        conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        cur.execute("""
            SELECT
                valuation_id, address, lat, lon,
                area_total, rooms, floor, total_floors,
                building_type, building_type_source,
                estimated_price, estimated_price_per_sqm,
                price_range_low, price_range_high,
                interest_price, interest_price_per_sqm,
                expected_profit, profit_rate,
                investment_breakdown,
                confidence, method_used,
                comparables_count,
                created_at
            FROM valuation_history
            WHERE address = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (address, limit))

        results = cur.fetchall()
        cur.close()
        conn.close()

        if not results:
            return {"address": address, "count": 0, "history": []}

        return {
            "address": address,
            "count": len(results),
            "history": [
                {
                    **{k: (float(v) if isinstance(v, (int, float)) and k not in ['valuation_id', 'rooms', 'floor', 'total_floors', 'confidence', 'comparables_count'] else v) for k, v in dict(r).items() if k != 'created_at' and k != 'investment_breakdown'},
                    "investment_breakdown": r['investment_breakdown'],
                    "created_at": r['created_at'].isoformat()
                }
                for r in results
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history/{address}")
def get_valuation_history(address: str, limit: int = Query(10, ge=1, le=50)):
    """Get valuation history for an address."""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")
    
    try:
        conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT 
                valuation_id,
                address, lat, lon,
                area_total, rooms, floor, total_floors,
                building_type, building_type_source,
                estimated_price, estimated_price_per_sqm,
                price_range_low, price_range_high,
                confidence, method_used,
                comparables_count,
                created_at
            FROM valuation_history
            WHERE address ILIKE %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (f'%{address}%', limit))
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        return {
            "address": address,
            "count": len(results),
            "history": [
                {
                    "valuation_id": r['valuation_id'],
                    "estimated_price": float(r['estimated_price']),
                    "estimated_price_per_sqm": float(r['estimated_price_per_sqm']),
                    "confidence": r['confidence'],
                    "method_used": r['method_used'],
                    "comparables_count": r['comparables_count'],
                    "building_type": r['building_type'],
                    "created_at": r['created_at'].isoformat(),
                    "params": {
                        "area_total": float(r['area_total']),
                        "rooms": r['rooms'],
                        "floor": r['floor'],
                        "total_floors": r['total_floors']
                    }
                }
                for r in results
            ]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history/details/{valuation_id}")
def get_valuation_details(valuation_id: int):
    """Get detailed valuation including comparables."""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")
    
    try:
        conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        # Get valuation
        cur.execute("""
            SELECT * FROM valuation_history
            WHERE valuation_id = %s
        """, (valuation_id,))
        
        valuation = cur.fetchone()
        if not valuation:
            raise HTTPException(status_code=404, detail="Valuation not found")
        
        # Get comparables
        cur.execute("""
            SELECT * FROM valuation_comparables
            WHERE valuation_id = %s
            ORDER BY rank NULLS LAST, price_per_sqm ASC
        """, (valuation_id,))
        
        comparables = cur.fetchall()
        cur.close()
        conn.close()
        
        return {
            "valuation": dict(valuation),
            "comparables": [dict(c) for c in comparables]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calculate-interest-price")
def calculate_custom_interest_price(
    request: dict
):
    """
    Рассчитать цену интереса с кастомными параметрами.
    Позволяет включать/выключать различные расходы.
    """
    if not calculate_interest_price or not InvestmentParams:
        raise HTTPException(status_code=500, detail="Investment calculator not available")
    
    try:
        market_price = request.get('market_price')
        area_total = request.get('area_total')
        params_dict = request.get('params', {})
        
        params = InvestmentParams(**params_dict)
        result = calculate_interest_price(market_price, area_total, params)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/save-investment-params")
def save_investment_params(request: dict):
    """
    Сохранить обновлённые параметры инвестиционного анализа.
    """
    valuation_id = request.get('valuation_id')
    investment_data = request.get('investment_data', {})
    # Данные о корректировке цены
    price_adjustment = request.get('price_adjustment', 0)
    adjustment_note = request.get('adjustment_note', '')

    if not valuation_id:
        raise HTTPException(status_code=400, detail="valuation_id обязателен")

    import psycopg2
    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")

    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()

        # Обновляем инвестиционные данные и корректировку цены
        cur.execute("""
            UPDATE valuation_history SET
                interest_price = %s,
                interest_price_per_sqm = %s,
                expected_profit = %s,
                profit_rate = %s,
                investment_breakdown = %s,
                price_adjustment = %s,
                adjustment_note = %s,
                adjusted_at = CASE WHEN %s != 0 THEN NOW() ELSE adjusted_at END
            WHERE valuation_id = %s
            RETURNING valuation_id
        """, (
            int(investment_data.get('interest_price')) if investment_data.get('interest_price') else None,
            float(investment_data.get('interest_price_per_sqm')) if investment_data.get('interest_price_per_sqm') else None,
            int(investment_data.get('expected_profit')) if investment_data.get('expected_profit') else None,
            float(investment_data.get('profit_rate')) if investment_data.get('profit_rate') else None,
            json.dumps(investment_data.get('cost_breakdown')) if investment_data.get('cost_breakdown') else None,
            price_adjustment,
            adjustment_note if adjustment_note else None,
            price_adjustment,  # Для условия CASE
            valuation_id
        ))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return {"success": True, "valuation_id": valuation_id}
        else:
            raise HTTPException(status_code=404, detail="Оценка не найдена")

    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Ошибка базы данных: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/listing/{listing_id}")
def get_listing_details(listing_id: int):
    """Get detailed info about a listing from local database."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")

    try:
        conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        # Get listing with latest price
        cur.execute("""
            SELECT
                l.id,
                l.url,
                l.address,
                l.area_total,
                l.area_living,
                l.area_kitchen,
                l.rooms,
                l.floor,
                l.total_floors,
                l.building_type,
                l.description,
                l.is_active,
                l.first_seen,
                l.last_seen,
                l.lat,
                l.lon,
                lp.price,
                l.initial_price,
                l.price_change_count,
                l.price_change_pct
            FROM listings l
            LEFT JOIN LATERAL (
                SELECT price FROM listing_prices
                WHERE id = l.id
                ORDER BY seen_at DESC
                LIMIT 1
            ) lp ON true
            WHERE l.id = %s
        """, (listing_id,))

        listing = cur.fetchone()

        if not listing:
            raise HTTPException(status_code=404, detail="Листинг не найден")

        # Get price history
        cur.execute("""
            SELECT price, seen_at
            FROM listing_prices
            WHERE id = %s
            ORDER BY seen_at DESC
            LIMIT 20
        """, (listing_id,))

        price_history = cur.fetchall()
        cur.close()
        conn.close()

        return {
            "listing": {
                "id": listing['id'],
                "url": listing['url'],
                "address": listing['address'],
                "area_total": float(listing['area_total']) if listing['area_total'] else None,
                "area_living": float(listing['area_living']) if listing['area_living'] else None,
                "area_kitchen": float(listing['area_kitchen']) if listing['area_kitchen'] else None,
                "rooms": listing['rooms'],
                "floor": listing['floor'],
                "total_floors": listing['total_floors'],
                "building_type": listing['building_type'],
                "description": listing['description'],
                "is_active": listing['is_active'],
                "first_seen": listing['first_seen'].isoformat() if listing['first_seen'] else None,
                "last_seen": listing['last_seen'].isoformat() if listing['last_seen'] else None,
                "lat": listing['lat'],
                "lon": listing['lon'],
                "price": float(listing['price']) if listing['price'] else None,
                "initial_price": float(listing['initial_price']) if listing['initial_price'] else None,
                "price_change_count": listing['price_change_count'],
                "price_change_pct": listing['price_change_pct']
            },
            "price_history": [
                {
                    "price": float(p['price']),
                    "date": p['seen_at'].isoformat()
                }
                for p in price_history
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/valuation/refine")
def refine_valuation(request: dict):
    """
    Уточнить оценку, исключив определённые аналоги.
    Сохраняет решение пользователя для обучения.
    """
    import psycopg2
    import json

    valuation_id = request.get('valuation_id')
    excluded_listing_ids = request.get('excluded_listing_ids', [])
    reason = request.get('reason', '')

    if not valuation_id:
        raise HTTPException(status_code=400, detail="valuation_id обязателен")

    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")

    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()

        # Mark comparables as excluded
        for listing_id in excluded_listing_ids:
            cur.execute("""
                UPDATE valuation_comparables
                SET excluded = TRUE, exclusion_reason = %s
                WHERE valuation_id = %s AND listing_id = %s
            """, (reason, valuation_id, listing_id))

        # Get remaining comparables for recalculation
        cur.execute("""
            SELECT listing_id, price, price_per_sqm, area_total, weight
            FROM valuation_comparables
            WHERE valuation_id = %s AND (excluded IS NULL OR excluded = FALSE)
            ORDER BY price_per_sqm ASC
        """, (valuation_id,))

        remaining = cur.fetchall()

        if len(remaining) < 3:
            conn.rollback()
            raise HTTPException(status_code=400, detail="После исключения останется менее 3 аналогов")

        # Recalculate using bottom 3
        top3 = remaining[:3]
        avg_price_per_sqm = float(sum(float(r[2]) for r in top3)) / 3

        # Get area_total from valuation
        cur.execute("SELECT area_total FROM valuation_history WHERE valuation_id = %s", (valuation_id,))
        val_row = cur.fetchone()
        area_total = float(val_row[0]) if val_row else 50.0

        # Apply bargain discount (7%)
        new_price_per_sqm = avg_price_per_sqm * 0.93
        new_estimated_price = new_price_per_sqm * area_total

        # Update valuation
        cur.execute("""
            UPDATE valuation_history
            SET
                estimated_price = %s,
                estimated_price_per_sqm = %s,
                refinement_reason = %s,
                refinement_at = NOW()
            WHERE valuation_id = %s
            RETURNING valuation_id
        """, (new_estimated_price, new_price_per_sqm, reason, valuation_id))

        # Save refinement for AI learning
        cur.execute("""
            INSERT INTO valuation_refinements (
                valuation_id,
                excluded_listing_ids,
                reason,
                original_price,
                refined_price,
                created_at
            ) VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT DO NOTHING
        """, (
            valuation_id,
            json.dumps(excluded_listing_ids),
            reason,
            None,  # will be filled from original
            new_estimated_price
        ))

        conn.commit()
        cur.close()
        conn.close()

        return {
            "success": True,
            "new_estimated_price": new_estimated_price,
            "new_price_per_sqm": new_price_per_sqm,
            "remaining_comparables": len(remaining),
            "message": f"Оценка уточнена. Исключено {len(excluded_listing_ids)} аналогов."
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send-to-telegram")
def send_report_to_telegram(request: dict):
    """Отправка красивой карточки с оценкой в Telegram."""
    valuation_id = request.get('valuation_id')
    telegram_username = request.get('telegram_username')

    if not valuation_id or not telegram_username:
        raise HTTPException(status_code=400, detail="valuation_id and telegram_username required")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=500, detail="Telegram bot не настроен. Обратитесь к администратору.")

    try:
        from .card_generator import generate_telegram_card, generate_telegram_message
    except ImportError:
        raise HTTPException(status_code=500, detail="Card generator not available")

    import psycopg2
    from psycopg2.extras import RealDictCursor

    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")

    try:
        # Get valuation data
        conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        cur.execute("""
            SELECT
                vh.*,
                ARRAY_AGG(
                    json_build_object(
                        'listing_id', vc.listing_id,
                        'url', vc.url,
                        'price', vc.price,
                        'price_per_sqm', vc.price_per_sqm,
                        'area_total', vc.area_total,
                        'distance_km', vc.distance_km
                    ) ORDER BY vc.rank NULLS LAST
                ) as comparables
            FROM valuation_history vh
            LEFT JOIN valuation_comparables vc ON vh.valuation_id = vc.valuation_id
            WHERE vh.valuation_id = %s
            GROUP BY vh.valuation_id
        """, (valuation_id,))

        valuation = cur.fetchone()
        cur.close()
        conn.close()

        if not valuation:
            raise HTTPException(status_code=404, detail="Valuation not found")

        valuation_dict = dict(valuation)

        # Generate card image and message
        card_bytes = generate_telegram_card(valuation_dict)
        message_text = generate_telegram_message(valuation_dict)

        # Send via Telegram Bot API
        import requests

        # Normalize username
        chat_id = telegram_username
        if chat_id.startswith('@'):
            chat_id = chat_id[1:]

        # Send photo with caption
        files = {
            'photo': ('valuation_card.png', card_bytes, 'image/png')
        }
        data = {
            'chat_id': chat_id,
            'caption': message_text,
            'parse_mode': 'HTML'
        }

        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendPhoto",
            data=data,
            files=files,
            timeout=30
        )

        if response.ok:
            return {"success": True, "message": "Отчет успешно отправлен в Telegram!"}
        else:
            error_data = response.json()
            error_msg = error_data.get('description', 'Неизвестная ошибка')
            raise HTTPException(status_code=500, detail=f"Telegram API error: {error_msg}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/generate-report/{valuation_id}")
def generate_report(valuation_id: int):
    """Генерация PDF отчета об оценке."""
    from fastapi.responses import Response
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    try:
        from .report_generator import generate_report_bytes
    except ImportError:
        raise HTTPException(status_code=500, detail="Report generator not available")
    
    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")
    
    try:
        conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        # Get valuation with comparables
        cur.execute("""
            SELECT 
                vh.*,
                ARRAY_AGG(
                    json_build_object(
                        'listing_id', vc.listing_id,
                        'url', vc.url,
                        'price', vc.price,
                        'price_per_sqm', vc.price_per_sqm,
                        'area_total', vc.area_total,
                        'distance_km', vc.distance_km
                    ) ORDER BY vc.rank NULLS LAST
                ) as comparables
            FROM valuation_history vh
            LEFT JOIN valuation_comparables vc ON vh.valuation_id = vc.valuation_id
            WHERE vh.valuation_id = %s
            GROUP BY vh.valuation_id
        """, (valuation_id,))
        
        valuation = cur.fetchone()
        cur.close()
        conn.close()
        
        if not valuation:
            raise HTTPException(status_code=404, detail="Valuation not found")
        
        # Generate PDF
        pdf_bytes = generate_report_bytes(dict(valuation))
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=valuation_report_{valuation_id}.pdf"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === HTML Report Endpoints ===

try:
    from .html_report_generator import (
        generate_valuation_report,
        get_report_by_uuid,
        get_report_html
    )
    HTML_REPORTS_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  HTML report generator not available: {e}")
    HTML_REPORTS_AVAILABLE = False


class ReportGenerateInput(BaseModel):
    """Input for report generation."""
    cian_id: Optional[int] = None
    address: str
    area_total: float
    rooms: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    district: Optional[str] = None
    metro: Optional[str] = None
    seller_price: Optional[float] = None

    # Valuation data
    interest_price: float
    interest_price_per_sqm: float
    market_price_low: Optional[float] = None
    market_price_high: Optional[float] = None

    # Statistics
    avg_price_per_sqm: float = 0
    median_price_per_sqm: float = 0
    min_price_per_sqm: float = 0
    max_price_per_sqm: float = 0

    # BOTTOM-3 data
    bottom3_avg: float = 0
    bottom3_prices: Optional[List[float]] = None
    bargain_percent: int = 7

    # Analogs
    rosreestr_deals: Optional[List[dict]] = None
    cian_analogs: Optional[List[dict]] = None
    bottom3_analogs: Optional[List[dict]] = None

    # Telegram
    telegram_user_id: Optional[int] = None
    telegram_chat_id: Optional[int] = None


@app.post("/reports/generate")
def api_generate_report(data: ReportGenerateInput):
    """
    Generate HTML valuation report.

    Returns report UUID and URL for accessing the report.
    """
    if not HTML_REPORTS_AVAILABLE:
        raise HTTPException(status_code=501, detail="HTML report generator not available")

    try:
        result = generate_valuation_report(
            cian_id=data.cian_id,
            address=data.address,
            area_total=data.area_total,
            rooms=data.rooms,
            floor=data.floor,
            total_floors=data.total_floors,
            district=data.district,
            metro=data.metro,
            seller_price=data.seller_price,

            interest_price=data.interest_price,
            interest_price_per_sqm=data.interest_price_per_sqm,
            market_price_low=data.market_price_low,
            market_price_high=data.market_price_high,

            avg_price_per_sqm=data.avg_price_per_sqm,
            median_price_per_sqm=data.median_price_per_sqm,
            min_price_per_sqm=data.min_price_per_sqm,
            max_price_per_sqm=data.max_price_per_sqm,

            bottom3_avg=data.bottom3_avg,
            bottom3_prices=data.bottom3_prices or [],
            bargain_percent=data.bargain_percent,

            rosreestr_deals=data.rosreestr_deals,
            cian_analogs=data.cian_analogs,
            bottom3_analogs=data.bottom3_analogs,

            telegram_user_id=data.telegram_user_id,
            telegram_chat_id=data.telegram_chat_id,
        )

        return {
            "success": True,
            "report_uuid": result["report_uuid"],
            "report_url": result["report_url"],
            "full_url": f"https://nevsky.express{result['report_url']}",
            "created_at": result["created_at"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@app.get("/r/{report_uuid}")
def view_report(report_uuid: str):
    """
    View HTML report by UUID.

    Returns HTML content directly for rendering in browser.
    """
    if not HTML_REPORTS_AVAILABLE:
        raise HTTPException(status_code=501, detail="HTML report generator not available")

    html_content = get_report_html(report_uuid)

    if not html_content:
        raise HTTPException(status_code=404, detail="Report not found")

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content)


@app.get("/reports/{report_uuid}")
def get_report(report_uuid: str):
    """
    Get report data by UUID.

    Returns report metadata and data in JSON format.
    """
    if not HTML_REPORTS_AVAILABLE:
        raise HTTPException(status_code=501, detail="HTML report generator not available")

    report = get_report_by_uuid(report_uuid)

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Don't return full HTML in JSON response
    report_copy = dict(report)
    report_copy.pop('html_content', None)

    return {
        "success": True,
        "report": report_copy,
    }


@app.get("/reports")
def list_reports(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    telegram_user_id: Optional[int] = None,
):
    """
    List recent reports.
    """
    if not HTML_REPORTS_AVAILABLE:
        raise HTTPException(status_code=501, detail="HTML report generator not available")

    import psycopg2
    from psycopg2.extras import RealDictCursor

    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")

    try:
        conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        if telegram_user_id:
            cur.execute("""
                SELECT report_uuid, cian_id, address, area_total, rooms,
                       interest_price, seller_price, created_at
                FROM valuation_reports
                WHERE telegram_user_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (telegram_user_id, limit, offset))
        else:
            cur.execute("""
                SELECT report_uuid, cian_id, address, area_total, rooms,
                       interest_price, seller_price, created_at
                FROM valuation_reports
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))

        reports = cur.fetchall()
        cur.close()
        conn.close()

        return {
            "success": True,
            "reports": [dict(r) for r in reports],
            "count": len(reports),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Claude Parser Endpoints ===

class ParseTextInput(BaseModel):
    """Input for text parsing."""
    text: str = Field(..., description="Text to parse (property description, listing text, etc.)")


class ParsedDataOutput(BaseModel):
    """Output from Claude parser."""
    address: Optional[str] = None
    area_total: Optional[float] = None
    area_living: Optional[float] = None
    area_kitchen: Optional[float] = None
    rooms: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    building_type: Optional[str] = None
    building_year: Optional[int] = None
    price: Optional[float] = None
    cadastral_number: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    source_type: str = "unknown"
    confidence: int = 0
    parse_notes: Optional[str] = None


@app.post("/parse/text", response_model=ParsedDataOutput)
def api_parse_text(data: ParseTextInput):
    """
    Parse property data from arbitrary text using Claude AI.

    Examples of supported input:
    - "2-комнатная квартира, 65 м², 5/17 этаж, панельный дом 2006 года"
    - Pasted text from CIAN listing
    - Property description from chat/email
    - Any text containing property parameters
    """
    if not CLAUDE_PARSER_AVAILABLE:
        raise HTTPException(status_code=501, detail="Claude parser not available")

    try:
        result = parse_text(data.text)

        # Try to geocode if address found
        if result.address and not (result.lat and result.lon):
            try:
                result = enhance_parsed_data(result)
            except Exception as e:
                print(f"Enhancement error: {e}")

        return ParsedDataOutput(**result.model_dump())

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse error: {str(e)}")


@app.post("/parse/image", response_model=ParsedDataOutput)
async def api_parse_image(
    file: UploadFile = File(..., description="Image or PDF file")
):
    """
    Parse property data from image or PDF using Claude Vision.

    Supported file types:
    - Images: JPEG, PNG, WebP, GIF
    - PDF documents (first page will be converted to image)

    Supported documents:
    - Screenshots of CIAN listings
    - EGRN extract (Выписка ЕГРН)
    - Purchase agreement (ДКП)
    - Any document with property information
    """
    if not CLAUDE_PARSER_AVAILABLE:
        raise HTTPException(status_code=501, detail="Claude parser not available")

    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: JPEG, PNG, WebP, GIF, PDF"
        )

    # Check file size (max 10MB)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size: 10MB")

    # Handle PDF files
    mime_type = file.content_type
    if file.content_type == "application/pdf":
        try:
            import fitz  # PyMuPDF
            pdf_doc = fitz.open(stream=contents, filetype="pdf")
            if pdf_doc.page_count == 0:
                raise HTTPException(status_code=400, detail="PDF is empty")

            # Convert first page to image
            page = pdf_doc[0]
            # Render at 2x resolution for better OCR
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            contents = pix.tobytes("jpeg")
            mime_type = "image/jpeg"
            pdf_doc.close()
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="PDF support not available. Install PyMuPDF: pip install pymupdf"
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to process PDF: {str(e)}")

    try:
        result = parse_image(contents, mime_type)

        # Try to geocode if address found
        if result.address and not (result.lat and result.lon):
            try:
                result = enhance_parsed_data(result)
            except Exception as e:
                print(f"Enhancement error: {e}")

        return ParsedDataOutput(**result.model_dump())

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse error: {str(e)}")


@app.post("/parse/url", response_model=ParsedDataOutput)
def api_parse_url(url: str = Query(..., description="Property listing URL (CIAN, Avito, Yandex)")):
    """
    Parse property data from listing URL.

    Supported platforms:
    - CIAN: cian.ru/flat/...
    - Avito: avito.ru/.../kvartiry/...
    - Yandex Realty: realty.yandex.ru/offer/..., realty.ya.ru/offer/...

    For CIAN, first checks our database for the listing.
    For Avito/Yandex, tries to fetch page and extract data with Claude.
    """
    if not CLAUDE_PARSER_AVAILABLE:
        raise HTTPException(status_code=501, detail="Claude parser not available")

    try:
        # Determine platform and use appropriate parser
        if 'cian.ru' in url:
            result = parse_cian_url(url)
        elif 'avito.ru' in url:
            result = parse_avito_url(url)
        elif 'realty.yandex.ru' in url or 'realty.ya.ru' in url:
            result = parse_yandex_realty_url(url)
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported URL. Supported platforms: cian.ru, avito.ru, realty.yandex.ru"
            )

        # Geocode address if coordinates are missing
        if result.address and (result.lat is None or result.lon is None):
            geo = geocode_address(result.address)
            if geo:
                result.lat = geo.get('lat')
                result.lon = geo.get('lon')

        return ParsedDataOutput(**result.model_dump())

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse error: {str(e)}")


@app.post("/smart-estimate")
async def smart_estimate(
    text: Optional[str] = Form(None, description="Text description of property"),
    file: Optional[UploadFile] = File(None, description="Image of document"),
    url: Optional[str] = Form(None, description="CIAN listing URL"),
    # Optional manual overrides
    area_total: Optional[float] = Form(None),
    rooms: Optional[int] = Form(None),
    floor: Optional[int] = Form(None),
    total_floors: Optional[int] = Form(None),
    building_type: Optional[str] = Form(None),
    building_year: Optional[int] = Form(None),
    k: int = Form(10, ge=1, le=50),
    max_distance_km: float = Form(5.0, ge=0.5, le=20.0),
):
    """
    Smart valuation endpoint: parse input automatically and estimate.

    Accepts:
    - Text description (parsed with Claude)
    - Image upload (parsed with Claude Vision)
    - CIAN URL (looked up in database)
    - Manual parameter overrides

    Returns full valuation with comparables.
    """
    if not CLAUDE_PARSER_AVAILABLE:
        raise HTTPException(status_code=501, detail="Claude parser not available")

    parsed_data = None

    # Parse from input source
    if url:
        # Определить платформу и использовать соответствующий парсер
        if 'cian.ru' in url:
            parsed_data = parse_cian_url(url)
        elif 'avito.ru' in url:
            parsed_data = parse_avito_url(url)
        elif 'realty.yandex.ru' in url or 'realty.ya.ru' in url:
            parsed_data = parse_yandex_realty_url(url)
        else:
            raise HTTPException(
                status_code=400,
                detail="Неподдерживаемый URL. Поддерживаемые платформы: cian.ru, avito.ru, realty.yandex.ru"
            )
    elif file:
        contents = await file.read()
        if len(contents) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large")
        parsed_data = parse_image(contents, file.content_type or "image/jpeg")
    elif text:
        parsed_data = parse_text(text)
    else:
        raise HTTPException(status_code=400, detail="Provide text, file, or url")

    # Apply manual overrides
    if area_total:
        parsed_data.area_total = area_total
    if rooms:
        parsed_data.rooms = rooms
    if floor:
        parsed_data.floor = floor
    if total_floors:
        parsed_data.total_floors = total_floors
    if building_type:
        parsed_data.building_type = building_type
    if building_year:
        parsed_data.building_year = building_year

    # Validate required fields
    if not parsed_data.area_total:
        raise HTTPException(
            status_code=400,
            detail="Could not determine area. Please provide area_total parameter."
        )

    # Try to geocode address
    if parsed_data.address and not (parsed_data.lat and parsed_data.lon):
        try:
            parsed_data = enhance_parsed_data(parsed_data)
        except Exception:
            pass

    # If still no coordinates, try address search
    if not (parsed_data.lat and parsed_data.lon) and parsed_data.address:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            import re

            dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")
            conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
            cur = conn.cursor()

            # Normalize address for search
            addr = parsed_data.address
            # Remove common abbreviations
            addr = re.sub(r'\bул\.\s*', '', addr, flags=re.IGNORECASE)
            addr = re.sub(r'\bд\.\s*', '', addr, flags=re.IGNORECASE)
            addr = re.sub(r'\bдом\s*', '', addr, flags=re.IGNORECASE)
            addr = re.sub(r'\bг\.\s*', '', addr, flags=re.IGNORECASE)
            addr = re.sub(r'\bМосква,?\s*', '', addr, flags=re.IGNORECASE)
            addr = addr.strip(' ,')

            # Extract street name and house number
            match = re.search(r'([А-Яа-яёЁ\-\s]+?),?\s*(\d+)', addr)
            if match:
                street_name = match.group(1).strip()
                house_num = match.group(2)
                # Search for street name + house number
                search_pattern = f'%{street_name}%{house_num}%'
            else:
                search_pattern = f'%{addr}%'

            cur.execute("""
                SELECT lat, lon, address, total_floors, house_year, building_type FROM listings
                WHERE address ILIKE %s AND lat IS NOT NULL AND lon IS NOT NULL
                ORDER BY last_seen DESC
                LIMIT 1
            """, (search_pattern,))

            result = cur.fetchone()

            # If not found, try just street name
            if not result and match:
                cur.execute("""
                    SELECT lat, lon, address, total_floors, house_year, building_type FROM listings
                    WHERE address ILIKE %s AND lat IS NOT NULL AND lon IS NOT NULL
                    ORDER BY last_seen DESC
                    LIMIT 1
                """, (f'%{street_name}%',))
                result = cur.fetchone()

            cur.close()
            conn.close()

            if result:
                parsed_data.lat = result['lat']
                parsed_data.lon = result['lon']
                # ВАЖНО: Заполняем этажность и год постройки из базы если не были распознаны
                if not parsed_data.total_floors and result.get('total_floors'):
                    parsed_data.total_floors = result['total_floors']
                    print(f"📊 Got total_floors from DB: {result['total_floors']}")
                if not parsed_data.building_year and result.get('house_year'):
                    parsed_data.building_year = result['house_year']
                    print(f"📅 Got building_year from DB: {result['house_year']}")
                if not parsed_data.building_type and result.get('building_type'):
                    parsed_data.building_type = result['building_type']
                    print(f"🏢 Got building_type from DB: {result['building_type']}")
                print(f"📍 Found coordinates from DB: {result['address']}")
        except Exception as e:
            print(f"Address lookup error: {e}")

    if not (parsed_data.lat and parsed_data.lon):
        raise HTTPException(
            status_code=400,
            detail="Could not determine coordinates. Please provide lat/lon or a valid address."
        )

    # Build PropertyInput and call estimate
    # ВАЖНО: передаём cian_listing_id для исключения из аналогов
    property_input = PropertyInput(
        address=parsed_data.address,
        lat=parsed_data.lat,
        lon=parsed_data.lon,
        area_total=parsed_data.area_total,
        rooms=parsed_data.rooms,
        floor=parsed_data.floor,
        total_floors=parsed_data.total_floors,
        building_type=parsed_data.building_type,
        building_year=parsed_data.building_year,
        exclude_listing_id=getattr(parsed_data, 'cian_listing_id', None),
    )

    # Use existing estimate endpoint logic
    return estimate_property(property_input, k=k, max_distance_km=max_distance_km, max_age_days=90)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
