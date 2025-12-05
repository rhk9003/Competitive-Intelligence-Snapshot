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
st.markdown("戰略記錄專用工具：針對 Facebook 廣告檔案庫等「無限捲動」網站進行深度優化。")

# --- 核心：環境檢查 ---
def ensure_browsers_installed():
    try:
        with sync_playwright() as p:
            p.chromium.launch(headless=True)
    except Exception:
        with st.spinner("正在初始化核心引擎..."):
            subprocess.run(["playwright", "install", "chromium"])
            subprocess.run(["playwright", "install-deps"])
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
    """
    # 1. 嘗試點擊「查看更多」類型的按鈕 (針對 FB/IG/新聞網站)
    # 這裡使用一些常見的 class 或文字特徵來嘗試點擊
    try:
        page.evaluate("""
            () => {
                // 定義常見的展開按鈕關鍵字
                const keywords = ['查看更多', '顯示更多', 'See more', 'Read more', '展開', '更多'];
                
                // 找出所有可能是按鈕的元素
                const elements = document.querySelectorAll('div[role="button"], span, a, button');
                
                elements.forEach(el => {
                    if (keywords.some(keyword => el.innerText.includes(keyword))) {
                        try { el.click(); } catch(e) {}
                    }
                });
            }
        """)
    except:
        pass # 點擊失敗不影響主流程

    # 2. 智慧無限捲動
    # 不使用固定的 setInterval，改用 Python 控制的迴圈檢查高度變化
    previous_height = page.evaluate("document.body.scrollHeight")
    
    # 最多嘗試滾動 20 次 (避免無限卡死)，每次間隔 2 秒
    for i in range(20):
        # 滾動到底部
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        
        # 等待內容載入 (Facebook 需要比較久)
        time.sleep(2.5)
        
        # 再次嘗試點擊新載入內容的「查看更多」
        try:
            page.evaluate("""
                () => {
                    const keywords = ['查看更多', 'See more'];
                    const elements = document.querySelectorAll('div[role="button"], span');
                    elements.forEach(el => {
                        if (keywords.some(keyword => el.innerText.includes(keyword))) {
                            try { el.click(); } catch(e) {}
                        }
                    });
                }
            """)
        except:
            pass

        # 檢查高度是否變化
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == previous_height:
            # 如果高度沒變，代表到底了，跳出迴圈
            break
        previous_height = new_height

    # 滾回頂部以免 PDF 只有下面
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1) # 等待滾回頂部後的渲染

# --- 模式一：單一網址 ---
def generate_single_pdf(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        # 加大 Viewport 讓截圖更完整
        context = browser.new_context(
            viewport={"width": 1280, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()
        try:
            st.info(f"正在連接：{url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.emulate_media(media="screen")
            
            st.info("正在執行深度挖掘 (滾動加載 + 自動展開)...")
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
            
            for i, url in enumerate(url_list):
                status_text.text(f"處理中 ({i+1}/{total}): {url}")
                page = context.new_page()
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.emulate_media(media="screen")
                    
                    # 使用新的智慧滾動邏輯
                    smart_scroll_and_expand(page)
                    
                    pdf_bytes = page.pdf(format="A4", print_background=True)
                    
                    filename = get_safe_filename(url, i)
                    zip_file.writestr(filename, pdf_bytes)
                    
                except Exception as e:
                    st.error(f"跳過錯誤連結 {url}: {str(e)[:100]}")
                finally:
                    page.close()
                    
                progress_bar.progress((i + 1) / total)

        browser.close()
        status_text.text(f"任務完成！")
        
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
    batch_urls = st.text_area("輸入網址列表", height=200)
    if st.button("執行批次轉換", key="btn_batch"):
        url_pattern = re.compile(r'(https?://\S+)')
        url_list = list(dict.fromkeys(url_pattern.findall(batch_urls)))
        
        if url_list:
            st.info(f"開始處理 {len(url_list)} 個網址...")
            zip_result = generate_batch_pdfs(url_list)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button("📦 下載 ZIP", zip_result, f"batch_{timestamp}.zip", "application/zip")
        else:
            st.warning("未偵測到有效網址")
