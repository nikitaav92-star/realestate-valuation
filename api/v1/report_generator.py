"""
Report Generator Module
Генерация брендированных отчетов об оценке для отправки партнерам.
"""

from typing import Optional, List, Dict
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
import io
import os


# Регистрация шрифта с поддержкой Cyrillic (русский текст)
try:
    pdfmetrics.registerFont(TTFont('FreeSans', '/usr/share/fonts/truetype/freefont/FreeSans.ttf'))
    pdfmetrics.registerFont(TTFont('FreeSansBold', '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf'))
    CYRILLIC_FONT = 'FreeSans'
    CYRILLIC_FONT_BOLD = 'FreeSansBold'
except Exception as e:
    print(f"⚠️  Не удалось загрузить FreeSans шрифт: {e}. PDF будет без поддержки Cyrillic.")
    CYRILLIC_FONT = 'Helvetica'
    CYRILLIC_FONT_BOLD = 'Helvetica-Bold'


class ReportGenerator:
    """Генератор PDF отчетов об оценке недвижимости."""
    
    def __init__(self):
        self.company_name = "OurDocs Оценка"
        self.company_slogan = "Профессиональная оценка недвижимости"
        self.website = "rating.ourdocs.org"
        self.brand_color = colors.HexColor("#f59e0b")  # Orange
        self.secondary_color = colors.HexColor("#3b82f6")  # Blue
        
    def generate_valuation_report(
        self,
        address: str,
        area_total: float,
        rooms: Optional[int],
        floor: Optional[int],
        total_floors: Optional[int],
        building_type: Optional[str],
        market_price: float,
        market_price_per_sqm: float,
        interest_price: Optional[float],
        interest_price_per_sqm: Optional[float],
        comparables: List[Dict],
        confidence: int,
        created_at: Optional[datetime] = None
    ) -> bytes:
        """
        Генерация PDF отчета об оценке.
        
        Returns:
            bytes: PDF контент
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm
        )
        
        story = []
        styles = getSampleStyleSheet()

        # Применить Cyrillic шрифт ко всем стилям
        for style_name in styles.byName:
            styles[style_name].fontName = CYRILLIC_FONT
        styles['Title'].fontName = CYRILLIC_FONT_BOLD
        styles['Heading1'].fontName = CYRILLIC_FONT_BOLD
        styles['Heading2'].fontName = CYRILLIC_FONT_BOLD
        styles['Heading3'].fontName = CYRILLIC_FONT_BOLD

        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontName=CYRILLIC_FONT_BOLD,
            fontSize=24,
            textColor=self.brand_color,
            spaceAfter=30,
            alignment=TA_CENTER
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontName=CYRILLIC_FONT_BOLD,
            fontSize=16,
            textColor=self.secondary_color,
            spaceAfter=12
        )
        
        # Header
        story.append(Paragraph(self.company_name, title_style))
        story.append(Paragraph(self.company_slogan, styles['Normal']))
        story.append(Spacer(1, 20*mm))
        
        # Title
        story.append(Paragraph("ОТЧЕТ ОБ ОЦЕНКЕ НЕДВИЖИМОСТИ", title_style))
        story.append(Spacer(1, 10*mm))
        
        # Date
        date_str = (created_at or datetime.now()).strftime("%d.%m.%Y")
        story.append(Paragraph(f"Дата оценки: {date_str}", styles['Normal']))
        story.append(Spacer(1, 10*mm))
        
        # Object Details
        story.append(Paragraph("1. ОБЪЕКТ ОЦЕНКИ", heading_style))
        
        object_data = [
            ["Адрес:", address],
            ["Общая площадь:", f"{area_total} м²"],
        ]
        
        if rooms:
            object_data.append(["Количество комнат:", str(rooms)])
        if floor and total_floors:
            object_data.append(["Этаж:", f"{floor}/{total_floors}"])
        if building_type:
            type_names = {
                'panel': 'Панельный',
                'brick': 'Кирпичный',
                'monolithic': 'Монолитный',
                'block': 'Блочный',
                'wood': 'Деревянный',
                'other': 'Другой'
            }
            object_data.append(["Тип дома:", type_names.get(building_type, building_type)])
        
        object_table = Table(object_data, colWidths=[50*mm, 110*mm])
        object_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), CYRILLIC_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(object_table)
        story.append(Spacer(1, 10*mm))
        
        # Valuation Results
        story.append(Paragraph("2. РЕЗУЛЬТАТЫ ОЦЕНКИ", heading_style))
        
        results_data = [
            ["Рыночная стоимость:", f"{market_price:,.0f} ₽", f"({market_price_per_sqm:,.0f} ₽/м²)"],
        ]
        
        if interest_price:
            discount = (market_price - interest_price) / market_price * 100
            results_data.append([
                "Цена интереса (инвестор):",
                f"{interest_price:,.0f} ₽",
                f"(-{discount:.1f}%)"
            ])
        
        results_data.append(["Уверенность оценки:", f"{confidence}%", ""])
        
        results_table = Table(results_data, colWidths=[60*mm, 60*mm, 40*mm])
        results_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), CYRILLIC_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('FONTNAME', (1, 0), (1, -1), CYRILLIC_FONT_BOLD),
            ('TEXTCOLOR', (1, 0), (1, 0), self.secondary_color),
            ('TEXTCOLOR', (1, 1), (1, 1), self.brand_color),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(results_table)
        story.append(Spacer(1, 10*mm))
        
        # Comparables
        if comparables and len(comparables) > 0:
            story.append(Paragraph("3. ОБЪЕКТЫ-АНАЛОГИ", heading_style))
            story.append(Paragraph(
                f"Для оценки использовано {len(comparables)} объектов-аналогов. "
                "Ниже представлены ТОП-3 наиболее релевантных:",
                styles['Normal']
            ))
            story.append(Spacer(1, 5*mm))
            
            comp_data = [["№", "Площадь", "Цена", "₽/м²", "Расст."]]
            
            for idx, comp in enumerate(comparables[:3], 1):
                comp_data.append([
                    str(idx),
                    f"{comp['area_total']:.1f} м²",
                    f"{comp['price']:,.0f} ₽",
                    f"{comp['price_per_sqm']:,.0f}",
                    f"{comp['distance_km']:.1f} км"
                ])
            
            comp_table = Table(comp_data, colWidths=[10*mm, 30*mm, 50*mm, 35*mm, 25*mm])
            comp_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), CYRILLIC_FONT),
                ('BACKGROUND', (0, 0), (-1, 0), self.brand_color),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), CYRILLIC_FONT_BOLD),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            story.append(comp_table)
            
            # Add URLs if available
            if any('url' in c and c['url'] for c in comparables[:3]):
                story.append(Spacer(1, 5*mm))
                story.append(Paragraph("Ссылки на объявления:", styles['Heading3']))
                for idx, comp in enumerate(comparables[:3], 1):
                    if 'url' in comp and comp['url']:
                        story.append(Paragraph(
                            f"{idx}. <link href='{comp['url']}'>{comp['url']}</link>",
                            styles['Normal']
                        ))
        
        story.append(Spacer(1, 15*mm))
        
        # Footer
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontName=CYRILLIC_FONT,
            fontSize=9,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        
        story.append(Paragraph("_" * 80, footer_style))
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph(
            f"Отчет сгенерирован автоматически • {self.website}",
            footer_style
        ))
        story.append(Paragraph(
            "Для проверки и детального анализа перейдите на сайт",
            footer_style
        ))
        
        # Build PDF
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        return pdf_bytes


def generate_report_bytes(valuation_data: Dict) -> bytes:
    """
    Удобная функция для генерации отчета из словаря с данными оценки.
    
    Args:
        valuation_data: Данные оценки (из API response)
        
    Returns:
        bytes: PDF контент
    """
    generator = ReportGenerator()
    
    return generator.generate_valuation_report(
        address=valuation_data.get('address', 'Не указан'),
        area_total=valuation_data.get('area_total', 0),
        rooms=valuation_data.get('rooms'),
        floor=valuation_data.get('floor'),
        total_floors=valuation_data.get('total_floors'),
        building_type=valuation_data.get('building_type_detected'),
        market_price=valuation_data.get('estimated_price', 0),
        market_price_per_sqm=valuation_data.get('estimated_price_per_sqm', 0),
        interest_price=valuation_data.get('interest_price'),
        interest_price_per_sqm=valuation_data.get('interest_price_per_sqm'),
        comparables=valuation_data.get('comparables', []),
        confidence=valuation_data.get('confidence', 0),
        created_at=datetime.now()
    )
