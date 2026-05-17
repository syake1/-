import streamlit as st

# 画面を横いっぱいに広く使う設定
st.set_page_config(layout="wide")

st.title("願慶寺 ホームページ")

st.write("下のボタンをクリックすると、願慶寺のホームページが新しいタブで開きます。")

# 【ここをご自身のGoogleサイトのURLに書き換えてください】
# ※「https://sites.google.com/view/サイト名」の形です
google_site_url = "https://sites.google.com/view/あなたのサイト名"

# クリックすると新しいページで開くボタンを設置
st.link_button("👉 願慶寺ホームページを開く", google_site_url, type="primary")
