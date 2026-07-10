# anything2skill 安全 hook（選配加固，v5）

## 老實說它能做什麼、不能做什麼（先讀這段）
`guard-activation.py` 是一支 Claude Code **PreToolUse hook**，跑在 agent 之外。它的**真實承諾很窄，但誠實**：

- ✅ **能做（safe-by-default）**：讓本工具**自家蒸出**的 skill，不會被 agent 自己裝進「會自動觸發」的路徑（`.claude/skills/`）——**就算蒸餾的 agent 犯了錯**，你的 skill 也是「先躺在 vault、等你人審、你親手複製進去才生效」（複製、不搬移——vault 永遠留正本）。這對正常使用流程是實在的防呆。
- ❌ **不能做**：它**不是**防「被惡意來源挾持的 agent」的牆。那種 agent 大可**不蓋本工具的標記**（就寫一個不帶 `x-anything2skill` 的惡意 skill），或**改用 Bash 重導向**寫檔——兩條都繞過本 hook。這是經四輪紅隊確認的事實，不迴避。

> **防惡意來源的唯一真防線是「只蒸你信任的來源＋啟用前人審」，不是這支 hook。** 這跟你不會隨便執行網路上撿來的腳本是同一個道理。這支 hook 是「信任來源」姿態之上的**防呆加固**，不是安全保證。

## 怎麼運作
Claude Code 只自動觸發放在 `.claude/skills/` 裡的 skill。本工具的 skill 平常住在 **vault**（那路徑之外＝天生不會被自動觸發）。hook 守位置這道門，**不解析檔案內容**（v1–v3 解析 frontmatter 的版本被紅隊三度攻破——hook 的 parser 追不上 Claude Code 真正那顆載入器；v4/v5 改守位置，跳出那場軍備競賽）：
- ❌ 擋：agent 把**帶 `x-anything2skill` 標記的檔案** Write/Edit/MultiEdit 進 `.claude/skills/`。
- ✅ 放行：寫進 vault、你自己的其他 skill、非本工具的檔。
- 路徑正規化（v5）：解 `..`／`//`／尾端點／NTFS ADS／8.3 短名（realpath），擋常見混淆——但**路徑正規化是無底洞、best-effort**，決心繞的攻擊者仍有 Bash 等路（見上）。

**裝這支 hook ＝ 選擇「嚴格模式」**：預設流程裡（沒裝 hook），agent 會在「出示審核卡＋你明確說啟用」之後**代辦**啟用的四動作交易（複製啟用制）：**複製**進 `.claude/skills/`（vault 留正本）＋刪生效目錄那份的 `disable-model-invocation: true` 行＋INDEX 翻✅＋commit。裝了 hook，其中「寫進 `.claude/skills/`」那步（複製）會被擋下——**屬預期行為，不是 bug**：此時**你本人**手動做①複製 vault 的 `skills/<name>/` 進 `.claude/skills/`（複製、別搬移——vault 要留正本）②刪生效那份的 disable 行；agent 會**先**給你精確路徑、幫你開資料夾（macOS 的 `~/.claude` 在 Finder 預設隱藏），**等你回覆做完、它驗證生效那份就緒（檔案在、disable 行已刪）之後**，才代做 vault 側的 INDEX 翻轉＋commit（不受 hook 影響）——你沒做完，索引不會先說「已啟用」。要不要裝，取決於你要「順手」還是「最嚴格」。

## 前提
你的 **vault 必須在 `.claude/skills/` 之外**（預設 `~/skill-vault` 就是）。若把 vault 設成 `.claude/skills/`，正常蒸餾寫入會被擋。

## 怎麼啟用
`~/.claude/settings.json` 的 `hooks.PreToolUse` 陣列加一個物件——**Windows 用 `python`、macOS/Linux 用 `python3`**（macOS 預設沒有 `python` 這個指令，照抄 Windows 版＝hook 根本沒上工、你還以為自己開了嚴格模式）：

Windows：
```json
{ "matcher": "Write|Edit|MultiEdit",
  "hooks": [ { "type": "command", "command": "python \"<你的路徑>/anything2skill/hooks/guard-activation.py\"" } ] }
```
macOS / Linux：
```json
{ "matcher": "Write|Edit|MultiEdit",
  "hooks": [ { "type": "command", "command": "python3 \"<你的路徑>/anything2skill/hooks/guard-activation.py\"" } ] }
```
改完重開 Claude Code。停用＝移除。純標準庫、不寫檔、不連網。

**裝完自驗（30 秒，別跳過）**：重開後叫 agent「寫一個測試檔到 `~/.claude/skills/hook-test/SKILL.md`，內容含一行 `x-anything2skill: v1`」——**被擋下＝hook 上工了**（然後請它清掉測試殘留）；沒被擋＝檢查 `python`/`python3` 指令名與腳本路徑是否正確。
