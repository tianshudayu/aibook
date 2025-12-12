import sqlite3
import uvicorn
import os
import random
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse 
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

# --- 🔴 配置区 ---
# 替换为你的真实 Key
DEEPSEEK_API_KEY = "sk-748df802a9ba4528a5b5fea7b7a7d53f" 
DB_FILE = "app.db"

# --- 1. 数据库初始化 (核心修复：确保一定会运行) ---
def init_db():
    print("正在初始化数据库...")
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, credits INTEGER DEFAULT 0)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, user_id TEXT, amount REAL, status TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
    print(f"✅ 数据库就绪: {DB_FILE}")

# --- 2. 核心设置 ---

# 生命周期管理器：在 App 启动前先运行数据库初始化
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db() # 👈 移到了这里，确保云端启动时也会执行
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    user_id: str
    question: str

class PayRequest(BaseModel):
    user_id: str
    amount: float

# --- 3. 辅助函数 ---
def get_balance(user_id: str) -> int:
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row: return row[0]
        cursor.execute("INSERT INTO users VALUES (?, ?)", (user_id, 0))
        return 0

def update_balance(user_id: str, change: int):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (change, user_id))

# --- 4. 路由 ---

@app.get("/")
def read_root():
    return FileResponse('index.html')

# 图片服务接口
@app.get("/{filename}")
def get_image(filename: str):
    if filename.endswith(".jpg") and os.path.exists(filename):
        return FileResponse(filename)
    return HTTPException(status_code=404, detail="Image not found")

@app.post("/api/init")
def init_user(req: dict):
    return {"credits": get_balance(req.get("user_id"))}

@app.post("/api/chat")
def chat(req: ChatRequest):
    balance = get_balance(req.user_id)
    if balance <= 0: raise HTTPException(status_code=402, detail="余额不足")
    update_balance(req.user_id, -1)
    
    try:
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是一本答案之书。用简短、神秘、哲理的语言回答用户。30字以内。"},
                {"role": "user", "content": req.question}
            ],
            "stream": False
        }
        resp = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=data, timeout=30)
        if resp.status_code == 200:
            ai_reply = resp.json()['choices'][0]['message']['content']
        else:
            ai_reply = "星象模糊，请稍后再试。"
    except:
        ai_reply = "连接宇宙失败。"

    return {"answer": ai_reply, "remaining_credits": get_balance(req.user_id)}

@app.post("/api/pay")
def pay(req: PayRequest):
    order_id = f"TRUST-{random.randint(100000, 999999)}"
    # 这里会用到 orders 表，之前报错就是因为没这张表
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("INSERT INTO orders (order_id, user_id, amount, status) VALUES (?, ?, ?, ?)", 
                     (order_id, req.user_id, req.amount, "TRUST_PAID"))
    points = 10 if req.amount < 15 else 30
    update_balance(req.user_id, points)
    return {"status": "success", "msg": f"感谢信任！已增加 {points} 点灵力", "new_balance": get_balance(req.user_id)}

if __name__ == "__main__":
    # 本地运行时保留这行
    uvicorn.run(app, host="0.0.0.0", port=8000)