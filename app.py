import streamlit as st
import pandas as pd
import os
import base64
import json
import gspread
import plotly.graph_objects as go
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
        st.error(f"❌ 寫入雲端試算表失敗，請檢查權限設定。")
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

# --- 4. 核心量化分析與視覺化區塊 ---
st.title("🚀 飆股量化分析系統 (朱家泓 SOP 全功能版)")
stock_id = st.text_input("請輸入台股代號 (例如: 2330)", value="2330")
analyze_btn = st.button("啟動量化分析並儲存結果")

if analyze_btn:
    with st.spinner(f'正在分析 {stock_id} 數據並生成圖表...'):
        try:
            sdk = st.session_state.fubon_sdk
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            # 抓取近 90 天 K 線資料
            kline_data = sdk.marketdata.historical_kline(stock_id, (datetime.now()-timedelta(days=90)).strftime("%Y%m%d"), datetime.now().strftime("%Y%m%d"))
            
            if kline_data:
                df = pd.DataFrame([vars(k) for k in kline_data])
                df[['close', 'open', 'high', 'low', 'volume']] = df[['close', 'open', 'high', 'low', 'volume']].astype(float)
                
                # 確保日期欄位存在，若無則使用 index
                x_axis = df['date'] if 'date' in df.columns else df.index

                # --- 運算指標 (純 pandas，不依賴外部套件) ---
                df['MA5'] = df['close'].rolling(window=5).mean()
                df['MA10'] = df['close'].rolling(window=10).mean()
                df['MA20'] = df['close'].rolling(window=20).mean()
                df['Vol_MA5'] = df['volume'].rolling(window=5).mean()
                
                low_min = df['low'].rolling(window=9, min_periods=1).min()
                high_max = df['high'].rolling(window=9, min_periods=1).max()
                rsv = (df['close'] - low_min) / (high_max - low_min) * 100
                df['K'] = rsv.rolling(window=3, min_periods=1).mean()
                df['D'] = df['K'].rolling(window=3, min_periods=1).mean()
                
                ema12 = df['close'].ewm(span=12, adjust=False).mean()
                ema26 = df['close'].ewm(span=26, adjust=False).mean()
                df['MACD'] = ema12 - ema26
                df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
                df['Hist'] = df['MACD'] - df['Signal']
                
                curr = df.iloc[-1]
                prev = df.iloc[-2]

                # --- 評分系統 ---
                # 1. 均線趨勢 (30分)
                if curr['close'] > curr['MA5'] and curr['MA5'] > curr['MA10'] and curr['MA10'] > curr['MA20']:
                    score1, desc1 = 30, "完美多頭排列"
                elif curr['MA5'] > curr['MA10'] or curr['MA10'] > curr['MA20']:
                    score1, desc1 = 15, "均線糾結"
                else:
                    score1, desc1 = 0, "空頭排列"

                # 2. 量價突破 (30分)
                if curr['close'] > prev['high'] and curr['volume'] > curr['Vol_MA5']:
                    score2, desc2 = 30, "帶量突破昨高"
                elif curr['close'] > prev['high']:
                    score2, desc2 = 15, "量縮過高"
                elif curr['close'] < prev['low']:
                    score2, desc2 = 0, "跌破昨低"
                else:
                    score2, desc2 = 10, "區間震盪"

                # 3. K線型態 (20分)
                total_range = curr['high'] - curr['low']
                shadow_ratio = (curr['high'] - max(curr['close'], curr['open'])) / total_range if total_range > 0 else 0
                if curr['close'] > curr['open'] and shadow_ratio < 0.3:
                    score3, desc3 = 20, "實體紅K"
                elif shadow_ratio >= 0.5:
                    score3, desc3 = 0, "長上影線"
                else:
                    score3, desc3 = 10, "普通K線"

                # 4. 指標共振 (20分)
                kd_bull = curr['K'] > curr['D']
                macd_bull = curr['Hist'] > 0
                if kd_bull and macd_bull:
                    score4, desc4 = 20, "雙指標偏多"
                elif kd_bull or macd_bull:
                    score4, desc4 = 10, "單一轉強"
                else:
                    score4, desc4 = 0, "指標轉弱"

                total_score = score1 + score2 + score3 + score4

                # ================= 介面展示 =================
                st.subheader(f"📊 {stock_id} 綜合評分：{total_score} / 100 分")
                st.progress(total_score / 100)
                
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("均線趨勢", f"{score1}/30分", desc1)
                c2.metric("量價突破", f"{score2}/30分", desc2)
                c3.metric("K線型態", f"{score3}/20分", desc3)
                c4.metric("指標共振", f"{score4}/20分", desc4)

                st.markdown("---")
                
                # --- 圖表區塊 ---
                col_chart, col_radar = st.columns([2, 1])

                with col_chart:
                    st.markdown("### 📈 近期 K 線與均線圖")
                    fig_k = go.Figure(data=[go.Candlestick(
                        x=x_axis, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='K線'
                    )])
                    fig_k.add_trace(go.Scatter(x=x_axis, y=df['MA5'], name='5MA', line=dict(color='blue', width=1)))
                    fig_k.add_trace(go.Scatter(x=x_axis, y=df['MA10'], name='10MA', line=dict(color='orange', width=1)))
                    fig_k.add_trace(go.Scatter(x=x_axis, y=df['MA20'], name='20MA', line=dict(color='green', width=1)))
                    fig_k.update_layout(margin=dict(l=0, r=0, t=30, b=0), xaxis_rangeslider_visible=False, height=400)
                    st.plotly_chart(fig_k, use_container_width=True)

                with col_radar:
                    st.markdown("### 🎯 六芒星戰力分析")
                    # 將各項分數轉換為 100% 比例以完美呈現雷達圖形狀
                    r_values = [(score1/30)*100, (score2/30)*100, (score3/20)*100, (score4/20)*100]
                    theta_labels = ['均線趨勢', '量價突破', 'K線型態', '指標共振']
                    
                    fig_radar = go.Figure(data=go.Scatterpolar(
                        r=r_values + [r_values[0]], # 閉合線條
                        theta=theta_labels + [theta_labels[0]],
                        fill='toself',
                        line_color='rgba(255, 65, 54, 1)',
                        fillcolor='rgba(255, 65, 54, 0.4)'
                    ))
                    fig_radar.update_layout(
                        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                        showlegend=False, margin=dict(l=40, r=40, t=30, b=30), height=400
                    )
                    st.plotly_chart(fig_radar, use_container_width=True)

                # --- 存檔 ---
                full_reason = f"{desc1} | {desc2} | {desc3} | {desc4}"
                record = [today_str, stock_id, total_score, full_reason]
                if save_to_google_sheets(record):
                    st.success("✅ 分析完成！數據與判定理由已寫入 Google 試算表。")

        except Exception as e:
            st.error(f"分析過程發生錯誤: {e}")
