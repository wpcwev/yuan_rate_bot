from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Any

import aiohttp

from config import Settings


@dataclass(frozen=True)
class RateSnapshot:
    rapira_raw: Decimal
    rapira_adjusted: Decimal
    coinbase_cny: Decimal
    cny_cost_rub: Decimal
    public_rate_raw: Decimal
    public_rate: Decimal
    rapira_field: str
    rapira_symbol: str


class RateService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def calculate_auto(self) -> RateSnapshot:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.settings.request_timeout_seconds)
        ) as session:
            rapira_raw = await self._fetch_rapira_rate(session)
            coinbase_cny = await self._fetch_coinbase_rate(session)
        return self.calculate(rapira_raw=rapira_raw, coinbase_cny=coinbase_cny)

    def calculate(self, rapira_raw: Decimal, coinbase_cny: Decimal) -> RateSnapshot:
        if rapira_raw <= 0:
            raise ValueError("Rapira USDT/RUB rate must be greater than zero.")
        if coinbase_cny <= 0:
            raise ValueError("Coinbase USDT/CNY rate must be greater than zero.")

        rapira_adjusted = rapira_raw * (Decimal("1") + self.settings.rapira_markup_percent / Decimal("100"))
        cny_cost_rub = rapira_adjusted / coinbase_cny
        public_rate_raw = cny_cost_rub + self.settings.public_markup_rub
        public_rate = self._round_rate(public_rate_raw)

        return RateSnapshot(
            rapira_raw=rapira_raw,
            rapira_adjusted=rapira_adjusted,
            coinbase_cny=coinbase_cny,
            cny_cost_rub=cny_cost_rub,
            public_rate_raw=public_rate_raw,
            public_rate=public_rate,
            rapira_field=self.settings.rapira_price_field,
            rapira_symbol=self.settings.rapira_symbol,
        )

    async def _fetch_rapira_rate(self, session: aiohttp.ClientSession) -> Decimal:
        data = await self._get_json(session, self.settings.rapira_rates_url)
        items = data.get("data")
        if not isinstance(items, list):
            raise ValueError("Rapira response has no data list.")

        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("symbol", "")).upper() != self.settings.rapira_symbol:
                continue
            if self.settings.rapira_price_field not in item:
                raise ValueError(f"Rapira item has no {self.settings.rapira_price_field!r} field.")
            return Decimal(str(item[self.settings.rapira_price_field]))

        raise ValueError(f"Rapira symbol {self.settings.rapira_symbol!r} not found.")

    async def _fetch_coinbase_rate(self, session: aiohttp.ClientSession) -> Decimal:
        url = f"{self.settings.coinbase_rates_url}?currency={self.settings.coinbase_base_currency}"
        data = await self._get_json(session, url)
        rates = data.get("data", {}).get("rates", {})
        raw_rate = rates.get(self.settings.coinbase_quote_currency)
        if raw_rate is None:
            raise ValueError(
                f"Coinbase quote currency {self.settings.coinbase_quote_currency!r} not found."
            )
        return Decimal(str(raw_rate))

    async def _get_json(self, session: aiohttp.ClientSession, url: str) -> dict[str, Any]:
        async with session.get(url, headers={"Accept": "application/json"}) as response:
            response.raise_for_status()
            data = await response.json()
            if not isinstance(data, dict):
                raise ValueError(f"Unexpected JSON from {url}")
            return data

    def _round_rate(self, value: Decimal) -> Decimal:
        step = self.settings.round_to
        if step <= 0:
            return value
        rounding = ROUND_CEILING if self.settings.round_up else ROUND_HALF_UP
        return (value / step).to_integral_value(rounding=rounding) * step

    def round_public_rate(self, value: Decimal) -> Decimal:
        return self._round_rate(value)


def parse_decimal(raw: str) -> Decimal:
    return Decimal(raw.strip().replace(",", "."))


def fmt_money(value: Decimal, places: str = "0.01") -> str:
    return str(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def fmt_rate(value: Decimal, places: str = "0.0001") -> str:
    return str(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))
