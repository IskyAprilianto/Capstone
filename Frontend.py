import streamlit as st
import pymongo
import pandas as pd
import time
import paho.mqtt.client as mqtt
import ssl
from datetime import datetime, timedelta, timezone

# ================= HALAMAN =================
st.set_page_config(
    page_title="Hydroponic WIB",
    layout="wide"
)

# ================= KONFIGURASI =================
MONGO_URI = "mongodb+srv://Hydroponic:Hydro1234@hydroponic.exth76i.mongodb.net/?appName=Hydroponic"

# HIVEMQ
MQTT_BROKER = "86d65c85d9bb491caaff9aeda3828bf1.s1.eu.hivemq.cloud"
MQTT_PORT   = 8883
MQTT_USER   = "Hydroponic"
MQTT_PASS   = "Hydro1234"
MQTT_TOPIC_CMD    = "iot/actuator/pompa"
MQTT_TOPIC_STATUS = "iot/status/pompa"

# ================= KONEKSI MONGODB =================
@st.cache_resource
def init_db():
    return pymongo.MongoClient(MONGO_URI)

client_db = init_db()
db = client_db["db_iot_proyek"]
collection = db["sensor_data"]

# ================= KONEKSI MQTT =================
if "pump_status" not in st.session_state:
    st.session_state["pump_status"] = "UNKNOWN"

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

# ================= UTILS: WIB & CSV =================
def convert_to_wib(df):
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
    df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Jakarta")
    return df

# Fungsi khusus buat convert DataFrame jadi CSV string
@st.cache_data
def convert_df_to_csv(df):
    # Encode utf-8 biar aman
    return df.to_csv(index=False).encode('utf-8')

# ================= SIDEBAR =================
st.sidebar.title("🎛️ Kontrol")

# 1. TOMBOL POMPA
if st.sidebar.button("🚨 Hidupkan Pompa (Manual)"):
    mqtt_client.publish(MQTT_TOPIC_CMD, '{"pump":"ON"}')
    st.sidebar.success("Perintah dikirim ke HiveMQ!")

st.sidebar.divider()

# 2. STATUS POMPA
st.sidebar.subheader("⚙️ Status Pompa")
current_status = st.session_state["pump_status"]

if current_status == "ON":
    st.sidebar.success("🟢 Pompa: ON")
elif current_status == "MIXING":
    st.sidebar.warning("⏳ Status: MIXING (Jeda)")
elif current_status == "OFF":
    st.sidebar.info("⚪ Pompa: OFF")
else:
    st.sidebar.warning(f"⚠️ Status: {current_status}")

st.sidebar.divider()

# 3. DOWNLOAD DATA (FITUR BARU 🆕)
st.sidebar.subheader("📥 Download Data")

# Tombol untuk load semua data (hati-hati kalau data jutaan)
if st.sidebar.checkbox("Siapkan File CSV"):
    with st.spinner("Mengambil semua data dari Database..."):
        # Ambil SEMUA data (tanpa limit) atau limit besar misal 5000
        cursor_all = collection.find().sort("timestamp", -1).limit(5000)
        df_all = pd.DataFrame(list(cursor_all))
        
        if not df_all.empty:
            if "_id" in df_all.columns: del df_all["_id"]
            df_all = convert_to_wib(df_all)
            
            # Convert ke CSV
            csv_data = convert_df_to_csv(df_all)
            
            # Tampilkan Tombol Download
            st.sidebar.download_button(
                label="📄 Download CSV (Full)",
                data=csv_data,
                file_name=f'data_hidroponik_{datetime.now().strftime("%Y%m%d_%H%M")}.csv',
                mime='text/csv',
            )
        else:
            st.sidebar.warning("Data kosong.")

# ================= UI UTAMA =================
st.title("🇮🇩 Monitoring Hidroponik (WIB)")

# 1. DATA TERBARU
latest = list(collection.find().sort("timestamp", -1).limit(1))

if latest:
    data = latest[0]
    ph = data.get("ph", 0)
    
    ts = data["timestamp"]
    if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone(timedelta(hours=7)))

    status, color = get_status(ph) if 'get_status' in globals() else ("UNKNOWN", "info")
    
    # Fungsi Status pH (Saya taruh sini biar rapi)
    def get_ph_status_ui(val):
        if val < 5.5: return "ASAM", "error"
        elif val > 7.5: return "BASA", "error"
        else: return "NORMAL", "success"
    
    status_txt, status_col = get_ph_status_ui(ph)

    c1, c2, c3 = st.columns(3)
    c1.metric("pH Air", f"{ph:.2f}")
    getattr(c2, status_col)(f"Status: {status_txt}")
    c3.metric("Update", ts.strftime("%H:%M:%S WIB"))

    st.divider()

    # 2. GRAFIK & TABEL (Limit 50 biar ringan di layar)
    cursor = collection.find().sort("timestamp", -1).limit(50)
    df = pd.DataFrame(list(cursor))

    if not df.empty:
        if "_id" in df.columns: del df["_id"]
        df = convert_to_wib(df)
        st.line_chart(df.sort_values("timestamp"), x="timestamp", y="ph")
        with st.expander("Lihat Data Mentah (50 Terakhir)"):
             st.dataframe(df.sort_values("timestamp", ascending=False))

else:
    st.warning("Menunggu data dari ESP32...")

time.sleep(3)
st.rerun()