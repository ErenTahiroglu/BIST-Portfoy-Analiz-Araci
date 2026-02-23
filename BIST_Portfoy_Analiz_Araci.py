"""
BIST Portföy Analiz Aracı  –  v1.0
====================================
Borsa İstanbul hisse senetleri ve fonların finansal performansını
nominal ve reel (enflasyondan arındırılmış) bazda analiz eder.

Özellikler:
  • Günlük ve haftalık getiri analizi
  • Yıllık nominal / reel getiri (enflasyon düzeltmeli)
  • Kısa vadeli dönemsel performans (1, 2, 3, 6, 9 ay)
  • Temettü verimi hesaplama
  • Çoklu kaynak: Yahoo Finance (.IS) + Stooq doğrulaması
  • Kaynaklar arası fiyat farkı > %2 → uyarı
  • Excel export

Gereksinimler:
  pip install yfinance pandas pandas-datareader numpy openpyxl curl_cffi certifi requests python-dotenv customtkinter matplotlib
"""

# ══════════════════════════════════════════════════════════════════════════════
# SSL BYPASS
# ══════════════════════════════════════════════════════════════════════════════
import os, ssl, warnings, urllib3

os.environ["CURL_CA_BUNDLE"]     = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""
os.environ["SSL_CERT_FILE"]      = ""
os.environ["PYTHONHTTPSVERIFY"]  = "0"

warnings.filterwarnings("ignore")
urllib3.disable_warnings()
ssl._create_default_https_context = ssl._create_unverified_context

try:
    import certifi
    certifi.where = lambda: ""
    certifi.old_where = certifi.where
except ImportError:
    pass

try:
    from curl_cffi import requests as curl_req
    _CURL_SESSION = curl_req.Session(verify=False, impersonate="chrome")
    _HAS_CURL = True
except Exception:
    _HAS_CURL  = False
    _CURL_SESSION = None

# ── pandas_datareader uyumluluk yaması (pandas 2.x) ──────────────────────────
try:
    import pandas.util._decorators as _pd_dec
    if not hasattr(_pd_dec, "deprecate_kwarg"):
        raise AttributeError
except (ImportError, AttributeError):
    import sys as _sys, types as _types
    if "pandas.util._decorators" not in _sys.modules:
        _sys.modules["pandas.util._decorators"] = _types.ModuleType("pandas.util._decorators")
    _pd_dec = _sys.modules["pandas.util._decorators"]
    from functools import wraps as _wraps

    def _deprecate_kwarg(old_arg_name, new_arg_name=None, mapping=None, stacklevel=2):
        def _dec(func):
            @_wraps(func)
            def _wrapper(*args, **kwargs):
                if old_arg_name in kwargs:
                    if new_arg_name is not None:
                        kwargs[new_arg_name] = kwargs.pop(old_arg_name)
                    else:
                        kwargs.pop(old_arg_name)
                return func(*args, **kwargs)
            return _wrapper
        return _dec

    setattr(_pd_dec, "deprecate_kwarg", _deprecate_kwarg)

# ── Normal import'lar ─────────────────────────────────────────────────────────
import time
import threading
import requests as req_lib
import yfinance as yf
import pandas as pd
import pandas_datareader as pdr
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# ── pandas-datareader için SSL bypass ─────────────────────────────────────────
try:
    import requests as _req
    _pdr_session = _req.Session()
    _pdr_session.verify = False
    import pandas_datareader.base as _pdr_base
    _orig_pdr_init = _pdr_base._BaseReader.__init__
    def _patched_pdr_init(self, *args, **kwargs):
        _orig_pdr_init(self, *args, **kwargs)
        self.session = _pdr_session
    _pdr_base._BaseReader.__init__ = _patched_pdr_init
except Exception:
    pass

# ── Sabitler ──────────────────────────────────────────────────────────────────
VARSAYILAN_ENF   = 50.0          # Türkiye yüksek enflasyon ortamı
ANALIZ_YIL_SAYI  = 5
AYLIK_DONEMLER   = [1, 2, 3, 6, 9]
HAFTALIK_DONEMLER = [1, 2, 4, 8, 13, 26]  # Hafta cinsinden dönemler
RETRY_SAYISI     = 4
RETRY_BEKLEME    = [5, 15, 30, 60]
FIYAT_TOLERANS   = 2.0          # Kaynaklar arası max fark (%)

# Yahoo Finance'te BIST hisseleri .IS soneki ile aranır
BIST_SONEK = ".IS"

# Popüler BIST sembolleri (referans)
POPULER_BIST = {
    "THYAO": "Türk Hava Yolları",
    "ASELS": "ASELSAN",
    "GARAN": "Garanti BBVA",
    "AKBNK": "Akbank",
    "YKBNK": "Yapı Kredi",
    "EREGL": "Ereğli Demir Çelik",
    "BIMAS": "BİM Mağazalar",
    "SAHOL": "Sabancı Holding",
    "KCHOL": "Koç Holding",
    "SISE":  "Şişecam",
    "TUPRS": "Tüpraş",
    "FROTO": "Ford Otosan",
    "TOASO": "Tofaş",
    "TCELL": "Turkcell",
    "PGSUS": "Pegasus",
    "TAVHL": "TAV Havalimanları",
    "EKGYO": "Emlak Konut GYO",
    "KOZAL": "Koza Altın",
    "SASA":  "SASA Polyester",
    "TTKOM": "Türk Telekom",
}

# ── .env dosyasını yükle ──────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_AV_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")


# ══════════════════════════════════════════════════════════════════════════════
class HisseAnaliz:
# ══════════════════════════════════════════════════════════════════════════════

    def __init__(self, stop_event: Optional[threading.Event] = None):
        self._stop_event = stop_event
        self.bugun  = pd.Timestamp.now(tz="UTC")
        self.bu_yil = self.bugun.year
        self.yillar = list(range(self.bu_yil - ANALIZ_YIL_SAYI, self.bu_yil))

        print(f"\n{'═'*68}")
        print(f"  BIST PORTFÖY ANALİZ ARACI  –  v1.0")
        print(f"{'═'*68}")
        print(f"  Tarih         : {self.bugun.strftime('%d.%m.%Y')}")
        print(f"  Analiz yılları: {self.yillar[0]} – {self.yillar[-1]}")
        print(f"  curl_cffi     : {'✅ aktif' if _HAS_CURL else '⚠️ yok, yedek mod'}")
        print(f"  Alpha Vantage : {'✅ ' + _AV_KEY[:8] + '...' if _AV_KEY else '⚠️ yok'}")
        print(f"{'═'*68}\n")

        self.yillik_enf: Dict[int, float] = self._yillik_enflasyon_al()
        self.aylik_cpi:  pd.DataFrame      = self._aylik_cpi_al()

    # ─────────────────────────────────────────────────────────────────────────
    # SEMBOL NORMALIZASYONU
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _bist_sembol(sembol: str) -> str:
        """Sembolü Yahoo Finance BIST formatına çevirir (.IS soneki)."""
        sembol = sembol.upper().strip()
        if sembol.endswith(".IS"):
            return sembol
        # Zaten . içeriyorsa (örn: .E gibi) dokunma
        if "." in sembol:
            return sembol
        return sembol + BIST_SONEK

    @staticmethod
    def _temiz_sembol(sembol: str) -> str:
        """Gösterim için .IS sonekini kaldırır."""
        return sembol.replace(".IS", "").replace(".is", "")

    # ─────────────────────────────────────────────────────────────────────────
    # ENFLASYON (FRED – Türkiye CPI)
    # ─────────────────────────────────────────────────────────────────────────

    def _yillik_enflasyon_al(self) -> Dict[int, float]:
        """
        FRED'den Türkiye CPI verisini çeker.
        TURCPIALLMINMEI = Turkey Consumer Price Index, All Items
        """
        print("📊 Yıllık enflasyon çekiliyor (FRED – TURCPIALLMINMEI)...")
        try:
            cpi = pdr.get_data_fred(
                "TURCPIALLMINMEI",
                start=datetime(self.yillar[0] - 1, 1, 1),
                end  =datetime(self.bu_yil, 12, 31),
            )
            sonuc: Dict[int, float] = {}
            for yil in self.yillar:
                try:
                    once = cpi[cpi.index.year == yil - 1]["TURCPIALLMINMEI"].iloc[-1]
                    bu   = cpi[cpi.index.year == yil    ]["TURCPIALLMINMEI"].iloc[-1]
                    sonuc[yil] = ((bu - once) / once) * 100
                except Exception:
                    sonuc[yil] = VARSAYILAN_ENF
            print("✅ Yıllık enflasyon alındı (FRED – Türkiye CPI).\n")
            return sonuc
        except Exception as e:
            print(f"⚠️  FRED erişilemedi, tahmini değer kullanılacak ({VARSAYILAN_ENF}%): {e}\n")
            return {y: VARSAYILAN_ENF for y in self.yillar}

    def _aylik_cpi_al(self) -> pd.DataFrame:
        print("📊 Aylık CPI çekiliyor (FRED – Türkiye)...")
        try:
            bugun_n = self.bugun.tz_convert(None)
            cpi = pdr.get_data_fred(
                "TURCPIALLMINMEI",
                start=(bugun_n - pd.DateOffset(days=730)).to_pydatetime(),
                end  = bugun_n.to_pydatetime(),
            )
            print("✅ Aylık CPI alındı.\n")
            return cpi
        except Exception as e:
            print(f"⚠️  Aylık CPI alınamadı: {e}\n")
            return pd.DataFrame()

    def _donem_enflasyonu(self, bas: pd.Timestamp, bit: pd.Timestamp) -> float:
        try:
            if self.aylik_cpi.empty:
                raise ValueError
            def _n(ts):
                return ts.tz_convert(None) if ts.tzinfo else ts
            cb = self.aylik_cpi[self.aylik_cpi.index <= _n(bas)]["TURCPIALLMINMEI"].iloc[-1]
            ce = self.aylik_cpi[self.aylik_cpi.index <= _n(bit)]["TURCPIALLMINMEI"].iloc[-1]
            return ((ce - cb) / cb) * 100
        except Exception:
            return (VARSAYILAN_ENF / 365) * (bit - bas).days

    # ─────────────────────────────────────────────────────────────────────────
    # YARDIMCI
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _utc(df) -> pd.DataFrame:
        if isinstance(df, pd.Series):
            df = df.to_frame()
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        return df

    # ─────────────────────────────────────────────────────────────────────────
    # KAYNAK 1: Yahoo Finance (.IS sonekli)
    # ─────────────────────────────────────────────────────────────────────────

    def _yahoo_cek(self, sembol: str, baslangic: datetime, bitis: datetime
                   ) -> Optional[pd.DataFrame]:
        yf_sembol = self._bist_sembol(sembol)
        indir_kwargs = dict(
            start=baslangic, end=bitis,
            auto_adjust=True, progress=False, timeout=30,
        )
        if _HAS_CURL:
            indir_kwargs["session"] = _CURL_SESSION
        ham = yf.download(yf_sembol, **indir_kwargs)
        if ham is None or ham.empty:
            return None
        if isinstance(ham.columns, pd.MultiIndex):
            ham.columns = ham.columns.get_level_values(0)
        return self._utc(ham)

    # ─────────────────────────────────────────────────────────────────────────
    # KAYNAK 2: Stooq (doğrulama)
    # ─────────────────────────────────────────────────────────────────────────

    def _stooq_cek(self, sembol: str, baslangic: datetime, bitis: datetime
                   ) -> Optional[pd.DataFrame]:
        try:
            # Stooq'ta BIST hisseleri farklı formatlarda olabilir
            temiz = self._temiz_sembol(sembol)
            stooq_sembol = f"{temiz}.TR"
            df = pdr.get_data_stooq(stooq_sembol, start=baslangic, end=bitis)
            if df is None or df.empty:
                return None
            df = df.sort_index()
            return self._utc(df)
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # KAYNAK 3: Alpha Vantage (opsiyonel)
    # ─────────────────────────────────────────────────────────────────────────

    def _alphavantage_cek(self, sembol: str) -> Optional[pd.DataFrame]:
        if not _AV_KEY:
            return None
        try:
            temiz = self._temiz_sembol(sembol)
            # Alpha Vantage BIST için <SEMBOL>.IST kullanır
            av_sembol = f"{temiz}.IST"
            url = (
                f"https://www.alphavantage.co/query"
                f"?function=TIME_SERIES_DAILY_ADJUSTED"
                f"&symbol={av_sembol}&outputsize=full&apikey={_AV_KEY}"
            )
            r = req_lib.get(url, timeout=30, verify=False)
            data = r.json()
            ts = data.get("Time Series (Daily)", {})
            if not ts:
                return None
            df = pd.DataFrame.from_dict(ts, orient="index")
            df.index = pd.to_datetime(df.index)
            df = df.rename(columns={"5. adjusted close": "Close"})
            df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
            df = df[["Close"]].sort_index()
            return self._utc(df)
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # ÇOK KAYNAKLI VERİ ÇEKME + DOĞRULAMA
    # ─────────────────────────────────────────────────────────────────────────

    def _veri_cek(self, sembol: str) -> Optional[Dict]:
        temiz = self._temiz_sembol(sembol)
        print(f"  📥 {temiz} → veri çekiliyor...")
        baslangic = datetime(self.yillar[0] - 1, 12, 1)
        bitis     = self.bugun.tz_convert(None).to_pydatetime()

        # ── Yahoo Finance (birincil) ──────────────────────────────────────────
        fiyatlar_yf = None
        for deneme in range(RETRY_SAYISI):
            try:
                fiyatlar_yf = self._yahoo_cek(sembol, baslangic, bitis)
                if fiyatlar_yf is not None:
                    print(f"     ✅ Yahoo Finance: {len(fiyatlar_yf)} gün")
                    break
            except Exception as e:
                bekleme = RETRY_BEKLEME[min(deneme, len(RETRY_BEKLEME) - 1)]
                print(f"     ⏳ Yahoo deneme {deneme+1}/{RETRY_SAYISI}: {str(e)[:80]}")
                for _ in range(bekleme):
                    if self._stop_event and self._stop_event.is_set():
                        return None
                    time.sleep(1)

        # ── Stooq (ikincil) ───────────────────────────────────────────────────
        fiyatlar_stooq = None
        try:
            fiyatlar_stooq = self._stooq_cek(sembol, baslangic, bitis)
            if fiyatlar_stooq is not None:
                print(f"     ✅ Stooq        : {len(fiyatlar_stooq)} gün")
            else:
                print(f"     ⚠️  Stooq: veri yok")
        except Exception as e:
            print(f"     ⚠️  Stooq hata: {e}")

        # ── Alpha Vantage (üçüncül) ──────────────────────────────────────────
        fiyatlar_av = None
        if _AV_KEY:
            try:
                fiyatlar_av = self._alphavantage_cek(sembol)
                if fiyatlar_av is not None:
                    print(f"     ✅ Alpha Vantage: {len(fiyatlar_av)} gün")
                else:
                    print(f"     ⚠️  Alpha Vantage: veri yok")
            except Exception as e:
                print(f"     ⚠️  Alpha Vantage hata: {e}")

        if fiyatlar_yf is None and fiyatlar_stooq is None and fiyatlar_av is None:
            print(f"  ❌ {temiz}: hiçbir kaynaktan veri alınamadı.")
            return None

        # ── Çapraz doğrulama ──────────────────────────────────────────────────
        self._capraz_dogrula(temiz, fiyatlar_yf, fiyatlar_stooq, fiyatlar_av)

        # ── Birincil fiyat seçimi ─────────────────────────────────────────────
        if fiyatlar_yf is not None:
            fiyatlar = fiyatlar_yf
        elif fiyatlar_stooq is not None:
            fiyatlar = fiyatlar_stooq
        else:
            fiyatlar = fiyatlar_av

        # ── Temettü (Yahoo'dan) ───────────────────────────────────────────────
        temettular = pd.Series(dtype=float)
        try:
            yf_sembol = self._bist_sembol(sembol)
            ticker_kwargs = {"session": _CURL_SESSION} if _HAS_CURL else {}
            ticker = yf.Ticker(yf_sembol, **ticker_kwargs)
            tem    = ticker.dividends
            if tem is not None and not tem.empty:
                temettular = self._utc(tem.to_frame()).iloc[:, 0]
        except Exception:
            pass

        # ── Şirket adı ────────────────────────────────────────────────────────
        ad = POPULER_BIST.get(temiz, temiz)
        try:
            name = getattr(ticker.fast_info, "company_name", None)
            if name:
                ad = name
        except Exception:
            pass

        # ── Haftalık veri oluştur ─────────────────────────────────────────────
        haftalik = fiyatlar.resample("W-FRI").agg({
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum"
        }).dropna() if "Open" in fiyatlar.columns else fiyatlar.resample("W-FRI").last().dropna()

        return {
            "fiyatlar": fiyatlar,
            "haftalik": haftalik,
            "temettular": temettular,
            "ad": ad,
        }

    def _capraz_dogrula(self, sembol: str,
                        yf_df:    Optional[pd.DataFrame],
                        stooq_df: Optional[pd.DataFrame],
                        av_df:    Optional[pd.DataFrame]) -> None:
        fiyatlar_dict: Dict[str, float] = {}
        for isim, df in [("Yahoo", yf_df), ("Stooq", stooq_df), ("AlphaVantage", av_df)]:
            if df is not None and not df.empty and "Close" in df.columns:
                try:
                    fiyatlar_dict[isim] = float(df["Close"].dropna().iloc[-1])
                except Exception:
                    pass

        if len(fiyatlar_dict) < 2:
            return

        degerler = list(fiyatlar_dict.values())
        maks     = max(degerler)
        min_     = min(degerler)
        fark_pct = abs(maks - min_) / min_ * 100

        satir = "  🔍 Fiyat çapraz doğrulama: " + \
                " | ".join(f"{k}={v:.2f}₺" for k, v in fiyatlar_dict.items())
        print(satir)

        if fark_pct > FIYAT_TOLERANS:
            print(f"  ⚠️  DİKKAT: Kaynaklar arası fiyat farkı = %{fark_pct:.2f} "
                  f"(eşik: %{FIYAT_TOLERANS})")
        else:
            print(f"  ✅ Kaynaklar tutarlı (max fark: %{fark_pct:.2f})")

    # ─────────────────────────────────────────────────────────────────────────
    # HESAPLAMALAR
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _ydf(df: pd.DataFrame, yil: int) -> pd.DataFrame:
        return df[df.index.year == yil]

    def _yillik_getiri(self, fiyatlar: pd.DataFrame, yil: int) -> Optional[float]:
        try:
            once = self._ydf(fiyatlar, yil - 1)
            bu   = self._ydf(fiyatlar, yil)
            if once.empty or bu.empty:
                return None
            return ((bu["Close"].iloc[-1] - once["Close"].iloc[-1])
                    / once["Close"].iloc[-1]) * 100
        except Exception:
            return None

    def _toplam_getiri(self, fiyatlar: pd.DataFrame,
                       bas_yil: int, bit_yil: int) -> Optional[float]:
        try:
            once = self._ydf(fiyatlar, bas_yil - 1)
            bit  = self._ydf(fiyatlar, bit_yil)
            if once.empty or bit.empty:
                return None
            return ((bit["Close"].iloc[-1] - once["Close"].iloc[-1])
                    / once["Close"].iloc[-1]) * 100
        except Exception:
            return None

    def _temettu_verimi(self, temettular: pd.Series,
                        fiyatlar: pd.DataFrame, yil: int) -> float:
        try:
            yt = temettular[temettular.index.year == yil]
            if yt.empty:
                return 0.0
            yf_ = self._ydf(fiyatlar, yil)
            if yf_.empty:
                return 0.0
            return (yt.sum() / yf_["Close"].iloc[0]) * 100
        except Exception:
            return 0.0

    def _donemsel_getiri(self, fiyatlar: pd.DataFrame, ay: int
                         ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        try:
            hedef   = self.bugun - pd.DateOffset(months=ay)
            sonraki = fiyatlar[fiyatlar.index >= hedef]
            if sonraki.empty:
                return None, None, None
            bas = sonraki.iloc[0]
            bit = fiyatlar.iloc[-1]
            g   = ((bit["Close"] - bas["Close"]) / bas["Close"]) * 100
            enf = self._donem_enflasyonu(bas.name, bit.name)
            return g, g - enf, enf
        except Exception:
            return None, None, None

    def _haftalik_getiri(self, haftalik: pd.DataFrame, hafta: int
                         ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Haftalık dönemsel getiri hesapla."""
        try:
            hedef   = self.bugun - pd.DateOffset(weeks=hafta)
            sonraki = haftalik[haftalik.index >= hedef]
            if sonraki.empty:
                return None, None, None
            bas = sonraki.iloc[0]
            bit = haftalik.iloc[-1]
            g   = ((bit["Close"] - bas["Close"]) / bas["Close"]) * 100
            enf = self._donem_enflasyonu(bas.name, bit.name)
            return g, g - enf, enf
        except Exception:
            return None, None, None

    def _gunluk_istatistik(self, fiyatlar: pd.DataFrame, gun: int = 30
                            ) -> Optional[Dict]:
        """Son N günün günlük getiri istatistikleri."""
        try:
            son = fiyatlar.tail(gun + 1)
            if len(son) < 2:
                return None
            gunluk_getiri = son["Close"].pct_change().dropna() * 100
            return {
                "ort":    gunluk_getiri.mean(),
                "std":    gunluk_getiri.std(),
                "min":    gunluk_getiri.min(),
                "max":    gunluk_getiri.max(),
                "pozitif": (gunluk_getiri > 0).sum(),
                "negatif": (gunluk_getiri < 0).sum(),
                "toplam":  len(gunluk_getiri),
            }
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # SON FİYAT BİLGİSİ
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _son_fiyat_bilgisi(fiyatlar: pd.DataFrame) -> Dict:
        """Son işlem günü fiyat bilgisi."""
        try:
            son = fiyatlar.iloc[-1]
            onceki = fiyatlar.iloc[-2] if len(fiyatlar) > 1 else son
            degisim = ((son["Close"] - onceki["Close"]) / onceki["Close"]) * 100
            return {
                "fiyat":   son["Close"],
                "degisim": degisim,
                "tarih":   son.name.strftime("%d.%m.%Y"),
                "yuksek":  son["High"] if "High" in son.index else son["Close"],
                "dusuk":   son["Low"]  if "Low"  in son.index else son["Close"],
            }
        except Exception:
            return {"fiyat": 0, "degisim": 0, "tarih": "?", "yuksek": 0, "dusuk": 0}

    # ─────────────────────────────────────────────────────────────────────────
    # ANA ANALİZ
    # ─────────────────────────────────────────────────────────────────────────

    def analiz_et(self, sembol: str) -> Optional[Dict]:
        temiz = self._temiz_sembol(sembol)
        print(f"\n{'─'*68}")
        print(f"🔍  {temiz}")
        print(f"{'─'*68}")

        veri = self._veri_cek(sembol)
        if not veri:
            return None

        fiyatlar   = veri["fiyatlar"]
        haftalik   = veri["haftalik"]
        temettular = veri["temettular"]

        son_fiyat = self._son_fiyat_bilgisi(fiyatlar)
        print(f"\n  💰 Son Fiyat: {son_fiyat['fiyat']:.2f} ₺ "
              f"({son_fiyat['degisim']:+.2f}%) — {son_fiyat['tarih']}")

        sonuc = {
            "sembol": temiz, "ad": veri["ad"],
            "son_fiyat": son_fiyat,
            "yg": {}, "yr": {}, "yt": {},
            "s5": None, "s3": None,
            "ay": {}, "hafta": {},
            "gunluk_ist": None,
        }

        # ── Yıllık getiri ────────────────────────────────────────────────────
        print(f"\n  {'Yıl':<6} {'Getiri':>8} {'Reel':>8} {'Enflasyon':>10} {'Temettü':>8}")
        print(f"  {'─'*46}")
        for yil in self.yillar:
            g = self._yillik_getiri(fiyatlar, yil)
            if g is None:
                continue
            enf = self.yillik_enf.get(yil, VARSAYILAN_ENF)
            r   = g - enf
            t   = self._temettu_verimi(temettular, fiyatlar, yil)
            sonuc["yg"][yil] = g
            sonuc["yr"][yil] = r
            sonuc["yt"][yil] = t
            print(f"  {yil:<6} {g:>+7.2f}%  {r:>+7.2f}%  {enf:>+8.2f}%  {t:>7.2f}%")

        # ── Toplam getiri ─────────────────────────────────────────────────────
        s5 = self._toplam_getiri(fiyatlar, self.yillar[0],  self.yillar[-1])
        s3 = self._toplam_getiri(fiyatlar, self.yillar[-3], self.yillar[-1])
        sonuc["s5"] = s5
        sonuc["s3"] = s3
        print(f"\n  📊 Toplam getiri:")
        if s5 is not None:
            print(f"     Son 5 yıl ({self.yillar[0]}–{self.yillar[-1]}): {s5:>+8.2f}%")
        if s3 is not None:
            print(f"     Son 3 yıl ({self.yillar[-3]}–{self.yillar[-1]}): {s3:>+8.2f}%")

        # ── Aylık dönemsel getiri ─────────────────────────────────────────────
        print(f"\n  {'Dönem':<9} {'Getiri':>8} {'Reel':>8} {'Dönem Enf.':>11}")
        print(f"  {'─'*40}")
        for ay in AYLIK_DONEMLER:
            g, r, enf = self._donemsel_getiri(fiyatlar, ay)
            if g is None:
                continue
            sonuc["ay"][ay] = {"g": g, "r": r, "enf": enf}
            print(f"  Son {ay:>2} ay   {g:>+7.2f}%  {r:>+7.2f}%  {enf:>+9.2f}%")

        # ── Haftalık dönemsel getiri ──────────────────────────────────────────
        print(f"\n  {'Dönem':<12} {'Getiri':>8} {'Reel':>8}")
        print(f"  {'─'*32}")
        for hafta in HAFTALIK_DONEMLER:
            g, r, enf = self._haftalik_getiri(haftalik, hafta)
            if g is None:
                continue
            sonuc["hafta"][hafta] = {"g": g, "r": r, "enf": enf}
            print(f"  Son {hafta:>2} hafta  {g:>+7.2f}%  {r:>+7.2f}%")

        # ── Günlük istatistik ─────────────────────────────────────────────────
        gist = self._gunluk_istatistik(fiyatlar, 30)
        if gist:
            sonuc["gunluk_ist"] = gist
            print(f"\n  📈 Son 30 Gün İstatistikleri:")
            print(f"     Ort. günlük getiri : {gist['ort']:+.3f}%")
            print(f"     Volatilite (std)   : {gist['std']:.3f}%")
            print(f"     Min / Max          : {gist['min']:+.2f}% / {gist['max']:+.2f}%")
            print(f"     Pozitif / Negatif  : {gist['pozitif']} / {gist['negatif']} gün")

        return sonuc

    # ─────────────────────────────────────────────────────────────────────────
    # ÇOKLU ANALİZ + TABLO
    # ─────────────────────────────────────────────────────────────────────────

    def coklu_analiz(self, semboller: List[str]) -> Optional[pd.DataFrame]:
        sonuclar = []
        for i, s in enumerate(semboller):
            r = self.analiz_et(s)
            if r:
                sonuclar.append(r)
            if i < len(semboller) - 1:
                time.sleep(3)
        if not sonuclar:
            print("\n❌ Hiçbir sembol için veri alınamadı.")
            return None
        return self._tablo_olustur(sonuclar)

    def _tablo_olustur(self, sonuclar: List[Dict]) -> pd.DataFrame:
        satirlar = []
        for s in sonuclar:
            r = {
                "Sembol": s["sembol"],
                "Ad": s["ad"],
                "Son Fiyat (₺)": round(s["son_fiyat"]["fiyat"], 2),
                "Günlük %": round(s["son_fiyat"]["degisim"], 2),
            }
            for yil in self.yillar:
                if yil in s["yg"]:
                    r[f"{yil} Getiri%"]  = round(s["yg"][yil], 2)
                    r[f"{yil} Reel%"]    = round(s["yr"][yil], 2)
                    r[f"{yil} Temettü%"] = round(s["yt"][yil], 2)
            if s["s5"] is not None:
                r["5Y Getiri%"] = round(s["s5"], 2)
            if s["s3"] is not None:
                r["3Y Getiri%"] = round(s["s3"], 2)
            for ay in AYLIK_DONEMLER:
                if ay in s["ay"]:
                    r[f"{ay}A Getiri%"] = round(s["ay"][ay]["g"], 2)
                    r[f"{ay}A Reel%"]   = round(s["ay"][ay]["r"], 2)
            for hafta in HAFTALIK_DONEMLER:
                if hafta in s["hafta"]:
                    r[f"{hafta}H Getiri%"] = round(s["hafta"][hafta]["g"], 2)
                    r[f"{hafta}H Reel%"]   = round(s["hafta"][hafta]["r"], 2)

            # Günlük istatistik
            if s["gunluk_ist"]:
                r["30G Ort%"]  = round(s["gunluk_ist"]["ort"], 3)
                r["30G Vol%"]  = round(s["gunluk_ist"]["std"], 3)

            satirlar.append(r)

        df = pd.DataFrame(satirlar)
        print(f"\n\n{'═'*80}")
        print("📊  KARŞILAŞTIRMA TABLOSU  (değerler % cinsinden, fiyatlar ₺)")
        print(f"{'═'*80}\n")

        gruplar = [
            ["Sembol", "Ad", "Son Fiyat (₺)", "Günlük %"],
            [c for c in df.columns if "Getiri%" in c and len(c) <= 13 and c[0].isdigit()],
            [c for c in df.columns if "Reel%"   in c and len(c) <= 10 and c[0].isdigit()],
            [c for c in df.columns if "Temettü%" in c],
            [c for c in df.columns if c in ("5Y Getiri%", "3Y Getiri%")],
            [c for c in df.columns if "A Getiri%" in c or "A Reel%" in c],
            [c for c in df.columns if "H Getiri%" in c or "H Reel%" in c],
            [c for c in df.columns if c.startswith("30G")],
        ]
        for grup in gruplar:
            mevcut = [c for c in grup if c in df.columns]
            if mevcut:
                print(df[mevcut].to_string(index=False))
                print()
        return df

    # ─────────────────────────────────────────────────────────────────────────
    # EXCEL
    # ─────────────────────────────────────────────────────────────────────────

    def excel_kaydet(self, df: pd.DataFrame, dosya_adi: Optional[str] = None):
        if df is None or df.empty:
            print("⚠️  Kaydedilecek veri yok.")
            return
        if not dosya_adi:
            dosya_adi = f"bist_portfoy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        elif not dosya_adi.endswith(".xlsx"):
            dosya_adi += ".xlsx"
        try:
            with pd.ExcelWriter(dosya_adi, engine="openpyxl") as w:
                df.to_excel(w, index=False, sheet_name="Analiz")
                ws = w.sheets["Analiz"]
                for col in ws.columns:
                    maks = max(len(str(c.value or "")) for c in col)
                    ws.column_dimensions[col[0].column_letter].width = maks + 4
            print(f"\n✅ Excel kaydedildi: {dosya_adi}")
        except Exception as e:
            print(f"\n❌ Excel hatası: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ANA DÖNGÜ (konsol modu)
# ══════════════════════════════════════════════════════════════════════════════

def main():
    analiz = HisseAnaliz()
    tum_df_listesi: List[pd.DataFrame] = []

    while True:
        print("\n" + "─" * 68)
        print("📝  BIST hisse kodlarını girin (virgülle ayırın).")
        print("    Örnek: THYAO, ASELS, GARAN, EREGL, BIMAS")
        print("    (.IS soneki otomatik eklenir)")
        print("    Çıkmak için: kapat")
        if tum_df_listesi:
            toplam_sembol = sum(len(df) for df in tum_df_listesi)
            print(f"    📂 Bu oturumda analiz edilen sembol: {toplam_sembol}")
        print("─" * 68)

        girdi = input("Kodlar → ").strip()
        if girdi.lower() in {"kapat", "exit", "quit", "q", "çıkış"}:
            if tum_df_listesi:
                print(f"\n\n{'═'*68}")
                print("💾  OTURUM SONU — BİRİKMİŞ ANALİZ SONUÇLARI")
                print(f"{'═'*68}")
                tum_df = pd.concat(tum_df_listesi, ignore_index=True)
                tum_df = tum_df.drop_duplicates(subset=["Sembol"], keep="last")
                print(f"  Toplam sembol: {len(tum_df)}")
                print(f"  Semboller    : {', '.join(tum_df['Sembol'].tolist())}\n")

                if input("💾  Tüm sonuçları Excel'e kaydet? (E / H) → ").strip().upper() == "E":
                    ad = input("    Dosya adı (boş = otomatik) → ").strip()
                    analiz.excel_kaydet(tum_df, ad if ad else None)
            print("\n👋  Görüşmek üzere!\n")
            break

        if not girdi:
            print("⚠️  En az bir sembol girin.\n")
            continue

        semboller = [s.strip().upper() for s in girdi.split(",") if s.strip()]
        print(f"\n🔍  {len(semboller)} sembol analiz ediliyor: {', '.join(semboller)}")
        df = analiz.coklu_analiz(semboller)

        if df is not None:
            tum_df_listesi.append(df)
            print(f"\n  ℹ️  Sonuçlar biriktirildi. "
                  f"Excel için 'kapat' yazın.")

        print("\n" + "─" * 68)
        devam = input("🔄  Yeni analiz? (E / H) → ").strip().upper()
        if devam in {"H", "HAYIR", "N", "NO"}:
            if tum_df_listesi:
                print(f"\n\n{'═'*68}")
                print("💾  OTURUM SONU")
                print(f"{'═'*68}")
                tum_df = pd.concat(tum_df_listesi, ignore_index=True)
                tum_df = tum_df.drop_duplicates(subset=["Sembol"], keep="last")
                if input("💾  Excel'e kaydet? (E / H) → ").strip().upper() == "E":
                    ad = input("    Dosya adı (boş = otomatik) → ").strip()
                    analiz.excel_kaydet(tum_df, ad if ad else None)
            print("\n👋  Görüşmek üzere!\n")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Program durduruldu (Ctrl+C).\n")
    except Exception as e:
        print(f"\n❌  Beklenmeyen hata: {e}")
        input("Çıkmak için Enter'a basın...")
