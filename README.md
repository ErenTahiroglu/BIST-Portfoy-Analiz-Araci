# 📊 BIST Portföy Analiz Aracı

> ⚠️ **ARCHIVED / END-OF-LIFE PROJE**
>
> Bu proje **arşivlenmiştir** ve artık aktif olarak bakım görmemektedir. Yıllar sonra bile çalışabilmesi ve incelenebilmesi için aşağıdaki özelliklerle hardened edilmiştir:
>
> - ✅ Tüm bağımlılık sürümleri dondurumuştur (== ile sabitleme)
> - ✅ **Çevrimdışı/Mock Veri Modu**: Internet bağlantısı olmadan veya API değişiminde çalışabilir
> - ✅ Python 3.11.8 sürümü belirtilmiştir
> - ✅ Göreceli dosya yolları ile taşınabilirlik sağlanmıştır

**Finansal Danışmanlık Uyarısı:** Bu araç **yatırım danışmanlığı içermez**. Tamamen eğitim amaçlıdır. Gerçek portföy kararları için profesyonel danışmanlarla çalışınız.

---

Borsa İstanbul (BIST) hisse senetleri ve fonların finansal performansını **nominal ve reel (enflasyondan arındırılmış)** bazda **günlük ve haftalık** verilerle analiz eden masaüstü GUI uygulaması.

---

## 🚀 Özellikler

- **Masaüstü arayüz** — Koyu/açık tema, sekme tabanlı görünüm
- **Yıllık getiri analizi** — Son 5 yılın nominal ve reel getirileri
- **Günlük istatistikler** — Son 30 günün ort. getirisi, volatilitesi, min/max
- **Haftalık dönemsel getiri** — 1, 2, 4, 8, 13, 26 haftalık performans
- **Aylık dönemsel getiri** — Son 1, 2, 3, 6, 9 aylık dönemler
- **Temettü verimi** — Her yıl için otomatik hesaplama
- **Toplam getiri** — 3 yıllık ve 5 yıllık kümülatif performans
- **Reel getiri** — Türkiye enflasyonu (FRED – CPI) ile arındırılmış değerler
- **TEFAS entegrasyonu** — 3 harfli fon kodları otomatik algılanır (AKB, GAR, TKF…)
- **Çoklu kaynak doğrulama** — Yahoo Finance + Stooq + Alpha Vantage
- **Grafikler** — Yıllık getiri, 5Y/3Y, aylık dönem, haftalık dönem, volatilite grafikleri
- **Excel export** — Oturumun tüm sonuçları tek dosyaya

---

## 🛠️ VS Code ile Kurulum

### 1. Python'ı yükle
[python.org](https://www.python.org/downloads/) → **Python 3.9+**, kurulumda **"Add Python to PATH"** işaretle.

### 2. Projeyi aç
VS Code'da **File → Open Folder** ile bu klasörü aç.

### 3. Terminal aç ve sanal ortam kur
`Ctrl+Ö` (veya `Ctrl+\``) ile terminal aç:

```bash
py -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### 4. Python interpreter seç
`Ctrl+Shift+P` → "Python: Select Interpreter" → `.\.venv\Scripts\python.exe` seç.

### 5. Çalıştır
Yöntem A — **F5** tuşuna bas (launch.json yapılandırılmış, "GUI Başlat" seçili olmalı)

Yöntem B — Terminalden:
```bash
.\.venv\Scripts\python gui_app.py
```

---

## 🔌 Çevrimdışı / Mock Veri Modu (Archived Projeler İçin)

Proje, internet bağlantısı olmadan veya Yahoo Finance API değişiminde çalışabilmesi için **mock veri modunu** destekler.

### Mock Veriyi Etkinleştirme

**Adım 1:** `.env` dosyasında (yoksa `.env.example` dosyasını kopyalayıp `.env` yapın):

```
USE_MOCK_DATA=True
ALPHA_VANTAGE_KEY=your_key_here
```

**Adım 2:** Uygulamayı çalıştırın:

```bash
.\\.venv\\Scripts\\python gui_app.py
```

### Mevcut Mock Veriler

- `mock_data/THYAO.IS.csv` — Türk Hava Yolları (2021–2026)
- `mock_data/EREGL.IS.csv` — Ereğli Demir Çelik (2021–2026)
- `mock_data/ASELS.IS.csv` — ASELSAN (2021–2026)

### Yeni Sembol İçin Mock Veri Ekleme

1. `mock_data/{SEMBOL}.csv` dosyasını oluşturun (örn: `GARAN.IS.csv`)
2. CSV formatı: `Date,Open,High,Low,Close,Volume` (başlık gerekli)
3. `Date` sütunu `YYYY-MM-DD` formatında olmalı
4. USE_MOCK_DATA=True durumunda uygulamayı yeniden başlatın

Detaylı bilgi: [mock_data/README.md](mock_data/README.md)

---

## 📡 Veri Kaynakları

| Kaynak | Kullanım | Sembol Formatı |
|---|---|---|
| **Yahoo Finance** | Hisse fiyatı (birincil) | `THYAO.IS`, `ASELS.IS` |
| **Stooq** | Hisse fiyatı (doğrulama) | `THYAO.TR` |
| **Alpha Vantage** | Hisse fiyatı (opsiyonel) | `THYAO.IST` |
| **TEFAS** | Fon birim pay değeri | `AKB`, `GAR`, `TKF` |
| **FRED** | Enflasyon (TR CPI) | `TURCPIALLMINMEI` |

> **Not:** Hisse senetlerinde `.IS` soneki otomatik eklenir. Yatırım fonu kodları (3 harf) TEFAS'tan otomatik çekilir.

---

## 🔑 Alpha Vantage API Key (opsiyonel)

[alphavantage.co](https://www.alphavantage.co/support/#api-key) adresinden ücretsiz alınır. Uygulama ilk açılışta sorar veya ana ekrandaki **AV Key** alanından girebilirsiniz.

---

## 📁 Proje Yapısı

```
BIST-Portfoy-Analiz/
├── gui_app.py                     # Masaüstü GUI (buradan başlatılır)
├── BIST_Portfoy_Analiz_Araci.py   # Çekirdek analiz motoru
├── requirements.txt               # Çalışma zamanı bağımlılıkları
├── requirements-build.txt         # EXE derleme bağımlılıkları (PyInstaller)
├── bist_analiz.spec               # PyInstaller yapılandırması
├── .env.example                   # Örnek ortam değişkenleri
├── .gitignore
├── .vscode/
│   ├── settings.json              # Python interpreter ayarı (.venv)
│   └── launch.json                # F5 ile debug/çalıştırma
└── README.md
```

---

## 📦 EXE Olarak Derleme

Python kurulu olmayan bilgisayarlara dağıtmak için tek dosya `.exe` oluşturun.

### 1. PyInstaller'ı kur

```bash
.\.venv\Scripts\pip install -r requirements-build.txt
```

### 2. Derle

```bash
.\.venv\Scripts\pyinstaller bist_analiz.spec
```

Derleme 3–5 dakika sürer. Çıktı: `dist\BIST_Portfoy_Analiz_Araci.exe`

> **Not:** İlk çalıştırmada `.exe` birkaç saniye geç açılabilir (PyInstaller tek-dosya bootstrap süreci).

---

## 🛡️ Windows SmartScreen Uyarısı

`.exe` dosyasını ilk çalıştırdığınızda Windows şu uyarıyı verebilir:

> *"Microsoft Defender SmartScreen tanınmayan bir uygulamanın başlamasını engelledi."*

Bu uyarı **uygulama tehlikeli olduğu için değil**, dijital imzasız olduğu içindir.
Kaynak kod tamamen açık: [github.com/ErenTahiroglu/BIST-Portfoy-Analiz-Araci](https://github.com/ErenTahiroglu/BIST-Portfoy-Analiz-Araci)

**Çalıştırmak için:** "Daha fazla bilgi" → "Yine de çalıştır"

---

## 📋 Popüler BIST Sembolleri

```
THYAO, ASELS, GARAN, AKBNK, YKBNK, EREGL, BIMAS,
SAHOL, KCHOL, SISE, TUPRS, FROTO, TOASO, TCELL,
PGSUS, TAVHL, EKGYO, KOZAL, SASA, TTKOM
```

---

## 📋 Popüler TEFAS Fon Kodları

```
AKB  AKP  GAR  ISY  TKF  IYF  YAY  HLF  DWF  APF
```

> Tam fon listesi için: [tefas.gov.tr](https://www.tefas.gov.tr)

---

## ⚠️ Bilinen Sınırlamalar

- Yahoo Finance'te bazı küçük BIST hisseleri bulunmayabilir
- Stooq'ta BIST verisi kısıtlı olabilir (doğrulama her zaman çalışmayabilir)
- Alpha Vantage ücretsiz plan: günde 25 istek
- FRED'deki Türkiye CPI verisi birkaç ay gecikmeli yayınlanır
- TEFAS'ta temettü verisi tutulmaz (fonlar için temettü sütunu 0 görünür)
- Mock veri modu: Örnek veriler gerçek pazar verisi **değildir**, yalnızca UI/analiz testi için kullanılır
- Mock veri modu FRED enflasyon verisi desteği sunmaz (varsayılan %50 enflasyon kullanır)
