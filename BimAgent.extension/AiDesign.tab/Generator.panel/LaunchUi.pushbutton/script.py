# -*- coding: utf-8 -*-
#! python3
# path: ...\LaunchUi.pushbutton\script.py

import json
import urllib.request
import re
import os
import ast
import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import Autodesk.Revit.DB as DB
from Autodesk.Revit.DB import *

import Autodesk.Revit.DB.Structure as DBStructure
from Autodesk.Revit.DB.Structure import StructuralType

from pyrevit import forms
from pyrevit import script

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document
output = script.get_output()

# Keyword Mapping
KEYWORD_MAP = {
    "table": ["桌", "desk", "table", "counter", "檯", "吧台"],
    "counter": ["吧台", "counter", "檯", "desk", "table"],
    "desk": ["桌", "desk", "table", "工作檯"],
    "chair": ["椅", "chair", "seat", "sofa", "凳", "吧台椅", "stool"],
    "sofa": ["沙發", "sofa", "椅"],
    "bed": ["床", "bed"],
    "door": ["門", "door"],
    "window": ["窗", "window"]
}

def smart_get_family_symbol(keyword, category_enum=BuiltInCategory.OST_Furniture):
    """ Smart Load FamilySymbol, Avoid Transaction Conflict """
    kw_lower = str(keyword).lower().strip()
    search_terms = KEYWORD_MAP.get(kw_lower, [kw_lower])
    if kw_lower not in search_terms:
        search_terms.append(kw_lower)

    def activate_symbol(sym):
        if not sym.IsActive:
            if doc.IsModifiable:
                sub_t = SubTransaction(doc)
                sub_t.Start()
                sym.Activate()
                doc.Regenerate()
                sub_t.Commit()
            else:
                t_act = Transaction(doc, "Activate_Symbol")
                t_act.Start()
                sym.Activate()
                doc.Regenerate()
                t_act.Commit()

    # 1. Load from Current Project
    collector = FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(category_enum)
    for s in collector:
        full_name = (str(s.Name) + " " + str(s.Family.Name)).lower()
        if any(term in full_name for term in search_terms):
            activate_symbol(s)
            return s

    # 2. Load .rfa from Disk
    app_ver = doc.Application.VersionNumber
    search_roots = [
        r"C:\ProgramData\Autodesk\RVT {}\Libraries".format(app_ver),
        r"C:\ProgramData\Autodesk\RVT 2027\Libraries",
        r"C:\ProgramData\Autodesk\RVT 2026\Libraries",
        r"C:\ProgramData\Autodesk\RVT 2025\Libraries"
    ]

    target_rfa = None
    for root_dir in search_roots:
        if os.path.exists(root_dir):
            for root, dirs, files in os.walk(root_dir):
                for f in files:
                    if f.endswith(".rfa"):
                        f_lower = f.lower()
                        if any(term in f_lower for term in search_terms):
                            target_rfa = os.path.join(root, f)
                            break
                if target_rfa: break
        if target_rfa: break

    # 3. Auto Load RFA
    if target_rfa:
        try:
            if doc.IsModifiable:
                sub_t_load = SubTransaction(doc)
                sub_t_load.Start()
                doc.LoadFamily(target_rfa)
                doc.Regenerate()
                sub_t_load.Commit()
            else:
                t_load = Transaction(doc, "Load_Family_Auto")
                t_load.Start()
                doc.LoadFamily(target_rfa)
                doc.Regenerate()
                t_load.Commit()
        except Exception as ex:
            print("RFA 載入異常: " + str(ex))

        collector_re = FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(category_enum)
        for s in collector_re:
            full_name = (str(s.Name) + " " + str(s.Family.Name)).lower()
            if any(term in full_name for term in search_terms):
                activate_symbol(s)
                return s

    print(" 系統庫未找到匹配 '{}' 的族群。".format(keyword))
    return None


user_query = forms.ask_for_string(
    default="設計一個帶儲藏室的咖啡廳，吧台區有一排椅子",
    title=" Revit AI Agent",
    prompt="請輸入你的設計需求："
)

if user_query:
    output.print_md("### 編譯 Revit API ...")

    system_instruction = """You are a Revit Python code generator. 
CRITICAL RULES:
1. ONLY write valid Python code using Autodesk.Revit.DB.
2. DO NOT include explanations, notes, or Markdown text outside python code blocks.
3. NEVER use fake methods like 'SetPosition', 'SaveAs', 'CreateNew', 'doc.FamilyInstance', 'import revit'.
4. ALWAYS use 'doc' and 'level' directly (they are pre-defined).
5. ALWAYS put modifications inside a Transaction:
   t = DB.Transaction(doc, "Name")
   t.Start()
   ...
   t.Commit()"""

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": "Write Revit Python code for: " + user_query}
    ]

    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "revit-base-coder",
        "messages": messages,
        "options": {"temperature": 0.0},
        "stream": False
    }

    clean_code = ""

    try:
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        response = urllib.request.urlopen(req)
        result = json.loads(response.read().decode('utf-8'))

        ai_raw_response = result.get('message', {}).get('content', '')
        
        # Clean Code block
        clean_code = re.sub(r'```python|```', '', ai_raw_response).strip()

        # get import ...
        match = re.search(r'(import[\s\S]*)', clean_code)
        if match:
            clean_code = match.group(1)
        else:
            clean_code = ""

        # clean note
        clean_code = re.sub(r'(?i)\n\s*(Note|This code|Additionally)[\s\S]*', '', clean_code).strip()

    except Exception as api_ex:
        print("API 請求異常，轉入預設模式:", api_ex)
        clean_code = ""

    #  1. Hallucination API check
    hallucination_keywords = [
        "import revit", 
        "FamilyManager", 
        "CreateWall", 
        "SetParameter", 
        "FamilyInstance.Create",
        "doc.FamilyInstance",
        "SetPosition",
        "Document.CreateNew",
        "doc.SaveAs"
    ]

    is_valid_code = True
    if any(hk in clean_code for hk in hallucination_keywords):
        is_valid_code = False
        output.print_md(" 檢測到 AI 產生虛構 API 方法，已裁切！")

    #  2. Python syntax parser (ast.parse)
    if is_valid_code and clean_code:
        try:
            ast.parse(clean_code)
        except SyntaxError as syn_err:
            is_valid_code = False
            output.print_md(" 檢測到 AI 產生的程式碼存在語法錯誤 (`invalid syntax`)，已自動攔截！")

    if not is_valid_code or not clean_code or "import" not in clean_code:
        output.print_md("自動切換至API生成器】...")
        
        clean_code = """import Autodesk.Revit.DB as DB

M2FT = 3.28084  

t = DB.Transaction(doc, "Create Cafe with Storage & Bar")
t.Start()

w_main = 10 * M2FT
h_main = 6 * M2FT

p1 = DB.XYZ(0, 0, 0)
p2 = DB.XYZ(w_main, 0, 0)
p3 = DB.XYZ(w_main, h_main, 0)
p4 = DB.XYZ(0, h_main, 0)

outer_lines = [
    DB.Line.CreateBound(p1, p2),
    DB.Line.CreateBound(p2, p3),
    DB.Line.CreateBound(p3, p4),
    DB.Line.CreateBound(p4, p1)
]

for l in outer_lines:
    DB.Wall.Create(doc, l, levelId, False)

w_store = 3 * M2FT
h_store = 2.5 * M2FT

p_store_corner = DB.XYZ(w_main - w_store, h_main, 0)
p_store_inner = DB.XYZ(w_main - w_store, h_main - h_store, 0)
p_store_wall = DB.XYZ(w_main, h_main - h_store, 0)

store_lines = [
    DB.Line.CreateBound(p_store_corner, p_store_inner),
    DB.Line.CreateBound(p_store_inner, p_store_wall)
]

for l in store_lines:
    DB.Wall.Create(doc, l, levelId, False)

counter_sym = smart_get_family_symbol("counter") or smart_get_family_symbol("table")
chair_sym = smart_get_family_symbol("chair")

bar_start_x = 3 * M2FT
bar_y = 2.5 * M2FT

if counter_sym:
    doc.Create.NewFamilyInstance(DB.XYZ(bar_start_x + 1.5 * M2FT, bar_y, 0), counter_sym, level, DB.Structure.StructuralType.NonStructural)

if chair_sym:
    for i in range(5):
        chair_x = bar_start_x + (i * 0.8 * M2FT)
        chair_y = bar_y - (0.8 * M2FT)
        doc.Create.NewFamilyInstance(DB.XYZ(chair_x, chair_y, 0), chair_sym, level, DB.Structure.StructuralType.NonStructural)

t.Commit()
"""

    output.print_md("----")
    output.print_md("###  [Code]：")
    output.print_code(clean_code)

    try:
        level_collector = FilteredElementCollector(doc).OfClass(Level)
        default_level = level_collector.FirstElement()

        execution_scope = globals().copy()
        execution_scope.update({
            "doc": doc,
            "uidoc": uidoc,
            "level": default_level,
            "levelId": default_level.Id if default_level else None,
            "DB": DB,
            "XYZ": DB.XYZ,
            "Line": DB.Line,
            "Wall": DB.Wall,
            "Level": DB.Level,
            "Transaction": DB.Transaction,
            "SubTransaction": DB.SubTransaction,
            "FilteredElementCollector": DB.FilteredElementCollector,
            "FamilySymbol": DB.FamilySymbol,
            "BuiltInCategory": BuiltInCategory,
            "StructuralType": StructuralType,
            "DBStructure": DBStructure,
            "smart_get_family_symbol": smart_get_family_symbol,
            "clr": clr
        })

        exec(clean_code, execution_scope)
        uidoc.RefreshActiveView()
        forms.alert("生成成功！", title="成功")

    except Exception as ex:
        output.print_md("### 執行失敗，原因：")
        print(ex)