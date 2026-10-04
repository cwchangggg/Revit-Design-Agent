# Revit-Design-Agent

本專案旨在建構一個連結 Autodesk Revit、模型上下文協定 (Model Context Protocol, MCP) 與大型語言模型 (LLM) 的自動化開發環境。透過標準化的通訊協定，將自然語言指令轉化為合規且精確的 Revit API 操作，解決小型 LLM 易產生 API 語法幻覺 (Hallucination) 與執行期錯誤的問題。

---

## 專案核心架構

系統採用三層分離架構設計，確保指令傳遞的穩定性與擴充性：

1. **LLM Agent Layer**: 接收使用者自然語言需求，根據 MCP 定義的工具 (Tools) 與 Context 生成呼叫指令。
2. **MCP Server Protocol**: 擔任 LLM 與 Revit 內部的橋樑，傳遞具體 JSON-RPC 請求，限定工具參數結構。
3. **Revit Host Executer (pyRevit Script)**: 接收指令、執行語法解析 (AST Check)、進行 API 黑名單過濾，並安全呼叫 Revit API。

---

## 系統核心防護機制

針對小型語言模型（如 `revit-base-coder` 或在地化模型）常出現語法亂寫、虛構 API (例如 `doc.FamilyInstance.Create`、`SetPosition`) 或夾帶非程式碼說明 (如 `Note:...`) 等問題，內建以下三重防護：

1. **語法編譯預審 (AST Compiler Gate)**
* 執行前透過 Python 原生 `ast.parse()` 解析生成的程式碼。
* 若存在未註解的說明文字或語法結構錯誤 (`SyntaxError`)，立即攔截並轉入備用邏輯。


2. **API 幻覺黑名單過濾器 (API Hallucination Filter)**
* 過濾常見的非官方語法（包括但不限於 `import revit`, `FamilyManager`, `CreateWall`, `SetParameter`, `doc.FamilyInstance`, `SetPosition`, `SaveAs`）。
* 一旦比對到無效關鍵字，程式會自動裁切或判定為無效回應。


3. **安全接管機制 (Fallback Engine)**
* 當 AI 產出的程式碼無法通過 AST 解析或黑名單驗證時，系統會自動觸發內建的標準 Autodesk.Revit.DB 官方 API 備用流程，確保使用者端執行零中斷。

---

## 安裝與設定說明

### 1. 前置需求

* Autodesk Revit 2023 或更新版本
* pyRevit 外掛套件平台
* Python 3.x 環境（pyRevit 執行環境）
* Ollama / Local LLM Endpoint 或遠端 LLM API (例如 OpenAI API)
* 本專案使用 Llama3 來開發，可自行更換模型及對應程式碼

### 2. 部署 pyRevit PushButton

將本專案腳本配置於 pyRevit 擴充資料夾中：

```text
MyTools.extension/
└── MyTab.tab/
    └── Tools.panel/
        └── LaunchUi.pushbutton/
            ├── bundle.yaml
            ├── icon.png
            └── script.py

```

### 3. MCP 連接埠設定

若使用 MCP Server 模式，請確保本地 MCP 協定服務器監聽埠號（預設為 HTTP / JSON-RPC 或 WebSocket）配置正確，並在 `script.py` 中設定對應 Endpoint。

---

## 介面與資料處理流程 (Workflow)

1. **使用者輸入**：在 pyRevit 彈出視窗中輸入自然語言需求（例如：設計包含儲藏室與吧台椅子的咖啡廳空間）。
2. **Prompt 構造與發送**：
* 包含系統提示詞 (System Instructions)，明確限制只能使用 `Autodesk.Revit.DB`、禁止引入無效模組。
* 設定 `temperature: 0.0` 降低隨機性。


3. **回應清理與驗證**：
* 擷取 `import` 開頭至程式碼結束部分。
* 剔除結尾處 `Note:` 等說明字串。
* 進行 AST 語法檢驗與 API 黑名單過濾。


4. **Revit API 執行**：
* 注入作用域變數 (`doc`, `uidoc`, `level`, `levelId`, `DB`, `smart_get_family_symbol`)。
* 於 Transaction 事務內執行語法並更新視圖 (`RefreshActiveView`)。



---

## Revit API 標準開發規範 (供 Prompt 參考)

為避免 LLM 產生無效程式碼，Prompt 需遵守以下寫作規則：

* **單位換算**：Revit 內部長度單位皆為英呎 (Feet)。1 米 (Meter) = 3.28084 英呎，必須進行換算。
* **事務控制**：所有修改模型的操作必須封裝於 Transaction 中：
```python
t = DB.Transaction(doc, "Transaction Name")
t.Start()
# Revit API Operations
t.Commit()

```


* **元件載入與放置**：
* 牆面建立：使用 `DB.Wall.Create(doc, line, levelId, False)`
* 族群放置：使用 `doc.Create.NewFamilyInstance(position, symbol, level, StructuralType.NonStructural)`
* 族群啟用：放置前必須確認 `symbol.IsActive` 為 True，否則需呼叫 `symbol.Activate()`。



---

## 錯誤處理與日誌

* **API 請求失敗**：自動捕捉 `urllib.error.URLError` 或 HTTP 超時，並輸出日誌紀錄。
* **執行期例外**：所有未預期的 Revit 內部 Exception 皆會輸出完整 Stack Trace 至 pyRevit Console Output，以利除錯。
