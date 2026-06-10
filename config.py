import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv


load_dotenv()


def _decimal_env(name: str, default: str) -> Decimal:
    raw = os.getenv(name, default).strip().replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a decimal number, got {raw!r}") from exc


def _int_env(name: str, default: str) -> int:
    raw = os.getenv(name, default).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def _bool_env(name: str, default: str) -> bool:
    raw = os.getenv(name, default).strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _admin_ids(raw: str | None) -> set[int]:
    if not raw:
        return set()
    return {int(x) for x in re.split(r"[,\s]+", raw.strip()) if x.isdigit()}


def _optional_decimal_env(name: str) -> Decimal | None:
    raw = os.getenv(name, "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a decimal number, got {raw!r}") from exc


def _tiers_env(name: str, default: str) -> list[tuple[int, Decimal]]:
    raw = os.getenv(name, default).strip()
    tiers: list[tuple[int, Decimal]] = []
    for part in re.split(r"[;\n]+", raw):
        if not part.strip():
            continue
        min_amount, markup = part.split(":", 1)
        tiers.append((int(min_amount.strip()), Decimal(markup.strip().replace(",", "."))))
    return sorted(tiers)


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    admin_ids: set[int]

    rapira_rates_url: str
    rapira_symbol: str
    rapira_price_field: str

    coinbase_rates_url: str
    coinbase_base_currency: str
    coinbase_quote_currency: str

    rapira_markup_percent: Decimal
    public_markup_rub: Decimal
    round_to: Decimal
    round_up: bool
    request_timeout_seconds: int

    post_tiers: list[tuple[int, Decimal]]
    check_markup_rub: Decimal
    check_round_to: Decimal
    min_exchange_cny: int
    trial_exchange_cny: int
    usdt_buy_rate_rub: Decimal | None
    usdt_sell_rate_rub: Decimal | None
    usdt_buy_offset_rub: Decimal
    usdt_sell_offset_rub: Decimal
    usdt_cny_regular: Decimal | None
    usdt_cny_big: Decimal | None
    usdt_cny_big_from: int
    usdt_cny_offset: Decimal
    min_rub_to_usdt_rub: Decimal
    min_usdt_to_rub: Decimal
    min_usdt_to_cny: Decimal
    contact_username: str
    reviews_username: str
    chat_username: str
    max_url: str
    site_rates_path: str


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TGTOKEN") or ""
    token = token.strip()
    if not token or token == "123456:replace_me":
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env or environment variables.")

    return Settings(
        telegram_bot_token=token,
        admin_ids=_admin_ids(os.getenv("ADMIN_IDS")),
        rapira_rates_url=os.getenv("RAPIRA_RATES_URL", "https://api.rapira.net/open/market/rates").strip(),
        rapira_symbol=os.getenv("RAPIRA_SYMBOL", "USDT/RUB").strip().upper(),
        rapira_price_field=os.getenv("RAPIRA_PRICE_FIELD", "close").strip(),
        coinbase_rates_url=os.getenv("COINBASE_RATES_URL", "https://api.coinbase.com/v2/exchange-rates").strip(),
        coinbase_base_currency=os.getenv("COINBASE_BASE_CURRENCY", "USDT").strip().upper(),
        coinbase_quote_currency=os.getenv("COINBASE_QUOTE_CURRENCY", "CNY").strip().upper(),
        rapira_markup_percent=_decimal_env("RAPIRA_MARKUP_PERCENT", "2.9"),
        public_markup_rub=_decimal_env("PUBLIC_MARKUP_RUB", "0.00"),
        round_to=_decimal_env("ROUND_TO", "0.01"),
        round_up=_bool_env("ROUND_UP", "true"),
        request_timeout_seconds=_int_env("REQUEST_TIMEOUT_SECONDS", "10"),
        post_tiers=_tiers_env("POST_TIERS", "1000:0.15;3000:0.10;10000:0.05;30000:0.00"),
        check_markup_rub=_decimal_env("CHECK_MARKUP_RUB", "0.40"),
        check_round_to=_decimal_env("CHECK_ROUND_TO", "0.10"),
        min_exchange_cny=_int_env("MIN_EXCHANGE_CNY", "500"),
        trial_exchange_cny=_int_env("TRIAL_EXCHANGE_CNY", "100"),
        usdt_buy_rate_rub=_optional_decimal_env("USDT_BUY_RATE_RUB"),
        usdt_sell_rate_rub=_optional_decimal_env("USDT_SELL_RATE_RUB"),
        usdt_buy_offset_rub=_decimal_env("USDT_BUY_OFFSET_RUB", "4"),
        usdt_sell_offset_rub=_decimal_env("USDT_SELL_OFFSET_RUB", "-3"),
        usdt_cny_regular=_optional_decimal_env("USDT_CNY_REGULAR"),
        usdt_cny_big=_optional_decimal_env("USDT_CNY_BIG"),
        usdt_cny_big_from=_int_env("USDT_CNY_BIG_FROM", "10000"),
        usdt_cny_offset=_decimal_env("USDT_CNY_OFFSET", "-0.08"),
        min_rub_to_usdt_rub=_decimal_env("MIN_RUB_TO_USDT_RUB", "35000"),
        min_usdt_to_rub=_decimal_env("MIN_USDT_TO_RUB", "500"),
        min_usdt_to_cny=_decimal_env("MIN_USDT_TO_CNY", "500"),
        contact_username=os.getenv("CONTACT_USERNAME", "@exchange_kir").strip(),
        reviews_username=os.getenv("REVIEWS_USERNAME", "@otzivi_17teen").strip(),
        chat_username=os.getenv("CHAT_USERNAME", "@chat_17teen").strip(),
        max_url=os.getenv(
            "MAX_URL",
            "https://max.ru/u/f9LHodD0cOIlGK214Iw7B-Xt7rBa_q85OmfEK61yQXs8e0apAqgArel29NI",
        ).strip(),
        site_rates_path=os.getenv("SITE_RATES_PATH", "/var/www/17exchange/rates.json").strip(),
    )
