"""
Product Stock & Price Change Monitor
Monitors a watchlist of EAN codes, detects stock/price changes,
and sends alerts via email or webhook (Slack/Teams).

Author: Mohamed Amine
Stack: requests, BeautifulSoup, pandas, schedule, smtplib, SQLite
Run: python stock_monitor.py  (runs continuously, checks every N minutes)
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import sqlite3
import smtplib
import json
import time
import re
import schedule
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("stock_monitor.log"),
    ],
)

# ---------------------------------------------------------------------------
# Config — in production load from env vars or a config file
# ---------------------------------------------------------------------------

@dataclass
class MonitorConfig:
    check_interval_minutes: int = 30
    db_path: str = "stock_monitor.db"
    watchlist_path: str = "watchlist.json"

    # Alert settings
    alert_on_stock_change: bool = True
    alert_on_price_change: bool = True
    price_change_threshold_pct: float = 3.0

    # Email (set to None to disable)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = None       # set via env: SMTP_USER
    smtp_pass: Optional[str] = None       # set via env: SMTP_PASS
    alert_recipients: list = field(default_factory=lambda: ["alerts@example.com"])

    # Slack webhook (set to None to disable)
    slack_webhook_url: Optional[str] = None


CONFIG = MonitorConfig()


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db():
    with sqlite3.connect(CONFIG.db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ean TEXT NOT NULL,
                name TEXT,
                price REAL,
                price_str TEXT,
                in_stock INTEGER,
                stock_label TEXT,
                url TEXT,
                checked_at TEXT NOT NULL,
                status TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ean TEXT NOT NULL,
                alert_type TEXT,
                old_value TEXT,
                new_value TEXT,
                triggered_at TEXT NOT NULL,
                notified INTEGER DEFAULT 0
            )
        """)
        conn.commit()
    logging.info("Database initialized.")


def save_snapshot(snap: dict):
    with sqlite3.connect(CONFIG.db_path) as conn:
        conn.execute("""
            INSERT INTO snapshots (ean, name, price, price_str, in_stock, stock_label, url, checked_at, status)
            VALUES (:ean, :name, :price, :price_str, :in_stock, :stock_label, :url, :checked_at, :status)
        """, snap)
        conn.commit()


def get_last_snapshot(ean: str) -> Optional[dict]:
    with sqlite3.connect(CONFIG.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT * FROM snapshots WHERE ean = ? AND status = 'success'
            ORDER BY checked_at DESC LIMIT 1
        """, (ean,)).fetchone()
        return dict(row) if row else None


def save_alert(ean: str, alert_type: str, old_val: str, new_val: str):
    with sqlite3.connect(CONFIG.db_path) as conn:
        conn.execute("""
            INSERT INTO alerts (ean, alert_type, old_value, new_value, triggered_at)
            VALUES (?, ?, ?, ?, ?)
        """, (ean, alert_type, old_val, new_val, datetime.now().isoformat()))
        conn.commit()


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "nl-NL,nl;q=0.9",
}

def scrape_ean(ean: str, session: requests.Session) -> dict:
    snap = {
        "ean": ean,
        "name": None,
        "price": None,
        "price_str": None,
        "in_stock": None,
        "stock_label": None,
        "url": None,
        "checked_at": datetime.now().isoformat(),
        "status": "success",
    }

    try:
        resp = session.get(f"https://www.intratuin.nl/search?q={ean}", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        link = soup.select_one("a.product-tile__link, a[href*='/p/']")
        if not link:
            snap["status"] = "not_found"
            return snap

        url = "https://www.intratuin.nl" + link.get("href", "")
        snap["url"] = url

        time.sleep(0.5)
        prod = session.get(url, headers=HEADERS, timeout=15)
        prod.raise_for_status()
        psoup = BeautifulSoup(prod.text, "html.parser")

        # Name
        h1 = psoup.select_one("h1[class*='title'], h1.product-title")
        snap["name"] = h1.get_text(strip=True) if h1 else None

        # Price
        price_el = psoup.select_one("span[class*='price--current'], span.product-price__current")
        if price_el:
            raw = price_el.get_text(strip=True)
            snap["price_str"] = raw
            m = re.search(r"[\d]+[,.][\d]{2}", raw)
            snap["price"] = float(m.group().replace(",", ".")) if m else None

        # Stock
        stock_el = psoup.select_one("span[class*='stock'], div[class*='availability']")
        if stock_el:
            label = stock_el.get_text(strip=True)
            snap["stock_label"] = label
            snap["in_stock"] = int("voorraad" in label.lower() or "beschikbaar" in label.lower())

    except Exception as e:
        snap["status"] = "error"
        logging.error(f"Error scraping EAN {ean}: {e}")

    return snap


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def detect_changes(ean: str, new_snap: dict) -> list[dict]:
    """Compare new snapshot to last known. Return list of change events."""
    changes = []
    old = get_last_snapshot(ean)
    if not old:
        return changes   # first run — no baseline

    # Stock change
    if CONFIG.alert_on_stock_change and new_snap["in_stock"] is not None:
        if old["in_stock"] != new_snap["in_stock"]:
            changes.append({
                "type": "stock",
                "old": "In stock" if old["in_stock"] else "Out of stock",
                "new": "In stock" if new_snap["in_stock"] else "Out of stock",
            })

    # Price change
    if CONFIG.alert_on_price_change and new_snap["price"] and old["price"]:
        pct = abs((new_snap["price"] - old["price"]) / old["price"]) * 100
        if pct >= CONFIG.price_change_threshold_pct:
            direction = "↑" if new_snap["price"] > old["price"] else "↓"
            changes.append({
                "type": "price",
                "old": f"€ {old['price']:.2f}",
                "new": f"€ {new_snap['price']:.2f} ({direction}{pct:.1f}%)",
            })

    return changes


# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------

def send_email_alert(alerts_payload: list[dict]):
    if not CONFIG.smtp_user or not CONFIG.smtp_pass:
        logging.warning("Email alerts disabled — SMTP credentials not set.")
        return

    html = "<h2>🔔 Product Monitor Alerts</h2>"
    for a in alerts_payload:
        emoji = "📦" if a["change"]["type"] == "stock" else "💰"
        html += f"""
        <div style="border-left:4px solid #059669;padding:12px;margin:10px 0;">
            <strong>{emoji} {a['change']['type'].upper()} CHANGE</strong><br>
            EAN: <code>{a['ean']}</code> — {a['name'] or 'Unknown'}<br>
            <strong>{a['change']['old']}</strong> → <strong>{a['change']['new']}</strong><br>
            <a href="{a['url']}">View product</a>
        </div>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Stock Monitor] {len(alerts_payload)} change(s) detected"
    msg["From"] = CONFIG.smtp_user
    msg["To"] = ", ".join(CONFIG.alert_recipients)
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(CONFIG.smtp_host, CONFIG.smtp_port) as s:
            s.starttls()
            s.login(CONFIG.smtp_user, CONFIG.smtp_pass)
            s.sendmail(CONFIG.smtp_user, CONFIG.alert_recipients, msg.as_string())
        logging.info(f"Email alert sent to {CONFIG.alert_recipients}")
    except Exception as e:
        logging.error(f"Failed to send email alert: {e}")


def send_slack_alert(alerts_payload: list[dict]):
    if not CONFIG.slack_webhook_url:
        return

    blocks = [{"type": "header", "text": {"type": "plain_text", "text": "🔔 Product Monitor Alerts"}}]
    for a in alerts_payload:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{a['change']['type'].upper()}* — `{a['ean']}`\n"
                    f"_{a['name'] or 'Unknown product'}_\n"
                    f"{a['change']['old']} → *{a['change']['new']}*\n"
                    f"<{a['url']}|View on intratuin.nl>"
                ),
            },
        })

    try:
        requests.post(CONFIG.slack_webhook_url, json={"blocks": blocks}, timeout=10)
        logging.info("Slack alert sent.")
    except Exception as e:
        logging.error(f"Slack alert failed: {e}")


# ---------------------------------------------------------------------------
# Main monitoring loop
# ---------------------------------------------------------------------------

def load_watchlist() -> list[str]:
    path = Path(CONFIG.watchlist_path)
    if path.exists():
        return json.loads(path.read_text())
    # Default demo watchlist
    return ["8711969051234", "8711969087652"]


def run_check():
    logging.info("=" * 50)
    logging.info(f"Running check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    eans = load_watchlist()
    session = requests.Session()
    pending_alerts = []

    for ean in eans:
        logging.info(f"Checking EAN: {ean}")
        snap = scrape_ean(ean, session)
        save_snapshot(snap)

        changes = detect_changes(ean, snap)
        for change in changes:
            logging.info(f"  CHANGE DETECTED [{change['type']}]: {change['old']} → {change['new']}")
            save_alert(ean, change["type"], change["old"], change["new"])
            pending_alerts.append({
                "ean": ean,
                "name": snap.get("name"),
                "url": snap.get("url", ""),
                "change": change,
            })

        time.sleep(1)

    if pending_alerts:
        send_email_alert(pending_alerts)
        send_slack_alert(pending_alerts)
        logging.info(f"Dispatched {len(pending_alerts)} alert(s).")
    else:
        logging.info("No changes detected.")


def export_history(ean: str = None) -> pd.DataFrame:
    """Export monitoring history to DataFrame / Excel."""
    query = "SELECT * FROM snapshots"
    params = ()
    if ean:
        query += " WHERE ean = ?"
        params = (ean,)
    query += " ORDER BY checked_at DESC"

    with sqlite3.connect(CONFIG.db_path) as conn:
        df = pd.read_sql_query(query, conn, params=params)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"monitor_history_{ts}.xlsx"
    df.to_excel(path, index=False)
    logging.info(f"History exported to {path}")
    return df


def main():
    init_db()
    logging.info(f"Stock monitor started. Checking every {CONFIG.check_interval_minutes} min.")
    logging.info(f"Watchlist: {load_watchlist()}")

    # Run immediately on start
    run_check()

    # Then on schedule
    schedule.every(CONFIG.check_interval_minutes).minutes.do(run_check)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()