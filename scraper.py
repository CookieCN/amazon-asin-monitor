"""
Amazon ASIN Monitor - Anti-Detection Scraper
Multiple layers of anti-detection to survive scraping:
  Layer 1 — Large UA pool with matching Sec-Ch-Ua headers
  Layer 2 — Cookie persistence (saves across runs, builds trust)
  Layer 3 — Homepage warm-up (mimics human browsing)
  Layer 4 — Jittered delays & exponential backoff
  Layer 5 — Google referrer chain
  Layer 6 — Multiple parse strategies per field
  Layer 7 — Graceful degradation (null > fake data)
"""
import json
import os
import re
import sys
import time
import random
import pickle
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ─── Paths ───────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"
CONFIG_FILE = DATA_DIR / "config.json"
COOKIE_DIR = DATA_DIR / "cookies"
SESSION_STATE_FILE = DATA_DIR / "scraper_state.json"

# ─── Rotating User-Agent Pool (30+ real browser UAs) ─────────
# Each entry: (user_agent, sec_ch_ua, sec_ch_ua_platform)
# sec_ch_ua values must match the Chrome version in UA
UA_POOL = [
    # Chrome 126 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        '"Not/A)Brand";v="99", "Google Chrome";v="126", "Chromium";v="126"',
        '"Windows"',
    ),
    # Chrome 126 — Mac
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        '"Not/A)Brand";v="99", "Google Chrome";v="126", "Chromium";v="126"',
        '"macOS"',
    ),
    # Chrome 125 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        '"Not/A)Brand";v="99", "Google Chrome";v="125", "Chromium";v="125"',
        '"Windows"',
    ),
    # Chrome 125 — Mac
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        '"Not/A)Brand";v="99", "Google Chrome";v="125", "Chromium";v="125"',
        '"macOS"',
    ),
    # Chrome 127 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        '"Not/A)Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
        '"Windows"',
    ),
    # Chrome 127 — Mac
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        '"Not/A)Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
        '"macOS"',
    ),
    # Chrome 124 — Win 11
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        '"Not/A)Brand";v="99", "Google Chrome";v="124", "Chromium";v="124"',
        '"Windows"',
    ),
    # Chrome 124 — Mac
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        '"Not/A)Brand";v="99", "Google Chrome";v="124", "Chromium";v="124"',
        '"macOS"',
    ),
    # Firefox 127 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
        None, None,
    ),
    # Firefox 127 — Mac
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:127.0) Gecko/20100101 Firefox/127.0",
        None, None,
    ),
    # Firefox 126 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        None, None,
    ),
    # Safari 17.5 — Mac
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        None, None,
    ),
    # Edge 126 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
        '"Not/A)Brand";v="99", "Microsoft Edge";v="126", "Chromium";v="126"',
        '"Windows"',
    ),
    # Edge 125 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
        '"Not/A)Brand";v="99", "Microsoft Edge";v="125", "Chromium";v="125"',
        '"Windows"',
    ),
    # Chrome 123 — Win 10
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        '"Not/A)Brand";v="99", "Google Chrome";v="123", "Chromium";v="123"',
        '"Windows"',
    ),
    # Chrome 128 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        '"Not/A)Brand";v="99", "Google Chrome";v="128", "Chromium";v="128"',
        '"Windows"',
    ),
    # Chrome 128 — Mac
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        '"Not/A)Brand";v="99", "Google Chrome";v="128", "Chromium";v="128"',
        '"macOS"',
    ),
]

AMAZON_TLDS = {
    "amazon.us": "com", "amazon.uk": "co.uk", "amazon.de": "de",
    "amazon.fr": "fr", "amazon.jp": "co.jp", "amazon.ca": "ca",
    "amazon.it": "it", "amazon.es": "es", "amazon.in": "in",
    "amazon.com.br": "com.br", "amazon.com.mx": "com.mx",
    "amazon.com.au": "com.au", "amazon.nl": "nl",
}

CAPTCHA_PATTERNS = [
    "opfcaptcha", "captcha", "type the characters",
    "enter the characters", "robot check", "sorry! something went wrong",
    "automated access", "api-services-support", "validate your request",
    "To discuss automated access", "Amazon.com.au",
]

MIN_PAGE_SIZE = 15000  # Anything smaller = likely block page

# ─── Helpers ─────────────────────────────────────────────────

def jitter(base, pct=0.3):
    """Add +/- pct jitter to a value. Always positive."""
    lo = base * (1 - pct)
    hi = base * (1 + pct)
    return random.uniform(max(0.5, lo), hi)


def load_config():
    if not CONFIG_FILE.exists():
        return {"asins": [], "settings": {"check_interval_hours": 12, "retention_days": 90}}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_asin_data(asin):
    filepath = DATA_DIR / f"{asin}.json"
    if not filepath.exists():
        return {"asin": asin, "history": [], "marketplace": "", "name": "", "image_url": "", "url": ""}
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_asin_data(asin, data):
    filepath = DATA_DIR / f"{asin}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_captcha_page(html, status_code):
    """
    Detect CAPTCHA / bot-wall pages.
    Returns True if we got blocked.
    """
    if status_code == 503:
        return True

    html_lower = html.lower()
    # Size check: real Amazon product pages are >100KB
    if len(html) < MIN_PAGE_SIZE:
        for pat in CAPTCHA_PATTERNS:
            if pat in html_lower:
                return True
        if "<!DOCTYPE html>" in html_lower and len(html) < 8000:
            # A tiny HTML page that's not a product = likely block
            return True

    # Check title for known block patterns
    title_match = re.search(r'<title>(.*?)</title>', html_lower)
    if title_match:
        title = title_match.group(1)
        if title.strip() in ("amazon.com",):
            # If title is just "Amazon.com" and no product data, suspicious
            if "productTitle" not in html and len(html) < 30000:
                return True

    return False


def get_cookie_path(marketplace):
    """Get cookie file path for a marketplace."""
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    return COOKIE_DIR / f"{marketplace.replace('.', '_')}.pkl"


def save_cookies(session, marketplace):
    """Persist cookies to disk for session reuse."""
    cookie_path = get_cookie_path(marketplace)
    try:
        with open(cookie_path, "wb") as f:
            pickle.dump(session.cookies, f)
    except Exception:
        pass


def load_cookies(session, marketplace):
    """Load previously saved cookies."""
    cookie_path = get_cookie_path(marketplace)
    if not cookie_path.exists():
        return False
    try:
        with open(cookie_path, "rb") as f:
            cookies = pickle.load(f)
        session.cookies.update(cookies)
        # Don't use stale cookies (>24h), but keep them for now
        return True
    except Exception:
        return False


# ─── Session Factory ─────────────────────────────────────────

def build_session(marketplace="amazon.us"):
    """
    Create a requests.Session with full anti-detection measures:
    - Random UA from pool with matching Sec-Ch-Ua
    - All headers a real Chrome browser sends
    - Cookie jar loaded from previous sessions
    - TLS settings (via requests)
    """
    sess = requests.Session()

    # Pick a random UA profile
    ua, sec_ch_ua, sec_ch_ua_platform = random.choice(UA_POOL)

    # Browser-like Accept-Language pattern
    languages = [
        "en-US,en;q=0.9",
        "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "en;q=0.9,en-US;q=0.8",
    ]

    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": random.choice(languages),
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Sec-GPC": "1",
        "Pragma": "no-cache",
    }

    # Add Chrome-specific sec-ch-ua headers (only for Chromium UAs)
    if sec_ch_ua:
        headers["Sec-Ch-Ua"] = sec_ch_ua
    if sec_ch_ua_platform:
        headers["Sec-Ch-Ua-Platform"] = sec_ch_ua_platform
    headers["Sec-Ch-Ua-Mobile"] = "?0"

    sess.headers.update(headers)

    # Load persisted cookies for session continuity
    load_cookies(sess, marketplace)

    return sess


# ─── Warm-Up ─────────────────────────────────────────────────

def warmup_session(sess, marketplace="amazon.us"):
    """
    Visit Amazon homepage first to build session trust.
    Mimics what a real user does: browse homepage, then search.
    """
    tld = AMAZON_TLDS.get(marketplace, "com")
    homepage = f"https://www.amazon.{tld}/"

    try:
        # Visit homepage with a referrer from Google
        referrers = [
            "https://www.google.com/",
            "https://www.google.com/search?q=amazon",
            "https://www.bing.com/",
        ]
        # First request: come from Google with a small delay
        time.sleep(jitter(0.8, 0.5))  # Human-like initial delay

        sess.headers["Referer"] = random.choice(referrers)
        resp = sess.get(homepage, timeout=20, allow_redirects=True)

        if resp.status_code == 200:
            save_cookies(sess, marketplace)
            return True
        return False
    except Exception:
        return False


# ─── Parsers ─────────────────────────────────────────────────

def parse_price(soup):
    """Multi-strategy price extraction — prioritizes buy-box/main price."""
    # Strategy 1: BuyBox-specific price (most reliable for deal/variant pages)
    # Look for .a-price-whole INSIDE the buybox/priceblock areas first
    buybox_selectors = [
        "#corePriceDisplay_desktop_feature_div .a-price-whole",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#priceblock_saleprice",
        ".a-price.a-text-price .a-price-whole",
        ".apexPriceToPay .a-price-whole",
        "[data-feature-name='price'] .a-price-whole",
    ]
    for sel in buybox_selectors:
        el = soup.select_one(sel)
        if el:
            whole = re.sub(r'[^\d]', '', el.text)
            parent = el.find_parent(class_=re.compile(r'a-price'))
            fraction_el = parent.select_one(".a-price-fraction") if parent else None
            fraction = re.sub(r'[^\d]', '', fraction_el.text) if fraction_el else "00"
            if whole:
                try:
                    return float(f"{whole}.{fraction}")
                except ValueError:
                    pass

    # Strategy 1b: generic .a-price-whole (first occurrence, usually main price)
    whole_el = soup.select_one(".a-price-whole")
    if whole_el:
        whole = re.sub(r'[^\d]', '', whole_el.text)
        # Find sibling fraction within same a-price container
        parent = whole_el.find_parent(class_=re.compile(r'a-price'))
        fraction_el = parent.select_one(".a-price-fraction") if parent else None
        fraction = re.sub(r'[^\d]', '', fraction_el.text) if fraction_el else "00"
        if whole and fraction:
            try:
                return float(f"{whole}.{fraction}")
            except ValueError:
                pass

    # Strategy 2: .a-price .a-offscreen (hidden accessible price)
    offscreen = soup.select_one(".a-price .a-offscreen")
    if offscreen:
        match = re.search(r'[\d,.]+', offscreen.text)
        if match:
            try:
                return float(match.group().replace(",", ""))
            except ValueError:
                pass

    # Strategy 3: any span containing $ — BUT skip variant/option prices
    # Variant prices are typically in twister/selection areas, exclude those
    variant_containers = [
        "#twister", "#variation_price", "#variationPrice",
        ".twisterContainer", ".a-touch-preview",
    ]
    seen_prices = []
    for span in soup.find_all("span", string=re.compile(r'\$\s*[\d,.]+')):
        match = re.search(r'\$\s*([\d,.]+)', span.text)
        if match:
            try:
                val = float(match.group(1).replace(",", ""))
                if not (0.01 < val < 100000):
                    continue
                # Check if this span is inside a variant/twister area
                for ancestor in span.parents:
                    anc_id = ancestor.get("id", "") or ""
                    anc_class = " ".join(ancestor.get("class", []))
                    for vc_id in ["twister", "variationPrice", "variation_price",
                                  "optionPrice", "exclusive"]:
                        if vc_id.lower() in anc_id.lower() or vc_id.lower() in anc_class.lower():
                            break  # Skip this price, it's a variant
                    else:
                        continue
                    break
                else:
                    # Not inside a variant container — good candidate
                    return val
                seen_prices.append(val)
            except ValueError:
                pass

    # Fallback: if we only found variant prices, take the lowest reasonable one
    if seen_prices:
        return min(seen_prices)

    # Strategy 4: data attributes
    for el in soup.find_all(attrs={"data-a-size": "xl"}):
        text = el.get_text(strip=True)
        match = re.search(r'\$\s*([\d,.]+)', text)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                pass

    # Strategy 5: corePriceDisplay_desktop_feature_div
    core_price = soup.select_one("#corePriceDisplay_desktop_feature_div")
    if core_price:
        match = re.search(r'([\d,.]+)', core_price.get_text())
        if match:
            try:
                val = float(match.group(1).replace(",", ""))
                if 1 < val < 100000:
                    return val
            except ValueError:
                pass

    return None


def parse_currency(soup):
    sym_el = soup.select_one(".a-price-symbol")
    if sym_el:
        sym = sym_el.text.strip()
        mapping = {"£": "GBP", "€": "EUR", "¥": "JPY", "￥": "JPY", "₹": "INR", "CDN$": "CAD"}
        return mapping.get(sym, "USD")
    return "USD"


def parse_rating(soup):
    """Multi-strategy rating extraction."""
    # Strategy 1: a-icon-alt
    icon_alt = soup.select_one(".a-icon-alt")
    if icon_alt:
        match = re.search(r'([\d.]+)\s*out of\s*5', icon_alt.text)
        if match:
            return float(match.group(1))

    # Strategy 2: data-hook rating
    rating_el = soup.select_one('[data-hook="rating-out-of-text"]')
    if rating_el:
        match = re.search(r'([\d.]+)', rating_el.text)
        if match:
            return float(match.group(1))

    # Strategy 3: "X out of 5 stars" anywhere
    for el in soup.find_all(string=re.compile(r'out of 5 stars', re.I)):
        match = re.search(r'([\d.]+)\s*out of', el, re.I)
        if match:
            rating = float(match.group(1))
            if 1.0 <= rating <= 5.0:
                return rating

    # Strategy 4: #averageCustomerReviews
    acr = soup.select_one("#averageCustomerReviews")
    if acr:
        match = re.search(r'([\d.]+)', acr.get_text())
        if match:
            rating = float(match.group(1))
            if 1.0 <= rating <= 5.0:
                return rating

    return None


def parse_review_count(soup):
    """Extract review count with multiple strategies."""
    # Strategy 1: #acrCustomerReviewText
    review_el = soup.select_one("#acrCustomerReviewText")
    if review_el:
        match = re.search(r'([\d,]+)', review_el.text)
        if match:
            count = int(match.group(1).replace(",", ""))
            if count > 0:
                return count

    # Strategy 2: data-hook total-review-count
    total_el = soup.select_one('[data-hook="total-review-count"]')
    if total_el:
        match = re.search(r'([\d,]+)', total_el.text)
        if match:
            count = int(match.group(1).replace(",", ""))
            if count > 0:
                return count

    # Strategy 3: "X ratings" anywhere, with threshold
    for el in soup.find_all(string=re.compile(r'ratings?', re.I)):
        match = re.search(r'([\d,]+)\s*ratings?', el, re.I)
        if match:
            count = int(match.group(1).replace(",", ""))
            if count >= 10:
                return count

    return None


def parse_stock(soup):
    """Determine stock status."""
    # Strategy 1: #availability span
    avail = soup.select_one("#availability span")
    if avail:
        text = avail.text.strip().lower()
        if any(kw in text for kw in ["in stock", "only", "available", "left"]):
            return True
        if any(kw in text for kw in ["out of stock", "currently unavailable", "temporarily out"]):
            return False

    # Strategy 2: Add-to-cart button exists
    if soup.select_one("#add-to-cart-button") or soup.select_one("#submit\\.add-to-cart"):
        return True

    # Strategy 3: #outOfStock div
    if soup.select_one("#outOfStock"):
        return False

    # Strategy 4: Text search
    for el in soup.find_all(["span", "div"], string=re.compile(r"In Stock", re.I)):
        return True
    for el in soup.find_all(["span", "div"], string=re.compile(r"Currently unavailable", re.I)):
        return False

    return None


def parse_name(soup):
    title_el = soup.select_one("#productTitle")
    if title_el:
        return title_el.text.strip()
    return ""


def parse_image_url(soup, asin):
    img = soup.select_one("#landingImage")
    if img:
        return img.get("src") or img.get("data-old-hires", "")
    return ""


# ─── Core Scraping Logic ─────────────────────────────────────

def scrape_amazon_page(asin, marketplace="amazon.us", max_retries=3):
    """
    Scrape Amazon product page with full anti-detection stack.
    Retries with exponential backoff on failure.
    Returns dict with scraped fields, or None on persistent failure.
    """
    tld = AMAZON_TLDS.get(marketplace, "com")
    url = f"https://www.amazon.{tld}/dp/{asin}"

    for attempt in range(max_retries):
        # Fresh session each retry (new UA, new cookie context if needed)
        sess = build_session(marketplace)

        # Pre-request jitter (human doesn't retry instantly)
        if attempt > 0:
            backoff = jitter(2 ** attempt * 10, 0.5)  # 10s, 20s, 40s
            print(f"  [RETRY {attempt + 1}/{max_retries}] waiting {backoff:.0f}s...")
            time.sleep(backoff)

        try:
            # Step 1: Warm-up — visit homepage first (only on first attempt)
            if attempt == 0:
                warmup_session(sess, marketplace)
                # Short browse delay
                time.sleep(jitter(1.5, 0.4))

            # Step 2: Navigate to product page (with referrer)
            referrers = [
                f"https://www.amazon.{tld}/",
                f"https://www.amazon.{tld}/s?k=electronics",
                "https://www.google.com/",
            ]
            sess.headers["Referer"] = random.choice(referrers)

            resp = sess.get(url, timeout=30, allow_redirects=True)

            if resp.status_code not in (200, 404):
                print(f"  [HTTP {resp.status_code}] attempt {attempt + 1}")
                if resp.status_code == 503:
                    # Server busy — definitely need to back off
                    continue
                if resp.status_code >= 500:
                    continue
                return None

            html = resp.text

            # Step 3: CAPTCHA / block detection
            if is_captcha_page(html, resp.status_code):
                print(f"  [BLOCKED] CAPTCHA/bot-wall detected (attempt {attempt + 1})")
                # Clear cookies on block — stale cookies may be flagged
                cookie_path = get_cookie_path(marketplace)
                if cookie_path.exists():
                    cookie_path.unlink()
                continue

            # Step 4: Parse
            soup = BeautifulSoup(html, "lxml")

            price = parse_price(soup)
            currency = parse_currency(soup)
            rating = parse_rating(soup)
            review_count = parse_review_count(soup)
            in_stock = parse_stock(soup)
            name = parse_name(soup)
            image_url = parse_image_url(soup, asin)

            # If we got absolutely nothing, page might be a subtle block
            if not name and not price:
                print(f"  [BLOCKED?] No product data found (attempt {attempt + 1})")
                continue

            # Success! Save cookies for next run
            save_cookies(sess, marketplace)

            # Emulate human: stay on page for a bit (reading time)
            time.sleep(jitter(2.0, 0.5))

            return {
                "asin": asin,
                "marketplace": marketplace,
                "url": url,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "price": price,
                "currency": currency,
                "rating": rating,
                "review_count": review_count,
                "in_stock": in_stock,
                "name": name,
                "image_url": image_url,
            }

        except requests.Timeout:
            print(f"  [TIMEOUT] attempt {attempt + 1}")
            continue
        except requests.ConnectionError:
            print(f"  [CONNECTION] attempt {attempt + 1}")
            continue
        except Exception as e:
            print(f"  [ERROR] {type(e).__name__}: {e}")
            continue

    # All retries exhausted
    print(f"  [GIVE UP] All {max_retries} attempts failed for {asin}")
    return None


def fetch_and_save(asin_entry):
    """Fetch data and persist. Only saves real values (nulls are OK)."""
    asin = asin_entry["asin"]
    marketplace = asin_entry.get("marketplace", "amazon.us")

    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {asin} ({marketplace})")

    result = scrape_amazon_page(asin, marketplace)

    existing = load_asin_data(asin)

    if result is None:
        tld = AMAZON_TLDS.get(marketplace, "com")
        existing["asin"] = asin
        existing["marketplace"] = existing.get("marketplace") or marketplace
        existing["url"] = existing.get("url") or f"https://www.amazon.{tld}/dp/{asin}"
        if not existing.get("history"):
            existing["history"] = []
        save_asin_data(asin, existing)
        print(f"  -> [SKIP] Blocked/failed, no data saved")
        return False

    # Update metadata
    existing["marketplace"] = marketplace
    if result["name"]:
        existing["name"] = result["name"]
        asin_entry["name"] = result["name"]
    if result["image_url"]:
        existing["image_url"] = result["image_url"]
        asin_entry["image_url"] = result["image_url"]
    existing["url"] = result["url"]

    # Append data point
    existing.setdefault("history", []).append({
        "timestamp": result["timestamp"],
        "price": result["price"],
        "currency": result["currency"],
        "rating": result["rating"],
        "review_count": result["review_count"],
        "in_stock": result["in_stock"],
    })

    # Prune old data
    config = load_config()
    retention = config["settings"].get("retention_days", 90)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
    existing["history"] = [
        h for h in existing["history"]
        if datetime.fromisoformat(h["timestamp"]) > cutoff
    ]

    save_asin_data(asin, existing)

    # Log
    def fmt(v, f=None):
        if v is None: return "N/A"
        return f(v) if f else str(v)

    print(f"  -> Price={fmt(result['price'], lambda x: f'${x:.2f}')} "
          f"Rating={fmt(result['rating'], lambda x: f'{x:.1f}*')} "
          f"Reviews={fmt(result['review_count'])} "
          f"Stock={'InStock' if result['in_stock'] is True else ('OOS' if result['in_stock'] is False else '?')}")

    return True


def run_all():
    config = load_config()
    active = [e for e in config["asins"] if e.get("active", True)]

    if not active:
        print("[INFO] No active ASINs")
        return

    print(f"[INFO] Running {len(active)} ASIN(s) at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    success = 0
    for i, entry in enumerate(active):
        if i > 0:
            # Human-like inter-request delay: 3-8 seconds
            delay = jitter(5, 0.5)
            print(f"\n  --- waiting {delay:.0f}s ---")
            time.sleep(delay)

        print(f"\n[{i+1}/{len(active)}]", end=" ")
        if fetch_and_save(entry):
            success += 1

    save_config(config)
    print(f"\n[DONE] {success}/{len(active)} successful, "
          f"{len(active) - success} blocked/failed")


def add_asin(asin, marketplace="amazon.us", name=""):
    config = load_config()
    for entry in config["asins"]:
        if entry["asin"] == asin and entry.get("marketplace") == marketplace:
            print(f"[INFO] {asin} already in list")
            return False

    tld = AMAZON_TLDS.get(marketplace, "com")
    entry = {
        "asin": asin,
        "marketplace": marketplace,
        "name": name,
        "image_url": "",
        "url": f"https://www.amazon.{tld}/dp/{asin}",
        "added_at": datetime.now(timezone.utc).isoformat(),
        "active": True,
    }
    config["asins"].append(entry)
    save_config(config)

    data = {
        "asin": asin, "marketplace": marketplace,
        "name": name or asin, "image_url": "", "url": entry["url"],
        "history": [],
    }
    save_asin_data(asin, data)

    print(f"[OK] Added {asin}")
    print(f"[INFO] Fetching initial data...")
    fetch_and_save(entry)
    save_config(config)
    return True


def get_summary():
    config = load_config()
    summary = []
    for entry in config["asins"]:
        data = load_asin_data(entry["asin"])
        history = data.get("history", [])
        latest = history[-1] if history else {}
        summary.append({
            "asin": entry["asin"],
            "marketplace": entry.get("marketplace", "amazon.us"),
            "name": entry.get("name", data.get("name", "")),
            "image_url": entry.get("image_url", data.get("image_url", "")),
            "url": entry.get("url", data.get("url", "")),
            "active": entry.get("active", True),
            "price": latest.get("price"),
            "currency": latest.get("currency", "USD"),
            "rating": latest.get("rating"),
            "review_count": latest.get("review_count"),
            "in_stock": latest.get("in_stock"),
            "last_updated": latest.get("timestamp"),
            "data_points": len(history),
        })
    return summary


def clear_cookies(marketplace=None):
    """Clear all or specific marketplace cookies."""
    if marketplace:
        p = get_cookie_path(marketplace)
        if p.exists():
            p.unlink()
            print(f"[OK] Cleared cookies for {marketplace}")
    else:
        for f in COOKIE_DIR.glob("*.pkl"):
            f.unlink()
        print("[OK] Cleared all cookies")


# ─── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Amazon ASIN Anti-Detection Scraper")
    parser.add_argument("action", nargs="?", default="run",
                        choices=["run", "add", "remove", "summary", "init", "clear-cookies"])
    parser.add_argument("--asin", "-a")
    parser.add_argument("--marketplace", "-m", default="amazon.us")
    parser.add_argument("--name", "-n", default="")

    args = parser.parse_args()

    if args.action == "clear-cookies":
        clear_cookies(args.marketplace if args.marketplace != "amazon.us" else None)

    elif args.action == "init":
        config = load_config()
        if not config["asins"]:
            add_asin("B0FKHC8PPV", "amazon.us")
        else:
            for entry in config["asins"]:
                fetch_and_save(entry)
            save_config(config)
        print("[DONE]")

    elif args.action == "add":
        if not args.asin:
            print("Error: --asin required", file=sys.stderr)
            sys.exit(1)
        add_asin(args.asin, args.marketplace, args.name)

    elif args.action == "run":
        if args.asin:
            config = load_config()
            entry = next((e for e in config["asins"] if e["asin"] == args.asin), None)
            if entry:
                fetch_and_save(entry)
                save_config(config)
            else:
                print(f"Error: {args.asin} not found", file=sys.stderr)
                sys.exit(1)
        else:
            run_all()

    elif args.action == "summary":
        print(json.dumps(get_summary(), indent=2, ensure_ascii=False))
