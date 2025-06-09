# app.py（升級版）
import streamlit as st
import pandas as pd
import re
from io import BytesIO
import requests
import json
import os

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
# 🔢 Firebase 計數功能設定
firebase_url = "https://nutrition-searcher-default-rtdb.firebaseio.com/views/total.json"

def increase_view_count():
    try:
        # 讀取目前人次
        r = requests.get(firebase_url)
        if r.status_code == 200:
            current = r.json()
            current = int(current) if current is not None else 0
        else:
            current = 0
        # 增加 +1
        new_total = current + 1
        requests.put(firebase_url, json=new_total)
        return new_total
    except:
        return "讀取失敗"

# ✅ 只在 session 第一次執行時計數
if 'view_tracked' not in st.session_state:
    view_count = increase_view_count()
    st.session_state.view_tracked = True
else:
    # 若已追蹤，則只讀取不再加總
    try:
        view_count = requests.get(firebase_url).json()
    except:
        view_count = "讀取失敗"

# 讀取 Excel 資料庫
@st.cache_data

def load_data():
    df = pd.read_excel("食品營養成分資料庫2024UPDATE2 (1).xlsx", sheet_name="工作表1", header=1)
    df.fillna('', inplace=True)
    return df

df = load_data()

# 排除非營養素欄位（保留所有欄位用於選擇營養素）
exclude_cols = ['整合編號', '食品分類', '樣品名稱', '內容物描述', '俗名', '廢棄率(%)']
nutrient_cols = [col for col in df.columns if col not in exclude_cols]

st.title("🥗 DRIs 計算小工具")

# 1️⃣ 使用者輸入：多筆食材 + 克數
user_input = st.text_area("請輸入食材與重量（格式如：地瓜 150g）", "地瓜 150g\n雞胸肉 120g\n豆腐 100g")

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
    matched = df[
        df['樣品名稱'].astype(str).str.contains(keyword, na=False) |
        df['俗名'].astype(str).str.contains(keyword, na=False)
    ]
    options = matched['樣品名稱'].unique().tolist()

    if not options:
        st.error(f"❌ 查無資料：{keyword}")
        selected_samples.append((None, grams))
        continue

    selected = st.selectbox(f"{keyword}（{grams}g）對應樣品：", options, key=f"select_{i}")
    selected_samples.append((selected, grams))

# 3️⃣ 營養素選擇
st.markdown("### ✅ 請選擇欲查詢的營養素：")
selected_nutrients = st.multiselect("可選擇多個欄位：", nutrient_cols)

# 4️⃣ 查詢按鈕觸發
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
st.markdown(f"<div style='text-align:center'> 網站總瀏覽人次：<strong>{view_count}</strong> 次</div>", unsafe_allow_html=True)
