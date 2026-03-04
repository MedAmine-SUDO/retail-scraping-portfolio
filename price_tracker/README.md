# 💰 Multi-Site Price Tracker

Compare the same EAN product across **intratuin.nl**, **gamma.nl**, and **hornbach.nl** to find the best price. Exports a color-coded Excel report highlighting the cheapest option.

## What it does

- Takes one or more EAN codes as input
- Scrapes all 3 sites in parallel (per EAN)
- Detects best price automatically
- Exports color-coded `.xlsx` — lowest price row highlighted in green

## Usage

```bash
# Single EAN
python price_tracker.py 8711969051234

# Multiple EANs
python price_tracker.py 8711969051234 8711969087652
```

## Example Output

```
Comparing prices for EAN: 8711969051234
--------------------------------------------------
  Checking intratuin.nl... € 12.99
  Checking gamma.nl...     € 14.49
  Checking hornbach.nl...  € 11.75

  ✓ Best price: hornbach.nl — € 11.75

✓ Exported to: price_comparison_20240122_081400.xlsx
```

## Adding More Sites

Each site is defined in the `SITES` dict — add a new entry with CSS selectors and you're done:

```python
SITES["newsite.nl"] = {
    "search_url": "https://www.newsite.nl/search?q={ean}",
    "product_link_sel": "a[href*='/product/']",
    "price_sel": "span.price",
    "name_sel": "h1.title",
    "stock_sel": "span.stock",
}
```

## Install

```bash
pip install requests beautifulsoup4 pandas openpyxl
```