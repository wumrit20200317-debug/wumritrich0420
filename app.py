import streamlit as st
import pandas as pd
import requests
import datetime
import plotly.graph_objects as go
import numpy as np

# 頁面設定
st.set_page_config(page_title="大家跟CHECHE一起賺大錢1.0", layout="wide")

# ==========================================
# 🔒 系統登入區塊 (僅保留密碼輸入)
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("### 🔒 系統登入")
    # 僅輸入系統密碼，移除所有提示與其他欄位
    sys_pwd = st.text_input("請輸入系統密碼", type="password")
    
    if st.button("確認登入"):
        # 密碼嚴格設定為 lnp666
        if sys_pwd == "lnp666":
            st.session_state["authenticated"] = True
            # 從系統後台 (Secrets) 讀取 API Key
            st.session_state["api_key"] = st.secrets.get("FUGLE_API_KEY", "")
            st.rerun()
        else:
            st.error("密碼錯誤，請重新輸入！")
            
    st.stop() # 阻擋未登入者

# 檢查 API Key 是否配置
if not st.session_state["api_key"]:
    st.error("系統錯誤：未偵測到 API 金鑰，請聯繫管理員於系統後台設定 FUGLE_API_KEY。")
    st.stop()

# ==========================================
# 📊 主程式區塊
# ==========================================
st.title("大家跟CHECHE一起賺大錢1.0")

st.markdown("### 請輸入台股代號與股價")
st.info("提示：支援多筆查詢，請以逗號分隔。若要自訂股價請加上 @。例如：`2330, 2330@1050, 6532@70`")
user_input = st.text_input("輸入股號", "2330")

# --- 技術指標計算函數 ---
def calculate_indicators(df):
    df['SMA5'] = df['close'].rolling(window=5).mean()
    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['VOL_SMA5'] = df['volume'].rolling(window=5).mean()
    
    # MACD 計算
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    
    # KD 計算
    min9 = df['low'].rolling(window=9).min()
    max9 = df['high'].rolling(window=9).max()
    rsv = (df['close'] - min9) / (max9 - min9) * 100
    rsv = rsv.fillna(50)
    
    k_vals = np.zeros(len(df))
    d_vals = np.zeros(len(df))
    k_vals[0], d_vals[0] = 50.0, 50.0
    
    for i in range(1, len(df)):
        k_vals[i] = (2/3) * k_vals[i-1] + (1/3) * rsv.iloc[i]
        d_vals[i] = (2/3) * d_vals[i-1] + (1/3) * k_vals[i]
        
    df['K'] = k_vals
    df['D'] = d_vals
    
    return df

# --- API 資料獲取函數 ---
def fetch_stock_data(symbol, api_key):
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=180)
    
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/historical/candles/{symbol}?from={start_date}&to={end_date}"
    headers = {"X-API-KEY": api_key}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json().get('data', [])
            if not data:
                return None, "查無 K 線資料"
            df = pd.DataFrame(data)
            df = df.sort_values('date').reset_index(drop=True)
            return df, "success"
        else:
            return None, f"API 錯誤 ({response.status_code})"
    except Exception as e:
        return None, str(e)

# --- 飆股量化分析模型 (SOP核心) ---
def evaluate_stock(df, custom_price=None):
    latest = df.iloc[-1].copy()
    prev = df.iloc[-2].copy()
    
    if custom_price is not None:
        latest['close'] = float(custom_price)
        
    scores = {"均線趨勢": 0, "動能表現": 0, "MACD指標": 0, "KD指標": 0, "價格強弱": 0}
    reasons = {}

    # 1. 均線趨勢 (20分)
    r1 = []
    if latest['close'] > latest['SMA20']:
        scores["均線趨勢"] += 10
        r1.append("股價在月線之上 (+10)")
    if latest['SMA20'] > prev['SMA20']:
        scores["均線趨勢"] += 10
        r1.append("月線上揚趨勢 (+10)")
    reasons["均線趨勢"] = "；".join(r1) if r1 else "趨勢偏弱"

    # 2. 動能表現 (20分)
    if latest['volume'] > latest['VOL_SMA5']:
        scores["動能表現"] = 20
        reasons["動能表現"] = "量增，動能充足 (+20)"
    else:
        reasons["動能表現"] = "縮量，動能不足 (+0)"

    # 3. MACD指標 (20分)
    r3 = []
    if latest['MACD'] > latest['MACD_Signal']:
        scores["MACD指標"] += 10
        r3.append("MACD紅柱/多頭交叉 (+10)")
    if latest['MACD'] > 0:
        scores["MACD指標"] += 10
        r3.append("處於零軸之上強勢區 (+10)")
    reasons["MACD指標"] = "；".join(r3) if r3 else "指標空頭排列"

    # 4. KD指標 (20分)
    r4 = []
    if latest['K'] > latest['D']:
        scores["KD指標"] += 10
        r4.append("K>D 黃金交叉 (+10)")
    if 20 <= latest['K'] <= 80:
        scores["KD指標"] += 10
        r4.append("KD位於健康擴張區 (+10)")
    elif latest['K'] > 80:
        scores["KD指標"] += 5
        r4.append("KD高檔鈍化 (+5)")
    reasons["KD指標"] = "；".join(r4) if r4 else "KD死亡交叉"

    # 5. 價格強弱 (20分)
    if latest['close'] > latest['SMA5']:
        scores["價格強弱"] = 20
        reasons["價格強弱"] = "站上5日線，短期轉強 (+20)"
    else:
        reasons["價格強弱"] = "跌破5日線，短期轉弱 (+0)"

    total_score = sum(scores.values())
    if total_score >= 80: conclusion = "🔥 強烈偏多，符合飆股特徵。"
    elif total_score >= 60: conclusion = "📈 偏多看待，趨勢轉強。"
    elif total_score >= 40: conclusion = "⚖️ 震盪整理，多空拉扯。"
    else: conclusion = "📉 偏空弱勢，建議保守避開。"

    return scores, reasons, total_score, conclusion

# --- 執行執行按鈕 ---
if st.button("開始分析", type="primary"):
    if user_input:
        raw_inputs = [x.strip() for x in user_input.split(',')]
        
        for item in raw_inputs:
            if not item: continue
            
            # 解析 @ 語法
            if '@' in item:
                symbol, price_str = item.split('@')
                try: custom_price = float(price_str)
                except: custom_price = None
            else:
                symbol = item
                custom_price = None
                
            st.markdown(f"### 🔍 標的分析：{symbol}")
            
            with st.spinner(f"資料抓取中..."):
                df, err_msg = fetch_stock_data(symbol, st.session_state["api_key"])
                
            if df is None:
                st.error(f"無法分析 {symbol}：{err_msg}")
                continue
                
            df = calculate_indicators(df)
            scores, reasons, total_score, conclusion = evaluate_stock(df, custom_price)
            
            # 雷達圖
            categories = list(scores.keys())
            values = list(scores.values())
            fig = go.Figure(data=go.Scatterpolar(
                r=values + [values[0]],
                theta=categories + [categories[0]],
                fill='toself',
                line=dict(color='red')
            ))
            fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 20])), showlegend=False)
            st.plotly_chart(fig, width="stretch")
            
            # 報告內容
            p_display = f"{custom_price}" if custom_price else f"{df.iloc[-1]['close']} (收盤價)"
            report = f"【大家跟CHECHE一起賺大錢1.0 - {symbol}】\n"
            report += f"設定參考價：{p_display}\n\n"
            report += "[各指標給分原因及說明]\n"
            for cat in categories:
                report += f"- {cat} ({scores[cat]}/20)：{reasons[cat]}\n"
            report += f"\n[綜合說明]\n總評分：{total_score}/100\n判定結果：{conclusion}\n"
            
            st.markdown("#### 分析結果 (支援 iOS 點擊複製)")
            st.code(report, language="markdown")
