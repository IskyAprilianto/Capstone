import streamlit as st
import pandas as pd
import requests
import time
import paho.mqtt.client as mqtt
import ssl
from datetime import datetime

# ================= KONFIGURASI =================
BACKEND_URL = "https://240d6c5a-085e-4090-9e99-77c9e41ddc06-00-1p1eomiap7bc6.picard.replit.dev/api/get_ph?device_id=68FE7181895C"

MQTT_BROKER = "3f8165ca59d840d9bc964c540d1b792e.s1.eu.hivemq.cloud"
MQTT_PORT   = 8883
MQTT_USER   = "Hydroponic"
MQTT_PASS   = "Hydro1234"

# ================= PAGE =================
st.set_page_config(
    page_title="Hydroponic Monitoring",
    layout="wide"
)

st.title("🌱 Monitoring Hidroponik (Multi Device)")

# ================= MQTT =================
if "pump_status" not in st.session_state:
    st.session_state["pump_status"] = "UNKNOWN"

def on_connect(client, userdata, flags, rc, props):
    if rc == 0:
        client.subscribe("iot/status/pompa/+")

def on_message(client, userdata, msg):
    st.session_state["pump_status"] = msg.payload.decode()

@st.cache_resource
def init_mqtt():
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.username_pw_set(MQTT_USER, MQTT_PASS)
    c.tls_set(cert_reqs=ssl.CERT_NONE)
    c.tls_insecure_set(True)
    c.on_connect = on_connect
    c.on_message = on_message
    c.connect(MQTT_BROKER, MQTT_PORT, 60)
    c.loop_start()
    return c

mqtt_client = init_mqtt()

# ================= API HELPERS =================
def api_get_devices():
    r = requests.get(f"{BACKEND_URL}/api/get_devices", timeout=5)
    return r.json().get("devices", [])

def api_get_last(device_id):
    r = requests.get(
        f"{BACKEND_URL}/api/get_last_data",
        params={"device_id": device_id},
        timeout=5
    )
    return r.json()

def api_get_ph(device_id, limit=50):
    r = requests.get(
        f"{BACKEND_URL}/api/get_ph",
        params={"device_id": device_id, "limit": limit},
        timeout=5
    )
    return r.json().get("data", [])

# ================= SIDEBAR =================
st.sidebar.title("⚙️ Kontrol")

devices = api_get_devices()
if not devices:
    st.sidebar.warning("Belum ada device")
    st.stop()

device_id = st.sidebar.selectbox("Pilih Device", devices)

# ====== TOMBOL POMPA ======
if st.sidebar.button("🟢 ON Pompa"):
    mqtt_client.publish(f"iot/actuator/pompa/{device_id}", "ON")
    st.sidebar.success("Perintah ON dikirim")

if st.sidebar.button("🔴 OFF Pompa"):
    mqtt_client.publish(f"iot/actuator/pompa/{device_id}", "OFF")
    st.sidebar.success("Perintah OFF dikirim")

st.sidebar.divider()

# ====== STATUS POMPA ======
status = st.session_state["pump_status"]
if status == "ON":
    st.sidebar.success("Pompa: ON")
elif status == "MIXING":
    st.sidebar.warning("Pompa: MIXING")
elif status == "OFF":
    st.sidebar.info("Pompa: OFF")
else:
    st.sidebar.warning("Status: UNKNOWN")

# ================= MAIN =================

# ====== DATA TERAKHIR ======
last = api_get_last(device_id)

if "ph" in last:
    c1, c2, c3 = st.columns(3)
    c1.metric("pH Terbaru", f"{last['ph']:.2f}")
    c2.metric("Pompa", last.get("pompa", "UNKNOWN"))
    c3.metric("Waktu", last.get("timestamp", "-"))
else:
    st.warning("Data terakhir belum tersedia")

st.divider()

# ====== GRAFIK HISTORIS ======
st.subheader("📈 Grafik pH (50 Data Terakhir)")
hist = api_get_ph(device_id, limit=50)

if hist:
    df = pd.DataFrame(hist)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    st.line_chart(df.sort_values("timestamp"), x="timestamp", y="ph")
else:
    st.info("Belum ada data historis")

st.divider()

# ====== TABEL DATA ======
with st.expander("📄 Data Mentah"):
    if hist:
        st.dataframe(df.sort_values("timestamp", ascending=False))
    else:
        st.write("Data kosong")

# ================= AUTO REFRESH =================
time.sleep(5)
st.rerun()
