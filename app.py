import streamlit as st
from playwright.sync_api import sync_playwright
import time
import os
import subprocess

# --- 初始化設定 ---
st.set_page_config(page_title="網頁轉 PDF 神器", layout="centered")
st.title("📄 網頁轉 PDF 工具")
st.markdown("輸入網址，自動滾動加載圖片，並將網頁存成 PDF 下載。")

# --- 關鍵：檢查並安裝瀏覽器 (針對 Streamlit Cloud 環境) ---
def ensure_browsers_installed():
    # 檢查是否已經安裝過 chromium，避免重複執行
    # 注意：在 Streamlit Cloud 重啟時可能會重置，所以保留這個檢查很安全
    try:
        # 嘗試執行一個簡單的 playwright 指令看是否報錯
        with sync_playwright() as p:
            p.chromium.launch(headless=True)
    except Exception:
        st.warning("正在初始化瀏覽器核心，第一次執行需耗時約 30-60 秒，請稍候...")
        subprocess.run(["playwright", "install", "chromium"])
        subprocess.run(["playwright", "install-deps"]) # 安裝系統依賴
        st.success("瀏覽器核心安裝完成！")

# --- 核心功能：滾動頁面 (處理 Lazy Loading) ---
def scroll_page(page):
    """模擬使用者滾動，確保動態圖片載入"""
    page.evaluate("""
        async () => {
            await new Promise((resolve) => {
                var totalHeight = 0;
                var distance = 100;
                var timer = setInterval(() => {
                    var scrollHeight = document.body.scrollHeight;
                    window.scrollBy(0, distance);
                    totalHeight += distance;

                    if(totalHeight >= scrollHeight - window.innerHeight){
                        clearInterval(timer);
                        resolve();
                    }
                }, 100);
            });
        }
    """)
    # 滾動完後稍微等待一下，確保渲染完成
    time.sleep(2) 
    # 滾回頂部，有些固定 Header 遮擋的問題可以透過這樣重置
    page.evaluate("window.scrollTo(0, 0)")

# --- 核心功能：產生 PDF ---
def generate_pdf(url):
    with sync_playwright() as p:
        # 啟動瀏覽器
        # --no-sandbox 是為了在 Linux/Docker 環境下穩定運行
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()

        try:
            # 1. 前往網址
            st.info(f"正在讀取網頁：{url}")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # 2. 模擬螢幕顯示 (避免列印樣式跑版)
            page.emulate_media(media="screen")
            
            # 3. 執行滾動加載
            st.info("正在處理動態內容與圖片載入...")
            scroll_page(page)

            # 4. 輸出 PDF
            st.info("正在渲染 PDF...")
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True, # 保留背景顏色/圖片
                margin={"top": "1cm", "bottom": "1cm", "left": "1cm", "right": "1cm"}
            )
            
            return pdf_bytes
            
        except Exception as e:
            st.error(f"發生錯誤：{e}")
            return None
        finally:
            browser.close()

# --- UI 介面邏輯 ---
# 確保環境準備好
if 'browser_checked' not in st.session_state:
    ensure_browsers_installed()
    st.session_state['browser_checked'] = True

url_input = st.text_input("請輸入目標網址 (包含 https://)", placeholder="https://www.example.com")

if st.button("開始轉換", type="primary"):
    if not url_input:
        st.warning("請輸入網址")
    else:
        with st.spinner('機器人正在工作中，請稍候...'):
            pdf_data = generate_pdf(url_input)
            
            if pdf_data:
                st.success("轉換成功！")
                st.download_button(
                    label="下載 PDF",
                    data=pdf_data,
                    file_name="output_page.pdf",
                    mime="application/pdf"
                )
