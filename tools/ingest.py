#!/usr/bin/env python3
"""
Принять сгенерированные картинки и разложить по наборам.

  _incoming/monsters/*.png   -> packs/monsters/N.png   (фон убран, обрезано)
  _incoming/farm/*.png       -> packs/farm/N.png
  _incoming/cars/*.png       -> packs/cars/N.png
  _incoming/birds/*.png      -> packs/birds/N.png
  _incoming/props/night/*.png-> packs/props/night/N.png   (то же для farm, track)
  _incoming/icon.png         -> icons/* всех размеров

Белый/светлый фон убирается заливкой от краёв (как в самом приложении) —
поэтому подходят и картинки без прозрачности.
Нужен Pillow: pip install pillow. Желателен pngquant (brew install pngquant) —
без него PNG останутся 32-битными и будут весить в четыре раза больше.
"""
import os, sys, json, glob, shutil, subprocess
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INC  = os.path.join(ROOT, '_incoming')

def remove_bg(im, tol=48):
    """заливка от краёв: всё, что цветом плавно тянется от границы, — фон"""
    im = im.convert('RGBA'); w, h = im.size; px = im.load()
    seen = bytearray(w*h); stack = []
    for x in range(w): stack += [(x,0),(x,h-1)]
    for y in range(h): stack += [(0,y),(w-1,y)]
    ref = None
    while stack:
        x, y = stack.pop(); i = y*w+x
        if seen[i]: continue
        r,g,b,a = px[x,y]
        if a < 20: seen[i] = 1; px[x,y] = (r,g,b,0); nb=[(x+1,y),(x-1,y),(x,y+1),(x,y-1)]
        else:
            if ref is None: ref = (r,g,b)
            # фон должен быть светлым и похожим на соседа
            if not (r+g+b > 600): continue
            seen[i] = 1; px[x,y] = (r,g,b,0); nb=[(x+1,y),(x-1,y),(x,y+1),(x,y-1)]
        for nx, ny in nb:
            if 0 <= nx < w and 0 <= ny < h and not seen[ny*w+nx]:
                nr,ng,nb_,na = px[nx,ny]
                if na < 20 or abs(nr-r)+abs(ng-g)+abs(nb_-b) < tol: stack.append((nx,ny))
    return im

def has_real_alpha(im):
    """Картинка уже с прозрачным фоном (gpt-image с background=transparent)?
    Судим по доле прозрачных пикселей: у персонажа на прозрачном фоне их
    почти половина кадра. Край проверять нельзя — модель иногда дорисовывает
    тонкую непрозрачную рамку, и по краю картинка выглядит «залитой»."""
    if im.mode != 'RGBA': return False
    h = im.getchannel('A').histogram()
    return sum(h[:20]) / (im.width * im.height) > 0.05

def strip_frame(im, tol=48):
    """Снять светлую рамку/поля у картинки, у которой фон УЖЕ прозрачный.
    Идём от краёв только по НЕПРОЗРАЧНЫМ светлым пикселям и останавливаемся
    на прозрачности — так белая шерсть овцы внутри остаётся нетронутой."""
    w, h = im.size; px = im.load()
    seen = bytearray(w*h); stack = []
    for x in range(w): stack += [(x,0),(x,h-1)]
    for y in range(h): stack += [(0,y),(w-1,y)]
    while stack:
        x, y = stack.pop(); i = y*w+x
        if seen[i]: continue
        seen[i] = 1
        # рамка — это узкая полоса у края; глубже 14 px не лезем, иначе
        # белый кролик, упёршийся лапами в край, уйдёт целиком
        if min(x, y, w-1-x, h-1-y) > 14: continue
        r,g,b,a = px[x,y]
        if a < 20 or r+g+b <= 600: continue          # прозрачное или цветное — стоп
        px[x,y] = (r,g,b,0)
        for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny*w+nx]:
                nr,ng,nb_,na = px[nx,ny]
                if na >= 20 and abs(nr-r)+abs(ng-g)+abs(nb_-b) < tol: stack.append((nx,ny))
    return im

def clean_edges(im, ring=6, min_alpha=48):
    """Тонкая полупрозрачная кромка по периметру исходника (модель любит
    дорисовать «поля») попадает в обрезку и видна квадратной рамкой.
    Гасим кольцо у края и все еле заметные пиксели."""
    w, h = im.size
    a = im.getchannel('A').point(lambda v: 0 if v < min_alpha else v)
    d = ImageDraw.Draw(a)
    d.rectangle([0, 0, w-1, ring-1], fill=0); d.rectangle([0, h-ring, w-1, h-1], fill=0)
    d.rectangle([0, 0, ring-1, h-1], fill=0); d.rectangle([w-ring, 0, w-1, h-1], fill=0)
    im.putalpha(a)
    return im

def tidy(path, pad=12):
    im = Image.open(path).convert('RGBA')
    im = strip_frame(im) if has_real_alpha(im) else remove_bg(im)
    im = clean_edges(im)
    b = im.getchannel('A').getbbox()
    if b: im = im.crop((max(0,b[0]-pad), max(0,b[1]-pad), min(im.width,b[2]+pad), min(im.height,b[3]+pad)))
    return im

def squeeze(path):
    """Ужать PNG палитрой. Картинки уезжают на телефоны через мобильный
    интернет, а 32-битная RGBA от нейросети весит по мегабайту на персонажа —
    в четыре раза больше, чем нужно. pngquant с порогом 80 не трогает то,
    что не может сжать без потерь качества; нет pngquant — просто пропускаем."""
    if not shutil.which('pngquant'): return
    subprocess.run(['pngquant', '--quality=80-98', '--speed', '1', '--strip',
                    '--force', '--skip-if-larger', '--ext', '.png', path],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def ingest_pack(src_dir, dst_dir):
    files = sorted(glob.glob(os.path.join(src_dir, '*.png')) + glob.glob(os.path.join(src_dir, '*.jpg')) + glob.glob(os.path.join(src_dir, '*.webp')))
    if not files: return []
    os.makedirs(dst_dir, exist_ok=True)
    for f in glob.glob(os.path.join(dst_dir, '*.png')): os.remove(f)
    out = []
    for n, f in enumerate(files, 1):
        im = tidy(f); im.thumbnail((900, 900))
        p = os.path.join(dst_dir, f'{n}.png'); im.save(p); squeeze(p)
        out.append('/' + os.path.relpath(p, ROOT))
    print(f'{os.path.relpath(dst_dir, ROOT)}: {len(out)} шт.')
    return out

def main():
    idx_path = os.path.join(ROOT, 'packs', 'index.json')
    idx = json.load(open(idx_path)) if os.path.exists(idx_path) else {'packs': {}, 'props': {}}
    titles = {'monsters':'Монстрики', 'farm':'Ферма', 'cars':'Машинки', 'birds':'Птички и летуны'}
    for key in titles:
        items = ingest_pack(os.path.join(INC, key), os.path.join(ROOT, 'packs', key))
        if items: idx['packs'][key] = {'title': titles[key], 'items': items}
    for world in ('night', 'farm', 'track'):
        items = ingest_pack(os.path.join(INC, 'props', world), os.path.join(ROOT, 'packs', 'props', world))
        if items: idx['props'][world] = items
    def _ver(path):
        import hashlib
        fp = path.lstrip('/').split('?')[0]; st = os.stat(os.path.join(ROOT, fp))
        return f"/{fp}?v={hashlib.md5(f'{st.st_size}-{int(st.st_mtime)}'.encode()).hexdigest()[:8]}"
    for k in idx['packs']: idx['packs'][k]['items'] = [_ver(x) for x in idx['packs'][k]['items']]
    for k in idx['props']: idx['props'][k] = [_ver(x) for x in idx['props'][k]]
    json.dump(idx, open(idx_path, 'w'), ensure_ascii=False, indent=1)

    icon = os.path.join(INC, 'icon.png')
    if os.path.exists(icon):
        im = Image.open(icon).convert('RGB').resize((1024,1024), Image.LANCZOS)
        d = os.path.join(ROOT, 'icons')
        im.save(f'{d}/icon-1024.png')
        for s in (512, 192, 180, 64, 32):
            name = {512:'icon-512.png', 192:'icon-192.png', 180:'apple-touch-icon.png', 64:'favicon-64.png', 32:'favicon-32.png'}[s]
            im.resize((s,s), Image.LANCZOS).save(f'{d}/{name}')
        # maskable: та же картинка с запасом по краям
        m = Image.new('RGB', (1024,1024), im.getpixel((10,10))); m.paste(im.resize((800,800), Image.LANCZOS), (112,112)); m.resize((512,512), Image.LANCZOS).save(f'{d}/maskable-512.png')
        im.resize((64,64), Image.LANCZOS).save(f'{d}/favicon.ico', sizes=[(16,16),(32,32),(48,48)])
        for f in glob.glob(f'{d}/*.png'): squeeze(f)
        print('иконки обновлены')
    print('готово — перезапусти сервер, чтобы демо-мир пересеялся, если менял seed/')

if __name__ == '__main__':
    main()
