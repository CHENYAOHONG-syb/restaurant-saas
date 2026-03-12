import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os

base_url = "https://web-production-202a.up.railway.app"

os.makedirs("qr_tables", exist_ok=True)

# 生成二维码图片
for table in range(1, 21):

    url = f"{base_url}?table={table}"

    img = qrcode.make(url)

    filename = f"qr_tables/table_{table}.png"

    img.save(filename)


# 创建PDF
pdf = canvas.Canvas("restaurant_qr_tables.pdf", pagesize=A4)

x = 50
y = 750
count = 0

for table in range(1, 21):

    file = f"qr_tables/table_{table}.png"

    pdf.drawImage(file, x, y, width=100, height=100)

    pdf.drawString(x, y-15, f"Table {table}")

    x += 130
    count += 1

    if count % 4 == 0:
        x = 50
        y -= 150

pdf.save()

print("QR Code PDF created: restaurant_qr_tables.pdf")
