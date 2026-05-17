import streamlit as st
import streamlit.components.v1 as components

# 画面を横いっぱいに広く使う設定
st.set_page_config(layout="wide")

st.title("願慶寺 ホームページ")

# 【ここを書き換えてください】
# Googleサイトで「公開」したあとの、実際のホームページのURLをここに入れます
google_site_url = "https://sites.google.com/view/あなたのサイト名"

# 画面にきれいに埋め込み表示（高さは1000ピクセル）
components.iframe(google_site_url, height=1000, scrolling=True)
