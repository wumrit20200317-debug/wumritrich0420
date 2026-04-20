import streamlit as st
import pandas as pd
import os

# 嘗試讀取套件，測試安裝是否成功
try:
    import fubon_neo
    import gspread
    import pandas_ta
    import google.auth
    install_status = "✅ 所有必要套件安裝成功！"
except Exception as e:
    install_status = f"❌ 套件讀取失敗：{e}"

st.set_page_config(page_title="系統環境測試")

st.title("🧪 系統環境檢查站")

# 1. 檢查安裝狀態
st.subheader("1. 軟體套件狀態")
if "✅" in install_status:
    st.success(install_status)
else:
    st.error(install_status)

# 2. 檢查 Secrets 裡面有沒有 Google 的東西
st.subheader("2. 金鑰保險箱 (Secrets) 檢查")
if "GOOGLE_SHEETS_CREDENTIALS" in st.secrets:
    st.success("✅ Google JSON 金鑰已偵測到")
else:
    st.warning("⚠️ 尚未偵測到 Google 金鑰，請檢查 Secrets 區塊。")

if "FUBON_CERT_BASE64" in st.secrets:
    st.success("✅ 富邦憑證亂碼已偵測到")
else:
    st.warning("⚠️ 尚未偵測到富邦憑證，請檢查 Secrets 區塊。")

st.write("---")
st.write("請先確認以上兩項都變綠色（✅），我們再進行下一步的分析邏輯開發。")
