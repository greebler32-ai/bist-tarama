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

def show_menu():
    RESET="\033[0m"; BOLD="\033[1m"
    CYAN="\033[96m"; GREEN="\033[92m"; YELLOW="\033[93m"
    MAGENTA="\033[95m"; BLUE="\033[94m"; WHITE="\033[97m"; RED="\033[91m"
    DIM="\033[90m"

    # Aciklama alani genis tutulur; uzun metinler cerceveyi bozmak yerine sarilir.
    WNO=4; WT=38; WP=23; WM=78
    top="+"+"-"*WNO+"+"+"-"*WT+"+"+"-"*WP+"+"+"-"*WM+"+"

    print()
    print(CYAN+BOLD+"="*len(top)+RESET)
    print(CYAN+BOLD+"BIST V34 FIX31 - ANA MENU".center(len(top))+RESET)
    print(CYAN+BOLD+"="*len(top)+RESET)
    print()

    print(DIM+top+RESET)
    print(
        DIM+"|"+RESET+CYAN+BOLD+"NO".center(WNO)+RESET+
        DIM+"|"+RESET+YELLOW+BOLD+"TARAMA".center(WT)+RESET+
        DIM+"|"+RESET+YELLOW+BOLD+"ANA PERIYOT".center(WP)+RESET+
        DIM+"|"+RESET+GREEN+BOLD+"MANTIK / ACIKLAMA".center(WM)+RESET+DIM+"|"+RESET
    )
    print(DIM+top+RESET)

    rows=[
        ("1","Trendi Yukari Donen","1 SAAT",
         "Yeni trend donusunu erken, fazla gurultusuz yakalar"),
        ("2","%4-%7 Yukselis Adaylari","1 SAAT",
         "Gun ici yukselis potansiyeli olan hisseleri arar"),
        ("3","Guclu AL Sinyali","2 SAAT",
         "ALMA + Momentum + Stoch RSI + Bollinger teyidi"),
        ("4","Guclu Trade Firsatlari","1 SAAT",
         "Fisher + ALMA donusunu erken yakalar"),
        ("5","En Guclu 6 Teknik Sinyal","1 SAAT",
         "Fisher + MA Deviation donuslerini arar"),
        ("6","Yataydan Yukselise Gecebilecekler","15 DAKIKA",
         "ALMA 5/11 + SMA25 + Bollinger + Stoch RSI + SMI + Hacim"),
        ("7","Dipten Donus Sinyali","1 SAAT",
         "Stoch RSI + MA21 ile dipten donus arar"),
        ("8","Tum Taramalarda One Cikanlar","SECILEBILIR",
         "1-7 taramalarini secilen zaman periyodunda birlikte tarar"),
        ("9","V33 Birlesik Yarinin Top10","GUNLUK / SEANS SONU",
         "Dusus->Tepki + Kirilim->Onay + teyitli Daralma; yeni ana gun sonu"),
        ("10","Canli %5-%10 Trade Adaylari","15 DAKIKA",
         "Gun ici momentumla %5+ hareket adaylarini arar"),
        ("11","Canli Tavan Avcisi","15 DAKIKA",
         "Hacim + VWAP + DI + momentum ile tavan adaylarini arar"),
        ("12","Donus Avcisi V20","15 DAKIKA",
         "-%7/-10 dusus sonrasi teyitli dip donuslerini arar"),
        ("13","V19.3 Tavan Radar","15 DAKIKA",
         "Hacim ivmesi + RVOL + VWAP + DI + kirilim ile teyit arar"),
        ("14","V32 Gun Sonu Hazirlik","GUNLUK / CANLI ONCESI",
         "Sikisma/kirilim aday havuzu; ertesi gun canli teyit zorunlu"),
        ("15","V32 Canli Tavan Avcisi","15/30/60 DAKIKA",
         "RVOL 2.5/3 + RSI50 + VWAP + momentum + hacim karakteri"),
        ("16","Tum Motorlar + V34 Karar Katmani","CANLI + GUN SONU",
         "Tum motorlari calistirir; veri gecikmesi, piyasa rejimi, risk/odul ve sinyal durumunu kaydeder"),
        ("17","V34 iTick Anlik Aday Takibi","ANLIK / WEBSOCKET",
         "Yalniz Donus Avcisi en guclu 3 adayini iTick anlik fiyatla izler ve hareketlerini kaydeder"),
        ("18","Patlama Oncesi Havuz","GUNLUK",
         "MIATK tipi: uzun dinlenme -> dusus durur -> daralma -> hacim uyanisi; patlamadan once aday havuzu"),
        ("19","V33 Tarih Secimli Kor Test","TARIH SECIMI / D-1",
         "Secilen donemde D-1 kapanisina gore Top10 ile ertesi gun tavanlarini karsilastirir"),
        ("20","ERKEN-3G Patlama Havuzu","GUNLUK / TOP10",
         "Taban-sikisma + dusus-durdu + kademeli-uyanis + devam-dinlenme + para girisi; hedef D+1/D+2/D+3"),
        ("21","ERKEN-3G Kor Test","TARIH SECIMI / D+1..D+3",
         "Her gun Top10'u gelecegi gormeden kurar; ilk 3 seansta +5/+7/+9.5 ve MAE basarisini olcer"),
        ("22","ERKEN-3G + Donus Kesisim","GUN SONU + CANLI 15DK",
         "ERKEN-3G hazirlik adaylarini Donus Avcisi ile canli teyit eder; ortak adaylari birlesik skorla siralar"),
        ("23","ERKEN-3G + Donus + iTick Top3","CANLI / WEBSOCKET",
         "Kesisimdeki en guclu 3 ortak adayi iTick sabit kartlarda anlik fiyatla takip eder"),
        ("24","Tarama Hafizasi","KALICI ARSIV",
         "Tum tarama adaylarini tarih/motor ile saklar; MRSHL gibi bir hissenin hangi taramada ne zaman ciktigini bulur"),
        ("25","Hafiza Sonuc Guncelle","D+1 / D+2 / D+3","Sonraki 3 seans hareketi ve saklanan H1/H2/H3 hedeflerini olcer"),
        ("26","Balina Izi","GUNLUK / FIYAT-HACIM","Birikim, guclu alim ve dagitim izleri; kurum teyidi yok"),
        ("27","Motor ve Patern Basari Ozeti","HAFIZA / 3 SEANS","Balina izi dahil tamamlanmis adaylari motor ve tip bazinda ozetler"),
        ("28","Balina Izi + ERKEN-3G","GUNLUK / AYRI KESISIM","Ayni tarihte erken hazirlik ve birikim/guclu alim izi; canli teyit beklenir"),
    ]

    for no,name,period,logic in rows:
        if no in {"6","10","11","12","13"}:
            nc=RED+BOLD
        elif no in {"8","9","14","15","18","19","20","21","22","23","24"}:
            nc=BLUE+BOLD
        else:
            nc=YELLOW+BOLD

        if "15 DAKIKA" in period:
            pc=YELLOW+BOLD
        elif "SEANS SONU" in period or "GUNLUK" in period:
            pc=CYAN+BOLD
        else:
            pc=GREEN+BOLD

        logic_lines=textwrap.wrap(logic,width=WM-2,break_long_words=False,
                                  break_on_hyphens=False) or [""]
        for line_no,line in enumerate(logic_lines):
            first=(line_no==0)
            print(
                DIM+"|"+RESET+CYAN+BOLD+f"{no if first else '':^{WNO}}"+RESET+
                DIM+"|"+RESET+nc+f" {name if first else '':<{WT-2}} "+RESET+
                DIM+"|"+RESET+pc+f" {period if first else '':<{WP-2}} "+RESET+
                DIM+"|"+RESET+WHITE+f" {line:<{WM-2}} "+RESET+DIM+"|"+RESET
            )
        row_sep="+"+"="*WNO+"+"+"="*WT+"+"+"="*WP+"+"+"="*WM+"+"
        print(DIM+row_sep+RESET)

    print()
    print(GREEN+BOLD+"ZAMAN PERIYODU SECIMI: 1-8 taramalarinda 5dk / 15dk / 1s / 2s / 4s / Gunluk secilebilir."+RESET)
    print(YELLOW+BOLD+"SABIT 15 DAKIKA: 10 / 11 / 12 / 13 | V32: 14 / 15 | OTOMATIK TUMU: 16"+RESET)
    print(CYAN+BOLD+"GUN SONU ANA: 9 (V33) | HAZIRLIK: 14 | PATLAMA HAVUZU: 18 | EYLUL KOR TEST: 19 | ERKEN-3G: 20 | ERKEN-3G KOR TEST: 21 | CANLI KESISIM: 22 | KESISIM iTick TOP3: 23 | TARAMA HAFIZASI: 24 | SONUC: 25 | BALINA: 26 | OZET: 27 | KESISIM: 28"+RESET)
    print(RED+BOLD+"[0] CIKIS"+RESET)
    print(CYAN+BOLD+"="*len(top)+RESET)

def main():
    while True:
        show_menu()
        choice=input("Seçiminiz: ").strip()

        if choice=="0":
            print("Program kapatıldı.")
            break
        elif choice in {"1","2","3","4","5","6","7"}:
            try:
                tf_label,tf=choose_timeframe()
                sonuc=run_single(int(choice),tf_label,tf)
                hafiza.record_scan(f"TARAMA_{choice}",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nTARAMA HATASI: {exc}")
        elif choice=="8":
            try:
                tf_label,tf=choose_timeframe()
                sonuc=run_master(tf_label,tf)
                hafiza.record_scan("MASTER_1_7",sonuc,source="MENU")
            except Exception as exc:
                _restore_limits()
                print(f"\nMASTER TARAMA HATASI: {exc}")
        elif choice=="9":
            try:
                sonuc=v33_eod.main()
                hafiza.record_scan("V33_TOP10",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nGUN SONU TOP10 HATASI: {exc}")
        elif choice=="10":
            try:
                sonuc=live.momentum_main()
                hafiza.record_scan("CANLI_TRADE",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nCANLI TRADE HATASI: {exc}")
        elif choice=="11":
            try:
                sonuc=live.tavan_main()
                hafiza.record_scan("CANLI_TAVAN",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nCANLI TAVAN HATASI: {exc}")
        elif choice=="12":
            try:
                sonuc=live.reversal_main()
                hafiza.record_scan("DONUS_AVCISI",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nDONUS AVCISI V20 HATASI: {exc}")
        elif choice=="13":
            try:
                sonuc=radar.main()
                hafiza.record_scan("TAVAN_RADAR",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nTAVAN RADAR HATASI: {exc}")
        elif choice=="14":
            try:
                sonuc=v32_eod.main()
                hafiza.record_scan("V32_EOD",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nV32 GUN SONU HATASI: {exc}")
        elif choice=="15":
            try:
                sonuc=v32_live.main()
                hafiza.record_scan("V32_CANLI",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nV32 CANLI HATASI: {exc}")
        elif choice=="16":
            try:
                sonuc=v20_auto.main()
                hafiza.record_scan("TUM_MOTORLAR_V34",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nV20 OTOMATIK TEST HATASI: {exc}")
        elif choice=="17":
            try:
                sonuc=itick_live.main()
                hafiza.record_scan("ITICK_TOP3",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nV34 ITICK CANLI TAKIP HATASI: {exc}")
        elif choice=="18":
            try:
                sonuc=patlama_havuz.main()
                hafiza.record_scan("PATLAMA_ONCESI",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nPATLAMA ONCESI HAVUZ HATASI: {exc}")
        elif choice=="19":
            try:
                sonuc=v33_sep_test.main()
                hafiza.record_scan("V33_EYLUL_KOR_TEST",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nV33 EYLUL KOR TEST HATASI: {exc}")
        elif choice=="20":
            try:
                sonuc=erken3g.main()
                hafiza.record_scan("ERKEN3G_TOP10",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nERKEN-3G HAVUZ HATASI: {exc}")
        elif choice=="21":
            try:
                sonuc=erken3g_test.main()
                hafiza.record_scan("ERKEN3G_KOR_TEST",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nERKEN-3G KOR TEST HATASI: {exc}")
        elif choice=="22":
            try:
                sonuc=erken3g_live.main()
                hafiza.record_scan("ERKEN3G_DONUS_KESISIM",sonuc,source="MENU")
            except Exception as exc:
                print(f"\nERKEN-3G + DONUS KESISIM HATASI: {exc}")
        elif choice=="23":
            try:
                kesisim = erken3g_live.main()
                hafiza.record_scan("ERKEN3G_DONUS_ITICK_TOP3",kesisim,source="MENU")
                if kesisim is not None and not kesisim.empty:
                    itick_live.itick_external(kesisim, "ERKEN3G_DONUS_KESISIM")
                else:
                    print("\nKesisim adayi yok; iTick Top3 baslatilmadi.")
            except Exception as exc:
                print(f"\nERKEN-3G + DONUS + ITICK HATASI: {exc}")
        elif choice=="28":
            try:
                import balina_erken_kesisim
                sonuc=balina_erken_kesisim.main()
                hafiza.record_scan("BALINA_ERKEN3G_KESISIM",sonuc.drop(columns=["TETIK_GIRIS","CANLI_GIRIS"],errors="ignore"),source="MENU")
                if sonuc is not None and not sonuc.empty and "GIRIS_DURUMU" in sonuc:
                    tetik=sonuc[sonuc.GIRIS_DURUMU=="GIRIS_TETIKLENDI"].copy()
                    if not tetik.empty:
                        hafiza.record_scan("BALINA_ERKEN3G_CANLI_TETIK",tetik,source="MENU")
            except Exception as exc:
                print(f"BALINA ERKEN KESISIM HATASI: {exc}")
        elif choice=="27":
            try:
                import performance_summary
                performance_summary.main()
            except Exception as exc:
                print(f"BASARI OZET HATASI: {exc}")
        elif choice=="25":
            try:
                import memory_results
                memory_results.main()
            except Exception as exc:
                print(f"HAFIZA SONUC HATASI: {exc}")
        elif choice=="26":
            try:
                import balina_izi
                sonuc = balina_izi.main()
                hafiza.record_scan("BALINA_IZI", sonuc, source="MENU")
            except Exception as exc:
                print(f"BALINA IZI HATASI: {exc}")
        elif choice=="24":
            try:
                hafiza.main()
            except Exception as exc:
                print(f"\nTARAMA HAFIZASI HATASI: {exc}")
        else:
            print("Geçersiz seçim.")

        input("\nMenüye dönmek için ENTER'a basın...")

if __name__=="__main__":
    main()
