import qrcode
import os

BASE_URL = "http://192.168.1.3:5000/menu/menu"

restaurant_id = 1
total_tables = 10

os.makedirs("qr_tables", exist_ok=True)

for table in range(1, total_tables+1):

    url = f"{BASE_URL}?table={table}&restaurant_id={restaurant_id}"

    img = qrcode.make(url)

    img.save(f"qr_tables/table_{table}.png")

print("QR codes generated ✅")