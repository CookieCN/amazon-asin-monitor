/**
 * Amazon real scraper using puppeteer-extra with stealth plugin.
 * Extracts price, rating, review count, stock status, name, and image.
 */
import puppeteer from 'puppeteer-core';
import StealthPlugin from 'puppeteer-extra-plugin-stealth';
import { writeFileSync, existsSync, readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

puppeteer.use(StealthPlugin());

const ASIN = process.argv[2] || 'B0FKHC8PPV';
const MARKETPLACE = process.argv[3] || 'amazon.us';

const tldMap = {
  'amazon.us': 'com',
  'amazon.uk': 'co.uk',
  'amazon.de': 'de',
  'amazon.fr': 'fr',
  'amazon.jp': 'co.jp',
  'amazon.ca': 'ca',
  'amazon.it': 'it',
  'amazon.es': 'es',
};

const tld = tldMap[MARKETPLACE] || 'com';
const url = `https://www.amazon.${tld}/dp/${ASIN}`;

console.log(`[INFO] Opening ${url} with stealth browser...`);

async function scrape() {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: [
      '--disable-blink-features=AutomationControlled',
      '--disable-dev-shm-usage',
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-infobars',
      '--window-size=1920,1080',
    ],
  });

  const page = await browser.newPage();

  // Set realistic viewport and user agent
  await page.setViewport({ width: 1920, height: 1080 });
  await page.setUserAgent(
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
  );

  // Set extra headers
  await page.setExtraHTTPHeaders({
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
  });

  // Block unnecessary resources
  await page.setRequestInterception(true);
  page.on('request', (req) => {
    const type = req.resourceType();
    if (type === 'image' || type === 'font' || type === 'media') {
      req.abort();
    } else {
      req.continue();
    }
  });

  const result = {
    asin: ASIN,
    marketplace: MARKETPLACE,
    url,
    timestamp: new Date().toISOString(),
    price: null,
    currency: 'USD',
    rating: null,
    review_count: null,
    in_stock: null,
    name: '',
    image_url: '',
  };

  try {
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });

    // Wait for critical elements
    await page.waitForTimeout(3000);

    const title = await page.title();
    console.log(`[INFO] Page title: ${title.substring(0, 80)}`);

    // Check for CAPTCHA
    const pageText = await page.evaluate(() => document.body.innerText);
    if (pageText.includes('Enter the characters you see below') || 
        pageText.includes('Sorry, we just need to make sure') ||
        pageText.includes('Type the characters')) {
      console.log('[ERROR] CAPTCHA detected!');
      // Take screenshot for debugging
      await page.screenshot({ path: join(__dirname, 'captcha_debug.png') });
      console.log('[INFO] Screenshot saved to captcha_debug.png');
    }

    // --- Product Name ---
    try {
      result.name = await page.$eval('#productTitle', el => el.textContent.trim());
      console.log(`[OK] Name: ${result.name.substring(0, 60)}...`);
    } catch (e) {
      console.log('[WARN] Could not find productTitle');
    }

    // --- Price ---
    try {
      const priceWhole = await page.$eval('.a-price-whole', el => el.textContent.replace(',', '').trim());
      let priceFraction = '00';
      try {
        priceFraction = await page.$eval('.a-price-fraction', el => el.textContent.trim());
      } catch (e) {}
      result.price = parseFloat(`${priceWhole}.${priceFraction}`);
      console.log(`[OK] Price: $${result.price}`);
    } catch (e) {
      // Try alternative price selectors
      try {
        const priceText = await page.$eval('.a-price .a-offscreen', el => el.textContent.trim());
        const match = priceText.match(/[\d,.]+/);
        if (match) {
          result.price = parseFloat(match[0].replace(/,/g, ''));
          console.log(`[OK] Price (alt): $${result.price}`);
        }
      } catch (e2) {
        console.log('[WARN] Could not find price');
      }
    }

    // --- Currency ---
    try {
      const sym = await page.$eval('.a-price-symbol', el => el.textContent.trim());
      if (sym.includes('£')) result.currency = 'GBP';
      else if (sym.includes('€')) result.currency = 'EUR';
      else if (sym.includes('¥') || sym.includes('￥')) result.currency = 'JPY';
    } catch (e) {}

    // --- Rating ---
    try {
      const ratingText = await page.$eval('.a-icon-alt', el => el.textContent.trim());
      const match = ratingText.match(/([\d.]+)\s*out of/);
      if (match) {
        result.rating = parseFloat(match[1]);
        console.log(`[OK] Rating: ${result.rating}`);
      }
    } catch (e) {
      try {
        const ratingText = await page.$eval('[data-hook="rating-out-of-text"]', el => el.textContent);
        const match = ratingText.match(/([\d.]+)/);
        if (match) result.rating = parseFloat(match[1]);
        console.log(`[OK] Rating (alt): ${result.rating}`);
      } catch (e2) {
        console.log('[WARN] Could not find rating');
      }
    }

    // --- Review Count ---
    try {
      const reviewText = await page.$eval('#acrCustomerReviewText', el => el.textContent.trim());
      const match = reviewText.match(/([\d,]+)/);
      if (match) {
        result.review_count = parseInt(match[1].replace(/,/g, ''));
        console.log(`[OK] Reviews: ${result.review_count}`);
      }
    } catch (e) {
      try {
        const reviewText = await page.$eval('[data-hook="total-review-count"]', el => el.textContent);
        const match = reviewText.match(/([\d,]+)/);
        if (match) result.review_count = parseInt(match[1].replace(/,/g, ''));
        console.log(`[OK] Reviews (alt): ${result.review_count}`);
      } catch (e2) {
        console.log('[WARN] Could not find review count');
      }
    }

    // --- Stock Status ---
    try {
      const availText = await page.$eval('#availability span', el => el.textContent.trim().toLowerCase());
      if (availText.includes('in stock') || availText.includes('only')) {
        result.in_stock = true;
      } else if (availText.includes('out of stock') || availText.includes('unavailable')) {
        result.in_stock = false;
      }
      console.log(`[OK] Stock: ${result.in_stock}`);
    } catch (e) {
      // Check for add to cart button
      try {
        await page.$eval('#add-to-cart-button', el => true);
        result.in_stock = true;
        console.log('[OK] Stock (cart): true');
      } catch (e2) {
        try {
          await page.$eval('#outOfStock', el => true);
          result.in_stock = false;
          console.log('[OK] Stock (oos): false');
        } catch (e3) {
          console.log('[WARN] Could not determine stock');
        }
      }
    }

    // --- Image URL ---
    try {
      result.image_url = await page.$eval('#landingImage', el => el.src || el.getAttribute('data-old-hires'));
      console.log(`[OK] Image: ${result.image_url?.substring(0, 60)}...`);
    } catch (e) {
      console.log('[WARN] Could not find image');
    }

  } catch (e) {
    console.error(`[ERROR] ${e.message}`);
  } finally {
    await browser.close();
  }

  return result;
}

scrape().then(result => {
  // Save to data file
  const dataPath = join(__dirname, 'data', `${ASIN}.json`);
  
  // Read existing data
  let existing = { asin: ASIN, history: [], marketplace: MARKETPLACE, name: '', image_url: '', url };
  try {
    if (existsSync(dataPath)) {
      existing = JSON.parse(readFileSync(dataPath, 'utf-8'));
    }
  } catch (e) {}

  // Update metadata
  if (result.name) existing.name = result.name;
  if (result.image_url) existing.image_url = result.image_url;
  existing.marketplace = MARKETPLACE;
  existing.url = url;

  // Append new data point
  existing.history.push({
    timestamp: result.timestamp,
    price: result.price,
    currency: result.currency,
    rating: result.rating,
    review_count: result.review_count,
    in_stock: result.in_stock,
  });

  // Keep only last 200 entries
  if (existing.history.length > 200) {
    existing.history = existing.history.slice(-200);
  }

  writeFileSync(dataPath, JSON.stringify(existing, null, 2));
  console.log(`\n[DONE] Data saved to data/${ASIN}.json`);
  console.log(JSON.stringify(result, null, 2));
});
