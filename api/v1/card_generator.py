"""
Telegram Card Generator
Генерация красивых карточек-изображений для отправки в Telegram.
"""

from PIL import Image, ImageDraw, ImageFont
import io
from typing import Optional
from datetime import datetime


class CardGenerator:
    """Генератор карточек оценки недвижимости."""

    def __init__(self):
        # Цвета (темная тема как на сайте)
        self.bg_color = (17, 24, 39)  # #111827
        self.card_bg = (31, 41, 55)   # #1f2937
        self.green = (34, 197, 94)    # #22c55e
        self.orange = (245, 158, 11)  # #f59e0b
        self.red = (239, 68, 68)      # #ef4444
        self.purple = (139, 92, 246)  # #8b5cf6
        self.blue = (59, 130, 246)    # #3b82f6
        self.white = (255, 255, 255)
        self.gray = (156, 163, 175)   # #9ca3af
        self.light_gray = (229, 231, 235)  # #e5e7eb

        # Шрифты
        try:
            self.font_bold = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 32)
            self.font_regular = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 24)
            self.font_small = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 18)
            self.font_large = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 48)
            self.font_title = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 28)
        except:
            # Fallback to default
            self.font_bold = ImageFont.load_default()
            self.font_regular = ImageFont.load_default()
            self.font_small = ImageFont.load_default()
            self.font_large = ImageFont.load_default()
            self.font_title = ImageFont.load_default()

    def format_price(self, price: float) -> str:
        """Форматирование цены."""
        if price >= 1_000_000:
            return f"{price/1_000_000:.2f} млн ₽"
        return f"{price:,.0f} ₽".replace(",", " ")

    def format_price_short(self, price: float) -> str:
        """Короткое форматирование цены."""
        if price >= 1_000_000:
            return f"{price/1_000_000:.1f}М"
        return f"{price/1000:.0f}К"

    def draw_rounded_rect(self, draw, xy, radius, fill):
        """Рисование прямоугольника с закругленными углами."""
        x1, y1, x2, y2 = xy
        draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
        draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
        draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill)
        draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill)
        draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill)
        draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill)

    def generate_card(
        self,
        address: str,
        area_total: float,
        rooms: Optional[int],
        floor: Optional[int],
        total_floors: Optional[int],
        building_type: Optional[str],
        sale_price: float,
        sale_price_psm: float,
        interest_price: float,
        discount_percent: float,
        our_profit: float,
        confidence: int,
        source: str = "ЦИАН"
    ) -> bytes:
        """Генерация карточки оценки."""

        # Размер карточки
        width, height = 800, 600
        img = Image.new('RGB', (width, height), self.bg_color)
        draw = ImageDraw.Draw(img)

        # Заголовок
        draw.text((30, 20), "📊 OurDocs Оценка", font=self.font_title, fill=self.orange)
        draw.text((30, 55), "rating.ourdocs.org", font=self.font_small, fill=self.gray)

        # Дата
        date_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        draw.text((width - 180, 25), date_str, font=self.font_small, fill=self.gray)

        # Линия разделитель
        draw.line([(30, 90), (width - 30, 90)], fill=self.gray, width=1)

        # Адрес
        # Обрезаем адрес если слишком длинный
        short_address = address if len(address) < 50 else address[:47] + "..."
        draw.text((30, 105), "📍 " + short_address, font=self.font_regular, fill=self.light_gray)

        # Параметры объекта
        params = []
        if area_total:
            params.append(f"{area_total} м²")
        if rooms:
            params.append(f"{rooms} комн.")
        if floor and total_floors:
            params.append(f"{floor}/{total_floors} эт.")

        type_names = {
            'panel': 'Панель', 'brick': 'Кирпич', 'monolithic': 'Монолит',
            'block': 'Блочный', 'wood': 'Дерево', 'other': 'Другое'
        }
        if building_type:
            params.append(type_names.get(building_type, building_type))

        params_str = " • ".join(params)
        draw.text((30, 140), params_str, font=self.font_small, fill=self.gray)

        # Карточки с ценами
        card_y = 180
        card_height = 120
        card_width = 235
        gap = 20

        # Карточка 1: Цена продажи
        self.draw_rounded_rect(draw, (30, card_y, 30 + card_width, card_y + card_height), 12, self.card_bg)
        draw.text((45, card_y + 15), "💰 Цена продажи", font=self.font_small, fill=self.gray)
        draw.text((45, card_y + 45), self.format_price(sale_price), font=self.font_bold, fill=self.green)
        draw.text((45, card_y + 85), f"{sale_price_psm:,.0f} ₽/м²".replace(",", " "), font=self.font_small, fill=self.gray)

        # Карточка 2: Цена интереса
        x2 = 30 + card_width + gap
        self.draw_rounded_rect(draw, (x2, card_y, x2 + card_width, card_y + card_height), 12, self.card_bg)
        draw.text((x2 + 15, card_y + 15), "💎 Цена интереса", font=self.font_small, fill=self.gray)
        draw.text((x2 + 15, card_y + 45), self.format_price(interest_price), font=self.font_bold, fill=self.orange)
        draw.text((x2 + 15, card_y + 85), f"↓{discount_percent:.1f}% от рынка", font=self.font_small, fill=self.red)

        # Карточка 3: Наша прибыль
        x3 = x2 + card_width + gap
        self.draw_rounded_rect(draw, (x3, card_y, x3 + card_width, card_y + card_height), 12, self.card_bg)
        draw.text((x3 + 15, card_y + 15), "💵 Наша прибыль", font=self.font_small, fill=self.gray)
        draw.text((x3 + 15, card_y + 45), self.format_price(our_profit), font=self.font_bold, fill=self.purple)
        draw.text((x3 + 15, card_y + 85), f"при покупке по цене интереса", font=self.font_small, fill=self.gray)

        # Нижняя секция: Уверенность и Источник
        bottom_y = card_y + card_height + 30

        # Уверенность
        self.draw_rounded_rect(draw, (30, bottom_y, 30 + 180, bottom_y + 80), 12, self.card_bg)
        draw.text((45, bottom_y + 15), "🎯 Уверенность", font=self.font_small, fill=self.gray)
        confidence_color = self.green if confidence >= 70 else self.orange if confidence >= 50 else self.red
        draw.text((45, bottom_y + 40), f"{confidence}%", font=self.font_bold, fill=confidence_color)

        # Источник цен
        self.draw_rounded_rect(draw, (230, bottom_y, 230 + 220, bottom_y + 80), 12, self.card_bg)
        draw.text((245, bottom_y + 15), "📊 Источник цен", font=self.font_small, fill=self.gray)
        draw.text((245, bottom_y + 40), source, font=self.font_bold, fill=self.blue)

        # Скидка большая
        self.draw_rounded_rect(draw, (470, bottom_y, width - 30, bottom_y + 80), 12, self.card_bg)
        draw.text((485, bottom_y + 15), "📉 Скидка", font=self.font_small, fill=self.gray)
        draw.text((485, bottom_y + 40), f"{discount_percent:.1f}%", font=self.font_bold, fill=self.red)

        # Футер
        footer_y = height - 60
        draw.line([(30, footer_y), (width - 30, footer_y)], fill=(55, 65, 81), width=1)
        draw.text((30, footer_y + 15), "Автоматическая оценка на основе рыночных данных", font=self.font_small, fill=self.gray)
        draw.text((width - 200, footer_y + 15), "🤖 AI-Powered", font=self.font_small, fill=self.purple)

        # Сохраняем в bytes
        buffer = io.BytesIO()
        img.save(buffer, format='PNG', quality=95)
        buffer.seek(0)
        return buffer.getvalue()


def generate_telegram_card(valuation_data: dict) -> bytes:
    """Удобная функция для генерации карточки из данных оценки."""
    generator = CardGenerator()

    # Извлекаем данные
    sale_price = valuation_data.get('bottom3_price') or valuation_data.get('estimated_price', 0)
    sale_price_psm = valuation_data.get('bottom3_price_per_sqm') or valuation_data.get('estimated_price_per_sqm', 0)
    interest_price = valuation_data.get('interest_price', sale_price * 0.85)
    discount_percent = valuation_data.get('discount_percent', 15.0)
    our_profit = valuation_data.get('our_profit') or valuation_data.get('expected_profit') or (sale_price - interest_price) * 0.5

    return generator.generate_card(
        address=valuation_data.get('address', 'Адрес не указан'),
        area_total=valuation_data.get('area_total', 0),
        rooms=valuation_data.get('rooms'),
        floor=valuation_data.get('floor'),
        total_floors=valuation_data.get('total_floors'),
        building_type=valuation_data.get('building_type_detected'),
        sale_price=sale_price,
        sale_price_psm=sale_price_psm,
        interest_price=interest_price,
        discount_percent=discount_percent,
        our_profit=our_profit,
        confidence=valuation_data.get('confidence', 75),
        source=valuation_data.get('price_source', 'ЦИАН')
    )


def generate_telegram_message(valuation_data: dict) -> str:
    """Генерация текстового сообщения для Telegram."""

    address = valuation_data.get('address', 'Адрес не указан')
    area = valuation_data.get('area_total', 0)
    rooms = valuation_data.get('rooms')

    sale_price = valuation_data.get('bottom3_price') or valuation_data.get('estimated_price', 0)
    sale_psm = valuation_data.get('bottom3_price_per_sqm') or valuation_data.get('estimated_price_per_sqm', 0)
    interest_price = valuation_data.get('interest_price', sale_price * 0.85)
    discount = ((sale_price - interest_price) / sale_price * 100) if sale_price > 0 else 0
    profit = valuation_data.get('our_profit') or valuation_data.get('expected_profit') or (sale_price - interest_price) * 0.5
    confidence = valuation_data.get('confidence', 75)

    def fmt(price):
        if price >= 1_000_000:
            return f"{price/1_000_000:.2f} млн ₽"
        return f"{price:,.0f} ₽".replace(",", " ")

    msg = f"""📊 <b>Оценка недвижимости</b>

📍 <b>{address}</b>
🏠 {area} м² {f'• {rooms} комн.' if rooms else ''}

━━━━━━━━━━━━━━━━━━

💰 <b>Цена продажи:</b> {fmt(sale_price)}
   <i>({sale_psm:,.0f} ₽/м²)</i>

💎 <b>Цена интереса:</b> {fmt(interest_price)}
   <i>↓{discount:.1f}% от рынка</i>

💵 <b>Прибыль:</b> ~{fmt(profit)}

🎯 Уверенность: {confidence}%

━━━━━━━━━━━━━━━━━━
🌐 rating.ourdocs.org
"""
    return msg
