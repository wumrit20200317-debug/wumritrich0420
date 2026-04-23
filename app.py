import streamlit as st
import time
import json
import google.generativeai as genai
import yfinance as yf
import plotly.graph_objects as go
import os
import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import urllib.request
import re

# 試算表套件
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    GSHEET_AVAILABLE = True
except ImportError:
    GSHEET_AVAILABLE = False

# 富邦 SDK 
try:
    from fubon_neo.sdk import FubonSDK, Mode
    FUBON_AVAILABLE = True
except ImportError:
    FUBON_AVAILABLE = False

# ==========================================
# 0. 頁面配置
# ==========================================
st.set_page_config(page_title="大家跟CHECHE一起賺大錢1.0", page_icon="🎯", layout="wide")

# ==========================================
# 1. 密碼大門邏輯 (Security Gate)
# ==========================================
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets.get("password", "lnp666"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title("🔐 大家跟CHECHE一起賺大錢1.0 - 認證登入")
        st.text_input("請輸入通關密碼：", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.title("🔐 大家跟CHECHE一起賺大錢1.0 - 認證登入")
        st.text_input("請輸入通關密碼：", type="password", on_change=password_entered, key="password")
        st.error("❌ 密碼錯誤，請重新輸入。")
        return False
    return True

if not check_password():
    st.stop()

# ==========================================
# 2. 金庫防錯與調度中心 (Secrets Helper)
# ==========================================
def get_secret_val(key_name, default=None):
    if key_name in st.secrets: return st.secrets[key_name]
    for k in st.secrets.keys():
        if key_name in k: return st.secrets[k]
    return default

# Gemini 金鑰讀取
API_KEYS = []
try:
    raw_keys = get_secret_val("api_keys")
    if raw_keys:
        if hasattr(raw_keys, "values"): API_KEYS = list(raw_keys.values())
        elif isinstance(raw_keys, list): API_KEYS = [str(k) for k in raw_keys]
        elif isinstance(raw_keys, str): API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
except: pass

if not API_KEYS:
    st.error("❌ 系統偵測不到有效的 Gemini API 金鑰，請確認 Secrets 設定。")
    st.stop()

if 'key_pool' not in st.session_state:
    st.session_state.key_pool = {i: datetime.now() for i in range(len(API_KEYS))}

# 富邦狀態偵測
fubon_cfg = get_secret_val("fubon")
fubon_status = "🟢 已連線" if fubon_cfg else "🔴 未連線 (Secret 缺失)"

with st.sidebar:
    st.header("🔌 系統狀態")
    st.write(f"富邦 API：{fubon_status}")
    if not fubon_cfg: st.caption("請確認 Secrets 中有 [fubon] 區塊")

# 本地暫存 (解決休眠前當次使用的顯示問題)
if 'db' not in st.session_state:
    st.session_state.db = {"manual_results": []}

# ==========================================
# 3. Google 試算表寫入引擎 (背景靜默執行)
# ==========================================
def write_to_gsheet_silent(data):
    if not GSHEET_AVAILABLE: return
    try:
        gcp_creds = get_secret_val("gcp")
        sheet_url = get_secret_val("gsheet_url")
        if not gcp_creds or not sheet_url: return
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(gcp_creds), scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url(sheet_url).sheet1
        
        # 整理要寫入的欄位 (時間, 代號, 名稱, 成本, 現價, 總分, 否決條件, AI結論)
        row = [
            data.get('timestamp', ''),
            data.get('resolved_ticker', ''),
            data.get('stock_name', ''),
            data.get('cost_price', ''),
            data.get('current_price', ''),
            data.get('total_score', ''),
            data.get('veto_alert', ''),
            data.get('conclusion', '')
        ]
        sheet.append_row(row)
    except Exception as e:
        # 靜默失敗，不干擾使用者主流程
        pass

# ==========================================
# 4. 數據與計算引擎 (yfinance)
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_chinese_name(tk):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        url = f"https://tw.stock.yahoo.com/quote/{tk}" if tk.isdigit() else f"https://hk.finance.yahoo.com/quote/{tk}"
        req = urllib.request.Request(url, headers=headers)
        html = urllib.request.urlopen(req, timeout=3).read().decode('utf-8')
        if tk.isdigit():
            match = re.search(r'<title>(.*?)\(', html)
            if match: return match.group(1).strip()
        else:
            match = re.search(r'<title>(.*?)\s+\(', html)
            if match: return match.group(1).replace('股票價格', '').replace('今日', '').strip()
    except: pass
    return "" 

@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_data(ticker):
    try:
        tk = ticker + ".TW" if ticker.isdigit() else ticker
        df = yf.Ticker(tk).history(period="1y")
        if df.empty and ticker.isdigit():
            df = yf.Ticker(ticker + ".TWO").history(period="1y")
        return df if not df.empty else None
    except: return None

def calculate_ta(df):
    try:
        c = df['Close'].iloc[-1]
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma20_yest = df['Close'].rolling(20).mean().iloc[-2]
        ma60 = df['Close'].rolling(60).mean().iloc[-1]
        ma60_yest = df['Close'].rolling(60).mean().iloc[-2]
        vol = df['Volume'].iloc[-1]
        vol5ma = df['Volume'].rolling(5).mean().iloc[-1]
        h20 = df['High'].tail(20).max()
        l20 = df['Low'].tail(20).min()
        
        low_9 = df['Low'].rolling(9).min()
        high_9 = df['High'].rolling(9).max()
        rsv = (df['Close'] - low_9) / (high_9 - low_9) * 100
        k = rsv.ewm(alpha=1/3).mean().iloc[-1]
        d = k # 簡化
        
        return {
            "C": round(c, 2), "MAs": [round(ma5,2), ma20, ma60],
            "T20": 1 if ma20 > ma20_yest else 0, "T60": 1 if ma60 > ma60_yest else 0,
            "Vol": vol, "Vol5": vol5ma, "H20": h20, "L20": l20, "K": k, "D": d
        }
    except: return None

def get_scores(ta):
    scores = {"MA": 0, "Pattern": 0, "Vol": 0, "KD": 0}
    vetos = []
    
    # 否決邏輯
    if ta['C'] < ta['MAs'][1] and ta['T20'] == 0: vetos.append("股價跌破月線且下彎")
    if ta['C'] < ta['L20']: vetos.append("股價跌破前波低點")
    
    # 給分原因 (100滿分配置)
    if ta['C'] > ta['MAs'][0]: scores["MA"] = 25
    if ta['Vol'] > ta['Vol5']: scores["Vol"] = 25
    if ta['K'] > ta['D']: scores["KD"] = 25
    if ta['C'] >= ta['H20'] * 0.95: scores["Pattern"] = 25
    
    total = sum(scores.values())
    radar = [scores["MA"], scores["Pattern"], 10, scores["Vol"], 10, 10, scores["KD"], 10]
    return total, radar, vetos

# ==========================================
# 5. AI 調度 (Gemini 引擎)
# ==========================================
SYS_INSTRUCT = """你是專業的波段量化分析師。嚴格回傳純JSON。鍵值：
{"trading_plan": {"buy_zone":"建議買區","stop_loss":"停損價位","take_profit":"停利預估","risk_reward_eval":"風報比簡評"}, 
"conclusion": "針對目前得分與狀態，給出綜合操作說明"}"""

def ask_gemini(prompt_data):
    num_keys = len(API_KEYS)
    for attempt in range(num_keys * 2): 
        idx = attempt % num_keys
        genai.configure(api_key=API_KEYS[idx])
        model = genai.GenerativeModel('gemini-2.5-flash', system_instruction=SYS_INSTRUCT)
        try:
            res = model.generate_content(prompt_data, generation_config=genai.types.GenerationConfig(temperature=0.0))
            raw = res.text
            parsed = json.loads(raw[raw.find('{'):raw.rfind('}')+1])
            return parsed
        except: time.sleep(1); continue
    return {"conclusion": "AI 分析暫時無法取得，請稍後再試。", "trading_plan": {}}

# ==========================================
# 6. UI 渲染
# ==========================================
def plot_kline(df, cost=None):
    try:
        df['5MA'], df['20MA'], df['60MA'] = [df['Close'].rolling(w).mean() for w in [5, 20, 60]]
        df = df.tail(60)
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='日K')])
        for ma, color, n in [(df['5MA'], 'blue', '5MA'), (df['20MA'], 'green', '20MA'), (df['60MA'], 'purple', '60MA')]:
            fig.add_trace(go.Scatter(x=df.index, y=ma, line=dict(color=color, width=1.5), name=n))
        if cost: fig.add_hline(y=cost, line_dash="dash", line_color="red", annotation_text=f"成本: {cost}")
        fig.update_layout(height=350, margin=dict(l=0,r=0,t=20,b=0), xaxis_rangeslider_visible=False)
        return fig
    except: return None

def plot_radar(scores):
    cats = ['均線', '型態', '支撐', '價量', '主流', 'MACD', 'KD', '乖離']
    fig = go.Figure(data=go.Scatterpolar(r=scores, theta=cats, fill='toself'))
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20), polar=dict(radialaxis=dict(visible=True, range=[0, 30])))
    return fig

# ==========================================
# 7. 主程式執行區
# ==========================================
st.title("🎯 大家跟CHECHE一起賺大錢1.0")
st.info("💡 輸入代號(如 `2330`)，持股加成本(如 `3163@400`)，逗號可批次輸入。")

user_in = st.text_input("請輸入診斷清單：", placeholder="例如: 2330, 2454@1000")

if st.button("🚀 啟動診斷", type="primary", use_container_width=True):
    tickers = [t.strip() for t in user_in.split(",") if t.strip()]
    if not tickers: st.warning("請先輸入股號！")
    else:
        for tk_raw in tickers:
            tk, cost = (tk_raw.split("@")[0].upper(), float(tk_raw.split("@")[1])) if "@" in tk_raw else (tk_raw.upper(), None)
            df = get_stock_data(tk)
            if df is not None:
                ta = calculate_ta(df)
                total_s, radar_s, vetos = get_scores(ta)
                name = get_chinese_name(tk)
                
                mini_prompt = f'{{"T":"{tk}","C":{ta["C"]},"Score":{total_s},"Vetos":{vetos}}}'
                ai_res = ask_gemini(mini_prompt)
                
                res_data = {
                    "resolved_ticker": tk, "stock_name": name, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_score": total_s, "radar_scores": radar_s, "veto_alert": "；".join(vetos) if vetos else "無", 
                    "current_price": ta['C'], "cost_price": cost,
                    "conclusion": ai_res.get("conclusion", ""), "trading_plan": ai_res.get("trading_plan", {})
                }
                
                # 1. 存入本地畫面顯示
                st.session_state.db["manual_results"].insert(0, res_data)
                # 2. 靜默寫入 Google 試算表 (做為永久回測留存)
                write_to_gsheet_silent(res_data)
                
        st.rerun()

# 顯示紀錄
for i, item in enumerate(st.session_state.db["manual_results"]):
    tk, name, cost, price = item['resolved_ticker'], item['stock_name'], item['cost_price'], item['current_price']
    pnl_tag = f"&nbsp;&nbsp;<span style='color:{'#ff4b4b' if price>=cost else '#00cc96'}; font-weight:bold;'>【帳面: {'+' if price>=cost else ''}{round((price-cost)/cost*100, 2)}%】</span>" if cost else ""
    
    with st.expander(f"📌 {tk} {name} (現價: {price})", expanded=(i==0)):
        st.markdown(f"🕒 *時間: {item['timestamp']}* {pnl_tag}", unsafe_allow_html=True)
        
        if item['veto_alert'] != "無": st.error(f"🚫 否決條件：{item['veto_alert']}")
        st.markdown(f"<h1 style='text-align:center;'>{item['total_score']} / 100</h1>", unsafe_allow_html=True)
        st.info(f"**📝 綜合說明：** {item['conclusion']}")
        
        c_left, c_right = st.columns([1, 1])
        with c_left:
            p = item['trading_plan']
            if p:
                st.warning(f"買區: {p.get('buy_zone')}\n\n停損: {p.get('stop_loss')}\n\n停利: {p.get('take_profit')}\n\n風報: {p.get('risk_reward_eval')}")
            
            # 一鍵複製 (去除贅字)
            copy_txt = f"代號: {tk} {name}\n總分: {item['total_score']}\n現價: {price}\n說明: {item['conclusion']}\n否決: {item['veto_alert']}"
            st.markdown("<br>**📋 長按全選複製報告：**", unsafe_allow_html=True)
            st.code(copy_txt, language="markdown")
            
        with c_right:
            st.plotly_chart(plot_radar(item['radar_scores']), use_container_width=True)
            df_k = get_stock_data(tk)
            if df_k is not None: st.plotly_chart(plot_kline(df_k, cost), use_container_width=True)
            
if st.button("🗑️ 清空畫面紀錄"):
    st.session_state.db = {"manual_results": []}
    st.rerun()