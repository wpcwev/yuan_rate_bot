# yuan_rate_bot

Telegram-бот для расчета курса RUB/CNY.

Сейчас бот считает курс, показывает лесенку цен по суммам и обновляет `rates.json`
для сайта. Для автоматического обновления сайта используется отдельный скрипт
`update_site_rates.py`, который удобно запускать systemd-таймером раз в час.

## Формула

```text
adjusted_usdt_rub = rapira_usdt_rub * (1 + RAPIRA_MARKUP_PERCENT / 100)
cny_cost = adjusted_usdt_rub / coinbase_usdt_cny
public_rate = round_up(cny_cost + PUBLIC_MARKUP_RUB)
rate_from_500 = ceil_to_0.10(rate_from_30000 + CHECK_MARKUP_RUB)
site_usdt_cny = coinbase_usdt_cny + USDT_CNY_OFFSET
```

По текущей логике:

- `rapira_usdt_rub` берется из Rapira API.
- `RAPIRA_MARKUP_PERCENT=2.9` превращает пример `74.83` в `77.00`.
- `coinbase_usdt_cny` берется из Coinbase API.
- `PUBLIC_MARKUP_RUB` - основная маржа для лучшего курса CNY.
- `CHECK_MARKUP_RUB=0.40` добавляется к лучшему курсу для диапазона от 500¥.
- `USDT_CNY_OFFSET=-0.08` делает курс USDT/CNY для сайта ниже Coinbase на 8 копеек.

## API-источники

- Rapira: `https://api.rapira.net/open/market/rates`
- Coinbase: `https://api.coinbase.com/v2/exchange-rates?currency=USDT`

## Команды бота

```text
/rate
```

Берет курсы из API и считает курс.

```text
/rates
```

Берет курсы из API и показывает курс по суммам.

```text
/calc 74.83 6.7754
```

Считает вручную по переданным значениям.

```text
/rates_calc 74.83 6.7754
```

Показывает курс по суммам по переданным значениям.

```text
/site_preview
```

Показывает, какие данные будут записаны на сайт.

```text
/site_update
```

Обновляет `rates.json` сайта.

```text
/settings
```

Показывает текущие настройки формулы.

```text
/formula
```

Показывает формулу.

```text
/myid
```

Показывает Telegram ID, чтобы можно было добавить себя в `ADMIN_IDS`.

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python main.py
```

На Windows вместо `source`:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Настройка `.env`

Минимально нужно указать токен:

```text
TELEGRAM_BOT_TOKEN=123456:replace_me
```

Рекомендуется ограничить доступ:

```text
ADMIN_IDS=123456789,987654321
```

Основные параметры:

```text
RAPIRA_MARKUP_PERCENT=2.9
PUBLIC_MARKUP_RUB=0.20
ROUND_TO=0.05
ROUND_UP=true
POST_TIERS=1000:0.15;3000:0.10;10000:0.05;30000:0.00
CHECK_MARKUP_RUB=0.40
CHECK_ROUND_TO=0.10
USDT_CNY_OFFSET=-0.08
MIN_RUB_TO_USDT_RUB=35000
MIN_USDT_TO_RUB=500
MIN_USDT_TO_CNY=500
CONTACT_USERNAME=@exchange_kir
MAX_URL=https://max.ru/u/f9LHodD0cOIlGK214Iw7B-Xt7rBa_q85OmfEK61yQXs8e0apAqgArel29NI
SITE_RATES_PATH=/var/www/17exchange/rates.json
```

## Запуск на Ubuntu через systemd

Пример сервиса `/etc/systemd/system/yuan-rate-bot.service`:

```ini
[Unit]
Description=Yuan Rate Telegram Bot
After=network.target

[Service]
WorkingDirectory=/opt/yuan_rate_bot
ExecStart=/opt/yuan_rate_bot/.venv/bin/python /opt/yuan_rate_bot/main.py
Restart=always
RestartSec=5
EnvironmentFile=/opt/yuan_rate_bot/.env

[Install]
WantedBy=multi-user.target
```

Команды:

```bash
sudo systemctl daemon-reload
sudo systemctl enable yuan-rate-bot
sudo systemctl start yuan-rate-bot
sudo systemctl status yuan-rate-bot
```

## Автообновление сайта раз в час

Пример one-shot сервиса `/etc/systemd/system/yuan-rate-site-update.service`:

```ini
[Unit]
Description=Update yuan rates for site
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/yuan_rate_bot
ExecStart=/opt/yuan_rate_bot/.venv/bin/python /opt/yuan_rate_bot/update_site_rates.py
EnvironmentFile=/opt/yuan_rate_bot/.env
```

Пример таймера `/etc/systemd/system/yuan-rate-site-update.timer`:

```ini
[Unit]
Description=Hourly yuan rates site update

[Timer]
OnBootSec=2min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
```
