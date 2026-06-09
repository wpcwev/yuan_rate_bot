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
    )
