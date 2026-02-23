# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — BIST Portföy Analiz Aracı
# Kullanım: env\Scripts\pyinstaller bist_analiz.spec

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas        = []
binaries     = []
hiddenimports = []

# ── customtkinter: tema, font ve resim dosyaları zorunlu ─────────────────────
ctk_d, ctk_b, ctk_h = collect_all("customtkinter")
datas        += ctk_d
binaries     += ctk_b
hiddenimports += ctk_h

# ── matplotlib: font ve stil dosyaları ───────────────────────────────────────
datas += collect_data_files("matplotlib")

# ── curl_cffi: CFFI binary bağımlılıkları ────────────────────────────────────
try:
    curl_d, curl_b, curl_h = collect_all("curl_cffi")
    datas        += curl_d
    binaries     += curl_b
    hiddenimports += curl_h
except Exception:
    pass

# ─────────────────────────────────────────────────────────────────────────────
a = Analysis(
    ["gui_app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        # Çekirdek modül — importlib yerine doğrudan import yapılıyor,
        # yine de açıkça belirt.
        "BIST_Portfoy_Analiz_Araci",
        # pandas-datareader alt modülleri
        "pandas_datareader",
        "pandas_datareader.data",
        "pandas_datareader.stooq",
        "pandas_datareader.fred",
        "pandas_datareader.base",
        # Diğer
        "yfinance",
        "openpyxl",
        "openpyxl.styles",
        "openpyxl.utils",
        "numpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test", "test", "unittest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BIST_Portfoy_Analiz_Araci",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # Konsol penceresi açılmaz
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
