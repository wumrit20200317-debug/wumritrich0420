import streamlit as st
import pandas as pd
import os
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

# --- 富邦 API 資安與連線區塊 ---
st.sidebar.header("⚙️ 系統與 API 設定")

# 1. 檢查是否已在 Streamlit Secrets 設定帳密
try:
    fubon_user = st.secrets["FUBON_USER"]
    fubon_pass = st.secrets["FUBON_PASS"]
    cert_pass = st.secrets["CERT_PASS"]
except Exception:
    st.error("⚠️ 系統錯誤：尚未在 Streamlit Cloud 後台設定富邦 API 帳密 (Secrets)！請先完成設定。")
    st.stop()

# 2. 憑證上傳機制 (避免憑證放 GitHub 被盜用)
cert_file = st.sidebar.file_uploader("請上傳您的富邦憑證 (.pfx)", type=['pfx'])
if cert_file is not None:
    with open("fubon_cert.pfx", "wb") as f:
        f.write(cert_file.getbuffer())
    st.sidebar.success("憑證已暫存於雲端！")

if not os.path.exists("fubon_cert.pfx"):
    st.warning("👈 請先在左側選單上傳您的【富邦憑證 (.pfx)】才能連線抓取資料。")
    st.stop()

# 3. 初始化富邦 SDK
if "fubon_sdk" not in st.session_state:
    try:
        sdk = FubonSDK()
        # 進行登入
        res = sdk.init(fubon_user, fubon_pass, "fubon_cert.pfx", cert_pass)
        if res:
            st.session_state.fubon_sdk = sdk
            st.sidebar.success("✅ 富邦 API 連線成功")
        else:
            st.sidebar.error("❌ 富邦 API 連線失敗，請檢查帳密或憑證。")
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
            
            # 設定抓取時間範圍 (抓過去 20 天以確保有至少 5 個交易日可算均量)
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=20)).strftime("%Y%m%d")
            
            # 抓取歷史 K 線
            kline_data = sdk.marketdata.historical_kline(stock_id, start_date, end_date)
            
            if not kline_data:
                st.error(f"找不到代號 {stock_id} 的資料，或該股票近期無交易。")
            else:
                # 整理富邦回傳的資料結構
                df = pd.DataFrame([vars(k) for k in kline_data])
                df['close'] = df['close'].astype(float)
                df['open'] = df['open'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['volume'] = df['volume'].astype(float)
                
                # 確保照時間排序
                df = df.sort_values(by='date').reset_index(drop=True)

                # 提取最新一日的數據
                today_open = df['open'].iloc[-1]
                today_high = df['high'].iloc[-1]
                today_low = df['low'].iloc[-1]
                today_close = df['close'].iloc[-1]
                today_vol = df['volume'].iloc[-1]
                
                # 計算過去 5 日平均成交量 (不含今日，或含今日皆可，此處採最後 5 筆)
                vol_5d_avg = df['volume'].tail(5).mean()

                # 分析項目一：上影線與量能壓力指標 (佔 25 分)
                if today_high == today_low:
                    upper_shadow_ratio = 0
                else:
                    upper_shadow_ratio = (today_high - max(today_close, today_open)) / (today_high - today_low)
                
                is_long_upper_shadow = upper_shadow_ratio >= 0.5
                is_huge_volume = today_vol > vol_5d_avg

                # 評分邏輯
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

                # 輸出結果
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
