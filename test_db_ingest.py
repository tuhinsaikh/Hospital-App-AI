import requests

url = 'http://localhost:8000/update_floor_plan'

floor_plan = """
Ground Floor: Main Reception, 24/7 Emergency Room (ER) / Casualty, Pharmacy, and the primary Diagnostic Center (X-ray, Ultrasound, and CT Scan).
First Floor: Contains the Blood Bank, Outpatient Department (OPD) clinics, and the Physiotherapy center.
Second Floor: Contains the General Wards (separated into Male and Female sections), Semi-Private Rooms numbered 201-220, the Maternity and Labor ward, and the Dialysis Unit.
Third Floor: Contains fully Air-Conditioned Private Rooms numbered 301-330, VIP Deluxe Suites, and the Intensive Care Unit (ICU).
Fourth Floor: Operation Theaters (OT) and the Neonatal Intensive Care Unit (NICU).
"""

r = requests.post(url, data={"document": floor_plan})
print("Upload:", r.json())
