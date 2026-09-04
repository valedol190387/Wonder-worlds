#!/usr/bin/env python3
"""
Пересобирает картинки главной и демо-набор из готовых наборов packs/:
  img/hero.jpg, img/world-*.jpg, icons/og.jpg, seed/*.png
Запускать после tools/ingest.py.
"""
import os, json, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
random.seed(7)
FONT = '/System/Library/Fonts/Helvetica.ttc'
idx = json.load(open('packs/index.json'))
def pack(k): return [Image.open(p.lstrip('/').split('?')[0]).convert('RGBA') for p in idx['packs'][k]['items']]
mon, farm, cars, birds = pack('monsters'), pack('farm'), pack('cars'), pack('birds')

def place(canvas, sprite, cx, ground_y, h, shadow=True):
    s = h / sprite.height; w = int(sprite.width * s); hh = int(h)
    m = sprite.resize((w, hh), Image.LANCZOS)
    if shadow:
        sh = Image.new('RGBA', canvas.size, (0,0,0,0))
        ImageDraw.Draw(sh).ellipse([cx-w*0.36, ground_y-h*0.05, cx+w*0.36, ground_y+h*0.05], fill=(20,8,40,150))
        sh = sh.filter(ImageFilter.GaussianBlur(h*0.04)); canvas.alpha_composite(sh)
    canvas.paste(m, (int(cx-w/2), int(ground_y-hh)), m)

def scene(bgfile, size, sprites, hz=0.38, height=0.30):
    W, H = size
    bg = Image.open(bgfile).convert('RGB'); s = max(W/bg.width, H/bg.height)
    bg = bg.resize((int(bg.width*s), int(bg.height*s)), Image.LANCZOS)
    c = bg.crop(((bg.width-W)//2, (bg.height-H)//2, (bg.width-W)//2+W, (bg.height-H)//2+H)).convert('RGBA')
    for sp, ux, t in sorted(sprites, key=lambda x: x[2]):          # дальние рисуем первыми
        y = H*(hz + (1-hz)*(0.14 + 0.86*t**1.7)); h = H*height*(0.2 + 0.8*t**1.25)
        place(c, sp, W*ux, y, h)
    return c.convert('RGB')

os.makedirs('img', exist_ok=True); os.makedirs('seed', exist_ok=True)

scene('bg/night.jpg', (1600,900), [(mon[0],0.18,0.85),(mon[1],0.62,0.98),(mon[2],0.28,0.35),
      (mon[3],0.45,0.55),(mon[5],0.66,0.30),(mon[7],0.83,0.72)]).save('img/hero.jpg', quality=86)
scene('bg/night.jpg', (800,450), [(mon[2],0.32,0.5),(mon[7],0.68,0.85)]).save('img/world-night.jpg', quality=84)
scene('bg/farm.jpg',  (800,450), [(farm[0],0.30,0.55),(farm[2],0.66,0.85)]).save('img/world-farm.jpg', quality=84)
scene('bg/track.jpg', (800,450), [(cars[3],0.35,0.6),(cars[6],0.68,0.9)], height=0.24).save('img/world-track.jpg', quality=84)

sky = Image.open('bg/sky.jpg').convert('RGB').resize((800,450), Image.LANCZOS).convert('RGBA')
for sp, ux, uy, h in [(birds[2],0.25,0.30,150),(birds[4],0.62,0.22,120),(birds[0],0.78,0.55,170),(birds[5],0.42,0.62,120)]:
    s = h/sp.height; m = sp.resize((int(sp.width*s), int(h)), Image.LANCZOS)
    sky.paste(m, (int(800*ux-m.width/2), int(450*uy-h/2)), m)
sky.convert('RGB').save('img/world-sky.jpg', quality=84)

og = scene('bg/night.jpg', (1200,630), [(mon[0],0.80,0.9),(mon[3],0.63,0.55),(mon[5],0.90,0.5)]).convert('RGBA')
shade = Image.new('RGBA', (1200,630), (0,0,0,0)); ImageDraw.Draw(shade).rectangle([0,0,720,630], fill=(12,5,28,150))
og = Image.alpha_composite(og, shade.filter(ImageFilter.GaussianBlur(70)))
d = ImageDraw.Draw(og); big = ImageFont.truetype(FONT, 96, index=1); mid = ImageFont.truetype(FONT, 34, index=1)
d.text((70,160), 'Wonder', font=big, fill=(255,255,255)); d.text((70,262), 'Worlds', font=big, fill=(255,210,63))
d.text((72,400), 'Нарисуй монстрика, сфоткай —\nи он оживёт на большом экране', font=mid, fill=(232,222,255), spacing=10)
og.convert('RGB').save('icons/og.jpg', quality=88)

for f in os.listdir('seed'):
    if f.endswith('.png'): os.remove(os.path.join('seed', f))
for i, sp in enumerate(mon, 1):
    m = sp.copy(); m.thumbnail((700,700)); m.save(f'seed/m{i}.png')
print('hero, карточки, og, seed — пересобраны')
