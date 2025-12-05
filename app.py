import streamlit as st
from playwright.sync_api import sync_playwright
import time
import subprocess
import zipfile
import io
import re
from datetime import datetime

# --- 初始化設定 ---
st.set_page_config(page_title="網頁情資擷取助手 (Pro)", layout="centered")
st.title("🛡️ 網頁情資擷取助手")
st.markdown("戰略記錄專用工具：支援「單點快照」與「批量歸檔」，已優化抗干擾能力。")

# --- 核心：環境檢查 (只跑一次) ---
def ensure_browsers_installed():
    try:
        with sync_playwright() as p:
            p.chromium.launch(headless=True)
    except Exception:
        with st.spinner("正在初始化核心引擎 (首次執行需 30-60 秒)..."):
            subprocess.run(["playwright", "install", "chromium"])
            subprocess.run(["playwright", "install-deps"])
            st.success("核心就緒！")

if 'browser_checked' not in st.session_state:
    ensure_browsers_installed()
    st.session_state['browser_checked'] = True

# --- 通用工具函式 ---
def get_safe_filename(url, index=None):
    # 移除 http/https
    clean_url = re.sub(r'^https?://', '', url)
    # 替換不合法字元為底線
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', clean_url)
    # 如果有傳入 index，代表是批次模式，加上序號
    if index is not None:
        return f"{index+1:02d}_{safe_name[:50]}.pdf"
    return f"{safe_name[:50]}.pdf"

def scroll_page(page):
    """模擬真人滾動，觸發 Lazy Loading"""
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
    time.sleep(2)
    page.evaluate("window.scrollTo(0, 0)")

# --- 模式一：單一網址處理邏輯 ---
def generate_single_pdf(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()
        try:
            st.info(f"正在連接目標：{url}")
            
            # [關鍵修正] 改用 domcontentloaded 以避免被廣告追蹤碼卡死 Timeout
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.emulate_media(media="screen")
            
            st.info("正在執行深度滾動掃描...")
            scroll_page(page)
            
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "1cm", "bottom": "1cm", "left": "1cm", "right": "1cm"}
            )
            return pdf_bytes
        except Exception as e:
            st.error(f"擷取失敗：{e}")
            return None
        finally:
            browser.close()

# --- 模式二：批次網址處理邏輯 ---
def generate_batch_pdfs(url_list):
    zip_buffer = io.BytesIO()
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            total = len(url_list)
            success_count = 0
            
            for i, url in enumerate(url_list):
                status_text.text(f"正在處理 ({i+1}/{total}): {url}")
                page = context.new_page()
                
                try:
                    # [關鍵修正] 改用 domcontentloaded 提升對 Pixnet 等重廣告網站的相容性
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.emulate_media(media="screen")
                    scroll_page(page)
                    
                    pdf_bytes = page.pdf(
                        format="A4",
                        print_background=True,
                        margin={"top": "1cm", "bottom": "1cm", "left": "1cm", "right": "1cm"}
                    )
                    
                    filename = get_safe_filename(url, i)
                    zip_file.writestr(filename, pdf_bytes)
                    success_count += 1
                    
                except Exception as e:
                    # 容錯處理：單一失敗不影響整體，只印出錯誤訊息
                    st.error(f"跳過錯誤連結 {url}: {str(e)[:100]}...") 
                finally:
                    page.close()
                    
                progress_bar.progress((i + 1) / total)

        browser.close()
        status_text.text(f"任務完成。成功擷取 {success_count} / {total} 個頁面。")
        
    zip_buffer.seek(0)
    return zip_buffer

# --- UI 介面佈局 (Tabs) ---
tab1, tab2 = st.tabs(["🔍 單一精確擷取", "📚 批量戰略歸檔"])

# === Tab 1: 單一模式 ===
with tab1:
    st.header("單一網頁轉 PDF")
    single_url = st.text_input("輸入網址", placeholder="https://www.example.com")
    
    if st.button("執行轉換", key="btn_single"):
        if not single_url:
            st.warning("請輸入網址")
        else:
            pdf_data = generate_single_pdf(single_url)
            if pdf_data:
                file_name = get_safe_filename(single_url)
                st.success("轉換成功！")
                st.download_button(
                    label="下載 PDF",
                    data=pdf_data,
                    file_name=file_name,
                    mime="application/pdf"
                )

# === Tab 2: 批次模式 (含 Regex 容錯) ===
with tab2:
    st.header("批量網頁轉 PDF (ZIP 打包)")
    batch_urls = st.text_area(
        "輸入網址列表 (支援混合文字貼上，系統會自動過濾出網址)", 
        height=200,
        placeholder="即使貼入含有說明的文字，例如：\n1. Google首頁 https://google.com\n2. 雅虎 https://yahoo.com\n系統也能自動識別。"
    )
    
    if st.button("執行批次轉換", key="btn_batch"):
        # --- 升級後的邏輯：使用 Regex 自動抓取網址 ---
        # 尋找所有以 http 或 https 開頭，直到遇到空白為止的字串
        url_pattern = re.compile(r'(https?://\S+)')
        url_list = url_pattern.findall(batch_urls)
        
        # 去除重複網址 (保持順序)
        url_list = list(dict.fromkeys(url_list))

        if not url_list:
            st.warning("⚠️ 未偵測到有效網址，請確認內容包含 http:// 或 https://")
        else:
            st.info(f"已識別 {len(url_list)} 個有效網址，開始作業...")
            
            if len(url_list) > 10:
                st.warning("💡 網址較多，請耐心等候...")
            
            zip_result = generate_batch_pdfs(url_list)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button(
                label="📦 下載 ZIP 壓縮檔",
                data=zip_result,
                file_name=f"strategic_snapshot_{timestamp}.zip",
                mime="application/zip"
            )
