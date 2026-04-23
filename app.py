import streamlit as st
import time
import json
import base64
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

# 載入富邦 API 與 Google 憑證 (對應要求)
from oauth2client.service_account import ServiceAccountCredentials
from fubon_neo.sdk import FubonSDK, Mode
from fubon_neo.constant import TimeInForce, OrderType, PriceType, MarketType

# ==========================================
# 1. 富邦 API 登入與初始化 (防呆安全版)
# ==========================================
@st.cache_resource
def init_fubon_api():
    if "fubon" not in st.secrets:
        return None, "⚠️ 尚未在 Streamlit Secrets 設定富邦 API 金鑰 ([fubon] 區塊)"
    try:
        # 將 Base64 憑證還原成實體檔案
        cert_bytes = base64.b64decode(st.secrets["fubon"]["cert_base64"])
        with open("fubon_cert.pfx", "wb") as f:
            f.write(cert_bytes)
            
        sdk = FubonSDK()
        res = sdk.login(st.secrets["fubon"]["id"], st.secrets["fubon"]["password"], "fubon_cert.pfx")
        if res:
            return sdk, "✅ 富邦 API 連線成功"
        else:
            return None, "❌ 富邦 API 登入失敗：請確認帳號密碼與憑證"
    except Exception as e:
        return None, f"❌ 富邦連線發生異常: {str(e)}"

# ==========================================
# 2. 密碼大門邏輯
# ==========================================
def check_password():
    if "password" not in st.secrets: return True
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

# 啟動系統與富邦連線
st.set_page_config(page_title="大家跟CHECHE一起賺大錢1.0", page_icon="🎯", layout="wide")

fubon_sdk, fubon_status = init_fubon_api()
with st.sidebar:
    st.subheader("⚙️ 系統狀態")
    if fubon_sdk:
        st.success(fubon_status)
    else:
        st.error(fubon_status)

# ==========================================
# 3. 智能調度中心
# ==========================================
API_KEYS = []
try:
    if "api_keys" in st.secrets:
        raw_keys = st.secrets["api_keys"]
        API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()] if isinstance(raw_keys, str) else list(raw_keys)
except Exception: pass

if not API_KEYS:
    st.error("❌ 系統偵測不到有效的 Gemini API 金鑰。")
    st.stop()

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
# 4. 數據精算與分析 (保留核心演算法)
# ==========================================
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
    try: 
        df = yf.Ticker(ticker).history(period="1y")
        return None if df.empty else df
    except: return None

@st.cache_data(ttl=3600, show_spinner=False)
def get_market_return(is_tw):
    try:
        df = yf.Ticker("^TWII" if is_tw else "^GSPC").history(period="1mo")
        return (df['Close'].iloc[-1] - df['Close'].iloc[-10]) / df['Close'].iloc[-10] * 100
    except: return 0

def calculate_technical_data(df, market_ret):
    try:
        close, open_p, vol = df['Close'].iloc[-1], df['Open'].iloc[-1], df['Volume'].iloc[-1]
        ma5, ma10, ma20, ma60 = [df['Close'].rolling(w).mean().iloc[-1] for w in [5, 10, 20, 60]]
        ma20_yest, ma60_yest = df['Close'].rolling(20).mean().iloc[-2], df['Close'].rolling(60).mean().iloc[-2] 
        vol_5ma = df['Volume'].rolling(5).mean().iloc[-1]
        high_20, low_20 = df['High'].tail(20).max(), df['Low'].tail(20).min()
        low_20_yest = df['Low'].iloc[-21:-1].min() if len(df) >= 21 else df['Low'].min() 
        
        exp1, exp2 = df['Close'].ewm(span=12, adjust=False).mean(), df['Close'].ewm(span=26, adjust=False).mean()
        dif, dea = (exp1 - exp2), (exp1 - exp2).ewm(span=9, adjust=False).mean()
        osc, osc_yest = dif - dea, dif.iloc[-2] - dea.iloc[-2]
        
        low_9, high_9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
        rsv = (df['Close'] - low_9) / (high_9 - low_9) * 100
        k, d = rsv.ewm(alpha=1/3).mean(), rsv.ewm(alpha=1/3).mean().ewm(alpha=1/3).mean()
        
        rs = ((df.tail(10)['Close'].iloc[-1] - df.tail(10)['Close'].iloc[0])/df.tail(10)['Close'].iloc[0]*100) - market_ret
        bias20 = (close - ma20)/ma20*100
        
        return {
            "C": round(close, 2), "O": round(open_p, 2), "MAs": [round(ma5,2), round(ma10,2), round(ma20,2), round(ma60,2)],
            "T20": 1 if ma20 > ma20_yest else 0, "T60": 1 if ma60 > ma60_yest else 0, 
            "BIAS": round(bias20, 2), "RS": round(rs, 2), "Vol": vol, "Vol5": vol_5ma,
            "H20": round(high_20, 2), "L20": round(low_20, 2), "L20_Y": round(low_20_yest, 2),
            "DIF": round(dif.iloc[-1], 2), "DEA": round(dea.iloc[-1], 2), "OSC": round(osc.iloc[-1], 2), "OSC_Y": round(osc_yest, 2),
            "K": round(k.iloc[-1], 2), "D": round(d.iloc[-1], 2), "K_Y": round(k.iloc[-2], 2)
        }
    except: return None

def get_python_scores(ta):
    scores, breakdown, vetos = {}, {}, []
    C, MAs, T20, T60 = ta["C"], ta["MAs"], ta["T20"], ta["T60"]
    
    if C < MAs[2] and T20 == 0: vetos.append("股價跌破月線(20MA)且月線下彎，波段保護力消失")
    if C < ta["L20_Y"]: vetos.append("股價跌破近20日低點，盤整區間破底轉空")
    if C < ta["O"] and ta["Vol"] > ta["Vol5"] * 2.5: vetos.append("爆出大於5日均量2.5倍的天量且收黑，具備極高出貨疑慮")
    if C < MAs[3] and T60 == 0: vetos.append("上方季線(60MA)下彎蓋頭反壓，長線上漲空間受限")
    if ta["DIF"] < 0 and ta["DEA"] < 0 and ta["DIF"] < ta["DEA"] and ta["OSC"] < ta["OSC_Y"]: vetos.append("MACD零軸下死亡交叉且綠柱放大，空方動能強勁")
    if MAs[0] < MAs[1] < MAs[2]: vetos.append("短中期均線(5MA<10MA<20MA)呈空頭排列，切勿接刀")

    veto_str = "；".join(vetos) if vetos else "無"

    if C > MAs[0] > MAs[1] > MAs[2] > MAs[3]: scores["MA"] = 15; breakdown["均線"] = "短中長天期均線呈標準多頭排列，多方動能極強。"
    elif C > MAs[2] and T20 == 1: scores["MA"] = 10; breakdown["均線"] = "股價穩站月線之上且趨勢向上，具備波段保護力。"
    elif T20 == 1: scores["MA"] = 5; breakdown["均線"] = "股價雖跌破月線，但月線仍維持上彎，視為強勢整理。"
    else: scores["MA"] = 0; breakdown["均線"] = "跌破下彎的月線，短線趨勢偏空。"
    
    if C >= ta["H20"]: scores["Pattern"] = 15; breakdown["型態"] = "創下近20日新高，動能強勢發動突破。"
    elif C >= ta["H20"] * 0.97: scores["Pattern"] = 10; breakdown["型態"] = "逼近前波高點(3%以內)，蓄勢準備挑戰突破。"
    elif C >= (ta["H20"] + ta["L20"])/2: scores["Pattern"] = 5; breakdown["型態"] = "處於近期箱型整理區間的中軸之上，持續震盪。"
    else: scores["Pattern"] = 0; breakdown["型態"] = "弱勢破底或處於盤整區間下緣。"
    
    if C > MAs[3]: scores["Support"] = 10; breakdown["壓力"] = "站上季線(60MA)，長線具備強烈支撐。"
    else: scores["Support"] = 0; breakdown["壓力"] = "位於季線之下，上方長線壓力較為沉重。"
    
    if C > ta["O"] and ta["Vol"] > ta["Vol5"] * 1.5: scores["Volume"] = 15; breakdown["價量"] = "帶量收紅，成交量大於5日均量1.5倍，主力攻擊量現。"
    elif C > ta["O"] and ta["Vol"] > ta["Vol5"]: scores["Volume"] = 10; breakdown["價量"] = "溫和放量收紅，量價配合良好。"
    elif ta["Vol"] <= ta["Vol5"]: scores["Volume"] = 5; breakdown["價量"] = "量縮整理，籌碼相對安定未失控。"
    else: scores["Volume"] = 0; breakdown["價量"] = "爆量收黑或出現價量背離，須留意出貨風險。"
    
    if ta["RS"] > 5: scores["RS"] = 15; breakdown["RS"] = "近10日報酬強於大盤5%以上，為市場主流強勢股。"
    elif ta["RS"] > 0: scores["RS"] = 10; breakdown["RS"] = "近期走勢優於大盤，具備相對抗跌特性。"
    else: scores["RS"] = 0; breakdown["RS"] = "走勢弱於大盤，目前較不受市場資金青睞。"
    
    if ta["DIF"] > ta["DEA"] and ta["OSC"] > ta["OSC_Y"] and ta["OSC"] > 0: scores["MACD"] = 10; breakdown["MACD"] = "維持多頭交叉，且紅柱狀圖持續放大，動能強勁。"
    elif ta["DIF"] > ta["DEA"] and ta["OSC"] > 0: scores["MACD"] = 7; breakdown["MACD"] = "維持多頭，但紅柱狀圖已開始縮短，上攻動能略減。"
    elif ta["DIF"] < ta["DEA"] and ta["OSC"] > ta["OSC_Y"]: scores["MACD"] = 3; breakdown["MACD"] = "空頭格局，但綠柱狀圖縮短，有跌深反彈契機。"
    else: scores["MACD"] = 0; breakdown["MACD"] = "死亡交叉且綠柱持續放大，空方動能增強。"
    
    if ta["K"] > ta["D"] and ta["K"] > ta["K_Y"]: scores["KD"] = 10; breakdown["KD"] = "K>D且K值向上，短線強勢不變。"
    elif ta["K"] > ta["D"]: scores["KD"] = 5; breakdown["KD"] = "維持黃金交叉，但K值略微下彎轉弱。"
    else: scores["KD"] = 0; breakdown["KD"] = "死亡交叉，短線進入弱勢整理。"
    
    if 0 <= ta["BIAS"] <= 8: scores["BIAS"] = 10; breakdown["乖離"] = "正乖離介於0~8%的安全起漲區間內。"
    elif 8 < ta["BIAS"] <= 15: scores["BIAS"] = 5; breakdown["乖離"] = "正乖離偏高，短線有過熱拉回風險。"
    else: scores["BIAS"] = 0; breakdown["乖離"] = "乖離率過大或呈現負乖離破線狀態。"
    
    total = sum(scores.values())
    radar = [scores["MA"], scores["Pattern"], scores["Support"], scores["Volume"], scores["RS"], scores["MACD"], scores["KD"], scores["BIAS"]]
    return total, radar, breakdown, veto_str

SYS_INSTRUCT = """你是朱家泓波段長。以下是客觀技術分數(滿分100)。
請嚴格回傳純JSON。鍵值：{"trading_plan":{"buy_zone":"建議買區","stop_loss":"停損價位","take_profit":"停利預估","risk_reward_eval":"風報比簡評"}, "conclusion":"綜合操作建議"}"""

def safe_generate_content(prompt_data):
    num_keys = len(API_KEYS)
    for attempt in range(num_keys * 3): 
        time.sleep(random.uniform(1.0, 2.5)) 
        healthy_idx = -1
        free_keys = list(range(num_keys - 1)) if num_keys > 1 else [0]
        vip_key = num_keys - 1
        for idx in free_keys:
            if datetime.now() >= st.session_state.key_pool[idx]:
                healthy_idx = idx; break
        if healthy_idx == -1 and num_keys > 1 and datetime.now() >= st.session_state.key_pool[vip_key]: healthy_idx = vip_key
        if healthy_idx == -1:
            wait_sec = (min(st.session_state.key_pool.values()) - datetime.now()).total_seconds() + 2
            if wait_sec > 0: st.toast(f"💤 引擎冷卻中，等待 {int(wait_sec)} 秒..."); time.sleep(wait_sec); continue
        genai.configure(api_key=API_KEYS[healthy_idx])
        model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=SYS_INSTRUCT)
        try:
            return model.generate_content(prompt_data, generation_config=genai.types.GenerationConfig(temperature=0.0))
        except Exception as e:
            st.session_state.key_pool[healthy_idx] = datetime.now() + timedelta(seconds=60)
            continue
    raise Exception("所有引擎嘗試均失敗。")

def run_analysis(ticker_input):
    try:
        tk, cost = (ticker_input.split("@")[0].strip().upper(), float(ticker_input.split("@")[1].strip())) if "@" in ticker_input else (ticker_input.strip().upper(), None)
        
        yahoo_tk = tk + ".TW" if tk.isdigit() else tk
        df = get_stock_data(yahoo_tk)
        if df is None and tk.isdigit(): df = get_stock_data(tk + ".TWO")
        if df is None: return {"error": "無法取得報價資料 (請確認代號是否正確或已下市)"}
        
        ta = calculate_technical_data(df, get_market_return(".TW" in tk or ".TWO" in tk))
        if ta is None: return {"error": "指標運算異常"}
        
        total_score, radar_array, py_breakdown, py_veto = get_python_scores(ta)
        mini_prompt = f'{{"T":"{tk}","C":{ta["C"]},"Score":{total_score},"Radar":{radar_array},"MAs":{ta["MAs"]},"B":{ta["BIAS"]}}}'
        
        res = safe_generate_content(mini_prompt)
        try:
            raw = res.text
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            parsed = json.loads(match.group(0)) if match else json.loads(raw)
        except: return {"error": "AI 回傳解析失敗"}
            
        parsed.update({
            'tech_breakdown': py_breakdown, 'veto_alert': py_veto, 'total_score': total_score, 'radar_scores': radar_array,
            'cost_price': cost, 'resolved_ticker': tk, 'yahoo_ticker': yahoo_tk, 
            'stock_name': get_chinese_name(tk), 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'current_price': ta['C']
        })
        return parsed
    except Exception as e: return {"error": f"系統異常: {str(e)}"}

# ==========================================
# 5. UI 與圖表渲染
# ==========================================
def plot_kline(df, cost=None):
    try:
        df['5MA'], df['10MA'], df['20MA'], df['60MA'] = [df['Close'].rolling(w).mean() for w in [5, 10, 20, 60]]
        df = df.tail(60)
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='日K線')])
        for ma, color, n in [(df['5MA'], 'blue', '5日線'), (df['10MA'], 'orange', '10日線'), (df['20MA'], 'green', '月線(20日)'), (df['60MA'], 'purple', '季線(60日)')]:
            fig.add_trace(go.Scatter(x=df.index, y=ma, line=dict(color=color, width=1.5), name=n))
        if cost: fig.add_hline(y=cost, line_dash="dash", line_color="red", annotation_text=f"成本: {cost}")
        fig.update_layout(height=350, margin=dict(l=0,r=0,t=20,b=0), xaxis_rangeslider_visible=False)
        return fig
    except: return None

def plot_radar(scores_input):
    try:
        scores = list(scores_input) 
        cats = ['均線(15)', '型態(15)', '壓力(10)', '價量(15)', 'RS(15)', 'MACD(10)', 'KD(10)', '乖離(10)']
        norm = [(s/m)*100 for s, m in zip(scores, [15, 15, 10, 15, 15, 10, 10, 10])]
        norm.append(norm[0]); cats.append(cats[0]); scores.append(scores[0])
        fig = go.Figure(go.Scatterpolar(r=norm, theta=cats, fill='toself', fillcolor='rgba(0, 150, 255, 0.3)', line=dict(color='rgba(0, 110, 255, 0.8)', width=2), text=[f"得分: {s}" for s in scores], hoverinfo="text+theta"))
        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100], showticklabels=False)), showlegend=False, height=250, margin=dict(l=40, r=40, t=20, b=20))
        return fig
    except: return None

st.title("🎯 大家跟CHECHE一起賺大錢1.0")
st.info("**💡 指南：** 支援代號輸入(如 `2330`)，持股加成本(如 `2330@800`)，支援逗號分隔多筆(如 `2330, 2317@150`)。")

col_in, col_clear = st.columns([3, 1])
with col_in: user_in = st.text_input("請輸入診斷清單：", key="main_in", placeholder="例如: 2330, 2330@800, AMD@170")
with col_clear:
    st.write("<br>", unsafe_allow_html=True)
    if st.button("🗑️ 清空歷史"): st.session_state.db = {"manual_results": []}; save_history([]); st.rerun()

if st.button("🚀 啟動學術診斷", type="primary", use_container_width=True):
    tickers = [t.strip() for t in user_in.split(",") if t.strip()]
    if not tickers: st.warning("⚠️ 請輸入股票代號！")
    else:
        prog, status = st.progress(0), st.empty()
        for idx, tk in enumerate(tickers):
            status.info(f"⏳ 分析 {tk} ...")
            res = run_analysis(tk)
            if "error" not in res: st.session_state.db['manual_results'].insert(0, {"full_ticker": res['resolved_ticker'], "deep": res}); save_history(st.session_state.db['manual_results'])
            else: st.error(f"❌ {tk} 失敗：{res['error']}")
            prog.progress((idx + 1) / len(tickers))
        status.empty(); st.rerun()

for i, item in enumerate(st.session_state.db['manual_results']):
    d = item['deep']
    tk, yahoo_tk, name, cost, c_price = d.get('resolved_ticker', ''), d.get('yahoo_ticker', ''), d.get('stock_name', ''), d.get('cost_price'), d.get('current_price', 0)
    pnl = f"&nbsp;&nbsp;<span style='color:{'#ff4b4b' if c_price<cost else '#00cc96'}; font-weight:bold;'>【帳面: {'+' if c_price>=cost else ''}{round((c_price-cost)/cost*100, 2)}%】</span>" if cost else ""
    links = f"&nbsp;&nbsp;<a href='https://hk.finance.yahoo.com/quote/{yahoo_tk}' target='_blank'>Yahoo</a>"
    
    with st.expander(f"📌 {tk} {name}", expanded=(i==0)):
        st.markdown(f"🕒 *{d.get('timestamp', '')}* {pnl} {links}", unsafe_allow_html=True)
        if d.get('veto_alert') and d.get('veto_alert') != '無': st.error(f"🚫 否決觸發：{d['veto_alert']}")
        st.markdown(f"<h1 style='text-align:center;'>{d.get('total_score', '?')} / 100</h1>", unsafe_allow_html=True)
        st.info(f"**操作建議：** {d.get('conclusion', '')}")
        
        c_left, c_right = st.columns([1, 1])
        with c_left:
            st.subheader("📊 給分細節")
            for k, v in d.get('tech_breakdown', {}).items(): st.write(f"- **{k}**: {v}")
            p = d.get('trading_plan', {})
            st.warning(f"買區: {p.get('buy_zone')}\n\n停損: {p.get('stop_loss')}\n\n停利: {p.get('take_profit')}\n\n風報: {p.get('risk_reward_eval')}")
            
            copy_text = f"【{tk} {name}】波段診斷\n總分: {d.get('total_score', '')}\n結論: {d.get('conclusion', '')}\n否決: {d.get('veto_alert', '無')}\n買區: {p.get('buy_zone')}\n停損: {p.get('stop_loss')}\n停利: {p.get('take_profit')}"
            st.markdown("<br>**📋 長按複製報告：**", unsafe_allow_html=True); st.code(copy_text, language="markdown")
            
        with c_right:
            if fig:=plot_radar(d.get('radar_scores', [])): st.plotly_chart(fig, use_container_width=True, key=f"r_{i}")
            if df_k:=get_stock_data(yahoo_tk):
                if k_fig:=plot_kline(df_k, cost): st.plotly_chart(k_fig, use_container_width=True, key=f"k_{i}")

        b1, b2, b3 = st.columns([1, 1, 2])
        with b1:
            if st.button("🔄 重新診斷", key=f"up_{i}", use_container_width=True):
                if "error" not in (new_res:=run_analysis(f"{tk}@{cost}" if cost else tk)):
                    st.session_state.db['manual_results'][i]['deep'] = new_res; save_history(st.session_state.db['manual_results']); st.rerun()
        with b2:
            if st.button("❌ 刪除紀錄", key=f"del_{i}", use_container_width=True): delete_record(i); st.rerun()
