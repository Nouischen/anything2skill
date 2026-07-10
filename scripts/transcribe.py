# 轉逐字稿。自動選後端：NVIDIA GPU→本機 faster-whisper；Apple Silicon Mac→本機 mlx-whisper；都沒有→OpenAI API（需金鑰）。
# 用法（Mac/Linux 用 python3）：
#   本機/自動： python transcribe.py <audio_dir> <transcript_dir>
#   強制 API ： python transcribe.py <audio_dir> <transcript_dir> --api
import os, sys, json, glob, re, platform

_SCRIPTDIR = os.path.dirname(os.path.abspath(__file__))  # requirements-*.txt 在腳本同目錄；訊息一律印這個絕對路徑，別讓使用者在專案根目錄撲空

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

if len(sys.argv) < 3:
    print("用法: python transcribe.py <audio_dir> <transcript_dir> [--api]（Mac/Linux 用 python3）", flush=True); sys.exit(2)
AUD, TR = sys.argv[1], sys.argv[2]
USE_API = "--api" in sys.argv[3:]
if not os.path.isdir(AUD):
    print(f"[ERR] 音訊資料夾不存在或不是資料夾：{AUD}（先確認下載步驟的輸出路徑，再重跑）", flush=True); sys.exit(3)
try:
    os.makedirs(TR, exist_ok=True)
except OSError as _e:
    print(f"[ERR] 無法建立逐字稿輸出資料夾 {TR}：{_e}（換一個可寫入的路徑再重跑）", flush=True); sys.exit(3)
LANG = os.environ.get("ANYTHING2SKILL_LANG") or None  # 預設 None＝Whisper 自動偵測語言；設了才強制該語言
_CJK = re.compile(r"[぀-ヿ㐀-鿿豈-﫿가-힯]")
def sep_for(lang, text=""):
    # CJK / 日 / 韓 段落間不加空白；其餘語言用空白。lang 未知（自動偵測）時，用文字內容推斷。
    if lang:
        return "" if lang.lower().startswith(("zh", "ja", "ko", "yue")) else " "
    return "" if _CJK.search(text or "") else " "

def ts(s):
    if s is None: s = 0.0   # 後端偶爾回 None 的 start/end（空白段/靜音）→ 當 0，別讓時間戳計算拋 TypeError
    h=int(s//3600); m=int((s%3600)//60); s=int(s%60); return f"{h:02d}:{m:02d}:{s:02d}"

def _atomic_write(path, text):
    # 先寫 .tmp 再 os.replace：中途當掉（睡眠/斷電/Ctrl-C）不會留下半截檔被下次執行當成「已完成」而 skip
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)

def write_local_outputs(base, rows, detected_lang):
    # 本機後端（faster-whisper／mlx-whisper）共用：寫 timestamped / json / fulltext 三個檔（皆原子寫）
    texts = [r["text"] for r in rows]
    _atomic_write(base + ".timestamped.txt", "".join(f"[{ts(r['start'])}] {r['text']}\n" for r in rows))
    _atomic_write(base + ".json", json.dumps(rows, ensure_ascii=False, indent=1))
    _atomic_write(base + ".fulltext.txt", sep_for(detected_lang, "".join(texts)).join(texts))

def is_apple_silicon():
    # 判斷「硬體」是不是 Apple Silicon——連 Rosetta 下跑 x86_64 Python 的情況也要認出來
    if sys.platform != "darwin":
        return False
    if platform.machine().lower() in ("arm64", "aarch64"):
        return True
    try:
        import subprocess
        return subprocess.run(["sysctl", "-n", "hw.optional.arm64"],
                              capture_output=True, text=True).stdout.strip() == "1"
    except Exception:
        return False

# 副檔名比對一律轉小寫再比：Linux 檔案系統分大小寫，LECTURE.MP3 也是合法音檔，glob 樣式會漏掉
EXTS = {".m4a", ".mp4", ".webm", ".aac", ".mp3", ".wav", ".opus", ".ogg", ".mka", ".flac"}
files = sorted(os.path.join(AUD, n) for n in os.listdir(AUD)
               if os.path.splitext(n)[1].lower() in EXTS and os.path.isfile(os.path.join(AUD, n)))
def _outbase(f, seen):
    # 輸出檔名用「不含副檔名的檔名」，但同名不同副檔（lesson.mp3 / lesson.m4a）會撞同一路徑、
    # 後者靜默覆蓋前者 → 撞名時附上副檔名去撞（lesson / lesson-m4a），避免逐字稿被蓋掉。
    stem = os.path.splitext(os.path.basename(f))[0]
    ext = os.path.splitext(f)[1].lstrip(".").lower()
    # 大小寫無關比對：Windows/macOS 檔案系統不分大小寫，Lesson 與 lesson 會寫到同一實體檔
    cand = stem
    if cand.lower() in seen:
        cand = f"{stem}-{ext}"
        n = 2
        while cand.lower() in seen:
            cand = f"{stem}-{ext}-{n}"; n += 1
    seen.add(cand.lower())
    return os.path.join(TR, cand)
_seen = set()
jobs = [(f, base) for f in files for base in (_outbase(f, _seen),)
        if not os.path.exists(base + ".fulltext.txt")]
print(f"[plan] 待轉錄 {len(jobs)} / 共 {len(files)}", flush=True)
# 對照 download 的 manifest：下載成功的單元數若多於這裡找到的音檔數，代表有課被漏掉（如未支援副檔名）
try:
    with open(os.path.join(AUD, "manifest.json"), encoding="utf-8") as _mf:
        _man = json.load(_mf)
    _ok = sum(1 for x in _man if isinstance(x, dict) and x.get("status") in ("ok", "skip"))
    if _ok > len(files):
        print(f"[WARN] download 標記成功 {_ok} 個單元，但這裡只找到 {len(files)} 個可轉錄音檔——可能有課被漏掉（副檔名不支援？），請檢查 {AUD}。", flush=True)
except Exception:
    pass
if not files:
    print("[ERR] 音訊資料夾沒有任何音檔可轉錄（下載步驟可能失敗了，請先檢查 download 結果）。", flush=True); sys.exit(3)
if not jobs:
    print("[ALLDONE] 無待處理（全部已完成）"); sys.exit(0)

def has_gpu():
    try:
        import ctypes
        lib = None
        for dll in ("nvcuda.dll", "libcuda.so", "libcuda.so.1"):
            try: lib = ctypes.CDLL(dll); break
            except Exception: pass
        if not lib:
            return False
        # DLL 載得到 ≠ 有能用的 GPU（Optimus 筆電、驅動太舊、只有內顯卻殘留 nvidia dll）。
        # 真的初始化 CUDA 並數一下裝置，數得到 ≥1 才算數。
        try:
            n = ctypes.c_int(0)
            if lib.cuInit(0) == 0 and lib.cuDeviceGetCount(ctypes.byref(n)) == 0 and n.value >= 1:
                return True
        except Exception:
            return True  # 少數平台沒有 cuInit 符號時，退回「載得到就當有」（原行為）
        return False
    except Exception:
        pass
    return False

# ---- 選後端：--api 強制 API；否則 Apple Silicon→MLX、NVIDIA→CUDA、其餘→API ----
if USE_API:
    backend = "api"
elif is_apple_silicon():
    backend = "mlx"
elif has_gpu():
    backend = "cuda"
else:
    backend = "api"
    print("[model] 未偵測到可用的本機 GPU（無 NVIDIA CUDA，也非 Apple Silicon）。", flush=True)

# ---- 明確宣告本次後端：讓使用者一眼看出走了哪條路（速度／費用／音檔是否離開本機）----
_BACKEND_BANNER = {
    "cuda": "本機 NVIDIA GPU · faster-whisper large-v3（免費、音檔不離開這台電腦、最快）",
    "mlx":  "本機 Apple Silicon · mlx-whisper large-v3（免費、音檔不離開這台電腦）",
    "api":  "OpenAI Whisper API · whisper-1（付費約 US$0.006/分鐘、音檔會上傳到 OpenAI、速度取決於網路）",
}
print(f"[backend] 本次轉錄後端 = {backend.upper()}｜{_BACKEND_BANNER.get(backend, backend)}", flush=True)
if backend == "api" and not USE_API:
    print("[backend] （這台沒有可用的本機 GPU，才自動改走雲端 API；想免費本機轉錄請換有 NVIDIA 顯卡或 Apple Silicon 的電腦）", flush=True)

# ---- API 路徑 ----
if backend == "api":
    if not os.environ.get("OPENAI_API_KEY"):
        print("[需要] 這台沒有可用的本機 GPU，要用 API 轉錄：請設定環境變數 OPENAI_API_KEY 後重跑（約 US$0.006/分鐘），"
              "或改在有 NVIDIA 顯卡／Apple Silicon Mac 的電腦上跑（那兩種都能免費本機轉錄）。", flush=True)
        sys.exit(2)
    try:
        from openai import OpenAI
    except Exception:
        print("[需要] 請先 pip install openai", flush=True); sys.exit(2)
    import subprocess, tempfile, shutil
    MAX_API_BYTES = 24 * 1024 * 1024  # whisper-1 上限 25MB，留安全邊界

    def _ff(args):
        try:
            return subprocess.run(["ffmpeg", "-nostdin", "-y", *args], capture_output=True)
        except FileNotFoundError:
            return None

    def api_one(client, path_in):
        with open(path_in, "rb") as fh:
            kw = {"language": LANG} if LANG else {}  # 沒指定語言就讓 Whisper 自動偵測
            return client.audio.transcriptions.create(model="whisper-1", file=fh, **kw).text

    def api_transcribe(client, audio):
        # 先壓成 16k 單聲道低位元率（whisper 只需這樣），順便大幅縮小體積 → 多數課程一次就送得出去
        tmpd = tempfile.mkdtemp(prefix="c2n_")
        try:
            comp = os.path.join(tmpd, "a.m4a")
            r = _ff(["-i", audio, "-ac", "1", "-ar", "16000", "-b:a", "32k", comp])
            src = comp if (r is not None and r.returncode == 0 and os.path.exists(comp)) else audio
            if os.path.getsize(src) <= MAX_API_BYTES:
                return api_one(client, src)
            # 仍超過上限（超長課程）→ 需要 ffmpeg 壓縮/切段；沒有 ffmpeg 就處理不了大檔，明講而不是把原檔硬送給 OpenAI 被拒
            if r is None:
                raise RuntimeError(f"這個音檔約 {os.path.getsize(src)//(1024*1024)}MB、超過 OpenAI API 25MB 上限，需要 ffmpeg 壓縮／切段，但系統找不到 ffmpeg。請先安裝 ffmpeg 再重跑。")
            seg = os.path.join(tmpd, "seg_%03d.m4a")
            _ff(["-i", src, "-f", "segment", "-segment_time", "600", "-c", "copy", seg])
            parts = sorted(glob.glob(os.path.join(tmpd, "seg_*.m4a"))) or [src]
            texts = [api_one(client, p) for p in parts]
            return sep_for(LANG, "".join(texts)).join(texts)
        finally:
            shutil.rmtree(tmpd, ignore_errors=True)

    client = OpenAI()
    print("[model] OpenAI Whisper API（注意：音檔會上傳到 OpenAI 進行轉錄）", flush=True)
    fails = []
    for audio, base in jobs:
        name = os.path.basename(base)
        print(f"[job] {os.path.basename(audio)} -> {name} (API)", flush=True)
        try:
            text = api_transcribe(client, audio)
            _atomic_write(base + ".fulltext.txt", text)
            print(f"[done] {name}", flush=True)
        except Exception as e:
            fails.append(name); print(f"[ERR] {name}: {e}", flush=True)
            _m = str(e).lower()
            if any(k in _m for k in ("invalid_api_key", "incorrect api key", "authentication", " 401",
                                     "insufficient_quota", "exceeded your current quota", " 429")):
                print("[需要] 看起來是 OpenAI 金鑰無效或額度用完——先到 platform.openai.com 檢查金鑰與 Billing，"
                      "修好再重跑（已完成的單元會自動跳過）。先停下，免得整批都撞同一個錯。", flush=True)
                sys.exit(2)
            if any(k in _m for k in ("apiconnectionerror", "connection error", "failed to connect",
                                     "max retries", "unsupported_country", "unsupported_region", "getaddrinfo")):
                print("[需要] 連不上 OpenAI API（多半是防火牆／公司或醫院網路擋了 api.openai.com，或所在地區不支援）。"
                      "換一個網路、或設定 proxy 後重跑（已完成的單元會自動跳過）。先停下，免得整批都撞同一個錯。", flush=True)
                sys.exit(2)
    if fails:
        print(f"[WARN] {len(fails)} 個單元轉錄失敗（未產生逐字稿）：{', '.join(fails)}", flush=True)
        print("[ALLDONE]", flush=True); sys.exit(1)
    print("[ALLDONE]", flush=True); sys.exit(0)

# ---- Apple Silicon 本機路徑（mlx-whisper，吃 Mac GPU/神經引擎，免費）----
if backend == "mlx":
    if platform.machine().lower() not in ("arm64", "aarch64"):
        print("[需要] 這是 Apple Silicon Mac，但你現在用的是 x86_64（Rosetta）的 Python，mlx-whisper 需要原生 arm64 的 Python。"
              "請改用 arm64 版 Python（例如 brew 裝的 python3）再跑，或改用 --api。", flush=True)
        sys.exit(2)
    try:
        import mlx_whisper
    except Exception:
        print(f"[需要] 偵測到 Apple Silicon Mac，但未安裝 mlx-whisper（吃 Mac GPU、免費本機轉錄）。"
              f"請 pip3 install -r \"{os.path.join(_SCRIPTDIR, 'requirements-mac.txt')}\"（若報 externally-managed-environment 就加 --break-system-packages），或改用 --api。", flush=True)
        sys.exit(2)
    MLX_REPO = os.environ.get("ANYTHING2SKILL_MLX_MODEL", "mlx-community/whisper-large-v3-mlx")
    print(f"[model] MLX {MLX_REPO}（Apple Silicon 本機；第一次會從 huggingface.co 下載約 1–3GB 模型、只需一次，網路慢請耐心等）", flush=True)
    fails = []
    for audio, base in jobs:
        name = os.path.basename(base)
        print(f"[job] {os.path.basename(audio)} -> {name} (MLX)", flush=True)
        try:
            kw = {"language": LANG} if LANG else {}  # 沒指定就自動偵測
            # 防幻覺/防重複循環護欄（與 CUDA 路徑對齊；whisper 在靜音段會吐重複與幻覺）
            r = mlx_whisper.transcribe(audio, path_or_hf_repo=MLX_REPO,
                    condition_on_previous_text=False,
                    compression_ratio_threshold=2.4,
                    no_speech_threshold=0.6, **kw)
            rows = [{"start": float(s.get("start") or 0.0), "end": float(s.get("end") or 0.0),
                     "text": (s.get("text") or "").strip()} for s in r.get("segments", [])]
            if not rows and (r.get("text") or "").strip():
                rows = [{"start": 0.0, "end": 0.0, "text": r["text"].strip()}]
            write_local_outputs(base, rows, r.get("language") or LANG)
            print(f"[done] {name}: {len(rows)} segments", flush=True)
        except Exception as e:
            fails.append(name); print(f"[ERR] {name}: {e}", flush=True)
            _m = str(e).lower()
            if any(k in _m for k in ("huggingface", "hf.co", "connection", "max retries", "ssl", "getaddrinfo", "timed out")):
                print("[需要] 模型下載失敗（網路／防火牆問題）——第一次要從 huggingface.co 下載約 3GB 模型。"
                      "可設 HF_ENDPOINT=https://hf-mirror.com 換鏡像、或換網路重跑；模型只需下載一次。先停下，免得整批都撞同一個錯。", flush=True)
                sys.exit(2)
    if fails:
        print(f"[WARN] {len(fails)} 個單元轉錄失敗（未產生逐字稿）：{', '.join(fails)}", flush=True)
        print("[ALLDONE]", flush=True); sys.exit(1)
    print("[ALLDONE]", flush=True); sys.exit(0)

# ---- 本機 faster-whisper 路徑（NVIDIA CUDA）----
# Windows：pip 裝的 nvidia-cudnn/cublas wheel 會把 DLL 放在 site-packages\nvidia\*\bin，
# 但那不在 DLL 搜尋路徑，CTranslate2 會報 "Unable to load cudnn/cublas"。這裡主動把它們加進來，
# 否則照文件裝完 requirements-gpu.txt 的旗艦本機路徑也會載入失敗。
if sys.platform == "win32":
    try:
        import site
        for sp in list(site.getsitepackages() or []) + [site.getusersitepackages()]:
            for p in glob.glob(os.path.join(sp, "nvidia", "*", "bin")):
                try:
                    os.add_dll_directory(p)
                    os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")
                except Exception:
                    pass
    except Exception:
        pass
try:
    from faster_whisper import WhisperModel
except Exception as _e:
    print(f"[需要] 偵測到 NVIDIA 顯卡但無法載入 faster-whisper（{_e}）。"
          "請 pip install -U faster-whisper nvidia-cudnn-cu12 nvidia-cublas-cu12（Mac/Linux 用 pip3）。"
          "若裝不起來，多半是你的 Python 版本太新、還沒有對應的 wheel——換用 Python 3.12 再裝（README 的建議版本），或改用 --api。", flush=True)
    sys.exit(2)

PRIMER = os.environ.get("ANYTHING2SKILL_PRIMER",
    "以下是一場線上課程或講座的錄音，內容為專業知識講解。")

print("[model] 載入 large-v3（第一次會下載模型、約 1–3 GB，網路慢請耐心等，不是當掉）…", flush=True)
try:
    model = WhisperModel("large-v3", device="cuda", compute_type="int8_float16")
    print("[model] large-v3 CUDA int8_float16", flush=True)
except Exception as e:
    if os.environ.get("ANYTHING2SKILL_ALLOW_CPU"):
        print(f"[model] CUDA 失敗({e})，改用 CPU（large-v3 在 CPU 上非常慢）", flush=True)
        model = WhisperModel("large-v3", device="cpu", compute_type="int8")
        # 前面的 [backend] 橫幅在模型初始化前就印了 CUDA；這裡實際退回 CPU，補一行更正，讓「本次真正的後端」不被誤判
        print("[backend] ⚠ 實際後端 = CPU（前面宣告的 CUDA 初始化失敗、已改用 CPU；large-v3 在 CPU 上非常慢，這才是本次真正使用的後端）", flush=True)
    else:
        _m = str(e).lower()
        if any(k in _m for k in ("huggingface", "hf.co", "connection", "max retries", "ssl", "getaddrinfo", "timed out", "read timed out")):
            # 第一次載入模型要從 huggingface.co 下載 ~3GB——被防火牆/TLS 攔或該地區封鎖時，錯誤看起來像 CUDA 失敗，其實是網路
            print(f"[需要] 模型下載失敗（網路／防火牆問題，不是顯卡問題）：{e}。"
                  "第一次跑要從 huggingface.co 下載約 3GB 模型。公司／醫院網路常擋 HuggingFace——可設 HF_ENDPOINT=https://hf-mirror.com 換鏡像、或換一個網路重跑；模型只需下載一次。", flush=True)
        elif any(k in _m for k in ("no cuda-capable device", "insufficient", "driver version", "cuda driver", "cuda_error")):
            print(f"[需要] CUDA 執行失敗({e})——多半是你的 NVIDIA 顯示卡驅動太舊，帶不動 CUDA 12。"
                  "請到 nvidia.com 更新顯卡驅動後重跑；或先改用 --api（雲端轉錄）。", flush=True)
        else:
            print(f"[需要] CUDA 初始化失敗({e})。若是 'Unable to load cudnn/cublas' 這類："
                  f"腳本已自動把 pip 的 nvidia DLL 目錄加進搜尋路徑，若還是失敗，多半是沒裝 \"{os.path.join(_SCRIPTDIR, 'requirements-gpu.txt')}\""
                  "（含 nvidia-cudnn-cu12 nvidia-cublas-cu12），或裝到了跟這支腳本不同的 Python。"
                  "large-v3 在 CPU 上會非常慢，也可改用 --api；真的要用 CPU 設 ANYTHING2SKILL_ALLOW_CPU=1 再重跑。", flush=True)
        sys.exit(2)

fails = []
for audio, base in jobs:
    name = os.path.basename(base)
    print(f"[job] {os.path.basename(audio)} -> {name}", flush=True)
    try:
        segments, info = model.transcribe(audio, language=LANG, beam_size=5, vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500), condition_on_previous_text=False,
            repetition_penalty=1.1, no_repeat_ngram_size=3, initial_prompt=PRIMER,
            temperature=[0.0,0.2,0.4], compression_ratio_threshold=2.4, no_speech_threshold=0.6)
        total = info.duration or 1; rows=[]; last=-5
        for seg in segments:
            rows.append({"start":seg.start,"end":seg.end,"text":seg.text.strip()})
            pct=int(seg.end/total*100)
            if pct>=last+10: last=pct; print(f"  {name} ...{pct}%", flush=True)
        write_local_outputs(base, rows, getattr(info, "language", None) or LANG)
        print(f"[done] {name}: {len(rows)} segments", flush=True)
    except Exception as e:
        fails.append(name); print(f"[ERR] {name}: {e}", flush=True)
if fails:
    print(f"[WARN] {len(fails)} 個單元轉錄失敗（未產生逐字稿）：{', '.join(fails)}", flush=True)
    print("[ALLDONE]", flush=True); sys.exit(1)
print("[ALLDONE]", flush=True); sys.exit(0)
