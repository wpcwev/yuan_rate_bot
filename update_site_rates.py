import asyncio
import logging

from config import load_settings
from rate_service import RateService
from site_export import build_site_rates, write_site_rates


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    settings = load_settings()
    rate_service = RateService(settings)
    snapshot = await rate_service.calculate_auto()
    payload = build_site_rates(snapshot, settings, rate_service)
    target = write_site_rates(payload, settings.site_rates_path)
    logging.info("updated site rates: %s", target)


if __name__ == "__main__":
    asyncio.run(main())
