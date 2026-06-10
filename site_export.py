import json
from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

from config import Settings
from rate_service import RateService, RateSnapshot, fmt_money, fmt_rate


def _decimal_number(value: Decimal, places: str = "0.01") -> float:
    return float(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def _round_up_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _telegram_url(username: str) -> str:
    return f"https://t.me/{username.lstrip('@')}"


def get_usdt_rates(snapshot: RateSnapshot, settings: Settings) -> tuple[Decimal, Decimal]:
    buy_rate = settings.usdt_buy_rate_rub
    if buy_rate is None:
        buy_rate = snapshot.rapira_raw + settings.usdt_buy_offset_rub

    sell_rate = settings.usdt_sell_rate_rub
    if sell_rate is None:
        sell_rate = snapshot.rapira_raw + settings.usdt_sell_offset_rub

    return buy_rate, sell_rate


def build_cny_tiers(
    snapshot: RateSnapshot, settings: Settings, rate_service: RateService
) -> tuple[list[dict], Decimal]:
    tier_rates: list[tuple[int, Decimal]] = []
    best_tier_rate: Decimal | None = None
    best_tier_min = -1

    for min_amount, tier_markup in settings.post_tiers:
        tier_rate = rate_service.round_public_rate(snapshot.public_rate + tier_markup)
        if min_amount > best_tier_min:
            best_tier_min = min_amount
            best_tier_rate = tier_rate
        if min_amount != settings.min_exchange_cny:
            tier_rates.append((min_amount, tier_rate))

    if best_tier_rate is None:
        best_tier_rate = snapshot.public_rate

    check_rate = _round_up_to_step(
        best_tier_rate + settings.check_markup_rub,
        settings.check_round_to,
    )
    tier_rates.append((settings.min_exchange_cny, check_rate))

    cny_tiers = [
        {"from": min_amount, "rate": _decimal_number(tier_rate)}
        for min_amount, tier_rate in sorted(tier_rates, reverse=True)
    ]
    return cny_tiers, check_rate


def build_site_rates(snapshot: RateSnapshot, settings: Settings, rate_service: RateService) -> dict:
    cny_tiers, check_rate = build_cny_tiers(snapshot, settings, rate_service)
    usdt_buy, usdt_sell = get_usdt_rates(snapshot, settings)
    usdt_cny_rate = snapshot.coinbase_cny + settings.usdt_cny_offset
    if usdt_cny_rate <= 0:
        raise ValueError("USDT/CNY site rate must be greater than zero.")

    return {
        "updatedAt": datetime.now(ZoneInfo("Europe/Moscow")).isoformat(timespec="seconds"),
        "cny": {
            "tiers": cny_tiers,
            "checkRate": _decimal_number(check_rate),
            "minAmount": settings.min_exchange_cny,
            "trialAmount": settings.trial_exchange_cny,
        },
        "usdt": {
            "marketRub": _decimal_number(snapshot.rapira_raw),
            "buyRub": _decimal_number(usdt_buy),
            "sellRub": _decimal_number(usdt_sell),
            "cnyMarket": _decimal_number(snapshot.coinbase_cny, "0.0001"),
            "cnyRate": _decimal_number(usdt_cny_rate),
            "cnyRegular": _decimal_number(usdt_cny_rate),
            "cnyBig": _decimal_number(usdt_cny_rate),
            "cnyBigFrom": settings.usdt_cny_big_from,
            "minBuyRub": _decimal_number(settings.min_rub_to_usdt_rub),
            "minSellUsdt": _decimal_number(settings.min_usdt_to_rub),
            "minCnyUsdt": _decimal_number(settings.min_usdt_to_cny),
        },
        "contacts": {
            "telegram": _telegram_url(settings.contact_username),
            "telegramLabel": settings.contact_username,
            "reviews": _telegram_url(settings.reviews_username),
            "reviewsLabel": settings.reviews_username,
            "chat": _telegram_url(settings.chat_username),
            "chatLabel": settings.chat_username,
            "max": settings.max_url,
        },
    }


def write_site_rates(payload: dict, path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def build_site_preview(snapshot: RateSnapshot, settings: Settings, rate_service: RateService) -> str:
    payload = build_site_rates(snapshot, settings, rate_service)
    lines = ["Данные для сайта:", ""]

    for tier in payload["cny"]["tiers"]:
        lines.append(f"от {tier['from']}¥ - {fmt_money(Decimal(str(tier['rate'])))} ₽/¥")

    lines.extend(
        [
            "",
            f"USDT рынок Rapira: {fmt_money(snapshot.rapira_raw)} ₽",
            f"Купить USDT: {fmt_money(Decimal(str(payload['usdt']['buyRub'])))} ₽",
            f"Продать USDT: {fmt_money(Decimal(str(payload['usdt']['sellRub'])))} ₽",
            f"USDT/CNY Coinbase: {fmt_rate(snapshot.coinbase_cny)}",
            f"USDT/CNY для сайта: {fmt_rate(Decimal(str(payload['usdt']['cnyRate'])))}",
            "",
            f"Файл сайта: {settings.site_rates_path}",
        ]
    )
    return "\n".join(lines)
