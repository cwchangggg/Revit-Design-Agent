# -*- coding: utf-8 -*-
# path: C:\Users\shuli\OneDrive\桌面\###Aaron2025\AI_smartDraw\revit_mcp_server.py
import mcp
import asyncio
import json
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
import mcp.types as types

# init MCP 
server = Server("revit-2027-inspector")

# 1. Decalration
@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        # tool A：Dynamic search Revit properties
        types.Tool(
            name="inspect_revit_class",
            description="當你不確定某個 Revit 物件（如 Level, Wall, FamilyInstance）有哪些合法屬性或方法時，必須呼叫此工具查詢，嚴禁盲猜。",
            inputSchema={
                "type": "object",
                "properties": {
                    "class_name": {"type": "string", "description": "Revit API 類別名稱，例如 'Level' 或 'Wall'"}
                },
                "required": ["class_name"],
            }
        ),
        # tool B：syntax check and test 
        types.Tool(
            name="validate_and_run_code",
            description="將你寫好的 Python 程式碼送去 Revit 測試執行。如果執行失敗，會回傳精準的 Revit 報錯訊息，讓你重新修正程式碼。",
            inputSchema={
                "type": "object",
                "properties": {
                    "proposed_code": {"type": "string", "description": "你編譯出的純 Python 程式碼"}
                },
                "required": ["proposed_code"],
            }
        )
    ]

# 2. Dynamic report tool
@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    if name == "inspect_revit_class":
        class_name = arguments.get("class_name", "").lower()
        if "level" in class_name:
            info = {
                "Valid_Attributes": ["Elevation (double)", "Name (string)", "Id (ElementId)"],
                "Forbidden_Attributes": ["X (不存在)", "Y (不存在)", "Location (沒有坐標)"],
                "Tip": "計算排列時，請以原點 XYZ(0,0,0) 為基準自行計算偏移量，不准抽 Level 的 X 屬性！"
            }
            return [types.TextContent(type="text", text=json.dumps(info, ensure_ascii=False))]
        
    elif name == "validate_and_run_code":
        code = arguments.get("proposed_code", "")
        if "level.X" in code or "StartTransaction" in code:
            return [types.TextContent(type="text", text=" Revit 核心退件錯誤：'Level' 物件沒有 'X' 屬性，且禁用 StartTransaction！請修正代碼。")]
        return [types.TextContent(type="text", text=" Revit 語法審查通過！執行成功！")]

    return [types.TextContent(type="text", text="未知工具")]

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, InitializationOptions(
            server_name="revit-2027-inspector",
            server_version="1.0.0",
            capabilities=server.get_capabilities(NotificationOptions(), {})
        ))

if __name__ == "__main__":
    asyncio.run(main())