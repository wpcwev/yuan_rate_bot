import asyncio
import logging
from decimal import Decimal, InvalidOperation

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from config import Settings, load_settings
from rate_service import RateService, RateSnapshot, fmt_money, fmt_rate, parse_decimal
from site_export import build_site_preview, build_site_rates, get_usdt_rates, write_site_rates


router = Router()
settings: Settings
rate_service: RateService


def is_allowed(message: Message) -> bool:
    if not settings.admin_ids:
        return True
    user_id = message.from_user.id if message.from_user else None
    return bool(user_id and user_id in settings.admin_ids)


async def guard(message: Message) -> bool:
    if is_allowed(message):
        return True
    await message.reply("Нет доступа. Попроси владельца добавить твой Telegram ID в ADMIN_IDS.")
    return False


def build_rate_text(snapshot: RateSnapshot) -> str:
    usdt_buy, usdt_sell = get_usdt_rates(snapshot, settings)
    usdt_cny_site = snapshot.coinbase_cny + settings.usdt_cny_offset
    return (
        "Расчет курса RUB/CNY\n\n"
        f"Rapira {snapshot.rapira_symbol} ({snapshot.rapira_field}): {fmt_money(snapshot.rapira_raw)}\n"
        f"Надбавка к Rapira для CNY: +{fmt_rate(settings.rapira_markup_percent, '0.01')}%\n"
        f"Расчетный USDT/RUB для CNY: {fmt_money(snapshot.rapira_adjusted)}\n"
        f"Coinbase USDT/CNY: {fmt_rate(snapshot.coinbase_cny)}\n\n"
        f"Себестоимость 1 CNY: {fmt_money(snapshot.cny_cost_rub)} RUB\n"
        f"Доп. маржа: +{fmt_money(settings.public_markup_rub)} RUB/CNY\n"
        f"Базовый курс CNY: {fmt_money(snapshot.public_rate)} RUB/CNY\n\n"
        f"Купить USDT: {fmt_money(usdt_buy)} RUB\n"
        f"Продать USDT: {fmt_money(usdt_sell)} RUB\n"
        f"USDT/CNY для калькулятора: {fmt_money(usdt_cny_site)}"
    )


def build_tiers_text(snapshot: RateSnapshot) -> str:
    lines = ["Курс юаня по суммам:", ""]
    payload = build_site_rates(snapshot, settings, rate_service)

    for tier in payload["cny"]["tiers"]:
        lines.append(f"от {tier['from']}¥ - {fmt_money(Decimal(str(tier['rate'])))} ₽/¥")

    usdt_buy, usdt_sell = get_usdt_rates(snapshot, settings)
    lines.extend(
        [
            "",
            f"Себестоимость: {fmt_money(snapshot.cny_cost_rub)} ₽/¥",
            f"Базовый курс с маржей: {fmt_money(snapshot.public_rate)} ₽/¥",
            "",
            f"Rapira USDT/RUB: {fmt_money(snapshot.rapira_raw)}",
            f"Расчетный USDT/RUB для CNY: {fmt_money(snapshot.rapira_adjusted)}",
            f"USDT/CNY Coinbase: {fmt_rate(snapshot.coinbase_cny)}",
            f"USDT/CNY для калькулятора: {fmt_money(Decimal(str(payload['usdt']['cnyRate'])))}",
            "",
            f"Купить USDT: {fmt_money(usdt_buy)} ₽",
            f"Продать USDT: {fmt_money(usdt_sell)} ₽",
        ]
    )
    return "\n".join(lines)


@router.message(Command("start", "help"))
async def cmd_help(message: Message):
    if not await guard(message):
        return

    await message.reply(
        "Я считаю курс RUB/CNY и могу обновлять rates.json для сайта.\n\n"
        "Команды:\n"
        "/rate - подробный расчет\n"
        "/rates - курс лесенкой по суммам\n"
        "/calc <rapira> <cny> - подробный расчет вручную\n"
        "/rates_calc <rapira> <cny> - лесенка вручную\n"
        "/site_preview - показать данные для сайта\n"
        "/site_update - обновить rates.json на сайте\n"
        "/settings - показать настройки\n"
        "/formula - показать формулу\n"
        "/myid - показать твой Telegram ID\n\n"
        "Пример: /rates_calc 74.83 6.7754"
    )


@router.message(Command("rate"))
async def cmd_rate(message: Message):
    if not await guard(message):
        return

    waiting = await message.reply("Считаю курс: беру Rapira и Coinbase...")
    try:
        snapshot = await rate_service.calculate_auto()
    except Exception:
        logging.exception("Failed to calculate rate")
        await waiting.edit_text("Не смог получить курсы из API. Проверь доступность Rapira и Coinbase.")
        return

    await waiting.edit_text(build_rate_text(snapshot))


@router.message(Command("rates", "post"))
async def cmd_rates(message: Message):
    if not await guard(message):
        return

    waiting = await message.reply("Считаю курсы по суммам: беру Rapira и Coinbase...")
    try:
        snapshot = await rate_service.calculate_auto()
    except Exception:
        logging.exception("Failed to calculate rate tiers")
        await waiting.edit_text("Не смог получить курсы из API. Проверь доступность Rapira и Coinbase.")
        return

    await waiting.edit_text(build_tiers_text(snapshot))


@router.message(Command("rates_calc", "post_calc"))
async def cmd_rates_calc(message: Message, command: CommandObject):
    if not await guard(message):
        return

    if not command.args:
        await message.reply(
            "Использование: /rates_calc <rapira_usdt_rub> <coinbase_usdt_cny>\n"
            "Пример: /rates_calc 74.83 6.7754"
        )
        return

    parts = command.args.split()
    if len(parts) != 2:
        await message.reply(
            "Нужно два числа: Rapira USDT/RUB и Coinbase USDT/CNY.\n"
            "Пример: /rates_calc 74.83 6.7754"
        )
        return

    try:
        rapira_raw = parse_decimal(parts[0])
        coinbase_cny = parse_decimal(parts[1])
        snapshot = rate_service.calculate(rapira_raw=rapira_raw, coinbase_cny=coinbase_cny)
    except (InvalidOperation, ValueError) as exc:
        await message.reply(f"Не смог посчитать курсы: {exc}")
        return

    await message.reply(build_tiers_text(snapshot))


@router.message(Command("calc"))
async def cmd_calc(message: Message, command: CommandObject):
    if not await guard(message):
        return

    if not command.args:
        await message.reply(
            "Использование: /calc <rapira_usdt_rub> <coinbase_usdt_cny>\n"
            "Пример: /calc 74.83 6.7754"
        )
        return

    parts = command.args.split()
    if len(parts) != 2:
        await message.reply(
            "Нужно два числа: Rapira USDT/RUB и Coinbase USDT/CNY.\n"
            "Пример: /calc 74.83 6.7754"
        )
        return

    try:
        rapira_raw = parse_decimal(parts[0])
        coinbase_cny = parse_decimal(parts[1])
        snapshot = rate_service.calculate(rapira_raw=rapira_raw, coinbase_cny=coinbase_cny)
    except (InvalidOperation, ValueError) as exc:
        await message.reply(f"Не смог посчитать: {exc}")
        return

    await message.reply(build_rate_text(snapshot))


@router.message(Command("site_preview"))
async def cmd_site_preview(message: Message):
    if not await guard(message):
        return

    waiting = await message.reply("Собираю данные для сайта...")
    try:
        snapshot = await rate_service.calculate_auto()
    except Exception:
        logging.exception("Failed to build site preview")
        await waiting.edit_text("Не смог получить курсы из API.")
        return

    await waiting.edit_text(build_site_preview(snapshot, settings, rate_service))


@router.message(Command("site_update"))
async def cmd_site_update(message: Message):
    if not await guard(message):
        return

    waiting = await message.reply("Обновляю курсы на сайте...")
    try:
        snapshot = await rate_service.calculate_auto()
        payload = build_site_rates(snapshot, settings, rate_service)
        target = write_site_rates(payload, settings.site_rates_path)
    except Exception:
        logging.exception("Failed to update site rates")
        await waiting.edit_text("Не смог обновить сайт. Проверь API и права на rates.json.")
        return

    await waiting.edit_text(f"Готово. Обновил файл:\n{target}")


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    if not await guard(message):
        return

    admin_mode = "включено" if settings.admin_ids else "выключено"
    await message.reply(
        "Настройки:\n\n"
        f"Rapira URL: {settings.rapira_rates_url}\n"
        f"Rapira symbol: {settings.rapira_symbol}\n"
        f"Rapira field: {settings.rapira_price_field}\n"
        f"Coinbase base/quote: {settings.coinbase_base_currency}/{settings.coinbase_quote_currency}\n"
        f"Надбавка к Rapira для CNY: +{fmt_rate(settings.rapira_markup_percent, '0.01')}%\n"
        f"Доп. маржа CNY: +{fmt_money(settings.public_markup_rub)} RUB/CNY\n"
        f"Ступени: {settings.post_tiers}\n"
        f"Малая ступень CNY: лучший тариф +{fmt_money(settings.check_markup_rub)}, округление {settings.check_round_to}\n"
        f"USDT offsets: buy {fmt_money(settings.usdt_buy_offset_rub)}, sell {fmt_money(settings.usdt_sell_offset_rub)}\n"
        f"USDT/CNY offset: {fmt_money(settings.usdt_cny_offset)}\n"
        f"Минимумы: RUB->USDT {fmt_money(settings.min_rub_to_usdt_rub, '0.01')} RUB, "
        f"USDT->RUB {fmt_money(settings.min_usdt_to_rub, '0.01')} USDT, "
        f"USDT->CNY {fmt_money(settings.min_usdt_to_cny, '0.01')} USDT\n"
        f"Site rates path: {settings.site_rates_path}\n"
        f"Округление: {settings.round_to}, вверх: {settings.round_up}\n"
        f"Ограничение по ADMIN_IDS: {admin_mode}"
    )


@router.message(Command("formula"))
async def cmd_formula(message: Message):
    if not await guard(message):
        return

    await message.reply(
        "Формулы:\n\n"
        "CNY:\n"
        "adjusted_usdt_rub = rapira_usdt_rub * (1 + RAPIRA_MARKUP_PERCENT / 100)\n"
        "cny_cost = adjusted_usdt_rub / coinbase_usdt_cny\n"
        "public_rate = round_up(cny_cost + PUBLIC_MARKUP_RUB)\n\n"
        "USDT:\n"
        "buy_usdt = rapira_usdt_rub + USDT_BUY_OFFSET_RUB\n"
        "sell_usdt = rapira_usdt_rub + USDT_SELL_OFFSET_RUB\n"
        "site_usdt_cny = coinbase_usdt_cny + USDT_CNY_OFFSET\n\n"
        "Малая ступень CNY:\n"
        "rate_from_500 = ceil_to_0.10(rate_from_30000 + CHECK_MARKUP_RUB)\n\n"
        "Пример: Rapira 74.5 -> купить USDT 78.5, продать USDT 71.5."
    )


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    user_id = message.from_user.id if message.from_user else None
    await message.reply(f"Твой Telegram ID: {user_id}")


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    global settings, rate_service
    settings = load_settings()
    rate_service = RateService(settings)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=None),
    )
    dp = Dispatcher()
    dp.include_router(router)

    logging.info("yuan_rate_bot started")
    await dp.start_polling(bot, allowed_updates=["message"])


if __name__ == "__main__":
    asyncio.run(main())
