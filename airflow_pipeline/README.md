# ⚙️ Airflow EAN Price Monitor Pipeline

Production-grade Apache Airflow DAG that runs daily, scrapes prices, stores history, detects changes, and emails alerts. Deployable to AWS MWAA or self-hosted Airflow.

## Pipeline

```
scrape_prices → store_to_db → check_price_alerts → export_weekly_report
```

| Task | What it does |
|------|-------------|
| `scrape_prices` | Fetches price + stock for all watched EANs, pushes to XCom |
| `store_to_db` | Persists results to SQLite (swap for PostgreSQL/RDS in prod) |
| `check_price_alerts` | Compares today vs yesterday, emails on ≥5% price change |
| `export_weekly_report` | Every Monday, generates Excel price trend report |

## Schedule

Runs daily at **08:00** (`0 8 * * *`). Configure via Airflow Variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `ean_watchlist` | JSON array of EANs to monitor | `["8711969051234"]` |
| `alert_email` | Recipient for price alerts | `alerts@yourcompany.com` |

## Setup

### Local (Docker)

```bash
cd airflow-pipeline
docker-compose up -d   # uses standard Airflow docker-compose
# Copy DAG to ~/airflow/dags/
cp ean_price_monitor_dag.py ~/airflow/dags/
```

### AWS MWAA

```bash
# Upload DAG to your MWAA S3 bucket
aws s3 cp ean_price_monitor_dag.py s3://your-mwaa-bucket/dags/
```

## Install (local dev)

```bash
pip install apache-airflow==2.8.1 requests beautifulsoup4 pandas openpyxl sqlalchemy
```

## Extending

- Swap SQLite for **PostgreSQL** or **AWS RDS** by changing the connection string in `store_to_db`
- Add **Slack notifications** by adding a `SlackWebhookOperator` after `check_price_alerts`
- Add more sites by extending the scraper in `scrape_prices`