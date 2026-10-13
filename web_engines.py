from __future__ import annotations

from pathlib import Path
import sys, io, contextlib
import textwrap
from collections import defaultdict
from statistics import mean

_REQUIRED_LOCAL_FILES = [
    "strategy1_yukselis.py",
    "strategy2_gunluk47.py",
    "strategy3_ideal.py",
    "strategy5_guclu.py",
    "strategy6_trad.py",
    "strategy7_yan_tahta.py",
    "strategy8_ma21_stoch_madev.py",
    "symbols.py",
    "v19_paths.py",
    "v19_report.py",
    "v19_2_canli.py",
    "v19_3_tavan_radar.py",
    "v32_live_tavan.py",
    "v32_eod_hazirlik.py",
    "v33_eod_combined.py",
    "v20_auto_forward.py",
    "v34_decision_layer.py",
    "v34_performance_ledger.py",
    "v34_itick_live.py",
    "patlama_oncesi_havuz.py",
    "v33_eylul_kor_test.py",
    "erken3g_havuz.py",
    "erken3g_kor_test.py",
    "erken3g_canli_kesisim.py",
    "candidate_memory.py",
    "memory_results.py",
    "target_tracking.py",
    "entry_status.py",
    "performance_summary.py",
    "balina_erken_kesisim.py",
    "sleeper_pool.py",
    "sleeper_whale.py",
    "data_quality.py",
    "balina_izi.py",
]
_here = Path(__file__).resolve().parent
_missing = [x for x in _REQUIRED_LOCAL_FILES if not (_here/x).exists()]
if _missing:
    print("HATA: Eksik dosyalar:")
    for x in _missing:
        print(" -", x)
    print("\nZIP'i tamamen ayni klasore cikartin.")
    sys.exit(1)

import strategy1_yukselis as s1
import strategy2_gunluk47 as s2
import strategy3_ideal as s3
import strategy5_guclu as s5
import strategy6_trad as s6
import strategy7_yan_tahta as s7
import strategy8_ma21_stoch_madev as s8
import v19_2_canli as live
import v19_3_tavan_radar as radar
import v32_live_tavan as v32_live
import v32_eod_hazirlik as v32_eod
import v33_eod_combined as v33_eod
import v20_auto_forward as v20_auto
import v34_itick_live as itick_live
import patlama_oncesi_havuz as patlama_havuz
import v33_eylul_kor_test as v33_sep_test
import erken3g_havuz as erken3g
import erken3g_kor_test as erken3g_test
import erken3g_canli_kesisim as erken3g_live
import candidate_memory as hafiza

STRATEGIES = [
    ("YÜKSELİŞ TRENDİ", s1, "run_video2_scan"),
    ("GÜNLÜK %4-%7", s2, "run_video_scan"),
    ("İDEAL TARAMA (2 SAAT)", s3, "run_video3_scan"),
    ("GÜÇLÜ TRADE", s5, "run_video5_scan"),
    ("TRADE 6", s6, "run_video6_scan"),
    ("YAN TAHTA", s7, "run_video7_scan"),
    ("MA21 + STOCH RSI + MADEV", s8, "run_video8_scan"),
]

_ORIGINAL_MAX_RESULTS = {
    id(mod): getattr(mod, "MAX_RESULTS", None)
    for _, mod, _ in STRATEGIES
}

def _set_master_limits():
    for _, mod, _ in STRATEGIES:
        if hasattr(mod, "MAX_RESULTS"):
            mod.MAX_RESULTS = 1000

def _restore_limits():
    for _, mod, _ in STRATEGIES:
        old = _ORIGINAL_MAX_RESULTS.get(id(mod))
        if old is not None and hasattr(mod, "MAX_RESULTS"):
            mod.MAX_RESULTS = old

def _signal_text(x):
    return str(x.get("signal") or x.get("combination") or "SİNYAL")

def run_silent(mod, func_name):
    fn = getattr(mod, func_name)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn()
    if result is None: return []
    if hasattr(result,"to_dict"): return result.to_dict("records")
    return result

def decision(count, avg_score):
    if count >= 4 and avg_score >= 70:
        return "ÇOK GÜÇLÜ"
    if count >= 3 and avg_score >= 70:
        return "GÜÇLÜ AL"
    if count >= 2 and avg_score >= 65:
        return "AL"
    return "TAKİP"

def format_table(rows):
    headers = ["HİSSE","SAYI","SİNYAL","PUAN","GİRİŞ","STOP","HEDEF","KAZANÇ %","KARAR"]
    strategy_codes = {
        "YÜKSELİŞ TRENDİ":"S1",
        "GÜNLÜK %4-%7":"S2",
        "İDEAL TARAMA (2 SAAT)":"S3",
        "GÜÇLÜ TRADE":"S4",
        "TRADE 6":"S5",
        "YAN TAHTA":"S6",
        "MA21 + STOCH RSI + MADEV":"S7",
    }
    data=[]
    for r in rows:
        codes="+".join(strategy_codes.get(n,"S?") for n in r.get("strategy_names",[]))
        data.append([
            r["symbol"],str(r["count"]),codes,f'{r["avg_score"]:.1f}',
            f'{r["entry"]:.2f}',f'{r["stop"]:.2f}',f'{r["target"]:.2f}',
            f'%{r["gain_pct"]:.2f}',r["decision"]
        ])
    widths=[max(len(headers[i]),max((len(x[i]) for x in data),default=0)) for i in range(len(headers))]
    sep="+"+"+".join("-"*(w+2) for w in widths)+"+"
    out=[sep,"| "+" | ".join(headers[i].ljust(widths[i]) for i in range(len(headers)))+" |",sep]
    for row in data:
        out.append("| "+" | ".join(row[i].ljust(widths[i]) for i in range(len(row)))+" |")
    out.append(sep)
    return "\n".join(out)

TIMEFRAMES = {
    "1": ("5 DAKİKA", "5m"),
    "2": ("15 DAKİKA", "15m"),
    "3": ("1 SAAT", "1h"),
    "4": ("2 SAAT", "2h"),
    "5": ("4 SAAT", "4h"),
    "6": ("GÜNLÜK", "1d"),
}

def choose_timeframe():
    RESET="\033[0m"; BOLD="\033[1m"; CYAN="\033[96m"; YELLOW="\033[93m"; GREEN="\033[92m"
    print("\n"+CYAN+BOLD+"ZAMAN PERİYODU"+RESET)
    print(YELLOW+"[1] 5 DAKİKA"+RESET)
    print(YELLOW+"[2] 15 DAKİKA"+RESET)
    print(GREEN+"[3] 1 SAAT"+RESET)
    print(GREEN+"[4] 2 SAAT"+RESET)
    print(GREEN+"[5] 4 SAAT"+RESET)
    print(CYAN+"[6] GÜNLÜK"+RESET)
    while True:
        choice=input("Periyot seçiminiz: ").strip()
        if choice in TIMEFRAMES:
            return TIMEFRAMES[choice]
        print("Geçersiz seçim. 1-6 arasında bir sayı girin.")

def apply_timeframe(tf):
    for _, mod, _ in STRATEGIES:
        if hasattr(mod, "set_timeframe"):
            mod.set_timeframe(tf)

def run_single(index, tf_label, tf):
    _restore_limits()
    apply_timeframe(tf)
    name, mod, fn_name = STRATEGIES[index-1]
    print("\n"+"="*100)
    print(f"TARAMA {index} | {name} | PERİYOT: {tf_label}")
    print("="*100)
    return getattr(mod, fn_name)()

def run_master(tf_label, tf):
    apply_timeframe(tf)
    _set_master_limits()
    print("="*110)
    print(f"BIST MASTER SCANNER | 7 TARAMA | PERİYOT: {tf_label}")
    print("="*110)
    all_hits=defaultdict(list)
    failures=[]
    for idx,(name,mod,fn) in enumerate(STRATEGIES,1):
        print(f"[{idx}/{len(STRATEGIES)}] {name} çalışıyor...")
        try:
            hits=run_silent(mod,fn)
            print(f"      -> {len(hits)} aday")
            for h in hits:
                symbol=str(h.get("symbol","")).replace(".IS","").strip()
                if symbol:
                    h=dict(h); h["strategy_name"]=name
                    all_hits[symbol].append(h)
        except Exception as exc:
            failures.append((name,str(exc)))
            print(f"      -> HATA: {exc}")
    merged=[]
    for symbol,hits in all_hits.items():
        scores=[float(h.get("score",0)) for h in hits]
        entries=[float(h["entry"]) for h in hits if h.get("entry") is not None]
        stops=[float(h["stop"]) for h in hits if h.get("stop") is not None]
        targets=[float(h["target"]) for h in hits if h.get("target") is not None]
        if not entries or not stops or not targets:
            continue
        avg_score=mean(scores) if scores else 0.0
        master_entry=max(entries); master_stop=max(stops); master_target=mean(targets)
        from data_quality import valid_long
        if not valid_long(master_entry,master_stop,master_target):
            failures.append((symbol,"Gecersiz birlesik giris/stop/hedef; listeden cikarildi"))
            continue
        gain=((master_target/master_entry)-1)*100 if master_entry else 0.0
        merged.append({
            "symbol":symbol,"count":len(hits),
            "strategy_names":[h["strategy_name"] for h in hits],
            "avg_score":avg_score,"entry":master_entry,"stop":master_stop,
            "target":master_target,"gain_pct":gain,
            "decision":decision(len(hits),avg_score),
        })
    merged.sort(key=lambda x:(x["count"],x["avg_score"]),reverse=True)
    print("\n"+"="*110)
    print(f"MASTER SONUÇ | Toplam benzersiz aday: {len(merged)}")
    print("="*110)
    print(format_table(merged) if merged else "Hiçbir stratejide aday bulunamadı.")
    if failures:
        print("\nÇalışmayan modüller:")
        for name,err in failures:
            print(f"- {name}: {err}")
    _restore_limits()
    return merged

