// Anything2Skill 分析後台（Cloudflare Worker + D1）
// POST /event  收匿名事件寫入 D1（嚴格驗證、擋垃圾）
// GET  /admin  Basic Auth 儀表板：總用戶、總 skill 數、每人幾份、來源類型分布、每日趨勢
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors() });
    if (request.method === 'POST' && url.pathname === '/event') {
      if (await limited(env.EVENT_LIMITER, ip)) return json({ ok: false, e: 'rate limited' }, 429);
      return handleEvent(request, env);
    }
    if (request.method === 'GET' && url.pathname === '/admin') {
      if (await limited(env.ADMIN_LIMITER, ip)) return new Response('Too many requests', { status: 429, headers: { 'Cache-Control': 'no-store' } });
      return handleAdmin(request, env);
    }
    return new Response('Not found', { status: 404 });
  }
};

// 依來源 IP 限流（Workers Rate Limiting 綁定）；綁定不存在時不擋，確保無設定也能運作
async function limited(limiter, key) {
  if (!limiter) return false;
  try { const { success } = await limiter.limit({ key }); return !success; }
  catch (_) { return false; }
}
function cors() {
  return { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'POST,OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type' };
}
function json(o, s = 200) { return new Response(JSON.stringify(o), { status: s, headers: { 'Content-Type': 'application/json', ...cors() } }); }

async function handleEvent(request, env) {
  // 事件酬載很小（幾百 bytes）。不能信任 client 的 Content-Length（chunked／HTTP-2 常無 CL frame → 可繞過），
  // 直接讀實際 bytes 設上限再解析，避免有人灌巨量 JSON 耗資源。
  let raw;
  try { raw = await request.text(); } catch { return json({ ok: false, e: 'bad body' }, 400); }
  // 先用字串長度便宜擋掉超大 body（UTF-16 units ≤ UTF-8 bytes，故 length>2048 必然超標），
  // 小 body 再精算實際 UTF-8 bytes，讓 CJK 等多位元組酬載也真的受 2048 bytes 限制。
  if (raw.length > 2048 || new TextEncoder().encode(raw).length > 2048) return json({ ok: false, e: 'too large' }, 413);
  let b;
  try { b = JSON.parse(raw); } catch { return json({ ok: false, e: 'bad json' }, 400); }
  // 裸 null／陣列／數字等合法但非物件的 JSON：後面讀 b.install_id 會拋 TypeError→平台 500，
  // 這裡先擋成 400，回可預期的驗證錯誤
  if (!b || typeof b !== 'object' || Array.isArray(b)) return json({ ok: false, e: 'bad json' }, 400);
  const install_id = String(b.install_id || '');
  if (!/^a2s_[a-f0-9]{8,40}$/.test(install_id)) return json({ ok: false, e: 'bad id' }, 400);
  const event = ['install', 'skills_done'].includes(b.event) ? b.event : null;
  if (!event) return json({ ok: false, e: 'bad event' }, 400);
  const note_count = Math.max(0, Math.min(100000, parseInt(b.note_count) || 0));
  // 伺服器端也強制媒體類別白名單（別只信任 client）：非清單內一律壓成 'other'，
  // 擋掉直接 POST 或改過的 client 把站台域名/課名塞進平台分布欄位。
  const ALLOWED_PLATFORMS = ['youtube', 'video', 'course', 'text', 'article', 'other'];
  const rawPlat = String(b.platform || '').toLowerCase().replace(/[^a-z0-9_.-]/g, '').slice(0, 32);
  const platform = ALLOWED_PLATFORMS.includes(rawPlat) ? rawPlat : 'other';
  const version = String(b.version || '').slice(0, 16).replace(/[^0-9a-z.\-]/gi, '');
  const ts = Math.min(Math.floor(Date.now() / 1000) + 86400, Math.max(0, parseInt(b.ts) || Math.floor(Date.now() / 1000)));
  try {
    await env.DB.prepare('INSERT INTO events (install_id,event,note_count,platform,version,ts,received_at) VALUES (?,?,?,?,?,?,?)')
      .bind(install_id, event, note_count, platform, version, ts, Math.floor(Date.now() / 1000)).run();
  } catch (e) { return json({ ok: false, e: 'db' }, 500); }
  return new Response(null, { status: 204, headers: cors() });
}

function unauthorized() {
  return new Response('Auth required', { status: 401, headers: { 'WWW-Authenticate': 'Basic realm="anything2skill admin"', 'Cache-Control': 'no-store' } });
}
// 常數時間字串比對：不因不匹配位置提早結束，避免用回應時間爆破密碼
function timingSafeEqualStr(a, b) {
  a = String(a); b = String(b);
  let diff = a.length ^ b.length;
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0;
}
async function handleAdmin(request, env) {
  const user = env.ADMIN_USER || 'admin';
  const key = env.ADMIN_KEY;
  if (!key) return new Response('後台未設定 ADMIN_KEY，請 wrangler secret put ADMIN_KEY', { status: 500, headers: { 'Cache-Control': 'no-store' } });

  // 三種進場方式：① 網址帶 ?k=<KEY>（一次性書籤連結，進來後種 cookie）② cookie（同瀏覽器之後免帶 k）③ 傳統 Basic Auth
  const url = new URL(request.url);
  const qKey = url.searchParams.get('k') || '';
  const cookie = request.headers.get('Cookie') || '';
  const cKey = (cookie.match(/(?:^|;\s*)a2s_admin=([^;]+)/) || [])[1] || '';
  let ok = false, setCookie = false;
  if (qKey && timingSafeEqualStr(qKey, key)) { ok = true; setCookie = true; }
  else if (cKey) {
    // decodeURIComponent 對畸形百分比編碼（如 cookie 'a2s_admin=%'）會丟 URIError；不接住會讓整個 handler 500。
    let dKey = ''; try { dKey = decodeURIComponent(cKey); } catch (_) { dKey = cKey; }
    if (timingSafeEqualStr(dKey, key)) ok = true;
  }
  else {
    const auth = request.headers.get('Authorization') || '';
    if (auth.startsWith('Basic ')) {
      try {
        const idx = auth.slice(6).length ? atob(auth.slice(6)) : '';
        const sep = idx.indexOf(':');
        const u = sep >= 0 ? idx.slice(0, sep) : idx;
        const p = sep >= 0 ? idx.slice(sep + 1) : '';
        ok = timingSafeEqualStr(u, user) && timingSafeEqualStr(p, key);
      } catch (_) {}
    }
    if (!ok) return unauthorized();
  }
  if (!ok) return unauthorized();

  // 憑 ?k= 進來 → 立刻 302 到乾淨 /admin 並種 cookie，避免密鑰殘留在網址列/瀏覽器歷史/proxy log。
  // 之後同瀏覽器帶 cookie 開 /admin 即免帶 k。
  if (setCookie) {
    return new Response(null, { status: 302, headers: {
      'Location': '/admin',
      'Set-Cookie': `a2s_admin=${encodeURIComponent(key)}; Path=/admin; HttpOnly; Secure; SameSite=Lax; Max-Age=43200`,
      'Cache-Control': 'no-store',
      'Referrer-Policy': 'no-referrer',
    } });
  }

  // DB 綁定缺失/誤名（部署漏設）時，env.DB.prepare 會拋 TypeError→平台 500；先擋成可讀的 503
  if (!env.DB || typeof env.DB.prepare !== 'function') {
    return new Response('analytics DB binding missing — run schema + set [[d1_databases]] binding "DB"', {
      status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' } });
  }
  const q = (sql) => env.DB.prepare(sql).all().then(r => r.results || []);
  const totals = (await q(`SELECT
      COUNT(DISTINCT install_id) users,
      COALESCE(SUM(CASE WHEN event='skills_done' THEN note_count END),0) notes,
      COUNT(CASE WHEN event='skills_done' THEN 1 END) runs
    FROM events`))[0] || { users: 0, notes: 0, runs: 0 };
  const perUser = await q(`SELECT install_id,
      COALESCE(SUM(CASE WHEN event='skills_done' THEN note_count END),0) notes,
      COUNT(CASE WHEN event='skills_done' THEN 1 END) runs,
      MAX(received_at) last FROM events GROUP BY install_id ORDER BY notes DESC LIMIT 100`);
  const plats = await q(`SELECT COALESCE(NULLIF(platform,''),'(未標)') platform,
      COUNT(*) hits, COALESCE(SUM(note_count),0) notes FROM events WHERE event='skills_done' GROUP BY 1 ORDER BY notes DESC`);
  const daily = await q(`SELECT date(received_at,'unixepoch') d,
      COUNT(DISTINCT install_id) users,
      COALESCE(SUM(CASE WHEN event='skills_done' THEN note_count END),0) notes
    FROM events GROUP BY d ORDER BY d DESC LIMIT 30`);

  // 走到這裡＝cookie 或 Basic Auth 進場（?k= 已在上方 302 攔掉），不再帶密鑰進網址
  const headers = { 'Content-Type': 'text/html;charset=utf-8', 'Cache-Control': 'no-store' };
  return new Response(renderDash({ totals, perUser, plats, daily }), { headers });
}

function esc(s) { return String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }
function fmtDate(ts) { if (!ts) return '-'; const d = new Date(ts * 1000); return d.toISOString().slice(0, 10); }
function renderDash({ totals, perUser, plats, daily }) {
  const maxNotes = Math.max(1, ...daily.map(d => d.notes));
  const dailyRows = daily.map(d => `<tr><td>${d.d}</td><td>${d.users}</td><td>${d.notes}</td>
    <td><div class="bar" style="width:${Math.round(d.notes / maxNotes * 100)}%"></div></td></tr>`).join('');
  const userRows = perUser.map(u => `<tr><td class="mono">${esc(u.install_id)}</td><td><b>${u.notes}</b></td><td>${u.runs}</td><td>${fmtDate(u.last)}</td></tr>`).join('') || '<tr><td colspan="4" class="muted">尚無資料</td></tr>';
  const platRows = plats.map(p => `<tr><td>${esc(p.platform)}</td><td>${p.hits}</td><td>${p.notes}</td></tr>`).join('') || '<tr><td colspan="3" class="muted">尚無資料</td></tr>';
  return `<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Anything2Skill 用量後台</title>
<style>
:root{--accent:#0091AC;--bg:#f6f8f9;--panel:#fff;--line:#e6eced;--muted:#6b7778}
body{margin:0;background:var(--bg);color:#26302f;font-family:"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif}
.hero{background:linear-gradient(135deg,#0091AC,#006d84);color:#fff;padding:28px 32px}
.hero h1{margin:0;font-size:20px}.hero p{margin:4px 0 0;opacity:.9;font-size:13px}
.wrap{max-width:960px;margin:0 auto;padding:20px 24px 60px}
.cards{display:flex;gap:16px;margin:20px 0}
.card{flex:1;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 20px}
.card .n{font-size:30px;font-weight:800;color:var(--accent)}.card .l{color:var(--muted);font-size:13px;margin-top:4px}
h2{font-size:15px;margin:26px 0 10px}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:13.5px}
th{background:#eaf3f5;text-align:left;padding:9px 12px;font-weight:700}
td{padding:8px 12px;border-top:1px solid var(--line);vertical-align:middle}
.mono{font-family:Consolas,monospace;font-size:12px;color:#555}
.muted{color:var(--muted)}.bar{height:10px;background:var(--accent);border-radius:5px;min-width:2px}
</style></head><body>
<div class="hero"><h1>📊 Anything2Skill 用量後台</h1><p>匿名使用計數 · 只有數字、不含任何內容</p></div>
<div class="wrap">
  <div class="cards">
    <div class="card"><div class="n">${totals.users}</div><div class="l">使用者（不重複安裝碼）</div></div>
    <div class="card"><div class="n">${totals.notes}</div><div class="l">總產出 skill 數</div></div>
    <div class="card"><div class="n">${totals.runs}</div><div class="l">完成次數</div></div>
  </div>
  <h2>每日趨勢（近 30 天）</h2>
  <table><thead><tr><th>日期</th><th>活躍用戶</th><th>skill 數</th><th style="width:40%">量</th></tr></thead><tbody>${dailyRows || '<tr><td colspan=4 class=muted>尚無資料</td></tr>'}</tbody></table>
  <h2>來源類型分布</h2>
  <table><thead><tr><th>來源類型</th><th>事件數</th><th>skill 數</th></tr></thead><tbody>${platRows}</tbody></table>
  <h2>每位使用者產出（Top 100）</h2>
  <table><thead><tr><th>匿名安裝碼</th><th>skill 數</th><th>完成次數</th><th>最後活動</th></tr></thead><tbody>${userRows}</tbody></table>
</div></body></html>`;
}
