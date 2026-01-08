import os
import json
import base64
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = "rtv_secret_hospital_key"

# ================= FIREBASE SETUP =================
# ================= FIREBASE SETUP =================

cred = None

firebase_base64 = os.getenv("FIREBASE_KEY_BASE64")
firebase_key_path = os.getenv("FIREBASE_KEY_PATH")

if firebase_base64:
    # Railway (Base64 env variable)
    key_json = base64.b64decode(firebase_base64).decode("utf-8")
    cred = credentials.Certificate(json.loads(key_json))

elif firebase_key_path:
    # Render / local with env path
    cred = credentials.Certificate(firebase_key_path)

elif os.path.exists("key.json"):
    # Local fallback
    cred = credentials.Certificate("key.json")

else:
    raise RuntimeError("Firebase credentials not found")

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()



# ================= AUTO-INITIALIZE INVENTORY =================
def init_inventory():
    """Populates 30 items into Firestore if the collection is empty."""
    inventory_ref = db.collection('Inventory')
    docs = list(inventory_ref.limit(1).stream())
    
    if not docs:
        items = {
            "Paracetamol": 500, "Insulin": 45, "Amoxicillin": 120, "Oxygen Cylinder": 15,
            "IV Fluids": 200, "Ventilators": 8, "Syringes": 1000, "Gloves": 1500,
            "Masks": 2000, "Bandages": 300, "BP Monitors": 20, "Thermometers": 50,
            "Defibrillators": 5, "Wheelchairs": 15, "Stethoscopes": 40, "X-ray Films": 100,
            "Saline Bags": 250, "Surgical Gowns": 100, "Hand Sanitizer": 80, "Adhesive Tape": 60,
            "Catheters": 40, "Nebulizers": 12, "Dialysis Kits": 5, "Pulse Oximeters": 30,
            "ECG Paper": 50, "Disinfectant": 40, "Cotton Rolls": 100, "Antibiotics": 200,
            "Aspirin": 400, "Vitamins": 300
        }
        for name, qty in items.items():
            inventory_ref.document(name).set({"quantity": qty})

# Run this once on startup
init_inventory()

# ================= CONSTANTS =================
TOTAL_BEDS = 50

@app.route('/')
def home():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    today = datetime.today().date()
    
    # Fetch Data from Firestore
    patients = [doc.to_dict() for doc in db.collection('Patients').stream()]
    doctors = [doc.to_dict() for doc in db.collection('Doctors').stream()]
    inventory_docs = db.collection('Inventory').stream()
    inventory = {doc.id: doc.to_dict().get('quantity', 0) for doc in inventory_docs}

    # ---------- BED CALCULATION ----------
    occupied_beds = 0
    discharge_dates = []
    for p in patients:
        try:
            d_str = p.get('discharge_date')
            if d_str:
                d_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                if d_date >= today:
                    occupied_beds += 1
                    discharge_dates.append(d_date)
        except Exception: continue

    available_beds = TOTAL_BEDS - occupied_beds
    suggested_date = min(discharge_dates).strftime("%Y-%m-%d") if available_beds <= 0 and discharge_dates else "Immediate"

    # ---------- ROUTINE & SLOTS ----------
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    routine = {d: [] for d in days}
    total_slots = 0
    for d in doctors:
        total_slots += int(d.get('slots', 0))
        for day in d.get("days", []):
            routine[day].append(d)

    low_stock_count = sum(1 for qty in inventory.values() if qty < 20)

    return render_template(
        "index.html",
        patients=patients, doctors=doctors, routine=routine,
        inventory=inventory, low_stock_count=low_stock_count,
        available_beds=available_beds, occupied_beds=occupied_beds,
        total_beds=TOTAL_BEDS, total_appointments=total_slots,
        suggested_date=suggested_date
    )

@app.route('/add_patient', methods=['POST'])
def add_patient():
    admission_str = request.form['admission_date']
    admission = datetime.strptime(admission_str, "%Y-%m-%d")
    discharge = admission + timedelta(days=5)
    
    db.collection("Patients").add({
        "name": request.form['name'],
        "age": request.form['age'],
        "gender": request.form['gender'],
        "blood_group": request.form['blood_group'],
        "disease": request.form['disease'],
        "doctor": request.form['doctor'],
        "notes": request.form['notes'],
        "admission_date": admission_str,
        "discharge_date": discharge.strftime("%Y-%m-%d")
    })
    return redirect(url_for('home'))

@app.route('/add_doctor', methods=['POST'])
def add_doctor():
    db.collection("Doctors").add({
        "name": request.form['doc_name'],
        "qual": request.form['qual'],
        "specialty": request.form['specialty'],
        "slots": request.form['slots'],
        "shift_start": request.form['shift_start'],
        "shift_end": request.form['shift_end'],
        "days": request.form.getlist("days")
    })
    return redirect(url_for('home'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST' and request.form['password'] == "admin123":
        session['logged_in'] = True
        return redirect(url_for('home'))
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)