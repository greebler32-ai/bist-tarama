from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo
import time

import numpy as np
import pandas as pd
import yfinance as yf

import v19_2_canli as live
import v19_3_tavan_radar as radar
import v32_live_tavan as v32_live
import v32_eod_hazirlik as v32_eod
import v33_eod_combined as v33_eod
import erken3g_havuz as erken3g
import patlama_oncesi_havuz as patlama
import balina_izi
import candidate_memory as hafiza
from v34_decision_layer import enrich_candidates
from v34_performance_ledger import candidate_id, initialise_rows, evaluate_path, apply_result
from v19_paths import result_file

IST = ZoneInfo("Europe/Istanbul")
SCAN_TIMES = (dtime(10, 30), dtime(12, 0), dtime(14, 30), dtime(16, 45))
CLOSE_EVAL = dtime(18, 15)
TEST_SESSIONS = 20
LEDGER = "TUM_CANLI_OTOMATIK_ILK_SINYALLER.csv"
RUN_LOG = "TUM_TARAMALAR_OTOMATIK_CALISMA_LOG.csv"
SUMMARY = "TUM_CANLI_MOTOR_BASARI_OZETI.csv"
EOD_LEDGER = "V33_GUN_SONU_ADAY_YASAM_DONGUSU.csv"

LIVE_ENGINES = (
    ("V19_2_CANLI_TRADE", lambda: live.momentum_main("15m")),
    ("V19_2_CANLI_TAVAN", lambda: live.tavan_main("15m")),
    ("V20_DONUS_AVCISI", live.reversal_main),
    ("V19_3_TAVAN_RADAR", lambda: radar.main("15m")),
    ("V32_CANLI_TAVAN", lambda: v32_live.main("15m")),
)

EOD_ENGINES = (
    ("V33_GUN_SONU_TOP10", v33_eod.main),
    ("V32_GUN_SONU_HAZIRLIK", v32_eod.main),
    ("ERKEN3G_HAVUZ", erken3g.main),
    ("PATLAMA_ONCESI", lambda: pd.DataFrame(patlama.main())),
    ("BALINA_IZI", balina_izi.main),
)


def _read_csv(path):
    try:
        return pd.read_csv(path)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def _append_run(now, slot, count, status):
    path = result_file(RUN_LOG)
    old = _read_csv(path)
    row = pd.DataFrame([{
        "TARIH": now.strftime("%Y-%m-%d"), "SAAT": now.strftime("%H:%M:%S"),
        "PLANLI_SAAT": slot, "ADAY_SAYISI": int(count), "DURUM": status,
    }])
    pd.concat([old, row], ignore_index=True).to_csv(path, index=False, encoding="utf-8-sig")


def _save_first_signals(found, now, slot, motor="V20_DONUS_AVCISI"):
    if found is None or found.empty:
        _append_run(now, slot, 0, "ADAY_YOK")
        return 0
    found = enrich_candidates(found, motor, now)
    path = result_file(LEDGER)
    old = _read_csv(path)
    add = found.copy()
    add["MOTOR"] = motor
    add["SINYAL_TARIHI"] = now.strftime("%Y-%m-%d")
    add["ILK_SINYAL_ZAMANI"] = now.strftime("%Y-%m-%d %H:%M:%S")
    add["TARAMA_SLOTU"] = slot
    add["GIRIS_TURU"] = "YAHOO_GECIKMELI"
    add["ANLIK_GIRIS"] = np.nan
    add = initialise_rows(add, motor, now, slot)
    for col in ("D0_MAX_%", "D0_KAPANIS_%", "D1_MAX_%", "D1_KAPANIS_%"):
        add[col] = np.nan
    for day in ("D0", "D1"):
        for target in (5, 7, 9):
            add[f"{day}_{target}"] = False
    if not old.empty:
        existing = set(zip(old["SINYAL_TARIHI"].astype(str), old["MOTOR"].astype(str), old["HISSE"].astype(str)))
        keep = [((str(d), motor, str(s)) not in existing) for d, s in zip(add.SINYAL_TARIHI, add.HISSE)]
        add = add.loc[keep]
    pd.concat([old, add], ignore_index=True).to_csv(path, index=False, encoding="utf-8-sig")
    _append_run(now, slot, len(add), "KAYDEDILDI")
    print(f"{motor} | Ilk kez kaydedilen aday: {len(add)} | Dosya: {path}")
    return len(add)


def _save_eod_candidates(found, now, slot, motor):
    """Gun sonu motorunun yalniz ekranda gosterdigi Top10'u kalici izler."""
    if found is None or found.empty or "HISSE" not in found:
        return 0
    add = found.head(10).copy()
    add["MOTOR"] = motor
    add["SINYAL_TARIHI"] = now.strftime("%Y-%m-%d")
    add["ILK_SINYAL_ZAMANI"] = now.strftime("%Y-%m-%d %H:%M:%S")
    add["TARAMA_SLOTU"] = slot
    add = initialise_rows(add, motor, now, slot)
    path = result_file(EOD_LEDGER)
    old = _read_csv(path)
    if not old.empty and "ADAY_ID" in old:
        add = add.loc[~add["ADAY_ID"].isin(set(old["ADAY_ID"].astype(str)))]
    pd.concat([old, add], ignore_index=True).to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Gun sonu yasam dongusune eklenen Top10: {len(add)} | {path}")
    return len(add)


def _success_summary(df, now):
    """Motorlari birbirine karistirmadan D0/D1 basarisini raporlar."""
    rows = []
    groups = [("TUM_MOTORLAR", df)] + list(df.groupby("MOTOR", dropna=False))
    for motor, part in groups:
        for day in ("D0", "D1"):
            valid = part[pd.to_numeric(part[f"{day}_MAX_%"], errors="coerce").notna()].copy()
            vals = pd.to_numeric(valid[f"{day}_MAX_%"], errors="coerce")
            closes = pd.to_numeric(valid[f"{day}_KAPANIS_%"], errors="coerce")
            rows.append({
                "RAPOR_ZAMANI": now.strftime("%Y-%m-%d %H:%M:%S"),
                "MOTOR": str(motor), "GUN": day,
                "TOPLAM_SINYAL": int(len(part)), "DEGERLENDIRILEN": int(len(valid)),
                "ORT_MAX_%": vals.mean() if len(valid) else np.nan,
                "ORT_KAPANIS_%": closes.mean() if len(valid) else np.nan,
                "POZITIF_KAPANIS_%": 100 * (closes > 0).mean() if len(valid) else np.nan,
                "BASARI_5_%": 100 * (vals >= 5).mean() if len(valid) else np.nan,
                "BASARI_7_%": 100 * (vals >= 7).mean() if len(valid) else np.nan,
                "BASARI_9_%": 100 * (vals >= 9).mean() if len(valid) else np.nan,
                "VERI_NOTU": "GIRIS Yahoo gecikmeli olabilir; PhilipCapital anlik giris degildir",
            })
    out = pd.DataFrame(rows)
    path = result_file(SUMMARY)
    out.to_csv(path, index=False, encoding="utf-8-sig")
    stamped = result_file(f"TUM_CANLI_MOTOR_BASARI_OZETI_{now:%Y%m%d_%H%M}.csv")
    out.to_csv(stamped, index=False, encoding="utf-8-sig")
    print("\nMOTOR BAZLI BASARI OZETI")
    show = ["MOTOR", "GUN", "DEGERLENDIRILEN", "ORT_MAX_%", "POZITIF_KAPANIS_%",
            "BASARI_5_%", "BASARI_7_%", "BASARI_9_%"]
    with pd.option_context("display.width", 180):
        print(out[show].to_string(index=False))
    print("Dönüş Avcısı diğer motorlardan ayrı raporlanır.")
    print("Başarı özeti:", path)
    return out


def _intraday(symbol):
    d = yf.download(symbol + ".IS", period="1mo", interval="5m", auto_adjust=False,
                    progress=False, threads=False, timeout=15)
    return live.flat(d)


def evaluate_ledger(now=None):
    now = now or datetime.now(IST)
    path = result_file(LEDGER)
    df = _read_csv(path)
    if df.empty:
        print("Degerlendirilecek canli tarama sinyali yok.")
        return df
    if "ADAY_ID" not in df:
        df["ADAY_ID"] = ""
    for idx, row in df.iterrows():
        try:
            if not str(row.get("ADAY_ID", "")).strip() or str(row.get("ADAY_ID", "")).lower() == "nan":
                df.at[idx, "ADAY_ID"] = candidate_id(
                    row.get("SINYAL_TARIHI", ""), row.get("MOTOR", ""),
                    row.get("HISSE", ""), row.get("TARAMA_SLOTU", ""))
            entry = float(row["GIRIS"])
            signal_at = pd.Timestamp(row["ILK_SINYAL_ZAMANI"])
            bars = _intraday(str(row["HISSE"]))
            if bars.empty or entry <= 0:
                continue
            dates = sorted({x for x in bars.index.date if x >= signal_at.date()})
            d0 = bars[(bars.index.date == signal_at.date()) & (bars.index >= signal_at)]
            if not d0.empty:
                df.at[idx, "D0_MAX_%"] = 100 * (float(d0.High.max()) / entry - 1)
                df.at[idx, "D0_KAPANIS_%"] = 100 * (float(d0.Close.iloc[-1]) / entry - 1)
            next_dates = [x for x in dates if x > signal_at.date()]
            if next_dates:
                d1 = bars[bars.index.date == next_dates[0]]
                df.at[idx, "D1_MAX_%"] = 100 * (float(d1.High.max()) / entry - 1)
                df.at[idx, "D1_KAPANIS_%"] = 100 * (float(d1.Close.iloc[-1]) / entry - 1)
            path = pd.concat([d0, d1 if next_dates else pd.DataFrame()]).sort_index()
            apply_result(df, idx, evaluate_path(row, path, entry, now))
            for day in ("D0", "D1"):
                val = df.at[idx, f"{day}_MAX_%"]
                if pd.notna(val):
                    for target in (5, 7, 9):
                        df.at[idx, f"{day}_{target}"] = bool(float(val) >= target)
        except Exception as exc:
            print(f"Degerlendirme atlandi: {row.get('HISSE')} | {exc}")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    report = result_file(f"TUM_CANLI_D0_D1_DEGERLENDIRME_{now:%Y%m%d_%H%M}.csv")
    df.to_csv(report, index=False, encoding="utf-8-sig")
    print("D+0 / D+1 raporu:", report)
    _success_summary(df, now)
    return df


def evaluate_eod_ledger(now=None):
    """V33 Top10'un sonraki seansta MFE/MAE ve hedef zamanlarini tamamlar."""
    now = now or datetime.now(IST)
    path = result_file(EOD_LEDGER)
    df = _read_csv(path)
    if df.empty:
        return df
    if "ADAY_ID" not in df:
        df["ADAY_ID"] = ""
    for idx, row in df.iterrows():
        try:
            if not str(row.get("ADAY_ID", "")).strip() or str(row.get("ADAY_ID", "")).lower() == "nan":
                df.at[idx, "ADAY_ID"] = candidate_id(
                    row.get("SINYAL_TARIHI", ""), row.get("MOTOR", ""),
                    row.get("HISSE", ""), row.get("TARAMA_SLOTU", ""))
            signal_date = pd.Timestamp(row["SINYAL_TARIHI"]).date()
            entry = float(row["GIRIS"])
            bars = _intraday(str(row["HISSE"]))
            dates = sorted({x for x in bars.index.date if x > signal_date})
            if not dates:
                continue
            d1 = bars[bars.index.date == dates[0]]
            if d1.empty:
                continue
            df.at[idx, "D1_MAX_%"] = 100 * (float(d1.High.max()) / entry - 1)
            df.at[idx, "D1_KAPANIS_%"] = 100 * (float(d1.Close.iloc[-1]) / entry - 1)
            for target in (5, 7, 9):
                df.at[idx, f"D1_{target}"] = bool(float(df.at[idx, "D1_MAX_%"]) >= target)
            apply_result(df, idx, evaluate_path(row, d1, entry, now))
        except Exception as exc:
            print(f"V33 yasam dongusu atlandi: {row.get('HISSE')} | {exc}")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print("V33 Top10 yasam dongusu:", path)
    return df


def _completed_sessions():
    log = _read_csv(result_file(RUN_LOG))
    if log.empty:
        return 0
    return int(log.loc[log.DURUM == "KAPANIS_DEGERLENDIRILDI", "TARIH"].nunique())


def run_live_slot(slot):
    for motor, fn in LIVE_ENGINES:
        print(f"\n{'='*80}\nOTOMATIK MOTOR: {motor} | SLOT: {slot}\n{'='*80}")
        try:
            found = fn()
            hafiza.record_scan(motor,found,source="OTOMATIK",note=slot)
            _save_first_signals(found, datetime.now(IST), slot, motor)
        except Exception as exc:
            print(f"{motor} HATASI: {exc}")
            _append_run(datetime.now(IST), slot, 0, f"HATA:{motor}:{exc}")


def run_eod_once(slot="GUN_SONU"):
    for motor, fn in EOD_ENGINES:
        print(f"\n{'='*80}\nGUN SONU MOTORU: {motor}\n{'='*80}")
        try:
            found = fn()
            hafiza.record_scan(motor,found,source="OTOMATIK",note=slot)
            if motor in {"V33_GUN_SONU_TOP10","V32_GUN_SONU_HAZIRLIK"}:
                found = enrich_candidates(found, motor, datetime.now(IST))
            if found is not None and not found.empty:
                enriched_path = result_file(f"{motor}_V34_{datetime.now(IST):%Y%m%d_%H%M}.csv")
                found.to_csv(enriched_path, index=False, encoding="utf-8-sig")
                print("V34 karar katmani:", enriched_path)
                if motor == "V33_GUN_SONU_TOP10":
                    _save_eod_candidates(found, datetime.now(IST), slot, motor)
            count = 0 if found is None else len(found)
            _append_run(datetime.now(IST), slot, count, f"GUN_SONU_KAYDEDILDI:{motor}")
        except Exception as exc:
            print(f"{motor} HATASI: {exc}")
            _append_run(datetime.now(IST), slot, 0, f"HATA:{motor}:{exc}")


def _daytime_eod_already_ran(day):
    """Program yeniden açılsa da gündüz D-1 taramasını aynı gün çoğaltma."""
    log = _read_csv(result_file(RUN_LOG))
    if log.empty or "PLANLI_SAAT" not in log or "TARIH" not in log:
        return False
    return bool(((log["TARIH"].astype(str) == day) &
                 (log["PLANLI_SAAT"].astype(str) == "GUN_ICI_D1") &
                 (log["DURUM"].astype(str).str.startswith("GUN_SONU_KAYDEDILDI"))).any())


def main():
    print("\nTUM CANLI MOTORLAR + GUN SONU | 20 SEANS ILERI TEST")
    print("Canli: 10:30 / 12:00 / 14:30 / 16:45")
    print("Gunluk motorlar: seans icinde D-1 ile bir kez + 18:15 kapanis sonrasi bir kez")
    print("Bu pencere test boyunca acik kalmalidir. Durdurmak icin CTRL+C.")
    if _completed_sessions() >= TEST_SESSIONS:
        print("20 tamamlanmis test seansina ulasildi. Yeni kayit yapilmadi.")
        return
    done = set()
    while True:
        now = datetime.now(IST)
        if now.weekday() >= 5:
            print("Hafta sonu; otomatik test kapatildi.")
            return
        day = now.strftime("%Y-%m-%d")
        # Seans içinde hangi saatte açılırsa açılsın yalnız bir defa çalışır.
        # V33/V32 tamamlanmamış son günlük mumu kendi içinde dışladığı için
        # bu çıktı bugünü değil, son tamamlanmış seansı (D-1) kullanır.
        daytime_key = (day, "GUN_ICI_D1")
        if (dtime(10, 0) <= now.time() <= dtime(17, 30) and
                daytime_key not in done and not _daytime_eod_already_ran(day)):
            print("\nGUN ICI GUNLUK TARAMA BASLADI | D-1 TAMAMLANMIS MUM")
            run_eod_once("GUN_ICI_D1")
            done.add(daytime_key)
        for planned in SCAN_TIMES:
            key = (day, planned.strftime("%H:%M"))
            deadline = (datetime.combine(now.date(), planned, IST) + timedelta(minutes=20)).time()
            if key not in done and planned <= now.time() <= deadline:
                print(f"\nTum canli motorlar basladi: {key[1]}")
                run_live_slot(key[1])
                done.add(key)
        close_key = (day, "18:15")
        if close_key not in done and CLOSE_EVAL <= now.time() <= dtime(18, 40):
            evaluate_ledger(now)
            evaluate_eod_ledger(now)
            run_eod_once("KAPANIS_1815")
            _append_run(now, "18:15", 0, "KAPANIS_DEGERLENDIRILDI")
            done.add(close_key)
            print(f"Tamamlanan test seansi: {_completed_sessions()}/{TEST_SESSIONS}")
            return
        if now.time() > dtime(18, 40):
            print("Bugunun otomatik test penceresi sona erdi.")
            return
        time.sleep(20)


if __name__ == "__main__":
    main()
