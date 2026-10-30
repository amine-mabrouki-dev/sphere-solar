from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

out_dir = Path(__file__).resolve().parent.parent / 'reports' / 'diagrams'
out_dir.mkdir(parents=True, exist_ok=True)

font = ImageFont.load_default()

def draw_box(draw, xy, text, font, fill='#FFFFFF', outline='#000000'):
    draw.rectangle(xy, fill=fill, outline=outline, width=2)
    lines = text.split('\n')
    sizes = [font.getbbox(line) for line in lines]
    max_w = max(b[2] - b[0] for b in sizes)
    total_h = sum(b[3] - b[1] for b in sizes)
    x0, y0, x1, y1 = xy
    current_y = y0 + (y1 - y0 - total_h) / 2
    for line, bbox in zip(lines, sizes):
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        text_x = x0 + (x1 - x0 - w) / 2
        draw.text((text_x, current_y), line, fill='black', font=font)
        current_y += h

# Architecture diagram
arch = Image.new('RGB', (900, 420), 'white')
draw = ImageDraw.Draw(arch)
boxes = [
    ((60, 150, 260, 210), 'Inverter\nSolis'),
    ((340, 50, 560, 110), 'ESP32\nFirmware'),
    ((340, 170, 560, 230), 'MQTT Broker\nMosquitto'),
    ((340, 290, 560, 350), 'Backend\nFastAPI'),
    ((740, 150, 860, 210), 'Mobile App\nExpo'),
]
for xy, label in boxes:
    draw_box(draw, xy, label, font)

connections = [
    ((260, 180), (340, 80)),
    ((560, 80), (740, 180)),
    ((560, 210), (740, 210)),
    ((500, 320), (740, 320)),
]
for start, end in connections:
    draw.line([start, end], fill='black', width=3)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if dx == 0 and dy == 0:
        continue
    dist = (dx*dx + dy*dy) ** 0.5
    ux = dx / dist
    uy = dy / dist
    perp = (-uy, ux)
    arrow_tip = (end[0] - ux * 12, end[1] - uy * 12)
    p1 = (arrow_tip[0] + perp[0] * 6, arrow_tip[1] + perp[1] * 6)
    p2 = (arrow_tip[0] - perp[0] * 6, arrow_tip[1] - perp[1] * 6)
    draw.polygon([end, p1, p2], fill='black')

arch.save(out_dir / 'architecture.png')
print('Created architecture.png')

# ERD diagram
erd = Image.new('RGB', (900, 620), 'white')
draw = ImageDraw.Draw(erd)
entities = [
    ((60, 60, 280, 160), 'users\nid PK\nemail\npassword_hash\nrole'),
    ((60, 220, 280, 340), 'installations\nid PK\nname\nlocation\nowner_user_id FK'),
    ((60, 400, 280, 540), 'inverters\nid PK\ninstallation_id FK\nserial\nmodel'),
    ((500, 40, 820, 180), 'readings\nid PK\ninverter_id FK\nts\npv_v,pv_i,pv_p\nac_v,ac_i,freq\ne_day,e_total\nbatt_v,batt_i,batt_soc\ntemp,alarm'),
    ((500, 220, 820, 360), 'latest_metrics\ninverter_id PK\nts\npv_v,pv_i,pv_p\nac_v,ac_i,freq\ne_day,e_total\nbatt_v,batt_i,batt_soc\ntemp,alarm\nupdated_at'),
    ((500, 420, 820, 540), 'alerts\nid PK\ninverter_id FK\ncode\nmessage\nraised_at\ncleared_at'),
]
for xy, label in entities:
    draw_box(draw, xy, label, font)

relations = [
    ((170, 160), (170, 220)),
    ((170, 340), (170, 400)),
    ((280, 470), (500, 470)),
    ((280, 110), (500, 110)),
    ((280, 290), (500, 290)),
]
for start, end in relations:
    draw.line([start, end], fill='black', width=3)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if dx == 0 and dy == 0:
        continue
    dist = (dx*dx + dy*dy) ** 0.5
    ux = dx / dist
    uy = dy / dist
    arrow_tip = (end[0] - ux * 12, end[1] - uy * 12)
    perp = (-uy, ux)
    p1 = (arrow_tip[0] + perp[0] * 6, arrow_tip[1] + perp[1] * 6)
    p2 = (arrow_tip[0] - perp[0] * 6, arrow_tip[1] - perp[1] * 6)
    draw.polygon([end, p1, p2], fill='black')

erd.save(out_dir / 'erd.png')
print('Created erd.png')
