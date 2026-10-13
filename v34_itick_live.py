from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
import urllib.request
import urllib.parse
from datetime import datetime

import pandas as pd
import websocket

import v19_2_canli as live
from v19_paths import result_file
from v34_decision_layer import enrich_candidates


# iTick mevcut ücretsiz paket aynı anda en fazla 3 sembol aboneliğine izin verir.
MAX_LIVE = 3
WS_URL = "wss://api.itick.org/stock"
REST_QUOTE_URL = "https://api.itick.org/stock/quote"


def _diag_log(event, detail=""):
    """iTick baglanti adimlarini sessizce kaybetme; sonradan teshis icin logla."""
    try:
        path = result_file("V34_ITICK_DIAGNOSTIK.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {event} | {detail}\n")
    except Exception:
        pass


def _prepare_candidates():
    """Yalnız Dönüş Avcısı; iTick sınırına uygun en güçlü üç aday."""
    print("\nDONUS AVCISI adaylari taraniyor...")
    reversal = live.reversal_main()
    if reversal is None or reversal.empty:
        return pd.DataFrame()
    out = reversal.copy()
    out["KAYNAK_MOTOR"] = "V20_DONUS_AVCISI"
    out["PUAN"] = pd.to_numeric(out.get("PUAN"), errors="coerce").fillna(0)
    out = out.sort_values("PUAN", ascending=False).drop_duplicates("HISSE").head(MAX_LIVE)
    out = enrich_candidates(out, "V20_DONUS_AVCISI")
    return out.sort_values(["V34_GUVEN", "PUAN"], ascending=False).head(MAX_LIVE)


def _save_session_summary(stats, lookup):
    """Her tick yerine, program durduğunda hisse başına tek satır kaydeder."""
    if not stats:
        return
    path = result_file("V34_ITICK_SEANS_OZETI.csv")
    old = pd.DataFrame()
    try:
        old = pd.read_csv(path)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        pass
    ended = datetime.now()
    rows = []
    for symbol, values in stats.items():
        candidate = lookup[symbol]
        entry = float(candidate.get("GIRIS", values["ILK_FIYAT"]))
        rows.append({
            "BASLANGIC": values["BASLANGIC"],
            "BITIS": ended.strftime("%Y-%m-%d %H:%M:%S"),
            "HISSE": symbol,
            "ILK_ANLIK_FIYAT": values["ILK_FIYAT"],
            "EN_YUKSEK": values["EN_YUKSEK"],
            "EN_DUSUK": values["EN_DUSUK"],
            "SON_FIYAT": values["SON_FIYAT"],
            "TARAMA_GIRIS": entry,
            "MAX_YUKSELIS_%": 100 * (values["EN_YUKSEK"] / entry - 1) if entry > 0 else 0,
            "MAX_DUSUS_%": 100 * (values["EN_DUSUK"] / entry - 1) if entry > 0 else 0,
            "SON_HAREKET_%": 100 * (values["SON_FIYAT"] / entry - 1) if entry > 0 else 0,
            "HAM_PUAN": candidate.get("HAM_PUAN"),
            "V34_GUVEN": candidate.get("V34_GUVEN"),
            "SINYAL_DURUMU": candidate.get("SINYAL_DURUMU"),
            "HEDEF_GORDU": bool(values["EN_YUKSEK"] >= float(candidate.get("HEDEF", float("inf")))),
            "STOP_GORDU": bool(values["EN_DUSUK"] <= float(candidate.get("STOP", 0))),
        })
    pd.concat([old, pd.DataFrame(rows)], ignore_index=True).to_csv(
        path, index=False, encoding="utf-8-sig"
    )
    print("\nSeans ozeti kaydedildi:", path)


def itick_live(candidates):
    key = os.environ.get("ITICK_KEY")
    if not key:
        print("\nHATA: ITICK_KEY bulunamadi.")
        print("PowerShell: $env:ITICK_KEY=\"ANAHTARINIZ\"")
        return

    lookup = {str(r.HISSE).replace(".IS", ""): r for _, r in candidates.iterrows()}
    symbols = list(lookup.keys())[:3]
    last_price = {}
    stats = {}
    lock = threading.Lock()

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BG_GREEN = "\033[42;97;1m"
    BG_RED = "\033[41;97;1m"
    BG_WHITE = "\033[47;30;1m"

    # Sabit terminal koordinatlari. Her sembol 4 satirlik bir karttir.
    CARD_START_ROWS = [5, 10, 15]
    PRICE_COL = 30
    STATUS_ROW = 20

    def _goto(row, col):
        sys.stdout.write(f"\033[{row};{col}H")

    def _erase_line(row):
        _goto(row, 1)
        sys.stdout.write("\033[2K")

    def _fmt(v, nd=0):
        try:
            return f"{float(v):.{nd}f}"
        except Exception:
            return "-"

    def _draw_price_box(row, price_text, color=BG_WHITE):
        # Sadece bu kutunun koordinatlarina yazilir; yeni satir uretilmez.
        width = 22
        top = "┌" + "─" * width + "┐"
        mid = "│" + f"{price_text:^{width}}" + "│"
        bot = "└" + "─" * width + "┘"
        for off, content in enumerate((top, mid, bot)):
            _goto(row + off, PRICE_COL)
            sys.stdout.write(color + content + RESET)
        sys.stdout.flush()

    def _draw_static_panel():
        sys.stdout.write("\033[2J\033[H")
        print(f"{BOLD}{GREEN}BIST - DÖNÜŞ AVCISI | CANLI TOP 3{RESET}")
        print(f"{DIM}3 sembol sabit kalir. Fiyat degisince sadece kutu yanip soner; asagi satir akmaz.{RESET}")
        print("=" * 74)

        for i, symbol in enumerate(symbols):
            row = CARD_START_ROWS[i]
            c = lookup[symbol]
            ham = c.get("HAM_PUAN", c.get("PUAN", "-"))
            guven = c.get("V34_GUVEN", c.get("PUAN", "-"))
            durum = str(c.get("SINYAL_DURUMU", "-"))

            _goto(row, 1)
            sys.stdout.write(f"{BOLD}{CYAN}#{i+1}  {symbol:<9}{RESET}")
            _goto(row+1, 1)
            sys.stdout.write(f"Ham Puan : {_fmt(ham):>4}")
            _goto(row+2, 1)
            sys.stdout.write(f"V34 Guven: {_fmt(guven):>4}")
            _goto(row+3, 1)
            sys.stdout.write(f"Durum    : {durum:<18}")
            _draw_price_box(row, "VERI BEKLENIYOR", BG_WHITE)

        _goto(STATUS_ROW, 1)
        sys.stdout.write(f"{DIM}Baglanti: iTick resmi endpoint | CTRL+C: cikis | Son veri: bekleniyor{RESET}")
        sys.stdout.flush()

    def _set_status(msg):
        with lock:
            _erase_line(STATUS_ROW)
            _goto(STATUS_ROW, 1)
            sys.stdout.write(f"{DIM}{msg:<74}{RESET}")
            sys.stdout.flush()

    def _flash_price(symbol, price, old):
        idx = symbols.index(symbol)
        row = CARD_START_ROWS[idx]

        if old is None:
            flash_color = BG_WHITE
        elif price > old:
            flash_color = BG_GREEN
        elif price < old:
            flash_color = BG_RED
        else:
            flash_color = BG_WHITE

        # Yanip sonme: renkli -> normal -> renkli -> normal.
        # Hep AYNI koordinata yazilir; terminale yeni satir basmaz.
        for color, delay in (
            (flash_color, 0.10),
            (BG_WHITE, 0.07),
            (flash_color, 0.10),
            (BG_WHITE, 0.0),
        ):
            with lock:
                _draw_price_box(row, f"{price:.2f} TL", color)
            if delay:
                import time
                time.sleep(delay)

    def _subscribe(ws):
        params = ",".join(f"{s}$TR" for s in symbols)
        payload = {"ac": "subscribe", "params": params, "types": "quote"}
        _diag_log("SUBSCRIBE_SEND", json.dumps(payload, ensure_ascii=False))
        ws.send(json.dumps(payload))
        _set_status(f"AUTH OK | Abonelik gonderildi: {', '.join(symbols)}")

    def _rest_snapshot():
        # WebSocket ilk tick'i beklerken iTick REST ile ilk fiyat denenir.
        # Hata artik sessizce yutulmaz; diagnostik loga yazilir.
        ok = 0
        for symbol in symbols:
            try:
                qs = urllib.parse.urlencode({"region": "TR", "code": symbol})
                req = urllib.request.Request(
                    REST_QUOTE_URL + "?" + qs,
                    headers={"accept": "application/json", "token": key},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = resp.read().decode("utf-8")
                payload = json.loads(raw)
                data = payload.get("data") or {}
                price = data.get("ld")
                _diag_log("REST", f"{symbol} code={payload.get('code')} msg={payload.get('msg')} ld={price}")
                if price is not None:
                    price = float(price)
                    last_price[symbol] = price
                    idx = symbols.index(symbol)
                    with lock:
                        _draw_price_box(CARD_START_ROWS[idx], f"{price:.2f} TL", BG_WHITE)
                    ok += 1
            except Exception as exc:
                _diag_log("REST_HATA", f"{symbol}: {type(exc).__name__}: {exc}")
        if ok:
            _set_status(f"iTick REST baslangic fiyati: {ok}/{len(symbols)} sembol | WebSocket bekleniyor")
        else:
            _set_status("iTick REST fiyat gelmedi | WebSocket auth/abonelik bekleniyor | log kaydedildi")

    def _heartbeat(ws):
        # iTick dokumani uygulama-seviyesinde ping ister; TCP/WebSocket ping tek basina yeterli sayilmayabilir.
        while True:
            try:
                time.sleep(25)
                ts = str(int(time.time() * 1000))
                ws.send(json.dumps({"ac": "ping", "params": ts}))
            except Exception as exc:
                _diag_log("PING_STOP", str(exc))
                return

    def on_open(ws):
        # Token header ile baglanilir; auth cevabi sunucudan otomatik gelir.
        _diag_log("WS_OPEN", WS_URL)
        _set_status("iTick socket acildi | AUTH cevabi bekleniyor...")
        threading.Thread(target=_rest_snapshot, daemon=True).start()
        threading.Thread(target=_heartbeat, args=(ws,), daemon=True).start()

    def on_message(ws, message):
        try:
            msg = json.loads(message)

            # Kontrol cevaplarini logla; piyasa ticklerini log dosyasina yagdirma.
            if msg.get("resAc") or not msg.get("data"):
                _diag_log("WS_MSG", str(msg)[:1200])

            # Sunucu protokol cevaplarini sessizce yutma: ekranda goster.
            if msg.get("resAc") == "auth":
                if int(msg.get("code", 0)) == 1:
                    _subscribe(ws)
                else:
                    _set_status(f"ITICK AUTH HATASI: {msg.get('msg', 'auth failed')}")
                return

            if msg.get("resAc") == "subscribe":
                if int(msg.get("code", 0)) == 1:
                    _set_status(f"iTick CANLI | Abonelik aktif: {', '.join(symbols)} | Ilk fiyat bekleniyor")
                else:
                    _set_status(f"ITICK ABONELIK HATASI: {msg.get('msg', 'subscribe failed')}")
                return

            if msg.get("resAc") == "pong":
                return

            # Baglanti / protokol mesajlarini da tani.
            if not msg.get("data"):
                if int(msg.get("code", 1)) == 0:
                    _set_status(f"ITICK HATA: {msg.get('msg', msg)}")
                elif str(msg.get("msg", "")).lower().startswith("connected"):
                    _set_status("iTick sunucu baglantisi OK | AUTH bekleniyor...")
                return

            data = msg.get("data") or {}
            symbol = str(data.get("s") or "").replace("$TR", "").upper()
            price = data.get("ld")
            if symbol not in lookup or price is None:
                _diag_log("VERI_ESLESMEDI", f"symbol={symbol} price={price} type={data.get('type')} keys={list(data.keys())}")
                return

            price = float(price)
            old = last_price.get(symbol)
            if old == price:
                return

            last_price[symbol] = price

            if symbol not in stats:
                stats[symbol] = {
                    "BASLANGIC": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ILK_FIYAT": price,
                    "EN_YUKSEK": price,
                    "EN_DUSUK": price,
                    "SON_FIYAT": price,
                }
            else:
                stats[symbol]["EN_YUKSEK"] = max(stats[symbol]["EN_YUKSEK"], price)
                stats[symbol]["EN_DUSUK"] = min(stats[symbol]["EN_DUSUK"], price)
                stats[symbol]["SON_FIYAT"] = price

            # Fiyat animasyonunu ayri thread'de yap; websocket akisini bloklama.
            t = threading.Thread(target=_flash_price, args=(symbol, price, old), daemon=True)
            t.start()
            _set_status(
                f"Baglanti: iTick | Son veri: {symbol} {price:.2f} TL | {datetime.now():%H:%M:%S}"
            )

        except Exception as exc:
            _set_status(f"VERI HATASI: {exc}")

    def on_error(ws, error):
        _diag_log("WS_ERROR", f"{type(error).__name__}: {error}")
        _set_status(f"ITICK HATASI: {error}")

    def on_close(ws, code, msg):
        _diag_log("WS_CLOSE", f"code={code} msg={msg}")
        _set_status(f"ITICK BAGLANTISI KAPANDI: {code} {msg}")

    _draw_static_panel()

    ws = websocket.WebSocketApp(
        WS_URL,
        header=[f"token: {key}"],
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    try:
        ws.run_forever(ping_interval=20, ping_timeout=10)
    except KeyboardInterrupt:
        _set_status("Anlik takip kullanici tarafindan durduruldu.")
    finally:
        _save_session_summary(stats, lookup)
        _goto(STATUS_ROW + 2, 1)
        sys.stdout.write("\n")


def prepare_external_candidates(df, source="ERKEN3G_DONUS_KESISIM"):
    """Kesisim gibi harici bir aday listesini mevcut sabit 3 iTick paneline uyarlar."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out["HISSE"] = out["HISSE"].astype(str).str.replace(".IS", "", regex=False).str.upper()
    out["KAYNAK_MOTOR"] = source
    # Sabit panel / seans ozeti mevcut alan adlarini kullanmaya devam etsin.
    if "PUAN" not in out.columns:
        out["PUAN"] = pd.to_numeric(out.get("DONUS_PUAN", out.get("BIRLESIK_SKOR", 0)), errors="coerce").fillna(0)
    out["HAM_PUAN"] = pd.to_numeric(out.get("DONUS_PUAN", out.get("BIRLESIK_SKOR", 0)), errors="coerce").fillna(0)
    out["V34_GUVEN"] = pd.to_numeric(out.get("BIRLESIK_SKOR", out.get("ERKEN3G_SKOR", 0)), errors="coerce").fillna(0)
    out["SINYAL_DURUMU"] = out.get("TEYIT", pd.Series("KESISIM", index=out.index)).astype(str)
    if "GIRIS" not in out.columns:
        out["GIRIS"] = pd.to_numeric(out.get("CANLI_GIRIS"), errors="coerce")
    # Hedef/stop yoksa seans ozeti hata vermesin; bu katman emir uretmez.
    if "HEDEF" not in out.columns:
        out["HEDEF"] = float("inf")
    if "STOP" not in out.columns:
        out["STOP"] = 0.0
    if "RISK_ODUL" not in out.columns:
        out["RISK_ODUL"] = None
    return out.sort_values(["V34_GUVEN", "HAM_PUAN"], ascending=False).drop_duplicates("HISSE").head(MAX_LIVE)


def itick_external(df, source="ERKEN3G_DONUS_KESISIM"):
    candidates = prepare_external_candidates(df, source)
    if candidates.empty:
        print("iTick'e aktarilacak kesisim adayi bulunamadi.")
        return candidates
    cols = [c for c in ["HISSE","KAYNAK_MOTOR","V34_GUVEN","HAM_PUAN","SINYAL_DURUMU","ADAY_TIPI","ZAMANLAMA_3G","PARA_GIRISI","GIRIS"] if c in candidates.columns]
    print("\nITICK'E AKTARILAN KESISIM TOP 3")
    print(candidates[cols].to_string(index=False))
    candidates.to_csv(result_file("V34_ITICK_KESISIM_TOP3.csv"), index=False, encoding="utf-8-sig")
    itick_live(candidates)
    return candidates

def main():
    candidates = _prepare_candidates()
    if candidates.empty:
        print("Canli takibe aktarilacak aday bulunamadi.")
        return candidates
    cols = ["HISSE", "KAYNAK_MOTOR", "HAM_PUAN", "V34_GUVEN",
            "SINYAL_DURUMU", "GIRIS", "STOP", "HEDEF", "RISK_ODUL"]
    cols = [c for c in cols if c in candidates.columns]
    print("\nITICK'E AKTARILAN EN GUCLU 3 ADAY")
    print(candidates[cols].to_string(index=False))
    candidates.to_csv(result_file("V34_ITICK_ADAYLAR.csv"), index=False, encoding="utf-8-sig")
    itick_live(candidates)
    return candidates


if __name__ == "__main__":
    main()
