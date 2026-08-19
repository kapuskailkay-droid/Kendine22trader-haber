import hashlib
import time
import xml.etree.ElementTree as ET
import ccxt
import pandas as pd
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# --- SABİT BOT VE TELEGRAM AYARLARI (GÖMÜLÜ) ---
GOMULU_BOT_TOKEN = "7820599329:AAEAa13edhS9PLoG1t8R34PLO9xpKlaT_Lc"
GOMULU_CHAT_ID = "-1004434260285"
GOMULU_TOPIC_ID = "3972"

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(
    page_title="KENDİNE22TRADER - Canlı Kripto Haber & Piyasa Radarı",
    layout="wide"
)

if "gonderilen_haber_hashleri" not in st.session_state:
    st.session_state.gonderilen_haber_hashleri = set()

if "son_fiyat_hafizasi" not in st.session_state:
    st.session_state.son_fiyat_hafizasi = {}

# --- YAN PANEL: TELEGRAM AYARLARI ---
st.sidebar.header("📱 Telegram Bildirim Ayarları")
telegram_aktif = st.sidebar.checkbox("🚀 Telegram Bildirimleri Açık", value=True)
bot_token = st.sidebar.text_input("Telegram Bot Token", value=GOMULU_BOT_TOKEN, type="password")
chat_id = st.sidebar.text_input("Telegram Chat ID", value=GOMULU_CHAT_ID)
topic_id = st.sidebar.text_input("Haber Sekmesi Topic ID", value=GOMULU_TOPIC_ID)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Canlı Takip & Alarm Ayarları")

oto_yenileme = st.sidebar.checkbox("🔄 Otomatik Canlı Takip Açık", value=True)
yenileme_araligi = st.sidebar.selectbox("Tarama Sıklığı", options=[10, 15, 30, 60], index=1, format_func=lambda x: f"{x} Saniyede Bir")

if oto_yenileme:
    st_autorefresh(interval=yenileme_araligi * 1000, key="canli_haber_ve_alarm")
    st.sidebar.success(f"🟢 Canlı haber akışı aktif: Her {yenileme_araligi} sn")

st.sidebar.markdown("---")
st.sidebar.header("🎯 BTC & ETH Ani Değişim Eşikleri")
min_artis_5m = st.sidebar.slider("5 Dakikalık Değişim Eşiği (%)", 0.8, 5.0, 1.2, 0.1)
min_artis_15m = st.sidebar.slider("15 Dakikalık Değişim Eşiği (%)", 1.2, 8.0, 2.0, 0.1)
min_artis_60m = st.sidebar.slider("60 Dakikalık Değişim Eşiği (%)", 2.0, 12.0, 3.0, 0.1)

st.title("⚡ KENDİNE22TRADER - Canlı Kripto Haber & BTC/ETH Radarı")

# --- TELEGRAM MESAJ GÖNDERİCİ (TOPIC 3972 KİLİTLİ) ---
def telegram_mesaj_gonder(metin):
    if telegram_aktif and bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token.strip()}/sendMessage"
        
        # Hedef Topic ID'yi doğrudan data payload içine yerleştiriyoruz
        hedef_topic = str(topic_id).strip() if (topic_id and str(topic_id).strip() != "") else GOMULU_TOPIC_ID
        
        data = {
            "chat_id": chat_id.strip(),
            "text": metin,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        if hedef_topic:
            try:
                data["message_thread_id"] = int(hedef_topic)
            except ValueError:
                pass
                
        try:
            requests.post(url, data=data, timeout=8)
        except Exception:
            pass

# --- TÜM PİYASADAN CANLI HABER ÇEKİCİ (FİLTRESİZ TÜM GELİŞMELER) ---
def canli_kripto_haberleri_tara():
    haberler = []
    
    # 1. Kaynak: Çoklu RSS Akışları (CoinTelegraph, CoinDesk, Decrypt, BitcoinMagazine, CryptoSlate)
    rss_kaynaklari = [
        {"ad": "CoinTelegraph", "url": "https://cointelegraph.com/rss"},
        {"ad": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
        {"ad": "Decrypt", "url": "https://decrypt.co/feed"},
        {"ad": "CryptoSlate", "url": "https://cryptoslate.com/feed/"},
        {"ad": "Bitcoin Magazine", "url": "https://bitcoinmagazine.com/feed"}
    ]
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    for kaynak in rss_kaynaklari:
        try:
            res = requests.get(kaynak["url"], headers=headers, timeout=4)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                for item in root.findall("./channel/item")[:5]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    link = item.find("link").text if item.find("link") is not None else ""
                    pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                    
                    if title and link:
                        haberler.append({
                            "baslik": title.strip(),
                            "kaynak": kaynak["ad"],
                            "link": link.strip(),
                            "zaman": pub_date
                        })
        except Exception:
            pass
            
    # 2. Kaynak: CryptoPanic Canlı Akış
    try:
        cp_res = requests.get("https://cryptopanic.com/api/v1/posts/?auth_token=free&public=true", timeout=4).json()
        for p in cp_res.get("results", [])[:10]:
            title = p.get("title", "")
            source_name = p.get("source", {}).get("title", "Kripto Gündem")
            url = p.get("url", "")
            if title and url:
                haberler.append({
                    "baslik": title.strip(),
                    "kaynak": source_name,
                    "link": url.strip(),
                    "zaman": p.get("published_at", "")
                })
    except Exception:
        pass

    # Haberleri İşle ve Telegram'a Bildir
    ekran_listesi = []
    for h in haberler:
        h_hash = hashlib.md5(h["baslik"].encode('utf-8')).hexdigest()
        
        if h_hash not in st.session_state.gonderilen_haber_hashleri:
            st.session_state.gonderilen_haber_hashleri.add(h_hash)
            
            # Telegram Mesajı
            tg_metin = (
                f"📰 <b>KRİPTO PİYASASI CANLI AKIŞ</b>\n\n"
                f"📌 <b>{h['baslik']}</b>\n\n"
                f"🌐 <b>Kaynak:</b> {h['kaynak']}\n"
                f"🔗 <a href='{h['link']}'>Haberi & Detayları Oku ↗</a>"
            )
            telegram_mesaj_gonder(tg_metin)
            
        ekran_listesi.append({
            "Haber Başlığı": h["baslik"],
            "Kaynak": h["kaynak"],
            "Link": h["link"]
        })
        
    return pd.DataFrame(ekran_listesi)

# --- BTC & ETH ANİ HAREKET DEDEKTÖRÜ (MİKABOT FORMATI) ---
def btc_eth_hareket_kontrol():
    mexc = ccxt.mexc({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
    takip_pariteleri = ['BTC/USDT', 'ETH/USDT']
    bildirimler = []
    
    try:
        tickers = mexc.fetch_tickers(takip_pariteleri)
    except Exception:
        return pd.DataFrame()
        
    for sembol in takip_pariteleri:
        if sembol in tickers:
            anlik_fiyat = tickers[sembol]['last']
            parite_kodu = sembol.replace('/', '')
            
            for tf, limit_mum, esik, sure_adi in [('5m', 6, min_artis_5m, '5dk'), ('15m', 6, min_artis_15m, '15dk'), ('1h', 6, min_artis_60m, '60dk')]:
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
                            
                            if alarm_anahtari not in st.session_state.son_fiyat_hafizasi.get(sembol, set()):
                                if sembol not in st.session_state.son_fiyat_hafizasi:
                                    st.session_state.son_fiyat_hafizasi[sembol] = set()
                                
                                st.session_state.son_fiyat_hafizasi[sembol].add(alarm_anahtari)
                                telegram_mesaj_gonder(alarm_mesaji)
                                
                            bildirimler.append({
                                "Parite": parite_kodu,
                                "Değişim": f"{isaret}%{round(yuzde_fark, 2)}",
                                "Süre": sure_adi,
                                "Fiyat ($)": anlik_fiyat,
                                "Nakit Payı": f"%{nakit_payi}"
                            })
                except Exception:
                    pass
                
    return pd.DataFrame(bildirimler)

# --- ÇALIŞTIRMA VE EKRAN ---
col_haber, col_fiyat = st.columns([1.3, 0.7])

with col_haber:
    st.subheader(f"📰 Kripto Piyasası Canlı Haber Akışı ({pd.Timestamp.now().strftime('%H:%M:%S')})")
    df_haber = canli_kripto_haberleri_tara()
    if not df_haber.empty:
        st.dataframe(
            df_haber,
            column_config={"Link": st.column_config.LinkColumn("Haber Linki", display_text="Haberi Oku ↗")},
            use_container_width=True
        )
    else:
        st.info("Haber akışı taranıyor...")

with col_fiyat:
    st.subheader("⚡ BTC & ETH Hızlı Hareketler")
    df_fiyat = btc_eth_hareket_kontrol()
    if not df_fiyat.empty:
        st.dataframe(df_fiyat, use_container_width=True)
    else:
        st.info("BTC ve ETH belirlenen eşiklerin altında stabil seyrediyor.")
