# anything2skill

**The courses you took, the videos piling up — let AI turn them into skills that actually land.**

Those methods you learned but never really put to use — videos, courses, articles, transcripts — anything2skill distills them into an agent-callable skill (`SKILL.md`), so your AI then does the work **that way, every time** — not its own generic default. Built for people already using (or just starting with) **Claude Code**.

**English** · [中文](#中文-anything2skill) &nbsp;|&nbsp; License: MIT · Author: Dr. Yu-Chieh Chen

> **Honest by design:** it never claims to make your AI "smarter" (we disproved that ourselves). It makes your AI **faithful and consistent** to a method you trust. New skills land **inert** in a local vault and only activate after you review a one-screen card and explicitly confirm.

## What it does

- **Distill**: video (auto download + transcribe), article, transcript, course → a structured skill (steps / checklist / guardrails / verbatim anchors).
- **Value pre-check + honest label**: before distilling, it tells you where the value comes from — "knowledge an LLM can't generate," or "an LLM knows this too, but it saves you knowing what to ask + gives you consistency." **Only genuinely framework-less chit-chat gets talked out of.** A useful framework is kept even if it's generic — just honestly labeled so you choose.
- **Anti-bloat fusion**: new content is compared against your existing skill library first — the same teacher told more fully gets **merged deeper**; the **same framework across domains** (coffee quadrants vs. tea quadrants) is **factored into "one framework + per-domain examples"** instead of piling up near-duplicates; rival schools coexist, kept separate; a real conflict pauses for you to choose. **And fusion only ever touches skills it distilled (tagged `x-anything2skill`) — it never reads, merges, or modifies your own hand-made skills.** Your library stays clean after a year.

## What we don't claim (honesty statement)

**We do not claim "install a skill and the AI gets smarter."** We ran our own blind test: for general methodology, a *person who asks good questions* gets about the same answer with or without the skill — modern LLMs already know that stuff.

So where's the value? In the fact that **most people don't have the time or the clarity to ask the good question**. A skill buys you three things:
1. **The "knowing what to ask" is done for you** — the expert's framing and structure are handed to you directly.
2. **Faithful**: when you say "do it that way," the AI actually does — steps, ratios, even the "don't do X" guardrails (blind-rated faithfulness at a 9:2 margin).
3. **Consistent**: repeat the task and the structure holds — instead of the AI's own default opinion that may quietly contradict the method you trust.

## Install (pick one path)

**Path A — plugin install (recommended: two commands, the distiller subagent auto-loads)**
In Claude Code, type:
```
/plugin marketplace add Nouischen/anything2skill
/plugin install anything2skill@anything2skill
```
Restart Claude Code once, then say "distill this video into a skill."

**Path B — skill-folder install**
```
git clone https://github.com/Nouischen/anything2skill.git
```
1. Put the folder in your Claude Code skills directory (e.g. `~/.claude/skills/anything2skill`).
2. **Copy `agents/a2s-distiller.md` into `~/.claude/agents/`** (once) — this is the bundled Sonnet distiller subagent that makes "layered token saving" work; you can skip it (the skill has a fallback) but layering is less reliable (the plugin path auto-loads it).
3. Restart Claude Code once, then say "distill this video into a skill."

**Requirements**: desktop; **Claude Code itself needs a paid Claude plan (Pro and up)** — that's Anthropic's subscription, separate from this tool, which is free and open-source; distilling consumes your plan's usage (∝ content length; it estimates before starting). Also: Python 3.10–3.13 (**3.12 recommended** — local-GPU faster-whisper may lack a prebuilt wheel on the newest versions; drop to 3.12 or use API transcription), ffmpeg, yt-dlp (video download; run `pip install -r scripts/requirements.txt` **inside the installed package dir**, `pip3` on Mac/Linux), Node.js (telemetry script). Free local transcription needs an NVIDIA GPU (Windows/Linux, `requirements-gpu.txt`) or Apple Silicon (Mac, `requirements-mac.txt`); with neither, the OpenAI Whisper API works (`requirements-api.txt`, bring your own key, ~US$0.006/min, audio uploaded to OpenAI). **For plain text / transcripts, Python/ffmpeg/yt-dlp mostly aren't needed.**

**Model & cost — spend where it matters**: the token-heavy "re-read tens of thousands of words + draft" is auto-dispatched to the bundled **Sonnet subagent** (cheap); only the small-token, high-judgment fusion runs on your main model. So **Opus or above is recommended for the main model** (better fusion judgment), though Sonnet works too (tested — it holds the core judgment, just a bit less sharp). Long content auto-chunks; cost is estimated up front.

## Telemetry disclosure

By default it reports **anonymous usage counts**: an install code (randomly generated, not a hardware ID), event, skill count, source type (youtube/text/course…), version, timestamp. It **never** sends content, titles, URLs, or any personal data. **The package ships with the author's stats endpoint pre-filled** (`config.example.json`, counts only), so it reports out of the box; turn it off in one line: `ANYTHING2SKILL_TELEMETRY=off` (or set `"telemetry": false` in config.json). Self-host or clear the endpoint and nothing is reported.

## 🔒 Security model (please read)

A distilled skill **is executable agent instructions**, and its content comes from the source you feed it. That means **a malicious source could disguise an instruction as a normal-looking method rule**, and the tool can't guarantee it separates that from a genuine method. So this tool is designed so that **trust is granted by you, not automatically by the tool**:

- **Only distill sources you trust** (teachers you follow, courses you bought, your own notes) — just as you wouldn't run a random script off the internet.
- **A newly distilled skill carries `disable-model-invocation: true` by default** (Claude Code's official field — Claude won't auto-trigger it) and lives in the vault (outside `.claude/skills/`) — doubly inert.
- **Enabling = you reviewed it and explicitly confirmed, then the agent does it**: it shows a one-screen **review card** (what it does / steps / guardrails / verbatim anchors / risk notes, expand for full text); you say "enable" for that one skill; only then does it **copy** the skill into `~/.claude/skills/` (**your master always stays in the vault**, so every step is rollback-able and deleting the active copy never loses the method), remove the `disable-model-invocation: true` line on the copy, and mark it active in the library index. Nothing is enabled without your confirmation. Anytime, say "**my method library**" to see what you own, which to use, what's pending; say "**deactivate / delete <name>**" when done (both rollback-able); say "**remove anything2skill**" to uninstall the whole tool (your vault library is kept by default; steps in SKILL.md's exit section).
- **Any update to an existing skill of yours is previewed first** — it applies only when you say so; it won't quietly change what you trust.

In one line: this tool **produces** your method library, but the **key to enabling** stays in your hands.

**Optional strict mode (hook)**: a PreToolUse hook is included (`hooks/guard-activation.py`). Installing it = you choose "**the copy into the active folder is always done by hand**": even the agent-performed copy step of a confirmed activation is blocked (expected behavior — it then gives you exact steps and opens the folder for you; the vault-side index mark is still done for you), so this tool's own distilled skills can't reach the auto-trigger path without your hand — even if the distilling AI errs. For higher-risk sources, or if you just want the strictest posture; the default flow (review card + explicit confirm) is safe without it. Setup in [hooks/README.md](hooks/README.md). ⚠️ **It is not a wall against malicious sources**: an AI hijacked on the spot can skip the marker or write files via Bash to bypass it (we red-teamed this over four rounds). The one real defense against malicious sources is still the line above — **only distill sources you trust, and look before you enable.**

## ⚠️ Two important notes

- **Faithful method ≠ compliant**: this tool only faithfully reproduces the original method. In medicine, law, finance, etc., the method itself may not carry your jurisdiction's regulatory requirements — add the compliance layer yourself (distilled skills auto-append this caveat).
- **Copyright & DRM**: use it on content **you legally obtained**, for personal use. This tool **does not bypass DRM or encryption** — protected content (encrypted streams, ebook DRM, etc.) is skipped and reported, and it never recommends cracking tools. A distilled skill contains the essence of the original method; confirm the author's license before sharing publicly.

## Credits & license

- The distillation idea is inspired by [cangjie-skill](https://github.com/kangarooking/cangjie-skill) (MIT); this tool's differentiator is the value pre-check and the fusion protocol.
- The content-extraction pipeline builds on the sister project [course2notes](https://github.com/Nouischen/course2notes) (same author, free & open-source); for paid-course platforms, use it first to get a transcript (the course folder's `transcript/` is then a ready source), then feed that back here.
- License: [MIT](LICENSE)

## Roadmap

- Phase 2: fact-checking module (Crossref/DOI, academic claims marked verified), book/PDF parsing, landing page & setup wizard.

---

# 中文 anything2skill

**上過的課、囤著的影片，讓 AI 幫你變成落地的技能。**

那些你學過、卻一直沒真的用起來的方法——影片、課程、文章、逐字稿都行——anything2skill 把它蒸餾成 agent 可調用的 skill（`SKILL.md`），讓你的 AI 之後**照那套方法**幫你做事、每次一致——不是它自己的預設做法。給已經在用（或正要開始用）**Claude Code** 的你。

> **誠實設計**：它從不宣稱讓 AI「變聰明」（我們自己證偽過），只讓 AI**忠實還原、每次一致**於一套你信任的方法。新蒸的 skill 先**不生效**躺在本機 vault，看過一屏審核卡、你明確點頭才啟用。

## 它做什麼

- **蒸餾**：影片（自動下載＋轉錄）、文章、逐字稿、課程 → 結構化 skill（步驟／檢核表／禁區／原話錨點）。
- **價值預檢＋誠實標籤**：蒸之前先告訴你這套框架的價值來源——是「LLM 生不出來的新知識」，還是「LLM 也會、但省你不知道怎麼問＋每次一致」。**只有真正沒框架的純閒聊才勸退**；有用的框架就算通用也留給你，只是老實貼標籤讓你自己選。
- **融合防通膨**：新內容進來先跟你既有的 skill 庫比對——同一位老師的方法越講越完整就**併進去深化**；**同一套框架套在不同產業（咖啡四象限 vs 茶葉四象限）會抽成「一個框架＋多領域範例」而不是堆一堆近重複**；不同派系的方法並存分流、絕不攪拌；真有衝突（A 派台上報價、B 派台下談）會停下來讓你選。**而且融合只動它自己蒸的 skill（帶 `x-anything2skill` 標記的）——永遠不會讀、不會併、更不會改你原本手作的 skill。**你的 skill 庫用一年還是乾淨的。

## 我們不宣稱什麼（誠實聲明）

**我們不宣稱「裝了 skill，AI 會變聰明」。** 我們自己做過盲測：對於通用方法論，*一個很會問問題的人* 帶不帶 skill，答案品質差不多——現代 LLM 本來就會那些。

那 skill 的價值在哪？在於**大部分人沒空、也沒那個清晰度把好問題問出來**。skill 幫你買到三件事：
1. **省下「知道怎麼問」的功夫**：把專家的提問框架與結構直接給你，你不用自己摸索該問什麼、答案該長怎樣。
2. **忠實**：你說「照那套方法做」時，AI 真的照那套做——步驟、比例、連「不要做什麼」的禁區都守住（盲評忠實度 9:2 級距）。
3. **一致**：同樣任務重複問，結構穩定不漂移；沒有 skill 的 AI 每次給你的是它自己的預設意見，可能安靜地跟你認同的方法相反。

## 安裝（兩條路擇一）

**方式 A：plugin 安裝（推薦——兩條指令，蒸餾子代理自動載入）**
在 Claude Code 裡輸入：
```
/plugin marketplace add Nouischen/anything2skill
/plugin install anything2skill@anything2skill
```
重開 Claude Code 一次，對它說「把這個影片蒸成 skill」即可。

**方式 B：skill 資料夾安裝**
```
git clone https://github.com/Nouischen/anything2skill.git
```
1. 把資料夾放進你的 Claude Code skills 目錄（如 `~/.claude/skills/anything2skill`）。
2. **把 `agents/a2s-distiller.md` 複製到 `~/.claude/agents/`**（一次就好）——這是隨包的 Sonnet 蒸餾子代理，「分層省 token」靠它；跳過這步也能跑（skill 內建 fallback），但分層會不穩（plugin 安裝則自動載入、免這步）。
3. 重開 Claude Code 一次，對它說「把這個影片蒸成 skill」即可。

需求：桌機、**Claude Code 本體需要 Claude 付費方案（Pro 起）**——那是 Anthropic 的訂閱費，與本工具無關、本工具免費開源；蒸餾會消耗你方案的用量（量 ∝ 內容長度，開跑前會先估給你看）。其他：Python 3.10–3.13（**建議 3.12**——本機 GPU 轉錄用的 faster-whisper 對最新版可能尚無預編譯 wheel，裝不起來就改用 3.12 的直譯器/虛擬環境、或改走 API 轉錄）、ffmpeg、yt-dlp（影片下載；在**安裝好的技能包目錄裡**跑 `pip install -r scripts/requirements.txt`，Mac/Linux 用 `pip3`）、Node.js（跑遙測腳本）；本機免費轉錄需 NVIDIA GPU（Windows/Linux，`requirements-gpu.txt`）或 Apple Silicon（Mac，`requirements-mac.txt`），都沒有可用 OpenAI Whisper API（`requirements-api.txt`，自備 key，約 US$0.006/分鐘，音檔會上傳 OpenAI）。**只蒸純文字／逐字稿時，Python/ffmpeg/yt-dlp 多數用不到。**

**模型與成本：省在刀口上。** 最花 token 的「重讀幾萬字逐字稿＋起草」會自動派給隨包附的 **Sonnet 子代理**（便宜）；只有小 token、高判斷的融合決定跑在你的主模型上。所以**建議主模型用 Opus 以上求穩**（融合判斷品質更好），但主模型設 Sonnet 也能跑——實測 Sonnet 也扛得住核心判斷，只是稍打折。長內容自動分塊、開跑前先估成本告知你。

## 遙測揭露

預設回報**匿名使用計數**：安裝碼（隨機生成，非硬體識別）、事件、skill 數、來源類型（youtube/text/course…）、版本、時間。**絕不回傳**內容、標題、網址、任何個資。**本包出廠已預填作者的統計端點**（`config.example.json`，只收上述計數），所以開箱預設會回報；一句話即可關閉：`ANYTHING2SKILL_TELEMETRY=off`（或 config.json 設 `"telemetry": false`）。自架或清空端點自然不回報。

## 🔒 安全模型（請務必讀）

蒸出來的 skill **是可執行的 agent 指令**，內容來自你餵的來源。這代表：**一個惡意來源可以把指令偽裝成一條看起來正常的方法規則**，而工具無法保證能把它和真正的方法分開。所以本工具的設計是「**信任由你賦予，不由工具自動賦予**」：

- **只蒸你信任的來源**（你認同的老師、你買的課、你自己的筆記）——就像你不會隨便執行網路上撿來的腳本。
- **新蒸的 skill 預設帶 `disable-model-invocation: true`**（Claude Code 官方欄位，Claude 不會自動觸發它），且住在 vault（`.claude/skills/` 之外）——雙重不生效。
- **啟用＝你看過＋你明確點頭，然後由 agent 代辦**：它先給你一張一屏的**審核卡**（這顆做什麼／步驟／禁區／原話錨點／風險註記，想看全文再展開），你對這顆明確說「啟用」，它才把 skill **複製**一份進 `~/.claude/skills/`（**你的正本永遠留在 vault**，所以每步可回滾、刪掉生效那份也不會遺失方法）＋刪掉生效那份的 `disable-model-invocation: true` 行＋在方法庫索引標記為已啟用。沒經過你的確認，agent 不會啟用任何東西。之後隨時說「**我的方法庫**」就能看你擁有哪些方法、要用哪顆、哪顆待啟用；不要了就說「**停用/刪除〈名稱〉**」（都可回滾）；要卸載整個工具，說「**移除 anything2skill**」即可（你的 vault 方法庫預設保留，步驟見 SKILL.md 退場節）。
- **任何要改動你既有 skill 的更新，都會先給你預覽**，你點頭才套用——不會偷改你信任的東西。

一句話：這工具幫你**產出**方法庫，但**啟用**的鑰匙一直在你手上。

**選配嚴格模式（hook）**：附了一支 PreToolUse hook（`hooks/guard-activation.py`）。裝上它＝你選擇「**複製進生效目錄一律親手做**」：agent 連「經你確認後代辦啟用」的複製那步也會被擋下（屬預期行為，此時它會給你精確步驟並幫你開資料夾，vault 側的索引標記仍會代辦），本工具自家蒸出的 skill 沒有你的手就進不了自動觸發路徑——就算蒸餾的 AI 犯錯也一樣。適合蒸較高風險來源、或單純想要最嚴格姿態的人；預設流程（審核卡＋明確確認）不裝也安全。啟用方式見 [hooks/README.md](hooks/README.md)。⚠️ **它不是防惡意來源的牆**：被當場挾持的 AI 可以不蓋標記、或改用 Bash 寫檔繞過它（我們四輪紅隊確認過）。防惡意來源的唯一真防線，還是上面那句——**只蒸你信任的來源＋啟用前你自己看一眼**。

## ⚠️ 兩個重要提醒

- **方法忠實 ≠ 合規**：本工具只忠實還原原方法。醫療、法律、財務等領域，方法本身可能不含你執業地區的法規要求——合規層請自行疊加（蒸出的 skill 會自動附這條警語）。
- **版權與 DRM**：請用於處理**你自己合法取得**的內容、供個人使用。本工具**不繞過 DRM 或加密保護**——偵測到受保護內容（加密串流、電子書 DRM 等）會直接跳過並告知，也不會推薦破解工具。蒸出的 skill 含原方法精華，公開分享前請確認原作者授權。

## 致謝與授權

- 蒸餾理念受 [cangjie-skill](https://github.com/kangarooking/cangjie-skill)（MIT）啟發；本工具的差異化在價值預檢與融合協議。
- 內容擷取管線基於姊妹專案 [course2notes](https://github.com/Nouischen/course2notes)（同作者、免費開源）；付費課程平台先用它拿逐字稿（跑完後課程資料夾裡的 `transcript/` 就是現成來源），再回來餵本工具。
- License: [MIT](LICENSE)

## Roadmap（藍圖）

- Phase 2：事實查證模組（Crossref/DOI，學術內容主張標 verified）、書籍/PDF 解析、落地頁與設定精靈。
