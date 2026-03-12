import qrcode
import os

base_url = "https://web-production-202a.up.railway.app"
os.makedirs("qr_tables", exist_ok=True)

for table in range(1, 21):

    url = f"{base_url}/restaurant/1?table={table}"

    img = qrcode.make(url)

    filename = f"qr_tables/table_{table}.png"

    img.save(filename)

    print(f"Created QR for Table {table}")
