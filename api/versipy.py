import os, re, math, hashlib, difflib
import pandas as pd
from flask import Flask, request, jsonify, send_file

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__)
_hosp, _kb = None, None


def hospitals():
    global _hosp
    if _hosp is None:
        df = pd.read_csv(os.path.join(BASE, "data", "HospInfo.csv"), encoding="latin1")
        rows = []
        for _, r in df.iterrows():
            m = re.search(r"\(([-+]?\d+\.\d+),\s*([-+]?\d+\.\d+)\)", str(r["Location"]))
            if not m:
                continue
            nama = str(r["Hospital Name"])
            rows.append({
                "nama": nama,
                "tipe": str(r["Hospital Type"]),
                "lat": float(m.group(1)),
                "lon": float(m.group(2)),
                # Data bed SIMULASI (0-29), stabil per rumah sakit. Dataset tidak punya data bed.
                "bed_kosong": int(hashlib.md5(nama.encode()).hexdigest(), 16) % 30,
                "ada_ugd": str(r["Emergency Services"]).strip().lower() == "yes",
            })
        _hosp = rows
    return _hosp


def knowledge():
    global _kb
    if _kb is None:
        try:
            d = pd.read_csv(os.path.join(BASE, "data", "Penyakit.csv"))
            d["keyword"] = d["keyword"].str.lower()
            _kb = (d[d["level"] == 1]["keyword"].tolist(), d[d["level"] == 2]["keyword"].tolist())
        except Exception:
            _kb = (["jantung", "darah", "kritis"], ["demam", "patah"])
    return _kb


def jarak_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def cocok(kata, daftar):
    # Gestalt pattern matching (difflib); cutoff diperketat supaya kata acak tidak lolos
    return kata in daftar or bool(difflib.get_close_matches(kata, daftar, n=1, cutoff=0.8))


def urgensi(keluhan):
    lv1, lv2 = knowledge()
    kata = re.findall(r"\w+", keluhan.lower())
    if any(cocok(k, lv1) for k in kata):
        return 1, "Darurat: butuh penanganan segera"
    if any(cocok(k, lv2) for k in kata):
        return 2, "Sedang: butuh dokter"
    return 3, "Ringan: rawat jalan"


@app.route("/api/search", methods=["POST"])
def search():
    d = request.get_json(force=True)
    try:
        lat, lon, keluhan = float(d["lat"]), float(d["lon"]), str(d.get("keluhan", "")).strip()
    except (KeyError, ValueError):
        return jsonify(error="Lokasi tidak valid."), 400
    if not keluhan:
        return jsonify(error="Isi keluhan terlebih dahulu."), 400

    level, label = urgensi(keluhan)
    hasil = []
    for h in hospitals():
        if level == 1 and not h["ada_ugd"]:
            continue
        if h["bed_kosong"] <= 0:
            continue
        j = jarak_km(lat, lon, h["lat"], h["lon"])
        if j < 100:
            hasil.append({**h, "jarak": round(j, 2)})

    if level <= 2:  # darurat/sedang: terdekat dulu
        hasil.sort(key=lambda x: x["jarak"])
    else:           # ringan: bed terbanyak dulu, jarak sebagai pembanding
        hasil.sort(key=lambda x: (-x["bed_kosong"], x["jarak"]))
    return jsonify(level=level, label=label, total=len(hasil), hasil=hasil[:3])


@app.route("/")
def home():
    return send_file(os.path.join(BASE, "public", "index.html"))
