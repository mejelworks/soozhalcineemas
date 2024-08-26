from playwright.sync_api import sync_playwright
import os
import shutil
import urllib.parse
import re
import requests
import time
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
    # Find and remove Wix.com ad containers
    wix_ad_containers = soup.find_all(id="WIX_ADS")
    for ad in wix_ad_containers:
        ad.decompose()
    return str(soup)

def save_page(page, url, filename, asset_folder, main_domain, max_retries=3):
    """Visit the page, wait for it to load, replace URLs, remove ads, and save the HTML content."""
    retries = 0
    while retries < max_retries:
        try:
            page.goto(url, timeout=60000)  # Increased timeout to 60 seconds
            page.wait_for_load_state("networkidle", timeout=60000)  # Wait for network idle with increased timeout

            # Replace image URLs with local paths
            content = page.content()
            image_elements = page.query_selector_all("img")

            for img in image_elements:
                img_url = img.get_attribute("src")
                if img_url:
                    # Download the asset
                    img_filename = safe_filename(img_url)
                    download_asset(img_url, asset_folder, img_filename)

                    # Replace the URL in the HTML content with the local path
                    content = content.replace(img_url, f"./images/{img_filename}")

            # Replace internal page links without .html extensions
            nav_links = page.query_selector_all("nav a")
            for nav_link in nav_links:
                link_url = nav_link.get_attribute("href")
                link_text = nav_link.inner_text().strip()
                
                # Ensure we're only replacing internal links
                if link_url and main_domain in link_url and link_text:
                    # Create a local path for the page (without .html extension)
                    local_page_filename = f"./pages/{link_text.replace(' ', '_').lower()}"
                    
                    # Replace the URL in the HTML content with the local page path
                    content = content.replace(link_url, local_page_filename)

            # Remove Wix ads
            content = remove_wix_ads(content)

            # Save the modified HTML content to a file
            with open(filename, "w", encoding="utf-8") as file:
                file.write(content)
            print(f"Saved: {filename}")
            return  # Exit the function if successful

        except Exception as e:
            retries += 1
            print(f"Failed to save page {url} (attempt {retries}/{max_retries}): {e}")
            time.sleep(2)  # Wait for 2 seconds before retrying

    print(f"Giving up on page {url} after {max_retries} attempts.")

def download_asset(url, asset_folder, filename):
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

def run(playwright):
    # Cleanup existing directories
    cleanup_directories()

    # Create a folder structure
    os.makedirs("pages", exist_ok=True)
    os.makedirs("images", exist_ok=True)
    
    # Launch browser (set headless=True if you don't need the browser UI)
    browser = playwright.chromium.launch(headless=False)
    page = browser.new_page()

    # Define the main domain to filter internal pages
    main_domain = "soozhalhoo.wixsite.com"
    
    # Navigate to the main page
    main_url = f"https://{main_domain}/mysite"
    page.goto(main_url)

    # Wait for the navbar to be loaded (adjust selector if necessary)
    page.wait_for_selector("nav")

    # Extract all navigation bar links (adjust selector if necessary)
    nav_links = page.query_selector_all("nav a")
    links = []

    for nav_link in nav_links:
        try:
            link_url = nav_link.get_attribute("href")
            link_text = nav_link.inner_text().strip()
            # Only add links that belong to the main domain
            if link_url and main_domain in link_url:
                links.append((link_text, link_url))
        except Exception as e:
            print(f"Failed to extract link: {e}")

    # Save the home page as index.html
    save_page(page, main_url, "index.html", "images", main_domain)

    # Loop through each extracted link and download its content
    for link_text, link_url in links:
        try:
            # If the link is a relative URL, prepend the base URL
            if link_url.startswith("/"):
                link_url = urllib.parse.urljoin(main_url, link_url)
            
            # Create a filename for the saved page (sanitize the text for filenames)
            filename = f"pages/{link_text.replace(' ', '_').lower()}.html"
            
            # Save the page content
            save_page(page, link_url, filename, "images", main_domain)

        except Exception as e:
            print(f"Failed to process link {link_text}: {e}")

    # Close the browser
    browser.close()

# Initialize and run Playwright
with sync_playwright() as playwright:
    run(playwright)
