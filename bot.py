import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
import feedparser
from deep_translator import GoogleTranslator
import requests

# --- SABİT BOT VE TELEGRAM AYARLARI ---
BOT_TOKEN = "7820599329:AAEAa13edhS9PLoG1t8R34PLO9xpKlaT_Lc"
CHAT_ID = "-1004434260285"
TOPIC_ID = 3972

hafiza = set()
translator = GoogleTranslator(source='auto', target='tr')

# Render Port Dinleyicisi
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"KENDINE22TRADER Haber Botu 7/24 Aktif!")

    def log_message(self, format, *args):
        return

def start_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

def telegram_haber_gonder(baslik, ozet, link, kaynak):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    # Otomatik Türkçe Çeviri
    try:
        baslik_tr = translator.translate(baslik)
    except Exception:
        baslik_tr = baslik

    try:
        ozet_tr = translator.translate(ozet[:300]) if ozet else ""
    except Exception:
        ozet_tr = ozet[:300] if ozet else ""

    metin = (
        f"⚡ <b>KENDİNE22TRADER KRİPTO HABER RADARI</b>\n\n"
        f"📰 <b>{baslik_tr}</b>\n\n"
        f"📝 {ozet_tr}...\n\n"
        f"🏛 <b>Kaynak:</b> {kaynak}\n"
        f"🔗 <a href='{link}'>Haberi Oku ↗</a>"
    )
    
    data = {
        "chat_id": CHAT_ID,
        "message_thread_id": TOPIC_ID,
        "text": metin,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, data=data, timeout=12)
    except Exception as e:
        print(f"Telegram Haber Gönderme Hatası: {e}")

def main():
    threading.Thread(target=start_http_server, daemon=True).start()
    print("🚀 KENDİNE22TRADER 7/24 Haber & Piyasa Botu Başlatıldı...")
    
    rss_kaynaklari = [
        ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("CoinTelegraph", "https://cointelegraph.com/rss"),
        ("Decrypt", "https://decrypt.co/feed")
    ]
    
    while True:
        try:
            for kaynak_adi, url in rss_kaynaklari:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    haber_id = entry.get("link", entry.get("title", ""))
                    if haber_id not in hafiza:
                        baslik = entry.get("title", "Kripto Gelişmesi")
                        ozet = entry.get("summary", entry.get("description", ""))
                        link = entry.get("link", "")
                        
                        telegram_haber_gonder(baslik, ozet, link, kaynak_adi)
                        hafiza.add(haber_id)
                        print(f"✅ Haber Gönderildi: {baslik[:40]}...")
                        time.sleep(2)
        except Exception as e:
            print(f"Haber Tarama Hatası: {e}")
            
        time.sleep(120)

if __name__ == "__main__":
    main()
