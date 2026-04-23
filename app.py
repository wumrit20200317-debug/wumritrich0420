# 1. 系統登入密碼
password = "123"

# 2. Gemini AI 金鑰 (支援多組，請用英文逗號隔開)
api_keys = "AIzaSy_你的第一組金鑰, AIzaSy_你的第二組金鑰"

# 3. Google 試算表設定
gsheet_name = "我的股票紀錄表"

# 4. Google Cloud 服務帳戶 JSON (開通試算表寫入權限的那一包)
[gcp_service_account]
type = "service_account"
project_id = "你的專案ID"
private_key_id = "你的金鑰ID"
private_key = "-----BEGIN PRIVATE KEY-----\n你的超長亂數金鑰第一行\n金鑰第二行...\n-----END PRIVATE KEY-----\n"
client_email = "你的服務帳號@xxx.iam.gserviceaccount.com"
client_id = "你的數字ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "你的憑證網址"

# 5. 富邦證券 API 設定
[fubon]
id = "你的身分證字號"
pwd = "你的富邦登入密碼"
cert_path = "fubon.pfx"  # 請確認你的憑證檔案已上傳至 Github 根目錄且檔名相同
cert_pwd = "你的憑證密碼"
