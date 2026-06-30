"""
Scrape Amazon product data using DrissionPage (stealth browser).
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from DrissionPage import ChromiumPage, ChromiumOptions


def scrape_amazon_real(asin, marketplace="amazon.us"):
    """
    Scrape real Amazon product data using DrissionPage.
    Returns dict with price, rating, review_count, in_stock, name, image_url.
    """
    tld_map = {
        "amazon.us": "com",
        "amazon.uk": "co.uk",
        "amazon.de": "de",
        "amazon.fr": "fr",
        "amazon.jp": "co.jp",
        "amazon.ca": "ca",
        "amazon.it": "it",
        "amazon.es": "es",
    }
    tld = tld_map.get(marketplace, "com")
    url = f"https://www.amazon.{tld}/dp/{asin}"

    result = {
        "asin": asin,
        "marketplace": marketplace,
        "url": url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "price": None,
        "currency": "USD",
        "rating": None,
        "review_count": None,
        "in_stock": None,
        "name": "",
        "image_url": "",
    }

    print(f"[INFO] Opening {url} ...")

    co = ChromiumOptions()
    co.headless()  # Run in headless mode
    co.set_browser_path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    # Set a realistic user agent
    co.set_user_agent(
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    )

    page = ChromiumPage(co)
    
    try:
        page.get(url, timeout=30)
        time.sleep(3)  # Wait for JavaScript to render
        
        html = page.html
        
        # Check if we got a CAPTCHA
        if 'captcha' in html.lower() and len(html) < 5000:
            print("[WARN] CAPTCHA detected, page content too small")
            # Try waiting a bit more
            time.sleep(5)
            html = page.html

        # --- Product Name ---
        try:
            title_el = page.ele('#productTitle', timeout=3)
            if title_el:
                result["name"] = title_el.text.strip()
                print(f"[OK] Name: {result['name'][:60]}...")
        except:
            pass

        # --- Price ---
        try:
            # Try whole price + fraction
            whole_el = page.ele('.a-price-whole', timeout=2)
            fraction_el = page.ele('.a-price-fraction', timeout=1)
            if whole_el:
                whole = whole_el.text.replace(',', '').strip()
                fraction = fraction_el.text.strip() if fraction_el else '00'
                result["price"] = float(f"{whole}.{fraction}")
                print(f"[OK] Price: ${result['price']}")
        except:
            pass

        if result["price"] is None:
            try:
                price_el = page.ele('.a-price .a-offscreen', timeout=2)
                if price_el:
                    price_text = price_el.text.strip()
                    price_match = re.search(r'[\d,.]+', price_text)
                    if price_match:
                        result["price"] = float(price_match.group().replace(',', ''))
                        print(f"[OK] Price (alt): ${result['price']}")
            except:
                pass

        # Try to detect currency
        try:
            sym_el = page.ele('.a-price-symbol', timeout=1)
            if sym_el:
                sym = sym_el.text.strip()
                if '£' in sym:
                    result["currency"] = "GBP"
                elif '€' in sym:
                    result["currency"] = "EUR"
                elif '¥' in sym or '￥' in sym:
                    result["currency"] = "JPY"
        except:
            pass

        # --- Rating ---
        try:
            # Try a-icon-alt
            rating_el = page.ele('.a-icon-alt', timeout=2)
            if rating_el:
                rating_text = rating_el.text.strip()
                rating_match = re.search(r'([\d.]+)\s*out of', rating_text)
                if rating_match:
                    result["rating"] = float(rating_match.group(1))
                    print(f"[OK] Rating: {result['rating']}")
        except:
            pass

        if result["rating"] is None:
            try:
                # Try data hook for average rating
                rating_el = page.ele('[data-hook="rating-out-of-text"]', timeout=1)
                if rating_el:
                    rating_match = re.search(r'([\d.]+)', rating_el.text)
                    if rating_match:
                        result["rating"] = float(rating_match.group(1))
                        print(f"[OK] Rating (alt): {result['rating']}")
            except:
                pass

        # --- Review Count ---
        try:
            review_el = page.ele('#acrCustomerReviewText', timeout=2)
            if review_el:
                review_match = re.search(r'([\d,]+)', review_el.text)
                if review_match:
                    result["review_count"] = int(review_match.group(1).replace(',', ''))
                    print(f"[OK] Reviews: {result['review_count']}")
        except:
            pass

        if result["review_count"] is None:
            try:
                review_el = page.ele('[data-hook="total-review-count"]', timeout=1)
                if review_el:
                    review_match = re.search(r'([\d,]+)', review_el.text)
                    if review_match:
                        result["review_count"] = int(review_match.group(1).replace(',', ''))
                        print(f"[OK] Reviews (alt): {result['review_count']}")
            except:
                pass

        # --- Stock Status ---
        try:
            avail_el = page.ele('#availability span', timeout=2)
            if avail_el:
                text = avail_el.text.strip().lower()
                if any(kw in text for kw in ['in stock', 'only', 'available']):
                    result["in_stock"] = True
                elif any(kw in text for kw in ['out of stock', 'unavailable', 'currently unavailable']):
                    result["in_stock"] = False
                print(f"[OK] Stock: {result['in_stock']}")
        except:
            pass

        if result["in_stock"] is None:
            try:
                # Look for add to cart button
                cart_el = page.ele('#add-to-cart-button', timeout=1)
                if cart_el:
                    result["in_stock"] = True
                    print(f"[OK] Stock (cart btn): True")
                else:
                    # Check for out of stock text
                    if page.ele('#outOfStock', timeout=1):
                        result["in_stock"] = False
                        print(f"[OK] Stock (outOfStock): False")
            except:
                pass

        # --- Image URL ---
        try:
            img_el = page.ele('#landingImage', timeout=2)
            if img_el:
                src = img_el.attr('src') or img_el.attr('data-old-hires')
                if src:
                    result["image_url"] = src
                    print(f"[OK] Image: {src[:60]}...")
        except:
            pass

    except Exception as e:
        print(f"[ERROR] Page load failed: {e}")
    finally:
        try:
            page.quit()
        except:
            pass

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("asin", help="ASIN to scrape")
    parser.add_argument("--marketplace", "-m", default="amazon.us")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    result = scrape_amazon_real(args.asin, args.marketplace)
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n--- Result ---")
        print(f"Name:    {result['name']}")
        print(f"Price:   {result['price']} {result['currency']}")
        print(f"Rating:  {result['rating']} / 5.0")
        print(f"Reviews: {result['review_count']}")
        print(f"Stock:   {result['in_stock']}")
        print(f"Image:   {result['image_url']}")
