#!/usr/bin/env python3
"""
Telegram bot for real estate valuation.

Features:
- Address input → automatic valuation
- EGRN document parsing
- Smart rooms detection by area
- Interactive parameter selection
"""

import os
import sys
import logging
import requests
import re
from typing import Optional, Dict, Any, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# Admin keyboard (always visible)
ADMIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📊 Статус"), KeyboardButton("📦 База")],
        [KeyboardButton("🤖 Парсеры"), KeyboardButton("🔒 Прокси")],
        [KeyboardButton("⚙️ Управление")],
    ],
    resize_keyboard=True,
    is_persistent=True
)

# Regular user keyboard
USER_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🏠 Оценить квартиру")],
        [KeyboardButton("📖 Помощь")],
    ],
    resize_keyboard=True,
    is_persistent=True
)

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration
API_URL = os.getenv('VALUATION_API_URL', 'http://localhost:8001')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def estimate_rooms_by_area(
    area: float, 
    building_type: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None
) -> Tuple[int, float, str]:
    """
    Estimate number of rooms based on area and building type from database.
    
    Returns: (rooms, confidence, explanation)
    """
    try:
        from smart_params import estimate_rooms_smart, find_similar_listings_by_area
        
        rooms, confidence = estimate_rooms_smart(area, building_type, lat, lon)
        
        # Get similar listings for explanation
        similar = find_similar_listings_by_area(area, building_type, radius=10)
        
        if similar and len(similar) > 0:
            top_match = similar[0]
            explanation = (
                f"На основе {sum(s['cnt'] for s in similar[:3])} похожих объявлений "
                f"({area}±10 м², {building_type or 'любой тип'})"
            )
        else:
            explanation = f"На основе статистики рынка ({area} м²)"
        
        return rooms, confidence, explanation
        
    except Exception as e:
        logger.error(f"Smart estimation failed: {e}, using fallback")
        # Fallback to simple heuristic
        if area < 30:
            return 1, 0.6, "Простая оценка по площади"
        elif area < 45:
            return 1, 0.7, "Простая оценка по площади"
        elif area < 70:
            return 2, 0.7, "Простая оценка по площади"
        elif area < 90:
            return 3, 0.7, "Простая оценка по площади"
        elif area < 120:
            return 4, 0.6, "Простая оценка по площади"
        else:
            return 5, 0.5, "Простая оценка по площади"


def get_rooms_from_similar_listings(address: str, area: float) -> Optional[int]:
    """Get most common room count from similar listings in the area."""
    try:
        response = requests.get(
            f"{API_URL}/search-address",
            params={'q': address},
            timeout=10
        )
        
        if response.ok:
            data = response.json()
            # This would require additional API endpoint
            # For now, return None to fallback to area-based estimation
            return None
            
    except Exception as e:
        logger.error(f"Error searching similar listings: {e}")
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    from admin_commands import is_admin

    user = update.effective_user
    chat = update.effective_chat

    # Check if admin
    if is_admin(user.id):
        welcome_text = f"""
🔧 *Админ-панель парсера CIAN*

👤 {user.first_name} (ID: `{user.id}`)
💬 Chat ID: `{chat.id}`

Используйте кнопки ниже для управления системой.

*Доступные функции:*
📊 Статус - полный отчёт о системе
📦 База - статистика объявлений
🤖 Парсеры - состояние парсеров
🔒 Прокси - мониторинг трафика
⚙️ Управление - перезапуск/остановка
"""
        await update.message.reply_text(
            welcome_text,
            parse_mode='Markdown',
            reply_markup=ADMIN_KEYBOARD
        )
    else:
        # Regular user welcome
        welcome_text = f"""
🏠 *Бот оценки недвижимости*

Я помогу вам оценить квартиру в Москве!

*Что я умею:*
• Оценка по адресу
• Парсинг выписки ЕГРН
• Автоопределение параметров

*Как пользоваться:*
Просто напишите адрес, например:
`Новоясеневский проспект 32`

Или отправьте файл ЕГРН (PDF)
"""
        await update.message.reply_text(
            welcome_text,
            parse_mode='Markdown',
            reply_markup=USER_KEYBOARD
        )


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's chat ID."""
    chat = update.effective_chat
    user = update.effective_user

    text = f"""
*Ваши ID:*
Chat ID: `{chat.id}`
User ID: `{user.id}`
Username: @{user.username or 'не указан'}

Тип чата: {chat.type}
"""
    await update.message.reply_text(text, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = """
📖 *Справка*

*Примеры адресов:*
• Новоясеневский проспект 32
• Тверская улица 12
• Ленинский проспект 30

*Что определяется автоматически:*
✅ Координаты дома
✅ Район
✅ Тип дома (панель/кирпич/монолит)
✅ Количество комнат (по площади)

*Что нужно указать:*
📏 Площадь квартиры (обязательно)

*Опционально:*
• Этаж
• Всего этажей в доме

*Формат ЕГРН:*
Отправьте PDF файл выписки ЕГРН, я извлеку:
• Адрес
• Площадь
• Этаж
• Кадастровый номер
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle address input from user."""
    text = update.message.text.strip()

    # Ignore commands
    if text.startswith('/'):
        return

    logger.info(f"Received text: {text}")

    # Try to parse property description
    try:
        response = requests.post(
            f"{API_URL}/parse-property",
            json={'text': text},
            timeout=10
        )
        if response.ok:
            parsed = response.json()

            # If we got area from parsing, skip area input
            if parsed.get('area') and parsed.get('lat') and parsed.get('lon'):
                context.user_data['address'] = parsed.get('address') or text
                context.user_data['area'] = parsed['area']
                context.user_data['lat'] = parsed['lat']
                context.user_data['lon'] = parsed['lon']
                if parsed.get('rooms'):
                    context.user_data['rooms'] = parsed['rooms']
                if parsed.get('floor'):
                    context.user_data['floor'] = parsed['floor']
                if parsed.get('total_floors'):
                    context.user_data['total_floors'] = parsed['total_floors']

                # Show parsed data
                info_text = f"📍 Адрес: *{parsed.get('address_formatted') or context.user_data['address']}*\n"
                info_text += f"📏 Площадь: *{parsed['area']} м²*\n"
                if parsed.get('rooms'):
                    info_text += f"🏠 Комнат: *{parsed['rooms']}*\n"
                if parsed.get('floor'):
                    info_text += f"🔢 Этаж: *{parsed['floor']}"
                    if parsed.get('total_floors'):
                        info_text += f"/{parsed['total_floors']}"
                    info_text += "*\n"

                await update.message.reply_text(
                    f"✅ Распознано:\n{info_text}\n⏳ Оцениваю квартиру...",
                    parse_mode='Markdown'
                )

                # If rooms not parsed, ask for them
                if not parsed.get('rooms'):
                    area = parsed['area']
                    estimated_rooms, confidence, explanation = estimate_rooms_by_area(area)

                    keyboard = [
                        [
                            InlineKeyboardButton("Студия", callback_data='rooms_0'),
                            InlineKeyboardButton("1 комн", callback_data='rooms_1'),
                            InlineKeyboardButton("2 комн", callback_data='rooms_2'),
                        ],
                        [
                            InlineKeyboardButton("3 комн", callback_data='rooms_3'),
                            InlineKeyboardButton("4 комн", callback_data='rooms_4'),
                            InlineKeyboardButton("5+ комн", callback_data='rooms_5'),
                        ],
                        [
                            InlineKeyboardButton(
                                f"✅ {estimated_rooms} комн (авто)",
                                callback_data=f'rooms_{estimated_rooms}_auto'
                            )
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await update.message.reply_text(
                        f"Выберите количество комнат:",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    return

                # Proceed to valuation
                await perform_valuation(update, context)
                return

    except Exception as e:
        logger.warning(f"Parse error: {e}")

    # Fallback: treat as simple address
    context.user_data['address'] = text

    # Ask for area
    await update.message.reply_text(
        f"📍 Адрес: *{text}*\n\n"
        f"Теперь укажите площадь квартиры (м²):\n"
        f"Например: `75` или `75.5`",
        parse_mode='Markdown'
    )

    context.user_data['step'] = 'waiting_for_area'


async def handle_area_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle area input and proceed with valuation."""
    text = update.message.text.strip()
    
    # Try to parse area
    try:
        area = float(text.replace(',', '.'))
        
        if area < 10 or area > 500:
            await update.message.reply_text(
                "⚠️ Площадь должна быть от 10 до 500 м²"
            )
            return
            
    except ValueError:
        await update.message.reply_text(
            "⚠️ Пожалуйста, укажите площадь числом, например: 75"
        )
        return
    
    context.user_data['area'] = area
    
    # Try to get building type and coordinates if available
    address = context.user_data.get('address')
    building_type = None
    lat = None
    lon = None
    
    # Try to geocode and get building type
    if address:
        try:
            response = requests.get(
                f"{API_URL}/search-address",
                params={'q': address},
                timeout=5
            )
            if response.ok:
                data = response.json()
                if data.get('results'):
                    lat = data['results'][0]['lat']
                    lon = data['results'][0]['lon']
        except (requests.RequestException, KeyError, TypeError, ValueError):
            pass
    
    # Estimate rooms with smart algorithm
    estimated_rooms, confidence, explanation = estimate_rooms_by_area(area, building_type, lat, lon)
    
    # Create inline keyboard for room selection
    keyboard = [
        [
            InlineKeyboardButton("Студия", callback_data='rooms_0'),
            InlineKeyboardButton("1 комн", callback_data='rooms_1'),
            InlineKeyboardButton("2 комн", callback_data='rooms_2'),
        ],
        [
            InlineKeyboardButton("3 комн", callback_data='rooms_3'),
            InlineKeyboardButton("4 комн", callback_data='rooms_4'),
            InlineKeyboardButton("5+ комн", callback_data='rooms_5'),
        ],
        [
            InlineKeyboardButton(
                f"✅ {estimated_rooms} комн (авто)", 
                callback_data=f'rooms_{estimated_rooms}_auto'
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    confidence_emoji = "🎯" if confidence > 0.8 else "🤖" if confidence > 0.6 else "❓"
    confidence_text = f"({confidence*100:.0f}% уверенность)" if confidence > 0.5 else ""
    
    await update.message.reply_text(
        f"📏 Площадь: *{area} м²*\n\n"
        f"{confidence_emoji} Предполагаю *{estimated_rooms}-комнатную* квартиру {confidence_text}\n"
        f"_{explanation}_\n\n"
        f"Выберите количество комнат:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def handle_room_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle room count selection from inline keyboard."""
    query = update.callback_query
    await query.answer()
    
    # Parse callback data
    data = query.data
    rooms = int(data.split('_')[1])
    is_auto = '_auto' in data
    
    context.user_data['rooms'] = rooms
    
    # Optional: ask for floor
    keyboard = [
        [
            InlineKeyboardButton("Указать этаж", callback_data='floor_ask'),
            InlineKeyboardButton("Пропустить →", callback_data='floor_skip'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    source_text = "автоопределение 🤖" if is_auto else "выбрано вручную ✋"
    
    await query.edit_message_text(
        f"📏 Площадь: *{context.user_data['area']} м²*\n"
        f"🏠 Комнат: *{rooms}* ({source_text})\n\n"
        f"Хотите указать этаж?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def handle_floor_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle floor skip and proceed to valuation."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "⏳ Оцениваю квартиру...\n\n"
        "Это может занять несколько секунд."
    )
    
    await perform_valuation(update, context, query)


async def handle_floor_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask user for floor number."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "На каком этаже находится квартира?\n"
        "Напишите число, например: `5`",
        parse_mode='Markdown'
    )
    
    context.user_data['step'] = 'waiting_for_floor'


async def handle_floor_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle floor input."""
    text = update.message.text.strip()
    
    try:
        floor = int(text)
        
        if floor < 1 or floor > 100:
            await update.message.reply_text(
                "⚠️ Этаж должен быть от 1 до 100"
            )
            return
            
        context.user_data['floor'] = floor
        
        # Ask for total floors
        keyboard = [
            [
                InlineKeyboardButton("Пропустить →", callback_data='total_floors_skip'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"Этаж: *{floor}*\n\n"
            f"Сколько всего этажей в доме? (или пропустите)",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        context.user_data['step'] = 'waiting_for_total_floors'
        
    except ValueError:
        await update.message.reply_text(
            "⚠️ Пожалуйста, укажите этаж числом, например: 5"
        )


async def perform_valuation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    query = None
) -> None:
    """Perform valuation API call and send results."""

    address = context.user_data.get('address')
    area = context.user_data.get('area')
    rooms = context.user_data.get('rooms')
    floor = context.user_data.get('floor')
    total_floors = context.user_data.get('total_floors')
    lat = context.user_data.get('lat')
    lon = context.user_data.get('lon')

    try:
        # First, get coordinates if we don't have them
        if not lat or not lon:
            try:
                geo_response = requests.get(
                    f"{API_URL}/search-address",
                    params={'q': address},
                    timeout=5
                )
                if geo_response.ok:
                    geo_data = geo_response.json()
                    if geo_data.get('results'):
                        lat = geo_data['results'][0]['lat']
                        lon = geo_data['results'][0]['lon']
            except Exception as e:
                logger.warning(f"Geocoding failed: {e}")

        # Use combined-estimate for Rosreestr + CIAN valuation
        response = requests.post(
            f"{API_URL}/combined-estimate",
            json={
                'address': address,
                'lat': lat,
                'lon': lon,
                'area_total': area,
                'rooms': rooms,
                'floor': floor,
                'total_floors': total_floors
            },
            timeout=30
        )

        if not response.ok:
            error_detail = response.json().get('detail', 'Unknown error')
            await send_message(
                update, query,
                f"❌ Ошибка оценки:\n{error_detail}"
            )
            return

        result = response.json()

        # Format response - combined-estimate returns different fields
        market_price = result['market_price']
        price_millions = market_price / 1_000_000
        price_per_sqm = result['market_price_per_sqm']
        confidence = result['confidence']
        method_used = result['method_used']

        # Count comparables from both sources
        rosreestr_count = result.get('rosreestr_count', 0)
        cian_count = result.get('cian_count', 0)
        total_comparables = rosreestr_count + cian_count

        # Source info
        rosreestr_psm = result.get('rosreestr_median_psm')
        cian_psm = result.get('cian_median_psm')

        # Interest price from combined engine
        interest_price = result.get('interest_price') or int(market_price * 0.85)
        interest_price_per_sqm = result.get('interest_price_per_sqm') or int(price_per_sqm * 0.85)

        # Generate HTML report
        report_url = None
        try:
            # Get comparables from result
            rosreestr_deals = result.get('rosreestr_deals', [])
            cian_analogs = result.get('cian_analogs', [])

            # Prepare bottom3 from CIAN (already with 7% discount applied in engine)
            bottom3_analogs = cian_analogs[:3] if cian_analogs else []
            bottom3_prices = [c.get('price_per_sqm', 0) for c in bottom3_analogs]
            bottom3_avg = sum(bottom3_prices) / len(bottom3_prices) if bottom3_prices else 0

            # Get min/max from all comparables
            all_prices = []
            for d in rosreestr_deals:
                if d.get('price_per_sqm'):
                    all_prices.append(d['price_per_sqm'])
            for c in cian_analogs:
                if c.get('price_per_sqm'):
                    all_prices.append(c['price_per_sqm'])

            report_response = requests.post(
                f"{API_URL}/reports/generate",
                json={
                    'address': address,
                    'area_total': area,
                    'rooms': rooms,
                    'floor': floor,
                    'total_floors': total_floors,

                    'interest_price': interest_price,
                    'interest_price_per_sqm': interest_price_per_sqm,
                    'market_price_low': int(result['price_range_low']),
                    'market_price_high': int(result['price_range_high']),

                    'avg_price_per_sqm': int(price_per_sqm),
                    'median_price_per_sqm': int(price_per_sqm),
                    'min_price_per_sqm': int(min(all_prices)) if all_prices else 0,
                    'max_price_per_sqm': int(max(all_prices)) if all_prices else 0,

                    'bottom3_avg': int(bottom3_avg),
                    'bottom3_prices': [int(p) for p in bottom3_prices],
                    'bargain_percent': 7,

                    'bottom3_analogs': bottom3_analogs,
                    'rosreestr_deals': rosreestr_deals,
                    'cian_analogs': cian_analogs,

                    'telegram_user_id': update.effective_user.id if update.effective_user else None,
                    'telegram_chat_id': update.effective_chat.id if update.effective_chat else None,
                },
                timeout=30
            )

            if report_response.ok:
                report_data = report_response.json()
                report_url = report_data.get('full_url') or f"http://localhost:8001{report_data.get('report_url')}"
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")

        # Build source info text
        source_info = ""
        if rosreestr_psm:
            source_info += f"  Росреестр: {int(rosreestr_psm):,} ₽/м² ({rosreestr_count} сделок)\n"
        if cian_psm:
            source_info += f"  ЦИАН: {int(cian_psm):,} ₽/м² ({cian_count} объявлений)\n"

        interest_millions = interest_price / 1_000_000

        response_text = f"""
✅ *Оценка готова!*

📍 {address}
📏 {area} м² • {rooms} комн

💰 *Рыночная цена*
{price_millions:.2f} млн ₽ ({int(price_per_sqm):,} ₽/м²)

💎 *Цена интереса*
{interest_millions:.2f} млн ₽ ({int(interest_price_per_sqm):,} ₽/м²)

📊 *Источники данных:*
{source_info}
🎯 *Уверенность:* {confidence}%
📈 *Аналогов:* {total_comparables} (Росреестр: {rosreestr_count}, ЦИАН: {cian_count})

💡 *Методика:*
• Росреестр: реальные сделки (0% торг)
• ЦИАН: цены предложения (-7% торг)
• Взвешенная медиана по источникам
"""

        # Add Rosreestr deals info
        if rosreestr_deals:
            response_text += "\n📋 *Сделки Росреестра:*\n"
            for i, deal in enumerate(rosreestr_deals[:3], 1):
                response_text += (
                    f"{i}. {int(deal.get('price_per_sqm', 0)):,} ₽/м² • "
                    f"{deal.get('area', 0):.0f} м² • "
                    f"{deal.get('distance_km', 0):.1f} км\n"
                )

        # Add CIAN analogs info
        if cian_analogs:
            response_text += "\n📋 *Аналоги ЦИАН:*\n"
            for i, comp in enumerate(cian_analogs[:3], 1):
                response_text += (
                    f"{i}. {int(comp.get('price_per_sqm', 0)):,} ₽/м² • "
                    f"{comp.get('area', 0):.0f} м² • "
                    f"{comp.get('distance_km', 0):.1f} км\n"
                )

        # Add report link
        if report_url:
            response_text += f"\n📄 [Полный отчёт]({report_url})"

        await send_message(update, query, response_text, parse_mode='Markdown')

        # Clear context
        context.user_data.clear()
        
    except requests.Timeout:
        await send_message(
            update, query,
            "⏱️ Превышено время ожидания. Попробуйте еще раз."
        )
    except Exception as e:
        logger.error(f"Valuation error: {e}")
        await send_message(
            update, query,
            f"❌ Ошибка при оценке: {str(e)}"
        )


async def send_message(update: Update, query, text: str, **kwargs):
    """Helper to send message via update or query."""
    if query:
        await query.edit_message_text(text, **kwargs)
    else:
        await update.message.reply_text(text, **kwargs)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle EGRN document upload."""
    document = update.message.document
    
    if not document.file_name.lower().endswith('.pdf'):
        await update.message.reply_text(
            "⚠️ Пожалуйста, отправьте PDF файл выписки ЕГРН"
        )
        return
    
    await update.message.reply_text("📄 Скачиваю файл...")
    
    try:
        # Download file
        file = await document.get_file()
        file_path = f"/tmp/egrn_{update.effective_user.id}.pdf"
        await file.download_to_drive(file_path)
        
        await update.message.reply_text("🔍 Анализирую ЕГРН...")
        
        # Parse EGRN
        from egrn_parser import parse_egrn_pdf, format_egrn_summary
        
        egrn_data = parse_egrn_pdf(file_path)
        
        # Show extracted data
        summary = format_egrn_summary(egrn_data)
        await update.message.reply_text(summary)
        
        # Save to context
        if egrn_data.address:
            context.user_data['address'] = egrn_data.address
        if egrn_data.floor:
            context.user_data['floor'] = egrn_data.floor
        if egrn_data.total_floors:
            context.user_data['total_floors'] = egrn_data.total_floors
        
        # If we have area, proceed to room selection
        if egrn_data.area:
            context.user_data['area'] = egrn_data.area
            
            # Estimate rooms (no building type from EGRN yet)
            estimated_rooms, confidence, explanation = estimate_rooms_by_area(egrn_data.area)
            
            # Create keyboard
            keyboard = [
                [
                    InlineKeyboardButton("Студия", callback_data='rooms_0'),
                    InlineKeyboardButton("1 комн", callback_data='rooms_1'),
                    InlineKeyboardButton("2 комн", callback_data='rooms_2'),
                ],
                [
                    InlineKeyboardButton("3 комн", callback_data='rooms_3'),
                    InlineKeyboardButton("4 комн", callback_data='rooms_4'),
                    InlineKeyboardButton("5+ комн", callback_data='rooms_5'),
                ],
                [
                    InlineKeyboardButton(
                        f"✅ {estimated_rooms} комн (авто)", 
                        callback_data=f'rooms_{estimated_rooms}_auto'
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            confidence_emoji = "🎯" if confidence > 0.8 else "🤖" if confidence > 0.6 else "❓"
            
            await update.message.reply_text(
                f"\n{confidence_emoji} На основе площади ({egrn_data.area} м²), "
                f"предполагаю *{estimated_rooms}-комнатную* квартиру.\n"
                f"_{explanation}_\n\n"
                f"Выберите количество комнат:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            # No area found, ask manually
            await update.message.reply_text(
                "⚠️ Не удалось определить площадь из ЕГРН.\n"
                "Укажите площадь вручную (м²):"
            )
            context.user_data['step'] = 'waiting_for_area'
        
        # Clean up temp file
        import os
        os.remove(file_path)
        
    except Exception as e:
        logger.error(f"EGRN parsing error: {e}")
        await update.message.reply_text(
            f"❌ Ошибка при обработке ЕГРН:\n{str(e)}\n\n"
            f"Пожалуйста, укажите параметры вручную.\n"
            f"Напишите адрес квартиры:"
        )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all callback queries."""
    from admin_commands import (
        is_admin, restart_parsers, stop_parsers, start_parsers,
        get_service_status, start_service, stop_service, restart_service,
        get_service_logs, refresh_cookies, get_parser_status, get_cookies_status
    )

    query = update.callback_query
    data = query.data

    # User callbacks (room/floor selection)
    if data.startswith('rooms_'):
        await handle_room_selection(update, context)
        return
    elif data == 'floor_skip':
        await handle_floor_skip(update, context)
        return
    elif data == 'floor_ask':
        await handle_floor_ask(update, context)
        return
    elif data == 'total_floors_skip':
        await handle_floor_skip(update, context)
        return

    # Admin callbacks - check admin first
    if not is_admin(update.effective_user.id):
        await query.answer("⛔ Только для администраторов", show_alert=True)
        return

    await query.answer()

    # Parser menu (individual parser)
    if data.startswith('parser_'):
        from admin_commands import SERVICE_DESCRIPTIONS

        service = data.replace('parser_', '')
        status = get_service_status(service)

        if status['running']:
            icon = "🟢"
            status_text = f"работает {status['runtime']}" if status['runtime'] else "активен"
        elif status['active']:
            icon = "🟡"
            status_text = "ожидает запуска"
        else:
            icon = "🔴"
            status_text = "выключен"

        next_run = status.get('next_run', 'N/A')
        memory = f"{status['memory_mb']:.0f} MB" if status['memory_mb'] else "—"
        description = SERVICE_DESCRIPTIONS.get(service, '')

        msg = f"""<b>🔄 {PARSER_NAMES.get(service, service)}</b>

<i>{description}</i>

Статус: {icon} <b>{status_text}</b>
Следующий запуск: {next_run}
Память: {memory}
PID: {status.get('pid') or '—'}

Выберите действие:"""

        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_parser_menu(service))

    # Parser actions (start/stop/restart individual)
    elif data.startswith('action_'):
        parts = data.split('_')
        if len(parts) >= 3:
            action = parts[1]  # start, stop, restart
            service = parts[2]

            if action == 'start':
                await query.edit_message_text(f"▶️ Запускаю {PARSER_NAMES.get(service, service)}...")
                result = start_service(service)
            elif action == 'stop':
                await query.edit_message_text(f"⏹ Останавливаю {PARSER_NAMES.get(service, service)}...")
                result = stop_service(service)
            elif action == 'restart':
                await query.edit_message_text(f"🔄 Перезапускаю {PARSER_NAMES.get(service, service)}...")
                result = restart_service(service)
            else:
                result = "❌ Неизвестное действие"

            # Show result with back button
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data=f'parser_{service}')]
            ])
            await query.edit_message_text(f"<b>Результат:</b>\n{result}", parse_mode='HTML', reply_markup=keyboard)

    # Logs menu
    elif data == 'logs_menu':
        await query.edit_message_text(
            "<b>📋 ЛОГИ ПАРСЕРОВ</b>\n\nВыберите парсер:",
            parse_mode='HTML',
            reply_markup=LOGS_MENU
        )

    # Show logs
    elif data.startswith('logs_'):
        parts = data.split('_')
        if len(parts) >= 3:
            service = parts[1]
            lines = int(parts[2]) if parts[2].isdigit() else 50

            await query.edit_message_text(f"📋 Загружаю логи {PARSER_NAMES.get(service, service)}...")

            logs = get_service_logs(service, lines)

            # Buttons for more logs and back
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 Обновить", callback_data=f'logs_{service}_{lines}'),
                    InlineKeyboardButton("📋 100 строк", callback_data=f'logs_{service}_100'),
                ],
                [InlineKeyboardButton("⬅️ Назад", callback_data='logs_menu')],
            ])

            msg = f"<b>📋 {PARSER_NAMES.get(service, service)}</b> (последние {lines})\n\n<code>{logs}</code>"

            # Truncate if too long
            if len(msg) > 4000:
                msg = msg[:4000] + "...</code>"

            await query.edit_message_text(msg, parse_mode='HTML', reply_markup=keyboard)

    # Refresh cookies
    elif data == 'refresh_cookies':
        await query.edit_message_text(
            "🍪 <b>Обновляю cookies через прокси...</b>\n\n"
            "⏳ Это займёт 30-60 секунд.\n"
            "Пожалуйста, подождите.",
            parse_mode='HTML'
        )

        success, message = refresh_cookies()

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ К управлению", callback_data='mgmt_menu')]
        ])

        await query.edit_message_text(message, parse_mode='HTML', reply_markup=keyboard)

    # Refresh proxy status (from proxy_command)
    elif data == 'refresh_proxy_status':
        await query.answer("🔄 Обновляю статус...")
        # Just trigger the proxy command again
        from admin_commands import check_proxy_connections, get_nodemaven_traffic, get_cookies_status as get_cookies
        proxy = check_proxy_connections()
        traffic = get_nodemaven_traffic()
        cookies = get_cookies()

        # Rebuild the message (same as proxy_command)
        status_icon = '⚠️' if proxy['proxy_used'] else '✅'
        status_text = 'ПРОКСИ ИСПОЛЬЗУЕТСЯ!' if proxy['proxy_used'] else 'не используется'

        msg = f"""<b>🔒 МОНИТОРИНГ ПРОКСИ</b>
{'━' * 28}

<b>🔌 СОЕДИНЕНИЯ:</b>
• Через прокси: {proxy['proxy_connections']} {status_icon}
• К CIAN напрямую: {proxy['cian_connections']}
• Статус: <b>{status_text}</b>

"""
        if not traffic.get('error'):
            used = traffic.get('used_gb', 0)
            limit = traffic.get('limit_gb', 10)
            percent = (used / limit * 100) if limit > 0 else 0
            bar = '█' * int(percent / 10) + '░' * (10 - int(percent / 10))
            msg += f"""<b>📊 ТРАФИК NodeMaven:</b>
{bar} {percent:.1f}%
• Использовано: <b>{used:.2f} GB</b> из {limit:.0f} GB
• Осталось: <b>{traffic.get('remaining_gb', 0):.2f} GB</b>
"""
        else:
            msg += f"<b>📊 ТРАФИК:</b> ⚠️ {traffic.get('error')}\n"

        msg += "\n<b>🍪 COOKIES:</b>\n"
        if cookies['exists']:
            age = cookies['age_hours']
            icon = "✅" if age < 12 else ("🟡" if age < 20 else "🔴")
            msg += f"• {icon} Возраст: {age:.1f}ч\n"
        else:
            msg += "• ❌ Не найдены!\n"

        msg += "\n<i>⚠️ Правило: прокси ТОЛЬКО для cookies!</i>"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🍪 Обновить cookies", callback_data='refresh_cookies'),
                InlineKeyboardButton("🔄 Обновить", callback_data='refresh_proxy_status'),
            ]
        ])

        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=keyboard)

    # Services help/descriptions
    elif data == 'services_help':
        from admin_commands import format_services_help
        msg = format_services_help()
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад", callback_data='mgmt_menu')]
        ])
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=keyboard)

    # Management menu (back to main)
    elif data == 'mgmt_menu':
        parsers = get_parser_status()
        cookies = get_cookies_status()

        parser_lines = []
        for name in ['scraper', 'fastscan', 'enrich', 'alerts', 'geocoding']:
            status = get_service_status(name)
            if status['running']:
                icon = "🟢"
                info = f"работает {status['runtime']}" if status['runtime'] else "активен"
            elif status['active']:
                icon = "🟡"
                info = "ожидает"
            else:
                icon = "🔴"
                info = "выключен"
            parser_lines.append(f"  {icon} {PARSER_NAMES[name]}: {info}")

        if cookies['exists']:
            age = cookies['age_hours']
            cookies_icon = "✅" if age < 12 else ("🟡" if age < 20 else "🔴")
            cookies_line = f"{cookies_icon} {age:.1f}ч"
        else:
            cookies_line = "❌ Нет"

        msg = f"""<b>⚙️ УПРАВЛЕНИЕ СЕРВИСАМИ</b>

<b>Статус:</b>
{chr(10).join(parser_lines)}

<b>Cookies:</b> {cookies_line}
<b>Процессов:</b> {parsers['total_count']} ({parsers['memory_mb']:.0f} MB)

Выберите сервис для управления:"""

        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=MANAGEMENT_MAIN)

    # All parsers management
    elif data == 'mgmt_restart':
        await query.edit_message_text("🔄 Перезапускаю все парсеры...")
        result = restart_parsers()
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data='mgmt_menu')]])
        await query.edit_message_text(f"<b>Результат:</b>\n{result}", parse_mode='HTML', reply_markup=keyboard)

    elif data == 'mgmt_stop':
        await query.edit_message_text("⏹ Останавливаю все парсеры...")
        result = stop_parsers()
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data='mgmt_menu')]])
        await query.edit_message_text(f"<b>Результат:</b>\n{result}", parse_mode='HTML', reply_markup=keyboard)

    elif data == 'mgmt_start':
        await query.edit_message_text("▶️ Запускаю все парсеры...")
        result = start_parsers()
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data='mgmt_menu')]])
        await query.edit_message_text(f"<b>Результат:</b>\n{result}", parse_mode='HTML', reply_markup=keyboard)

    elif data == 'mgmt_close':
        await query.delete_message()

    else:
        await query.answer("Unknown action")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route messages based on current step or button press."""
    from admin_commands import is_admin

    text = update.message.text.strip()
    user_id = update.effective_user.id

    # Handle admin button presses
    if is_admin(user_id):
        if text == "📊 Статус":
            await status_command(update, context)
            return
        elif text == "📦 База":
            await db_command(update, context)
            return
        elif text == "🤖 Парсеры":
            await parsers_command(update, context)
            return
        elif text == "🔒 Прокси":
            await proxy_command(update, context)
            return
        elif text == "⚙️ Управление":
            await show_management_menu(update, context)
            return

    # Handle user button presses
    if text == "🏠 Оценить квартиру":
        await update.message.reply_text(
            "Напишите адрес квартиры, например:\n"
            "`Новоясеневский проспект 32`",
            parse_mode='Markdown'
        )
        return
    elif text == "📖 Помощь":
        await help_command(update, context)
        return

    # Normal message flow
    step = context.user_data.get('step')

    if step == 'waiting_for_area':
        await handle_area_input(update, context)
    elif step == 'waiting_for_floor':
        await handle_floor_input(update, context)
    elif step == 'waiting_for_total_floors':
        try:
            total_floors = int(text)
            context.user_data['total_floors'] = total_floors
            await update.message.reply_text("⏳ Оцениваю квартиру...")
            await perform_valuation(update, context)
        except ValueError:
            await update.message.reply_text("⚠️ Укажите число или пропустите")
    else:
        await handle_address(update, context)


# ============= ADMIN COMMANDS =============

# Admin chat ID for notifications
ADMIN_CHAT_ID = 1435579369  # @bruckbond

# Маппинг имён парсеров
PARSER_NAMES = {
    'scraper': 'Scraper',
    'fastscan': 'FastScan',
    'enrich': 'Enrich',
    'alerts': 'Alerts',
    'geocoding': 'Geocoding',
}

# Главное меню управления
MANAGEMENT_MAIN = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🔍 Scraper", callback_data='parser_scraper'),
        InlineKeyboardButton("⚡ FastScan", callback_data='parser_fastscan'),
        InlineKeyboardButton("📝 Enrich", callback_data='parser_enrich'),
    ],
    [
        InlineKeyboardButton("🔔 Alerts", callback_data='parser_alerts'),
        InlineKeyboardButton("📍 Geocoding", callback_data='parser_geocoding'),
    ],
    [
        InlineKeyboardButton("⏹ Стоп все", callback_data='mgmt_stop'),
        InlineKeyboardButton("▶️ Старт все", callback_data='mgmt_start'),
    ],
    [
        InlineKeyboardButton("🍪 Cookies", callback_data='refresh_cookies'),
        InlineKeyboardButton("📋 Логи", callback_data='logs_menu'),
    ],
    [
        InlineKeyboardButton("❓ Описания", callback_data='services_help'),
        InlineKeyboardButton("❌ Закрыть", callback_data='mgmt_close'),
    ],
])

# Меню логов
LOGS_MENU = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🔍 Scraper", callback_data='logs_scraper_50'),
        InlineKeyboardButton("⚡ FastScan", callback_data='logs_fastscan_50'),
    ],
    [
        InlineKeyboardButton("📝 Enrich", callback_data='logs_enrich_50'),
        InlineKeyboardButton("🔔 Alerts", callback_data='logs_alerts_50'),
    ],
    [
        InlineKeyboardButton("📍 Geocoding", callback_data='logs_geocoding_50'),
        InlineKeyboardButton("💓 Health", callback_data='logs_health_50'),
    ],
    [InlineKeyboardButton("⬅️ Назад", callback_data='mgmt_menu')],
])


def get_parser_menu(service: str) -> InlineKeyboardMarkup:
    """Генерация inline клавиатуры для управления парсером."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ Запустить", callback_data=f'action_start_{service}'),
            InlineKeyboardButton("⏹ Стоп", callback_data=f'action_stop_{service}'),
        ],
        [
            InlineKeyboardButton("🔄 Рестарт", callback_data=f'action_restart_{service}'),
            InlineKeyboardButton("📋 Логи", callback_data=f'logs_{service}_50'),
        ],
        [InlineKeyboardButton("⬅️ Назад", callback_data='mgmt_menu')],
    ])


async def show_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show management menu with inline keyboard."""
    from admin_commands import is_admin, get_parser_status, get_service_status, get_cookies_status

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только для администраторов")
        return

    parsers = get_parser_status()
    cookies = get_cookies_status()

    # Статус ВСЕХ сервисов
    parser_lines = []
    for name in ['scraper', 'fastscan', 'enrich', 'alerts', 'geocoding']:
        status = get_service_status(name)
        if status['running']:
            icon = "🟢"
            info = f"работает {status['runtime']}" if status['runtime'] else "активен"
        elif status['active']:
            icon = "🟡"
            info = "ожидает"
        else:
            icon = "🔴"
            info = "выключен"
        parser_lines.append(f"  {icon} {PARSER_NAMES[name]}: {info}")

    # Cookies status
    if cookies['exists']:
        age = cookies['age_hours']
        cookies_icon = "✅" if age < 12 else ("🟡" if age < 20 else "🔴")
        cookies_line = f"{cookies_icon} {age:.1f}ч"
    else:
        cookies_line = "❌ Нет"

    msg = f"""<b>⚙️ УПРАВЛЕНИЕ СЕРВИСАМИ</b>

<b>Статус:</b>
{chr(10).join(parser_lines)}

<b>Cookies:</b> {cookies_line}
<b>Процессов:</b> {parsers['total_count']} ({parsers['memory_mb']:.0f} MB)

Выберите сервис для управления:"""

    await update.message.reply_text(
        msg,
        parse_mode='HTML',
        reply_markup=MANAGEMENT_MAIN
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show full system status (admin only)."""
    from admin_commands import is_admin, format_compact_status

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только для администраторов")
        return

    try:
        msg = format_compact_status()
        await update.message.reply_text(msg, parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def parsers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show parser status (admin only)."""
    from admin_commands import is_admin, get_parser_status, get_timer_status

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только для администраторов")
        return

    parsers = get_parser_status()
    timers = get_timer_status()

    msg = f"<b>🤖 Парсеры ({parsers['total_count']} активных)</b>\n\n"

    for p in parsers['running']:
        msg += f"• PID {p['pid']}: {p['runtime']} ({p['memory_mb']:.0f}MB)\n"

    if not parsers['running']:
        msg += "Нет активных парсеров\n"

    msg += f"\n<b>⏱ Таймеры:</b>\n"
    for name, t in timers.items():
        status = "✅" if t.get('active') else "❌"
        msg += f"• {status} {name}\n"

    await update.message.reply_text(msg, parse_mode='HTML')


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Restart all parsers (admin only)."""
    from admin_commands import is_admin, restart_parsers

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только для администраторов")
        return

    await update.message.reply_text("🔄 Перезапускаю парсеры...")

    try:
        result = restart_parsers()
        await update.message.reply_text(f"<b>Результат:</b>\n{result}", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop all parsers (admin only)."""
    from admin_commands import is_admin, stop_parsers

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только для администраторов")
        return

    await update.message.reply_text("⏹ Останавливаю парсеры...")

    try:
        result = stop_parsers()
        await update.message.reply_text(f"<b>Результат:</b>\n{result}", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def start_parsers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start all parsers (admin only)."""
    from admin_commands import is_admin, start_parsers

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только для администраторов")
        return

    await update.message.reply_text("▶️ Запускаю парсеры...")

    try:
        result = start_parsers()
        await update.message.reply_text(f"<b>Результат:</b>\n{result}", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def db_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show database stats (admin only)."""
    from admin_commands import is_admin, get_db_stats

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только для администраторов")
        return

    db = get_db_stats()

    msg = f"""<b>📦 База данных</b>

• Активных: <b>{db['total_active']:,}</b>
• С описанием: {db['with_description']:,}
• С обременениями: {db['with_encumbrances']}
• Добавлено сегодня: +{db['added_today']}
• За последний час: +{db['added_last_hour']}
• Фото: {db['photos']:,}

<b>По комнатам:</b>
"""
    for rooms, count in sorted(db['by_rooms'].items()):
        room_name = 'Студия' if rooms == 0 else f'{rooms}-комн'
        msg += f"• {room_name}: {count:,}\n"

    await update.message.reply_text(msg, parse_mode='HTML')


async def proxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show proxy status (admin only)."""
    from admin_commands import is_admin, check_proxy_connections, get_nodemaven_traffic, get_cookies_status

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только для администраторов")
        return

    proxy = check_proxy_connections()
    traffic = get_nodemaven_traffic()
    cookies = get_cookies_status()

    status_icon = '⚠️' if proxy['proxy_used'] else '✅'
    status_text = 'ПРОКСИ ИСПОЛЬЗУЕТСЯ!' if proxy['proxy_used'] else 'не используется'

    msg = f"""<b>🔒 МОНИТОРИНГ ПРОКСИ</b>
{'━' * 28}

<b>🔌 СОЕДИНЕНИЯ:</b>
• Через прокси: {proxy['proxy_connections']} {status_icon}
• К CIAN напрямую: {proxy['cian_connections']}
• Статус: <b>{status_text}</b>

"""
    # Add traffic info
    if traffic.get('error'):
        msg += f"""<b>📊 ТРАФИК NodeMaven:</b>
⚠️ {traffic['error']}
"""
        if not traffic.get('configured'):
            msg += "<i>Добавьте NODEMAVEN_API_KEY в .env</i>\n"
    else:
        used = traffic.get('used_gb', 0)
        limit = traffic.get('limit_gb', 10)
        remaining = traffic.get('remaining_gb', 0)
        percent_used = (used / limit * 100) if limit > 0 else 0

        # Traffic bar
        bar_filled = int(percent_used / 10)
        bar_empty = 10 - bar_filled
        bar = '█' * bar_filled + '░' * bar_empty

        msg += f"""<b>📊 ТРАФИК NodeMaven:</b>
{bar} {percent_used:.1f}%
• Использовано: <b>{used:.2f} GB</b> из {limit:.0f} GB
• Осталось: <b>{remaining:.2f} GB</b>
• Запросов: {traffic.get('requests', 0):,}
"""
        if traffic.get('period_end'):
            msg += f"• Период до: {traffic['period_end']}\n"

    # Cookies status
    msg += "\n<b>🍪 COOKIES:</b>\n"
    if cookies['exists']:
        age = cookies['age_hours']
        if age < 12:
            cookies_icon = "✅"
            cookies_status = "актуальны"
        elif age < 20:
            cookies_icon = "🟡"
            cookies_status = "скоро истекут"
        else:
            cookies_icon = "🔴"
            cookies_status = "УСТАРЕЛИ!"
        msg += f"• Статус: {cookies_icon} {cookies_status}\n"
        msg += f"• Возраст: {age:.1f} часов\n"
        msg += f"• Размер: {cookies['size_kb']:.1f} KB\n"
    else:
        msg += "• ❌ Файл не найден!\n"

    msg += "\n<i>⚠️ Правило: прокси ТОЛЬКО для cookies!</i>"

    # Keyboard with refresh button
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍪 Обновить cookies", callback_data='refresh_cookies'),
            InlineKeyboardButton("🔄 Обновить", callback_data='refresh_proxy_status'),
        ]
    ])

    await update.message.reply_text(msg, parse_mode='HTML', reply_markup=keyboard)


async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin commands help."""
    from admin_commands import is_admin

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только для администраторов")
        return

    msg = """<b>🔧 Админ-команды</b>

<b>Мониторинг:</b>
/status - Полный статус системы
/db - Статистика базы данных
/parsers - Статус парсеров
/proxy - Статус прокси

<b>Управление:</b>
/restart - Перезапустить парсеры
/stop - Остановить парсеры
/startparsers - Запустить парсеры

<b>Информация:</b>
/admin - Эта справка
"""
    await update.message.reply_text(msg, parse_mode='HTML')


# ============= АВТОМАТИЧЕСКИЕ УВЕДОМЛЕНИЯ =============

async def send_hourly_status(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправить краткий статус админу каждый час."""
    from admin_commands import get_db_stats, get_parser_status
    from datetime import datetime, timedelta

    try:
        db = get_db_stats()
        parsers = get_parser_status()

        now_msk = datetime.utcnow() + timedelta(hours=3)

        msg = f"""⏰ <b>Статус {now_msk.strftime('%H:%M')} МСК</b>
📦 {db['total_active']:,} объявлений (+{db['added_last_hour']} за час)
🤖 Парсеров: {parsers['total_count']} активных
🏠 Обременений: {db['with_encumbrances']}"""

        await context.bot.send_message(ADMIN_CHAT_ID, msg, parse_mode='HTML')
        logger.info(f"Hourly status sent to admin")
    except Exception as e:
        logger.error(f"Failed to send hourly status: {e}")


async def check_and_alert(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверять проблемы каждые 5 минут и выполнять автоматические действия."""
    from admin_commands import (
        get_parser_status, get_cookies_age_hours, get_nodemaven_traffic,
        check_proxy_connections, auto_fix_stuck_process, kill_proxy_using_processes,
        parse_runtime_hours, refresh_cookies, stop_parsers, start_parsers
    )

    try:
        issues = []          # Предупреждения (не требуют действий)
        actions_taken = []   # Выполненные автоматические действия

        # ============ 1. ПРОВЕРКА ПРОЦЕССОВ ============
        parsers = get_parser_status()

        for p in parsers.get('running', []):
            runtime = p.get('runtime', '')
            pid = p.get('pid')
            cmd = p.get('cmd', '')

            if runtime:
                hours = parse_runtime_hours(runtime)

                # Уровень КРИТИЧЕСКИЙ: процесс работает > 1 дня
                if 'day' in runtime:
                    result = auto_fix_stuck_process(pid, cmd)
                    actions_taken.append(f"🔴 ЗАВИСШИЙ ({runtime}):\n{result}")

                # Уровень ВЫСОКИЙ: процесс работает > 4 часов - убить
                elif hours >= 4:
                    result = auto_fix_stuck_process(pid, cmd)
                    actions_taken.append(f"🟠 ДОЛГИЙ ({hours:.0f}ч):\n{result}")

                # Уровень СРЕДНИЙ: процесс работает 3-4 часа - предупреждение
                elif hours >= 3:
                    issues.append(f"⚠️ Долгий процесс: PID {pid} ({hours:.0f}ч)")

        # ============ 2. ПРОВЕРКА COOKIES ============
        cookies_age = get_cookies_age_hours()

        if cookies_age is not None:
            # Уровень КРИТИЧЕСКИЙ: cookies > 24 часов
            if cookies_age > 24:
                actions_taken.append("🔴 Cookies ИСТЕКЛИ! Останавливаю парсеры...")
                stop_parsers()
                success, msg = refresh_cookies()
                if success:
                    start_parsers()
                    actions_taken.append(f"✅ Cookies обновлены, парсеры запущены")
                else:
                    actions_taken.append(f"❌ Ошибка обновления cookies: {msg}")

            # Уровень СРЕДНИЙ: cookies 22-24 часа - предупреждение
            elif cookies_age > 22:
                issues.append(f"🍪 Cookies устаревают ({cookies_age:.0f}ч)")

        # ============ 3. ПРОВЕРКА ТРАФИКА ============
        traffic = get_nodemaven_traffic()

        if not traffic.get('error'):
            remaining = traffic.get('remaining_gb', 100)

            # Уровень КРИТИЧЕСКИЙ: < 0.1 GB
            if remaining < 0.1:
                stop_parsers()
                actions_taken.append(f"🛑 Парсеры ОСТАНОВЛЕНЫ - трафик {remaining:.2f} GB")

            # Уровень ВЫСОКИЙ: < 0.5 GB
            elif remaining < 0.5:
                issues.append(f"📊 Критически мало трафика: {remaining:.2f} GB")

        # ============ 4. ПРОВЕРКА ПРОКСИ ============
        proxy = check_proxy_connections()

        if proxy.get('proxy_used') and proxy.get('proxy_connections', 0) > 2:
            # Автоматически убить процессы использующие прокси
            killed, report = kill_proxy_using_processes()
            if killed > 0:
                actions_taken.append(f"🔌 Убито {killed} процессов через прокси:\n{report}")
            else:
                issues.append(f"⚠️ {proxy['proxy_connections']} соединений через прокси (бот/cookies)")

        # ============ ОТПРАВКА ОТЧЁТА ============
        if actions_taken or issues:
            msg_parts = []

            if actions_taken:
                msg_parts.append("🤖 <b>АВТОДЕЙСТВИЯ:</b>\n" + "\n".join(actions_taken))

            if issues:
                msg_parts.append("⚠️ <b>ПРЕДУПРЕЖДЕНИЯ:</b>\n" + "\n".join(issues))

            msg = "🚨 <b>АЛЕРТ</b>\n\n" + "\n\n".join(msg_parts)
            await context.bot.send_message(ADMIN_CHAT_ID, msg, parse_mode='HTML')
            logger.warning(f"Alert sent: actions={len(actions_taken)}, issues={len(issues)}")

    except Exception as e:
        logger.error(f"Failed to check and alert: {e}")


def main() -> None:
    """Start the bot."""

    if not TELEGRAM_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN not set!")
        print("Set it via: export TELEGRAM_BOT_TOKEN='your-token-here'")
        return

    # Create application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("myid", myid_command))

    # Admin commands
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("db", db_command))
    application.add_handler(CommandHandler("parsers", parsers_command))
    application.add_handler(CommandHandler("proxy", proxy_command))
    application.add_handler(CommandHandler("restart", restart_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("startparsers", start_parsers_command))
    application.add_handler(CommandHandler("admin", admin_help_command))

    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Автоматические уведомления через job_queue
    job_queue = application.job_queue
    if job_queue:
        # Статус каждый час (первый через 60 сек после старта)
        job_queue.run_repeating(send_hourly_status, interval=3600, first=60, name='hourly_status')

        # Проверка проблем каждые 5 минут (первая через 30 сек)
        job_queue.run_repeating(check_and_alert, interval=300, first=30, name='alert_check')

        logger.info("📅 Job queue configured: hourly status + alert checks")
    else:
        logger.warning("⚠️ Job queue not available!")

    # Start bot
    logger.info("🤖 Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

