from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from config import Settings
from rate_service import RateSnapshot


WEEKDAYS_RU = {
    0: "понедельник",
    1: "вторник",
    2: "среда",
    3: "четверг",
    4: "пятница",
    5: "суббота",
    6: "воскресенье",
}


def _money(value: Decimal, places: str = "0.01") -> str:
    return str(value.quantize(Decimal(places), rounding=ROUND_HALF_UP)).replace(".", ",")


def _whole(value: Decimal) -> str:
    return str(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _ceil_to(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def build_exchange_post(snapshot: RateSnapshot, settings: Settings, now: datetime | None = None) -> str:
    now = now or datetime.now(ZoneInfo("Europe/Moscow"))
    date_text = now.strftime("%d.%m")
    weekday = WEEKDAYS_RU[now.weekday()]

    base_rate = snapshot.public_rate
    lines = [
        f"💎Пополнение alipay, wechat, карты Китая, актуальный курс на {date_text}, {weekday} 🇷🇺🇨🇳",
        "",
    ]

    for min_amount, tier_markup in settings.post_tiers:
        tier_rate = _ceil_to(base_rate + tier_markup, settings.round_to)
        lines.append(f"1¥ - {_money(tier_rate)}₽ от {min_amount}¥")

    buy_rate = settings.usdt_buy_rate_rub or snapshot.rapira_raw
    sell_rate = settings.usdt_sell_rate_rub or snapshot.rapira_adjusted
    usdt_cny_regular = settings.usdt_cny_regular or snapshot.coinbase_cny
    usdt_cny_big = settings.usdt_cny_big or snapshot.coinbase_cny

    lines.extend(
        [
            "",
            f"Чеки от 500-1000¥ продаем по курсу {_money(settings.check_rate_rub)}₽📌",
            "",
            (
                f"Работаем от {settings.min_exchange_cny}¥, для новых клиентов "
                f"возможен пробный обмен от {settings.trial_exchange_cny}¥🎁"
            ),
            "",
            "Курс USDT/RUB💸",
            f"Покупка {_whole(buy_rate)}₽",
            f"Продажа {_whole(sell_rate)}₽",
            "Работаем без доп комиссий❗️",
            "",
            "Оплату принимаем на карту любого банка РФ и по сбп💸💸💸",
            "",
            (
                f"Курс для оплаты в usdt {_money(usdt_cny_regular)}, "
                f"от {settings.usdt_cny_big_from}¥ - {_money(usdt_cny_big)}💸"
            ),
            "",
            "❗️Номер карты для перевода уточняйте перед каждым обменом❗️",
            "",
            "Писать ",
            f"{settings.contact_username}💬",
            "",
            "Отзывы",
            f"{settings.reviews_username}🤝",
            "",
            "Мы в MAX💬",
            "",
            "Чат: ",
            f"{settings.chat_username}⚡️",
        ]
    )

    return "\n".join(lines)
