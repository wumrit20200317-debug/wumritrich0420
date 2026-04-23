import streamlit as st
import pandas as pd
import requests
import datetime
import plotly.graph_objects as go
import numpy as np

# 頁面設定
st.set_page_config(page_title="大家跟CHECHE一起賺大錢1.0", layout="wide")

# ==========================================
# 🔒 系統登入與 API 金鑰設定區塊
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("### 🔒 系統登入")
    sys_pwd = st.text_input("請輸入系統密碼", type="password")
    
    # 自動偵測是否已在 st.secrets 設定 FUGLE_API_KEY
    has_secret_api_key = "FUGLE_API_KEY" in st.secrets
    api_key_input = ""
    if not has_secret_api_key:
        api_key_input = st.text_input("偵測未設定隱藏金鑰，請手動輸入 Fugle API Key", type="password")
        
    if st.button("確認登入"):
        # 密碼設定，移除所有前端提示
        valid_passwords = ["lnp666", st.secrets.get("sys_password", "lnp666")]
        
        if sys_pwd in valid_passwords:
            st.session_state["authenticated"] = True
            # 儲存 API 金鑰至 Session
            st.session_state["api_key"] = st.secrets["FUGLE_API_KEY"] if has_secret_api_key else api_key_input
            st.rerun()
        else:
            st.error("密碼錯誤，請重新輸入！")
            
    st.stop() # 阻擋未登入者往下執行

# ==========================================
# 📊 主程式區塊
# ==========================================
st.title("大家跟CHECHE一起賺大錢1.0")

st.markdown("### 請輸入台股代號與股價")
st.info("提示：支援多筆查詢，請以逗號分隔。若要自訂股價請加上 @。例如：`2330, 2330@1050, 6532@70`")
user_input = st.text_input("輸入股號", "6532")

# --- 技術指標計算函數 (純 Pandas，無須套件) ---
def calculate_indicators(df):
    df['SMA5'] = df['close'].rolling(window=5).mean()
    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['VOL_SMA5'] = df['volume'].rolling(window=5).mean()
    
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    
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
                return None, "API 請求成功，但查無 K 線資料 (可能無此股號或該期間無交易)"
            df = pd.DataFrame(data)
            df = df.sort_values('date').reset_index(drop=True)
            return df, "success"
        elif response.status_code == 401:
            return None, "API 金鑰 (X-API-KEY) 錯誤或未輸入，授權失敗 (401)。"
        elif response.status_code == 404:
            return None, f"查無此代碼 (404)，請確認 {symbol} 是否為有效台股代號。"
        else:
            return None, f"API 回傳異常代碼: {response.status_code}，訊息: {response.text}"
    except Exception as e:
        return None, f"伺服器連線例外錯誤: {str(e)}"

# --- 系統分析模型：飆股量化評分邏輯 ---
def evaluate_stock(df, custom_price=None):
    latest = df.iloc[-1].copy()
    prev = df.iloc[-2].copy()
    
    if custom_price is not None:
        latest['close'] = float(custom_price)
        
    scores = {"均線趨勢": 0, "動能表現": 0, "MACD指標": 0, "KD指標": 0, "價格強弱": 0}
    reasons = {}

    # 1. 均線趨勢
    reason_1 = []
    if latest['close'] > latest['SMA20']:
        scores["均線趨勢"] += 10
        reason_1.append("股價在月線(SMA20)之上 (+10)")
    else:
        reason_1.append("股價在月線(SMA20)之下 (+0)")
    if latest['SMA20'] > prev['SMA20']:
        scores["均線趨勢"] += 10
        reason_1.append("月線上揚 (+10)")
    else:
        reason_1.append("月線下彎 (+0)")
    reasons["均線趨勢"] = "；".join(reason_1)

    # 2. 動能表現
    reason_2 = []
    if latest['volume'] > latest['VOL_SMA5']:
        scores["動能表現"] += 20
        reason_2.append("當日成交量大於5日均量，動能充足 (+20)")
    else:
        reason_2.append("當日成交量低於5日均量，動能偏弱 (+0)")
    reasons["動能表現"] = "；".join(reason_2)

    # 3. MACD指標
    reason_3 = []
    if latest['MACD'] > latest['MACD_Signal']:
        scores["MACD指標"] += 10
        reason_3.append("MACD > Signal (紅柱/多頭) (+10)")
    else:
        reason_3.append("MACD < Signal (綠柱/空頭) (+0)")
    if latest['MACD'] > 0:
        scores["MACD指標"] += 10
        reason_3.append("MACD在零軸之上 (+10)")
    else:
        reason_3.append("MACD在零軸之下 (+0)")
    reasons["MACD指標"] = "；".join(reason_3)

    # 4. KD指標
    reason_4 = []
    if latest['K'] > latest['D']:
        scores["KD指標"] += 10
        reason_4.append("K值大於D值，呈黃金交叉/多頭排列 (+10)")
    else:
        reason_4.append("K值小於D值，呈死亡交叉/空頭排列 (+0)")
    if 20 <= latest['K'] <= 80:
        scores["KD指標"] += 10
        reason_4.append("K值介於20~80健康區間 (+10)")
    elif latest['K'] > 80:
        scores["KD指標"] += 5
        reason_4.append("K值>80，可能有過熱/高檔鈍化風險 (+5)")
    else:
        reason_4.append("K值<20，處於低檔區 (+0)")
    reasons["KD指標"] = "；".join(reason_4)

    # 5. 價格強弱
    reason_5 = []
    if latest['close'] > latest['SMA5']:
        scores["價格強弱"] += 20
        reason_5.append("股價站上5日線，短期表現強勢 (+20)")
    else:
        reason_5.append("股價跌破5日線，短期表現轉弱 (+0)")
    reasons["價格強弱"] = "；".join(reason_5)

    total_score = sum(scores.values())
    
    if total_score >= 80: conclusion = "強烈偏多，各項指標均顯示強勢，符合飆股特徵。"
    elif total_score >= 60: conclusion = "偏多看待，部分指標轉強，可伺機觀察。"
    elif total_score >= 40: conclusion = "震盪整理，多空力道拉扯，建議觀望。"
    else: conclusion = "偏空弱勢，多數指標不佳，建議避開或降低持股。"

    return scores, reasons, total_score, conclusion

# --- 執行分析按鈕 ---
if st.button("開始分析", type="primary"):
    if user_input:
        raw_inputs = [x.strip() for x in user_input.split(',')]
        
        for item in raw_inputs:
            if not item: continue
                
            if '@' in item:
                symbol, price_str = item.split('@')
                try:
                    custom_price = float(price_str)
                except ValueError:
                    custom_price = None
            else:
                symbol = item
                custom_price = None
                
            st.markdown("---")
            st.subheader(f"📊 標的分析：{symbol}")
            
            with st.spinner(f"正在抓取 {symbol} 的資料..."):
                df, err_msg = fetch_stock_data(symbol, st.session_state["api_key"])
                
            if df is None or df.empty:
                st.error(f"❌ 無法取得 {symbol} 的歷史資料。")
                st.warning(f"系統偵錯訊息：{err_msg}")
                continue
            
            if len(df) < 20:
                st.error(f"❌ {symbol} 的歷史資料筆數不足以計算月線 (僅 {len(df)} 筆)。")
                continue
                
            df = calculate_indicators(df)
            scores, reasons, total_score, conclusion = evaluate_stock(df, custom_price)
            
            st.markdown("#### 雷達圖戰力分析")
            categories = list(scores.keys())
            values = list(scores.values())
            categories_plot = categories + [categories[0]]
            values_plot = values + [values[0]]
            
            fig = go.Figure(data=go.Scatterpolar(
                r=values_plot,
                theta=categories_plot,
                fill='toself',
                name=f'代號 {symbol}',
                line=dict(color='red')
            ))
            
            fig.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 20])),
                showlegend=False,
                margin=dict(l=40, r=40, t=20, b=20)
            )
            st.plotly_chart(fig, width="stretch")
            
            price_display = f"{custom_price}" if custom_price else f"{df.iloc[-1]['close']} (最新收盤價)"
            report_text = f"【大家跟CHECHE一起賺大錢1.0 - 標的：{symbol}】\n"
            report_text += f"設定股價：{price_display}\n\n"
            report_text += "[各指標給分原因及說明]\n"
            for cat in categories:
                report_text += f"- {cat} ({scores[cat]}/20)：{reasons[cat]}\n"
                
            report_text += "\n[綜合說明]\n"
            report_text += f"總分：{total_score}/100\n"
            report_text += f"判定：{conclusion}\n"
            
            st.markdown("#### 分析結果與判定理由 (點擊右上角圖示即可一鍵複製，支援 iOS)")
            st.code(report_text, language="markdown")
