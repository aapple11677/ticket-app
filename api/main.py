from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse  # ★ 新增這行
import os  # ★ 新增這行
from pydantic import BaseModel
# ... (下方原本的程式碼維持不動) ...
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from cryptography.fernet import Fernet
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware # 這行可以放在檔案最上方，或跟其他 import 放一起

# ==========================================
# 1. 資安設定：初始化 AES 加密金鑰
# 注意：正式上線時，請將金鑰存於環境變數 (.env) 中，切勿寫死在程式碼裡
# ==========================================
SECRET_KEY = Fernet.generate_key()
cipher_suite = Fernet(SECRET_KEY)

# ==========================================
# 2. 資料庫設定 (使用 SQLite 方便立即測試)
# 若要換成 PostgreSQL，只需改為 "postgresql://user:password@localhost/dbname"
# ==========================================
# 1. 把剛剛複製的字串貼上，並把 [YOUR-PASSWORD] 換成您剛剛設定的密碼 (注意密碼前後不要留括號)
SQLALCHEMY_DATABASE_URL = "postgresql://postgres.rjhhnqthhsklagzqwzdx:2LLIOROi...@aws-1-ap-southeast-2.pooler.supabase.com:6543/postgres"

# 2. 把後面 SQLite 專用的 check_same_thread 刪掉，留下這樣就好：
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 3. 定義資料庫模型 (Database Schema)
# ==========================================
class ProxyOrder(Base):
    __tablename__ = "proxy_orders"
    id = Column(Integer, primary_key=True, index=True)
    event_name = Column(String, index=True)
    ticket_date = Column(DateTime)          # 搶票日期 (供行事曆讀取)
    contact_info = Column(String)           # 聯絡人與平台
    ticket_details = Column(String)         # 區域與張數
    encrypted_account = Column(String)      # ★ 加密後的平台帳密
    credit_card_last_digits = Column(String)# 信用卡後幾碼
    order_status = Column(String, default="待搶票")
    is_paid_within_10_mins = Column(Boolean, default=False) # ★ 嚴格控管10分鐘內付款狀態

# 建立資料表
Base.metadata.create_all(bind=engine)

# ==========================================
# 4. FastAPI 伺服器與 API 端點
# ==========================================
app = FastAPI(title="演唱會票務管理系統 API")
# ==== 請將以下這段加入在 app = FastAPI(...) 的正下方 ====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 測試階段先允許所有來源，正式上線時會改成您的專屬網址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ========================================================

# 取得資料庫連線的依賴函式
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 定義前端傳入的資料格式 (Pydantic Model)
class ProxyOrderCreate(BaseModel):
    event_name: str
    ticket_date: datetime
    contact_info: str
    ticket_details: str
    account_password: str  # 前端傳明文，我們在後端加密
    credit_card_last_digits: str

@app.post("/api/proxy-orders/")
def create_proxy_order(order: ProxyOrderCreate, db: Session = Depends(get_db)):
    """
    建立代搶訂單的 API
    """
    # ★ 將前端傳來的明文帳密進行加密
    encrypted_acc = cipher_suite.encrypt(order.account_password.encode()).decode()

    # 寫入資料庫
    db_order = ProxyOrder(
        event_name=order.event_name,
        ticket_date=order.ticket_date,
        contact_info=order.contact_info,
        ticket_details=order.ticket_details,
        encrypted_account=encrypted_acc, # 存入密文
        credit_card_last_digits=order.credit_card_last_digits,
        is_paid_within_10_mins=False     # 預設為未付款
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    
    return {
        "message": "訂單建立成功，帳密已安全加密", 
        "order_id": db_order.id
    }
    # ... (上方原本處理訂單的程式碼維持不動) ...
# ==========================================
# ★ 新增：讀取訂單並提供給行事曆的 API
# ==========================================
@app.get("/api/proxy-orders/")
def get_proxy_orders(db: Session = Depends(get_db)):
    """從資料庫撈出所有訂單，並轉換成 FullCalendar 需要的格式"""
    orders = db.query(ProxyOrder).all()
    result = []
    for order in orders:
        result.append({
            "id": order.id,
            "title": f"代搶: {order.event_name}",   # 行事曆上顯示的方塊標題
            "start": order.ticket_date.isoformat(), # 決定方塊出現在哪一天
            "extendedProps": {                      # 把客戶細節藏在背景，點擊時才顯示
                "contact": order.contact_info,
                "details": order.ticket_details,
                "status": order.order_status
            },
            "color": "#ff4d4d" if order.order_status == "待搶票" else "#28a745" # 待搶票顯示紅色，其他顯示綠色
        })
    return result
# ★ 將以下這段加入到檔案的最下方
@app.get("/")
@app.get("/index.html")
def serve_frontend():
    # 自動尋找 index.html 的正確位置並顯示在瀏覽器上
    file_path = "index.html" if os.path.exists("index.html") else "../index.html"
    return FileResponse(file_path)
