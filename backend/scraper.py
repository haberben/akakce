import re
import time
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def parse_price(price_str):
    if not price_str:
        return None
    # Strip spaces and standard currency markers
    cleaned = price_str.strip().replace(" ", "").replace("TL", "").replace("tl", "").replace("₺", "")
    if "," in cleaned:
        if "." in cleaned:
            # e.g., 48.760,64 -> 48760.64
            cleaned = cleaned.replace(".", "")
        cleaned = cleaned.replace(",", ".")
    else:
        # e.g., 50.499 -> 50499.0
        parts = cleaned.split(".")
        if len(parts) == 2:
            if len(parts[1]) == 3:
                cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned)
    except ValueError:
        return None

class AkakceScraper:
    def __init__(self, headless=True):
        self.headless = headless
        self.playwright_mgr = None
        self.playwright = None
        self.browser = None
        self.context = None
        
    def start(self):
        print("Starting Playwright browser session with Stealth...")
        # Use Stealth wrap programmatically
        self.playwright_mgr = Stealth().use_sync(sync_playwright())
        self.playwright = self.playwright_mgr.__enter__()
        
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Navigate to homepage once to establish cookies and bypass initial anti-bot hurdles
        page = self.context.new_page()
        try:
            print("Visiting Akakçe home page for session setup...")
            page.goto("https://www.akakce.com/", wait_until="networkidle", timeout=30000)
            time.sleep(1)
        except Exception as e:
            print(f"Warning during home page setup: {e}")
        finally:
            page.close()
            
    def stop(self):
        print("Stopping Playwright browser session...")
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright_mgr:
            self.playwright_mgr.__exit__(None, None, None)
            
    def __enter__(self):
        self.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        
    def scrape_barcode(self, barcode):
        """
        Scrapes a barcode from Akakçe.
        Returns: Dict containing name, image_url, url, competitors,
        or None if not found or blocked.
        """
        print(f"Scraping barcode: {barcode}")
        page = self.context.new_page()

        
        try:
            search_url = f"https://www.akakce.com/arama/?q={barcode}"
            page.goto(search_url, wait_until="networkidle", timeout=30000)
            
            # Check for no results
            body_text = page.inner_text("body")
            if "hiç ürün bulunamadı" in body_text or "ürün bulunamadı" in body_text:
                print(f"Barcode {barcode} was not found on Akakçe.")
                return None
                
            current_url = page.url
            print(f"Landing URL: {current_url}")
            
            # Case A: We land on search results page (URL contains '/arama/')
            if "/arama/" in current_url:
                print("Landed on search results page. Resolving first product link...")
                try:
                    # Wait for search results product link to load
                    page.wait_for_selector('a.pw_v8', timeout=5000)
                    print("Clicking first product link via JS...")
                    page.eval_on_selector('a.pw_v8', 'el => el.click()')
                    page.wait_for_load_state("networkidle")
                    time.sleep(2)
                except Exception as click_err:
                    print(f"Could not click a.pw_v8 link via JS: {click_err}. Trying fallback navigation...")
                    html = page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    
                    product_links = []
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "/fiyati," in href or "/fiyatlar," in href or "en-ucuz-" in href:
                            if href.endswith(".html") and not href.startswith("https://www.akakce.com/arama/"):
                                product_links.append(href)
                                
                    if not product_links:
                        p_list = soup.find(id="p-list") or soup.find(class_=re.compile(r"pl_v\d"))
                        if p_list:
                            for a in p_list.find_all("a", href=True):
                                href = a["href"]
                                if href.endswith(".html"):
                                    product_links.append(href)
                                    
                    if product_links:
                        first_link = product_links[0]
                        if not first_link.startswith("http"):
                            first_link = "https://www.akakce.com" + first_link
                        print(f"Navigating to first product link with referrer: {first_link}")
                        page.goto(first_link, wait_until="networkidle", timeout=30000, referer=current_url)
                        time.sleep(2)
                    else:
                        print(f"No product links found on the search page for barcode {barcode}.")
                        return None
                    
            # Case B: We are on the product detail page
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # Check for Cloudflare block on details page
            page_title = page.title()
            if "Just a moment..." in page_title or "Cloudflare" in page_title:
                print("Blocked by Cloudflare on product detail page.")
                return None
                
            # Extract product details
            h1 = soup.find("h1")
            product_name = h1.text.strip() if h1 else "Unknown Product"
            
            # Image URL
            main_img = None
            for img in soup.find_all("img", src=True):
                src = img["src"]
                if ("i.akakce.com" in src or "cdn.akakce.com" in src) and ("/z/" in src or "/p/" in src):
                    main_img = src
                    break
            if not main_img:
                # Gallery fallback
                for div in soup.find_all("div", class_=True):
                    class_str = " ".join(div["class"])
                    if "img" in class_str or "gallery" in class_str:
                        img = div.find("img")
                        if img and img.get("src"):
                            main_img = img["src"]
                            break
                            
            # Competitors Extraction
            competitors = []
            
            # Online sellers
            pl = soup.find(id="PL")
            pl_items = pl.find_all("li", recursive=False) if pl else []
            
            # Physical store prices
            mp_items = []
            for ul in soup.find_all("ul", id=re.compile(r"^MP_")):
                mp_items.extend(ul.find_all("li", recursive=False))
                
            all_items = []
            for item in pl_items:
                all_items.append(("online", item))
            for item in mp_items:
                all_items.append(("store", item))
                
            for source_type, row in all_items:
                row_text = row.text.strip().replace("\n", " ")
                if not ("TL" in row_text or "tl" in row_text):
                    continue
                    
                # Store Name
                store_name = "N/A"
                img = row.find("img")
                if img and img.get("alt"):
                    store_name = img["alt"].strip()
                
                if store_name == "N/A" or store_name == "":
                    store_a = row.find("a", class_="s") or row.find("a", href=lambda h: h and "/magaza/" in h)
                    if store_a:
                        store_name = store_a.text.strip()
                    else:
                        span_s = row.find("span", class_="s") or row.find("span", class_="u") or row.find("span", class_="v")
                        if span_s:
                            store_name = span_s.text.strip()
                            
                # Fallback: text search
                if store_name == "N/A" or store_name == "":
                    text_upper = row_text.upper()
                    for s in ["AMAZON", "TRENDYOL", "HEPSİBURADA", "N11", "PAZARAMA", "MEDİAMARKT", "TEKNOSA", "TURKCELL", "VODAFONE", "VATAN"]:
                        if s in text_upper:
                            store_name = s.title()
                            break
                            
                if not store_name or store_name == "N/A":
                    continue
                    
                if "Trendyol" in store_name:
                    store_name = "Trendyol"
                    
                # Sub-seller (marketplace seller)
                sub_seller = store_name
                match_slash = re.search(r"/\s*([A-Za-z0-9şığüçöİŞĞÜÇÖ\-\.\s\&]+)$", row_text)
                if match_slash:
                    parsed_sub = match_slash.group(1).strip()
                    if len(parsed_sub) < 30:
                        sub_seller = parsed_sub
                        
                # Price
                price = None
                price_span = row.find("span", class_=re.compile(r"pt_v8|pr_v8|price"))
                if price_span:
                    price = parse_price(price_span.text)
                    
                if price is None:
                    price_match = re.search(r"([\d\.\,]+)\s*TL", row_text, re.IGNORECASE)
                    if price_match:
                        price = parse_price(price_match.group(1))
                        
                if price is None:
                    continue
                    
                # Link
                a_tag = row.find("a", href=True)
                link = a_tag["href"] if a_tag else "N/A"
                if link.startswith("/"):
                    link = "https://www.akakce.com" + link
                    
                competitors.append({
                    "store_name": store_name,
                    "sub_seller": sub_seller,
                    "price": price,
                    "link": link
                })
                
            # Sort by price
            competitors = sorted(competitors, key=lambda x: x["price"])
            
            return {
                "barcode": barcode,
                "name": product_name,
                "image_url": main_img,
                "url": page.url,
                "competitors": competitors
            }
            
        except Exception as e:
            print(f"Error scraping barcode {barcode}: {e}")
            return None
        finally:
            page.close()
