import asyncio
import logging
from decimal import Decimal, InvalidOperation

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from config import Settings, load_settings
from post_template import build_exchange_post
from rate_service import RateService, RateSnapshot, fmt_money, fmt_rate, parse_decimal


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
    return (
        "Расчет курса RUB/CNY\n\n"
        f"Rapira {snapshot.rapira_symbol} ({snapshot.rapira_field}): {fmt_money(snapshot.rapira_raw)}\n"
        f"Надбавка к Rapira: +{fmt_rate(settings.rapira_markup_percent, '0.01')}%\n"
        f"Расчетный USDT/RUB: {fmt_money(snapshot.rapira_adjusted)}\n"
        f"Coinbase USDT/CNY: {fmt_rate(snapshot.coinbase_cny)}\n\n"
        f"Себестоимость 1 CNY: {fmt_money(snapshot.cny_cost_rub)} RUB\n"
        f"Доп. наценка: +{fmt_money(settings.public_markup_rub)} RUB/CNY\n"
        f"Курс к публикации: {fmt_money(snapshot.public_rate)} RUB/CNY"
    )


@router.message(Command("start", "help"))
async def cmd_help(message: Message):
    if not await guard(message):
        return

    await message.reply(
        "Я считаю курс RUB/CNY по схеме:\n\n"
        "Rapira USDT/RUB + твоя надбавка -> делим на Coinbase USDT/CNY.\n\n"
        "Команды:\n"
        "/rate - взять курсы из API и посчитать\n"
        "/post - собрать готовый пост по API\n"
        "/calc <rapira> <cny> - посчитать вручную\n"
        "/post_calc <rapira> <cny> - собрать пост вручную\n"
        "/settings - показать настройки формулы\n"
        "/formula - показать формулу\n"
        "/myid - показать твой Telegram ID\n\n"
        "Пример: /calc 74.83 6.7754"
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
        await waiting.edit_text("Не смог получить курсы из API. Проверь интернет/доступность Rapira и Coinbase.")
        return

    await waiting.edit_text(build_rate_text(snapshot))


@router.message(Command("post"))
async def cmd_post(message: Message):
    if not await guard(message):
        return

    waiting = await message.reply("Собираю пост: беру Rapira и Coinbase...")
    try:
        snapshot = await rate_service.calculate_auto()
    except Exception:
        logging.exception("Failed to build post")
        await waiting.edit_text("Не смог получить курсы из API. Проверь интернет/доступность Rapira и Coinbase.")
        return

    await waiting.edit_text(build_exchange_post(snapshot, settings))


@router.message(Command("calc"))
async def cmd_calc(message: Message, command: CommandObject):
    if not await guard(message):
        return

    if not command.args:
        await message.reply("Использование: /calc <rapira_usdt_rub> <coinbase_usdt_cny>\nПример: /calc 74.83 6.7754")
        return

    parts = command.args.split()
    if len(parts) != 2:
        await message.reply("Нужно два числа: Rapira USDT/RUB и Coinbase USDT/CNY.\nПример: /calc 74.83 6.7754")
        return

    try:
        rapira_raw = parse_decimal(parts[0])
        coinbase_cny = parse_decimal(parts[1])
        snapshot = rate_service.calculate(rapira_raw=rapira_raw, coinbase_cny=coinbase_cny)
    except (InvalidOperation, ValueError) as exc:
        await message.reply(f"Не смог посчитать: {exc}")
        return

    await message.reply(build_rate_text(snapshot))


@router.message(Command("post_calc"))
async def cmd_post_calc(message: Message, command: CommandObject):
    if not await guard(message):
        return

    if not command.args:
        await message.reply(
            "Использование: /post_calc <rapira_usdt_rub> <coinbase_usdt_cny>\n"
            "Пример: /post_calc 74.83 6.7754"
        )
        return

    parts = command.args.split()
    if len(parts) != 2:
        await message.reply(
            "Нужно два числа: Rapira USDT/RUB и Coinbase USDT/CNY.\n"
            "Пример: /post_calc 74.83 6.7754"
        )
        return

    try:
        rapira_raw = parse_decimal(parts[0])
        coinbase_cny = parse_decimal(parts[1])
        snapshot = rate_service.calculate(rapira_raw=rapira_raw, coinbase_cny=coinbase_cny)
    except (InvalidOperation, ValueError) as exc:
        await message.reply(f"Не смог собрать пост: {exc}")
        return

    await message.reply(build_exchange_post(snapshot, settings))


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    if not await guard(message):
        return

    admin_mode = "включен" if settings.admin_ids else "выключен"
    await message.reply(
        "Настройки:\n\n"
        f"Rapira URL: {settings.rapira_rates_url}\n"
        f"Rapira symbol: {settings.rapira_symbol}\n"
        f"Rapira field: {settings.rapira_price_field}\n"
        f"Coinbase base/quote: {settings.coinbase_base_currency}/{settings.coinbase_quote_currency}\n"
        f"Надбавка к Rapira: +{fmt_rate(settings.rapira_markup_percent, '0.01')}%\n"
        f"Доп. наценка: +{fmt_money(settings.public_markup_rub)} RUB/CNY\n"
        f"Ступени поста: {settings.post_tiers}\n"
        f"Курс чеков: {fmt_money(settings.check_rate_rub)} RUB/CNY\n"
        f"Округление: {settings.round_to}, вверх: {settings.round_up}\n"
        f"Ограничение по ADMIN_IDS: {admin_mode}"
    )


@router.message(Command("formula"))
async def cmd_formula(message: Message):
    if not await guard(message):
        return

    await message.reply(
        "Формула:\n\n"
        "adjusted_usdt_rub = rapira_usdt_rub * (1 + RAPIRA_MARKUP_PERCENT / 100)\n"
        "cny_cost = adjusted_usdt_rub / coinbase_usdt_cny\n"
        "public_rate = round_up(cny_cost + PUBLIC_MARKUP_RUB)\n\n"
        "По твоему примеру: 74.83 * 1.029 = 77.00."
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
