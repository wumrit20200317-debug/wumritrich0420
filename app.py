import streamlit as st
import time
import json
from google import genai
from google.genai import types
import plotly.graph_objects as go
import os
import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import urllib.request
import re
import base64
from fubon_neo.sdk import FubonSDK, Mode

# ==========================================
# 1. 密碼大門邏輯 (Security Gate)
# ==========================================
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"] 
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title("🔐 股票學術交流站 - 認證登入")
        st.text_input("請輸入通關密碼：", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.title("🔐 股票學術交流站 - 認證登入")
        st.text_input("請輸入通關密碼：", type="password", on_change=password_entered, key="password")
        st.error("❌ 密碼錯誤，請重新輸入。")
        return False
    return True

if not check_password():
    st.stop()

# ==========================================
# 2. 富邦 API 初始化與連線 
# ==========================================
def init_fubon():
    if "fubon_sdk" not in st.session_state:
        try:
            if "FUBON_USER" in st.secrets:
                cert_content = base64.b64decode(st.secrets["FUBON_CERT_BASE64"])
                with open("fubon_cert.pfx", "wb") as f:
                    f.write(cert_content)
                sdk = FubonSDK()
                sdk.login(st.secrets["FUBON_USER"], st.secrets["FUBON_PASS"], "fubon_cert.pfx", st.secrets["CERT_PASS"])
                st.session_state.fubon_sdk = sdk
                st.session_state.fubon_status = "🟢 富邦 API 已連線"
            else:
                st.session_state.fubon_status = "🔴 富邦 API 未配置 (請檢查 Secrets)"
        except Exception as e:
            st.session_state.fubon_status = f"🔴 富邦 API 連線失敗: {str(e)}"

init_fubon()

# ==========================================
# 3. 智能調度中心 (API 最省邏輯)
# ==========================================
try:
    raw_keys = st.secrets["api_keys"]
    if isinstance(raw_keys, str):
        API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
    else:
        API_KEYS = list(raw_keys)
    if not API_KEYS: raise ValueError("金鑰為空")
except Exception:
    st.error("❌ 金庫 (Secrets) 尚未正確配置。")
    st.stop()

st.set_page_config(page_title="大家跟CHECHE一起賺大錢 1.0", page_icon="🎯", layout="wide")

if 'key_pool' not in st.session_state:
    st.session_state.key_pool = {i: datetime.now() for i in range(len(API_KEYS))}

HISTORY_FILE = "system_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f: return {"manual_results": json.load(f).get('manual_results', [])}
        except: pass
    return {"manual_results": []}

def save_history(manual_data):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f: json.dump({"manual_results": manual_data}, f, ensure_ascii=False, indent=4)
    except: pass

if 'db' not in st.session_state: st.session_state.db = load_history()

def delete_record(index):
    if 0 <= index < len(st.session_state.db['manual_results']):
        st.session_state.db['manual_results'].pop(index)
        save_history(st.session_state.db['manual_results'])

# ==========================================
# 4. 爬蟲與大數據精算 (替換為富邦 API)
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_top_50_volume():
    try:
        url = "https://tw.stock.yahoo.com/rank/volume"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        req = urllib.request.Request(url, headers=headers)
        html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8')
        matches = re.findall(r'href="/quote/(\d{4,5})', html)
        tickers = list(dict.fromkeys(matches))[:50]
        return tickers
    except Exception:
        return []

@st.cache_data(ttl=3600, show_spinner=False)
def get_chinese_name(tk):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        url = f"https://tw.stock.yahoo.com/quote/{tk}" if tk.isdigit() else f"https://hk.finance.yahoo.com/quote/{tk}"
        req = urllib.request.Request(url, headers=headers)
        html = urllib.request.urlopen(req, timeout=3).read().decode('utf-8')
        match = re.search(r'<title>(.*?)\(', html) if tk.isdigit() else re.search(r'<title>(.*?)\s+\(', html)
        if match: return match.group(1).replace('股票價格', '').replace('今日', '').strip()
    except: pass
    return "" 

@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_data(ticker):
    # 💯 核心修改：使用富邦 API 抓取歷史 K 線資料
    if "fubon_sdk" not in st.session_state or st.session_state.fubon_sdk is None:
        return None
    try:
        sdk = st.session_state.fubon_sdk
        reststock = sdk.marketdata.rest_client.stock
        
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        
        symbol = ticker.replace('.TW', '').replace('.TWO', '')
        response = reststock.historical.candles(**{"symbol": symbol, "from": start_date, "to": end_date})
        
        if hasattr(response, 'get') and 'data' in response: data = response['data']
        elif isinstance(response, list): data = response
        else: data = response
            
        df = pd.DataFrame(data)
        if df.empty: return None
        
        rename_map = {}
        for col in df.columns:
            if col.lower() == 'date': rename_map[col] = 'Date'
            elif col.lower() == 'open': rename_map[col] = 'Open'
            elif col.lower() == 'high': rename_map[col] = 'High'
            elif col.lower() == 'low': rename_map[col] = 'Low'
            elif col.lower() == 'close': rename_map[col] = 'Close'
            elif col.lower() == 'volume': rename_map[col] = 'Volume'
            
        df.rename(columns=rename_map, inplace=True)
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        df.sort_index(ascending=True, inplace=True)
        
        if len(df) < 60: return None
        return df
    except Exception:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def get_market_return(is_tw):
    # 💯 核心修改：使用富邦 API 抓取台灣加權指數 (IX0001)
    if "fubon_sdk" not in st.session_state or st.session_state.fubon_sdk is None:
        return 0
    try:
        sdk = st.session_state.fubon_sdk
        reststock = sdk.marketdata.rest_client.stock
        
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        symbol = "IX0001" 
        
        response = reststock.historical.candles(**{"symbol": symbol, "from": start_date, "to": end_date})
        
        if hasattr(response, 'get') and 'data' in response: data = response['data']
        elif isinstance(response, list): data = response
        else: data = response
            
        df = pd.DataFrame(data)
        if df.empty or len(df) < 10: return 0
            
        close_col = [c for c in df.columns if c.lower() == 'close']
        date_col = [c for c in df.columns if c.lower() == 'date']
        
        if date_col:
            df[date_col[0]] = pd.to_datetime(df[date_col[0]])
            df.sort_values(date_col[0], ascending=True, inplace=True)
            
        if close_col:
            closes = df[close_col[0]]
            return (closes.iloc[-1] - closes.iloc[-10]) / closes.iloc[-10] * 100
        return 0
    except Exception: 
        return 0

def calculate_technical_data(df, market_ret):
    try:
        close = df['Close'].iloc[-1]
        open_p = df['Open'].iloc[-1]
        ma5, ma10, ma20, ma60 = [df['Close'].rolling(w).mean().iloc[-1] for w in [5, 10, 20, 60]]
        ma20_yest = df['Close'].rolling(20).mean().iloc[-2]
        ma60_yest = df['Close'].rolling(60).mean().iloc[-2]
        
        vol = df['Volume'].iloc[-1]
        vol_5ma = df['Volume'].rolling(5).mean().iloc[-1]
        
        high_20 = df['High'].tail(20).max()
        low_20 = df['Low'].tail(20).min()
        low_20_yest = df['Low'].iloc[-21:-1].min() if len(df) >= 21 else df['Low'].min()
        
        exp1, exp2 = df['Close'].ewm(span=12, adjust=False).mean(), df['Close'].ewm(span=26, adjust=False).mean()
        dif, dea = (exp1 - exp2), (exp1 - exp2).ewm(span=9, adjust=False).mean()
        osc = dif - dea
        osc_yest = osc.iloc[-2]
        
        low_9, high_9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
        rsv = (df['Close'] - low_9) / (high_9 - low_9) * 100
        k = rsv.ewm(alpha=1/3).mean()
        d = k.ewm(alpha=1/3).mean()
        k_yest = k.iloc[-2]
        
        rs = ((df.tail(10)['Close'].iloc[-1] - df.tail(10)['Close'].iloc[0])/df.tail(10)['Close'].iloc[0]*100) - market_ret
        bias20 = (close - ma20)/ma20*100
        
        return {
            "C": round(close, 2), "O": round(open_p, 2), "MAs": [round(ma5,2), round(ma10,2), round(ma20,2), round(ma60,2)],
            "T20": 1 if ma20 > ma20_yest else 0, "T60": 1 if ma60 > ma60_yest else 0, 
            "BIAS": round(bias20, 2), "RS": round(rs, 2), 
            "Vol": vol, "Vol5": vol_5ma,
            "H20": round(high_20, 2), "L20": round(low_20, 2), "L20_Y": round(low_20_yest, 2),
            "DIF": round(dif.iloc[-1], 2), "DEA": round(dea.iloc[-1], 2), "OSC": round(osc.iloc[-1], 2), "OSC_Y": round(osc_yest, 2),
            "K": round(k.iloc[-1], 2), "D": round(d.iloc[-1], 2), "K_Y": round(k_yest, 2)
        }
    except: return None

# ==========================================
# 5. 鐵血計分引擎 (雷達圖資料)
# ==========================================
def get_python_scores(ta):
    scores = {}
    breakdown = {}
    vetos = []
    
    C, MAs, T20, T60 = ta["C"], ta["MAs"], ta["T20"], ta["T60"]
    
    if C < MAs[2] and T20 == 0: vetos.append("跌破下彎月線")
    if C < ta["L20_Y"]: vetos.append("跌破近20日低點")
    if C < ta["O"] and ta["Vol"] > ta["Vol5"] * 2.5: vetos.append("高檔爆量長黑出貨")
    if C < MAs[3] and T60 == 0: vetos.append("季線下彎蓋頭壓")
    if ta["DIF"] < 0 and ta["DEA"] < 0 and ta["DIF"] < ta["DEA"] and ta["OSC"] < ta["OSC_Y"]: vetos.append("MACD零軸下死叉")
    if MAs[0] < MAs[1] < MAs[2]: vetos.append("三線空頭排列")

    veto_str = "；".join(vetos) if vetos else "無"

    # 1. 均線(15)
    if C > MAs[0] > MAs[1] > MAs[2] > MAs[3]: scores["MA"] = 15; breakdown["均線"] = "標準多頭排列"
    elif C > MAs[2] and T20 == 1: scores["MA"] = 10; breakdown["均線"] = "穩站上彎月線"
    elif T20 == 1: scores["MA"] = 5; breakdown["均線"] = "跌破月線但趨勢仍向上"
    else: scores["MA"] = 0; breakdown["均線"] = "跌破下彎月線"
    
    # 2. 型態(15) 
    if C >= ta["H20"]: scores["Pattern"] = 15; breakdown["型態"] = "創20日新高"
    elif C >= ta["H20"] * 0.97: scores["Pattern"] = 10; breakdown["型態"] = "逼近前高"
    elif C >= (ta["H20"] + ta["L20"])/2: scores["Pattern"] = 5; breakdown["型態"] = "箱型中軸之上"
    else: scores["Pattern"] = 0; breakdown["型態"] = "弱勢整理"
    
    # 3. 壓力(10)
    if C > MAs[3]: scores["Support"] = 10; breakdown["壓力"] = "站上季線具支撐"
    else: scores["Support"] = 0; breakdown["壓力"] = "季線之下長線壓力重"
    
    # 4. 價量(15)
    if C > ta["O"] and ta["Vol"] > ta["Vol5"] * 1.5: scores["Volume"] = 15; breakdown["價量"] = "帶量收紅"
    elif C > ta["O"] and ta["Vol"] > ta["Vol5"]: scores["Volume"] = 10; breakdown["價量"] = "溫和放量收紅"
    elif ta["Vol"] <= ta["Vol5"]: scores["Volume"] = 5; breakdown["價量"] = "量縮整理"
    else: scores["Volume"] = 0; breakdown["價量"] = "爆量收黑"
    
    # 5. RS(15)
    if ta["RS"] > 5: scores["RS"] = 15; breakdown["RS"] = "強於大盤5%以上"
    elif ta["RS"] > 0: scores["RS"] = 10; breakdown["RS"] = "優於大盤"
    else: scores["RS"] = 0; breakdown["RS"] = "弱於大盤"
    
    # 6. MACD(10)
    if ta["DIF"] > ta["DEA"] and ta["OSC"] > ta["OSC_Y"] and ta["OSC"] > 0: scores["MACD"] = 10; breakdown["MACD"] = "多方動能強勁"
    elif ta["DIF"] > ta["DEA"] and ta["OSC"] > 0: scores["MACD"] = 7; breakdown["MACD"] = "多頭但紅柱縮短"
    elif ta["DIF"] < ta["DEA"] and ta["OSC"] > ta["OSC_Y"]: scores["MACD"] = 3; breakdown["MACD"] = "空頭但有反彈契機"
    else: scores["MACD"] = 0; breakdown["MACD"] = "空方動能增強"
    
    # 7. KD(10)
    if ta["K"] > ta["D"] and ta["K"] > ta["K_Y"]: scores["KD"] = 10; breakdown["KD"] = "強勢黃金交叉"
    elif ta["K"] > ta["D"]: scores["KD"] = 5; breakdown["KD"] = "黃金交叉但略弱"
    else: scores["KD"] = 0; breakdown["KD"] = "死亡交叉"
    
    # 8. 乖離(10)
    if 0 <= ta["BIAS"] <= 8: scores["BIAS"] = 10; breakdown["乖離"] = "安全正乖離區間"
    elif 8 < ta["BIAS"] <= 15: scores["BIAS"] = 5; breakdown["乖離"] = "乖離偏高需防拉回"
    else: scores["BIAS"] = 0; breakdown["乖離"] = "乖離過大或負乖離"
    
    total = sum(scores.values())
    radar = [scores["MA"], scores["Pattern"], scores["Support"], scores["Volume"], scores["RS"], scores["MACD"], scores["KD"], scores["BIAS"]]
    return total, radar, breakdown, veto_str

# ==========================================
# 6. 核心調度 (Gemini API)
# ==========================================
SYS_INSTRUCT = """你是朱家泓波段長。以下是客觀技術分數(滿分100)。
請嚴格回傳純JSON。鍵值：{"trading_plan":{"buy_zone":"建議買區","stop_loss":"停損價位","take_profit":"停利預估","risk_reward_eval":"風報比簡評"}, "conclusion":"綜合操作建議"}"""

def safe_generate_content(prompt_data):
    num_keys = len(API_KEYS)
    for attempt in range(num_keys * 2): 
        healthy_idx = -1
        free_keys = list(range(num_keys - 1)) if num_keys > 1 else [0]
        vip_key = num_keys - 1 if num_keys > 1 else 0
        
        for idx in free_keys:
            if datetime.now() >= st.session_state.key_pool[idx]:
                healthy_idx = idx; break
        
        if healthy_idx == -1 and num_keys > 1 and datetime.now() >= st.session_state.key_pool[vip_key]:
            healthy_idx = vip_key
            
        if healthy_idx == -1:
            wait_sec = (min(st.session_state.key_pool.values()) - datetime.now()).total_seconds() + 1
            if wait_sec > 0:
                st.toast(f"💤 引擎冷卻中，等待 {int(wait_sec)} 秒..."); time.sleep(wait_sec); continue
        
        client = genai.Client(api_key=API_KEYS[healthy_idx])
        try:
            res = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt_data,
                config=types.GenerateContentConfig(
                    system_instruction=SYS_INSTRUCT,
                    temperature=0.0
                )
            )
            return res
        except Exception as e:
            st.session_state.key_pool[healthy_idx] = datetime.now() + timedelta(seconds=60)
            if "429" in str(e).lower() or "quota" in str(e).lower(): st.toast(f"⚠️ 引擎 {healthy_idx+1} 流量限制...")
            else: time.sleep(1)
            continue
    raise Exception("所有引擎嘗試均失敗，請稍後再試。")

def run_analysis(ticker_input):
    try:
        tk, cost = (ticker_input.split("@")[0].strip().upper(), float(ticker_input.split("@")[1].strip())) if "@" in ticker_input else (ticker_input.strip().upper(), None)
        
        # 直接使用裸代號透過富邦 API 抓取
        df = get_stock_data(tk)
        
        if df is None: return {"error": "無法取得報價資料 (請確認富邦API連線，或K線資料不足60日)"}
        ta = calculate_technical_data(df, get_market_return(True))
        if ta is None: return {"error": "指標運算異常 (歷史資料處理失敗)"}
        
        chinese_name = get_chinese_name(tk)
        total_score, radar_array, py_breakdown, py_veto = get_python_scores(ta)
        
        mini_prompt = f'{{"T":"{tk}","C":{ta["C"]},"Score":{total_score},"Radar":{radar_array},"MAs":{ta["MAs"]},"B":{ta["BIAS"]}}}'
        res = safe_generate_content(mini_prompt)
        raw = res.text
        
        try:
            parsed = json.loads(raw[raw.find('{'):raw.rfind('}')+1])
        except Exception as e:
            return {"error": f"AI 回傳格式解析失敗: {str(e)}"}
            
        # UI 外部連結專用
        yahoo_tk = tk + ".TW" if tk.isdigit() else tk
            
        parsed.update({
            'tech_breakdown': py_breakdown,
            'veto_alert': py_veto, 
            'total_score': total_score, 'radar_scores': radar_array,
            'cost_price': cost, 'resolved_ticker': tk, 'yahoo_ticker': yahoo_tk, 
            'stock_name': chinese_name, 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'current_price': ta['C']
        })
        return parsed
    except Exception as e: return {"error": f"系統異常: {str(e)}"}

# ==========================================
# 7. UI 與圖表渲染
# ==========================================
def plot_kline(df, cost=None):
    try:
        df['5MA'], df['10MA'], df['20MA'], df['60MA'] = [df['Close'].rolling(w).mean() for w in [5, 10, 20, 60]]
        df = df.tail(60)
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='日K線')])
        for ma, color, n in [(df['5MA'], 'blue', '5日線'), (df['10MA'], 'orange', '10日線'), (df['20MA'], 'green', '月線(20日)'), (df['60MA'], 'purple', '季線(60日)')]:
            fig.add_trace(go.Scatter(x=df.index, y=ma, line=dict(color=color, width=1.5), name=n))
        if cost: fig.add_hline(y=cost, line_dash="dash", line_color="red", annotation_text=f"成本: {cost}")
        fig.update_layout(height=350, margin=dict(l=0,r=0,t=20,b=0), xaxis_rangeslider_visible=False, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        return fig
    except: return None

def plot_radar(scores_input):
    try:
        scores = list(scores_input) 
        cats = ['均線(15)', '型態(15)', '壓力(10)', '價量(15)', 'RS(15)', 'MACD(10)', 'KD(10)', '乖離(10)']
        max_s = [15, 15, 10, 15, 15, 10, 10, 10]
        if len(scores) != 8: return None
        norm = [(s/m)*100 for s, m in zip(scores, max_s)]
        norm.append(norm[0]); cats.append(cats[0]); scores.append(scores[0])
        
        fig = go.Figure(go.Scatterpolar(
            r=norm, theta=cats, fill='toself', fillcolor='rgba(0, 150, 255, 0.3)', line=dict(color='rgba(0, 110, 255, 0.8)', width=2),
            text=[f"得分: {s}" for s in scores], hoverinfo="text+theta", name='戰力'
        ))
        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100], showticklabels=False)), showlegend=False, height=250, margin=dict(l=40, r=40, t=20, b=20))
        return fig
    except: return None

# ==========================================
# UI 介面層
# ==========================================
with st.sidebar:
    st.markdown("### 系統狀態")
    st.info(st.session_state.get('fubon_status', '🔴 尚未初始化富邦 API'))
    
    st.markdown("---")
    st.markdown("### 🛠 快捷工具")
    if st.button("📊 自動獲取今日成交量前 50 大", use_container_width=True):
        top_50 = get_top_50_volume()
        if top_50:
            st.session_state.auto_fill = ", ".join(top_50)
            st.success("已成功抓取！請至主畫面輸入框查看。")
        else:
            st.error("抓取失敗，請稍後再試。")

st.title("🎯 大家跟CHECHE一起賺大錢 1.0")
st.info("**💡 戰車指南：** 直接輸入代號(如 `2330`)，持股加成本(如 `3163@400`)，逗號可批次。")

col_in, col_clear = st.columns([4, 1])
with col_in: 
    default_val = st.session_state.pop("auto_fill", "")
    user_in = st.text_input("請輸入診斷清單：", value=default_val, key="main_in", placeholder="例如: 2330, AMD@170")
with col_clear:
    st.write("<br>", unsafe_allow_html=True)
    if st.button("🗑️ 清空歷史"):
        st.session_state.db = {"manual_results": []}
        save_history([]); st.rerun()

if st.button("🚀 啟動學術診斷", type="primary", use_container_width=True):
    tickers = [t.strip() for t in user_in.split(",") if t.strip()]
    if not tickers:
        st.warning("⚠️ 請先在上方輸入框填寫股票代號！")
    else:
        prog, status = st.progress(0), st.empty()
        has_error = False
        
        for idx, tk in enumerate(tickers):
            status.info(f"⏳ 分析 {tk} ...")
            res = run_analysis(tk)
            if "error" not in res:
                st.session_state.db['manual_results'].insert(0, {"full_ticker": res['resolved_ticker'], "deep": res})
                save_history(st.session_state.db['manual_results'])
            else: 
                st.error(f"❌ {tk} 失敗：{res['error']}")
                has_error = True
            prog.progress((idx + 1) / len(tickers))
            
        status.empty()
        if not has_error: st.rerun()

for i, item in enumerate(st.session_state.db['manual_results']):
    d = item['deep']
    tk = d.get('resolved_ticker', '')
    yahoo_tk = d.get('yahoo_ticker', tk) 
    name = d.get('stock_name', '') 
    cost, c_price = d.get('cost_price'), d.get('current_price', 0)
    
    pnl_tag = f"&nbsp;&nbsp;<span style='color:{'#ff4b4b' if c_price>=cost else '#00cc96'}; font-weight:bold;'>【帳面: {'+' if c_price>=cost else ''}{round((c_price-cost)/cost*100, 2)}%】</span>" if cost else ""
    links = f"&nbsp;&nbsp;<a href='https://hk.finance.yahoo.com/quote/{yahoo_tk}' target='_blank' style='text-decoration:none; background:#eee; color:#333; padding:2px 8px; border-radius:12px; font-size:12px;'>Yahoo</a>&nbsp;<a href='https://tw.tradingview.com/chart/?symbol={tk}' target='_blank' style='text-decoration:none; background:#eee; color:#333; padding:2px 8px; border-radius:12px; font-size:12px;'>TradingView</a>"
    
    with st.expander(f"📌 {tk} {name}", expanded=(i==0)):
        st.markdown(f"🕒 *分析時間: {d.get('timestamp', '未知')}* {pnl_tag} {links}", unsafe_allow_html=True)
        if d.get('veto_alert') and d.get('veto_alert') != '無': 
            st.error(f"🚫 否決條件觸發：{d['veto_alert']}")
        
        st.markdown(f"<h1 style='text-align:center;'>{d.get('total_score', '?')} / 100</h1>", unsafe_allow_html=True)
        st.info(f"**操作建議：** {d.get('conclusion', '')}")
        
        c_left, c_right = st.columns([1, 1])
        with c_left:
            st.subheader("📊 給分細節")
            for k, v in d.get('tech_breakdown', {}).items(): st.write(f"- **{k}**: {v}")
            p = d.get('trading_plan', {})
            st.warning(f"買區: {p.get('buy_zone')}\n\n停損: {p.get('stop_loss')}\n\n停利: {p.get('take_profit')}\n\n風報: {p.get('risk_reward_eval')}")
            
            copy_text = f"【{tk} {name}】波段診斷報告\n時間: {d.get('timestamp', '')}\n總分: {d.get('total_score', '')} / 100\n結論: {d.get('conclusion', '')}\n否決: {d.get('veto_alert', '無')}\n\n[實戰計畫]\n買區: {p.get('buy_zone')}\n停損: {p.get('stop_loss')}\n停利: {p.get('take_profit')}\n風報比: {p.get('risk_reward_eval')}"
            st.markdown("<br>**📋 點擊右側圖示一鍵複製報告：**", unsafe_allow_html=True)
            st.code(copy_text, language="markdown")
            
        with c_right:
            radar_fig = plot_radar(d.get('radar_scores', []))
            if radar_fig: st.plotly_chart(radar_fig, use_container_width=True, key=f"r_{i}")
            
            df_k = get_stock_data(tk) # 使用富邦 API 直接獲取繪圖用資料
            if df_k is not None:
                k_fig = plot_kline(df_k, cost)
                if k_fig: st.plotly_chart(k_fig, use_container_width=True, key=f"k_{i}")

        st.write("---")
        b1, b2, b3 = st.columns([1, 1, 2])
        with b1:
            if st.button("🔄 重新診斷", key=f"up_{i}", use_container_width=True):
                target = f"{tk}@{cost}" if cost else tk
                new_res = run_analysis(target)
                if "error" not in new_res:
                    st.session_state.db['manual_results'][i]['deep'] = new_res
                    save_history(st.session_state.db['manual_results']); st.rerun()
        with b2:
            if st.button("❌ 刪除紀錄", key=f"del_{i}", use_container_width=True):
                delete_record(i); st.rerun()
