#!/usr/bin/env python3
"""
Генерация наборов персонажей и реквизита через gpt-image (OpenAI).

    OPENAI_API_KEY=... [HTTPS_PROXY=...] python tools/gen.py [monsters farm cars birds props icon]

Пишет PNG с ПРОЗРАЧНЫМ фоном в _incoming/<набор>/, дальше — tools/ingest.py.
Без аргументов генерит всё. Уже существующие файлы пропускает — можно перезапускать.
Прокси берётся из переменных окружения (HTTPS_PROXY / ALL_PROXY), как у любого
http-клиента; OpenAI режет запросы из РФ, так что без прокси отсюда не выйдет.
"""
import os, sys, base64, json, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INC  = os.path.join(ROOT, '_incoming')
KEY  = os.environ.get('OPENAI_API_KEY')
MODEL = os.environ.get('IMAGE_MODEL', 'gpt-image-1')

STYLE = ("drawn like a happy child's felt-tip marker drawing: bold wobbly black outlines, "
         "bright saturated marker colours with visible marker strokes, big friendly eyes, "
         "cute and simple, full body, front or three-quarter view, single character, "
         "centered, isolated on a transparent background, no shadow, no ground, no text")

PACKS = {
  'monsters': [
    "a tall skinny green monster with two curly antennae and a wide toothy grin",
    "a square teal monster with one huge eye and tiny horns",
    "a round fluffy rainbow-striped monster with big round eyes",
    "a blue blob monster with three eyes on stalks and stubby arms",
    "a long caterpillar-like rainbow monster with many little legs and a smiling face",
    "a yellow triangle-shaped monster with purple bat wings and horns",
    "a boxy red-and-teal robot monster with antenna and a happy screen face",
    "a green spotted monster with a giant open mouth full of square teeth",
  ],
  'farm': [
    "a pink pig standing on two legs, waving", "a black-and-white spotted cow",
    "a fluffy white sheep with a black face", "a yellow chicken with a red comb",
    "a brown puppy dog with floppy ears", "a grey cat with big green eyes",
    "a white rabbit with long pink ears", "a yellow duckling with an orange beak",
  ],
  'cars': [
    "a small yellow city car with eyes as headlights", "a blue delivery truck with a smiling face",
    "an orange school bus with a happy face", "a green racing car with a spoiler and the number 7",
    "a red tractor with big back wheels and a face", "a purple camper van with a smiling face",
    "a red fire truck with a ladder and a face", "a red beetle-shaped car with eyes and yellow spots",
  ],
  'birds': [
    "a plump yellow bird flying with spread wings", "a pink bird with a long tail, flying",
    "a blue bird flying, seen from the side", "a green parrot flying with colourful wings",
    "a big butterfly with rainbow wings", "a chubby striped bee with light-blue wings",
    "a purple bat with spread wings, friendly face", "a smiling orange balloon on a string",
  ],
}
PROPS = {
  'night': ["a purple round boulder", "a cluster of glowing purple and blue crystals",
            "three small purple rocks in a row", "a purple spotted alien mushroom", "a small round crater ring"],
  'farm':  ["a white daisy flower on a stem", "a red tulip", "a sunflower", "a golden haystack",
            "a red mushroom with white dots", "a green bush with red berries", "a blue wooden fence piece", "a tree stump"],
  'track': ["a single black car tire", "a stack of three black tires", "an orange-and-white traffic cone",
            "a blue barrel", "a checkered racing flag on a pole", "a red fuel canister", "a grey crash barrier piece", "a red stop sign"],
}
PROP_STYLE = ("drawn like a child's felt-tip marker drawing: bold black outlines, bright marker colours, "
              "simple shapes, single object, centered, isolated on a transparent background, no shadow, no text")

ICON = ("App icon: one cute fluffy teal monster with big eyes, small horns and a happy smile, "
        "drawn like a child's marker drawing with bold outlines, centered on a deep purple night sky "
        "with a moon and yellow stars, flat bold shapes, high contrast, fills the whole square, no text")

def gen(prompt, out, transparent=True, size='1024x1024'):
    if os.path.exists(out): print('есть  ', os.path.relpath(out, ROOT)); return True
    body = {'model': MODEL, 'prompt': prompt, 'size': size, 'n': 1, 'quality': 'medium', 'output_format': 'png'}
    if transparent: body['background'] = 'transparent'
    req = urllib.request.Request('https://api.openai.com/v1/images/generations',
        data=json.dumps(body).encode(), method='POST',
        headers={'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                j = json.load(r)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, 'wb') as f: f.write(base64.b64decode(j['data'][0]['b64_json']))
            print('ок    ', os.path.relpath(out, ROOT)); return True
        except Exception as e:
            msg = getattr(e, 'read', lambda: b'')().decode(errors='ignore')[:200] or str(e)
            print(f'сбой  {os.path.relpath(out, ROOT)}: {msg}'); time.sleep(3)
    return False

def main():
    if not KEY: sys.exit('нужен OPENAI_API_KEY')
    want = sys.argv[1:] or ['monsters', 'farm', 'cars', 'birds', 'props', 'icon']
    for k in ('monsters', 'farm', 'cars', 'birds'):
        if k in want:
            for i, p in enumerate(PACKS[k], 1):
                gen(f'{p}, {STYLE}', os.path.join(INC, k, f'{i:02d}.png'))
    worlds = [a.split(':')[1] for a in want if a.startswith('props:')] or (list(PROPS) if 'props' in want else [])
    for w in worlds:
        for i, p in enumerate(PROPS[w], 1):
            gen(f'{p}, {PROP_STYLE}', os.path.join(INC, 'props', w, f'{i:02d}.png'))
    if 'icon' in want:
        gen(ICON, os.path.join(INC, 'icon.png'), transparent=False)

if __name__ == '__main__':
    main()
