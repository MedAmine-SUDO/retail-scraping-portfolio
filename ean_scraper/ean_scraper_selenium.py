"""
EAN Scraper for intratuin.nl — Selenium version
================================================
intratuin.nl is a JavaScript-rendered Magento site.
requests+BeautifulSoup will only get an empty shell.
This script uses Selenium (headless Chrome) to get the fully rendered page.

Author: Mohamed Amine
"""

import sys
import time
import re
import json
from datetime import datetime

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
# webdriver-manager not needed — Selenium 4.6+ has built-in driver management


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def make_driver(headless: bool = True) -> webdriver.Chrome:
    """Create a headless Chrome driver.
    Uses Selenium Manager (built into Selenium 4.6+) — no chromedriver download needed.
    """
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # Selenium 4.6+ includes Selenium Manager which auto-downloads the right chromedriver
    # No Service() or webdriver-manager package needed
    driver = webdriver.Chrome(options=opts)

    # Mask webdriver flag
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


# ---------------------------------------------------------------------------
# Scraping logic
# ---------------------------------------------------------------------------

def accept_cookies(driver):
    """Dismiss cookie banner if present."""
    try:
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "button#onetrust-accept-btn-handler, "
                "button[class*='cookie-accept'], "
                "button[class*='accept-all']"
            ))
        )
        btn.click()
        time.sleep(0.5)
    except TimeoutException:
        pass  # No cookie banner — that's fine


def get_text(driver, selectors: list[str], default=None) -> str | None:
    """Try multiple CSS selectors, return text of first match."""
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            text = el.text.strip()
            if text:
                return text
        except NoSuchElementException:
            continue
    return default


def get_attr(driver, selectors: list[str], attr: str, default=None) -> str | None:
    """Try multiple CSS selectors, return attribute value of first match."""
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            val = el.get_attribute(attr)
            if val:
                return val.strip()
        except NoSuchElementException:
            continue
    return default


def scrape_ean(ean: str, driver: webdriver.Chrome) -> dict:
    """Scrape one EAN from intratuin.nl. Returns a result dict."""
    result = {
        "ean": ean,
        "name": None,
        "price": None,
        "stock_status": None,
        "description": None,
        "image_url": None,
        "product_url": None,
        "artikelnummer": None,
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "success",
        "error": None,
    }

    try:
        # --- Step 1: Search by EAN ---
        search_url = f"https://www.intratuin.nl/catalogsearch/result/?q={ean}"
        print(f"  → Loading search: {search_url}")
        driver.get(search_url)

        # Wait for page to load
        accept_cookies(driver)

        # Wait for either search results or "no results" message
        try:
            WebDriverWait(driver, 15).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        "a.product-item-link, "
                        "li.product-item a, "
                        "a[class*='product'][href*='.html'], "
                        ".product-items .item"
                    )),
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        ".search-no-result, [class*='no-result'], "
                        ".message.notice"
                    )),
                )
            )
        except TimeoutException:
            result["status"] = "timeout"
            result["error"] = "Search page did not load within 15s"
            return result

        # Check for no results
        try:
            no_result = driver.find_element(By.CSS_SELECTOR,
                ".search-no-result, [class*='no-result'], .message.notice"
            )
            if no_result.is_displayed():
                result["status"] = "not_found"
                result["error"] = f"No results for EAN {ean} on intratuin.nl"
                return result
        except NoSuchElementException:
            pass

        # --- Step 2: Get first product link ---
        product_link = None
        link_selectors = [
            "a.product-item-link",
            "li.product-item a[href*='.html']",
            ".products-grid .product-item a",
            "a[class*='product'][href*='.html']",
            ".item.product a",
        ]
        for sel in link_selectors:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                # Filter to product page links (end in .html, not /category/)
                for el in els:
                    href = el.get_attribute("href") or ""
                    if href.endswith(".html") and "/catalogsearch/" not in href:
                        product_link = href
                        break
                if product_link:
                    break
            except Exception:
                continue

        if not product_link:
            result["status"] = "not_found"
            result["error"] = "Could not find product link in search results"
            return result

        result["product_url"] = product_link
        print(f"  → Found product: {product_link}")

        # --- Step 3: Load product page ---
        driver.get(product_link)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR,
                "h1.page-title, h1[itemprop='name'], "
                ".product-info-main h1, span[itemprop='name']"
            ))
        )
        time.sleep(1)  # Let dynamic content settle

        # --- Step 4: Extract data ---

        # Name
        result["name"] = get_text(driver, [
            "h1.page-title span",
            "h1[itemprop='name']",
            ".product-info-main h1",
            "span[itemprop='name']",
            "h1.page-title",
        ])

        # Price — Magento price patterns
        result["price"] = get_text(driver, [
            "span.price",
            "[data-price-type='finalPrice'] span.price",
            ".product-info-price .price",
            "meta[itemprop='price']",  # fallback to meta
            ".price-box .price",
            "[class*='price-final'] span.price",
        ])
        # If still empty, try meta tag
        if not result["price"]:
            try:
                meta = driver.find_element(By.CSS_SELECTOR, "meta[itemprop='price']")
                val = meta.get_attribute("content")
                if val:
                    result["price"] = f"€ {val}"
            except NoSuchElementException:
                pass

        # Stock status
        result["stock_status"] = get_text(driver, [
            "[class*='stock'] span",
            "[class*='availability'] span",
            ".product-info-stock-sku .stock span",
            "[itemprop='availability']",
            "[class*='stock-status']",
            ".availability span",
        ])
        if not result["stock_status"]:
            # Try from meta
            try:
                meta = driver.find_element(By.CSS_SELECTOR,
                    "link[itemprop='availability']"
                )
                val = meta.get_attribute("href") or ""
                if "InStock" in val:
                    result["stock_status"] = "Op voorraad"
                elif "OutOfStock" in val:
                    result["stock_status"] = "Niet op voorraad"
            except NoSuchElementException:
                pass

        # Description
        result["description"] = get_text(driver, [
            ".product.attribute.description .value",
            "[itemprop='description']",
            ".product-info-main .description",
            "#description .value",
            ".product-description",
        ])
        if result["description"]:
            result["description"] = result["description"][:500]

        # Image
        result["image_url"] = get_attr(driver, [
            ".product.media img.gallery-placeholder__image",
            ".fotorama__img",
            "img[itemprop='image']",
            ".product-image-photo",
            ".gallery-image",
        ], "src")

        # Artikelnummer / EAN from specs table
        try:
            rows = driver.find_elements(By.CSS_SELECTOR,
                "table.data.table.additional-attributes tr, "
                ".product.attribute.sku .value, "
                ".additional-attributes tr"
            )
            for row in rows:
                text = row.text.lower()
                if "ean" in text or "artikelnummer" in text or "barcode" in text:
                    cells = row.find_elements(By.CSS_SELECTOR, "td")
                    if len(cells) >= 2:
                        result["artikelnummer"] = cells[-1].text.strip()
                        break
        except Exception:
            pass

        print(f"  ✓ {result['name']} | {result['price']} | {result['stock_status']}")

    except TimeoutException:
        result["status"] = "timeout"
        result["error"] = "Product page timed out"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"  ✗ Error: {e}")

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) > 1:
        eans = sys.argv[1:]
    else:
        raw = input("Enter EAN code(s), comma or space separated: ")
        eans = re.split(r"[,\s]+", raw.strip())
        eans = [e.strip() for e in eans if e.strip()]

    if not eans:
        print("No EAN codes provided.")
        sys.exit(1)

    print(f"\n🌿 intratuin.nl EAN Scraper")
    print(f"   EANs to scrape: {eans}")
    print(f"   Launching headless Chrome...\n")

    driver = make_driver(headless=True)
    results = []

    try:
        for i, ean in enumerate(eans, 1):
            print(f"[{i}/{len(eans)}] Scraping EAN: {ean}")
            result = scrape_ean(ean, driver)
            results.append(result)
            if i < len(eans):
                time.sleep(2)  # Polite delay between products
    finally:
        driver.quit()

    # --- Export ---
    df = pd.DataFrame(results)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"intratuin_products_{ts}.xlsx"

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Products")
        ws = writer.sheets["Products"]

        # Auto-size columns
        for col in ws.columns:
            max_len = max(
                (len(str(c.value or "")) for c in col), default=10
            )
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)
        ws.freeze_panes = "A2"

    success = sum(1 for r in results if r["status"] == "success")
    print(f"\n{'='*50}")
    print(f"✓ Done! {success}/{len(results)} products scraped successfully.")
    print(f"✓ Output saved to: {output_file}")

    # Print summary
    for r in results:
        icon = "✓" if r["status"] == "success" else "✗"
        print(f"  {icon} {r['ean']} — {r.get('name') or r.get('error') or r['status']}")


if __name__ == "__main__":
    main()