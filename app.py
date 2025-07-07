# app.py（升級版）
import streamlit as st
import pandas as pd
import re
from io import BytesIO
import uuid
import requests
import json

firebase_url_total = "https://nutrition-searcher-default-rtdb.firebaseio.com/views/total.json"
firebase_url_visitors = "https://nutrition-searcher-default-rtdb.firebaseio.com/visitors.json"

#ICON跟名稱
st.set_page_config(
    page_title="QuickNutrients",
    page_icon="favicon-32x32.png",
    layout="centered"
)
# 🔍 插入 Google Analytics 追蹤碼
st.components.v1.html("""
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-FSB7PV2XCJ"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-FSB7PV2XCJ');
</script>
""", height=0)

# 產生或讀取訪客 ID（存在 session 中）
if "visitor_id" not in st.session_state:
    visitor_id = str(uuid.uuid4())
    st.session_state.visitor_id = visitor_id
else:
    visitor_id = st.session_state.visitor_id

# 主函式：只記錄第一次出現的使用者
def check_and_increase_unique_view():
    try:
        # 讀取現有訪客清單
        visitor_db = requests.get(firebase_url_visitors).json() or {}

        # 第一次出現才記錄
        if visitor_id not in visitor_db:
            # +1 總瀏覽數
            total = requests.get(firebase_url_total).json() or 0
            total += 1
            requests.put(firebase_url_total, json=total)

            # 記下這位訪客
            requests.patch(firebase_url_visitors, json={visitor_id: True})
        else:
            # 如果出現過，直接抓目前總人次
            total = requests.get(firebase_url_total).json() or 0

        return total
    except:
        return "讀取失敗"
      
view_count = check_and_increase_unique_view()

# 讀取 Excel 資料庫
def load_data():
    # 讀取主資料庫
    df = pd.read_excel("食品營養成分資料庫2024.xlsx", sheet_name="工作表1", header=1)
    df.fillna('', inplace=True)
    df['資料來源'] = '主資料庫'

    # 讀取其他食材
    df1 = pd.read_excel("其餘食材.xlsx", sheet_name="工作表1", header=0)
    df1.fillna('', inplace=True)
    df1['資料來源'] = '其餘食材'

    # 🔍 對齊欄位（補上主資料庫有但 df1 沒有的欄位）
    for col in df.columns:
        if col not in df1.columns:
            df1[col] = 0

    # ➕ 若 df1 多出欄位也補到主資料庫（防止少欄問題）
    for col in df1.columns:
        if col not in df.columns:
            df[col] = 0

    # 🔁 重新排序欄位一致
    df1 = df1[df.columns]

    # 合併
    df_combined = pd.concat([df, df1], ignore_index=True)
    df_combined.fillna(0, inplace=True)

    # 🚨 強制轉成文字避免匹配失效
    df_combined['樣品名稱'] = df_combined['樣品名稱'].astype(str).str.strip()
    df_combined['俗名'] = df_combined['俗名'].astype(str).str.strip()

    return df_combined

# 讀取資料
df = load_data()

# 排除非營養素欄位（保留所有欄位用於選擇營養素）
exclude_cols = ['整合編號', '食品分類', '樣品名稱', '內容物描述', '俗名', '廢棄率(%)']
nutrient_cols = [col for col in df.columns if col not in exclude_cols]

st.title("🥗 營養成分快速查詢小工具")

# 1️⃣ 使用者輸入：多筆食材 + 克數
st.markdown("### ✏️ 請輸入食材與重量（格式如：地瓜 150g）")
user_input = st.text_area("", " ")

pattern = re.compile(r"(.+?)\s*(\d+(\.\d+)?)\s*g")
entries = [pattern.match(line.strip()) for line in user_input.strip().split('\n') if pattern.match(line.strip())]
parsed_inputs = [(m.group(1), float(m.group(2))) for m in entries]

if not parsed_inputs:
    st.warning("請輸入正確格式的食材資料，例如：地瓜 150g")
    st.stop()

# 2️⃣ 食材樣品選擇器
st.markdown("### 🔍 請針對每筆輸入選擇正確樣品：")
selected_samples = []

for i, (keyword, grams) in enumerate(parsed_inputs):
    keyword = keyword.strip()  # ✅ 去除前後空白
    matched = df[
        df['樣品名稱'].astype(str).str.contains(keyword, case=False, na=False) |
        df['俗名'].astype(str).str.contains(keyword, case=False, na=False)
    ]
    options = matched['樣品名稱'].unique().tolist()

    if not options:
        st.error(f"❌ 查無資料：{keyword}")
        selected_samples.append((None, grams))
        continue

    selected = st.selectbox(f"{keyword}（{grams}g）對應樣品：", options, key=f"select_{i}")
    selected_samples.append((selected, grams))

# 4️⃣ 查詢按鈕觸發
st.markdown("### ✅ 請選擇欲查詢的營養素：")
selected_nutrients = st.multiselect("可選擇多個欄位：", nutrient_cols)
if st.button("📊 查詢營養素"):
    result_rows = []

    for name, grams in selected_samples:
        if not name:
            continue
        record = df[df['樣品名稱'] == name].iloc[0]
        row = {'樣品名稱': name, '攝取量(g)': grams}
        for nutrient in selected_nutrients:
            val = record[nutrient] if nutrient in record else 0
            row[nutrient] = round(val * grams / 100, 2) if isinstance(val, (int, float)) else ''
        result_rows.append(row)

    if not result_rows:
        st.error("⚠️ 沒有成功匹配的樣品，請確認選擇是否正確。")
        st.stop()

    result_df = pd.DataFrame(result_rows)

    # 加總列
    total_row = {'樣品名稱': '總和', '攝取量(g)': result_df['攝取量(g)'].sum()}
    for nutrient in selected_nutrients:
        total_row[nutrient] = result_df[nutrient].apply(lambda x: x if isinstance(x, (int, float)) else 0).sum()

    result_df = pd.concat([result_df, pd.DataFrame([total_row])], ignore_index=True)

    st.success("✅ 查詢完成！")
    st.dataframe(result_df, use_container_width=True)

    # 匯出下載 Excel
    towrite = BytesIO()
    result_df.to_excel(towrite, index=False, sheet_name='營養結果')
    towrite.seek(0)
    st.download_button(
        label="📥 下載結果 Excel",
        data=towrite,
        file_name="查詢結果.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
# ✅ 顯示在頁面最底部
st.markdown(f"<hr style='margin-top:30px;'>", unsafe_allow_html=True)
st.markdown(f"<div style='text-align:center'> 👀 網站獨立訪客人次：<strong>{view_count}</strong> 位</div>", unsafe_allow_html=True)
