import hashlib
import os
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer
import ccxt
import requests

# --- SABİT GÖMÜLÜ TELEGRAM AYARLARI ---
BOT_TOKEN = "7820599329:AAEAa13edhS9PLoG1t8R34PLO9xpKlaT_Lc"
CHAT_ID = "-1004434260285"
TOPIC_ID = 3972

MIN_ARTIS_5M = 1.2
MIN_ARTIS_15M = 2.0
MIN_ARTIS_60M = 3.0

gonderilen_haberler = set()
son_fiyat_hafizasi = {}

# Render Ücretsiz Sunucu Dinleyicisi
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"KENDINE22TRADER Haber & BTC/ETH Botu 7/24 Aktif!")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

def turkceye_cevir(metin):
    if not metin or len(metin.strip()) == 0:
        return metin
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=tr&dt=t&q={urllib.parse.quote(metin)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=4).json()
        cevrilmis = "".join([c[0] for c in res[0] if c[0]])
        return cevrilmis if cevrilmis else metin
    except Exception:
        return metin

def telegram_mesaj_gonder(metin):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "message_thread_id": TOPIC_ID,
        "text": metin,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, data=data, timeout=8)
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def canli_haber_tara():
    haberler = []
    rss_kaynaklari = [
        {"ad": "CoinTelegraph", "url": "https://cointelegraph.com/rss"},
        {"ad": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
        {"ad": "Decrypt", "url": "https://decrypt.co/feed"},
        {"ad": "CryptoSlate", "url": "https://cryptoslate.com/feed/"},
        {"ad": "Bitcoin Magazine", "url": "https://bitcoinmagazine.com/feed"}
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for k in rss_kaynaklari:
        try:
            res = requests.get(k["url"], headers=headers, timeout=4)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                for item in root.findall("./channel/item")[:4]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    link = item.find("link").text if item.find("link") is not None else ""
                    if title and link:
                        haberler.append({"baslik": title.strip(), "kaynak": k["ad"], "link": link.strip()})
        except Exception:
            pass
            
    try:
        cp_res = requests.get("https://cryptopanic.com/api/v1/posts/?auth_token=free&public=true", timeout=4).json()
        for p in cp_res.get("results", [])[:6]:
            title = p.get("title", "")
            source_name = p.get("source", {}).get("title", "Kripto Gündem")
            url = p.get("url", "")
            if title and url:
                haberler.append({"baslik": title.strip(), "kaynak": source_name, "link": url.strip()})
    except Exception:
        pass

    for h in haberler:
        h_hash = hashlib.md5(h["baslik"].encode('utf-8')).hexdigest()
        if h_hash not in gonderilen_haberler:
            gonderilen_haberler.add(h_hash)
            turkce_baslik = turkceye_cevir(h["baslik"])
            tg_metin = (
                f"📰 <b>SON DAKİKA KRİPTO HABERİ</b>\n\n"
                f"🇹🇷 <b>{turkce_baslik}</b>\n\n"
                f"🇬🇧 <i>{h['baslik']}</i>\n\n"
                f"🌐 <b>Kaynak:</b> {h['kaynak']}\n"
                f"🔗 <a href='{h['link']}'>Haberi Oku ↗</a>"
            )
            telegram_mesaj_gonder(tg_metin)
            print(f"📰 Haber Gönderildi: {turkce_baslik[:35]}...")

def btc_eth_tara():
    mexc = ccxt.mexc({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
    pariteler = ['BTC/USDT', 'ETH/USDT']
    try:
        tickers = mexc.fetch_tickers(pariteler)
    except Exception:
        return
        
    for sembol in pariteler:
        if sembol in tickers:
            anlik_fiyat = tickers[sembol]['last']
            parite_kodu = sembol.replace('/', '')
            for tf, limit_mum, esik, sure_adi in [('5m', 6, MIN_ARTIS_5M, '5dk'), ('15m', 6, MIN_ARTIS_15M, '15dk'), ('1h', 6, MIN_ARTIS_60M, '60dk')]:
                try:
                    ohlcv = mexc.fetch_ohlcv(sembol, timeframe=tf, limit=limit_mum)
                    if len(ohlcv) >= 2:
                        baslangic_fiyat = ohlcv[0][1]
                        yuzde_fark = ((anlik_fiyat - baslangic_fiyat) / baslangic_fiyat) * 100
                        nakit_payi = round(38.0 + (abs(yuzde_fark) * 1.8) % 12, 2)
                        
                        if abs(yuzde_fark) >= esik:
                            yon_ikon = "🔼" if yuzde_fark > 0 else "🔽"
                            durum_ikon = "✅" if yuzde_fark > 0 else "⚠️"
                            isaret = "+" if yuzde_fark > 0 else ""
                            
                            alarm_mesaji = (
                                f"<b>{parite_kodu}</b> {yon_ikon} <b>%{isaret}{round(yuzde_fark, 2)} {sure_adi} içinde!</b> {anlik_fiyat}$ Ls:{durum_ikon}\n"
                                f"NakitPayı:%{nakit_payi}"
                            )
                            alarm_anahtari = f"{parite_kodu}_{tf}_{round(yuzde_fark, 1)}"
                            if alarm_anahtari not in son_fiyat_hafizasi.get(sembol, set()):
                                if sembol not in son_fiyat_hafizasi:
                                    son_fiyat_hafizasi[sembol] = set()
                                son_fiyat_hafizasi[sembol].add(alarm_anahtari)
                                telegram_mesaj_gonder(alarm_mesaji)
                                print(f"⚡ BTC/ETH Alarm: {alarm_mesaji}")
                except Exception:
                    pass

def main():
    threading.Thread(target=run_http_server, daemon=True).start()
    print("🚀 KENDİNE22TRADER Haber & BTC/ETH 7/24 Motoru Devrede...")
    while True:
        try:
            canli_haber_tara()
            btc_eth_tara()
        except Exception as e:
            print(f"Hata: {e}")
        time.sleep(20)

if __name__ == "__main__":
    main()
