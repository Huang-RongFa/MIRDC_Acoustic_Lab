# V1.4 模板與正式網站對照

來源：CNC_Acoustic_Lab_Three_Phones_v1_4_preview.html（完整 HTML/CSS/JavaScript）。

原模板採角色分頁：主控 01 房間、02 三人就緒、03 共用加工條件、04 不限時控制、05 三條波形；錄音端為加入、麥克風、等待主控。保留此順序及 class，擴充歷史、分析與設定導覽。

原色票：背景 #f6f9f9、白色卡片 #fff、文字 #17333b、青綠主按鈕 #107e76、邊線 #e7eef0；A/B/C 為 #4a96bf/#25a399/#d4a163。沿用系統繁中字體、16px 卡片圓角、11px 按鈕圓角。原 CSS 原樣擷取為 template.css，必要的可讀性與觸控調整獨立放置。

手機單欄；740px 起雙欄，1000px 擴大間隔。主控可同時是 Recorder A，因此主控頁也必須提供本機授權與就緒，不需要第四支手機。

原 JavaScript 的 localStorage/BroadcastChannel、預填 A/B 就緒、C 模擬按鈕、合成波形、延時成功狀態皆不適用正式錄音。改由 FastAPI/WebSocket 提供權威狀態；Web Audio 提供真實波形，MediaRecorder 分段、IndexedDB 暫存、SHA256 與冪等補傳。

倒數與 elapsed 使用伺服器時間；每台手機保留實際開始與 clock observations，不能宣稱樣本同步。刷新可恢復伺服器狀態及已保存分段，但不能恢復被瀏覽器中止的 MediaRecorder；此情境必須標為中斷。

驗收介面（使用者已確認）：REST/WebSocket、瀏覽器流程、獨立 PostgreSQL 測試庫。三實體手機、iOS 背景限制與現場音質另行實機驗收。
