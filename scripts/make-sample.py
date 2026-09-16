"""Create a deterministic PNG fixture for manual upload verification, without AI calls."""

from pathlib import Path

from PIL import Image, ImageDraw

target = Path(__file__).resolve().parents[1] / ".data" / "sample-panel.png"
target.parent.mkdir(parents=True, exist_ok=True)
image = Image.new("RGB", (600, 800))
draw = ImageDraw.Draw(image)
for y in range(800):
    draw.line(
        (0, y, 600, y),
        fill=(int(23 + y * 0.07), int(28 + y * 0.045), int(66 + y * 0.075)),
    )
draw.ellipse((360, 90, 470, 200), fill="#ffebc2")
for x, height in [(0, 260), (90, 190), (180, 310), (290, 240), (390, 290), (510, 230)]:
    draw.rectangle((x, 800 - height, x + 80, 800), fill="#25283d")
    for wy in range(800 - height + 20, 760, 40):
        draw.rectangle((x + 17, wy, x + 31, wy + 20), fill="#e7ba9f")
        draw.rectangle((x + 49, wy, x + 63, wy + 20), fill="#ba98ad")
draw.text((30, 32), "LINKTOON / SAMPLE PANEL", fill="white", font_size=22)
draw.text((30, 65), "A scene before the story begins.", fill="#c7b9e2", font_size=16)
image.save(target)
print(target)
