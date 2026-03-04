from PIL import Image, ImageDraw, ImageFont

img = Image.new('RGB', (600, 400), color='white')
d = ImageDraw.Draw(img)

# Outline
d.rectangle((20, 20, 580, 380), outline='black', width=5)

# Rooms
d.rectangle((20, 20, 300, 200), outline='black', width=3)
d.text((100, 100), "Radiology - Ground Floor", fill='black')

d.rectangle((300, 20, 580, 200), outline='black', width=3)
d.text((400, 100), "Emergency Room - Ground Floor", fill='black')

img.save('dummy_floorplan.jpg')
print("Created dummy_floorplan.jpg")
