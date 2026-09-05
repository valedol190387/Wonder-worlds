"""
Полигон скелетной анимации.

  POST /rig            картинка -> скелет (детектор + позер из torchserve)
  POST /animate/<id>   {motion} -> лист кадров PNG с альфой
  GET  /               страница полигона
  GET  /out/<id>/...   результаты

Внутри — Meta Animated Drawings (MIT). Мы ничего в нём не меняем: только
перенаправляем его запросы к torchserve на нужный адрес и добавляем свой
писатель кадров, который вместо GIF складывает лист PNG с прозрачностью —
его потом сможет играть мир на телевизоре.
"""
import os, sys, json, uuid, time, math, traceback, logging, threading
from pathlib import Path

RENDER_LOCK = threading.Lock()          # рендеры по одному
RIG_MAX = 360                           # рабочий размер персонажа: кадр листа всё равно 360
RENDER_SECONDS = 4.0                    # сколько записи рендерим: цикл-два движения
AMPLIFY = 1.5                           # размах движений: мультяшный, для схематичных рисунков
TARGET_FPS = 24                         # частота листа на экране

import numpy as np
import yaml
from flask import Flask, request, jsonify, send_from_directory, send_file

TORCHSERVE = os.environ.get('TORCHSERVE', 'http://localhost:8080').rstrip('/')
OUT = Path(os.environ.get('OUT_DIR', './out')); OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'bvh').mkdir(exist_ok=True)
AD = Path('/app/AnimatedDrawings') if Path('/app/AnimatedDrawings').exists() else Path(__file__).resolve().parents[1] / 'AnimatedDrawings'
sys.path.insert(0, str(AD / 'examples'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger('skeleton')

# --- перенаправляем обращения примера к torchserve ---------------------------
import requests
_post = requests.post

class _Resp:
    def __init__(self, content, status_code=200):
        self.content, self.status_code = content, status_code

def _post_redirected(url, *a, **k):
    if url.startswith('http://localhost:8080'):
        url = TORCHSERVE + url[len('http://localhost:8080'):]
    resp = _post(url, *a, **k)
    if url.endswith('drawn_humanoid_detector') and resp.status_code < 300:
        # Пример берёт детекцию с наибольшей уверенностью. На детском рисунке
        # это часто ГОЛОВА (у неё выразительнее черты), а тело с руками
        # остаётся за кадром. Нам детектор нужен не чтобы найти персонажа —
        # он на вырезе один, — а чтобы получить рамку. Берём самую крупную, а
        # если и она меньше 60% картинки, рамкой становится вся картинка.
        try:
            dets = json.loads(resp.content)
            files = k.get('files') or (a[0] if a else None)
            img_b = files['data'] if isinstance(files, dict) else None
            H = W = None
            if img_b is not None:
                arr = cv2.imdecode(np.frombuffer(img_b, np.uint8), cv2.IMREAD_COLOR)
                if arr is not None:
                    H, W = arr.shape[:2]
            if isinstance(dets, list) and dets and H and W:
                # Рамка — вся картинка, всегда: мы уже обрезали её по альфе с
                # полем. Рамка впритык к фигуре рвёт внешний контур силуэта о
                # края кадра, и построитель сетки берёт кусок вместо целого.
                log.info('детекций %d — рамка вся картинка (%dx%d)', len(dets), W, H)
                return _Resp(json.dumps([{'bbox': [0, 0, W, H], 'score': 1.0}]).encode(), 200)
        except Exception:
            log.warning('не смог перечитать детекции: %s', traceback.format_exc())
    return resp
requests.post = _post_redirected

from image_to_annotations import image_to_annotations  # noqa: E402
import animated_drawings.render                        # noqa: E402
from animated_drawings.controller import video_render_controller as vrc  # noqa: E402
import cv2                                              # noqa: E402

# --- писатель кадров: лист PNG с альфой вместо GIF ----------------------------
class SheetWriter(vrc.VideoWriter):
    """Складывает кадры в сетку. Рядом пишет json: размер кадра, сколько их,
    сколько в ряду, частота. Мир на телевизоре умеет играть такое с canvas."""
    COLS = 10
    MAX_FRAMES = 150

    def __init__(self, controller):
        super().__init__()
        # их валидатор пускает только .gif/.mp4 — в конфиге .gif, пишем PNG рядом
        self.out = Path(controller.cfg.output_video_path).with_suffix('.png')
        self.frames = []
        self.fps = 1.0 / max(1e-3, controller.delta_t) if getattr(controller, 'delta_t', None) else 24.0

    def process_frame(self, frame):
        self.frames.append(cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA).astype(np.uint8))

    def cleanup(self):
        n = len(self.frames)
        if not n:
            return
        # шаг — чтобы на экране было ~24 к/с; потолок кадров только страховка
        step = max(1, round(self.fps / TARGET_FPS))
        while math.ceil(n / step) > self.MAX_FRAMES: step += 1
        frames = self.frames[::step]
        fps = self.fps / step
        h, w = frames[0].shape[:2]
        # обрезаем общий пустой край, чтобы лист не был на три четверти воздухом
        alpha = np.max(np.stack([f[:, :, 3] for f in frames]), axis=0)
        ys, xs = np.where(alpha > 8)
        if len(xs):
            x0, x1 = max(0, xs.min() - 4), min(w, xs.max() + 5)
            y0, y1 = max(0, ys.min() - 4), min(h, ys.max() + 5)
            frames = [f[y0:y1, x0:x1] for f in frames]
            h, w = frames[0].shape[:2]
        cols = min(self.COLS, len(frames)); rows = math.ceil(len(frames) / cols)
        sheet = np.zeros((rows * h, cols * w, 4), np.uint8)
        for i, f in enumerate(frames):
            r, c = divmod(i, cols)
            sheet[r*h:(r+1)*h, c*w:(c+1)*w] = f
        cv2.imwrite(str(self.out), cv2.cvtColor(sheet, cv2.COLOR_RGBA2BGRA))
        meta = {'frames': len(frames), 'cols': cols, 'rows': rows, 'w': w, 'h': h, 'fps': round(fps, 2), 'source_frames': n}
        self.out.with_suffix('.json').write_text(json.dumps(meta))
        log.info('лист %s: %s', self.out.name, meta)

_orig_create = vrc.VideoWriter.create_video_writer
def _create(controller):
    if Path(controller.cfg.output_video_path).suffix == '.gif':
        return SheetWriter(controller)          # вместо GIF — лист PNG с альфой
    return _orig_create(controller)
vrc.VideoWriter.create_video_writer = staticmethod(_create)

# --- вырезание фона: та же U²-Net, что на телефоне ---------------------------------
#  На полигон кидают что угодно: стикеры, скриншоты, фото. Детектору Meta
#  нужен персонаж на белом, а нам для маски — честная альфа. Если у картинки
#  прозрачности нет, режем сами той же моделью, что и приложение.
import onnxruntime as ort
U2 = ort.InferenceSession(str(Path(__file__).with_name('u2netp.onnx')), providers=['CPUExecutionProvider'])
U2_IN = U2.get_inputs()[0].name
U2_MEAN = np.array([0.485, 0.456, 0.406], np.float32); U2_STD = np.array([0.229, 0.224, 0.225], np.float32)

def cutout_alpha(bgr):
    """BGR -> альфа 0..255 того же размера"""
    h, w = bgr.shape[:2]
    small = cv2.resize(bgr, (320, 320), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32)
    rgb = rgb / max(1.0, float(rgb.max()))
    x = ((rgb - U2_MEAN) / U2_STD).transpose(2, 0, 1)[None].astype(np.float32)
    pred = U2.run(None, {U2_IN: x})[0][0, 0]
    pred = (pred - pred.min()) / max(1e-6, float(pred.max() - pred.min()))
    return cv2.resize((pred * 255).astype(np.uint8), (w, h), interpolation=cv2.INTER_LINEAR)

def solid_mask(alpha, thr=96):
    """Сплошной силуэт: самая крупная область, все дыры внутри залиты.
    Их построитель сетки берёт САМЫЙ ДЛИННЫЙ контур как внешний — если в
    маске есть дыра (глаз, экран, просвет между ногами), длиннее может
    оказаться она, и сетка превращается в лоскут."""
    m = (alpha > thr).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n > 1:
        big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        m = (lab == big).astype(np.uint8)
    # заливка дыр: всё, что не достижимо от края по фону, — внутри персонажа
    h, w = m.shape
    ff = np.zeros((h + 2, w + 2), np.uint8)
    bg = (1 - m).copy()
    cv2.floodFill(bg, ff, (0, 0), 2)
    for x in (0, w - 1):
        for y in range(0, h, max(1, h // 8)):
            if bg[y, x] == 1: cv2.floodFill(bg, ff, (x, y), 2)
    for y in (0, h - 1):
        for x in range(0, w, max(1, w // 8)):
            if bg[y, x] == 1: cv2.floodFill(bg, ff, (x, y), 2)
    filled = (bg != 2).astype(np.uint8)     # фон = то, куда дотекла заливка
    return filled * 255

# --- движения ------------------------------------------------------------------
MOTION_DIR = AD / 'examples/config/motion'
RETARGET_DIR = AD / 'examples/config/retarget'
MOTIONS = {p.stem: p for p in sorted(MOTION_DIR.glob('*.yaml'))}
RU = {'dab': 'дэб', 'jesse_dance': 'танец', 'jumping': 'прыжок', 'jumping_jacks': 'зарядка',
      'wave_hello': 'машет', 'zombie': 'зомби-шаг'}

def bvh_frame_time(path: Path) -> float:
    for line in path.read_text().splitlines():
        if line.strip().startswith('Frame Time:'):
            return float(line.split(':')[1])
    return 1 / 60

def amplified_bvh(src: Path, amp: float, dst: Path) -> Path:
    """Копия записи с усиленными поворотами суставов: угол = покой +
    (угол − покой)·amp, где покой — первый кадр. Позиции корня не трогаем.
    Углы по времени разворачиваем, чтобы скачок через ±180° не улетал."""
    if dst.exists():
        return dst
    text = src.read_text().splitlines()
    i_motion = next(i for i, l in enumerate(text) if l.strip() == 'MOTION')
    chans = []
    for l in text[:i_motion]:
        t = l.strip().split()
        if t and t[0] == 'CHANNELS':
            chans += t[2:2 + int(t[1])]
    i_data = i_motion + 3                                   # Frames:, Frame Time:
    data = np.array([[float(v) for v in l.split()] for l in text[i_data:] if l.strip()])
    rot = np.array([c.lower().endswith('rotation') for c in chans])
    ang = np.unwrap(np.deg2rad(data[:, rot]), axis=0)
    rest = ang[0]
    data[:, rot] = np.rad2deg(rest + (ang - rest) * amp)
    out = text[:i_data] + [' '.join(f'{v:.6f}' for v in row) for row in data]
    dst.write_text('\n'.join(out) + '\n')
    return dst

def retarget_for(motion_cfg: Path) -> Path:
    fp = yaml.safe_load(motion_cfg.read_text()).get('filepath', '')
    if 'cmu1' in fp: return RETARGET_DIR / 'cmu1_pfp.yaml'
    if 'rokoko' in fp or 'mixamo' in fp: return RETARGET_DIR / 'mixamo_fff.yaml'
    return RETARGET_DIR / 'fair1_ppf.yaml'

# --- служба ----------------------------------------------------------------------
app = Flask(__name__, static_folder=None)

@app.get('/')
def index():
    return send_file(Path(__file__).with_name('lab.html'))

@app.get('/health')
def health():
    try:
        ok = requests.get(TORCHSERVE + '/ping', timeout=3).ok
    except Exception:
        ok = False
    return jsonify(ok=True, torchserve=ok, motions=list(MOTIONS))

@app.post('/rig')
def rig():
    f = request.files.get('image')
    if not f:
        return jsonify(error='нужна картинка'), 400
    rid = uuid.uuid4().hex[:10]
    d = OUT / rid; d.mkdir(parents=True)
    src = d / 'input.png'
    f.save(src)
    t0 = time.time()
    try:
        # AnimatedDrawings ждёт рисунок на светлом фоне: прозрачность кладём на белое
        img = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
        if img is None:
            return jsonify(error='не прочиталась'), 400
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        has_alpha = img.ndim == 3 and img.shape[2] == 4 and 0.02 < float((img[:, :, 3] < 96).mean()) < 0.98
        if not has_alpha:
            # прозрачности нет (или она пустая) — вырезаем сами, как телефон
            bgr = img[:, :, :3] if img.shape[2] == 4 else img
            alpha = cutout_alpha(bgr)
            img = np.dstack([bgr, alpha])
            log.info('вырезал фон моделью: непрозрачного %.0f%%', 100 * float((alpha >= 96).mean()))
        # обрезаем по персонажу с полем — детектору проще, рамке нечего терять
        ys, xs = np.where(img[:, :, 3] >= 96)
        if len(xs) < 200:
            return jsonify(error='на картинке не нашлось персонажа', id=rid), 422
        pad = int(0.06 * max(img.shape[:2]))
        y0, y1 = max(0, ys.min() - pad), min(img.shape[0], ys.max() + pad + 1)
        x0, x1 = max(0, xs.min() - pad), min(img.shape[1], xs.max() + pad + 1)
        img = img[y0:y1, x0:x1]
        cv2.imwrite(str(d / 'cutout.png'), img)
        a = img[:, :, 3:4] / 255.0
        cv2.imwrite(str(src), (img[:, :, :3] * a + 255 * (1 - a)).astype(np.uint8))   # для детектора — на белом
        image_to_annotations(str(src), str(d))
        # Их сегментация режет по яркости и теряет светлое внутри: у девочки
        # провалилось лицо. У нас есть честная альфа выреза — она и есть маска.
        if True:
            cfg = yaml.safe_load((d / 'char_cfg.yaml').read_text())
            bb = yaml.safe_load((d / 'bounding_box.yaml').read_text())
            scale = min(1.0, 1000 / max(img.shape[:2]))
            a = cv2.resize(img[:, :, 3], (round(img.shape[1]*scale), round(img.shape[0]*scale)))
            a = a[bb['top']:bb['bottom'], bb['left']:bb['right']]
            hole = float((a < 96).mean())          # доля прозрачного
            # альфа есть, но фон в ней непрозрачный (белый) — это не вырез,
            # такая «маска» была бы сплошным прямоугольником; оставляем их сегментацию
            if a.shape[0] == cfg['height'] and a.shape[1] == cfg['width'] and 0.02 < hole < 0.98:
                cv2.imwrite(str(d / 'mask.png'), solid_mask(a))
                log.info('маска взята из альфы выреза (прозрачного %.0f%%), дыры залиты', hole * 100)
            else:
                log.info('альфа без прозрачности (%.0f%%) — маска остаётся от сегментации', hole * 100)
    except Exception as e:
        log.error('rig %s: %s', rid, traceback.format_exc())
        return jsonify(error=f'скелет не нашёлся: {e}', id=rid), 422
    cfg = yaml.safe_load((d / 'char_cfg.yaml').read_text())
    W, H = cfg['width'], cfg['height']
    # Сетка рендера строится по маске: персонаж в 1000 px — это в четыре раза
    # больше треугольников, чем в 500, а кадр листа всё равно 360. Ужимаем.
    k = min(1.0, RIG_MAX / max(W, H))
    if k < 1.0:
        nw, nh = max(1, round(W * k)), max(1, round(H * k))
        for name in ('texture.png', 'mask.png'):
            im = cv2.imread(str(d / name), cv2.IMREAD_UNCHANGED)
            interp = cv2.INTER_NEAREST if name == 'mask.png' else cv2.INTER_AREA   # маска остаётся 0/255
            cv2.imwrite(str(d / name), cv2.resize(im, (nw, nh), interpolation=interp))
        for s in cfg['skeleton']:
            s['loc'] = [s['loc'][0] * k, s['loc'][1] * k]
        cfg['width'], cfg['height'] = W, H = nw, nh
        log.info('персонаж ужат до %dx%d', nw, nh)
    # позер иногда кладёт сустав на пиксель за рамку, а рендер на этом падает
    for s in cfg['skeleton']:
        s['loc'] = [int(min(max(s['loc'][0], 0), W - 1)), int(min(max(s['loc'][1], 0), H - 1))]
    (d / 'char_cfg.yaml').write_text(yaml.dump(cfg))
    return jsonify(id=rid, seconds=round(time.time() - t0, 1), skeleton=cfg['skeleton'],
                   width=cfg['width'], height=cfg['height'], motions=list(MOTIONS))

@app.post('/animate/<rid>')
def animate(rid):
    d = OUT / rid
    if not (d / 'char_cfg.yaml').exists():
        return jsonify(error='нет такого скелета'), 404
    motion = (request.json or {}).get('motion', 'dab')
    if motion not in MOTIONS:
        return jsonify(error='нет такого движения'), 400
    amp_q = float((request.json or {}).get('amp', AMPLIFY))
    tag = f'{motion}_x{amp_q:g}'          # размах всегда в имени: листы с разным размахом не путаются
    out_png = d / f'{tag}.png'
    if out_png.exists() and out_png.with_suffix('.json').exists():
        return jsonify(id=rid, motion=motion, sheet=f'/out/{rid}/{tag}.png',
                       meta=json.loads(out_png.with_suffix('.json').read_text()), cached=True)
    mcfg = MOTIONS[motion]
    # Записи длинные (у «машет» 839 кадров), а софтверный рендер даёт ~10 к/с:
    # почти всё время уходило на кадры, которые потом выбрасываются. Режем
    # запись до цикла-двух — пишем рядом урезанную копию конфига движения.
    amp = float((request.json or {}).get('amp', AMPLIFY))
    m = yaml.safe_load(mcfg.read_text())
    bvh = Path(m['filepath']) if str(m['filepath']).startswith('/') else (AD / m['filepath']).resolve()
    ft = bvh_frame_time(bvh)
    start = int(m.get('start_frame_idx') or 0)
    end = m.get('end_frame_idx')                       # null = до конца записи
    total = (int(end) - start) if end is not None else 10**9
    want = int(RENDER_SECONDS / ft)                    # записи разной частоты: режем по времени
    m['end_frame_idx'] = start + min(total, want)
    if amp != 1.0:
        bvh = amplified_bvh(bvh, amp, OUT / 'bvh' / f'{bvh.stem}_x{amp:g}.bvh')
    m['filepath'] = str(bvh)
    mcfg = d / f'motion_{motion}.yaml'
    mcfg.write_text(yaml.dump(m))
    log.info('%s: %.0f к/с в записи, берём %d кадров (%.1f с), размах ×%g', motion, 1/ft, m['end_frame_idx']-start, (m['end_frame_idx']-start)*ft, amp)
    mvc = {
        'scene': {'ANIMATED_CHARACTERS': [{
            'character_cfg': str(d / 'char_cfg.yaml'),
            'motion_cfg': str(mcfg),
            'retarget_cfg': str(retarget_for(MOTIONS[motion])),   # по исходной записи: усиленная копия лежит в другой папке
        }]},
        'view': {'USE_MESA': True, 'WINDOW_DIMENSIONS': [360, 360],
                 'CLEAR_COLOR': [1.0, 1.0, 1.0, 0.0]},
        'controller': {'MODE': 'video_render', 'OUTPUT_VIDEO_PATH': str(out_png.with_suffix('.gif'))},
    }
    mvc_fn = d / f'mvc_{motion}.yaml'
    mvc_fn.write_text(yaml.dump(mvc))
    t0 = time.time()
    # Рендеры строго по одному: шесть параллельных душат друг друга, а
    # контексты OSMesa в потоках ещё и не дружат. Очередь — и всё идёт.
    with RENDER_LOCK:
        if out_png.exists() and out_png.with_suffix('.json').exists():   # пока ждали — сделал сосед
            return jsonify(id=rid, motion=motion, sheet=f'/out/{rid}/{motion}.png',
                           meta=json.loads(out_png.with_suffix('.json').read_text()), cached=True)
        try:
            animated_drawings.render.start(str(mvc_fn))
        except Exception as e:
            log.error('animate %s/%s: %s', rid, motion, traceback.format_exc())
            return jsonify(error=f'рендер упал: {e}'), 500
    return jsonify(id=rid, motion=motion, sheet=f'/out/{rid}/{tag}.png',
                   meta=json.loads(out_png.with_suffix('.json').read_text()),
                   seconds=round(time.time() - t0, 1))

@app.get('/out/<rid>/<path:name>')
def out(rid, name):
    return send_from_directory(OUT / rid, name)

@app.get('/motions')
def motions():
    return jsonify({k: RU.get(k, k) for k in MOTIONS})

if __name__ == '__main__':
    log.info('полигон: torchserve=%s out=%s движений=%d', TORCHSERVE, OUT, len(MOTIONS))
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8200)), threaded=True)
