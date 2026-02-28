"""
Amanogawa.space scraper — headless Chrome via Playwright.
Captures all network requests to find API endpoints,
then dumps page content and any JSON API responses.
"""

import json
import sys
from playwright.sync_api import sync_playwright


def scrape_amanogawa():
    api_calls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Intercept all network requests to find API calls
        def handle_response(response):
            url = response.url
            content_type = response.headers.get("content-type", "")

            # Skip static assets
            if any(ext in url for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff", ".ico"]):
                return

            # Capture API/JSON responses
            if "json" in content_type or "/api/" in url or "graphql" in url:
                try:
                    body = response.json()
                    api_calls.append({
                        "url": url,
                        "status": response.status,
                        "content_type": content_type,
                        "body_preview": json.dumps(body, ensure_ascii=False)[:2000]
                    })
                except:
                    try:
                        text = response.text()
                        api_calls.append({
                            "url": url,
                            "status": response.status,
                            "content_type": content_type,
                            "body_preview": text[:2000]
                        })
                    except:
                        api_calls.append({
                            "url": url,
                            "status": response.status,
                            "content_type": content_type,
                            "body_preview": "(could not read body)"
                        })

        page.on("response", handle_response)

        # Go to main page
        print("=== Loading amanogawa.space ===")
        page.goto("https://amanogawa.space/", wait_until="networkidle", timeout=30000)

        # Wait for content to render
        page.wait_for_timeout(3000)

        # Get page title and content
        title = page.title()
        print(f"\nPage title: {title}")

        # Get all visible text
        body_text = page.inner_text("body")
        print(f"\n=== PAGE TEXT (first 3000 chars) ===\n{body_text[:3000]}")

        # Get all links
        links = page.eval_on_selector_all("a[href]", "els => els.map(e => ({text: e.innerText.trim(), href: e.href})).filter(x => x.text)")
        print(f"\n=== LINKS ({len(links)} total) ===")
        for link in links[:50]:
            print(f"  {link['text'][:60]:60s} → {link['href']}")

        # Print captured API calls
        print(f"\n=== API/JSON REQUESTS ({len(api_calls)} captured) ===")
        for call in api_calls:
            print(f"\n  URL: {call['url']}")
            print(f"  Status: {call['status']}")
            print(f"  Content-Type: {call['content_type']}")
            print(f"  Body: {call['body_preview'][:500]}")

        # Try to find anime catalog/list page
        # Look for navigation links that might lead to a catalog
        nav_links = page.eval_on_selector_all("a[href]", """
            els => els.map(e => ({text: e.innerText.trim(), href: e.href}))
                .filter(x => x.text && (
                    x.text.toLowerCase().includes('каталог') ||
                    x.text.toLowerCase().includes('catalog') ||
                    x.text.toLowerCase().includes('аніме') ||
                    x.text.toLowerCase().includes('anime') ||
                    x.text.toLowerCase().includes('бібліотека') ||
                    x.text.toLowerCase().includes('library') ||
                    x.text.toLowerCase().includes('список') ||
                    x.text.toLowerCase().includes('релізи') ||
                    x.text.toLowerCase().includes('release') ||
                    x.text.toLowerCase().includes('torrent') ||
                    x.text.toLowerCase().includes('торент')
                ))
        """)

        if nav_links:
            print(f"\n=== CATALOG/ANIME LINKS FOUND ===")
            for link in nav_links:
                print(f"  {link['text']} → {link['href']}")

            # Try visiting the first catalog-like link
            catalog_url = nav_links[0]['href']
            print(f"\n=== Loading catalog page: {catalog_url} ===")

            api_calls.clear()
            page.goto(catalog_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            catalog_text = page.inner_text("body")
            print(f"\n=== CATALOG PAGE TEXT (first 3000 chars) ===\n{catalog_text[:3000]}")

            print(f"\n=== CATALOG API REQUESTS ({len(api_calls)} captured) ===")
            for call in api_calls:
                print(f"\n  URL: {call['url']}")
                print(f"  Status: {call['status']}")
                print(f"  Body: {call['body_preview'][:1000]}")

        browser.close()


if __name__ == "__main__":
    scrape_amanogawa()
