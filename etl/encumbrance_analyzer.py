"""
Анализатор обременений в описаниях объявлений.

Обременения:
- Зарегистрированные люди
- Залог/ипотека на объекте
- Требуется выселение
- Снятие с регистрационного учета
- Прописанные люди
- Выселение по суду

ВАЖНО: Контекстный анализ для исключения ложных срабатываний
(например, "помощь с ипотекой" - это не обременение)
"""
import re
import logging
from typing import Dict, List, Tuple, Optional

LOGGER = logging.getLogger(__name__)


class EncumbranceAnalyzer:
    """Анализатор обременений в текстах объявлений."""
    
    # Паттерны для обнаружения обременений (негативный контекст)
    ENCUMBRANCE_PATTERNS = {
        'registered_people': {
            'name': 'Зарегистрированные люди',
            'patterns': [
                r'зарегистриров\w+ \d+ чел',
                r'прописан\w+ \d+ чел',
                r'зарегистриров\w+ дети',
                r'прописан\w+ дети',
                r'с жильц',
                r'с пропиской',
                r'есть прописанные',
                r'есть зарегистрированные',
                r'зарегистрирован собственник',
                r'прописан собственник',
                r'\d+ зарегистриров',
                r'\d+ прописан',
                r'проживают люди',
                r'живут люди',
                r'не выписан',
                r'с регистрацией',
            ],
            'negative_context': [
                r'без зарегистриров',
                r'никто не зарегистриров',
                r'без прописанных',
                r'никто не прописан',
                r'выписан',
                r'чистая продажа',
            ]
        },
        'eviction_required': {
            'name': 'Требуется выселение',
            'patterns': [
                r'требуется выселение',
                r'нужно выселение',
                r'необходимо выселение',
                r'требуется снятие',
                r'нужно снятие',
                r'выселение через суд',
                r'выселение по суду',
                r'принудительное выселение',
                r'судебное выселение',
                r'снятие с учета',
                r'снятие с регистр',
            ],
            'negative_context': []
        },
        'mortgage_on_property': {
            'name': 'Залог/ипотека на объекте',
            'patterns': [
                r'квартира в ипотеке',
                r'объект в залоге',
                r'под залогом',
                r'обременение ипотекой',
                r'ипотечное обременение',
                r'залог банка',
                r'не снято обременение',
                r'с обременением',
                r'банк залогодержатель',
                r'кредит на квартиру',
                r'ипотечный кредит на объект',
            ],
            'negative_context': [
                r'без обременений',
                r'нет обременений',
                r'обременений нет',
                r'помощь с ипотекой',
                r'помогу с ипотекой',
                r'ипотека возможна',
                r'возможна ипотека',
                r'подходит под ипотеку',
                r'одобрение ипотеки',
                r'оформление ипотеки',
                r'содействие в ипотеке',
                r'помогу оформить ипотеку',
                r'ипотека покупателя',
                r'покупка в ипотеку',
            ]
        },
        'tenants_living': {
            'name': 'Живут арендаторы',
            'patterns': [
                r'сдается',
                r'арендаторы',
                r'квартиранты',
                r'жильцы проживают',
                r'сдаётся',
                r'в аренде',
                r'сдана в аренду',
                r'проживают арендаторы',
                r'живут арендаторы',
            ],
            'negative_context': [
                r'свободна',
                r'освобождена',
                r'никто не проживает',
                r'не сдается',
                r'возможность сдачи',  # Это предложение, а не факт
                r'можно сдавать',
                r'подходит для сдачи',
            ]
        },
        'legal_issues': {
            'name': 'Юридические проблемы',
            'patterns': [
                r'судебное разбирательство',
                r'судебный спор',
                r'в суде',
                r'судебное решение',
                r'арест',
                r'под арестом',
                r'конфискация',
                r'наследственное дело',
                r'споры о наследстве',
                r'оспаривается',
                r'судебное производство',
            ],
            'negative_context': [
                r'без судебных',
                r'нет споров',
                r'чистая сделка',
            ]
        }
    }
    
    # Позитивные паттерны (исключают обременения)
    POSITIVE_PATTERNS = [
        r'чистая продажа',
        r'свободная продажа',
        r'без обременений',
        r'нет обременений',
        r'никто не прописан',
        r'никто не зарегистрирован',
        r'собственник выписан',
        r'освобождена',
        r'свободна',
        r'прямая продажа',
        r'юридически чистая',
        r'без проблем',
    ]
    
    def analyze(self, text: str) -> Dict[str, any]:
        """
        Анализирует текст на наличие обременений.
        
        Parameters
        ----------
        text : str
            Текст описания объявления
            
        Returns
        -------
        dict
            {
                'has_encumbrances': bool,
                'encumbrances': list,  # Список найденных обременений
                'details': dict,       # Детали по каждому типу
                'confidence': float,   # Уверенность (0-1)
                'flags': list,         # Список флагов
            }
        """
        if not text or len(text) < 20:
            return {
                'has_encumbrances': False,
                'encumbrances': [],
                'details': {},
                'confidence': 0.0,
                'flags': [],
            }
        
        text_lower = text.lower()
        
        # Проверить позитивные паттерны (исключают обременения)
        has_positive = self._check_positive_patterns(text_lower)
        
        # Найти обременения
        found_encumbrances = []
        details = {}
        
        for enc_type, config in self.ENCUMBRANCE_PATTERNS.items():
            result = self._check_encumbrance(text_lower, config)
            
            if result['found']:
                found_encumbrances.append({
                    'type': enc_type,
                    'name': config['name'],
                    'matches': result['matches'],
                    'confidence': result['confidence'],
                })
                
                details[enc_type] = {
                    'found': True,
                    'matches': result['matches'],
                    'confidence': result['confidence'],
                }
        
        # Рассчитать общую уверенность
        if found_encumbrances:
            # Средняя уверенность по всем найденным обременениям
            avg_confidence = sum(e['confidence'] for e in found_encumbrances) / len(found_encumbrances)
            
            # Снизить уверенность если есть позитивные паттерны
            if has_positive:
                avg_confidence *= 0.5
        else:
            avg_confidence = 0.0
        
        # Генерировать флаги
        flags = []
        for enc in found_encumbrances:
            if enc['confidence'] >= 0.7:
                flags.append(enc['type'])
        
        has_encumbrances = len(found_encumbrances) > 0 and avg_confidence >= 0.5
        
        return {
            'has_encumbrances': has_encumbrances,
            'encumbrances': found_encumbrances,
            'details': details,
            'confidence': avg_confidence,
            'flags': flags,
            'positive_indicators': has_positive,
        }
    
    def _check_positive_patterns(self, text: str) -> bool:
        """Проверить наличие позитивных паттернов."""
        for pattern in self.POSITIVE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _check_encumbrance(self, text: str, config: dict) -> dict:
        """
        Проверить конкретный тип обременения.
        
        Returns
        -------
        dict
            {
                'found': bool,
                'matches': list,
                'confidence': float,
            }
        """
        matches = []
        
        # Найти все совпадения с паттернами обременения
        for pattern in config['patterns']:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                matches.append({
                    'pattern': pattern,
                    'text': match.group(0),
                    'position': match.start(),
                })
        
        if not matches:
            return {
                'found': False,
                'matches': [],
                'confidence': 0.0,
            }
        
        # Проверить негативный контекст (исключающие паттерны)
        has_negative_context = False
        for pattern in config['negative_context']:
            if re.search(pattern, text, re.IGNORECASE):
                has_negative_context = True
                break
        
        # Рассчитать уверенность
        if has_negative_context:
            # Снизить уверенность если есть исключающий контекст
            confidence = 0.3 * min(len(matches) / 2.0, 1.0)
        else:
            # Высокая уверенность если нет исключающего контекста
            confidence = min(0.7 + (len(matches) - 1) * 0.1, 1.0)
        
        return {
            'found': True,
            'matches': matches,
            'confidence': confidence,
        }
    
    def get_summary(self, analysis: dict) -> str:
        """
        Получить краткое резюме анализа.
        
        Parameters
        ----------
        analysis : dict
            Результат анализа
            
        Returns
        -------
        str
            Текстовое резюме
        """
        if not analysis['has_encumbrances']:
            return "✅ Обременений не обнаружено"
        
        summary_parts = [
            f"⚠️  Обнаружено обременений: {len(analysis['encumbrances'])}",
            f"Уверенность: {analysis['confidence']:.0%}",
        ]
        
        for enc in analysis['encumbrances']:
            summary_parts.append(
                f"  • {enc['name']} ({enc['confidence']:.0%})"
            )
        
        if analysis.get('positive_indicators'):
            summary_parts.append("ℹ️  Найдены позитивные индикаторы (возможно ложное срабатывание)")
        
        return "\n".join(summary_parts)


# Singleton instance
_analyzer = None

def get_analyzer() -> EncumbranceAnalyzer:
    """Получить глобальный экземпляр анализатора."""
    global _analyzer
    if _analyzer is None:
        _analyzer = EncumbranceAnalyzer()
    return _analyzer


def analyze_description(description: str) -> Dict[str, any]:
    """
    Быстрая функция для анализа описания.
    
    Parameters
    ----------
    description : str
        Текст описания
        
    Returns
    -------
    dict
        Результат анализа
    """
    analyzer = get_analyzer()
    return analyzer.analyze(description)


# Примеры использования
if __name__ == "__main__":
    # Тестовые примеры
    examples = [
        {
            'description': 'Продается квартира. Помогу с ипотекой. Быстрый выход на сделку.',
            'expected': False,  # Это не обременение
        },
        {
            'description': 'Квартира в ипотеке, требуется снятие обременения банка. Прописаны 2 человека.',
            'expected': True,  # Есть обременения
        },
        {
            'description': 'Чистая продажа, никто не прописан, без обременений. Готова к сделке.',
            'expected': False,  # Нет обременений
        },
        {
            'description': 'Сдается арендаторам, договор до конца года. Зарегистрированы дети.',
            'expected': True,  # Есть обременения
        },
        {
            'description': 'Возможна покупка в ипотеку. Свободная продажа.',
            'expected': False,  # Это не обременение
        },
    ]
    
    analyzer = get_analyzer()
    
    print("="*60)
    print("ТЕСТИРОВАНИЕ АНАЛИЗАТОРА ОБРЕМЕНЕНИЙ")
    print("="*60)
    
    for i, example in enumerate(examples, 1):
        print(f"\n--- Пример {i} ---")
        print(f"Описание: {example['description'][:80]}...")
        
        result = analyzer.analyze(example['description'])
        
        print(f"Ожидается обременение: {example['expected']}")
        print(f"Обнаружено: {result['has_encumbrances']}")
        print(f"\n{analyzer.get_summary(result)}")
        
        if result['has_encumbrances'] != example['expected']:
            print("❌ ОШИБКА: Результат не совпадает с ожидаемым!")
        else:
            print("✅ OK")

