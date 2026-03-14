import qrcode

url="https://web-production-202a.up.railway.app"

img=qrcode.make(url)

img.save("menu_qr.png")

print("QR created")