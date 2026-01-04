from etl.collector_cian import browser_fetcher as bf


def test_clean_address_removes_map_and_metro_fragments():
    raw = (
        "Москва, ВАО, р-н Сокольники, ул. ГастеллоНа карте "
        "Сокольники 14 мин. Электрозаводская 15 мин."
    )
    cleaned = bf.clean_address_text(raw)
    assert cleaned == "Москва, ВАО, р-н Сокольники, ул. Гастелло"
    assert bf._address_is_valid(cleaned, require_city=False)


def test_clean_address_handles_multiple_subway_mentions():
    raw = (
        "Москва, СЗАО, р-н Южное Тушино, Лодочная ул., 27К2 На карте "
        "Тушинская 5 мин. Сходненская 7 мин."
    )
    cleaned = bf.clean_address_text(raw)
    assert cleaned == "Москва, СЗАО, р-н Южное Тушино, Лодочная ул., 27К2"
    assert bf._address_is_valid(cleaned, require_city=False)


def test_address_validation_allows_missing_house_number():
    raw = "Москва, район Сокольники, улица Гастелло"
    cleaned = bf.clean_address_text(raw)
    assert cleaned == raw
    assert bf._address_is_valid(cleaned, require_city=False)



def test_clean_address_drops_tail_after_house_number():
    raw = (
        "Москва, ЮАО, р-н Братеево, ул. Борисовские Пруды, 18К1, "
        "Борисово, Алма-Атинская, Марьино"
    )
    cleaned = bf.clean_address_text(raw)
    assert cleaned == "Москва, ЮАО, р-н Братеево, ул. Борисовские Пруды, 18К1"


def test_clean_address_removes_mkad_distance():
    raw = (
        "Москва, НАО (Новомосковский), Марьино деревня, ул. Жемчужная, 1к9, "
        "Киевское шоссе 16 км от МКАД, Киевское"
    )
    cleaned = bf.clean_address_text(raw)
    assert cleaned == (
        "Москва, НАО (Новомосковский), Марьино деревня, ул. Жемчужная, 1к9"
    )
