"""Claude-powered parser for extracting property data from text and images."""

import os
import base64
import json
import re
from typing import Optional, List
from pydantic import BaseModel, Field
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("Warning: anthropic package not installed")


# Claude API key from environment
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


class ParsedPropertyData(BaseModel):
    """Extracted property data from text/image."""
    address: Optional[str] = Field(None, description="Full address")
    area_total: Optional[float] = Field(None, description="Total area in sqm")
    area_living: Optional[float] = Field(None, description="Living area in sqm")
    area_kitchen: Optional[float] = Field(None, description="Kitchen area in sqm")
    rooms: Optional[int] = Field(None, description="Number of rooms")
    floor: Optional[int] = Field(None, description="Floor number")
    total_floors: Optional[int] = Field(None, description="Total floors in building")
    building_type: Optional[str] = Field(None, description="Building type: panel, brick, monolithic, block")
    building_year: Optional[int] = Field(None, description="Year built")
    price: Optional[float] = Field(None, description="Price in rubles")
    cadastral_number: Optional[str] = Field(None, description="Cadastral number")

    # Coordinates if found
    lat: Optional[float] = Field(None, description="Latitude")
    lon: Optional[float] = Field(None, description="Longitude")

    # Source info
    source_type: str = Field("unknown", description="text, image, cian_url, egrn, dkp")
    confidence: int = Field(50, description="Confidence 0-100")
    raw_text: Optional[str] = Field(None, description="Original text for debugging")
    parse_notes: Optional[str] = Field(None, description="Notes about parsing")

    # CIAN listing ID (для исключения из аналогов при оценке)
    cian_listing_id: Optional[int] = Field(None, description="CIAN listing ID")


# System prompt for property extraction
PROPERTY_EXTRACTION_PROMPT = """Ты - эксперт по анализу недвижимости в России. Твоя задача - извлечь параметры квартиры из текста или изображения.

Извлеки следующие параметры (если найдены):
- address: полный адрес (улица, дом, корпус)
- area_total: общая площадь в м²
- area_living: жилая площадь в м²
- area_kitchen: площадь кухни в м²
- rooms: количество комнат (число)
- floor: этаж
- total_floors: этажность дома
- building_type: тип дома (panel/brick/monolithic/block)
- building_year: год постройки
- price: цена в рублях (без пробелов)
- cadastral_number: кадастровый номер (если есть)

ВАЖНО:
- Если параметр не найден, верни null
- Цену указывай только числом без символов валюты
- Площадь указывай только числом
- Для building_type используй только: panel (панельный), brick (кирпичный), monolithic (монолитный), block (блочный)
- Год постройки - только 4-значное число

Верни результат в JSON формате:
{
    "address": "...",
    "area_total": 65.5,
    "rooms": 2,
    "floor": 5,
    "total_floors": 17,
    "building_type": "panel",
    "building_year": 2006,
    "price": 15000000,
    "confidence": 85,
    "source_type": "text",
    "parse_notes": "..."
}"""


def parse_text(text: str) -> ParsedPropertyData:
    """
    Parse property data from arbitrary text description.

    Examples of input:
    - "2-комнатная квартира, 65 м², 5/17 этаж, панельный дом 2006 года"
    - "Продаю 3к квартиру на Коцюбинского 10, 80 кв.м, 7 этаж, цена 18 млн"
    - Pasted text from CIAN listing
    """
    if not ANTHROPIC_AVAILABLE or not ANTHROPIC_API_KEY:
        return _fallback_parse_text(text)

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=PROPERTY_EXTRACTION_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Извлеки параметры квартиры из текста:\n\n{text}"
                }
            ]
        )

        # Extract JSON from response
        response_text = response.content[0].text

        # Try to find JSON in response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            data = json.loads(json_match.group())
            data['raw_text'] = text[:500]  # Keep first 500 chars for debugging
            data['source_type'] = 'text'
            return ParsedPropertyData(**data)
        else:
            return _fallback_parse_text(text)

    except Exception as e:
        print(f"Claude API error: {e}")
        return _fallback_parse_text(text)


def parse_image(image_data: bytes, mime_type: str = "image/jpeg") -> ParsedPropertyData:
    """
    Parse property data from image using Claude Vision.

    Supports:
    - Screenshots of CIAN listings
    - EGRN extract (Выписка ЕГРН)
    - Purchase agreement (ДКП)
    - Any document with property info
    """
    if not ANTHROPIC_AVAILABLE or not ANTHROPIC_API_KEY:
        return ParsedPropertyData(
            source_type="image",
            confidence=0,
            parse_notes="Claude Vision not available"
        )

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Encode image to base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=PROPERTY_EXTRACTION_PROMPT + """

Это изображение документа или скриншот. Внимательно прочитай весь текст на изображении.

Типы документов:
- Выписка ЕГРН: ищи кадастровый номер, адрес, площадь
- ДКП (договор купли-продажи): ищи адрес, площадь, цену, стороны сделки
- Скриншот ЦИАН: ищи все параметры объявления
- Карточка объекта: ищи характеристики квартиры""",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": image_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": "Извлеки параметры квартиры из этого изображения. Определи тип документа."
                        }
                    ]
                }
            ]
        )

        response_text = response.content[0].text

        # Try to find JSON in response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            data = json.loads(json_match.group())
            data['source_type'] = 'image'
            return ParsedPropertyData(**data)
        else:
            return ParsedPropertyData(
                source_type="image",
                confidence=20,
                parse_notes=f"Could not extract structured data. Response: {response_text[:200]}"
            )

    except Exception as e:
        print(f"Claude Vision error: {e}")
        return ParsedPropertyData(
            source_type="image",
            confidence=0,
            parse_notes=f"Error: {str(e)}"
        )


def parse_cian_url(url: str) -> ParsedPropertyData:
    """
    Parse CIAN listing URL and extract data from the page.
    """
    import requests

    # Extract listing ID from URL
    match = re.search(r'/flat/(\d+)', url)
    if not match:
        return ParsedPropertyData(
            source_type="cian_url",
            confidence=0,
            parse_notes="Invalid CIAN URL format"
        )

    listing_id = match.group(1)

    # Try to get from our database first
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")
        conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        cur.execute("""
            SELECT
                l.address, l.area_total, l.area_living, l.area_kitchen,
                l.rooms, l.floor, l.total_floors, l.building_type,
                l.house_year as building_year, l.lat, l.lon,
                COALESCE(lp.price, l.initial_price) as price
            FROM listings l
            LEFT JOIN LATERAL (
                SELECT price FROM listing_prices WHERE id = l.id ORDER BY seen_at DESC LIMIT 1
            ) lp ON true
            WHERE l.id = %s OR l.url LIKE %s
        """, (listing_id, f'%{listing_id}%'))

        result = cur.fetchone()
        cur.close()
        conn.close()

        if result:
            return ParsedPropertyData(
                address=result['address'],
                area_total=float(result['area_total']) if result['area_total'] else None,
                area_living=float(result['area_living']) if result['area_living'] else None,
                area_kitchen=float(result['area_kitchen']) if result['area_kitchen'] else None,
                rooms=result['rooms'],
                floor=result['floor'],
                total_floors=result['total_floors'],
                building_type=result['building_type'],
                building_year=result['building_year'],
                lat=result['lat'],
                lon=result['lon'],
                price=float(result['price']) if result['price'] else None,
                source_type="cian_url",
                confidence=95,
                parse_notes=f"Found in database: listing {listing_id}",
                cian_listing_id=int(listing_id)  # Для исключения из аналогов
            )
    except Exception as e:
        print(f"Database lookup error: {e}")

    # Fallback: try to fetch and parse CIAN page
    return ParsedPropertyData(
        source_type="cian_url",
        confidence=10,
        parse_notes=f"Listing {listing_id} not found in database. Manual entry needed."
    )


def _fallback_parse_text(text: str) -> ParsedPropertyData:
    """
    Fallback regex-based parser when Claude is not available.
    """
    result = ParsedPropertyData(source_type="text", confidence=30, raw_text=text[:500])

    # Extract rooms
    rooms_match = re.search(r'(\d+)[\s-]*(комн|к\b|комнат)', text, re.IGNORECASE)
    if rooms_match:
        result.rooms = int(rooms_match.group(1))

    # Extract area
    area_match = re.search(r'(\d+[,.]?\d*)\s*(м²|кв\.?\s*м|квадрат)', text, re.IGNORECASE)
    if area_match:
        result.area_total = float(area_match.group(1).replace(',', '.'))

    # Extract floor/total_floors (e.g., "5/17 этаж")
    floor_match = re.search(r'(\d+)\s*/\s*(\d+)\s*(эт|этаж)', text, re.IGNORECASE)
    if floor_match:
        result.floor = int(floor_match.group(1))
        result.total_floors = int(floor_match.group(2))

    # Extract year
    year_match = re.search(r'(19\d{2}|20[012]\d)\s*(г\.?|год)', text, re.IGNORECASE)
    if year_match:
        result.building_year = int(year_match.group(1))

    # Extract building type
    if re.search(r'панел', text, re.IGNORECASE):
        result.building_type = 'panel'
    elif re.search(r'кирпич', text, re.IGNORECASE):
        result.building_type = 'brick'
    elif re.search(r'монолит', text, re.IGNORECASE):
        result.building_type = 'monolithic'
    elif re.search(r'блоч', text, re.IGNORECASE):
        result.building_type = 'block'

    # Extract price (e.g., "15 млн", "15000000", "15 000 000")
    price_match = re.search(r'(\d+[\s,.]?\d*)\s*(млн|миллион)', text, re.IGNORECASE)
    if price_match:
        price_str = price_match.group(1).replace(' ', '').replace(',', '.')
        result.price = float(price_str) * 1_000_000
    else:
        price_match = re.search(r'(\d[\d\s]{5,})\s*(руб|₽)?', text)
        if price_match:
            price_str = price_match.group(1).replace(' ', '')
            if len(price_str) >= 6:  # At least 1 million
                result.price = float(price_str)

    # Extract address (simple heuristic)
    address_patterns = [
        r'(ул\.\s*[А-Яа-я\s]+,?\s*д\.?\s*\d+[а-яА-Я]?)',
        r'(улица\s+[А-Яа-я\s]+,?\s*\d+[а-яА-Я]?)',
        r'([А-Яа-я]+\s+проспект,?\s*\d+)',
        r'([А-Яа-я]+\s+бульвар,?\s*\d+)',
    ]
    for pattern in address_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result.address = match.group(1).strip()
            break

    result.parse_notes = "Parsed with fallback regex (Claude not available)"
    return result


# Helper function to validate and enhance parsed data
def enhance_parsed_data(data: ParsedPropertyData) -> ParsedPropertyData:
    """
    Enhance parsed data with geocoding and database lookups.
    """
    if data.address and not (data.lat and data.lon):
        # Try to geocode address
        try:
            from .geocode_helper import geocode_address
            coords = geocode_address(data.address)
            if coords:
                data.lat = coords['lat']
                data.lon = coords['lon']
        except ImportError:
            pass

    return data
