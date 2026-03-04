# 🌿 Retail Scraping Portfolio

> Python web scraping & data engineering projects built around Dutch garden retail (intratuin.nl).
> Demonstrates production-grade scraping, multi-site comparison, Airflow pipelines, and real-time monitoring.

---

## Projects

| # | Project | Stack | Description |
|---|---------|-------|-------------|
| 1 | [EAN Scraper](./ean_scraper/) | requests, BeautifulSoup, openpyxl | Scrape product data by EAN code → Excel |
| 2 | [Multi-Site Price Tracker](./price_tracker/) | requests, BeautifulSoup, pandas | Compare same EAN across 3 retailers |
| 3 | [Airflow Pipeline](./airflow_pipeline/) | Apache Airflow, SQLAlchemy, pandas | Scheduled daily scraping DAG with alerting |
| 4 | [Stock & Price Monitor](./stock_monitor/) | requests, schedule, SQLite, smtplib | Continuous monitor with email + Slack alerts |

---

## Quick Start

```bash
git clone https://github.com/MedAmine-SUDO/retail-scraping-portfolio.git
cd retail-scraping-portfolio
pip install -r requirements.txt
```

Each project has its own README with setup instructions and example output.

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Apache Airflow](https://img.shields.io/badge/Airflow-2.x-017CEE?logo=apacheairflow)
![Pandas](https://img.shields.io/badge/Pandas-2.x-150458?logo=pandas)
![SQLite](https://img.shields.io/badge/SQLite-3.x-003B57?logo=sqlite)

- **Scraping:** `requests`, `BeautifulSoup4`, `Selenium` (where needed)
- **Data:** `pandas`, `openpyxl`, `SQLAlchemy`, `SQLite` / `PostgreSQL`
- **Orchestration:** `Apache Airflow` / `schedule`
- **Alerting:** `smtplib` (email), Slack webhooks
- **Infrastructure:** AWS MWAA, Docker, S3

---

## Author

Built by Mohamed Amine · [Upwork Profile](https://www.upwork.com/freelancers/~01de6a80acbbaa49db) · [LinkedIn](https://www.linkedin.com/in/mabenafia/)