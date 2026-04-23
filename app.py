import streamlit as st
import pandas as pd
import requests
import datetime
import plotly.graph_objects as go
import numpy as np

# 頁面設定
st.set_page_config(page_title="大家跟CHECHE一起賺大錢1.0", layout="wide")

# 標題
st.title("大家跟CHECHE一起賺大錢1.0")

# 輸入區塊 (支援多筆輸入與自訂股價)
st.markdown("### 請輸入台股代號與股價")
st.info("提示：支援多筆查詢，請以逗號分隔。若要自訂股價請加上 @。例如：`2330, 2330@1050, 6532@70`")
user_input = st.text_input("輸入股號", "2330")

# --- 技術指標計算函數 (不使用 pandas_ta) ---
def calculate_indicators(df):
    # 均線
    df['SMA5'] = df['close'].rolling(window=5).mean()
    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['VOL_SMA5'] = df['volume'].rolling(window=5).mean()
    
    # MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    
    # KD
    min9 = df['low'].rolling(window=9).min()
    max9 = df['high'].rolling(window=9).max()
    rsv = (df['close'] - min9) / (max9 - min9) * 100
    rsv = rsv.fillna(50)
    
    df['K'] = 50.0
    df['D'] = 50.0
    k_vals = [50.0]
    d_vals = [50.0]
    
    # 遞迴計算 KD
    for i in range(1, len(rsv)):
        k = (2/3) * k_vals[-1] + (1/3) * rsv.iloc[i]
        d = (2/3) * d_vals[-1] + (1/3) * k
        k_vals.append(k)
        d_vals.append(d)
        
    df['K'] = k_vals
    df['D'] = d_vals
    
    return df

# --- API 資料獲取函數 ---
def fetch_stock_data(symbol):
    # 計算日期區間 (過去半年)
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=180)
    
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/historical/candles/{symbol}?from={start_date}&to={end_date}"
    headers = {"X-API-KEY": st.secrets.get("FUGLE_API_KEY", "")} # 如果沒有設定金鑰，請確認您的 API 授權方式
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json().get('data', [])
            if not data:
                return None
            df = pd.DataFrame(data)
            df = df.sort_values('date').reset_index(drop=True)
            return df
        else:
            return None
    except Exception as e:
        return None

# --- 評分邏輯函數 ---
def evaluate_stock(df, custom_price=None):
    latest = df.iloc[-1].copy()
    prev = df.iloc[-2].copy()
    
    # 若有自訂股價，覆蓋最後一筆的收盤價
    if custom_price is not None:
        latest['close'] = float(custom_price)
        
    scores = {
        "均線趨勢": 0,
        "動能表現": 0,
        "MACD指標": 0,
        "KD指標": 0,
        "價格強弱": 0
    }
    
    reasons = {}

    # 1. 均線趨勢 (滿分20)
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

    # 2. 動能表現 (滿分20)
    reason_2 = []
    if latest['volume'] > latest['VOL_SMA5']:
        scores["動能表現"] += 20
        reason_2.append("當日成交量大於5日均量，動能充足 (+20)")
    else:
        reason_2.append("當日成交量低於5日均量，動能偏弱 (+0)")
    reasons["動能表現"] = "；".join(reason_2)

    # 3. MACD指標 (滿分20)
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

    # 4. KD指標 (滿分20)
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

    # 5. 價格強弱 (滿分20)
    reason_5 = []
    if latest['close'] > latest['SMA5']:
        scores["價格強弱"] += 20
        reason_5.append("股價站上5日線，短期表現強勢 (+20)")
    else:
        reason_5.append("股價跌破5日線，短期表現轉弱 (+0)")
    reasons["價格強弱"] = "；".join(reason_5)

    total_score = sum(scores.values())
    
    # 綜合判定
    if total_score >= 80:
        conclusion = "強烈偏多，各項指標均顯示強勢，符合飆股特徵。"
    elif total_score >= 60:
        conclusion = "偏多看待，部分指標轉強，可伺機觀察。"
    elif total_score >= 40:
        conclusion = "震盪整理，多空力道拉扯，建議觀望。"
    else:
        conclusion = "偏空弱勢，多數指標不佳，建議避開或降低持股。"

    return scores, reasons, total_score, conclusion

# --- 主程式執行區塊 ---
if st.button("開始分析", type="primary"):
    if user_input:
        # 處理多筆輸入
        raw_inputs = [x.strip() for x in user_input.split(',')]
        
        for item in raw_inputs:
            if not item:
                continue
                
            # 解析股號與自訂股價
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
            
            # 取得資料
            with st.spinner(f"正在抓取 {symbol} 的資料..."):
                df = fetch_stock_data(symbol)
                
            if df is None or df.empty:
                st.error(f"無法取得 {symbol} 的歷史資料，請確認股號是否正確或 API 是否正常運作。")
                continue
                
            # 計算指標與評分
            df = calculate_indicators(df)
            scores, reasons, total_score, conclusion = evaluate_stock(df, custom_price)
            
            # 雷達圖戰力分析
            st.markdown("#### 雷達圖戰力分析")
            
            categories = list(scores.keys())
            values = list(scores.values())
            # 閉合雷達圖
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
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 20])
                ),
                showlegend=False,
                margin=dict(l=40, r=40, t=20, b=20)
            )
            st.plotly_chart(fig, use_container_width=True) # Plotly 內部圖表縮放仍依賴此設定，無礙
            
            # 生成說明文字 (可一鍵複製)
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
            # st.code 區塊自帶原生複製按鈕，iOS 可完美支援
            st.code(report_text, language="markdown")
