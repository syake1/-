import streamlit as st
import streamlit.components.v1 as components
import os

# 画面を横いっぱいに広く使う設定
st.set_page_config(layout="wide")

st.title("願慶寺 ホームページ")

# HTMLファイルを表示する処理
html_file_name = "願慶寺.html"

if os.path.exists(html_file_name):
    with open(html_file_name, "r", encoding="utf-8") as f:
        html_code = f.read()
    
    # 横幅いっぱいに、高さ1000ピクセルでHTMLを表示（スクロール可能）
    components.html(html_code, height=1000, scrolling=True)
else:
    st.error(f"「{html_file_name}」がリポジトリ内に見つかりません。ファイル名の大文字・小文字があっているか確認してください。")

# 予備として、他のページへのリンクも下に作っておきます
st.markdown("---")
st.subheader("その他のリンク")
st.link_button("直接ホームページを開く", f"https://syake1.github.io/-/{html_file_name}")
