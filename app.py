import streamlit as st
from playwright.sync_api import sync_playwright
import time
import subprocess
import zipfile
import io
import re
from datetime import datetime

# --- 初始化設定 ---
st.set_page_config(page_title="網頁情資擷取助手 (Pro+)", layout="centered")
st.title("🛡️ 網頁情資擷取助手 (Pro+)")
st.markdown("戰略記錄專用工具：針對 Facebook 廣告檔案庫 (Ads Library) 等「無限捲動」與「...展開」網站進行深度優化。")

# --- 核心：環境檢查 ---
def ensure_browsers_installed():
    try:
        # 嘗試啟動瀏覽器看是否成功
        with sync_playwright() as p:
            p.chromium.launch(headless=True)
    except Exception:
        with st.spinner("正在初始化核心引擎 (下載瀏覽器 binary)..."):
            # 針對 Streamlit Cloud 或無頭環境的自動安裝
            subprocess.run(["playwright", "install", "chromium"])
            st.success("核心就緒！")

if 'browser_checked' not in st.session_state:
    ensure_browsers_installed()
    st.session_state['browser_checked'] = True

# --- 通用工具函式 ---
def get_safe_filename(url, index=None):
    clean_url = re.sub(r'^https?://', '', url)
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', clean_url)
    if index is not None:
        return f"{index+1:02d}_{safe_name[:50]}.pdf"
    return f"{safe_name[:50]}.pdf"

# --- [關鍵修正] 深度互動滾動邏輯 ---
def smart_scroll_and_expand(page):
    """
    針對 Infinite Scroll 網站的智慧滾動與點擊展開
    修正版本：使用 Playwright 內建的 text selector 和 force: True 提高可靠性。
    """
    
    # 點擊目標：包含這些文字或符號的元素
    # Meta 廣告庫常用的縮略符號是 '...' (半形) 或 '…' (全形刪節號)
    # 我們將使用 Playwright 的 locator 來尋找包含這些文字的元素。
    keywords = ['查看更多', '顯示更多', 'See more', 'Read more', '展開', '更多', '...', '…', 'See details', 'About this ad']

    def click_all_expanders(page, keywords):
        clicked_count = 0
        for keyword in keywords:
            # 使用 Playwright 內建的 text selector 尋找包含關鍵字的元素
            # 並且假設這些元素是按鈕或可點擊的 div/span
            
            # 使用 contains selector，並對短文字/符號使用精確過濾
            locator = page.locator(f'text={keyword}')
            
            try:
                # 遍歷所有匹配的元素
                elements = locator.all()
                for el in elements:
                    text = el.inner_text().strip()
                    # 避免點擊內文中的長段落（如文章內文恰好有 ...）
                    if len(text) < 30 or text in ('...', '…', '查看更多', 'See more'):
                        try:
                            # 嘗試點擊，使用 force: True 應對部分被遮擋的情況
                            el.click(timeout=1000, force=True)
                            clicked_count += 1
                        except:
                            pass # 忽略點擊失敗 (可能是元素已消失或確實無法點擊)
            except:
                pass
        return clicked_count

    st.info("正在執行初始點擊展開...")
    click_all_expanders(page, keywords)
    time.sleep(1) # 讓初始展開完成

    # 智慧無限捲動與重複展開
    previous_height = page.evaluate("document.body.scrollHeight")
    max_scrolls = 20
    
    for i in range(max_scrolls):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        
        # FB 載入新內容需要時間
        time.sleep(2.5) 
        
        st.info(f"滾動並再次嘗試展開 (第 {i+1} 次)...")
        # 在新載入的內容上再次執行點擊展開
        click_all_expanders(page, keywords)
        time.sleep(1) # 讓新展開的內容穩定

        new_height = page.evaluate("document.body.scrollHeight")
        
        if new_height == previous_height:
            # 如果高度沒變，再多等一下確認是否到底
            time.sleep(2)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == previous_height:
                break # 真的到底了
        previous_height = new_height

    # 任務結束，滾回頂部以便截圖時版面正常
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)

# --- 模式一：單一網址 ---
def generate_single_pdf(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        # 加大 Viewport
        context = browser.new_context(
            viewport={"width": 1280, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()
        try:
            st.info(f"正在連接：{url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.emulate_media(media="screen")
            
            st.info("正在執行深度挖掘 (滾動加載 + 點擊 '...' 展開)...")
            smart_scroll_and_expand(page)
            
            pdf_bytes = page.pdf(format="A4", print_background=True)
            return pdf_bytes
        except Exception as e:
            st.error(f"錯誤：{e}")
            return None
        finally:
            browser.close()

# --- 模式二：批次網址 ---
def generate_batch_pdfs(url_list):
    zip_buffer = io.BytesIO()
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
             viewport={"width": 1280, "height": 1080},
             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            total = len(url_list)
            success_count = 0
            
            for i, url in enumerate(url_list):
                status_text.text(f"處理中 ({i+1}/{total}): {url}")
                page = context.new_page()
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.emulate_media(media="screen")
                    smart_scroll_and_expand(page)
                    
                    pdf_bytes = page.pdf(format="A4", print_background=True)
                    
                    filename = get_safe_filename(url, i)
                    zip_file.writestr(filename, pdf_bytes)
                    success_count += 1
                    
                except Exception as e:
                    st.error(f"跳過錯誤連結 {url}: {str(e)[:100]}")
                finally:
                    page.close()
                    
                progress_bar.progress((i + 1) / total)

        browser.close()
        status_text.text(f"任務完成！成功：{success_count}/{total}")
        
    zip_buffer.seek(0)
    return zip_buffer

# --- UI 介面 ---
tab1, tab2 = st.tabs(["🔍 單一精確擷取", "📚 批量戰略歸檔"])

with tab1:
    st.header("單一網頁轉 PDF")
    single_url = st.text_input("輸入網址", placeholder="https://www.facebook.com/ads/library/...")
    if st.button("執行轉換", key="btn_single"):
        if single_url:
            pdf_data = generate_single_pdf(single_url)
            if pdf_data:
                st.success("轉換成功！")
                st.download_button("下載 PDF", pdf_data, "output.pdf", "application/pdf")

with tab2:
    st.header("批量網頁轉 PDF")
    batch_urls = st.text_area("輸入網址列表 (自動過濾雜訊)", height=200)
    if st.button("執行批次轉換", key="btn_batch"):
        # 使用 Regex 過濾出網址，排除前後空白與雜訊
        url_pattern = re.compile(r'(https?://\S+)')
        url_list = list(dict.fromkeys(url_pattern.findall(batch_urls)))
        
        if url_list:
            st.info(f"開始處理 {len(url_list)} 個網址...")
            zip_result = generate_batch_pdfs(url_list)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button("📦 下載 ZIP", zip_result, f"batch_{timestamp}.zip", "application/zip")
        else:
            st.warning("未偵測到有效網址")
