import streamlit as st
import pandas as pd
import os
import base64
from datetime import datetime, timedelta
from fubon_neo.sdk import FubonSDK

# --- 系統設定 ---
SYSTEM_PASSWORD = "lnp666"

# --- 網頁介面設置 ---
st.set_page_config(page_title="飆股量化分析系統 1150418", layout="wide")

# --- 登入邏輯 ---
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

# --- 富邦 API 資安與自動連線區塊 ---
st.sidebar.header("⚙️ 系統狀態")

# 1. 讀取 Secrets 金鑰保險箱
try:
    fubon_user = st.secrets["FUBON_USER"]
    fubon_pass = st.secrets["FUBON_PASS"]
    cert_pass = st.secrets["CERT_PASS"]
    cert_base64 = st.secrets["FUBON_CERT_BASE64"]
except Exception:
    st.error("⚠️ 系統錯誤：尚未在 Streamlit Cloud 後台設定完整的富邦 API 帳密與憑證 Base64 (Secrets)！")
    st.stop()

# 2. 自動還原憑證 (從亂碼變回暫存的實體檔案供 API 讀取)
cert_path = "temp_fubon_cert.pfx"
if not os.path.exists(cert_path):
    with open(cert_path, "wb") as f:
        f.write(base64.b64decode(cert_base64))

# 3. 初始化富邦 SDK (無感登入)
if "fubon_sdk" not in st.session_state:
    try:
        sdk = FubonSDK()
        res = sdk.init(fubon_user, fubon_pass, cert_path, cert_pass)
        if res:
            st.session_state.fubon_sdk = sdk
            st.sidebar.success("✅ 富邦 API 連線成功 (自動授權)")
        else:
            st.sidebar.error("❌ 富邦 API 連線失敗，請檢查帳密或憑證密碼。")
            st.stop()
    except Exception as e:
        st.sidebar.error(f"登入發生異常: {e}")
        st.stop()

# --- 核心分析區塊 ---
st.title("🚀 飆股量化分析系統 1150418")
st.write("### 模組名稱：短線多頭健康度評估系統 (資料來源：富邦 API)")

col1, col2 = st.columns([1, 3])
with col1:
    stock_id = st.text_input("請輸入台股代號 (例如: 2330)", value="2330")
with col2:
    st.write("") 
    st.write("")
    analyze_btn = st.button("啟動量化分析")

st.write("---")

if analyze_btn:
    with st.spinner(f'正在透過富邦 API 抓取 {stock_id} K線與運算中...'):
        try:
            sdk = st.session_state.fubon_sdk
            
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=20)).strftime("%Y%m%d")
            
            kline_data = sdk.marketdata.historical_kline(stock_id, start_date, end_date)
            
            if not kline_data:
                st.error(f"找不到代號 {stock_id} 的資料，或該股票近期無交易。")
            else:
                df = pd.DataFrame([vars(k) for k in kline_data])
                df['close'] = df['close'].astype(float)
                df['open'] = df['open'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['volume'] = df['volume'].astype(float)
                
                df = df.sort_values(by='date').reset_index(drop=True)

                today_open = df['open'].iloc[-1]
                today_high = df['high'].iloc[-1]
                today_low = df['low'].iloc[-1]
                today_close = df['close'].iloc[-1]
                today_vol = df['volume'].iloc[-1]
                
                vol_5d_avg = df['volume'].tail(5).mean()

                # 分析項目一：上影線與量能壓力指標 (佔 25 分)
                if today_high == today_low:
                    upper_shadow_ratio = 0
                else:
                    upper_shadow_ratio = (today_high - max(today_close, today_open)) / (today_high - today_low)
                
                is_long_upper_shadow = upper_shadow_ratio >= 0.5
                is_huge_volume = today_vol > vol_5d_avg

                score_1 = 0
                reason_1 = ""
                if not is_long_upper_shadow:
                    score_1 = 25
                    reason_1 = "當日無長上影線（上影線比例 < 0.5）"
                elif is_long_upper_shadow and not is_huge_volume:
                    score_1 = 15
                    reason_1 = "出現長上影線，但成交量未超過 5 日均量"
                elif is_long_upper_shadow and is_huge_volume:
                    score_1 = 0
                    reason_1 = "出現長上影線且伴隨爆大量，上方賣壓極重"

                st.subheader(f"📊 {stock_id} 量化分析結果")
                st.write(f"最新收盤價: **{today_close:.2f}** | 今日成交量: **{today_vol:,.0f}** | 5日均量: **{vol_5d_avg:,.0f}**")
                
                st.metric(label="分析項目一：上影線與量能壓力指標", value=f"{score_1} / 25 分")
                
                if score_1 == 25:
                    st.success(f"給分理由：{reason_1} (上影線比例: {upper_shadow_ratio:.2f})")
                elif score_1 == 15:
                    st.warning(f"給分理由：{reason_1} (上影線比例: {upper_shadow_ratio:.2f})")
                else:
                    st.error(f"給分理由：{reason_1} (上影線比例: {upper_shadow_ratio:.2f})")

        except Exception as e:
            st.error(f"系統運算或 API 連線發生錯誤: {e}")
