#!/usr/bin/env node
/**
 * WonderWorlds — сервер.
 *
 * Ни одной зависимости: http, fs, crypto и встроенный node:sqlite (Node ≥ 22.13).
 * Запуск: node server.js        (PORT, DATA_DIR — через переменные окружения)
 *
 * Модель как у «взрослых» сервисов, но без аккаунтов:
 *   код мира   — 5 символов, по нему мир смотрят и добавляют в него монстриков
 *   ключ мира  — выдаётся создателю один раз, по нему миром управляют
 *                (сменить фон, очистить, удалить). Хранится в браузере создателя.
 *
 * Монстрики сохраняются на диск (PNG) и в базу (метаданные) — мир переживает
 * перезагрузку экрана, перезапуск сервера и деплой. Живые обновления на
 * экраны — через Server-Sent Events: одно направление, встроено в браузер,
 * переподключается само.
 */

const http   = require('http');
const fs     = require('fs');
const path   = require('path');
const url    = require('url');
const crypto = require('crypto');
const { DatabaseSync } = require('node:sqlite');

const PORT      = Number(process.env.PORT || 8123);
const DATA_DIR  = process.env.DATA_DIR || path.join(__dirname, 'data');
const ROOT      = __dirname;
const MAX_BODY  = 12 * 1024 * 1024;     // одна картинка (PNG монстрика или фон)
const MAX_MONSTERS = 60;                 // на мир; старые вытесняются
const MAX_WORLDS_PER_IP_HOUR = 20;
const WORLD_IDLE_DAYS = 90;              // мир без активности столько дней — удаляем

fs.mkdirSync(path.join(DATA_DIR, 'monsters'), { recursive: true });
fs.mkdirSync(path.join(DATA_DIR, 'bg'), { recursive: true });

/* ============================== база ============================== */

const db = new DatabaseSync(path.join(DATA_DIR, 'kidstv.db'));
db.exec(`
  PRAGMA journal_mode = WAL;
  CREATE TABLE IF NOT EXISTS worlds (
    code     TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL,
    name     TEXT NOT NULL DEFAULT '',
    world    TEXT NOT NULL DEFAULT 'night',
    motion   TEXT NOT NULL DEFAULT '',
    has_bg   INTEGER NOT NULL DEFAULT 0,
    created  INTEGER NOT NULL,
    seen     INTEGER NOT NULL
  );
  CREATE TABLE IF NOT EXISTS monsters (
    id      TEXT PRIMARY KEY,
    code    TEXT NOT NULL,
    name    TEXT NOT NULL DEFAULT '',
    created INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS monsters_code ON monsters(code, created);
`);

const q = {
  getWorld:    db.prepare('SELECT * FROM worlds WHERE code = ?'),
  insWorld:    db.prepare('INSERT INTO worlds(code,key_hash,name,world,motion,has_bg,created,seen) VALUES(?,?,?,?,?,0,?,?)'),
  touch:       db.prepare('UPDATE worlds SET seen = ? WHERE code = ?'),
  setWorld:    db.prepare('UPDATE worlds SET world = ?, motion = ?, has_bg = ?, name = ? WHERE code = ?'),
  delWorld:    db.prepare('DELETE FROM worlds WHERE code = ?'),
  listMon:     db.prepare('SELECT id,name,created FROM monsters WHERE code = ? ORDER BY created ASC'),
  countMon:    db.prepare('SELECT COUNT(*) AS n FROM monsters WHERE code = ?'),
  oldestMon:   db.prepare('SELECT id FROM monsters WHERE code = ? ORDER BY created ASC LIMIT ?'),
  insMon:      db.prepare('INSERT INTO monsters(id,code,name,created) VALUES(?,?,?,?)'),
  delMon:      db.prepare('DELETE FROM monsters WHERE id = ? AND code = ?'),
  delAllMon:   db.prepare('DELETE FROM monsters WHERE code = ?'),
  staleWorlds: db.prepare('SELECT code FROM worlds WHERE seen < ?'),
};

/* ============================ утилиты ============================ */

// без похожих символов: 0/O, 1/I на экране через полкомнаты не различить
const ALPHABET = 'ABCDEFGHJKLMNPQRTUVWXYZ23456789';
const randCode = n => { let c=''; for (let i=0;i<n;i++) c += ALPHABET[crypto.randomInt(ALPHABET.length)]; return c; };
const hash = s => crypto.createHash('sha256').update(String(s)).digest('hex');
const now  = () => Date.now();
const safeCode = c => String(c || '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8);
const safeId   = c => String(c || '').replace(/[^A-Za-z0-9]/g, '').slice(0, 32);

const monPath = (code, id) => path.join(DATA_DIR, 'monsters', code, id + '.png');
const bgPath  = code => path.join(DATA_DIR, 'bg', code + '.jpg');

function json(res, code, obj){
  const body = JSON.stringify(obj);
  res.writeHead(code, {'Content-Type':'application/json; charset=utf-8',
                       'Cache-Control':'no-store', 'Content-Length': Buffer.byteLength(body)});
  res.end(body);
}
function readBody(req, limit){
  return new Promise((resolve, reject)=>{
    let size = 0; const chunks = [];
    req.on('data', c => { size += c.length;
      if (size > limit){ reject(new Error('слишком большой файл')); req.destroy(); return; }
      chunks.push(c); });
    req.on('end', ()=> resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}
function dataUrlToBuffer(s, kinds){
  const m = /^data:(image\/[a-z+]+);base64,(.+)$/s.exec(String(s || ''));
  if (!m || !kinds.includes(m[1])) return null;
  return { mime: m[1], buf: Buffer.from(m[2], 'base64') };
}
const clientIp = req => (req.headers['x-forwarded-for'] || '').split(',')[0].trim() || req.socket.remoteAddress || '?';

/* лимит на монстриков: не чаще 20 в минуту с одного IP — ребёнок столько не нафоткает */
const monLog = new Map();
function canPost(ip){
  const t = now(), arr = (monLog.get(ip) || []).filter(x => t - x < 60e3);
  if (arr.length >= 20) return false;
  arr.push(t); monLog.set(ip, arr); return true;
}
setInterval(()=>{ const t = now(); for (const [k,v] of monLog) if (!v.some(x => t-x < 60e3)) monLog.delete(k); }, 300e3).unref();

/* Команды пульта (звук и прочее) считаем отдельно от рисунков: ребёнок,
   тыкающий в «Звук», не должен перекрыть себе отправку монстрика. */
const cmdLog = new Map();
function canCmd(ip){
  const t = now(), arr = (cmdLog.get(ip) || []).filter(x => t - x < 60e3);
  if (arr.length >= 60) return false;
  arr.push(t); cmdLog.set(ip, arr); return true;
}
setInterval(()=>{ const t = now(); for (const [k,v] of cmdLog) if (!v.some(x => t-x < 60e3)) cmdLog.delete(k); }, 300e3).unref();

/* простейший лимит: сколько миров создал один IP за час */
const createLog = new Map();
function canCreate(ip){
  const t = now(), arr = (createLog.get(ip) || []).filter(x => t - x < 3600e3);
  if (arr.length >= MAX_WORLDS_PER_IP_HOUR) return false;
  arr.push(t); createLog.set(ip, arr); return true;
}

/* ====================== живые экраны (SSE) ====================== */

const screens = new Map();            // code -> Set<res>
function broadcast(code, event, payload){
  const set = screens.get(code); if (!set) return 0;
  const data = `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
  let n = 0;
  for (const s of set){ try { s.write(data); n++; } catch(e){ set.delete(s); } }
  return n;
}

/* ===================== уборка старых миров ====================== */

function removeWorldFiles(code){
  try { fs.rmSync(path.join(DATA_DIR, 'monsters', code), { recursive: true, force: true }); } catch(e){}
  try { fs.rmSync(bgPath(code), { force: true }); } catch(e){}
}
function sweep(){
  const limit = now() - WORLD_IDLE_DAYS * 86400e3;
  for (const row of q.staleWorlds.all(limit)){
    q.delAllMon.run(row.code); q.delWorld.run(row.code); removeWorldFiles(row.code);
  }
}
setInterval(sweep, 6 * 3600e3).unref();
sweep();

/* ===================== демо-мир для витрины =====================
   Код DEMO1 — общий мир на главной: «посмотреть, как это выглядит».
   При старте, если он пуст, засеваем стартовыми монстриками из seed/.
   Ключа у него нет ни у кого — очистить его нельзя, а добавлять можно. */
const DEMO_CODE = 'DEMO1';
function seedDemo(){
  if (!q.getWorld.get(DEMO_CODE)){
    q.insWorld.run(DEMO_CODE, hash(crypto.randomBytes(16).toString('hex')), 'Общая планета', 'night', '', now(), now());
    fs.mkdirSync(path.join(DATA_DIR, 'monsters', DEMO_CODE), { recursive: true });
  }
  if (q.countMon.get(DEMO_CODE).n > 0) return;
  const seedDir = path.join(ROOT, 'seed');
  if (!fs.existsSync(seedDir)) return;
  fs.mkdirSync(path.join(DATA_DIR, 'monsters', DEMO_CODE), { recursive: true });   // папку могли снести при пересеве
  const names = ['Куки','Пух','Зюзя','Бублик','Тюша','Фрося','Шмяк','Лапа'];
  fs.readdirSync(seedDir).filter(f => f.endsWith('.png')).sort().forEach((f, i)=>{
    const id = randCode(10);
    fs.copyFileSync(path.join(seedDir, f), monPath(DEMO_CODE, id));
    q.insMon.run(id, DEMO_CODE, names[i % names.length], now() + i);
  });
}
seedDemo();
// демо-мир никогда не считается заброшенным
setInterval(()=> q.touch.run(now(), DEMO_CODE), 3600e3).unref();

/* ============================== API ============================== */

/* адреса сервера в локальной сети — нужны только когда экран открыт как
   localhost (домашний тест без домена): в QR нельзя класть localhost */
const SKIP_IFACE = /^(bridge|utun|awdl|llw|vmnet|docker|lo|gif|stf|ap\d)/i;
function lanUrls(){
  const out = [];
  for (const [name, addrs] of Object.entries(require('os').networkInterfaces())){
    if (SKIP_IFACE.test(name)) continue;
    for (const a of addrs || []){
      if (a.family !== 'IPv4' || a.internal) continue;
      out.push({iface:name, url:`http://${a.address}:${PORT}`});
    }
  }
  return out.sort((x,y)=> (y.url.includes('192.168.')?1:0) - (x.url.includes('192.168.')?1:0));
}

async function api(req, res, u){
  const p = u.pathname, ip = clientIp(req);
  const key = req.headers['x-world-key'] || '';

  if (p === '/api/lan') return json(res, 200, {lan: lanUrls()});

  // ---- создать мир ----
  if (p === '/api/worlds' && req.method === 'POST'){
    if (!canCreate(ip)) return json(res, 429, {error:'слишком много миров за час — попробуй позже'});
    let body = {};
    try { body = JSON.parse((await readBody(req, 64*1024)).toString('utf8') || '{}'); } catch(e){}
    const name  = String(body.name || '').slice(0, 40);
    const world = String(body.world || 'night').slice(0, 20);
    let code; for (let i=0;i<50;i++){ code = randCode(5); if (!q.getWorld.get(code)) break; }
    const secret = randCode(12);
    q.insWorld.run(code, hash(secret), name, world, '', now(), now());
    fs.mkdirSync(path.join(DATA_DIR, 'monsters', code), { recursive: true });
    return json(res, 200, {code, key: secret, name, world});
  }

  // всё остальное — про конкретный мир
  const m = /^\/api\/worlds\/([A-Za-z0-9]+)(\/[a-z]+)?(?:\/([A-Za-z0-9]+))?$/.exec(p);
  if (!m) return json(res, 404, {error:'нет такого адреса'});
  const code = safeCode(m[1]), sub = m[2] || '', id = safeId(m[3]);
  const w = q.getWorld.get(code);
  if (!w) return json(res, 404, {error:'мир не найден'});
  const isOwner = key && hash(key) === w.key_hash;
  const pub = ()=> ({code, name: w.name, world: w.world, motion: w.motion, hasBg: !!w.has_bg,
                     bgUrl: w.has_bg ? `/api/worlds/${code}/bg?v=${w.seen}` : null});

  // ---- информация о мире + список монстриков ----
  if (sub === '' && req.method === 'GET'){
    q.touch.run(now(), code);
    const list = q.listMon.all(code).map(r => ({id:r.id, name:r.name, url:`/api/worlds/${code}/monsters/${r.id}`}));
    return json(res, 200, Object.assign(pub(), {monsters: list, screens: (screens.get(code)||new Set()).size, owner: !!isOwner}));
  }

  // ---- проверка ключа ----
  if (sub === '/auth' && req.method === 'GET') return json(res, isOwner ? 200 : 403, {owner: !!isOwner});

  // ---- настройки: мир / движение / имя (владелец) ----
  if (sub === '' && req.method === 'PATCH'){
    if (!isOwner) return json(res, 403, {error:'нужен ключ владельца'});
    let body = {};
    try { body = JSON.parse((await readBody(req, 64*1024)).toString('utf8') || '{}'); } catch(e){}
    const world  = body.world  !== undefined ? String(body.world).slice(0,20)  : w.world;
    const motion = body.motion !== undefined ? String(body.motion).slice(0,10) : w.motion;
    const name   = body.name   !== undefined ? String(body.name).slice(0,40)   : w.name;
    let hasBg = w.has_bg;
    if (body.clearBg){ hasBg = 0; try { fs.rmSync(bgPath(code), {force:true}); } catch(e){} }
    q.setWorld.run(world, motion, hasBg, name, code);
    q.touch.run(now(), code);
    Object.assign(w, {world, motion, has_bg: hasBg, name, seen: now()});
    broadcast(code, 'world', pub());
    return json(res, 200, pub());
  }

  // ---- свой фон (владелец) ----
  if (sub === '/bg' && req.method === 'POST'){
    if (!isOwner) return json(res, 403, {error:'нужен ключ владельца'});
    let body;
    try { body = JSON.parse((await readBody(req, MAX_BODY)).toString('utf8')); } catch(e){ return json(res, 400, {error:'битые данные'}); }
    const img = dataUrlToBuffer(body.image, ['image/jpeg','image/png','image/webp']);
    if (!img) return json(res, 400, {error:'нужна картинка'});
    fs.writeFileSync(bgPath(code), img.buf);
    const motion = String(body.motion || w.motion || 'hop').slice(0,10);
    q.setWorld.run('custom', motion, 1, w.name, code); q.touch.run(now(), code);
    Object.assign(w, {world:'custom', motion, has_bg:1, seen: now()});
    broadcast(code, 'world', pub());
    return json(res, 200, pub());
  }
  if (sub === '/bg' && req.method === 'GET'){
    if (!w.has_bg) return json(res, 404, {error:'фона нет'});
    return sendFile(res, bgPath(code), 'image/jpeg', 'public, max-age=60');
  }

  // ---- монстрики ----
  if (sub === '/monsters' && req.method === 'POST'){
    if (!canPost(ip)) return json(res, 429, {error:'слишком часто — подожди минутку'});
    let body;
    try { body = JSON.parse((await readBody(req, MAX_BODY)).toString('utf8')); } catch(e){ return json(res, 400, {error:'битые данные'}); }
    const img = dataUrlToBuffer(body.png, ['image/png']);
    if (!img) return json(res, 400, {error:'нужен PNG'});
    const name = String(body.name || '').slice(0, 18);
    const mid = randCode(10);
    // место: вытесняем самых старых
    const n = q.countMon.get(code).n;
    if (n >= MAX_MONSTERS){
      for (const old of q.oldestMon.all(code, n - MAX_MONSTERS + 1)){
        q.delMon.run(old.id, code); try { fs.rmSync(monPath(code, old.id), {force:true}); } catch(e){}
        broadcast(code, 'remove', {id: old.id});
      }
    }
    fs.writeFileSync(monPath(code, mid), img.buf);
    q.insMon.run(mid, code, name, now()); q.touch.run(now(), code);
    const item = {id: mid, name, url:`/api/worlds/${code}/monsters/${mid}`};
    const delivered = broadcast(code, 'monster', item);
    return json(res, 200, Object.assign({delivered}, item));
  }
  if (sub === '/monsters' && req.method === 'GET' && id){
    return sendFile(res, monPath(code, id), 'image/png', 'public, max-age=31536000, immutable');
  }
  if (sub === '/monsters' && req.method === 'DELETE'){
    if (!isOwner) return json(res, 403, {error:'нужен ключ владельца'});
    if (id){
      q.delMon.run(id, code); try { fs.rmSync(monPath(code, id), {force:true}); } catch(e){}
      broadcast(code, 'remove', {id});
    } else {
      q.delAllMon.run(code);
      try { fs.rmSync(path.join(DATA_DIR,'monsters',code), {recursive:true, force:true}); } catch(e){}
      fs.mkdirSync(path.join(DATA_DIR, 'monsters', code), { recursive: true });
      broadcast(code, 'clear', {});
    }
    q.touch.run(now(), code);
    return json(res, 200, {ok:true});
  }

  // ---- команда с телефона-пульта на экран ----
  //  Телефон рядом с человеком, а телевизор — далеко: звук и прочие мелочи
  //  жмутся на телефоне, сюда приходит команда и уходит в поток экрана.
  if (sub === '/cmd' && req.method === 'POST'){
    if (!canCmd(ip)) return json(res, 429, {error:'слишком часто — подожди минутку'});
    let body = {};
    try { body = JSON.parse((await readBody(req, 4*1024)).toString('utf8') || '{}'); } catch(e){}
    const action = String(body.action || '');
    if (!['sound','music','wake'].includes(action)) return json(res, 400, {error:'неизвестная команда'});
    const delivered = broadcast(code, 'cmd', {action});
    q.touch.run(now(), code);
    return json(res, 200, {ok:true, delivered});
  }

  // ---- удалить мир целиком (владелец) ----
  if (sub === '' && req.method === 'DELETE'){
    if (!isOwner) return json(res, 403, {error:'нужен ключ владельца'});
    q.delAllMon.run(code); q.delWorld.run(code); removeWorldFiles(code);
    broadcast(code, 'gone', {});
    return json(res, 200, {ok:true});
  }

  // ---- поток событий на экран ----
  if (sub === '/events' && req.method === 'GET'){
    res.writeHead(200, {
      'Content-Type':'text/event-stream; charset=utf-8',
      'Cache-Control':'no-store, no-transform',
      'Connection':'keep-alive',
      'X-Accel-Buffering':'no',
    });
    res.write('retry: 3000\n\n');
    res.write(`event: hello\ndata: ${JSON.stringify(pub())}\n\n`);
    if (!screens.has(code)) screens.set(code, new Set());
    screens.get(code).add(res);
    q.touch.run(now(), code);
    const beat = setInterval(()=>{ try { res.write(': ping\n\n'); } catch(e){} }, 25000);
    const bye = ()=>{ clearInterval(beat); const s = screens.get(code); if (s){ s.delete(res); if (!s.size) screens.delete(code); } };
    req.on('close', bye); req.on('error', bye);
    return;
  }

  return json(res, 404, {error:'нет такого адреса'});
}

/* ============================ статика ============================ */

const MIME = {
  '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8',
  '.mjs':'text/javascript; charset=utf-8',
  '.css':'text/css; charset=utf-8',   '.json':'application/json; charset=utf-8',
  '.webmanifest':'application/manifest+json; charset=utf-8',
  '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.png':'image/png', '.webp':'image/webp',
  '.svg':'image/svg+xml', '.wasm':'application/wasm', '.ico':'image/x-icon',
  '.onnx':'application/octet-stream',
  '.md':'text/markdown; charset=utf-8', '.txt':'text/plain; charset=utf-8',
};
function sendFile(res, full, mime, cache){
  fs.stat(full, (err, st)=>{
    if (err || !st.isFile()){ res.writeHead(404, {'Content-Type':'text/plain; charset=utf-8'}); return res.end('нет такого файла'); }
    res.writeHead(200, {'Content-Type': mime, 'Content-Length': st.size, 'Cache-Control': cache});
    fs.createReadStream(full).pipe(res);
  });
}

/* Красивые адреса:  /            — главная (список миров)
                     /w/КОД       — экран мира (и одиночный режим на том же устройстве)
                     /w/КОД/add   — телефон: только съёмка и отправка          */
function serveStatic(req, res, u){
  let p = decodeURIComponent(u.pathname);
  if (p === '/' || p === '/index.html') p = '/index.html';
  else if (/^\/w\/[A-Za-z0-9]+(\/add)?\/?$/.test(p)) p = '/app.html';
  else if (p === '/app') p = '/app.html';
  else if (p === '/favicon.ico') p = '/icons/favicon.ico';
  const full = path.join(ROOT, p);
  if (!full.startsWith(ROOT)) { res.writeHead(403); return res.end(); }
  const ext = path.extname(full).toLowerCase();
  const cache = ext === '.html' ? 'no-cache'
              : p.endsWith('.json') ? 'no-cache'
              : (p.startsWith('/vendor/') || p.startsWith('/bg/') || p.startsWith('/icons/') || p.startsWith('/img/') || p.startsWith('/models/')) ? 'public, max-age=604800'
              : 'public, max-age=3600';
  sendFile(res, full, MIME[ext] || 'application/octet-stream', cache);
}

/* ============================== сервер ============================== */

const server = http.createServer((req, res)=>{
  const u = url.parse(req.url, true);
  if (u.pathname === '/health') return json(res, 200, {ok:true, screens:[...screens.values()].reduce((a,s)=>a+s.size,0)});
  if (u.pathname.startsWith('/api/')){
    api(req, res, u).catch(e => { console.error(e); try { json(res, 500, {error:'внутренняя ошибка'}); } catch(_){} });
    return;
  }
  serveStatic(req, res, u);
});

server.keepAliveTimeout = 65000;
server.listen(PORT, ()=>{
  const nets = require('os').networkInterfaces();
  const lan = Object.values(nets).flat().filter(n => n && n.family === 'IPv4' && !n.internal).map(n => n.address);
  console.log(`\n  WonderWorlds · данные в ${DATA_DIR}\n`);
  console.log(`  локально:      http://localhost:${PORT}`);
  for (const ip of lan) console.log(`  в этой сети:   http://${ip}:${PORT}`);
  console.log('');
});
