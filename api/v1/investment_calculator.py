"""
Investment Calculator Module
Расчет "цены интереса" на основе инвестиционной модели.

Поддерживает 4 типа проектов:
1. Собственный (own) - 100% прибыли наша, 4%/мес
2. Партнерский (partner) - 50/50, мин 4%/мес или 1 млн
3. Партнерский Флип (partner_flip) - 50/50 + ремонт 4%/мес
4. Банковский Флип (bank_flip) - ипотека 2%/мес, 50/50, мин 1 млн
"""

from typing import Dict, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum


class ProjectType(str, Enum):
    """Тип инвестиционного проекта."""
    OWN = "own"                    # Собственный
    PARTNER = "partner"            # Партнерский 50/50
    PARTNER_FLIP = "partner_flip"  # Партнерский Флип
    BANK_FLIP = "bank_flip"        # Банковский Флип


class InvestmentParams(BaseModel):
    """Параметры инвестиционного проекта."""

    # Тип проекта
    project_type: ProjectType = Field(default=ProjectType.OWN, description="Тип проекта")

    # Торговая скидка
    bargain_discount: float = Field(default=0.07, description="Скидка на торг (по умолчанию 7%)")

    # Целевая прибыль (4% в месяц = 12% за 3 месяца)
    target_profit_rate: float = Field(default=0.12, description="Целевая прибыль за период проекта")
    monthly_rate: float = Field(default=0.04, description="Базовая ставка доходности в месяц (4%)")
    project_period_months: int = Field(default=3, description="Период проекта в месяцах")

    # Партнерские параметры
    partner_split: float = Field(default=0.5, description="Доля партнера (50%)")
    min_profit: float = Field(default=1000000, description="Минимальная прибыль (наша) - 1 млн")

    # Ипотечные параметры (для bank_flip)
    mortgage_rate: float = Field(default=0.02, description="Ипотечная ставка в месяц (2%)")
    mortgage_issue_fee: float = Field(default=0.0075, description="Комиссия за выдачу кредита (0.75%)")
    mortgage_prepay_months: int = Field(default=3, description="Месяцев % по ипотеке вперед")
    ltv: float = Field(default=0.8, description="LTV - доля кредита от цены (80%)")

    # Налог (всегда учитывается)
    tax_rate: float = Field(default=0.06, description="Налог на прибыль (6%)")

    # Опциональные фиксированные расходы
    include_notary: bool = Field(default=False, description="Включить нотариуса")
    notary_fee: float = Field(default=50000, description="Нотариус")

    include_state_fee: bool = Field(default=False, description="Включить госпошлину")
    state_fee: float = Field(default=4000, description="Госпошлина")

    include_pip: bool = Field(default=False, description="Включить ПИП")
    pip_per_sqm: float = Field(default=1500, description="ПИП (план) за м²")

    include_agency: bool = Field(default=False, description="Включить агентские")
    agency_fee: float = Field(default=200000, description="Агентские")

    include_utilities: bool = Field(default=False, description="Включить ЖКУ")
    utilities_per_month: float = Field(default=11500, description="ЖКУ в месяц")

    # Дополнительные опции
    include_eviction: bool = Field(default=False, description="Включить расходы на выселение")
    eviction_cost: float = Field(default=150000, description="Выселение")

    include_renovation: bool = Field(default=False, description="Включить расходы на ремонт")
    renovation_per_sqm: float = Field(default=50000, description="Ремонт за м²")

    include_foreman: bool = Field(default=False, description="Включить прораба")
    foreman_fee: float = Field(default=100000, description="Прораб")

    include_financing: bool = Field(default=False, description="Включить кредитование")
    financing_rate: float = Field(default=0.30, description="Кредитование (30%)")

    include_registrators_transfer: bool = Field(default=False, description="Регистраторы (переход)")
    registrators_transfer_fee: float = Field(default=15000, description="Регистраторы переход права")

    include_registrators_mortgage: bool = Field(default=False, description="Регистраторы (ипотека)")
    registrators_mortgage_fee: float = Field(default=10000, description="Регистраторы ипотека")

    include_contur_registration: bool = Field(default=False, description="Регистрация Контур")
    contur_registration_fee: float = Field(default=4000, description="Регистрация в Контур")


class InterestPriceResult(BaseModel):
    """Результат расчета цены интереса."""

    # Тип проекта
    project_type: str = Field(description="Тип проекта")
    project_type_name: str = Field(description="Название типа проекта")

    # Входные данные
    market_price: float = Field(description="Рыночная цена (оценка ЦИАН)")
    market_price_per_sqm: float = Field(description="Рыночная цена за м²")
    area_total: float = Field(description="Общая площадь")

    # Цена после ремонта (для флипов)
    sale_price_after_renovation: Optional[float] = Field(None, description="Цена продажи после ремонта")
    renovation_bonus: Optional[float] = Field(None, description="Прибавка к цене от ремонта")

    # Цена интереса
    interest_price: float = Field(description="Цена интереса (максимальная цена покупки)")
    interest_price_per_sqm: float = Field(description="Цена интереса за м²")

    # Расчетные показатели
    expected_sale_price: float = Field(description="Ожидаемая цена продажи")
    expected_sale_per_sqm: float = Field(description="Цена продажи за м²")

    total_costs: float = Field(description="Общие расходы на проект")
    fixed_costs: float = Field(description="Фиксированные расходы")
    variable_costs: float = Field(description="Переменные расходы")
    renovation_cost: Optional[float] = Field(None, description="Стоимость ремонта")

    # Прибыль
    expected_profit: float = Field(description="Общая прибыль проекта")
    our_profit: float = Field(description="Наша прибыль")
    partner_profit: Optional[float] = Field(None, description="Прибыль партнера")

    profit_rate: float = Field(description="% прибыли к вложениям")
    monthly_profit_rate: float = Field(description="% прибыли в месяц")
    our_monthly_rate: float = Field(description="Наш % в месяц")

    # Ипотечные показатели (для bank_flip)
    mortgage_amount: Optional[float] = Field(None, description="Сумма кредита")
    mortgage_monthly_payment: Optional[float] = Field(None, description="Ежемесячный платеж по ипотеке")
    mortgage_total_interest: Optional[float] = Field(None, description="Всего % по ипотеке")
    mortgage_prepayment: Optional[float] = Field(None, description="Предоплата % партнером")
    mortgage_issue_cost: Optional[float] = Field(None, description="Комиссия за выдачу")
    renovation_profit: Optional[float] = Field(None, description="Доход на ремонт (4%/мес)")

    # Период
    project_months: int = Field(description="Срок проекта в месяцах")

    # Разбивка расходов
    cost_breakdown: Dict[str, float] = Field(description="Детализация расходов")


def _calculate_fixed_costs(params: InvestmentParams, area_total: float, interest_price: float = 0) -> tuple[float, Dict[str, float]]:
    """Рассчитать фиксированные расходы и детализацию."""
    fixed_costs = 0
    breakdown = {}

    # ЖКУ
    if params.include_utilities:
        zhku = params.utilities_per_month * params.project_period_months
        fixed_costs += zhku
        breakdown["ЖКУ"] = zhku

    # Основные расходы
    if params.include_notary:
        fixed_costs += params.notary_fee
        breakdown["Нотариус"] = params.notary_fee
    if params.include_state_fee:
        fixed_costs += params.state_fee
        breakdown["Госпошлина"] = params.state_fee
    if params.include_pip:
        pip_cost = params.pip_per_sqm * area_total
        fixed_costs += pip_cost
        breakdown["ПИП"] = pip_cost
    if params.include_agency:
        fixed_costs += params.agency_fee
        breakdown["Агентские"] = params.agency_fee

    # Дополнительные расходы
    if params.include_eviction:
        fixed_costs += params.eviction_cost
        breakdown["Выселение"] = params.eviction_cost
    if params.include_renovation:
        renovation = params.renovation_per_sqm * area_total
        fixed_costs += renovation
        breakdown["Ремонт"] = renovation
    if params.include_foreman:
        fixed_costs += params.foreman_fee
        breakdown["Прораб"] = params.foreman_fee
    if params.include_registrators_transfer:
        fixed_costs += params.registrators_transfer_fee
        breakdown["Регистраторы (переход)"] = params.registrators_transfer_fee
    if params.include_registrators_mortgage:
        fixed_costs += params.registrators_mortgage_fee
        breakdown["Регистраторы (ипотека)"] = params.registrators_mortgage_fee
    if params.include_contur_registration:
        fixed_costs += params.contur_registration_fee
        breakdown["Регистрация Контур"] = params.contur_registration_fee
    if params.include_financing and interest_price > 0:
        financing = interest_price * params.financing_rate / (1 - params.financing_rate)
        fixed_costs += financing
        breakdown["Кредитование"] = financing

    return fixed_costs, breakdown


def calculate_own(market_price: float, area_total: float, params: InvestmentParams) -> InterestPriceResult:
    """
    Тип 1: СОБСТВЕННЫЙ проект
    - 100% прибыли наша
    - Целевая доходность: 4%/мес = 12% за 3 мес (или 48% за 12 мес при выселении)
    - Ремонт НЕ влияет на цену интереса, только на цену продажи и прибыль
    """
    market_price_per_sqm = market_price / area_total
    base_sale_price = market_price * (1 - params.bargain_discount)

    # ВАЖНО: Расчет цены интереса БЕЗ учёта ремонта
    # Ремонт не влияет на цену покупки
    params_no_renovation = params.model_copy()
    params_no_renovation.include_renovation = False
    params_no_renovation.include_foreman = False
    fixed_costs_no_reno, breakdown = _calculate_fixed_costs(params_no_renovation, area_total, 0)

    # Целевая прибыль
    target_profit_rate = params.monthly_rate * params.project_period_months

    # Формула цены интереса (без ремонта)
    after_tax_rate = 1 - params.tax_rate
    multiplier_expense = 1 + target_profit_rate
    divisor = after_tax_rate + target_profit_rate

    interest_price = (base_sale_price * after_tax_rate - fixed_costs_no_reno * multiplier_expense) / divisor

    # Пересчет с financing
    if params.include_financing and params.financing_rate > 0:
        financing_cost = interest_price * params.financing_rate / (1 - params.financing_rate)
        fixed_costs_no_reno += financing_cost
        breakdown["Кредитование"] = financing_cost
        interest_price = (base_sale_price * after_tax_rate - fixed_costs_no_reno * multiplier_expense) / divisor

    # Валидация: цена интереса должна быть положительной
    if interest_price <= 0:
        raise ValueError(f"Расходы слишком высоки для целевой доходности. Цена интереса: {interest_price:,.0f} ₽")

    interest_price_per_sqm = interest_price / area_total

    # Теперь добавляем ремонт для расчёта прибыли
    renovation_cost = None
    renovation_bonus = None
    renovation_profit = None
    final_sale_price = base_sale_price
    total_fixed_costs = fixed_costs_no_reno

    if params.include_renovation:
        renovation_cost = params.renovation_per_sqm * area_total
        renovation_bonus = renovation_cost * 1.8  # Увеличение цены от ремонта (×1.8)
        final_sale_price = base_sale_price + renovation_bonus
        total_fixed_costs += renovation_cost
        breakdown["Ремонт"] = renovation_cost
        # Профит от ремонта = бонус - затраты
        renovation_profit = renovation_bonus - renovation_cost
        if params.include_foreman:
            total_fixed_costs += params.foreman_fee
            breakdown["Прораб"] = params.foreman_fee

    # Прибыль с учётом ремонта
    gross_profit = final_sale_price - interest_price
    tax_amount = gross_profit * params.tax_rate
    expected_profit = gross_profit - total_fixed_costs - tax_amount
    breakdown["Налог 6%"] = tax_amount

    total_investment = interest_price + total_fixed_costs
    actual_profit_rate = expected_profit / total_investment if total_investment > 0 else 0
    monthly_profit_rate = actual_profit_rate / params.project_period_months

    return InterestPriceResult(
        project_type=ProjectType.OWN.value,
        project_type_name="Собственный",
        market_price=market_price,
        market_price_per_sqm=market_price_per_sqm,
        area_total=area_total,
        sale_price_after_renovation=final_sale_price if params.include_renovation else None,
        renovation_bonus=renovation_bonus,
        interest_price=interest_price,
        interest_price_per_sqm=interest_price_per_sqm,
        expected_sale_price=final_sale_price,
        expected_sale_per_sqm=final_sale_price / area_total,
        total_costs=total_fixed_costs + tax_amount,
        fixed_costs=total_fixed_costs,
        variable_costs=tax_amount,
        renovation_cost=renovation_cost,
        renovation_profit=renovation_profit,
        expected_profit=expected_profit,
        our_profit=expected_profit,
        partner_profit=None,
        profit_rate=actual_profit_rate,
        monthly_profit_rate=monthly_profit_rate,
        our_monthly_rate=monthly_profit_rate,
        project_months=params.project_period_months,
        cost_breakdown=breakdown
    )


def calculate_partner(market_price: float, area_total: float, params: InvestmentParams) -> InterestPriceResult:
    """
    Тип 2: ПАРТНЕРСКИЙ 50/50
    - Прибыль делится 50/50 с партнером
    - НО наша доля должна быть не менее 4%/мес от вложений
    - Партнёр получает остаток (может быть меньше 4%/мес)
    - При сроке < 3 мес: наша минималка 1 млн руб
    - Ремонт НЕ влияет на цену интереса, только на цену продажи и прибыль
    """
    market_price_per_sqm = market_price / area_total
    base_sale_price = market_price * (1 - params.bargain_discount)

    # ВАЖНО: Расчет цены интереса БЕЗ учёта ремонта
    params_no_renovation = params.model_copy()
    params_no_renovation.include_renovation = False
    params_no_renovation.include_foreman = False
    fixed_costs_no_reno, breakdown = _calculate_fixed_costs(params_no_renovation, area_total, 0)

    after_tax_rate = 1 - params.tax_rate

    # Цена интереса рассчитывается для НАШЕЙ минимальной доходности 4%/мес
    # НЕ удваиваем - партнёр получает остаток, его доходность не гарантируется
    base_target = params.monthly_rate * params.project_period_months  # 4% × 3 мес = 12%

    multiplier_expense = 1 + base_target
    divisor = after_tax_rate + base_target

    interest_price = (base_sale_price * after_tax_rate - fixed_costs_no_reno * multiplier_expense) / divisor

    if params.include_financing and params.financing_rate > 0:
        financing_cost = interest_price * params.financing_rate / (1 - params.financing_rate)
        fixed_costs_no_reno += financing_cost
        breakdown["Кредитование"] = financing_cost
        interest_price = (base_sale_price * after_tax_rate - fixed_costs_no_reno * multiplier_expense) / divisor

    # Проверка минималки (без ремонта)
    total_investment_no_reno = interest_price + fixed_costs_no_reno
    gross_profit_no_reno = base_sale_price - interest_price
    tax_amount_no_reno = gross_profit_no_reno * params.tax_rate
    expected_profit_no_reno = gross_profit_no_reno - fixed_costs_no_reno - tax_amount_no_reno

    # Наша минимальная прибыль = 4%/мес от вложений
    min_our_profit = total_investment_no_reno * params.monthly_rate * params.project_period_months

    # Если наша прибыль < 1 млн при коротком сроке, пересчитываем
    if params.project_period_months < 3 and min_our_profit < params.min_profit:
        min_our_profit = params.min_profit
        interest_price = base_sale_price - (min_our_profit + fixed_costs_no_reno) / after_tax_rate

    # Валидация: цена интереса должна быть положительной
    if interest_price <= 0:
        raise ValueError(f"Расходы слишком высоки для целевой доходности. Цена интереса: {interest_price:,.0f} ₽")

    interest_price_per_sqm = interest_price / area_total

    # Теперь добавляем ремонт для расчёта прибыли
    renovation_cost = None
    renovation_bonus = None
    renovation_profit = None
    final_sale_price = base_sale_price
    total_fixed_costs = fixed_costs_no_reno

    if params.include_renovation:
        renovation_cost = params.renovation_per_sqm * area_total
        renovation_bonus = renovation_cost * 1.8  # Увеличение цены от ремонта (×1.8)
        final_sale_price = base_sale_price + renovation_bonus
        total_fixed_costs += renovation_cost
        breakdown["Ремонт"] = renovation_cost
        # Профит от ремонта = бонус - затраты
        renovation_profit = renovation_bonus - renovation_cost
        if params.include_foreman:
            total_fixed_costs += params.foreman_fee
            breakdown["Прораб"] = params.foreman_fee

    # Прибыль с учётом ремонта
    gross_profit = final_sale_price - interest_price
    tax_amount = gross_profit * params.tax_rate
    expected_profit = gross_profit - total_fixed_costs - tax_amount
    breakdown["Налог 6%"] = tax_amount

    total_investment = interest_price + total_fixed_costs

    # Наша минимальная доля = 4%/мес от вложений
    our_min_profit = total_investment * params.monthly_rate * params.project_period_months

    # Расчёт долей: 50/50, НО наша доля не менее 4%/мес
    fifty_fifty_share = expected_profit * (1 - params.partner_split)  # 50% от прибыли

    if fifty_fifty_share >= our_min_profit:
        # Прибыль достаточная - делим 50/50
        our_profit = fifty_fifty_share
        partner_profit = expected_profit * params.partner_split
    else:
        # Прибыль низкая - мы берём свои 4%/мес, партнёр получает остаток
        our_profit = our_min_profit
        partner_profit = max(0, expected_profit - our_profit)

    actual_profit_rate = expected_profit / total_investment if total_investment > 0 else 0
    monthly_profit_rate = actual_profit_rate / params.project_period_months
    our_monthly_rate = (our_profit / total_investment) / params.project_period_months if total_investment > 0 else 0

    return InterestPriceResult(
        project_type=ProjectType.PARTNER.value,
        project_type_name="Партнерский 50/50",
        market_price=market_price,
        market_price_per_sqm=market_price_per_sqm,
        area_total=area_total,
        sale_price_after_renovation=final_sale_price if params.include_renovation else None,
        renovation_bonus=renovation_bonus,
        interest_price=interest_price,
        interest_price_per_sqm=interest_price_per_sqm,
        expected_sale_price=final_sale_price,
        expected_sale_per_sqm=final_sale_price / area_total,
        total_costs=total_fixed_costs + tax_amount,
        fixed_costs=total_fixed_costs,
        variable_costs=tax_amount,
        renovation_cost=renovation_cost,
        renovation_profit=renovation_profit,
        expected_profit=expected_profit,
        our_profit=our_profit,
        partner_profit=partner_profit,
        profit_rate=actual_profit_rate,
        monthly_profit_rate=monthly_profit_rate,
        our_monthly_rate=our_monthly_rate,
        project_months=params.project_period_months,
        cost_breakdown=breakdown
    )


def calculate_partner_flip(market_price: float, area_total: float, params: InvestmentParams) -> InterestPriceResult:
    """
    Тип 3: ПАРТНЕРСКИЙ ФЛИП
    - Партнерский + ремонт
    - Цена интереса НЕ зависит от ремонта
    - Наша доля не менее 4%/мес, партнёр получает остаток
    - Цена продажи увеличивается на стоимость ремонта × 1.8
    """
    market_price_per_sqm = market_price / area_total
    base_sale_price = market_price * (1 - params.bargain_discount)

    # ВАЖНО: Расчет цены интереса БЕЗ учёта ремонта
    params_no_renovation = params.model_copy()
    params_no_renovation.include_renovation = False
    params_no_renovation.include_foreman = False
    fixed_costs_no_reno, breakdown = _calculate_fixed_costs(params_no_renovation, area_total, 0)

    after_tax_rate = 1 - params.tax_rate
    # НЕ удваиваем - наша доля гарантирована, партнёр получает остаток
    base_target = params.monthly_rate * params.project_period_months  # 4% × 6 мес = 24%

    multiplier_expense = 1 + base_target
    divisor = after_tax_rate + base_target

    # Цена интереса рассчитывается БЕЗ ремонта
    interest_price = (base_sale_price * after_tax_rate - fixed_costs_no_reno * multiplier_expense) / divisor

    if params.include_financing and params.financing_rate > 0:
        financing_cost = interest_price * params.financing_rate / (1 - params.financing_rate)
        fixed_costs_no_reno += financing_cost
        breakdown["Кредитование"] = financing_cost
        interest_price = (base_sale_price * after_tax_rate - fixed_costs_no_reno * multiplier_expense) / divisor

    # Валидация: цена интереса должна быть положительной
    if interest_price <= 0:
        raise ValueError(f"Расходы слишком высоки для целевой доходности. Цена интереса: {interest_price:,.0f} ₽")

    interest_price_per_sqm = interest_price / area_total

    # Теперь добавляем ремонт для расчёта прибыли
    renovation_cost = None
    renovation_bonus = None
    renovation_profit = None
    final_sale_price = base_sale_price
    total_fixed_costs = fixed_costs_no_reno

    if params.include_renovation:
        renovation_cost = params.renovation_per_sqm * area_total
        renovation_bonus = renovation_cost * 1.8  # Увеличение цены от ремонта (×1.8)
        final_sale_price = base_sale_price + renovation_bonus
        total_fixed_costs += renovation_cost
        breakdown["Ремонт"] = renovation_cost
        # Профит от ремонта = бонус - затраты
        renovation_profit = renovation_bonus - renovation_cost
        if params.include_foreman:
            total_fixed_costs += params.foreman_fee
            breakdown["Прораб"] = params.foreman_fee

    # Прибыль с учётом ремонта
    gross_profit = final_sale_price - interest_price
    tax_amount = gross_profit * params.tax_rate
    expected_profit = gross_profit - total_fixed_costs - tax_amount
    breakdown["Налог 6%"] = tax_amount

    total_investment = interest_price + total_fixed_costs

    # Наша минимальная доля = 4%/мес от вложений
    our_min_profit = total_investment * params.monthly_rate * params.project_period_months

    # Расчёт долей: 50/50, НО наша доля не менее 4%/мес
    fifty_fifty_share = expected_profit * (1 - params.partner_split)

    if fifty_fifty_share >= our_min_profit:
        our_profit = fifty_fifty_share
        partner_profit = expected_profit * params.partner_split
    else:
        our_profit = our_min_profit
        partner_profit = max(0, expected_profit - our_profit)

    actual_profit_rate = expected_profit / total_investment if total_investment > 0 else 0
    monthly_profit_rate = actual_profit_rate / params.project_period_months
    our_monthly_rate = (our_profit / total_investment) / params.project_period_months if total_investment > 0 else 0

    return InterestPriceResult(
        project_type=ProjectType.PARTNER_FLIP.value,
        project_type_name="Партнерский Флип",
        market_price=market_price,
        market_price_per_sqm=market_price_per_sqm,
        area_total=area_total,
        sale_price_after_renovation=final_sale_price if params.include_renovation else None,
        renovation_bonus=renovation_bonus,
        interest_price=interest_price,
        interest_price_per_sqm=interest_price_per_sqm,
        expected_sale_price=final_sale_price,
        expected_sale_per_sqm=final_sale_price / area_total,
        total_costs=total_fixed_costs + tax_amount,
        fixed_costs=total_fixed_costs,
        variable_costs=tax_amount,
        renovation_cost=renovation_cost,
        expected_profit=expected_profit,
        our_profit=our_profit,
        partner_profit=partner_profit,
        profit_rate=actual_profit_rate,
        monthly_profit_rate=monthly_profit_rate,
        our_monthly_rate=our_monthly_rate,
        renovation_profit=renovation_profit,
        project_months=params.project_period_months,
        cost_breakdown=breakdown
    )


def calculate_bank_flip(market_price: float, area_total: float, params: InvestmentParams) -> InterestPriceResult:
    """
    Тип 4: БАНКОВСКИЙ ФЛИП
    - Ипотека: 2%/мес (затраты по проекту)
    - Прибыль после ипотеки делится 50/50
    - Цена интереса НЕ зависит от ремонта
    - Ремонт влияет только на цену продажи и прибыль
    """
    market_price_per_sqm = market_price / area_total
    base_sale_price = market_price * (1 - params.bargain_discount)

    # ВАЖНО: Расчет цены интереса БЕЗ учёта ремонта
    params_clean = params.model_copy()
    params_clean.include_renovation = False
    params_clean.include_foreman = False
    params_clean.include_financing = False
    fixed_costs_no_reno, breakdown = _calculate_fixed_costs(params_clean, area_total, 0)

    after_tax_rate = 1 - params.tax_rate

    # Цена интереса БЕЗ ремонта (для ипотечных расчетов)
    initial_target = 0.24  # 24% целевая
    divisor = after_tax_rate + initial_target
    interest_price = (base_sale_price * after_tax_rate - fixed_costs_no_reno * (1 + initial_target)) / divisor

    # Валидация: цена интереса должна быть положительной
    if interest_price <= 0:
        raise ValueError(f"Расходы слишком высоки для целевой доходности. Цена интереса: {interest_price:,.0f} ₽")

    # Ипотечные расчеты (на основе цены интереса без ремонта)
    mortgage_amount = interest_price * params.ltv
    mortgage_monthly = mortgage_amount * params.mortgage_rate
    mortgage_total_interest = mortgage_monthly * params.project_period_months
    mortgage_prepayment = mortgage_monthly * params.mortgage_prepay_months
    mortgage_issue = mortgage_amount * params.mortgage_issue_fee

    # Добавляем ипотечные расходы
    fixed_costs_no_reno += mortgage_total_interest
    breakdown["Проценты по ипотеке"] = mortgage_total_interest
    fixed_costs_no_reno += mortgage_issue
    breakdown["Комиссия за выдачу"] = mortgage_issue

    interest_price_per_sqm = interest_price / area_total

    # Теперь добавляем ремонт для расчёта прибыли
    renovation_cost = None
    renovation_bonus = None
    renovation_profit = None
    final_sale_price = base_sale_price
    total_fixed_costs = fixed_costs_no_reno

    if params.include_renovation:
        renovation_cost = params.renovation_per_sqm * area_total
        renovation_bonus = renovation_cost * 1.8  # Увеличение цены от ремонта (×1.8)
        final_sale_price = base_sale_price + renovation_bonus
        total_fixed_costs += renovation_cost
        breakdown["Ремонт"] = renovation_cost
        # Профит от ремонта = бонус - затраты
        renovation_profit = renovation_bonus - renovation_cost
        if params.include_foreman:
            total_fixed_costs += params.foreman_fee
            breakdown["Прораб"] = params.foreman_fee

    # Прибыль с учётом ремонта
    gross_profit = final_sale_price - interest_price
    tax_amount = gross_profit * params.tax_rate
    expected_profit = gross_profit - total_fixed_costs - tax_amount
    breakdown["Налог 6%"] = tax_amount

    total_investment = interest_price + total_fixed_costs

    # Наша минимальная доля = 4%/мес от вложений (ипотека: 2%/мес)
    our_min_profit = total_investment * params.mortgage_rate * params.project_period_months

    # Делёжка прибыли: 50/50, НО наша доля не менее 2%/мес
    if renovation_profit:
        profit_to_split = expected_profit - renovation_profit
        fifty_fifty_share = profit_to_split * (1 - params.partner_split)

        if fifty_fifty_share + renovation_profit >= our_min_profit:
            partner_profit = profit_to_split * params.partner_split
            our_profit = fifty_fifty_share + renovation_profit
        else:
            our_profit = our_min_profit
            partner_profit = max(0, expected_profit - our_profit)
    else:
        fifty_fifty_share = expected_profit * (1 - params.partner_split)

        if fifty_fifty_share >= our_min_profit:
            our_profit = fifty_fifty_share
            partner_profit = expected_profit * params.partner_split
        else:
            our_profit = our_min_profit
            partner_profit = max(0, expected_profit - our_profit)

    actual_profit_rate = expected_profit / total_investment if total_investment > 0 else 0
    monthly_profit_rate = actual_profit_rate / params.project_period_months
    our_monthly_rate = (our_profit / total_investment) / params.project_period_months if total_investment > 0 else 0

    return InterestPriceResult(
        project_type=ProjectType.BANK_FLIP.value,
        project_type_name="Банковский Флип",
        market_price=market_price,
        market_price_per_sqm=market_price_per_sqm,
        area_total=area_total,
        sale_price_after_renovation=final_sale_price if params.include_renovation else None,
        renovation_bonus=renovation_bonus,
        interest_price=interest_price,
        interest_price_per_sqm=interest_price_per_sqm,
        expected_sale_price=final_sale_price,
        expected_sale_per_sqm=final_sale_price / area_total,
        total_costs=total_fixed_costs + tax_amount,
        fixed_costs=total_fixed_costs,
        variable_costs=tax_amount,
        renovation_cost=renovation_cost,
        expected_profit=expected_profit,
        our_profit=our_profit,
        partner_profit=partner_profit,
        profit_rate=actual_profit_rate,
        monthly_profit_rate=monthly_profit_rate,
        our_monthly_rate=our_monthly_rate,
        mortgage_amount=mortgage_amount,
        mortgage_monthly_payment=mortgage_monthly,
        mortgage_total_interest=mortgage_total_interest,
        mortgage_prepayment=mortgage_prepayment,
        mortgage_issue_cost=mortgage_issue,
        renovation_profit=renovation_profit,
        project_months=params.project_period_months,
        cost_breakdown=breakdown
    )


def calculate_interest_price(
    market_price: float,
    area_total: float,
    params: Optional[InvestmentParams] = None
) -> InterestPriceResult:
    """
    Основная функция расчета цены интереса.
    Выбирает метод расчета в зависимости от типа проекта.
    """
    if params is None:
        params = InvestmentParams()

    # Выбор метода расчета по типу проекта
    if params.project_type == ProjectType.PARTNER:
        return calculate_partner(market_price, area_total, params)
    elif params.project_type == ProjectType.PARTNER_FLIP:
        return calculate_partner_flip(market_price, area_total, params)
    elif params.project_type == ProjectType.BANK_FLIP:
        return calculate_bank_flip(market_price, area_total, params)
    else:
        # По умолчанию - собственный проект
        return calculate_own(market_price, area_total, params)


def calculate_all_project_types(
    market_price: float,
    area_total: float,
    params: Optional[InvestmentParams] = None
) -> Dict[str, InterestPriceResult]:
    """
    Рассчитать цену интереса для всех 4 типов проектов.
    Полезно для сравнения.
    """
    if params is None:
        params = InvestmentParams()

    results = {}

    for project_type in ProjectType:
        p = params.model_copy()
        p.project_type = project_type

        # Для флипов включаем ремонт
        if project_type in [ProjectType.PARTNER_FLIP, ProjectType.BANK_FLIP]:
            p.include_renovation = True

        results[project_type.value] = calculate_interest_price(market_price, area_total, p)

    return results


# Для обратной совместимости
def calculate_interest_price_simple(
    market_price_per_sqm: float,
    area_total: float,
    bargain_discount: float = 0.07,
    target_profit_rate: float = 0.12
) -> float:
    """Упрощенный расчет цены интереса за м²."""
    avg_fixed_per_sqm = (50000 + 4000 + 200000) / area_total + 1500 + (11500 * 3) / area_total
    sale_price_per_sqm = market_price_per_sqm * (1 - bargain_discount)
    interest_price_per_sqm = (sale_price_per_sqm - avg_fixed_per_sqm) / (1 + target_profit_rate / 0.94)
    return max(interest_price_per_sqm, 0)
