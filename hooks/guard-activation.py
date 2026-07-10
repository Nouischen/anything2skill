#!/usr/bin/env python3
"""anything2skill 的 PreToolUse 安全 hook（v5，位置式，不解析內容）。

⚠️ 這支 hook 的承諾要誠實看待（v1~v4 被四位獨立紅隊各破一次後定調）：
  **它做的是「safe-by-default」——讓本工具『自家蒸出』的 skill 不會被 agent 自己裝進會自動
  觸發的路徑，未經你人審前不生效；就算蒸餾的 agent 犯錯也一樣。**
  它**不是**防「被惡意來源挾持的 agent」的牆——那種 agent 大可不蓋本工具的標記、或改用 Bash
  重導向寫檔，就繞過本 hook。**防惡意來源的唯一真防線是「只蒸你信任的來源＋啟用前人審」，不是這支 hook。**

機制：Claude Code 只自動發現/觸發放在 `.claude/skills/` 裡的 skill；本工具的 skill 平常住在 vault
（那路徑之外＝天生 inert）。規則＝**agent 不准把帶 `x-anything2skill` 標記的檔案寫/改進 `.claude/skills/`**。
啟用＝使用者本人手動把審過的 skill **複製**進去（複製、不搬移——vault 留正本；人的動作、不經工具、不觸發本 hook）。

只認帶標記的自家產物（不干擾使用者其他 skill）——這對「safe-by-default 自家流程」是對的範圍；
但也正因如此，它擋不住「刻意不蓋標記的惡意 skill」，那本就在承諾外（見上）。
只攔 Write/Edit/MultiEdit，不攔 Bash 重導向。前提：vault 必須在 `.claude/skills/` 之外。

Windows 安全：UTF-8 讀 stdin、輸出純 ASCII JSON。阻擋＝permissionDecision:"deny"，exit 0。
"""
import sys
import os
import json
import re

MARKER = "x-anything2skill"          # 大小寫無關比對
# discovered skills 路徑：使用者級 ~/.claude/skills/ 與專案級 .claude/skills/ 都涵蓋
_SKILLS_DIR = re.compile(r"(?:^|/)\.claude/skills/")


def _deny(reason):
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(out))  # ensure_ascii=True -> 純 ASCII


def _canon(path):
    """把路徑正規化到能可靠比對的形式：剝 basename 的 NTFS ADS、用 realpath 解 `..`/`//`/8.3/symlink、
    再逐段剝尾端空白與點（Windows 檔案系統會剝）。best-effort——路徑正規化是無底洞，這支只求
    對『自家 clean-path 流程』穩、並擋掉常見混淆；決心繞的攻擊者仍有 Bash 等路可走（見檔頭誠實聲明）。"""
    p = path.replace("\\", "/")
    segs = p.split("/")
    if segs and ":" in segs[-1]:            # basename 的 ADS（SKILL.md::$DATA）→ 取冒號前
        segs[-1] = segs[-1].split(":")[0]   # 只切 basename，不會誤砍磁碟機代號
    p = "/".join(segs)
    try:
        p = os.path.realpath(p)             # 解 .. // 8.3 短名 symlink（對存在的前綴）
    except Exception:
        p = os.path.normpath(p)
    p = p.replace("\\", "/")
    p = "/".join(s.rstrip(" .") if s not in (".", "..") else s for s in p.split("/"))
    return p.lower()


def _under_skills_dir(path):
    # 比對兩種形式取聯集：①realpath 正規化（解 symlink/8.3/.. 、碰檔案系統）②純字面正規化（normpath 收斂 .. //，不碰檔案系統）。
    # ②補①的漏：若 `.claude/skills` 本身是 symlink，realpath 會把標記路徑解到別處而漏接，字面路徑仍含 `.claude/skills/` 靠②擋下。
    # ②用 normpath 收斂 `..`（純字面、不解 symlink），所以 `.claude/skills/../../vault` 這種真正指向 vault 的路徑不會被②誤判成在 skills 內。
    raw = os.path.normpath(path.replace("\\", "/")).replace("\\", "/")
    raw = "/".join(s.rstrip(" .") if s not in (".", "..") else s for s in raw.split("/")).lower()
    return bool(_SKILLS_DIR.search(_canon(path))) or bool(_SKILLS_DIR.search(raw))


def _has_marker(text):
    return bool(text) and MARKER in text.lower()


def _read_disk(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


DENY_MSG = (
    "anything2skill guard: an agent may not install or modify an anything2skill skill inside the "
    "auto-discovered skills path (.claude/skills/). Your vault (kept outside .claude/skills/) stays the "
    "master. Review the skill, then activate by COPYING it into .claude/skills/ YOURSELF (copy, do not "
    "move -- the vault keeps the master so nothing is lost) and removing the disable-model-invocation "
    "line in that copy. This manual step is the review gate by design. (To disable this guard, remove the "
    "hook in settings.json.)"
)


def main() -> int:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except Exception:
        try:
            raw = sys.stdin.read()
        except Exception:
            return 0   # 連 fallback 讀取都失敗（cp950 解碼等）：放行、絕不讓安全閘自己崩成 rc=1
    if not raw:
        return 0
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError, RecursionError):
        return 0   # 畸形/超深巢狀 JSON（RecursionError 不是 JSONDecodeError 子類，要另接、否則逃出成 fail-open）

    # 決策邏輯外包一層 backstop：已知的畸形形狀（非物件/非字串 path/非陣列 edits）在下面各自乾淨放行；
    # 任何「沒預料到」的例外一律 fail-closed（deny）——安全閘不該因內部錯誤崩潰成 rc=1（那反而 fail-open）。
    try:
        # 合法的 PreToolUse 酬載一定是物件；欄位型別不對＝畸形輸入，當「不干涉」放行、不崩潰。
        if not isinstance(data, dict):
            return 0
        tool = data.get("tool_name", "")
        if tool not in ("Write", "Edit", "MultiEdit"):
            return 0
        ti = data.get("tool_input")
        if not isinstance(ti, dict):
            return 0
        path = ti.get("file_path") or ""
        if not isinstance(path, str) or not path or not _under_skills_dir(path):
            return 0  # 不在 discovered 路徑內（vault、使用者其他檔）→ 不干涉

        # 在 .claude/skills/ 內：只擋「本工具的 skill」（帶 marker），放行使用者自己的其他 skill
        ours = False
        if tool == "Write":
            ours = _has_marker(ti.get("content") or "")
        else:  # Edit / MultiEdit：看磁碟現檔、以及編輯字串是否帶 marker
            disk = _read_disk(path)
            if disk is not None and _has_marker(disk):
                ours = True
            else:
                edits = ti.get("edits") if tool == "MultiEdit" else [ti]
                if not isinstance(edits, list):
                    edits = []  # 畸形 edits（非陣列）→ 當作找不到 marker、放行，不崩潰
                blob = "".join((e.get("new_string") or "") + (e.get("old_string") or "")
                               for e in edits if isinstance(e, dict))
                ours = _has_marker(blob)

        if ours:
            _deny(DENY_MSG)
        return 0
    except Exception:
        _deny(DENY_MSG)  # 非預期例外＝fail-closed
        return 0


if __name__ == "__main__":
    sys.exit(main())
