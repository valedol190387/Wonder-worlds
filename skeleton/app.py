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
import os, sys, json, uuid, time, math, traceback, logging
from pathlib import Path

import numpy as np
import yaml
from flask import Flask, request, jsonify, send_from_directory, send_file

TORCHSERVE = os.environ.get('TORCHSERVE', 'http://localhost:8080').rstrip('/')
OUT = Path(os.environ.get('OUT_DIR', './out')); OUT.mkdir(parents=True, exist_ok=True)
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
            if isinstance(dets, list) and dets:
                def area(d):
                    l, t, r, b = d['bbox']; return max(0, r - l) * max(0, b - t)
                dets.sort(key=area, reverse=True)
                big = dets[0]
                if H and W and area(big) < 0.6 * H * W:
                    log.info('детекция %.0f%% картинки — беру картинку целиком', 100 * area(big) / (H * W))
                    big = {'bbox': [0, 0, W, H], 'score': 1.0}
                else:
                    log.info('беру самую крупную детекцию из %d', len(dets))
                big['score'] = 1.0
                return _Resp(json.dumps([big]).encode(), 200)
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
    MAX_FRAMES = 80

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
        step = max(1, math.ceil(n / self.MAX_FRAMES))
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

# --- движения ------------------------------------------------------------------
MOTION_DIR = AD / 'examples/config/motion'
RETARGET_DIR = AD / 'examples/config/retarget'
MOTIONS = {p.stem: p for p in sorted(MOTION_DIR.glob('*.yaml'))}
RU = {'dab': 'дэб', 'jesse_dance': 'танец', 'jumping': 'прыжок', 'jumping_jacks': 'зарядка',
      'wave_hello': 'машет', 'zombie': 'зомби-шаг'}

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
        if img.ndim == 3 and img.shape[2] == 4:
            a = img[:, :, 3:4] / 255.0
            rgb = img[:, :, :3] * a + 255 * (1 - a)
            cv2.imwrite(str(src), rgb.astype(np.uint8))
        image_to_annotations(str(src), str(d))
        # Их сегментация режет по яркости и теряет светлое внутри: у девочки
        # провалилось лицо. У нас есть честная альфа выреза — она и есть маска.
        if img.ndim == 3 and img.shape[2] == 4:
            cfg = yaml.safe_load((d / 'char_cfg.yaml').read_text())
            bb = yaml.safe_load((d / 'bounding_box.yaml').read_text())
            scale = min(1.0, 1000 / max(img.shape[:2]))
            a = cv2.resize(img[:, :, 3], (round(img.shape[1]*scale), round(img.shape[0]*scale)))
            a = a[bb['top']:bb['bottom'], bb['left']:bb['right']]
            if a.shape[0] == cfg['height'] and a.shape[1] == cfg['width']:
                cv2.imwrite(str(d / 'mask.png'), (a > 96).astype(np.uint8) * 255)
                log.info('маска взята из альфы выреза')
    except Exception as e:
        log.error('rig %s: %s', rid, traceback.format_exc())
        return jsonify(error=f'скелет не нашёлся: {e}', id=rid), 422
    cfg = yaml.safe_load((d / 'char_cfg.yaml').read_text())
    # позер иногда кладёт сустав на пиксель за рамку, а рендер на этом падает
    W, H = cfg['width'], cfg['height']
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
    out_png = d / f'{motion}.png'
    if out_png.exists() and out_png.with_suffix('.json').exists():
        return jsonify(id=rid, motion=motion, sheet=f'/out/{rid}/{motion}.png',
                       meta=json.loads(out_png.with_suffix('.json').read_text()), cached=True)
    mcfg = MOTIONS[motion]
    mvc = {
        'scene': {'ANIMATED_CHARACTERS': [{
            'character_cfg': str(d / 'char_cfg.yaml'),
            'motion_cfg': str(mcfg),
            'retarget_cfg': str(retarget_for(mcfg)),
        }]},
        'view': {'USE_MESA': True, 'WINDOW_DIMENSIONS': [360, 360],
                 'CLEAR_COLOR': [1.0, 1.0, 1.0, 0.0]},
        'controller': {'MODE': 'video_render', 'OUTPUT_VIDEO_PATH': str(out_png.with_suffix('.gif'))},
    }
    mvc_fn = d / f'mvc_{motion}.yaml'
    mvc_fn.write_text(yaml.dump(mvc))
    t0 = time.time()
    try:
        animated_drawings.render.start(str(mvc_fn))
    except Exception as e:
        log.error('animate %s/%s: %s', rid, motion, traceback.format_exc())
        return jsonify(error=f'рендер упал: {e}'), 500
    return jsonify(id=rid, motion=motion, sheet=f'/out/{rid}/{motion}.png',
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
