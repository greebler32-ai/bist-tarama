from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

from symbols import get_bist_symbols
from v19_paths import result_file
import v33_eod_combined as v33

IST = ZoneInfo("Europe/Istanbul")

START = pd.Timestamp("2026-09-01")
END = pd.Timestamp("2026-09-10")
TAVAN_THRESHOLD = 9.50


def _flat(d):
    if d is None or d.empty:
        return pd.DataFrame()
    x = d.copy()
    if isinstance(x.columns, pd.MultiIndex):
        x.columns = [c[0] for c in x.columns]
    x.columns = [str(c).title() for c in x.columns]
    idx = pd.DatetimeIndex(x.index)
    if idx.tz is not None:
        idx = idx.tz_convert("Europe/Istanbul").tz_localize(None)
    x.index = idx.normalize()
    return x[~x.index.duplicated(keep="last")].sort_index()


def _features_hist(d):
    return v33._features(_flat(d),completed=True)


def _download_all(download_start="2025-01-01",download_end="2026-09-12"):
    syms = get_bist_symbols()
    raw = {}
    feat = {}

    print("\nV33 EYLUL KOR TEST - veri indiriliyor...")
    for i, s in enumerate(syms, 1):
        print(f"\r[{i}/{len(syms)}] {s:<14}", end="", flush=True)
        try:
            d = yf.download(
                s,
                start=download_start,
                end=download_end,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=15,
            )
            d = _flat(d)
            if len(d) >= 150:
                raw[s] = d
                feat[s] = _features_hist(d)
        except Exception:
            pass
    print()
    return raw, feat


def _trading_days(raw):
    days = set()
    for d in raw.values():
        days.update(x for x in d.index if START <= x <= END)
    return sorted(days)


def _previous_day(days, day):
    idx = days.index(day)
    if idx <= 0:
        return None
    return days[idx - 1]


def _score_on_day(feature_df, cutoff):
    if cutoff not in feature_df.index:
        eligible = feature_df.index[feature_df.index <= cutoff]
        if len(eligible) == 0:
            return None
        cutoff = eligible[-1]
    x = feature_df.loc[:cutoff]
    if len(x) < 150:
        return None
    return v33._score(x)


def main(start=None,end=None):
    from erken3g_kor_test import test_window
    if start is None:start=input('Baslangic YYYY-AA-GG [2026-09-01]: ').strip() or '2026-09-01'
    if end is None:end=input('Bitis YYYY-AA-GG [2026-09-10]: ').strip() or '2026-09-10'
    test_start,test_end,download_start,download_end=test_window(start,end)
    raw, feat = _download_all(download_start,download_end)
    if not raw:
        print("Veri indirilemedi.")
        return

    # Tum piyasanin takvimini kullan: 1 Eylul tahmini icin 31 Agustos da dahil olsun.
    market=_flat(yf.download("XU100.IS",start=download_start,end=download_end,interval="1d",auto_adjust=False,progress=False,threads=False,timeout=15))
    if market.empty:raise RuntimeError("XU100 seans verisi alinamadi; test durduruldu.")
    all_days=list(market.index)
    test_days = [d for d in all_days if test_start <= d <= test_end]

    daily_rows = []
    candidate_rows = []

    total_tavan = 0
    total_caught = 0
    total_top10 = 0
    total_top10_5 = 0
    total_top10_7 = 0
    total_top10_9 = 0

    print("\n" + "=" * 122)
    print("V33 | TARIH SECILEBILIR KOR TEST")
    print("Her hedef gun icin yalnizca BIR ONCEKI TAMAMLANMIS kapanisa kadar veri kullanilir.")
    print("=" * 122)

    for target_day in test_days:
        pos = all_days.index(target_day)
        if pos == 0:
            continue
        cutoff = all_days[pos - 1]

        scored = []
        actual_tavans = []

        for s, f in feat.items():
            # Hedef gunun gercek getirisi
            rd = raw[s]
            if target_day not in rd.index:
                continue

            try:
                prev_close = float(rd.loc[cutoff, "Close"]) if cutoff in rd.index else None
                target_close = float(rd.loc[target_day, "Close"])
                if prev_close and prev_close > 0:
                    actual_ret = (target_close / prev_close - 1) * 100
                else:
                    continue
            except Exception:
                continue

            if actual_ret >= TAVAN_THRESHOLD:
                actual_tavans.append((s.replace(".IS", ""), actual_ret))

            try:
                rec = _score_on_day(f, cutoff)
                if rec:
                    rec = dict(rec)
                    rec["HISSE"] = s.replace(".IS", "")
                    rec["TAHMIN_ICIN_VERI_TARIHI"] = cutoff.strftime("%Y-%m-%d")
                    rec["HEDEF_GUN"] = target_day.strftime("%Y-%m-%d")
                    rec["GERCEK_D1_%"] = actual_ret
                    rec["TAVAN_D1"] = actual_ret >= TAVAN_THRESHOLD
                    scored.append(rec)
            except Exception:
                pass

        if scored:
            df = pd.DataFrame(scored).sort_values(
                ["V33_SKOR", "MOTOR_E_DEVAM", "MOTOR_D_ERKEN", "MOTOR_B", "MOTOR_A", "RVOL"],
                ascending=False,
            )
            top = df.head(10).copy()
        else:
            top = pd.DataFrame()

        tavan_symbols = {x[0] for x in actual_tavans}
        top_symbols = set(top["HISSE"]) if not top.empty else set()
        caught = sorted(tavan_symbols & top_symbols)
        missed = sorted(tavan_symbols - top_symbols)

        total_tavan += len(tavan_symbols)
        total_caught += len(caught)
        total_top10 += len(top)

        if not top.empty:
            total_top10_5 += int((top["GERCEK_D1_%"] >= 5.0).sum())
            total_top10_7 += int((top["GERCEK_D1_%"] >= 7.0).sum())
            total_top10_9 += int((top["GERCEK_D1_%"] >= 9.0).sum())

            for _, r in top.iterrows():
                candidate_rows.append(r.to_dict())

        daily_rows.append({
            "HEDEF_GUN": target_day.strftime("%Y-%m-%d"),
            "VERI_CUTOFF": cutoff.strftime("%Y-%m-%d"),
            "TAVAN_SAYISI": len(tavan_symbols),
            "V33_TOP10_TAVAN_YAKALADI": len(caught),
            "YAKALANAN_TAVANLAR": ",".join(caught) if caught else "-",
            "KACIRILAN_TAVANLAR": ",".join(missed) if missed else "-",
            "TOP10_5PLUS": int((top["GERCEK_D1_%"] >= 5.0).sum()) if not top.empty else 0,
            "TOP10_7PLUS": int((top["GERCEK_D1_%"] >= 7.0).sum()) if not top.empty else 0,
            "TOP10_9PLUS": int((top["GERCEK_D1_%"] >= 9.0).sum()) if not top.empty else 0,
        })

        print(
            f"{target_day:%d.%m} | Tavan: {len(tavan_symbols):2d} | "
            f"Top10 yakaladi: {len(caught):2d} | "
            f"+5: {daily_rows[-1]['TOP10_5PLUS']:2d} | "
            f"+7: {daily_rows[-1]['TOP10_7PLUS']:2d} | "
            f"+9: {daily_rows[-1]['TOP10_9PLUS']:2d}"
        )
        if caught:
            print("   YAKALANAN :", ", ".join(caught))
        if missed:
            print("   KACIRILAN :", ", ".join(missed))

    daily_df = pd.DataFrame(daily_rows)
    cand_df = pd.DataFrame(candidate_rows)

    print("\n" + "=" * 122)
    print("SECILEN DONEM OZET")
    print("=" * 122)
    print(f"Toplam tavan kapanisi (gun-hisse): {total_tavan}")
    print(f"V33 Top10 icinde yakalanan       : {total_caught}")
    hit_rate = 100 * total_caught / total_tavan if total_tavan else 0.0
    print(f"Tavan yakalama orani             : %{hit_rate:.2f}")
    print(f"Top10 aday-gun sayisi            : {total_top10}")
    print(f"Top10 +5 ve uzeri                : {total_top10_5}")
    print(f"Top10 +7 ve uzeri                : {total_top10_7}")
    print(f"Top10 +9 ve uzeri                : {total_top10_9}")

    now = datetime.now(IST)
    daily_path = result_file(f"V33_FIX4_EYLUL_KOR_TEST_GUNLUK_{now:%Y%m%d_%H%M}.csv")
    cand_path = result_file(f"V33_FIX4_EYLUL_KOR_TEST_TOP10_DETAY_{now:%Y%m%d_%H%M}.csv")
    daily_df.to_csv(daily_path, index=False, encoding="utf-8-sig")
    cand_df.to_csv(cand_path, index=False, encoding="utf-8-sig")

    print("\nKaydedildi:")
    print(" -", daily_path)
    print(" -", cand_path)


if __name__ == "__main__":
    main()
