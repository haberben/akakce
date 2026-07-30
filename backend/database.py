import sqlite3
import os
import uuid
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "competitors.db"))

# Automatically create database parent directory if it doesn't exist
db_dir = os.path.dirname(DB_PATH)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Products table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        barcode TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        image_url TEXT,
        url TEXT,
        last_scanned TEXT
    )
    """)
    
    # Scans table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scans (
        scan_id TEXT PRIMARY KEY,
        scan_time TEXT NOT NULL,
        status TEXT NOT NULL
    )
    """)
    
    # Price history table (storing competitor prices for each scan)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id TEXT,
        barcode TEXT,
        store_name TEXT NOT NULL,
        sub_seller TEXT,
        price REAL NOT NULL,
        link TEXT,
        FOREIGN KEY (scan_id) REFERENCES scans(scan_id) ON DELETE CASCADE,
        FOREIGN KEY (barcode) REFERENCES products(barcode) ON DELETE CASCADE
    )
    """)
    
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

def add_product(barcode, name, image_url, url):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO products (barcode, name, image_url, url)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(barcode) DO UPDATE SET
        name=excluded.name,
        image_url=excluded.image_url,
        url=excluded.url
    """, (barcode, name, image_url, url))
    conn.commit()
    conn.close()

def delete_product(barcode):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE barcode = ?", (barcode,))
    cursor.execute("DELETE FROM price_history WHERE barcode = ?", (barcode,))
    conn.commit()
    conn.close()

def get_all_products():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products ORDER BY name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def create_scan(status="running"):
    scan_id = str(uuid.uuid4())
    scan_time = datetime.now().isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO scans (scan_id, scan_time, status)
    VALUES (?, ?, ?)
    """, (scan_id, scan_time, status))
    conn.commit()
    conn.close()
    return scan_id, scan_time

def update_scan_status(scan_id, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE scans SET status = ? WHERE scan_id = ?", (status, scan_id))
    conn.commit()
    conn.close()

def add_price_record(scan_id, barcode, store_name, sub_seller, price, link):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO price_history (scan_id, barcode, store_name, sub_seller, price, link)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (scan_id, barcode, store_name, sub_seller, price, link))
    cursor.execute("""
    UPDATE products SET last_scanned = ? WHERE barcode = ?
    """, (datetime.now().isoformat(), barcode))
    conn.commit()
    conn.close()

def get_product_prices_for_scan(barcode, scan_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT store_name, sub_seller, price, link 
    FROM price_history 
    WHERE barcode = ? AND scan_id = ?
    ORDER BY price ASC
    """, (barcode, scan_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_last_two_scan_ids_for_product(barcode):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT DISTINCT ph.scan_id, s.scan_time
    FROM price_history ph
    JOIN scans s ON ph.scan_id = s.scan_id
    WHERE ph.barcode = ? AND s.status = 'completed'
    ORDER BY s.scan_time DESC
    LIMIT 2
    """, (barcode,))
    rows = cursor.fetchall()
    conn.close()
    return [row['scan_id'] for row in rows]

def get_product_dashboard_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products")
    products = [dict(p) for p in cursor.fetchall()]
    
    result = []
    for prod in products:
        barcode = prod['barcode']
        scan_ids = get_last_two_scan_ids_for_product(barcode)
        
        current_lowest = None
        previous_lowest = None
        
        if len(scan_ids) >= 1:
            cursor.execute("""
            SELECT MIN(price) as min_p FROM price_history 
            WHERE barcode = ? AND scan_id = ?
            """, (barcode, scan_ids[0]))
            val = cursor.fetchone()
            if val and val['min_p'] is not None:
                current_lowest = val['min_p']
                
        if len(scan_ids) >= 2:
            cursor.execute("""
            SELECT MIN(price) as min_p FROM price_history 
            WHERE barcode = ? AND scan_id = ?
            """, (barcode, scan_ids[1]))
            val = cursor.fetchone()
            if val and val['min_p'] is not None:
                previous_lowest = val['min_p']
                
        prod['current_price'] = current_lowest
        prod['previous_price'] = previous_lowest
        
        # Include latest competitor details directly in dashboard data
        competitors = []
        if len(scan_ids) >= 1:
            cursor.execute("""
            SELECT store_name, sub_seller, price, link 
            FROM price_history 
            WHERE barcode = ? AND scan_id = ?
            ORDER BY price ASC
            """, (barcode, scan_ids[0]))
            competitors = [dict(row) for row in cursor.fetchall()]
        prod['competitors'] = competitors
        
        price_change_pct = None
        if current_lowest is not None and previous_lowest is not None:
            price_change_pct = round(((current_lowest - previous_lowest) / previous_lowest) * 100, 2)
            
        prod['price_change_pct'] = price_change_pct
        result.append(prod)
        
    conn.close()
    return result

def get_product_history_chart_data(barcode):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT s.scan_time, MIN(ph.price) as min_price
    FROM price_history ph
    JOIN scans s ON ph.scan_id = s.scan_id
    WHERE ph.barcode = ? AND s.status = 'completed'
    GROUP BY ph.scan_id
    ORDER BY s.scan_time ASC
    LIMIT 30
    """, (barcode,))
    rows = cursor.fetchall()
    conn.close()
    return [{"time": row['scan_time'], "price": row['min_price']} for row in rows]

def clear_all_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM price_history")
    cursor.execute("DELETE FROM products")
    cursor.execute("DELETE FROM scans")
    conn.commit()
    conn.close()
