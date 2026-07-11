// 匿名使用計數回報。只送：匿名安裝碼、事件、筆記數、平台類型、版本、時間。
// 絕不送內容/課名/網址/個資。可用 ANYTHING2SKILL_TELEMETRY=off 或 config.telemetry=false 關閉。
// 用法：node telemetry.js <event> [skillCount] [sourceType]
//   event = install | skills_done
const fs = require('fs');
const os = require('os');
const path = require('path');
const https = require('https');
const http = require('http');
const crypto = require('crypto');

// 只允許回傳「媒體類別」，不接受站台域名／課名等自由字串（配合後台白名單）
const ALLOWED_PLATFORMS = ['youtube', 'video', 'course', 'text', 'article', 'other'];

const VERSION = '1.0.3';
const HOME = path.join(os.homedir(), '.anything2skill');
const IDFILE = path.join(HOME, 'install_id');
const CONSENT = path.join(HOME, 'consent_shown');
const INSTALL_SENT = path.join(HOME, 'install_reported');

function loadConfig() {
  // config 檔在專案根目錄；也容忍放在 scripts/ 旁邊。
  // 迴圈順序＝先找遍兩處的 config.json、再退回 config.example.json——
  // 出廠必附根目錄 example，若先按目錄找，scripts/config.json 永遠輪不到（使用者 opt-out 會失效）。
  for (const p of ['config.json', 'config.example.json']) {
    for (const dir of [path.join(__dirname, '..'), __dirname]) {
      let txt;
      try { txt = fs.readFileSync(path.join(dir, p), 'utf8'); } catch (_) { continue; } // 檔不存在→試下一個
      try {
        const parsed = JSON.parse(txt);
        // 只接受真正的物件：裸 null／陣列／數字／字串等合法但非物件的 JSON 一律當「沒設定」（回 {}），
        // 否則下游 cfg.telemetry／cfg.telemetryEndpoint 會對 null 拋 TypeError（每次呼叫都炸）
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed;
        console.warn('[telemetry] ' + p + ' 不是 JSON 物件，忽略。');
        return {};
      }
      catch (_) {
        // 檔在但 JSON 壞掉：若是使用者自己的 config.json（非 example），把壞掉的 opt-out 當 opt-out（fail-safe），
        // 別靜默改用 example（telemetry:true）把遙測重新打開。
        if (p === 'config.json') {
          console.warn('[telemetry] config.json 解析失敗，為安全起見視為關閉遙測（請修正 JSON 或明確設 "telemetry": false）。');
          return { telemetry: false };
        }
      }
    }
  }
  return {};
}
function disabled(cfg) {
  if ((process.env.ANYTHING2SKILL_TELEMETRY || '').toLowerCase() === 'off') return true;
  if (cfg.telemetry === false) return true;
  return false;
}
// 隨機匿名安裝碼（非硬體識別、無個資）
function installId() {
  fs.mkdirSync(HOME, { recursive: true });
  try { const id = fs.readFileSync(IDFILE, 'utf8').trim(); if (id) return id; } catch (_) {}
  const id = 'a2s_' + crypto.randomBytes(8).toString('hex');
  fs.writeFileSync(IDFILE, id);
  return id;
}
function showConsentOnce() {
  if (fs.existsSync(CONSENT)) return;
  fs.mkdirSync(HOME, { recursive: true });
  console.log('\nℹ️  Anything2Skill 會回傳「匿名使用計數」（只有：安裝碼/事件/skill 數/來源類型/版本/時間，不含任何內容或個資）。');
  console.log('   關閉方式：設定環境變數 ANYTHING2SKILL_TELEMETRY=off，或在 config.json 設 "telemetry": false。\n');
  try { fs.writeFileSync(CONSENT, '1'); } catch (_) {}
}

function report(event, noteCount, platform) {
  const cfg = loadConfig();
  if (disabled(cfg)) { console.log('[telemetry] 已關閉，未回報。'); return; }
  try {
  showConsentOnce();
  // install 事件真正冪等：每台機器只送一次（否則每個 session 呼叫都灌水作者端 install 數）
  if (event === 'install' && fs.existsSync(INSTALL_SENT)) { console.log('[telemetry] install 已回報過，略過。'); return; }
  const ep = cfg.telemetryEndpoint;
  if (!ep || /REPLACE-ME/.test(ep)) { console.log('[telemetry] 未設定 endpoint，略過。'); return; }
  const plat = ALLOWED_PLATFORMS.includes(String(platform || '').toLowerCase())
    ? String(platform).toLowerCase() : 'other';
  const payload = JSON.stringify({
    install_id: installId(),
    event: event || 'unknown',
    note_count: Number(noteCount) || 0,
    platform: plat,
    version: VERSION,
    ts: Math.floor(Date.now() / 1000)
  });
  try {
    const u = new URL(ep);
    // 依 endpoint 的協定選 http/https，並帶上自訂埠（否則自訂埠會被忽略、退回 443，本機/自架端點連不上）
    const transport = u.protocol === 'http:' ? http : https;
    const req = transport.request({ hostname: u.hostname, port: u.port || undefined, path: u.pathname, method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) }, timeout: 4000 },
      res => { res.on('data', () => {}); res.on('end', () => {
        // install 哨兵只在「伺服器確實收下（2xx）」後才落檔——送出前就落會在 POST 失敗時永久漏記這台的 install
        if (event === 'install' && res.statusCode >= 200 && res.statusCode < 300) {
          try { fs.mkdirSync(HOME, { recursive: true }); fs.writeFileSync(INSTALL_SENT, '1'); } catch (_) {}
        }
      }); });
    req.on('error', () => {}); req.on('timeout', () => req.destroy());
    req.write(payload); req.end();
  } catch (_) { /* 回報失敗絕不影響主流程 */ }
  } catch (_) { /* HOME 不可寫等 FS 錯誤：遙測是附屬功能，絕不讓它中斷主流程 */ }
}

if (require.main === module) {
  report(process.argv[2], process.argv[3], process.argv[4]);
}
module.exports = { report };
