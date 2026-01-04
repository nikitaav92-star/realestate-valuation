"""
EGRN (Unified State Register of Real Estate) document parser.

Extracts information from EGRN PDF files:
- Address
- Total area
- Floor
- Cadastral number
- Building year (if available)
"""

import re
import PyPDF2
from typing import Optional, Dict
from dataclasses import dataclass


@dataclass
class EGRNData:
    """Parsed EGRN document data."""
    address: Optional[str] = None
    area: Optional[float] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    cadastral_number: Optional[str] = None
    building_year: Optional[int] = None
    raw_text: str = ""


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from PDF file."""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
    except Exception as e:
        raise ValueError(f"Failed to read PDF: {e}")


def parse_egrn_text(text: str) -> EGRNData:
    """
    Parse EGRN document text and extract key information.
    
    EGRN выписки обычно содержат:
    - Адрес (местоположение): "Москва, ул. Тверская, д. 12, кв. 34"
    - Площадь: "Площадь, кв.м: 75.5"
    - Кадастровый номер: "77:01:0001234:567"
    - Этаж: может быть в адресе или отдельной строкой
    """
    
    data = EGRNData(raw_text=text)
    
    # Extract address (various formats)
    address_patterns = [
        r'(?:Адрес|Местоположение|Расположение)[:：\s]*([^\n]+)',
        r'Москва[,\s]+([^\n]+)',
    ]
    
    for pattern in address_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data.address = match.group(1).strip()
            break
    
    # Extract area (площадь)
    area_patterns = [
        r'Площадь[^\d]*([\d,\.]+)\s*(?:кв\.?\s*м|м²)',
        r'(?:общая\s+)?площадь[^\d]*([\d,\.]+)',
    ]
    
    for pattern in area_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            area_str = match.group(1).replace(',', '.')
            try:
                data.area = float(area_str)
                break
            except ValueError:
                continue
    
    # Extract cadastral number
    cadastral_pattern = r'(\d{2}:\d{2}:\d{7}:\d+)'
    match = re.search(cadastral_pattern, text)
    if match:
        data.cadastral_number = match.group(1)
    
    # Extract floor from address or separate field
    floor_patterns = [
        r'(?:этаж|эт\.?)[^\d]*([\d]+)',
        r'на\s+([\d]+)\s+этаже',
        r'[\s,]эт\.?\s*([\d]+)',
    ]
    
    for pattern in floor_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                data.floor = int(match.group(1))
                break
            except ValueError:
                continue
    
    # Extract total floors (этажность дома)
    total_floors_patterns = [
        r'этажность[^\d]*([\d]+)',
        r'в\s+([\d]+)[\s-]*этажном',
        r'количество\s+этажей[^\d]*([\d]+)',
    ]
    
    for pattern in total_floors_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                data.total_floors = int(match.group(1))
                break
            except ValueError:
                continue
    
    # Extract building year
    year_patterns = [
        r'год\s+(?:постройки|ввода|строительства)[^\d]*([\d]{4})',
        r'построен[^\d]*([\d]{4})',
    ]
    
    for pattern in year_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                year = int(match.group(1))
                if 1800 <= year <= 2030:
                    data.building_year = year
                    break
            except ValueError:
                continue
    
    return data


def parse_egrn_pdf(pdf_path: str) -> EGRNData:
    """
    Parse EGRN PDF file and extract information.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        EGRNData object with extracted information
        
    Raises:
        ValueError: If PDF cannot be read or parsed
    """
    text = extract_text_from_pdf(pdf_path)
    
    if not text or len(text) < 100:
        raise ValueError("PDF appears to be empty or corrupted")
    
    data = parse_egrn_text(text)
    
    if not data.address and not data.area:
        raise ValueError(
            "Could not extract key information from EGRN. "
            "Please check if this is a valid EGRN document."
        )
    
    return data


def format_egrn_summary(data: EGRNData) -> str:
    """Format EGRN data as human-readable summary."""
    lines = ["📄 Данные из ЕГРН:", ""]
    
    if data.address:
        lines.append(f"📍 Адрес: {data.address}")
    
    if data.area:
        lines.append(f"📏 Площадь: {data.area} м²")
    
    if data.floor:
        floor_text = f"🏢 Этаж: {data.floor}"
        if data.total_floors:
            floor_text += f" из {data.total_floors}"
        lines.append(floor_text)
    
    if data.cadastral_number:
        lines.append(f"🔢 Кадастровый №: {data.cadastral_number}")
    
    if data.building_year:
        lines.append(f"📅 Год постройки: {data.building_year}")
    
    if len(lines) == 2:  # Only header
        lines.append("⚠️ Не удалось извлечь информацию")
    
    return "\n".join(lines)


# Example usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python egrn_parser.py <path_to_egrn.pdf>")
        sys.exit(1)
    
    try:
        data = parse_egrn_pdf(sys.argv[1])
        print(format_egrn_summary(data))
        print("\n" + "="*50)
        print("Raw data:")
        print(f"  Address: {data.address}")
        print(f"  Area: {data.area}")
        print(f"  Floor: {data.floor}/{data.total_floors}")
        print(f"  Cadastral: {data.cadastral_number}")
        print(f"  Year: {data.building_year}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

