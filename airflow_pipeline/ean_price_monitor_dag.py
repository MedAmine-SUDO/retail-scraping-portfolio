"""
Scheduled EAN Price Monitor — Apache Airflow DAG
Production-grade pipeline that runs daily, scrapes prices,
stores results in SQLite, and sends alerts.

Author: Mohamed Amine
Stack: Apache Airflow, requests, BeautifulSoup, pandas, SQLAlchemy, smtplib
"""

from datetime import datetime, timedelta
import json
import logging

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
from airflow.utils.email import send_email

# ---------------------------------------------------------------------------
# DAG configuration
# ---------------------------------------------------------------------------

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

try:
    EAN_LIST = Variable.get("ean_watchlist", default_var='["8711969051234","8711969087652"]')
except Exception:
    logging.warning("Airflow Variable 'ean_watchlist' not found. Using default list.")
    EAN_LIST = '["8711969051234","8711969087652"]'

dag = DAG(
    dag_id="ean_price_monitor",
    default_args=DEFAULT_ARGS,
    description="Daily EAN price scraping pipeline with alerting",
    schedule_interval="0 8 * * *",   # every day at 08:00
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["scraping", "price-monitoring", "retail"],
)

# ---------------------------------------------------------------------------
# Task 1: Scrape prices
# ---------------------------------------------------------------------------

def scrape_prices(**context):
    """Scrape prices for all watched EANs and push to XCom."""
    import requests
    from bs4 import BeautifulSoup
    import re, time

    eans = json.loads(EAN_LIST)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; PriceMonitorBot/1.0)",
        "Accept-Language": "nl-NL,nl;q=0.9",
    })

    results = []
    for ean in eans:
        for attempt in range(3):
            try:
                url = f"https://www.intratuin.nl/search?q={ean}"
                resp = session.get(url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                link = soup.select_one("a.product-tile__link, a[href*='/p/']")
                if not link:
                    results.append({"ean": ean, "price": None, "status": "not_found"})
                    break

                prod_url = "https://www.intratuin.nl" + link["href"]
                time.sleep(0.5)
                prod = session.get(prod_url, timeout=15)
                psoup = BeautifulSoup(prod.text, "html.parser")

                price_el = psoup.select_one("span[class*='price--current']")
                price = None
                if price_el:
                    m = re.search(r"[\d]+[,.][\d]{2}", price_el.get_text())
                    price = float(m.group().replace(",", ".")) if m else None

                name_el = psoup.select_one("h1[class*='title']")
                name = name_el.get_text(strip=True) if name_el else None

                results.append({
                    "ean": ean,
                    "name": name,
                    "price": price,
                    "url": prod_url,
                    "status": "success",
                    "scraped_at": datetime.now().isoformat(),
                })
                break

            except Exception as e:
                if attempt == 2:
                    results.append({"ean": ean, "price": None, "status": "error", "error": str(e)})
                    logging.error(f"Failed to scrape EAN {ean}: {e}")
                time.sleep(2 ** attempt)

    context["ti"].xcom_push(key="scraped_prices", value=results)
    logging.info(f"Scraped {len(results)} EANs. Success: {sum(1 for r in results if r['status']=='success')}")
    return results


# ---------------------------------------------------------------------------
# Task 2: Store to database
# ---------------------------------------------------------------------------

def store_to_db(**context):
    """Persist scraped prices to SQLite (swap for RDS/PostgreSQL in prod)."""
    from sqlalchemy import create_engine, text
    import pandas as pd

    results = context["ti"].xcom_pull(key="scraped_prices", task_ids="scrape_prices")
    if not results:
        logging.warning("No results to store.")
        return

    # In prod: use Variable.get("db_conn_string")
    engine = create_engine("sqlite:////tmp/price_history.db")

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ean TEXT NOT NULL,
                name TEXT,
                price REAL,
                url TEXT,
                status TEXT,
                scraped_at TEXT,
                run_date DATE DEFAULT (date('now'))
            )
        """))
        conn.commit()

    df = pd.DataFrame(results)
    df["run_date"] = datetime.now().date().isoformat()
    df.to_sql("price_history", engine, if_exists="append", index=False)
    logging.info(f"Stored {len(df)} rows to price_history table.")


# ---------------------------------------------------------------------------
# Task 3: Detect price changes and alert
# ---------------------------------------------------------------------------

def check_price_alerts(**context):
    """
    Compare today's prices with yesterday's.
    Send email alert if any price changed by > threshold.
    """
    from sqlalchemy import create_engine
    import pandas as pd

    engine = create_engine("sqlite:////tmp/price_history.db")
    ALERT_THRESHOLD_PCT = 5.0   # alert if price changes by 5%+

    try:
        df = pd.read_sql("""
            SELECT ean, name, price, run_date
            FROM price_history
            WHERE run_date >= date('now', '-2 days')
            ORDER BY run_date DESC
        """, engine)
    except Exception as e:
        logging.warning(f"Could not read history: {e}")
        return

    alerts = []
    for ean in df["ean"].unique():
        subset = df[df["ean"] == ean].sort_values("run_date", ascending=False)
        if len(subset) < 2:
            continue
        today_price = subset.iloc[0]["price"]
        prev_price = subset.iloc[1]["price"]
        if today_price and prev_price and prev_price > 0:
            pct_change = ((today_price - prev_price) / prev_price) * 100
            if abs(pct_change) >= ALERT_THRESHOLD_PCT:
                alerts.append({
                    "ean": ean,
                    "name": subset.iloc[0]["name"],
                    "prev_price": prev_price,
                    "today_price": today_price,
                    "pct_change": pct_change,
                })

    if alerts:
        body = "<h2>Price Change Alerts</h2><ul>"
        for a in alerts:
            direction = "📈 UP" if a["pct_change"] > 0 else "📉 DOWN"
            body += (
                f"<li><strong>{a['name']}</strong> (EAN: {a['ean']}): "
                f"€{a['prev_price']:.2f} → €{a['today_price']:.2f} "
                f"({direction} {abs(a['pct_change']):.1f}%)</li>"
            )
        body += "</ul>"

        send_email(
            to=Variable.get("alert_email", default_var="alerts@yourcompany.com"),
            subject=f"[Price Monitor] {len(alerts)} price changes detected",
            html_content=body,
        )
        logging.info(f"Sent alert for {len(alerts)} price changes.")
    else:
        logging.info("No significant price changes detected.")


# ---------------------------------------------------------------------------
# Task 4: Export weekly report
# ---------------------------------------------------------------------------

def export_weekly_report(**context):
    """Every Monday, export a weekly Excel report of price trends."""
    from sqlalchemy import create_engine
    import pandas as pd

    if datetime.now().weekday() != 0:   # 0 = Monday
        logging.info("Not Monday — skipping weekly report.")
        return

    engine = create_engine("sqlite:////tmp/price_history.db")
    df = pd.read_sql("""
        SELECT ean, name, price, run_date
        FROM price_history
        WHERE run_date >= date('now', '-7 days')
        ORDER BY ean, run_date
    """, engine)

    if df.empty:
        return

    pivot = df.pivot_table(index="ean", columns="run_date", values="price", aggfunc="first")
    pivot.columns = [str(c) for c in pivot.columns]

    out_path = f"/tmp/weekly_report_{datetime.now().strftime('%Y_%W')}.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        pivot.reset_index().to_excel(writer, sheet_name="Price Trends", index=False)
        df.to_excel(writer, sheet_name="Raw Data", index=False)

    logging.info(f"Weekly report exported to {out_path}")


# ---------------------------------------------------------------------------
# Wire up tasks
# ---------------------------------------------------------------------------

t1 = PythonOperator(task_id="scrape_prices", python_callable=scrape_prices, dag=dag)
t2 = PythonOperator(task_id="store_to_db", python_callable=store_to_db, dag=dag)
t3 = PythonOperator(task_id="check_price_alerts", python_callable=check_price_alerts, dag=dag)
t4 = PythonOperator(task_id="export_weekly_report", python_callable=export_weekly_report, dag=dag)

t1 >> t2 >> t3 >> t4