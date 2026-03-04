# 🔔 Stock & Price Change Monitor

Runs continuously, checks a watchlist of EAN codes every N minutes, detects price and stock changes, and fires alerts via **email** and/or **Slack**.

## What it does

- Monitors a JSON watchlist of EAN codes on a configurable schedule (default: every 30 min)
- Detects: price changes (configurable % threshold), stock in → out, stock out → in
- Sends **email alerts** (SMTP) and/or **Slack webhook** messages
- Persists all snapshots and alerts to SQLite for history and trend analysis
- Exports history to Excel on demand

## Usage

```bash
# Start the monitor (runs continuously)
python stock_monitor.py

# Output:
# 2024-01-22 08:00:01 [INFO] Stock monitor started. Checking every 30 min.
# 2024-01-22 08:00:01 [INFO] Watchlist: ['8711969051234', '8711969087652']
# 2024-01-22 08:00:03 [INFO] Checking EAN: 8711969051234
# 2024-01-22 08:00:05 [INFO] CHANGE DETECTED [price]: € 14.99 → € 12.99
# 2024-01-22 08:00:05 [INFO] Sent alert for 1 price change(s).
```

## Watchlist

Edit `watchlist.json` to add/remove EANs:

```json
["8711969051234", "8711969087652", "8711969034521"]
```

## Configuration

Edit `MonitorConfig` in `stock_monitor.py` or use environment variables:

```bash
export SMTP_USER="you@gmail.com"
export SMTP_PASS="your-app-password"
```

| Setting | Default | Description |
|---------|---------|-------------|
| `check_interval_minutes` | 30 | How often to check |
| `price_change_threshold_pct` | 3.0 | Min % change to trigger alert |
| `alert_on_stock_change` | True | Alert on in/out of stock |
| `slack_webhook_url` | None | Slack incoming webhook URL |

## Run as a service (Linux)

```bash
# /etc/systemd/system/stock-monitor.service
[Unit]
Description=EAN Stock Monitor
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/stock_monitor.py
Restart=always
User=ubuntu

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable stock-monitor
sudo systemctl start stock-monitor
```

## Install

```bash
pip install requests beautifulsoup4 pandas schedule openpyxl
```