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

# --- [關鍵升級] 深度互動滾動邏輯 ---
def smart_scroll_and_expand(page):
    """
    針對 Infinite Scroll 網站的智慧滾動與點擊展開
    修正版本：特別針對 Meta 廣告庫的 "..." 縮略符號進行處理
    """
    
    # 定義瀏覽器端執行的 JavaScript 邏輯
    # 邏輯說明：
    # 1. 搜尋包含特定關鍵字或符號的元素
    # 2. 嚴格檢查文字長度（< 30字），確保只點擊「按鈕」而非「文章內文」
    # 3. 觸發點擊事件
    expand_logic = """
        () => {
            const keywords = [
                '查看更多', '顯示更多', 'See more', 'Read more', '展開', '更多', 
                '...', '…', 'See details', 'About this ad'
            ];
            
            // 擴大選取範圍，Meta 的 ... 有時是 div, 有時是 span, 有時是 button
            const elements = document.querySelectorAll('div[role="button"], span, a, button, div');
            
            elements.forEach(el => {
                // 取得可見文字
                const text = el.innerText ? el.innerText.trim() : "";
                
                if (!text) return;

                // [關鍵安全檢查]：展開按鈕通常字數很少。
                // 如果字數太多(例如 > 30)，很可能是內文剛好包含 "..."，絕對不能點。
                if (text.length > 30) return;

                // 檢查是否完全等於符號，或包含關鍵字
                const isSymbol = (text === '...' || text === '…');
                const hasKeyword = keywords.some(keyword => text.includes(keyword));
                
                if (isSymbol || hasKeyword) {
                    try {
                        // 檢查元素是否可見，避免點擊隱藏元素報錯
                        if (el.offsetParent !== null) {
                            el.click();
                            // 標記已點擊 (雖然頁面刷新可能會重置，但對單次執行有幫助)
                            el.setAttribute('data-clicked', 'true');
                        }
                    } catch(e) {}
                }
            });
        }
    """

    # 1. 初始嘗試點擊 (針對首屏內容)
    try:
        page.evaluate(expand_logic)
    except:
        pass 

    # 2. 智慧無限捲動
    previous_height = page.evaluate("document.body.scrollHeight")
    
    # 設定最大滾動次數 (避免無限迴圈)
    max_scrolls = 20
    
    for i in range(max_scrolls):
        # 滾動到底部
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        
        # FB 廣告庫載入圖片和新卡片需要時間，給予緩衝
        time.sleep(2.5)
        
        # 再次執行點擊展開邏輯 (針對新載入的內容)
        try:
            page.evaluate(expand_logic)
            time.sleep(0.5) # 點擊後給一點時間讓文字展開
        except:
            pass

        # 檢查高度是否變化
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == previous_height:
            # 高度沒變，可能是網速慢，再給一次機會
            time.sleep(2)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == previous_height:
                break # 真的到底了
        previous_height = new_height

    # 任務結束，滾回頂部以便截圖時版面正常
    page.evaluate("window.scrollTo(0, 0)")
    # 等待頂部導覽列歸位
    time.sleep(1)

# --- 模式一：單一網址 ---
def generate_single_pdf(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        # 加大 Viewport 以容納更多廣告並減少 RWD 造成的版面擠壓
        context = browser.new_context(
            viewport={"width": 1280, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()
        try:
            st.info(f"正在連接：{url}")
            # 使用 domcontentloaded 較快，若需等待圖片完全載入可改用 networkidle (但 FB 常有背景傳輸導致 networkidle 卡住)
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
        url_list = list(dict.fromkeys(url_pat0tern.findall(batch_urls)))
        
        if url_list:
            st.info(f"開始處理 {len(url_list)} 個網址...")
            zip_result = generate_batch_pdfs(url_list)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button("📦 下載 ZIP", zip_result, f"batch_{timestamp}.zip", "application/zip")
        else:
            st.warning("未偵測到有效網址")
