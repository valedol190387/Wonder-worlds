# Фоны миров — спецификация для генерации

Кладём готовые файлы сюда: `bg/night.jpg`, `bg/day.jpg`, `bg/farm.jpg`, `bg/track.jpg`, `bg/sky.jpg`.
Файл есть — движок берёт его. Файла нет — рисует градиентом, ничего не ломается.

---

## 1. Геометрия — это главное

| Параметр | Значение |
|---|---|
| Соотношение сторон | **16:9**, строго |
| Генерировать | **3840 × 2160** |
| Класть в проект | **2560 × 1440** |
| **Линия горизонта** | **ровно 1/3 сверху** |
| Горизонт в пикселях | y = **720** на 4K · y = **480** на 2560 |
| Рабочая зона | нижние **2/3** кадра |

**Исключение — мир «Небо» (`sky.jpg`).** Он перевёрнут: там летают, а не ходят,
поэтому горизонт уходит вниз.

| Параметр | Значение |
|---|---|
| Линия горизонта | **на 82% сверху** |
| Горизонт в пикселях | y = **1771** на 4K · y = **1181** на 2560 |
| Рабочая зона | **верхние 82%** — само небо |

Горизонт должен быть **строго горизонтальным** и на всю ширину: не наклонённым,
не изогнутым, не «размытым переходом».

**А вот попасть в точное число не обязательно.** Приложение само находит горизонт
на картинке по перепаду цвета и смене фактуры и подгоняет её под себя.
Генераторы стабильно промахиваются (просишь 33%, получаешь 37–38%) — это
исправляется автоматически, перегенерировать не надо.

Работает это в пределах **±15%** от заявленного числа. Если горизонт уехал
сильнее, приложение не поверит находке и возьмёт значение из конфига мира —
тогда картинку лучше перегенерировать или прописать ей `bgHorizon` вручную.

---

## 2. Рабочая зона (нижние 2/3) — почти пустая

Это площадка, по которой ходят персонажи. Требования жёсткие:

- **Ничего крупного в центре.** Ни деревьев, ни камней, ни построек, ни техники
- Декор — **только вдоль левого и правого края** и **у самого горизонта**
- **Ни людей, ни животных, ни персонажей** — их приносят дети
- **Ни текста, ни подписей, ни логотипов, ни рамок**
- Поверхность должна читаться как **уходящая вдаль плоскость**: детали и текстура
  крупные внизу и мелкие к горизонту
- **Ровный свет.** Без виньетки, без резких теней поперёк площадки. Движок сам
  рисует мягкую тень-эллипс под каждым персонажем, и чужие тени с ней конфликтуют

---

## 3. Цвет — под детские рисунки

Рисунки приходят яркими фломастерами на белой бумаге. Фон не должен с ними спорить:

- Земля — **средней или приглушённой светлоты**. Не белая и не очень светлая,
  иначе белые края рисунков растворятся
- **Насыщенность фона ниже, чем у рисунка.** Самое яркое на экране — ребёнок,
  а не трава
- **Без мелкой пёстрой текстуры.** Крупные мягкие пятна, персонажи на них читаются
- Небо может быть любым — там никто не ходит

---

## 4. Безопасные поля

Экраны бывают не только 16:9, картинка обрезается по бокам:

- Всё важное держать в **центральных 75% по ширине** — это то, что видно всегда
- **Нижние 12%** перекрыты панелью кнопок и затемнением — туда ничего важного
- **Верхние 8%** — там всплывают сообщения

---

## 5. Файлы

| | |
|---|---|
| Формат | JPEG качество 82, или WebP качество 80 |
| Вес | **до 600 КБ** на файл |
| Имена | `night.jpg` `day.jpg` `farm.jpg` `track.jpg` `sky.jpg` |

Превьюшка в выборе миров делается из этого же файла автоматически, отдельную
готовить не надо.

---

## 6. Промпты — готовые, вставлять целиком

Каждый самодостаточный. Ничего дописывать не надо.
Для Midjourney хвост `--ar 16:9` уже внутри, для остальных он просто игнорируется.

### night.jpg — Планета, ночь
```
Painterly children's book illustration of an alien planet at night. Wide 16:9 landscape. The horizon line is a perfectly straight horizontal line positioned exactly one third down from the top of the frame. Deep violet and indigo night sky with two moons and scattered stars in the upper third. The lower two thirds are one vast, flat, completely empty dusty purple plain with nothing standing on it. A few shallow craters and small rocks appear only along the far left and far right edges. A silhouette of low distant hills runs along the horizon. Ground texture is coarse in the foreground and becomes fine near the horizon. Soft even diffuse light, no harsh shadows, no vignette. Muted low saturation colours, medium darkness so bright drawings stand out against it. No people, no characters, no animals, no text. --ar 16:9
```

### day.jpg — Планета, день
```
Painterly children's book illustration of an alien planet in daylight. Wide 16:9 landscape. The horizon line is a perfectly straight horizontal line positioned exactly one third down from the top of the frame. Warm blue sky with a soft pale sun and light haze in the upper third. The lower two thirds are one vast, flat, completely empty sandy ochre desert plain with nothing standing on it. Low dunes and shallow craters appear only along the far left and far right edges. Distant rocky ridges run along the horizon. Ground texture is coarse in the foreground and becomes fine near the horizon. Soft even diffuse light, no harsh shadows, no vignette. Muted dusty low saturation colours, medium tone so bright drawings stand out against it. No people, no characters, no animals, no text. --ar 16:9
```

### farm.jpg — Ферма
```
Painterly children's book illustration of a countryside meadow on a sunny day. Wide 16:9 landscape. The horizon line is a perfectly straight horizontal line positioned exactly one third down from the top of the frame. Blue sky with a few soft clouds in the upper third. The lower two thirds are one vast, flat, completely empty green grass field with nothing standing on it. A wooden fence, bushes and a couple of trees appear only along the far left and far right edges. Rolling green hills and a small distant red barn sit far away on the horizon. Grass texture is coarse in the foreground and becomes fine near the horizon. Soft even diffuse light, no harsh shadows, no vignette. Muted low saturation greens, medium tone so bright drawings stand out against it. No people, no characters, no animals, no text. --ar 16:9
```

### track.jpg — Автодром
```
Painterly children's book illustration of an empty racetrack seen from the driver's point of view. Wide 16:9 landscape. The horizon line is a perfectly straight horizontal line positioned exactly one third down from the top of the frame. Clear daytime sky with light haze in the upper third. The lower two thirds are one vast, flat, completely empty grey asphalt surface with nothing standing on it, crossed only by white painted lane markings that converge toward the horizon. Low grass banks, safety barriers and striped kerbs appear only along the far left and far right edges. A distant grandstand silhouette sits on the horizon. Asphalt texture is coarse in the foreground and becomes fine near the horizon. Soft even diffuse light, no harsh shadows, no vignette. Muted low saturation grey and green, medium tone so bright drawings stand out against it. No people, no characters, no animals, no text. --ar 16:9
```

### sky.jpg — Небо
```
Painterly children's book illustration of a vast open daytime sky seen from high above the clouds. Wide 16:9 landscape. The horizon line is a perfectly straight horizontal line positioned low in the frame, exactly 82 percent down from the top. The upper 82 percent is one huge open blue sky with a soft sun in the upper right and scattered soft white clouds placed only near the left edge, the right edge and along the bottom near the horizon, leaving the whole middle of the sky completely open and empty. The bottom strip below the horizon is a distant hazy land and sea seen from very far away, with no detail. Clouds are large near the bottom and small near the top. Soft even diffuse light, no harsh shadows, no vignette. Clear medium blue sky, saturated enough that bright drawings stand out against it, never washed out or white. No people, no characters, no birds, no animals, no text. --ar 16:9
```

**Важно для неба:** голубизна должна быть **выраженной, не белёсой**. Персонажи
летают по всему небу, и на бледном фоне светлые рисунки растворятся. Середина
неба должна остаться пустой — крупное облако по центру перекроет летящих.

### Негативный промпт (куда есть отдельное поле)
```
people, person, characters, animals, creatures, text, letters, watermark, signature, objects in the center, clutter, busy foreground, tilted horizon, curved horizon, vignette, frame, border, close-up, portrait, high contrast, neon colors, oversaturated
```

---

## 7. Новый мир

Дописать объект в `WORLDS` в `index.html` и положить сюда картинку:

```js
jungle: {
  label:'Джунгли', icon:'🌴', horizon:1/3, motion:'hop', bg:'bg/jungle.jpg',
  sky:['#0d2a1a','#1b4a2c','#3d7a4a'],          // запасной градиент
  hills:[{amp:.02,base:.88,col:'#123322'}],
  ground:['#2b5c33','#3d7a44','#5a9c5e'], haze:'150,200,150',
  decor:'bushes', decorCol:'#1e4a28', shadow:'#0f2a16',
  tag:'#eaffd0', dust:'#d8f0c8'
}
```

`motion` — как персонажи себя ведут:

| Значение | Поведение | Для чего |
|---|---|---|
| `'hop'` | прыгают по земле, сплющиваются при приземлении | монстры, звери |
| `'drive'` | катятся, покачиваясь, меняют полосу | машины |
| `'fly'` | парят, машут «крыльями», дрейфуют по всему небу | птицы, бабочки |

Для `'fly'` дополнительно задаются `bgHorizon` (где горизонт на картинке) и
`flyBand: [0.10, 0.70]` — полоса высот, в которой держатся летящие.

---

## 8. Про анимацию — на будущее

Статичная картинка анимируется поверх кодом, перегенерировать ничего не придётся:
плывущие облака, мерцание звёзд, качание травы, пыль по ветру.

Если захочется настоящий параллакс — сгенерировать **дополнительно**, отдельными
PNG с прозрачностью и на всю ширину:

- `night-sky.png` — только небо со светилами
- `night-far.png` — силуэт холмов у горизонта, ниже прозрачно
- `night-near.png` — кусты и камни по краям, остальное прозрачно

Тогда слои поедут с разной скоростью. Но это уже после основной механики.
