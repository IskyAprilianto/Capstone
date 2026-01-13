import streamlit as st
import pymongo
import pandas as pd
import time
import paho.mqtt.client as mqtt
import ssl
from datetime import datetime, timedelta, timezone

# ================= HALAMAN =================
st.set_page_config(
    page_title="Hydroponic Monitoring",
    page_icon="🌿",
    layout="wide"
)

# ================= KONFIGURASI DATABASE =================
# Pastikan URI ini benar sesuai MongoDB Atlas Anda
MONGO_URI = "mongodb+srv://Hydroponic:Hydro1234@hydroponic.exth76i.mongodb.net/?appName=Hydroponic"

@st.cache_resource
def init_db():
    return pymongo.MongoClient(MONGO_URI)

try:
    client_db = init_db()
    db = client_db["db_iot_proyek"]
    collection = db["sensor_data"]
except Exception as e:
    st.error(f"Gagal konek Database: {e}")

# ================= KONFIGURASI MQTT (HIVEMQ CLOUD) =================
# Kita pakai HiveMQ agar bisa jalan di Streamlit Cloud
MQTT_BROKER = "86d65c85d9bb491caaff9aeda3828bf1.s1.eu.hivemq.cloud"
MQTT_PORT   = 8883
MQTT_USER   = "Hydroponic"
MQTT_PASS   = "Hydro1234"
MQTT_TOPIC_STATUS = "iot/status/pompa"

# Session State untuk Status Pompa (Biar UI tidak flicker)
if "pump_status" not in st.session_state:
    st.session_state["pump_status"] = "OFF"

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        client.subscribe(MQTT_TOPIC_STATUS)

def on_message(client, userdata, msg):
    try:
        st.session_state["pump_status"] = msg.payload.decode()
    except:
        pass

@st.cache_resource
def init_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    
    # Setting SSL Wajib buat HiveMQ Cloud
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
    except Exception as e:
        st.error(f"Gagal konek MQTT: {e}")
    return client

mqtt_client = init_mqtt()

# ================= UTILS: KONVERSI WIB =================
def convert_to_wib(df):
    # Pastikan format timestamp dikenali sebagai datetime
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    # Jika belum ada timezone (naive), anggap UTC dulu
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
    
    # Convert ke Asia/Jakarta
    df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Jakarta")
    return df

def get_status_ph(ph):
    if ph < 5.5:
        return "ASAM", "error" # Merah
    elif ph > 7.5:
        return "BASA", "error" # Merah
    else:
        return "NORMAL", "success" # Hijau

# ================= SIDEBAR (MONITORING ONLY) =================
st.sidebar.title("🌿 Dashboard")
st.sidebar.markdown("Monitoring Hidroponik Real-time")

st.sidebar.divider()

# Status Pompa (Hanya Menampilkan, Tidak Mengontrol)
st.sidebar.subheader("Status Pompa")
status_pompa = st.session_state["pump_status"]

if status_pompa == "ON":
    st.sidebar.success("🟢 MENYALA")
elif status_pompa == "MIXING":
    st.sidebar.warning("⏳ MIXING (JEDA)")
elif status_pompa == "WAIT_MIXING":
    st.sidebar.warning("⛔ MENUNGGU")
else:
    st.sidebar.info("⚪ MATI")

st.sidebar.divider()
st.sidebar.caption("Terhubung ke HiveMQ & MongoDB Atlas")

# ================= UI UTAMA =================
st.title("🇮🇩 Monitoring Kualitas Air (WIB)")

# 1. AMBIL DATA TERAKHIR DARI MONGODB
try:
    latest = list(collection.find().sort("timestamp", -1).limit(1))

    if latest:
        data = latest[0]
        ph = data.get("ph", 0)
        
        # Konversi Waktu Single Data
        ts = data["timestamp"]
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        ts = ts.astimezone(timezone(timedelta(hours=7))) # WIB

        status_text, color_code = get_status_ph(ph)

        # Tampilkan Metrics (Kartu Atas)
        col1, col2, col3 = st.columns(3)
        col1.metric("pH Air Saat Ini", f"{ph:.2f}")
        getattr(col2, color_code)(f"Kondisi: {status_text}")
        col3.metric("Terakhir Update", ts.strftime("%H:%M:%S WIB"))

        st.divider()

        # 2. AMBIL DATA HISTORI UNTUK GRAFIK (50 Data Terakhir)
        cursor = collection.find().sort("timestamp", -1).limit(50)
        df = pd.DataFrame(list(cursor))

        if not df.empty:
            # Hapus _id biar bersih
            if "_id" in df.columns: del df["_id"]
            
            # Convert waktu ke WIB
            df = convert_to_wib(df)
            
            # Urutkan berdasarkan waktu (biar grafik jalan dari kiri ke kanan)
            df = df.sort_values("timestamp")

            st.subheader("📈 Grafik pH Air (Real-time)")
            st.line_chart(df, x="timestamp", y="ph")

            with st.expander("Lihat Data Tabel"):
                st.dataframe(df.sort_values("timestamp", ascending=False)) # Tabel urut dari yang terbaru
        
    else:
        st.info("Belum ada data masuk dari alat ESP32...")

except Exception as e:
    st.error(f"Terjadi kesalahan saat mengambil data: {e}")

# Auto Refresh setiap 3 detik tanpa tombol
time.sleep(3)
st.rerun()
