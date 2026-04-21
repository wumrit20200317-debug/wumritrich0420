import streamlit as st
import pandas as pd
import os

# --- 1. 嘗試讀取套件，測試 requirements.txt 是否安裝成功 ---
try:
    import fubon_neo
    import gspread
    import pandas_ta
    import google.auth
    install_status = "✅ 所有必要套件安裝成功！(requirements.txt 沒問題了)"
except Exception as e:
    install_status = f"❌ 套件讀取失敗：{e}"

st.set_page_config(page_title="系統環境測試", layout="wide")
st.title("🧪 系統環境與金鑰檢查站")

# --- 2. 顯示安裝狀態 ---
st.subheader("第一關：軟體套件安裝狀態")
if "✅" in install_status:
    st.success(install_status)
else:
    st.error(install_status)

# --- 3. 檢查 Secrets 保險箱 ---
st.subheader("第二關：金鑰保險箱 (Secrets) 讀取狀態")

# 檢查 Google JSON
if "GOOGLE_SHEETS_CREDENTIALS" in st.secrets:
    try:
        # 測試是否能成功解析 JSON 格式
        import json
        json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"])
        st.success("✅ Google JSON 金鑰已偵測到，且格式正確！")
    except json.JSONDecodeError:
        st.error("❌ 抓到兇手了！Google JSON 金鑰有抓到，但「格式錯誤」。請確認 Secrets 裡面有沒有用三個單引號 ''' 把 JSON 包起來。")
else:
    st.warning("⚠️ 尚未偵測到 Google 金鑰，請檢查 Secrets 區塊是否有定義 GOOGLE_SHEETS_CREDENTIALS。")

# 檢查富邦憑證亂碼
if "FUBON_CERT_BASE64" in st.secrets:
    st.success("✅ 富邦憑證亂碼已偵測到！")
else:
    st.warning("⚠️ 尚未偵測到富邦憑證，請檢查 Secrets 區塊。")

st.write("---")
st.info("💡 任務指示：如果上面兩關都出現綠色打勾 ✅，代表你的地基已經完美打好，我們馬上把正式的量化分析程式碼放回去！")
