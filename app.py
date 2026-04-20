import streamlit as st

# --- 系統設定 (這部分未來會教您放進 Secrets) ---
SYSTEM_PASSWORD = "lnp666" 

# --- 網頁介面設置 ---
st.set_page_config(page_title="飆股量化分析系統 1150418", layout="wide")

# --- 登入邏輯 ---
if "login_status" not in st.session_state:
    st.session_state.login_status = False

def check_login():
    if st.session_state.password_input == SYSTEM_PASSWORD:
        st.session_state.login_status = True
    else:
        st.error("密碼錯誤，請重新輸入！")

# 如果沒登入，顯示登入畫面
if not st.session_state.login_status:
    st.title("🔐 系統安全檢查")
    st.text_input("請輸入系統存取密碼：", type="password", key="password_input", on_change=check_login)
    st.stop() # 沒登入就停止執行後面的程式

# --- 登入成功後的畫面 ---
st.title("🚀 飆股量化分析系統 1150418")
st.success("身分認證成功！系統已就緒。")

st.sidebar.header("系統選單")
st.write("---")

# 這裡先放一個測試按鈕，確認邏輯正常
if st.button("點擊測試系統健康度"):
    st.balloons()
    st.write("✅ 雲端大腦運作正常！")
    st.write("下一個關卡：我們將連線富邦 API 抓取即時行情。")
