import os
import sys
import asyncio
import threading
from typing import List

# Force ProactorEventLoop on Windows for Playwright subprocess compatibility
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import database
from backend.scraper import AkakceScraper

# Initialize FastAPI
app = FastAPI(title="Akakçe Rakip Fiyat Analiz Programı")

# Get path to frontend files
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "frontend")
os.makedirs(FRONTEND_DIR, exist_ok=True)

# Global scan state tracker
scan_state = {
    "active": False,
    "total": 0,
    "current": 0,
    "current_barcode": "",
    "errors": []
}

# Request schemas
class BarcodeRequest(BaseModel):
    barcodes: List[str]

# Startup Event: Initialize SQLite Database
@app.on_event("startup")
def startup_event():
    database.init_db()

# Serve static frontend files
# We will mount static files at '/static' and map it to frontend/
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Root path: Serve index.html
@app.get("/")
def read_root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Akakçe Rakip Fiyat Analizi Backend Servisi Çalışıyor. Arayüz dosyaları (index.html) bekleniyor."}

# API: Get dashboard product list
@app.get("/api/products")
def get_products():
    try:
        return database.get_product_dashboard_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# API: Get single product details + history
@app.get("/api/products/{barcode}")
def get_product_detail(barcode: str):
    # Find product metadata
    products = database.get_all_products()
    product = next((p for p in products if p['barcode'] == barcode), None)
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
        
    # Get last scan id
    scan_ids = database.get_last_two_scan_ids_for_product(barcode)
    
    competitors = []
    prev_prices = {}
    
    if len(scan_ids) >= 1:
        competitors = database.get_product_prices_for_scan(barcode, scan_ids[0])
        
    if len(scan_ids) >= 2:
        # Load previous prices to highlight competitor changes
        prev_comps = database.get_product_prices_for_scan(barcode, scan_ids[1])
        for c in prev_comps:
            # key by sub_seller + store_name
            key = f"{c['store_name']}_{c['sub_seller']}"
            prev_prices[key] = c['price']
            
    # Add previous price comparison to current competitors
    for comp in competitors:
        key = f"{comp['store_name']}_{comp['sub_seller']}"
        comp['previous_price'] = prev_prices.get(key, None)
        if comp['previous_price'] is not None:
            comp['price_change'] = round(comp['price'] - comp['previous_price'], 2)
            comp['price_change_pct'] = round(((comp['price'] - comp['previous_price']) / comp['previous_price']) * 100, 2)
        else:
            comp['price_change'] = None
            comp['price_change_pct'] = None
            
    # Get history for charts
    history = database.get_product_history_chart_data(barcode)
    
    return {
        "product": product,
        "competitors": competitors,
        "history": history
    }

# API: Delete product from tracking
@app.delete("/api/products/{barcode}")
def delete_product(barcode: str):
    try:
        database.delete_product(barcode)
        return {"status": "success", "message": f"{barcode} takipten çıkarıldı."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Background scan executor
def run_scan_task(barcodes_to_scan: List[str]):
    global scan_state
    scan_state["active"] = True
    scan_state["total"] = len(barcodes_to_scan)
    scan_state["current"] = 0
    scan_state["errors"] = []
    
    print(f"Background scan started for {len(barcodes_to_scan)} products.")
    scan_id, scan_time = database.create_scan()
    
    try:
        with AkakceScraper(headless=True) as scraper:
            for barcode in barcodes_to_scan:
                scan_state["current_barcode"] = barcode
                
                # Fetch details
                data = scraper.scrape_barcode(barcode)
                
                if data:
                    # Update product metadata
                    database.add_product(
                        barcode=barcode,
                        name=data["name"],
                        image_url=data["image_url"],
                        url=data["url"]
                    )
                    
                    # Record prices
                    for comp in data["competitors"]:
                        database.add_price_record(
                            scan_id=scan_id,
                            barcode=barcode,
                            store_name=comp["store_name"],
                            sub_seller=comp["sub_seller"],
                            price=comp["price"],
                            link=comp["link"]
                        )
                else:
                    msg = f"{barcode} için fiyat verisi çekilemedi (Barkod Akakçe'de olmayabilir veya engellendi)."
                    print(msg)
                    scan_state["errors"].append(msg)
                    
                scan_state["current"] += 1
                
        database.update_scan_status(scan_id, "completed")
        print("Background scan task completed successfully.")
    except Exception as e:
        import traceback
        database.update_scan_status(scan_id, "failed")
        scan_state["errors"].append(f"Tarama hatası: {str(e)}")
        print("Error in background scan task:")
        traceback.print_exc()
    finally:
        scan_state["active"] = False

# API: Add new barcodes
@app.post("/api/products")
def add_barcodes(req: BarcodeRequest, background_tasks: BackgroundTasks):
    added = []
    all_products = [p['barcode'] for p in database.get_all_products()]
    
    for bc in req.barcodes:
        bc_clean = bc.strip()
        if not bc_clean or not bc_clean.isdigit():
            continue
        if bc_clean not in all_products:
            # Insert with placeholder name
            database.add_product(
                barcode=bc_clean,
                name=f"Taranmamış Ürün ({bc_clean})",
                image_url=None,
                url=None
            )
            added.append(bc_clean)
            
    if added:
        # Trigger background scan for the newly added products
        if not scan_state["active"]:
            background_tasks.add_task(run_scan_task, added)
            return {"status": "success", "message": f"{len(added)} yeni barkod eklendi ve arka planda tarama başlatıldı.", "added": added}
        else:
            return {"status": "success", "message": f"{len(added)} yeni barkod eklendi. Aktif bir tarama olduğu için tarama listesine alınamadı, mevcut işlem bittiğinde tarayabilirsiniz.", "added": added}
            
    return {"status": "success", "message": "Eklenen yeni barkod yok (tümü zaten takip listesinde veya geçersiz).", "added": []}

# API: Trigger scan (all or selected batch)
class ScanRequest(BaseModel):
    barcodes: List[str] = None

@app.post("/api/scan")
def trigger_scan(req: ScanRequest = None, background_tasks: BackgroundTasks = None):
    if scan_state["active"]:
        return {"status": "error", "message": "Zaten aktif bir tarama işlemi bulunuyor."}
        
    if req and req.barcodes:
        barcodes = req.barcodes
    else:
        products = database.get_all_products()
        barcodes = [p['barcode'] for p in products]
        
    if not barcodes:
        return {"status": "error", "message": "Taranacak ürün bulunmuyor."}
        
    background_tasks.add_task(run_scan_task, barcodes)
    return {"status": "success", "message": f"{len(barcodes)} ürün için tarama işlemi arka planda başlatıldı."}

# API: Get scan status
@app.get("/api/scan/status")
def get_scan_status():
    return scan_state
