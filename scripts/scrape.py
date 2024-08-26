import os
import shutil
import urllib.parse
import re
import requests
import time
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

def safe_filename(url):
    """Generate a safe filename from a URL."""
    filename = re.sub(r'[^\w\-_\.]', '_', os.path.basename(urllib.parse.urlparse(url).path))
    return filename

def cleanup_directories():
    """Clean up directories before scraping."""
    if os.path.exists("index.html"):
        os.remove("index.html")
    
    if os.path.exists("images"):
        shutil.rmtree("images")
    
    if os.path.exists("pages"):
        shutil.rmtree("pages")

def remove_wix_ads(html_content):
    """Remove Wix ads from the HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    wix_ad_containers = soup.find_all(id="WIX_ADS")
    for ad in wix_ad_containers:
        ad.decompose()
    return str(soup)

async def download_asset(url, asset_folder, filename):
    """Download an asset (e.g., image) and save it in the asset folder."""
    try:
        response = requests.get(url)
        response.raise_for_status()

        file_path = os.path.join(asset_folder, filename)
        with open(file_path, 'wb') as file:
            file.write(response.content)
        print(f"Downloaded asset: {filename}")

    except Exception as e:
        print(f"Failed to download asset {url}: {e}")

def to_camel_case(text):
    """Convert a string to camelCase."""
    words = re.sub(r'[^\w\s]', '', text).split()
    camel_case_text = words[0].lower() + ''.join(word.capitalize() for word in words[1:])
    return camel_case_text

async def save_page(page, url, filename, asset_folder, main_domain, max_retries=3):
    """Visit the page, wait for it to load, replace URLs, remove ads, and save the HTML content."""
    retries = 0
    while retries < max_retries:
        try:
            await page.goto(url, timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=60000)

            # Replace image URLs with local paths
            content = await page.content()
            image_elements = await page.query_selector_all("img")

            for img in image_elements:
                img_url = await img.get_attribute("src")
                if img_url:
                    img_filename = safe_filename(img_url)
                    await download_asset(img_url, asset_folder, img_filename)
                    content = content.replace(img_url, f"./images/{img_filename}")

            # Replace internal page links with camelCase file names
            nav_links = await page.query_selector_all("nav a")
            for nav_link in nav_links:
                link_url = await nav_link.get_attribute("href")
                link_text = (await nav_link.inner_text()).strip()

                if link_url and main_domain in link_url and link_text:
                    # Convert link text to camelCase for the filename
                    local_page_filename = f"./pages/{to_camel_case(link_text)}.html"
                    content = content.replace(link_url, local_page_filename)

            # Remove Wix ads
            content = remove_wix_ads(content)

            # Save the modified HTML content to a file
            with open(filename, "w", encoding="utf-8") as file:
                file.write(content)
            print(f"Saved: {filename}")
            return

        except Exception as e:
            retries += 1
            print(f"Failed to save page {url} (attempt {retries}/{max_retries}): {e}")
            await asyncio.sleep(2)

    print(f"Giving up on page {url} after {max_retries} attempts.")

async def scrape_link(context, link_text, link_url, main_domain):
    """Scrape a single link in a new browser tab."""
    filename = f"pages/{to_camel_case(link_text)}.html"
    page = await context.new_page()
    await save_page(page, link_url, filename, "images", main_domain)
    await page.close()

async def run():
    # Cleanup existing directories
    cleanup_directories()

    # Create a folder structure
    os.makedirs("pages", exist_ok=True)
    os.makedirs("images", exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()

        main_domain = "soozhalhoo.wixsite.com"
        
        main_url = f"https://{main_domain}/mysite"
        page = await context.new_page()
        await page.goto(main_url)
        await page.wait_for_selector("nav")

        nav_links = await page.query_selector_all("nav a")
        links = []

        for nav_link in nav_links:
            try:
                link_url = await nav_link.get_attribute("href")
                link_text = (await nav_link.inner_text()).strip()
                if link_url and main_domain in link_url:
                    links.append((link_text, link_url))
            except Exception as e:
                print(f"Failed to extract link: {e}")

        await save_page(page, main_url, "index.html", "images", main_domain)
        await page.close()

        tasks = [scrape_link(context, link_text, link_url, main_domain) for link_text, link_url in links]
        await asyncio.gather(*tasks)

        await browser.close()

asyncio.run(run())
