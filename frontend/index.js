let historyChart = null;

document.addEventListener("DOMContentLoaded", () => {
    // Initial fetch
    loadDashboard();
    checkScanStatus();

    // Event listeners
    document.getElementById("btn-add-barcodes").addEventListener("click", addBarcodes);
    document.getElementById("btn-scan-all").addEventListener("click", scanAll);
    document.getElementById("search-products").addEventListener("input", filterProducts);
    document.getElementById("modal-close").addEventListener("click", closeModal);
    
    // Periodically poll for scan progress
    setInterval(checkScanStatus, 2000);
});

// Load Dashboard Products
async function loadDashboard() {
    const grid = document.getElementById("products-grid");
    
    try {
        const response = await fetch("/api/products");
        if (!response.ok) throw new Error("Dashboard verisi alınamadı");
        
        const products = await response.json();
        
        // Update summary text
        const summary = document.getElementById("tracker-summary");
        if (products.length === 0) {
            summary.innerText = "Şu an takip edilen hiçbir ürün bulunmuyor.";
            grid.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-barcode"></i>
                    <h3>Takip Listesi Boş</h3>
                    <p>Sidebar'dan toplu barkod girişi yaparak fiyat takibine başlayın.</p>
                </div>
            `;
            return;
        }
        
        summary.innerText = `Toplam ${products.length} ürün takip ediliyor.`;
        grid.innerHTML = "";
        
        products.forEach(product => {
            const card = createProductCard(product);
            grid.appendChild(card);
        });
        
    } catch (error) {
        console.error(error);
        grid.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-triangle-exclamation" style="color: var(--color-danger)"></i>
                <h3>Hata Oluştu</h3>
                <p>Veriler yüklenirken bir problem yaşandı: ${error.message}</p>
            </div>
        `;
    }
}

// Format Date string
defFormatDate = (dateStr) => {
    if (!dateStr) return "Hiç taranmadı";
    const date = new Date(dateStr);
    return date.toLocaleString('tr-TR', { 
        day: '2-digit', 
        month: '2-digit', 
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Create Product Card DOM Element
function createProductCard(product) {
    const card = document.createElement("div");
    card.className = "product-card glass-panel";
    card.dataset.name = product.name.toLowerCase();
    card.dataset.barcode = product.barcode;
    
    const priceText = product.current_price 
        ? `${product.current_price.toLocaleString('tr-TR')} TL` 
        : "Taranmadı";
        
    // Trend badge markup
    let trendBadge = `<span class="trend-badge trend-stable"><i class="fa-solid fa-minus"></i> 0.00%</span>`;
    if (product.price_change_pct !== null) {
        if (product.price_change_pct < 0) {
            trendBadge = `<span class="trend-badge trend-down"><i class="fa-solid fa-arrow-down-long"></i> ${product.price_change_pct}%</span>`;
        } else if (product.price_change_pct > 0) {
            trendBadge = `<span class="trend-badge trend-up"><i class="fa-solid fa-arrow-up-long"></i> +${product.price_change_pct}%</span>`;
        }
    }

    const imageHtml = product.image_url 
        ? `<img src="${product.image_url}" class="product-img" alt="${product.name}">`
        : `<i class="fa-solid fa-image-portrait" style="font-size: 32px; color: var(--text-dark)"></i>`;

    card.innerHTML = `
        <div class="product-card-main">
            <div class="product-img-wrapper">
                ${imageHtml}
            </div>
            <div class="product-info">
                <div>
                    <h3 class="product-title" title="${product.name}">${product.name}</h3>
                    <div class="product-barcode">${product.barcode}</div>
                </div>
                <div class="product-pricing">
                    <span class="price-main">${priceText}</span>
                    ${product.current_price ? trendBadge : ''}
                </div>
            </div>
        </div>
        
        <!-- Expandable competitor list -->
        <div class="competitors-accordion" id="accordion-${product.barcode}">
            <div class="competitor-list" id="list-${product.barcode}">
                <div class="loading-state" style="padding: 10px;">
                    <div class="spinner" style="width:20px; height:20px; border-width:2px;"></div>
                </div>
            </div>
        </div>
        
        <div class="card-actions">
            <span class="scan-date"><i class="fa-solid fa-clock icon-spacer"></i>${defFormatDate(product.last_scanned)}</span>
            <div style="display:flex; gap: 8px;">
                <button class="btn btn-icon-only" onclick="deleteProduct('${product.barcode}')" title="Ürünü Sil">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
                <button class="btn btn-card-history" onclick="showHistory('${product.barcode}')" ${!product.last_scanned ? 'disabled' : ''}>
                    <i class="fa-solid fa-chart-line"></i> Grafik
                </button>
                <button class="btn btn-card-toggle" onclick="toggleCompetitors('${product.barcode}')" ${!product.last_scanned ? 'disabled' : ''}>
                    Rakipler <i class="fa-solid fa-chevron-down" style="margin-left:5px;"></i>
                </button>
            </div>
        </div>
    `;
    
    return card;
}

// Toggle competitor accordion
async function toggleCompetitors(barcode) {
    const accordion = document.getElementById(`accordion-${barcode}`);
    const list = document.getElementById(`list-${barcode}`);
    const btn = accordion.nextElementSibling.querySelector(".btn-card-toggle");
    
    if (accordion.classList.contains("expanded")) {
        accordion.classList.remove("expanded");
        accordion.style.maxHeight = null;
        btn.innerHTML = `Rakipler <i class="fa-solid fa-chevron-down" style="margin-left:5px;"></i>`;
    } else {
        // Load details first
        accordion.classList.add("expanded");
        btn.innerHTML = `Kapat <i class="fa-solid fa-chevron-up" style="margin-left:5px;"></i>`;
        
        try {
            const response = await fetch(`/api/products/${barcode}`);
            if (!response.ok) throw new Error("Detaylar yüklenemedi");
            const data = await response.json();
            
            renderCompetitors(list, data.competitors);
            
            // Adjust maxheight for transition
            accordion.style.maxHeight = accordion.scrollHeight + "px";
        } catch (error) {
            list.innerHTML = `<div style="color:var(--color-danger); font-size:12px; padding:10px;">Yükleme hatası: ${error.message}</div>`;
        }
    }
}

// Render Competitor Rows inside expanded block
function renderCompetitors(container, competitors) {
    if (competitors.length === 0) {
        container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:10px; text-align:center;">Satıcı bulunamadı.</div>`;
        return;
    }
    
    container.innerHTML = "";
    
    competitors.forEach((c, index) => {
        const isCheapest = index === 0;
        const row = document.createElement("div");
        row.className = `competitor-row ${isCheapest ? 'cheapest' : ''}`;
        
        // Competitor trend price change indicator
        let trendHtml = "";
        if (c.price_change_pct !== null && c.price_change_pct !== 0) {
            if (c.price_change_pct < 0) {
                trendHtml = `<span class="comp-trend comp-trend-down" title="Önceki taramaya göre düştü"><i class="fa-solid fa-caret-down"></i> ${Math.abs(c.price_change_pct)}%</span>`;
            } else {
                trendHtml = `<span class="comp-trend comp-trend-up" title="Önceki taramaya göre arttı"><i class="fa-solid fa-caret-up"></i> +${c.price_change_pct}%</span>`;
            }
        }
        
        const subSellerHtml = c.sub_seller !== c.store_name 
            ? `<span class="comp-sub-seller">(${c.sub_seller})</span>` 
            : "";
            
        row.innerHTML = `
            <div class="comp-shop-info">
                <span class="comp-name">${c.store_name} ${subSellerHtml}</span>
                ${isCheapest ? '<span class="comp-sub-seller" style="color:var(--color-warn); font-weight:600;"><i class="fa-solid fa-trophy"></i> En Ucuz Satıcı</span>' : ''}
            </div>
            <div class="comp-price-wrapper">
                <span class="comp-price">${c.price.toLocaleString('tr-TR')} TL</span>
                ${trendHtml}
            </div>
            <div>
                <a href="${c.link}" target="_blank" rel="noopener noreferrer" class="btn-goto-shop" title="Satıcıya Git">
                    <i class="fa-solid fa-arrow-up-right-from-square"></i>
                </a>
            </div>
        `;
        
        container.appendChild(row);
    });
}

// Filter products based on search query
function filterProducts() {
    const query = document.getElementById("search-products").value.toLowerCase();
    const cards = document.querySelectorAll(".product-card");
    
    cards.forEach(card => {
        const name = card.dataset.name;
        const barcode = card.dataset.barcode;
        if (name.includes(query) || barcode.includes(query)) {
            card.style.display = "flex";
        } else {
            card.style.display = "none";
        }
    });
}

// Add new barcodes
async function addBarcodes() {
    const input = document.getElementById("barcode-input");
    const barcodeText = input.value.trim();
    if (!barcodeText) {
        alert("Lütfen en az bir barkod giriniz.");
        return;
    }
    
    const barcodes = barcodeText.split("\n").map(b => b.trim()).filter(b => b.length > 0);
    
    const btn = document.getElementById("btn-add-barcodes");
    btn.disabled = true;
    btn.innerHTML = `<div class="spinner" style="width:16px; height:16px; border-width:2px; display:inline-block; margin-right:8px;"></div> Barkodlar Ekleniyor...`;
    
    try {
        const response = await fetch("/api/products", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ barcodes })
        });
        
        if (!response.ok) throw new Error("Barkod ekleme başarısız");
        const result = await response.json();
        
        input.value = "";
        alert(result.message);
        loadDashboard();
        checkScanStatus();
    } catch (error) {
        alert("Hata: " + error.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-plus btn-icon"></i> Barkodları Ekle ve Tara`;
    }
}

// Scan all products on-demand
async function scanAll() {
    const btn = document.getElementById("btn-scan-all");
    btn.disabled = true;
    
    try {
        const response = await fetch("/api/scan", { method: "POST" });
        if (!response.ok) throw new Error("Tarama tetiklenemedi");
        
        const result = await response.json();
        alert(result.message);
        checkScanStatus();
    } catch (error) {
        alert("Hata: " + error.message);
        btn.disabled = false;
    }
}

// Delete barcode from list
async function deleteProduct(barcode) {
    if (!confirm(`Barkodu (${barcode}) takipten çıkarmak ve fiyat geçmişini silmek istediğinize emin misiniz?`)) return;
    
    try {
        const response = await fetch(`/api/products/${barcode}`, { method: "DELETE" });
        if (!response.ok) throw new Error("Silme başarısız");
        loadDashboard();
    } catch (error) {
        alert("Hata: " + error.message);
    }
}

// Show scanning progress status
async function checkScanStatus() {
    const progressBox = document.getElementById("scan-progress-box");
    const fill = document.getElementById("progress-bar-fill");
    const ratio = document.getElementById("progress-ratio");
    const percent = document.getElementById("progress-percent");
    const barcodeLabel = document.getElementById("progress-barcode");
    const scanAllBtn = document.getElementById("btn-scan-all");
    
    try {
        const response = await fetch("/api/scan/status");
        if (!response.ok) return;
        const status = await response.json();
        
        if (status.active) {
            progressBox.classList.remove("hidden");
            scanAllBtn.disabled = true;
            
            const percentage = status.total > 0 ? Math.round((status.current / status.total) * 100) : 0;
            fill.style.width = `${percentage}%`;
            ratio.innerText = `${status.current}/${status.total}`;
            percent.innerText = `${percentage}%`;
            barcodeLabel.innerText = status.current_barcode || "...";
        } else {
            // If it was active and just finished, reload dashboard
            if (!progressBox.classList.contains("hidden")) {
                progressBox.classList.add("hidden");
                scanAllBtn.disabled = false;
                loadDashboard();
            }
        }
    } catch (error) {
        console.error("Scanning status check failed:", error);
    }
}

// Display Price History Modal and line chart
async function showHistory(barcode) {
    const modal = document.getElementById("history-modal");
    modal.classList.remove("hidden");
    
    const productNameEl = document.getElementById("modal-product-name");
    productNameEl.innerText = `${barcode} - Fiyat Trendi`;
    
    try {
        const response = await fetch(`/api/products/${barcode}`);
        if (!response.ok) throw new Error("Geçmiş verileri alınamadı");
        
        const data = await response.json();
        productNameEl.innerText = `${data.product.name} Fiyat Trendi`;
        
        const history = data.history;
        if (history.length === 0) {
            document.querySelector(".chart-container").innerHTML = "<div style='color:var(--text-muted); text-align:center; padding: 50px;'>Bu ürün için yeterli fiyat geçmişi bulunmuyor.</div>";
            return;
        }
        
        // Re-inject canvas in case it was replaced by empty message
        document.querySelector(".chart-container").innerHTML = '<canvas id="history-chart"></canvas>';
        
        const labels = history.map(h => {
            const date = new Date(h.time);
            return date.toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
        });
        const prices = history.map(h => h.price);
        
        // Destroy existing chart if any
        if (historyChart) {
            historyChart.destroy();
        }
        
        const ctx = document.getElementById('history-chart').getContext('2d');
        historyChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'En Ucuz Fiyat (TL)',
                    data: prices,
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.3,
                    pointBackgroundColor: '#818cf8',
                    pointBorderColor: '#ffffff',
                    pointHoverRadius: 7
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: {
                            color: '#94a3b8',
                            font: { family: 'Outfit', size: 12 }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 10 } }
                    },
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { 
                            color: '#94a3b8', 
                            font: { family: 'JetBrains Mono', size: 10 },
                            callback: function(value) { return value.toLocaleString('tr-TR') + ' TL'; }
                        }
                    }
                }
            }
        });
        
    } catch (error) {
        alert("Grafik yüklenirken hata oluştu: " + error.message);
    }
}

function closeModal() {
    document.getElementById("history-modal").classList.add("hidden");
    if (historyChart) {
        historyChart.destroy();
        historyChart = null;
    }
}
