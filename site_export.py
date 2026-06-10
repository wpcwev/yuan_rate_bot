import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

from config import Settings
from rate_service import RateService, RateSnapshot, fmt_money, fmt_rate


def _decimal_number(value: Decimal, places: str = "0.01") -> float:
    return float(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


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


def build_site_rates(snapshot: RateSnapshot, settings: Settings, rate_service: RateService) -> dict:
    cny_tiers = []
    for min_amount, tier_markup in sorted(settings.post_tiers, reverse=True):
        tier_rate = rate_service.round_public_rate(snapshot.public_rate + tier_markup)
        cny_tiers.append({"from": min_amount, "rate": _decimal_number(tier_rate)})

    usdt_buy, usdt_sell = get_usdt_rates(snapshot, settings)
    usdt_cny_regular = settings.usdt_cny_regular or snapshot.coinbase_cny
    usdt_cny_big = settings.usdt_cny_big or snapshot.coinbase_cny

    return {
        "updatedAt": datetime.now(ZoneInfo("Europe/Moscow")).isoformat(timespec="seconds"),
        "cny": {
            "tiers": cny_tiers,
            "checkRate": _decimal_number(settings.check_rate_rub),
            "minAmount": settings.min_exchange_cny,
            "trialAmount": settings.trial_exchange_cny,
        },
        "usdt": {
            "marketRub": _decimal_number(snapshot.rapira_raw),
            "buyRub": _decimal_number(usdt_buy),
            "sellRub": _decimal_number(usdt_sell),
            "cnyRegular": _decimal_number(usdt_cny_regular),
            "cnyBig": _decimal_number(usdt_cny_big),
            "cnyBigFrom": settings.usdt_cny_big_from,
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
            f"USDT/CNY: {fmt_rate(Decimal(str(payload['usdt']['cnyRegular'])))}",
            "",
            f"Файл сайта: {settings.site_rates_path}",
        ]
    )
    return "\n".join(lines)
