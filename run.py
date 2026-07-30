import uvicorn
import os
import sys

# Ensure the root directory is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("=============================================================")
    print("  Akakçe Rakip Fiyat Analiz Programı Başlatılıyor...       ")
    print("  Web Panel Arayüzü: http://127.0.0.1:8000                  ")
    print("=============================================================")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
