# 在 Jetson Orin Nano 8GB 上跑地端分析：相依檢查

日期：2026-11-23。狀態：**只做了靜態檢查與套件查詢，沒有在 Jetson 實機上跑過。**

## 角色

Jetson 取代地端電腦的角色：連到資料庫認領工作、計算、把結果寫回，網站照舊顯示。錄音仍由網站接收。
要跑的程式是 [`analysis/worker.py`](../analysis/worker.py)（說明見 [`analysis-worker.md`](analysis-worker.md)）。Jetson 只需要連得出去，不需要開放任何入站連線。

## 結論

| 項目 | 結果 |
|---|---|
| 程式能不能在 Linux ARM 上跑 | 靜態檢查沒有發現阻礙。worker 與模型沒有 Windows 專用的程式；只有錄音工具 `record_usb.py` 是 Windows 專用，Jetson 當 worker 時用不到 |
| 套件 | 六個套件在 PyPI 都有 Linux ARM（aarch64）的安裝檔，Python 3.10 與 3.8 都有符合 `requirements.txt` 的版本 |
| 建議的系統 | **JetPack 6**（Ubuntu 22.04、Python 3.10）。套件版本和目前開發機的環境幾乎相同 |
| **記憶體** | **照開發機的量測估計，3 分鐘的錄音約需 9 GB，超過 8 GB 的實體記憶體**（見下方）。沒有在 Jetson 上量過；這一輪沒有處理 |

## 記憶體（最重要的限制）

在開發機（Windows）上量到的尖峰記憶體，用 `psutil` 讀取分析子程序的峰值：

| 錄音 | 尖峰記憶體 | 時間 |
|---|---|---|
| 2 軌、37 秒 | 1820 MB | 約 33–45 秒 |
| 2 軌、57 秒 | 2818 MB | 約 44–50 秒 |

- 大約每秒錄音 50 MB。照這個比例，3 分鐘約需 9 GB。
- Orin Nano 8GB 的記憶體由 CPU 與 GPU 共用，系統本身也要用掉一部分。照上面的比例估計，實際能跑完的長度大約 2 分鐘；這是估計值，沒有在實機上量過。
- 照這個估計，要跑 3 分鐘的錄音得先降低模型的記憶體用量（改成分段計算、圖降低解析度）。這件事還沒有做。
- 加大 swap 可以避免程序被系統終止，但會慢很多，不建議當成解法。

## 套件（2026-11-23 查詢 PyPI）

`analysis/requirements.txt` 的需求，以及各 Python 版本在 aarch64 上能裝到的最新版：

| 套件 | 需求 | Python 3.10（JetPack 6） | Python 3.8（JetPack 5） |
|---|---|---|---|
| numpy | >= 1.24 | 2.2.6 | 1.24.4 |
| scipy | >= 1.10 | 1.15.3 | 1.10.1 |
| soundfile | >= 0.12 | 0.14.0 | 0.13.1 |
| matplotlib | >= 3.7 | 3.10.9 | 3.7.5 |
| psycopg（加 psycopg-binary） | >= 3.2 | 3.3.9 | 3.2.13 |
| imageio-ffmpeg | >= 0.4 | 0.8.1 | 0.5.1 |

- Python 3.8 能裝到的版本剛好落在需求的下限。**程式沒有在這些舊版本上跑過**；開發機用的是 Python 3.10、numpy 2.2.5、scipy 1.15.3。
- soundfile 的 aarch64 安裝檔內含 libsndfile，需要 glibc 2.28 以上。Ubuntu 20.04 與 22.04 都符合。
- ffmpeg：worker 會先找系統的 `ffmpeg`，找不到才用 imageio-ffmpeg 內附的。建議直接 `apt install ffmpeg`。需要能解 WebM／Opus 與 MP4／AAC。

## 程式的靜態檢查

對 `analysis/` 的六個程式（`analyze_multi_mic.py`、`worker.py`、`offline.py`、`background_check.py`、`sync_chirp.py`、`record_usb.py`）：

- 用 Python 3.8 的文法解析：全部通過。
- 搜尋 Python 3.9 以後才有的常見用法（`removeprefix`、`is_relative_to`、`zip(strict=)`、字典合併 `|`、內建泛型註記、`X | None`、`match`、`functools.cache`）：沒有找到。這是文字搜尋，不保證沒有遺漏。
- Windows 專用的部分（DirectShow、登錄檔、`sys.platform` 判斷）只出現在 `record_usb.py`。
- 圖上的中文字：
  - `analyze_multi_mic.py` 的字型清單有 `Noto Sans CJK TC`，裝了 `fonts-noto-cjk` 就會顯示。
  - `background_check.py` 的字型清單只有 Windows 的字型，在 Linux 上圖裡的中文會變成方框。這一輪沒有改。

## 安裝步驟（沒有實機驗證過）

```bash
sudo apt install python3-venv ffmpeg fonts-noto-cjk
python3 -m venv ~/cnc-analysis-venv
~/cnc-analysis-venv/bin/pip install -r analysis/requirements.txt "psycopg[binary]"
export ANALYSIS_DATABASE_URL='postgresql://analysis_worker@<資料庫主機>:5432/<資料庫>?sslmode=require'
export PGPASSWORD='<只放在這台 Jetson>'
~/cnc-analysis-venv/bin/python -X utf8 analysis/worker.py --work-dir ~/cnc_analysis
```

## 上機後要先確認的事

1. 不需要資料庫的測試全部通過：
   `test_synthetic.py`、`test_score_scale.py`、`test_alignment_fit.py`、`test_ears_umik.py`、`test_offline.py`、`test_background.py`。
   `test_ears_umik.py` 有幾項是 Windows 錄音工具的測試，在 Linux 上可能不通過，需要另外看。
2. 用一段 1 分鐘的真實錄音跑 `analysis/offline.py run`，記下尖峰記憶體（`/usr/bin/time -v`）與時間，和上表比較。
3. `worker.py --once` 能連到資料庫、認領一筆工作並寫回。
4. 圖裡的中文正常顯示。

## 還沒有處理的

- 記憶體用量（上面已說明）。
- 每聲道 Spectrogram／MFCC 的 worker（`analysis/track_analysis/`）還在另一個分支，沒有包含在這次檢查裡。
- 沒有做開機自動啟動（systemd）的設定。
- 沒有用到 GPU。目前的計算都在 CPU 上，用的是 numpy／scipy。
