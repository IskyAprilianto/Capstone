import threading
import json
import datetime
import ssl
import pymongo
import paho.mqtt.client as mqtt
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import timedelta, timezone

# ================= 1. KONFIGURASI UMUM =================
# MongoDB
MONGO_URI = "mongodb+srv://Hydroponic:Hydro1234@hydroponic.exth76i.mongodb.net/?appName=Hydroponic"

# HiveMQ Cloud (Pastikan sesuai dengan ESP32)
MQTT_BROKER = "3f8165ca59d840d9bc964c540d1b792e.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "Hydroponic"
MQTT_PASS = "Hydro1234"
MQTT_TOPIC = "iot/sensor/hydroponic"

# Timezone WIB (UTC+7)
WIB = datetime.timezone(datetime.timedelta(hours=7))

# ================= 2. SETUP DATABASE =================
try:
    client_db = pymongo.MongoClient(MONGO_URI)
    db = client_db["db_iot_proyek"]
    collection = db["sensor_data"]
    # Variable status koneksi db untuk log
    db_status = "✅ Terhubung"
except Exception as e:
    db_status = f"❌ Gagal: {e}"

# ================= 3. BAGIAN FLASK API (Untuk Azis & AI) =================
app = Flask(__name__)
CORS(app)  # Izinkan akses dari frontend manapun

# Helper convert datetime object ke string
def format_data(doc):
    if "timestamp" in doc:
        # Ubah ke WIB jika masih UTC
        ts = doc["timestamp"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_wib = ts.astimezone(WIB)
        doc["timestamp"] = ts_wib.strftime("%Y-%m-%d %H:%M:%S")

    if "_id" in doc: del doc["_id"]  # Hapus ID Mongo
    return doc


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "Backend Server Running",
        "service": "MQTT + API",
        "message": "Halo! Backend AKTIF siap digunakan."
    })


# Endpoint buat Frontend Azis & AI
@app.route('/api/get_ph', methods=['GET'])
def get_ph():
    try:
        limit = int(request.args.get('limit', 120))
        # Projection: Sembunyikan 'pompa' kalau Azis cuma minta pH
        projection = {"timestamp": 1, "ph": 1, "_id": 0}

        cursor = collection.find({}, projection).sort("timestamp",
                                                      -1).limit(limit)
        data = [format_data(doc) for doc in cursor]

        return jsonify({
            "status": "success",
            "total": len(data),
            "data": data
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500


# ================= 4. BAGIAN MQTT LISTENER (Untuk ESP32) =================
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"🚀 [MQTT] Listener Terhubung ke HiveMQ!")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"⚠️ [MQTT] Gagal Konek: {reason_code}")


def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        print(f"📥 [MQTT Masuk] {payload}")
        data = json.loads(payload)

        if "ph" in data:
            ph = float(data["ph"])
            status_pompa = data.get("pompa", "UNKNOWN")
            waktu = datetime.datetime.now(WIB)

            # Simpan ke MongoDB
            collection.insert_one({
                "timestamp": waktu,
                "ph": ph,
                "pompa": status_pompa
            })
            print(f"   💾 Saved DB: pH {ph} | Pompa {status_pompa}")

    except Exception as e:
        print("❌ Error processing message:", e)


# Fungsi Wrapper untuk menjalakan MQTT di Thread terpisah
def run_mqtt_client():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PASS)

    # SSL Setting (Wajib buat HiveMQ)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever(
        )  # Ini akan memblokir thread ini selamanya (bagus buat background)
    except Exception as e:
        print(f"❌ Gagal start MQTT: {e}")


# ================= 5. MAIN EXECUTION (GABUNGAN) =================
if __name__ == '__main__':
    # A. Jalankan MQTT di Background Thread
    mqtt_thread = threading.Thread(target=run_mqtt_client)
    mqtt_thread.daemon = True  # Biar kalau program di-close, thread ikut mati
    mqtt_thread.start()

    # B. PRINT STATUS AKTIF YANG KEREN (REQUEST KAMU)
    print("\n" + "=" * 50)
    print("🚀  STATUS: BACKEND SUDAH AKTIF !!!")
    print("=" * 50)
    print(f"📂  Database : {db_status}")
    print("📡  MQTT     : Running (Background)")
    print("🌍  API Port : 5000")
    print("-" * 50)
    print("👉  Backend siap melayani Request Frontend & ESP32")
    print("=" * 50 + "\n")

    # C. Jalankan Flask API di Main Thread
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
