import streamlit as st

# 画面設定（中央寄せで少し見やすくします）
st.set_page_config(page_title="願慶寺 ホームページ", layout="centered")

# タイトル
st.title("願慶寺（がんけいじ）へようこそ")

# メイン画像として otera.jpg を大きく表示
# ※画像ファイル名はGitHubにあるものと完全に一致させる必要があります
try:
    st.image("otera.jpg", use_container_width=True)
except:
    st.write("※ここに otera.jpg が表示されます")

# 区切り線
st.markdown("---")

# ご案内文章
st.header("お知らせ・ご案内")
st.write("ここに日々の行事や、お寺の歴史などを自由に書き込むことができます。")
st.write("文章はいくつでも追加可能です。")

# 複数の画像を横に並べて表示する（カラム機能）
st.subheader("境内の様子")
col1, col2 = st.columns(2)

with col1:
    try:
        st.image("sakura.jpg", caption="春の桜")
    except:
        st.write("※sakura.jpg")

with col2:
    try:
        st.image("winter_yoshizaki.jpg", caption="冬の景色")
    except:
        st.write("※winter_yoshizaki.jpg")

# さらに画像を追加する場合
st.markdown("---")
st.subheader("ポスター・資料")
try:
    st.image("yoshizaki_poster.jpg", use_container_width=True)
except:
    st.write("※yoshizaki_poster.jpg")
