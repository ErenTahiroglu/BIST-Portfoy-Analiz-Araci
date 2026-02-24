"""
BIST Portföy Analiz Aracı  –  Masaüstü GUI
=============================================
Çalıştır : python gui_app.py
"""

import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import customtkinter as ctk
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import numpy as np
import pandas as pd

# ── PyInstaller freeze desteği ────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    _BASE = sys._MEIPASS
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))

if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

# ── İş mantığı modülünü yükle ─────────────────────────────────────────────────
try:
    import BIST_Portfoy_Analiz_Araci as _core
    from BIST_Portfoy_Analiz_Araci import HisseAnaliz
except Exception as exc:
    raise ImportError(f"BIST_Portfoy_Analiz_Araci.py yüklenemedi: {exc}") from exc

# ── Tema & renkler ────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
_PALETTE = [cm.tab10(i) for i in range(10)]


def _env_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), ".env")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


# ══════════════════════════════════════════════════════════════════════════════
class FirstRunDialog(ctk.CTkToplevel):
    """İlk açılışta .env yoksa gösterilen diyalog."""

    def __init__(self, parent: ctk.CTk):
        super().__init__(parent)
        self.title("Hoşgeldiniz — İlk Kurulum")
        self.geometry("520x340")
        self.resizable(False, False)
        self._av_key = ""
        self._parent = parent
        self.after(150, self._init_content)

    def _init_content(self) -> None:
        self._build()
        self.update_idletasks()
        px = self._parent.winfo_x() + (self._parent.winfo_width()  - self.winfo_width())  // 2
        py = self._parent.winfo_y() + (self._parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")
        self.grab_set()
        self.focus_force()
        self.lift()

    def _build(self) -> None:
        pad = dict(padx=24, pady=6)

        ctk.CTkLabel(self,
                     text="BIST Portföy Analiz Aracı",
                     font=ctk.CTkFont(size=20, weight="bold")
                     ).pack(**pad, pady=(22, 2))

        ctk.CTkLabel(self,
                     text="Uygulama, fiyat doğrulaması için ücretsiz bir\n"
                          "Alpha Vantage API anahtarı kullanabilir (opsiyonel).\n\n"
                          "Yahoo Finance birincil kaynak olarak çalışır.\n"
                          "Key olmadan da kullanabilirsiniz.",
                     justify="center", wraplength=460,
                     font=ctk.CTkFont(size=13)
                     ).pack(**pad)

        ctk.CTkLabel(self, text="Alpha Vantage API Anahtarı (opsiyonel):"
                     ).pack(anchor="w", padx=24, pady=(10, 0))
        self._entry = ctk.CTkEntry(
            self, width=472,
            placeholder_text="Ücretsiz anahtar al: alphavantage.co/support/#api-key")
        self._entry.pack(padx=24, pady=(0, 4))

        btn_f = ctk.CTkFrame(self, fg_color="transparent")
        btn_f.pack(pady=(8, 20))
        ctk.CTkButton(btn_f, text="💾  Kaydet ve Devam Et",
                      command=self._save, width=210).pack(side="left", padx=8)
        ctk.CTkButton(btn_f, text="Şimdilik Geç",
                      command=self.destroy,
                      fg_color="#555", width=130).pack(side="left", padx=8)

    def _save(self) -> None:
        key = self._entry.get().strip()
        if key:
            try:
                with open(_env_path(), "w", encoding="utf-8") as f:
                    f.write(f"ALPHA_VANTAGE_KEY={key}\n")
                os.environ["ALPHA_VANTAGE_KEY"] = key
                _core._AV_KEY = key
                self._av_key = key
            except Exception:
                pass
        self.destroy()

    @property
    def av_key(self) -> str:
        return self._av_key


# ══════════════════════════════════════════════════════════════════════════════
class StdoutRedirector:
    def __init__(self, q: queue.Queue, total: int):
        self._q      = q
        self._total  = max(total, 1)
        self._done   = 0
        self._buf    = ""

    def write(self, text: str) -> None:
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            self._q.put(("log", line))
            self._detect(line)

    def flush(self) -> None:
        pass

    def _detect(self, line: str) -> None:
        if "enflasyon çekiliyor" in line:
            self._q.put(("progress", (0.03, "FRED: enflasyon verisi çekiliyor...")))
        elif "CPI çekiliyor" in line:
            self._q.put(("progress", (0.07, "FRED: CPI verisi çekiliyor...")))
        elif line.startswith("🔍  ") and len(line) < 40:
            sym = line.replace("🔍  ", "").strip()
            self._done += 1
            pct = 0.10 + (self._done / self._total) * 0.82
            self._q.put(("progress",
                         (min(pct, 0.92),
                          f"{sym} analiz ediliyor... ({self._done}/{self._total})")))
        elif "KARŞILAŞTIRMA TABLOSU" in line:
            self._q.put(("progress", (0.96, "Tablo oluşturuluyor...")))


# ══════════════════════════════════════════════════════════════════════════════
class AnalysisThread(threading.Thread):
    def __init__(self, symbols: list[str], av_key: str, q: queue.Queue):
        super().__init__(daemon=True, name="AnalysisThread")
        self.symbols = symbols
        self.av_key  = av_key
        self._q      = q
        self._stop   = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        original = sys.stdout
        redir    = StdoutRedirector(self._q, len(self.symbols))
        sys.stdout = redir
        try:
            if self.av_key:
                os.environ["ALPHA_VANTAGE_KEY"] = self.av_key
                _core._AV_KEY = self.av_key

            self._q.put(("progress", (0.01, "Başlatılıyor...")))
            analiz = HisseAnaliz(stop_event=self._stop)

            if self._stop.is_set():
                self._q.put(("cancelled", None))
                return

            df = analiz.coklu_analiz(self.symbols)

            if self._stop.is_set():
                self._q.put(("cancelled", None))
            elif df is not None:
                self._q.put(("progress", (1.0, f"Tamamlandı! ({len(df)} sembol)")))
                self._q.put(("result", (df, analiz)))
            else:
                self._q.put(("error", "Hiçbir sembol için veri alınamadı."))

        except Exception as exc:
            import traceback
            self._q.put(("log", traceback.format_exc()))
            self._q.put(("error", str(exc)))
        finally:
            sys.stdout = original


# ══════════════════════════════════════════════════════════════════════════════
class GUIApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("BIST Portföy Analiz Aracı  –  v1.1")
        self.geometry("1200x800")
        self.minsize(980, 640)

        self._q:           queue.Queue             = queue.Queue()
        self._thread:      AnalysisThread | None   = None
        self._session_dfs: list[pd.DataFrame]      = []
        self._current_df:  pd.DataFrame | None     = None
        self._analiz:      HisseAnaliz | None      = None
        self._sort_rev:    dict[str, bool]         = {}

        self._build_ui()
        self._poll_queue()
        self.after(400, self._check_first_run)

    # ─── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Başlık ────────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, height=52, corner_radius=0)
        top.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(top,
                     text="  🇹🇷 BIST Portföy Analiz Aracı",
                     font=ctk.CTkFont(size=18, weight="bold")
                     ).pack(side="left", padx=14)
        self._theme_seg = ctk.CTkSegmentedButton(
            top, values=["🌙 Koyu", "☀️ Açık"],
            command=self._toggle_theme, width=175)
        self._theme_seg.set("🌙 Koyu")
        self._theme_seg.pack(side="right", padx=14, pady=8)

        # ── Giriş paneli ──────────────────────────────────────────────────────
        inp = ctk.CTkFrame(self)
        inp.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
        inp.grid_columnconfigure(1, weight=1)

        sym_f = ctk.CTkFrame(inp)
        sym_f.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))
        sym_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(sym_f, text="Semboller:", width=95, anchor="e"
                     ).grid(row=0, column=0, padx=(8, 6))
        self._sym_entry = ctk.CTkEntry(
            sym_f, placeholder_text="THYAO, ASELS, GARAN, EREGL, BIMAS  (.IS otomatik eklenir)")
        self._sym_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=6)
        self._sym_entry.bind("<Return>", lambda _: self._start_analysis())

        av_f = ctk.CTkFrame(inp)
        av_f.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        av_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(av_f, text="AV Key:", width=95, anchor="e"
                     ).grid(row=0, column=0, padx=(8, 6))
        self._av_entry = ctk.CTkEntry(
            av_f,
            placeholder_text="ALPHA_VANTAGE_KEY — opsiyonel",
            show="*")
        self._av_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=6)
        av_val = os.environ.get("ALPHA_VANTAGE_KEY", "")
        if av_val:
            self._av_entry.insert(0, av_val)

        btn_f = ctk.CTkFrame(inp)
        btn_f.grid(row=0, column=2, rowspan=2, padx=8, pady=8)
        self._analyze_btn = ctk.CTkButton(
            btn_f, text="🔍  Analiz Et",
            command=self._start_analysis, width=155, height=36)
        self._analyze_btn.pack(pady=(6, 4))
        self._stop_btn = ctk.CTkButton(
            btn_f, text="⏹  Durdur",
            command=self._stop_analysis,
            width=155, height=36, fg_color="#555", state="disabled")
        self._stop_btn.pack(pady=(0, 6))

        # ── İlerleme ──────────────────────────────────────────────────────────
        prog_f = ctk.CTkFrame(self)
        prog_f.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 4))
        self._progress = ctk.CTkProgressBar(prog_f, height=14)
        self._progress.pack(fill="x", padx=10, pady=(8, 2))
        self._progress.set(0)
        self._status_lbl = ctk.CTkLabel(
            prog_f, text="Hazır.", anchor="w",
            font=ctk.CTkFont(size=12))
        self._status_lbl.pack(fill="x", padx=12, pady=(0, 6))

        # ── Sekmeler ──────────────────────────────────────────────────────────
        self._tabs = ctk.CTkTabview(self)
        self._tabs.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 4))
        self._tabs.add("📋  Tablo")
        self._tabs.add("📊  Grafikler")
        self._tabs.add("📈  Haftalık")
        self._tabs.add("📝  Log")

        self._build_table_tab()
        self._build_chart_tab()
        self._build_weekly_tab()
        self._build_log_tab()

        # ── Alt çubuk ─────────────────────────────────────────────────────────
        bot = ctk.CTkFrame(self)
        bot.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 8))
        self._excel_btn = ctk.CTkButton(
            bot, text="💾  Excel'e Kaydet",
            command=self._save_excel, state="disabled", width=165)
        self._excel_btn.pack(side="left", padx=8, pady=8)
        ctk.CTkButton(
            bot, text="🗑️  Temizle",
            command=self._clear_all, fg_color="#666", width=115
        ).pack(side="left", padx=4, pady=8)
        self._count_lbl = ctk.CTkLabel(
            bot, text="Toplam sembol: 0", font=ctk.CTkFont(size=12))
        self._count_lbl.pack(side="right", padx=16)

    # ─── Tablo sekmesi ────────────────────────────────────────────────────────

    def _build_table_tab(self) -> None:
        tab = self._tabs.tab("📋  Tablo")
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        frm = tk.Frame(tab)
        frm.grid(row=0, column=0, sticky="nsew")
        frm.grid_rowconfigure(0, weight=1)
        frm.grid_columnconfigure(0, weight=1)

        vsb = ttk.Scrollbar(frm, orient="vertical")
        hsb = ttk.Scrollbar(frm, orient="horizontal")

        self._apply_tree_style("dark")

        self._tree = ttk.Treeview(
            frm, show="headings", style="App.Treeview",
            yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.config(command=self._tree.yview)
        hsb.config(command=self._tree.xview)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self._tree.bind("<Button-1>", self._on_col_click)

    def _apply_tree_style(self, mode: str) -> None:
        dark = (mode == "dark")
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("App.Treeview",
                    background="#2b2b2b" if dark else "#f5f5f5",
                    foreground="#e0e0e0" if dark else "#111111",
                    fieldbackground="#2b2b2b" if dark else "#f5f5f5",
                    rowheight=26,
                    font=("Consolas", 10))
        s.configure("App.Treeview.Heading",
                    background="#3b3b3b" if dark else "#d0d0d0",
                    foreground="#ffffff" if dark else "#000000",
                    font=("Consolas", 10, "bold"))
        s.map("App.Treeview",
              background=[("selected", "#1f538d" if dark else "#3b8ed0")])

    def _populate_table(self, df: pd.DataFrame) -> None:
        self._tree.delete(*self._tree.get_children())
        cols = list(df.columns)
        self._tree["columns"] = cols

        for col in cols:
            is_txt = col in ("Sembol", "Ad")
            w      = max(len(col) * 9, 120 if is_txt else 85)
            self._tree.heading(col, text=col, anchor="w" if is_txt else "e")
            self._tree.column(col, width=w, anchor="w" if is_txt else "e",
                              minwidth=55, stretch=False)

        dark = ctk.get_appearance_mode() == "Dark"
        self._tree.tag_configure("odd",  background="#292929" if dark else "#f0f0f0")
        self._tree.tag_configure("even", background="#333333" if dark else "#ffffff")

        for i, (_, row) in enumerate(df.iterrows()):
            tag  = "odd" if i % 2 == 0 else "even"
            vals = []
            for col in cols:
                v = row[col]
                if col in ("Sembol", "Ad"):
                    vals.append(str(v) if pd.notna(v) else "—")
                elif col == "Son Fiyat (₺)":
                    vals.append(f"{v:.2f} ₺" if isinstance(v, (int, float)) and pd.notna(v) else "—")
                elif isinstance(v, float) and pd.notna(v):
                    vals.append(f"{v:+.2f}%")
                else:
                    vals.append("—")
            self._tree.insert("", "end", values=vals, tags=(tag,))

    def _on_col_click(self, event: tk.Event) -> None:
        if self._tree.identify("region", event.x, event.y) != "heading":
            return
        if self._current_df is None:
            return
        idx      = int(self._tree.identify_column(event.x).replace("#", "")) - 1
        col_name = self._tree["columns"][idx]
        rev      = self._sort_rev.get(col_name, False)
        try:
            sdf = self._current_df.sort_values(
                col_name, ascending=not rev, na_position="last")
            self._sort_rev[col_name] = not rev
            self._populate_table(sdf)
        except Exception:
            pass

    # ─── Grafik sekmesi ───────────────────────────────────────────────────────

    def _build_chart_tab(self) -> None:
        tab = self._tabs.tab("📊  Grafikler")
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        ctrl = ctk.CTkFrame(tab)
        ctrl.grid(row=0, column=0, sticky="ew", pady=(4, 0))
        ctk.CTkLabel(ctrl, text="Göster:", padx=10).pack(side="left")
        self._chart_seg = ctk.CTkSegmentedButton(
            ctrl,
            values=["Yıllık Getiri", "5Y / 3Y", "Aylık Dönemler", "Günlük Vol."],
            command=self._refresh_chart)
        self._chart_seg.set("Yıllık Getiri")
        self._chart_seg.pack(side="left", padx=8, pady=6)

        self._fig, self._ax = plt.subplots(figsize=(11, 5), dpi=96)
        self._style_chart()

        chart_frm = ctk.CTkFrame(tab)
        chart_frm.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        chart_frm.grid_rowconfigure(0, weight=1)
        chart_frm.grid_columnconfigure(0, weight=1)

        self._canvas = FigureCanvasTkAgg(self._fig, master=chart_frm)
        self._canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        tb_frm = tk.Frame(chart_frm)
        tb_frm.grid(row=1, column=0, sticky="ew")
        NavigationToolbar2Tk(self._canvas, tb_frm)

    # ─── Haftalık grafik sekmesi ──────────────────────────────────────────────

    def _build_weekly_tab(self) -> None:
        tab = self._tabs.tab("📈  Haftalık")
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        self._wfig, self._wax = plt.subplots(figsize=(11, 5), dpi=96)
        self._style_chart_ax(self._wfig, self._wax)

        chart_frm = ctk.CTkFrame(tab)
        chart_frm.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        chart_frm.grid_rowconfigure(0, weight=1)
        chart_frm.grid_columnconfigure(0, weight=1)

        self._wcanvas = FigureCanvasTkAgg(self._wfig, master=chart_frm)
        self._wcanvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        tb_frm = tk.Frame(chart_frm)
        tb_frm.grid(row=1, column=0, sticky="ew")
        NavigationToolbar2Tk(self._wcanvas, tb_frm)

    def _style_chart(self) -> None:
        self._style_chart_ax(self._fig, self._ax)

    def _style_chart_ax(self, fig, ax) -> None:
        dark = ctk.get_appearance_mode() == "Dark"
        bg   = "#2b2b2b" if dark else "#f5f5f5"
        abg  = "#383838" if dark else "#ffffff"
        fg   = "#e0e0e0" if dark else "#222222"

        fig.patch.set_facecolor(bg)
        ax.set_facecolor(abg)
        ax.tick_params(colors=fg, labelsize=9)
        for attr in ("yaxis", "xaxis"):
            getattr(ax, attr).label.set_color(fg)
        ax.title.set_color(fg)
        for sp in ax.spines.values():
            sp.set_edgecolor(fg)
            sp.set_alpha(0.3)
        ax.grid(True, alpha=0.15, color="#888", linestyle="--")

    def _refresh_chart(self, _=None) -> None:
        if self._current_df is None:
            return
        df    = self._current_df
        ctype = self._chart_seg.get()
        syms  = df["Sembol"].tolist()

        self._ax.clear()
        self._style_chart()

        fg = "#e0e0e0" if ctk.get_appearance_mode() == "Dark" else "#222222"

        def get_val(row: pd.Series, col: str) -> float:
            v = row.get(col)
            return float(v) if (v is not None and pd.notna(v)) else 0.0

        if ctype == "Yıllık Getiri":
            ycols = sorted(
                [c for c in df.columns
                 if "Getiri%" in c and len(c) <= 13 and c[0].isdigit()],
                key=lambda c: c[:4])
            if ycols:
                x = np.arange(len(ycols))
                w = min(0.8 / max(len(syms), 1), 0.32)
                for i, sym in enumerate(syms):
                    row = df[df["Sembol"] == sym].iloc[0]
                    vals = [get_val(row, c) for c in ycols]
                    offs = (i - len(syms) / 2 + 0.5) * w
                    bars = self._ax.bar(x + offs, vals, w,
                                       label=sym, color=_PALETTE[i % 10], alpha=0.87)
                    for bar in bars:
                        h = bar.get_height()
                        if abs(h) > 5:
                            self._ax.text(
                                bar.get_x() + bar.get_width() / 2, h,
                                f"{h:+.0f}", ha="center",
                                va="bottom" if h >= 0 else "top",
                                fontsize=7, color=fg)
                self._ax.set_xticks(x)
                self._ax.set_xticklabels([c[:4] for c in ycols])
                self._ax.set_ylabel("Getiri %")
                self._ax.set_title("Yıllık Nominal Getiri (%)")
                self._ax.axhline(0, lw=0.8, color="#aaa", alpha=0.5)
                self._ax.legend(fontsize=9, framealpha=0.3)

        elif ctype == "5Y / 3Y":
            cats = [c for c in ("5Y Getiri%", "3Y Getiri%") if c in df.columns]
            x = np.arange(len(syms))
            w = min(0.8 / max(len(cats), 1), 0.38)
            for i, col in enumerate(cats):
                vals = [get_val(df[df["Sembol"] == s].iloc[0], col)
                        if s in df["Sembol"].values else 0 for s in syms]
                offs = (i - len(cats) / 2 + 0.5) * w
                self._ax.bar(x + offs, vals, w,
                             label=col.replace(" Getiri%", ""),
                             color=_PALETTE[i % 10], alpha=0.87)
            self._ax.set_xticks(x)
            self._ax.set_xticklabels(syms)
            self._ax.set_ylabel("Toplam Getiri %")
            self._ax.set_title("Uzun Vadeli Toplam Getiri (%)")
            self._ax.axhline(0, lw=0.8, color="#aaa", alpha=0.5)
            self._ax.legend(fontsize=9, framealpha=0.3)

        elif ctype == "Aylık Dönemler":
            pcols = sorted(
                [c for c in df.columns if "A Getiri%" in c],
                key=lambda c: int(c.split("A")[0]))
            if pcols:
                x = np.arange(len(pcols))
                w = min(0.8 / max(len(syms), 1), 0.32)
                for i, sym in enumerate(syms):
                    row  = df[df["Sembol"] == sym].iloc[0]
                    vals = [get_val(row, c) for c in pcols]
                    offs = (i - len(syms) / 2 + 0.5) * w
                    self._ax.bar(x + offs, vals, w,
                                 label=sym, color=_PALETTE[i % 10], alpha=0.87)
                self._ax.set_xticks(x)
                self._ax.set_xticklabels([c.replace(" Getiri%", "") for c in pcols])
                self._ax.set_ylabel("Getiri %")
                self._ax.set_title("Kısa Vadeli Dönemsel Getiri (%)")
                self._ax.axhline(0, lw=0.8, color="#aaa", alpha=0.5)
                self._ax.legend(fontsize=9, framealpha=0.3)

        elif ctype == "Günlük Vol.":
            vol_cols = ["30G Ort%", "30G Vol%"]
            cats = [c for c in vol_cols if c in df.columns]
            if cats:
                x = np.arange(len(syms))
                w = min(0.8 / max(len(cats), 1), 0.38)
                for i, col in enumerate(cats):
                    vals = [get_val(df[df["Sembol"] == s].iloc[0], col)
                            if s in df["Sembol"].values else 0 for s in syms]
                    offs = (i - len(cats) / 2 + 0.5) * w
                    label = "Ort. Günlük Getiri" if "Ort" in col else "Volatilite (Std)"
                    self._ax.bar(x + offs, vals, w,
                                 label=label,
                                 color=_PALETTE[i % 10], alpha=0.87)
                self._ax.set_xticks(x)
                self._ax.set_xticklabels(syms)
                self._ax.set_ylabel("%")
                self._ax.set_title("Son 30 Gün — Günlük Getiri ve Volatilite")
                self._ax.axhline(0, lw=0.8, color="#aaa", alpha=0.5)
                self._ax.legend(fontsize=9, framealpha=0.3)

        self._fig.tight_layout(pad=1.5)
        self._canvas.draw()

    def _refresh_weekly_chart(self) -> None:
        if self._current_df is None:
            return
        df   = self._current_df
        syms = df["Sembol"].tolist()

        self._wax.clear()
        self._style_chart_ax(self._wfig, self._wax)

        fg = "#e0e0e0" if ctk.get_appearance_mode() == "Dark" else "#222222"

        hcols = sorted(
            [c for c in df.columns if "H Getiri%" in c],
            key=lambda c: int(c.split("H")[0]))
        if not hcols:
            self._wcanvas.draw()
            return

        x = np.arange(len(hcols))
        w = min(0.8 / max(len(syms), 1), 0.32)
        for i, sym in enumerate(syms):
            row = df[df["Sembol"] == sym].iloc[0]
            vals = []
            for c in hcols:
                v = row.get(c)
                vals.append(float(v) if (v is not None and pd.notna(v)) else 0.0)
            offs = (i - len(syms) / 2 + 0.5) * w
            self._wax.bar(x + offs, vals, w,
                          label=sym, color=_PALETTE[i % 10], alpha=0.87)

        self._wax.set_xticks(x)
        self._wax.set_xticklabels([c.replace(" Getiri%", "") for c in hcols])
        self._wax.set_ylabel("Getiri %")
        self._wax.set_title("Haftalık Dönemsel Getiri (%)")
        self._wax.axhline(0, lw=0.8, color="#aaa", alpha=0.5)
        self._wax.legend(fontsize=9, framealpha=0.3)

        self._wfig.tight_layout(pad=1.5)
        self._wcanvas.draw()

    # ─── Log sekmesi ──────────────────────────────────────────────────────────

    def _build_log_tab(self) -> None:
        tab = self._tabs.tab("📝  Log")
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        self._log = ctk.CTkTextbox(
            tab, font=("Consolas", 11), wrap="none")
        self._log.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

    def _log_append(self, text: str) -> None:
        self._log.insert("end", text + "\n")
        self._log.see("end")

    # ─── Queue polling ────────────────────────────────────────────────────────

    def _poll_queue(self) -> None:
        try:
            while True:
                mtype, payload = self._q.get_nowait()
                if mtype == "log":
                    self._log_append(payload)
                elif mtype == "progress":
                    pct, txt = payload
                    self._progress.set(pct)
                    self._status_lbl.configure(text=txt)
                elif mtype == "result":
                    df, analiz = payload
                    self._analiz = analiz
                    self._session_dfs.append(df)
                    merged = (pd.concat(self._session_dfs, ignore_index=True)
                              .drop_duplicates("Sembol", keep="last")
                              .reset_index(drop=True))
                    self._current_df = merged
                    self._populate_table(merged)
                    self._refresh_chart()
                    self._refresh_weekly_chart()
                    self._on_done()
                elif mtype == "error":
                    self._on_done()
                    messagebox.showerror("Hata", payload)
                    self._status_lbl.configure(text=f"Hata: {payload[:90]}")
                elif mtype == "cancelled":
                    self._on_done()
                    self._status_lbl.configure(text="Analiz durduruldu.")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _on_done(self) -> None:
        self._analyze_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        if self._current_df is not None:
            self._excel_btn.configure(state="normal")
            total = len(self._current_df)
            self._count_lbl.configure(text=f"Toplam sembol: {total}")
            self._tabs.set("📋  Tablo")

    # ─── Kontrol ──────────────────────────────────────────────────────────────

    def _start_analysis(self) -> None:
        raw = self._sym_entry.get().strip()
        if not raw:
            messagebox.showwarning("Uyarı",
                                   "En az bir sembol girin.\nÖrnek: THYAO, ASELS, GARAN")
            return
        if self._thread and self._thread.is_alive():
            messagebox.showwarning("Uyarı", "Analiz zaten devam ediyor.")
            return

        syms   = [s.strip().upper() for s in raw.split(",") if s.strip()]
        av_key = self._av_entry.get().strip()

        self._analyze_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._excel_btn.configure(state="disabled")
        self._progress.set(0)
        self._status_lbl.configure(text=f"Başlatılıyor... {len(syms)} sembol")
        self._log.delete("1.0", "end")
        self._tabs.set("📝  Log")

        self._thread = AnalysisThread(syms, av_key, self._q)
        self._thread.start()

    def _stop_analysis(self) -> None:
        if self._thread and self._thread.is_alive():
            self._thread.request_stop()
            self._status_lbl.configure(
                text="Durdurma isteği gönderildi...")

    def _save_excel(self) -> None:
        if not self._session_dfs:
            messagebox.showwarning("Uyarı", "Kaydedilecek sonuç yok.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Dosyası", "*.xlsx")],
            initialfile=f"bist_portfoy_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            title="Excel Dosyasını Kaydet")
        if not path:
            return
        tum = (pd.concat(self._session_dfs, ignore_index=True)
               .drop_duplicates("Sembol", keep="last"))
        if self._analiz:
            self._analiz.excel_kaydet(tum, path)
        else:
            tum.to_excel(path, index=False)
        messagebox.showinfo("Kaydedildi", f"Excel dosyası oluşturuldu:\n{path}")

    def _clear_all(self) -> None:
        if self._thread and self._thread.is_alive():
            messagebox.showwarning("Uyarı", "Önce analizi durdurun.")
            return
        self._session_dfs.clear()
        self._current_df = None
        self._analiz     = None
        self._tree.delete(*self._tree.get_children())
        self._ax.clear()
        self._style_chart()
        self._canvas.draw()
        self._wax.clear()
        self._style_chart_ax(self._wfig, self._wax)
        self._wcanvas.draw()
        self._log.delete("1.0", "end")
        self._progress.set(0)
        self._status_lbl.configure(text="Temizlendi. Hazır.")
        self._count_lbl.configure(text="Toplam sembol: 0")
        self._excel_btn.configure(state="disabled")

    def _toggle_theme(self, val: str) -> None:
        mode = "dark" if "Koyu" in val else "light"
        ctk.set_appearance_mode(mode)
        self._apply_tree_style(mode)
        if self._current_df is not None:
            self._populate_table(self._current_df)
        self._refresh_chart()
        self._refresh_weekly_chart()

    def _check_first_run(self) -> None:
        if os.path.exists(_env_path()):
            return
        if os.environ.get("ALPHA_VANTAGE_KEY", ""):
            return
        dlg = FirstRunDialog(self)
        self.wait_window(dlg)
        if dlg.av_key and not self._av_entry.get().strip():
            self._av_entry.insert(0, dlg.av_key)


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = GUIApp()
    app.mainloop()
