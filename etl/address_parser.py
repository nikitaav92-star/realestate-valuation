"""
Парсер адресов CIAN без внешних API.

Извлекает компоненты адреса из строки CIAN:
- Округ (САО, ЮАО, и т.д.)
- Район (Братеево, Марьино, и т.д.)
- Улица
- Дом, корпус, строение

Для внутреннего сравнения и аналитики.
Для юридической проверки - использовать DaData/ФИАС.
"""
import re
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class ParsedAddress:
    """Распарсенный адрес."""
    city: str = "Москва"
    okrug: Optional[str] = None      # САО, ЮАО, и т.д.
    district: Optional[str] = None   # Братеево, Марьино
    street: Optional[str] = None     # Братеевская
    street_type: Optional[str] = None  # ул, пр-т, пер, ш
    house: Optional[str] = None      # 8
    building: Optional[str] = None   # корпус (К4)
    structure: Optional[str] = None  # строение (С1)
    raw: str = ""                    # исходная строка

    def normalized(self) -> str:
        """Нормализованный адрес для сравнения."""
        parts = [self.city]
        if self.district:
            parts.append(f"р-н {self.district}")
        if self.street:
            parts.append(f"ул {self.street}")
        if self.house:
            h = f"д {self.house}"
            if self.building:
                h += f" к {self.building}"
            if self.structure:
                h += f" с {self.structure}"
            parts.append(h)
        return ", ".join(parts)

    def house_key(self) -> Optional[str]:
        """Ключ для группировки по дому."""
        if not self.street or not self.house:
            return None
        key = f"{self.street}_{self.house}"
        if self.building:
            key += f"к{self.building}"
        return key.lower()


# Округа Москвы
OKRUGS = {
    'ЦАО': 'Центральный',
    'САО': 'Северный',
    'СВАО': 'Северо-Восточный',
    'ВАО': 'Восточный',
    'ЮВАО': 'Юго-Восточный',
    'ЮАО': 'Южный',
    'ЮЗАО': 'Юго-Западный',
    'ЗАО': 'Западный',
    'СЗАО': 'Северо-Западный',
    'ЗелАО': 'Зеленоградский',
    'ТАО': 'Троицкий',
    'НАО': 'Новомосковский',
}

# Типы улиц
STREET_TYPES = [
    (r'\bулица\b', 'ул'),
    (r'\bул\.?\b', 'ул'),
    (r'\bпроспект\b', 'пр-т'),
    (r'\bпр-т\.?\b', 'пр-т'),
    (r'\bпереулок\b', 'пер'),
    (r'\bпер\.?\b', 'пер'),
    (r'\bшоссе\b', 'ш'),
    (r'\bш\.?\b', 'ш'),
    (r'\bбульвар\b', 'б-р'),
    (r'\bб-р\.?\b', 'б-р'),
    (r'\bнабережная\b', 'наб'),
    (r'\bнаб\.?\b', 'наб'),
    (r'\bпроезд\b', 'пр'),
    (r'\bаллея\b', 'ал'),
    (r'\bплощадь\b', 'пл'),
]


def parse_address(address: str) -> ParsedAddress:
    """
    Парсит адрес CIAN в структурированный формат.

    Examples:
        "Москва, ЮАО, р-н Братеево, Братеевская ул., 8К4"
        "Москва, ВАО, р-н Вешняки, Снайперская ул., 11"
        "Москва, НАО (Новомосковский), Марьино поселок, 5"
    """
    result = ParsedAddress(raw=address)

    if not address:
        return result

    addr = address.strip()

    # 1. Извлечь округ
    for okrug_code in OKRUGS:
        if okrug_code in addr:
            result.okrug = okrug_code
            break

    # 2. Извлечь район
    # Паттерн: "р-н Братеево" или "р-н Чертаново Южное" (до запятой или улицы)
    district_match = re.search(r'р-н\s+([А-Яа-яёЁ\-\s]+?)(?:,|\s+ул|\s+пр|\s+пер|\s+ш\.|$)', addr)
    if district_match:
        result.district = district_match.group(1).strip()
    else:
        # Попробовать "район X"
        district_match = re.search(r'район\s+([А-Яа-яёЁ\-\s]+?)(?:,|$)', addr)
        if district_match:
            result.district = district_match.group(1).strip()
        else:
            # Поселок/деревня как район (для НАО, ТАО)
            settlement_match = re.search(r'([\w\-]+)\s+(поселок|деревня|посёлок|село)', addr, re.IGNORECASE)
            if settlement_match:
                result.district = settlement_match.group(1).strip()

    # 3. Извлечь улицу и тип
    # Паттерны: "Братеевская ул." или "улица Братеевская" или "ул. Братеевская"

    # Паттерн 1: "Название ул." или "Название улица"
    street_match = re.search(
        r'([А-Яа-яёЁ0-9\-]+(?:\s+[А-Яа-яёЁ0-9\-]+)?)\s+(ул\.?|улица|пр-т|проспект|пер\.?|переулок|ш\.?|шоссе|б-р|бульвар)',
        addr, re.IGNORECASE
    )
    if street_match:
        result.street = street_match.group(1).strip()
        for pattern, short in STREET_TYPES:
            if re.search(pattern, street_match.group(2), re.IGNORECASE):
                result.street_type = short
                break
    else:
        # Паттерн 2: "улица Название" или "ул. Название"
        street_match = re.search(
            r'(ул\.?|улица|пр-т|проспект|пер\.?|переулок)\s+([А-Яа-яёЁ0-9\-]+(?:\s+[А-Яа-яёЁ0-9\-]+)?)',
            addr, re.IGNORECASE
        )
        if street_match:
            for pattern, short in STREET_TYPES:
                if re.search(pattern, street_match.group(1), re.IGNORECASE):
                    result.street_type = short
                    break
            result.street = street_match.group(2).strip()

    # 4. Извлечь дом, корпус, строение
    # Паттерны: "8К4", "8к4", "8 к4", "д. 8", "дом 8", "8/2", "8с1", "к704" (Зеленоград)

    # Сначала попробовать Зеленоград: "мкр. 7-й, к704" - корпус как дом
    zelenograd_match = re.search(r'мкр\.?\s*(\d+)[\-й]*,?\s*к(\d+)', addr, re.IGNORECASE)
    if zelenograd_match:
        result.street = f"мкр. {zelenograd_match.group(1)}"
        result.house = zelenograd_match.group(2)
    else:
        # Ищем в конце адреса
        # Паттерн: число + опционально К/к + число или /число
        house_match = re.search(
            r'[,\s](\d+)\s*[/]?\s*([КкKk](\d+))?([СсCc](\d+))?(?:\s*$|,)',
            addr
        )
        if house_match:
            result.house = house_match.group(1)
            if house_match.group(3):
                result.building = house_match.group(3)
            if house_match.group(5):
                result.structure = house_match.group(5)
        else:
            # Попробовать "д. 8" или "дом 8"
            house_match = re.search(r'(?:д\.?|дом)\s*(\d+)', addr, re.IGNORECASE)
            if house_match:
                result.house = house_match.group(1)

    # Если корпус не найден, ищем отдельно
    if not result.building:
        building_match = re.search(r'[КкKk]\.?\s*(\d+)', addr)
        if building_match:
            result.building = building_match.group(1)

    # Если строение не найдено
    if not result.structure:
        structure_match = re.search(r'[СсCc]\.?\s*(\d+)', addr)
        if structure_match:
            result.structure = structure_match.group(1)

    return result


def addresses_same_house(addr1: str, addr2: str) -> bool:
    """Проверить, относятся ли адреса к одному дому."""
    p1 = parse_address(addr1)
    p2 = parse_address(addr2)

    key1 = p1.house_key()
    key2 = p2.house_key()

    if not key1 or not key2:
        return False

    return key1 == key2


def addresses_same_street(addr1: str, addr2: str) -> bool:
    """Проверить, относятся ли адреса к одной улице."""
    p1 = parse_address(addr1)
    p2 = parse_address(addr2)

    if not p1.street or not p2.street:
        return False

    return p1.street.lower() == p2.street.lower()


# Тесты
if __name__ == "__main__":
    test_addresses = [
        "Москва, ЮАО, р-н Братеево, Братеевская ул., 8К4",
        "Москва, ВАО, р-н Вешняки, Снайперская ул., 11",
        "Москва, НАО (Новомосковский), Марьино поселок, 5",
        "Москва, ЗАО, р-н Дорогомилово, Киевская улица, 16",
        "Москва, САО, р-н Коптево, Большая Академическая улица, 79К3",
        "Москва, СВАО, р-н Бутырский, улица Яблочкова, 18",
    ]

    print("=" * 70)
    print("ТЕСТ ПАРСЕРА АДРЕСОВ")
    print("=" * 70)

    for addr in test_addresses:
        parsed = parse_address(addr)
        print(f"\nИсходный: {addr}")
        print(f"  Округ:   {parsed.okrug}")
        print(f"  Район:   {parsed.district}")
        print(f"  Улица:   {parsed.street} ({parsed.street_type})")
        print(f"  Дом:     {parsed.house} К{parsed.building or '-'} С{parsed.structure or '-'}")
        print(f"  Ключ:    {parsed.house_key()}")
        print(f"  Норм:    {parsed.normalized()}")
