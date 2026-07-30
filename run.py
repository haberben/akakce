import uvicorn
import os
import sys
import asyncio

# Force ProactorEventLoop on Windows for Playwright subprocess compatibility
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Ensure the root directory is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("=============================================================")
    print("  Akakçe Rakip Fiyat Analiz Programı Başlatılıyor...       ")
    print("  Web Panel Arayüzü: http://127.0.0.1:8000                  ")
    print("=============================================================")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
