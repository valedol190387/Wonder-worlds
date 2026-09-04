# Промпты для наборов персонажей и реквизита

Генерить в ChatGPT (GPT-Image) или через OpenRouter. Всегда **по одному персонажу на картинку**,
на **прозрачном или чисто-белом фоне** — скрипт `tools/ingest.py` сам уберёт белый фон и обрежет.

Общий хвост — добавлять к каждому промпту:

```
Single character, full body, front or three-quarter view, centered, on a pure white background, no shadow, no ground, no text. Style: a child's felt-tip marker drawing on paper — bold wobbly dark outlines, bright saturated flat colors, big friendly eyes, simple shapes, slightly imperfect hand-drawn look. Square image.
```

Сохранять как `_incoming/<набор>/<номер>.png`, потом:

```bash
python3 tools/ingest.py
```

---

## monsters — Монстрики (8)

1. A tall skinny monster with two curly horns and a toothy grin
2. A wide square monster with one huge eye and stubby legs
3. A round fluffy monster covered in fur with tiny feet
4. A drop-shaped monster with three eyes and two antennae
5. A long caterpillar-like monster with many little legs
6. A triangle-shaped monster with bat wings and a shy smile
7. A boxy robot monster with a screen face and an antenna
8. A pear-shaped spotted monster with a giant open mouth

## farm — Ферма (8)

1. A pink pig
2. A black-and-white spotted cow
3. A fluffy white sheep with a dark face
4. A yellow chicken with a red comb
5. A brown floppy-eared dog
6. A grey cat with a long tail
7. A white rabbit with tall ears and pink inside
8. A yellow duck with an orange beak

## cars — Машинки (8)

1. A small yellow car with big round eyes as headlights
2. A blue truck with a cargo box
3. An orange school bus with many windows
4. A green race car with a spoiler and the number 7
5. A red tractor with one huge back wheel
6. A purple delivery van
7. A red fire truck with a ladder
8. A round beetle car with polka dots

## birds — Птички и летуны (8)

1. A round yellow bird with tiny wings, side view, flying
2. A pink bird with a long tail feather, flying
3. A blue bird with a little crest, flying
4. A green parrot with a curved beak, flying
5. A butterfly with big colorful wings, top view
6. A striped bee with round wings, flying
7. A purple bat with wide wings, friendly face
8. A smiling orange balloon with a string

---

## Реквизит (стоит на земле, низ картинки = земля)

Хвост для реквизита:

```
Single object, centered, sitting on the ground, bottom edge of the object touching the bottom of the image, on a pure white background, no shadow, no text. Style: a child's felt-tip marker drawing — bold dark outlines, bright flat colors, simple shapes. Square image.
```

### props/night — Планета (5)
1. A big purple boulder
2. A cluster of glowing blue and violet crystals
3. Three small purple rocks in a row
4. A strange alien mushroom, violet cap with white dots
5. A small purple crater ring seen from a low angle

### props/farm (8)
1. A white daisy flower on a green stem
2. A red tulip
3. A big sunflower
4. A golden haystack
5. A red mushroom with white dots
6. A round green bush with red berries
7. A short wooden fence piece
8. A tree stump

### props/track (8)
1. A black tire standing upright
2. A stack of three tires
3. An orange traffic cone
4. A blue barrel
5. A checkered finish flag on a pole
6. A red fuel can
7. A grey crash barrier
8. A red stop sign on a pole

---

## Иконка приложения (1)

```
App icon: one cute round friendly monster with big eyes and a happy smile, drawn like a child's felt-tip marker drawing, centered on a deep purple night sky with two small moons and stars. Flat bold shapes, thick outlines, high contrast, fills the square, no text. 1024x1024.
```

Сохранить как `_incoming/icon.png` — `tools/ingest.py` нарежет все размеры.
