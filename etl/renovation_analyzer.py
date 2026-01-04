"""
Анализатор качества ремонта по фотографиям.

Использует Google Gemini для оценки фото квартир.
Пока заглушка - будет интегрирован позже.

Классы ремонта:
1 - Требует ремонта (старый ремонт, повреждения)
2 - Косметический (простой стандартный ремонт)
3 - Евроремонт (качественные материалы, современный)
4 - Дизайнерский (авторский интерьер, премиум)
"""
import logging
from typing import Dict, List, Optional

LOGGER = logging.getLogger(__name__)


class RenovationAnalyzer:
    """Анализатор качества ремонта по фото."""

    RENOVATION_CLASSES = {
        1: {"name": "Требует ремонта", "coef": 0.85},
        2: {"name": "Косметический", "coef": 1.00},
        3: {"name": "Евроремонт", "coef": 1.10},
        4: {"name": "Дизайнерский", "coef": 1.20},
    }

    PROMPT = """Оцени качество ремонта квартиры по фото.

Классы:
1 - Требует ремонта (старый ремонт, повреждения, ободранные обои)
2 - Косметический (простой стандартный ремонт, базовые материалы)
3 - Евроремонт (качественные материалы, современный дизайн)
4 - Дизайнерский (авторский интерьер, премиум материалы)

Ответь строго в JSON формате:
{"class": 1-4, "confidence": 0.0-1.0, "details": "краткое описание на русском"}
"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Инициализация анализатора.

        Parameters
        ----------
        api_key : str, optional
            API ключ Google Gemini. Если не указан - работает как заглушка.
        """
        self.api_key = api_key
        self.model = None

        if api_key:
            self._init_gemini()

    def _init_gemini(self):
        """Инициализация Gemini модели."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            LOGGER.info("✅ Gemini модель инициализирована")
        except ImportError:
            LOGGER.warning("⚠️ google-generativeai не установлен. pip install google-generativeai")
        except Exception as e:
            LOGGER.error(f"❌ Ошибка инициализации Gemini: {e}")

    def analyze(self, photo_urls: List[str]) -> Dict:
        """
        Анализ фотографий квартиры.

        Parameters
        ----------
        photo_urls : list
            Список URL фотографий

        Returns
        -------
        dict
            {
                "renovation_class": int (1-4),
                "renovation_name": str,
                "confidence": float (0-1),
                "price_coef": float,
                "details": str,
                "analyzed": bool
            }
        """
        if not photo_urls:
            return self._empty_result("Нет фотографий")

        if not self.model:
            # Заглушка - возвращаем "не проанализировано"
            return self._empty_result("Gemini не настроен")

        return self._analyze_with_gemini(photo_urls)

    def _analyze_with_gemini(self, photo_urls: List[str]) -> Dict:
        """Реальный анализ через Gemini."""
        try:
            import requests
            from PIL import Image
            from io import BytesIO
            import json

            # Загружаем первые 5 фото
            images = []
            for url in photo_urls[:5]:
                try:
                    resp = requests.get(url, timeout=10)
                    img = Image.open(BytesIO(resp.content))
                    images.append(img)
                except Exception as e:
                    LOGGER.warning(f"Не удалось загрузить фото {url}: {e}")

            if not images:
                return self._empty_result("Не удалось загрузить фото")

            # Отправляем в Gemini
            response = self.model.generate_content([self.PROMPT, *images])

            # Парсим ответ
            result = self._parse_gemini_response(response.text)
            return result

        except Exception as e:
            LOGGER.error(f"Ошибка анализа Gemini: {e}")
            return self._empty_result(f"Ошибка: {e}")

    def _parse_gemini_response(self, text: str) -> Dict:
        """Парсинг ответа Gemini."""
        import json
        import re

        try:
            # Ищем JSON в ответе
            json_match = re.search(r'\{[^}]+\}', text)
            if json_match:
                data = json.loads(json_match.group())

                renovation_class = int(data.get("class", 2))
                renovation_class = max(1, min(4, renovation_class))

                return {
                    "renovation_class": renovation_class,
                    "renovation_name": self.RENOVATION_CLASSES[renovation_class]["name"],
                    "confidence": float(data.get("confidence", 0.5)),
                    "price_coef": self.RENOVATION_CLASSES[renovation_class]["coef"],
                    "details": data.get("details", ""),
                    "analyzed": True,
                }
        except Exception as e:
            LOGGER.warning(f"Не удалось распарсить ответ Gemini: {e}")

        return self._empty_result("Не удалось распарсить ответ")

    def _empty_result(self, reason: str) -> Dict:
        """Пустой результат (заглушка)."""
        return {
            "renovation_class": None,
            "renovation_name": None,
            "confidence": 0.0,
            "price_coef": 1.0,
            "details": reason,
            "analyzed": False,
        }


# Singleton
_analyzer = None


def get_analyzer(api_key: Optional[str] = None) -> RenovationAnalyzer:
    """Получить глобальный экземпляр анализатора."""
    global _analyzer
    if _analyzer is None:
        _analyzer = RenovationAnalyzer(api_key)
    return _analyzer


def analyze_listing_photos(photo_urls: List[str], api_key: Optional[str] = None) -> Dict:
    """
    Быстрая функция для анализа фото объявления.

    Parameters
    ----------
    photo_urls : list
        Список URL фотографий
    api_key : str, optional
        API ключ Gemini

    Returns
    -------
    dict
        Результат анализа
    """
    analyzer = get_analyzer(api_key)
    return analyzer.analyze(photo_urls)


if __name__ == "__main__":
    # Тест заглушки
    print("=== Тест RenovationAnalyzer (заглушка) ===")

    analyzer = RenovationAnalyzer()  # Без API ключа

    result = analyzer.analyze([
        "https://example.com/photo1.jpg",
        "https://example.com/photo2.jpg",
    ])

    print(f"Результат: {result}")
    print(f"Проанализировано: {result['analyzed']}")
    print(f"Причина: {result['details']}")
