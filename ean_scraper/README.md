# 📦 EAN Scraper — intratuin.nl

Scrape product data from intratuin.nl using one or more EAN codes and export to a formatted Excel file.

## What it does

- Accepts EAN codes via CLI args or interactive prompt
- Searches intratuin.nl and navigates to the product page
- Extracts: name, price, description, stock status, image URL, product URL
- Exports results to a timestamped `.xlsx` file with auto-sized columns

## Usage

```bash
# Single EAN
python ean_scraper_selenium.py 8711969051234

# Multiple EANs
python ean_scraper_selenium.py 8711969051234 8711969087652

# Interactive
python ean_scraper_selenium.py
# Enter EAN code(s), comma-separated: 8711969051234, 8711969087652
```

## Output

```
intratuin_products_20240122_081400.xlsx
```

| EAN | Name | Price | Stock | Description | Image URL | Product URL | Scraped At | Status |
|-----|------|-------|-------|-------------|-----------|-------------|------------|--------|
| 8711... | Monstera Deliciosa | € 12,99 | Op voorraad | ... | https://... | https://... | 2024-01-22 | success |

## Install

```bash
pip install requests beautifulsoup4 openpyxl pandas
```
