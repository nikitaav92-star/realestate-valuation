-- Добавление полей для обременений и пометки ошибок

-- Поля для обременений
ALTER TABLE listings ADD COLUMN IF NOT EXISTS has_encumbrances BOOLEAN DEFAULT FALSE;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS encumbrance_types TEXT[];  -- Массив типов обременений
ALTER TABLE listings ADD COLUMN IF NOT EXISTS encumbrance_details JSONB;  -- Детали анализа
ALTER TABLE listings ADD COLUMN IF NOT EXISTS encumbrance_confidence NUMERIC(3,2);  -- Уверенность (0.00-1.00)

-- Поля для пометки ошибок
ALTER TABLE listings ADD COLUMN IF NOT EXISTS is_error BOOLEAN DEFAULT FALSE;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS error_reason TEXT;  -- Причина ошибки
ALTER TABLE listings ADD COLUMN IF NOT EXISTS error_comment TEXT;  -- Комментарий для будущих правок
ALTER TABLE listings ADD COLUMN IF NOT EXISTS marked_by TEXT;  -- Кто пометил (user/auto)
ALTER TABLE listings ADD COLUMN IF NOT EXISTS marked_at TIMESTAMP WITH TIME ZONE;  -- Когда помечено

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_listings_encumbrances ON listings(has_encumbrances) WHERE has_encumbrances = TRUE;
CREATE INDEX IF NOT EXISTS idx_listings_errors ON listings(is_error) WHERE is_error = TRUE;
CREATE INDEX IF NOT EXISTS idx_listings_encumbrance_types ON listings USING gin(encumbrance_types);

-- Комментарии
COMMENT ON COLUMN listings.has_encumbrances IS 'Есть ли обременения (зарегистрированные, залог, выселение и т.д.)';
COMMENT ON COLUMN listings.encumbrance_types IS 'Типы обременений: registered_people, mortgage_on_property, eviction_required, tenants_living, legal_issues';
COMMENT ON COLUMN listings.encumbrance_details IS 'Детали анализа обременений (JSON)';
COMMENT ON COLUMN listings.encumbrance_confidence IS 'Уверенность в обнаружении обременений (0.00 - 1.00)';

COMMENT ON COLUMN listings.is_error IS 'Помечено как ошибка (неправильно распарсено, нужно исключить)';
COMMENT ON COLUMN listings.error_reason IS 'Причина ошибки (например: wrong_property_type, parsing_error, duplicate)';
COMMENT ON COLUMN listings.error_comment IS 'Комментарий для будущих правок алгоритма парсера';
COMMENT ON COLUMN listings.marked_by IS 'Кто пометил: user (вручную) или auto (автоматически)';
COMMENT ON COLUMN listings.marked_at IS 'Когда объявление было помечено';

-- Представление для быстрого просмотра проблемных объявлений
CREATE OR REPLACE VIEW listings_with_issues AS
SELECT 
    id,
    url,
    address,
    address_full,
    has_encumbrances,
    encumbrance_types,
    encumbrance_confidence,
    is_error,
    error_reason,
    error_comment,
    marked_at
FROM listings
WHERE is_active = TRUE 
  AND (has_encumbrances = TRUE OR is_error = TRUE)
ORDER BY marked_at DESC NULLS LAST, id DESC;

COMMENT ON VIEW listings_with_issues IS 'Объявления с обременениями или помеченные как ошибка';

