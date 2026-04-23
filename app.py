import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import base64
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fubon_neo.sdk import FubonSDK, Mode
from fubon_neo.constant import TimeInForce, OrderType, PriceType, MarketType

# --- 1. 系統安全性與頁面設定 ---
st.set_page_config(page_title="大家跟CHECHE一起賺大錢1.0", layout="wide")

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]:
        return True
    st.title("大家跟CHECHE一起賺大錢 1.0")
    password = st.text_input("請輸入系統授權碼", type="password")
    if st.button("登入"):
        if password == "lnp666":
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("授權碼錯誤。")
    return False

if not check_password():
    st.stop()

# --- 2. 富邦 API 初始化 ---
@st.cache_resource
def get_fubon_sdk():
    try:
        acc = st.secrets["fubon"]["account"]
        pwd = st.secrets["fubon"]["password"]
        api_key = st.secrets["fubon"]["api_key"]
        cert_b64 = st.secrets["fubon"]["cert_base64"]
        cert_pwd = st.secrets["fubon"]["cert_password"]

        with open("fubon_cert.pfx", "wb") as f:
            f.write(base64.b64decode(cert_b64))

        sdk = FubonSDK()
        sdk.login(acc, pwd, api_key)
        sdk.init_realtime(Mode.Simulation)
        return sdk
    except Exception as e:
        st.error(f"富邦 API 連線異常: {e}")
        return None

# --- 3. 背景記憶庫 (Google 試算表) ---
def silent_log_to_sheet(data_row):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_json = json.loads(st.secrets["google"]["service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Stock_Analysis_History").sheet1
        sheet.append_row(data_row)
    except:
        pass 

# --- 4. 核心運算：技術指標 (朱家泓 SOP) ---
def compute_technical_indicators(df):
    df['MA5'] = df['close'].rolling(5).mean()
    df['MA10'] = df['close'].rolling(10).mean()
    df['MA20'] = df['close'].rolling(20).mean()
    df['MA60'] = df['close'].rolling(60).mean()
    
    low_9 = df['low'].rolling(9).min()
    high_9 = df['high'].rolling(9).max()
    rsv = 100 * (df['close'] - low_9) / (high_9 - low_9)
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = ema12 - ema26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD'] = (df['DIF'] - df['DEA']) * 2
    
    df['VMA5'] = df['volume'].rolling(5).mean()
    return df

# --- 5. 核心量化分析邏輯 ---
def perform_full_analysis(symbol, cost, df):
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    veto_triggers = []
    if curr['close'] < curr['MA20'] and curr['MA20'] < prev['MA20']:
        veto_triggers.append("破下彎月線")
    if curr['close'] < curr['MA60'] and curr['MA60'] < prev['MA60']:
        veto_triggers.append("季線蓋頭反壓")
    if curr['MA5'] < curr['MA10'] and curr['MA10'] < curr['MA20'] and curr['MA20'] < prev['MA20']:
        veto_triggers.append("均線三線空頭排列")
    if curr['close'] < df['low'].iloc[-20:-1].min():
        veto_triggers.append("跌破前波低點")
    if curr['volume'] > curr['VMA5'] * 2 and curr['close'] < curr['open'] and curr['close'] < prev['close']:
        veto_triggers.append("高檔爆量長黑")

    if veto_triggers:
        return 0, f"【一票否決】原因：{', '.join(veto_triggers)}", "風險警告模式", [], {}

    if curr['MA20'] > prev['MA20'] and curr['close'] >= curr['MA20'] * 0.98:
        mode = "模式 B：多頭回檔模式"
        weights = {"趨勢": 35, "型態": 25, "量價": 20, "指標": 20}
    else:
        mode = "模式 A：盤整突破模式"
        weights = {"趨勢": 30, "型態": 35, "量價": 20, "指標": 15}

    scores = {"趨勢": 0, "型態": 0, "量價": 0, "指標": 0}
    details = []

    if curr['MA5'] > curr['MA10'] > curr['MA20']:
        scores["趨勢"] = weights["趨勢"]
        details.append(f"趨勢：多頭排列 (+{weights['趨勢']}分)")
    elif curr['close'] > curr['MA20']:
        scores["趨勢"] = weights["趨勢"] * 0.6
        details.append(f"趨勢：站上月線 (+{scores['趨勢']:.1f}分)")

    recent_high = df['high'].iloc[-20:-1].max()
    if curr['close'] > recent_high:
        scores["型態"] = weights["型態"]
        details.append(f"型態：突破前高 (+{weights['型態']}分)")
    else:
        scores["型態"] = weights["型態"] * 0.4
        details.append(f"型態：區間震盪 (+{scores['型態']:.1f}分)")

    if curr['volume'] > curr['VMA5'] * 1.5 and curr['close'] > curr['open']:
        scores["量價"] = weights["量價"]
        details.append(f"量價：帶量長紅 (+{weights['量價']}分)")
    else:
        scores["量價"] = weights["量價"] * 0.5
        details.append(f"量價：量能平穩 (+{scores['量價']:.1f}分)")

    if curr['K'] > curr['D'] and curr['MACD'] > 0:
        scores["指標"] = weights["指標"]
        details.append(f"指標：KD金叉且MACD雙多 (+{weights['指標']}分)")
    elif curr['K'] > curr['D']:
        scores["指標"] = weights["指標"] * 0.7
        details.append(f"指標：KD金叉 (+{scores['指標']:.1f}分)")

    total = sum(scores.values())
    conclusion = f"分析結論：{mode}。總分 {total:.1f}。{'積極關注' if total >= 80 else '分批佈局' if total >= 60 else '觀望為宜'}。"
    
    return total, conclusion, mode, details, scores

# --- 6. 介面呈現 ---
st.title("大家跟CHECHE一起賺大錢1.0")

with st.sidebar:
    st.write("### 系統狀態")
    sdk = get_fubon_sdk()
    if sdk:
        st.success("富邦 API：已連線")
    else:
        st.error("富邦 API：未連線")

input_raw = st.text_input("請輸入台股代號 (多筆用逗號隔開，可加成本價 @):", placeholder="例如: 2330, 3163@400")

if st.button("執行量化分析"):
    if not input_raw:
        st.warning("請輸入代號")
    else:
        entries = [e.strip() for e in input_raw.split(",")]
        for entry in entries:
            if "@" in entry:
                symbol, cost = entry.split("@")
            else:
                symbol, cost = entry, "未設定"
            
            with st.spinner(f"分析 {symbol} 中..."):
                # 模擬資料 (正式上線請替換為富邦 SDK 抓取邏輯)
                dates = pd.date_range(end=datetime.date.today(), periods=100)
                dummy_df = pd.DataFrame({
                    'date': dates,
                    'open': np.random.randn(100).cumsum() + 500,
                    'high': np.random.randn(100).cumsum() + 510,
                    'low': np.random.randn(100).cumsum() + 490,
                    'close': np.random.randn(100).cumsum() + 500,
                    'volume': np.random.randint(500, 2000, 100)
                })
                
                df_with_idx = compute_technical_indicators(dummy_df)
                total_score, summary, analysis_mode, detail_list, radar_data = perform_full_analysis(symbol, cost, df_with_idx)
                
                st.markdown(f"### 🔍 {symbol} 診斷報表 (成本: {cost})")
                
                c1, c2 = st.columns(2)
                with c1:
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
                    fig.add_trace(go.Candlestick(x=df_with_idx['date'], open=df_with_idx['open'], high=df_with_idx['high'], low=df_with_idx['low'], close=df_with_idx['close'], name="K線"), row=1, col=1)
                    fig.add_trace(go.Scatter(x=df_with_idx['date'], y=df_with_idx['MA20'], name="20MA"), row=1, col=1)
                    fig.add_trace(go.Bar(x=df_with_idx['date'], y=df_with_idx['volume'], name="成交量"), row=2, col=1)
                    fig.update_layout(height=400, xaxis_rangeslider_visible=False, margin=dict(t=0, b=0))
                    st.plotly_chart(fig, use_container_width=True)
                
                with c2:
                    if total_score > 0:
                        categories = list(radar_data.keys())
                        fig_radar = go.Figure()
                        fig_radar.add_trace(go.Scatterpolar(r=list(radar_data.values()), theta=categories, fill='toself'))
                        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 35])), height=400, margin=dict(t=30, b=30))
                        st.plotly_chart(fig_radar, use_container_width=True)
                    else:
                        st.error("觸發一票否決，不顯示雷達圖。")

                st.write(f"**分析模式：** {analysis_mode}")
                st.write(f"**判定結果：** {summary}")
                with st.expander("詳細給分說明"):
                    for d in detail_list:
                        st.write(f"• {d}")
                
                copy_text = f"【大家跟CHECHE一起賺大錢】\n標的：{symbol}\n模式：{analysis_mode}\n總分：{total_score}\n判定：{summary}\n" + "\n".join(detail_list)
                st.text_area("報告內容 (長按全選複製):", value=copy_text, height=120)
                
                silent_log_to_sheet([datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), symbol, cost, total_score, summary])

st.divider()
st.caption("免責聲明：系統僅供學術研究，不構成投資建議。")
