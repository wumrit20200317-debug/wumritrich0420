import streamlit as st
import pandas as pd
import pandas_ta as ta
import os
import base64
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from fubon_neo.sdk import FubonSDK

# --- 1. 系統安全驗證 ---
SYSTEM_PASSWORD = "lnp666" 
st.set_page_config(page_title="飆股量化分析系統 1150418", layout="wide")

if "login_status" not in st.session_state:
    st.session_state.login_status = False

def check_login():
    if st.session_state.password_input == SYSTEM_PASSWORD:
        st.session_state.login_status = True
    else:
        st.error("密碼錯誤，請重新輸入！")

if not st.session_state.login_status:
    st.title("🔐 系統安全檢查")
    st.text_input("請輸入系統存取密碼：", type="password", key="password_input", on_change=check_login)
    st.stop()

# --- 2. Google Sheets 自動紀錄功能 ---
def save_to_google_sheets(data_row):
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds_info = json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"])
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open(st.secrets["GOOGLE_SHEET_NAME"]).sheet1
        sheet.append_row(data_row)
        return True
    except Exception as e:
        st.error(f"❌ 寫入雲端試算表失敗，請檢查共用權限或 Secret 內容。")
        return False

# --- 3. 富邦 API 自動初始化 ---
st.sidebar.header("⚙️ 系統狀態")
try:
    fubon_user = st.secrets["FUBON_USER"]
    fubon_pass = st.secrets["FUBON_PASS"]
    cert_pass = st.secrets["CERT_PASS"]
    cert_base64 = st.secrets["FUBON_CERT_BASE64"]
except Exception:
    st.error("⚠️ 請至 Streamlit Secrets 設定金鑰！")
    st.stop()

# 還原憑證檔
cert_path = "temp_fubon_cert.pfx"
if not os.path.exists(cert_path):
    with open(cert_path, "wb") as f:
        f.write(base64.b64decode(cert_base64))

# 初始化 SDK 
if "fubon_sdk" not in st.session_state:
    try:
        sdk = FubonSDK()
        res = sdk.init(fubon_user, fubon_pass, cert_path, cert_pass)
        if res:
            st.session_state.fubon_sdk = sdk
            st.sidebar.success("✅ 富邦 API 連線成功")
        else:
            st.sidebar.error("❌ 富邦登入失敗")
            st.stop()
    except Exception as e:
        st.sidebar.error(f"API 異常: {e}")
        st.stop()

# --- 4. 核心量化分析區塊 ---
st.title("🚀 飆股量化分析系統 1150418")
stock_id = st.text_input("請輸入台股代號 (例如: 2330)", value="2330")
analyze_btn = st.button("啟動量化分析並儲存結果")

if analyze_btn:
    with st.spinner(f'正在分析 {stock_id} ...'):
        try:
            sdk = st.session_state.fubon_sdk
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            # 抓取 K 線資料 (抓近 60 天確保指標計算準確)
            kline_data = sdk.marketdata.historical_kline(stock_id, (datetime.now()-timedelta(days=60)).strftime("%Y%m%d"), datetime.now().strftime("%Y%m%d"))
            
            if kline_data:
                df = pd.DataFrame([vars(k) for k in kline_data])
                df[['close', 'open', 'high', 'low', 'volume']] = df[['close', 'open', 'high', 'low', 'volume']].astype(float)
                
                # A. 計算 KD 指標 (9, 3, 3)
                kd = ta.stoch(df['high'], df['low'], df['close'], k=9, d=3, smooth_k=3)
                df = pd.concat([df, kd], axis=1)
                
                curr = df.iloc[-1]
                prev = df.iloc[-2]
                avg_vol_5d = df['volume'].tail(5).mean()

                # --- 【分析項目一】：上影線與量能壓力 (25分) ---
                shadow_ratio = (curr.high - max(curr.close, curr.open)) / (curr.high - curr.low) if curr.high != curr.low else 0
                if shadow_ratio < 0.5:
                    score1, desc1 = 25, "無長上影線"
                elif curr.volume > avg_vol_5d:
                    score1, desc1 = 0, "長上影線伴隨爆量"
                else:
                    score1, desc1 = 15, "長上影線但量能正常"

                # --- 【分析項目二】：價格防守指標 (25分) ---
                if curr.close > prev.high:
                    score2, desc2 = 25, "力道延續 (過前高)"
                elif curr.close < prev.low:
                    score2, desc2 = 0, "支撐破裂 (破前低)"
                else:
                    score2, desc2 = 15, "區間震盪"

                # --- 【分析項目三】：KD 位階狀態 (20分) ---
                curr_k = curr['STOCHk_9_3_3']
                if curr_k < 20:
                    score3, desc3 = 20, f"低檔超賣 (K:{curr_k:.1f})"
                elif 20 <= curr_k < 50:
                    score3, desc3 = 15, f"中低位階 (K:{curr_k:.1f})"
                elif 50 <= curr_k < 80:
                    score3, desc3 = 10, f"中高位階 (K:{curr_k:.1f})"
                else:
                    score3, desc3 = 0, f"高檔過熱 (K:{curr_k:.1f})"

                # 總計
                total_score = score1 + score2 + score3
                
                # --- 介面呈現 ---
                st.subheader(f"📊 {stock_id} 綜合評分：{total_score} / 70 分")
                st.progress(total_score / 70)
                
                c1, c2, c3 = st.columns(3)
                c1.metric("上影線指標", f"{score1}分", desc1)
                c2.metric("價格防守", f"{score2}分", desc2)
                c3.metric("KD 位階", f"{score3}分", desc3)

                # --- 自動儲存至 Google 試算表 ---
                full_reason = f"{desc1} | {desc2} | {desc3}"
                record = [today_str, stock_id, total_score, full_reason]
                if save_to_google_sheets(record):
                    st.success("✅ 數據分析已永久存檔至 Google 試算表。")
            
        except Exception as e:
            st.error(f"分析過程發生錯誤: {e}")
