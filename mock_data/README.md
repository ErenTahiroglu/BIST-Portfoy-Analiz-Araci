# Mock Veri Klasörü

Bu klasör, proje internet bağlantısı olmadan veya Yahoo Finance API değişiminde çalışabilmesi için örnek OHLCV verilerini içerir.

## Dosya Formatı

Her CSV dosyasının adı sembol komudu (örn: `THYAO.IS.csv`, `EREGL.IS.csv`) olmalı ve şu sütunları içermeli:

```
Date,Open,High,Low,Close,Volume
2021-01-04,9.80,9.92,9.74,9.88,1250000
```

- **Date**: YYYY-MM-DD formatında tarih
- **Open**: Açılış fiyatı
- **High**: En yüksek fiyat
- **Low**: En düşük fiyat
- **Close**: Kapanış fiyatı
- **Volume**: İşlem hacmi

## Mevcut Veriler

- `THYAO.IS.csv`: Türk Hava Yolları (2021-2026)
- `EREGL.IS.csv`: Ereğli Demir Çelik (2021-2026)
- `ASELS.IS.csv`: ASELSAN (2021-2026)

## Yeni Sembol Ekleme

1. CSV dosyasını bu klasöre ekleyin: `mock_data/{SEMBOL}.csv`
2. `.env` dosyasında `USE_MOCK_DATA=True` olduğundan emin olun
3. Uygulamayı yeniden başlatın

## Mock Veri Etkinleştirme

`.env` dosyasında şu satırı ekleyin:

```
USE_MOCK_DATA=True
```

Bu ayarlandığında, uygulama internet kaynaklarından veri çekmek yerine bu klasördeki CSV dosyalarını kullanacaktır.
