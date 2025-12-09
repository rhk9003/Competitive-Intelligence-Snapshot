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
        # 嘗試啟動瀏覽器看是否成功
        with sync_playwright() as p:
            p.chromium.launch(headless=True)
    except Exception:
        with st.spinner("正在初始化核心引擎 (下載瀏覽器 binary)..."):
            # [關鍵修正] 移除了 'install-deps'，因為它需要 root 權限，且 packages.txt 已經處理了系統依賴
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
    這裡特別為 FB 廣告檔案庫加入：
    - 廣告要點
    - 查看摘要詳情
    - 查看廣告詳情
    等按鈕的自動點擊
    """

    def click_expand_targets():
        page.evaluate("""
            () => {
                const keywords = [
                    '查看更多', '顯示更多', 'See more', 'Read more', '展開', '更多',
                    '廣告要點', '查看摘要詳情', '查看廣告詳情', '查看廣告內容', '查看詳情'
                ];

                // 盡量把可能可點擊的元素都掃一輪
                const elements = Array.from(
                    document.querySelectorAll('div[role="button"], span, a, button')
                );

                elements.forEach(el => {
                    const text = (el.innerText || '').trim();
                    if (!text) return;

                    if (keywords.some(k => text.includes(k))) {
                        try {
                            el.click();
                        } catch (e) {}
                    }
                });
            }
        """)

    # 先在頂部點一次
    click_expand_targets()
    time.sleep(1)

    # 智慧無限捲動
    previous_height = page.evaluate("document.body.scrollHeight")

    # 最多嘗試滾動 20 次
    for i in range(20):
        # 往下捲到底
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2.5)  # 等新內容載入

        # 對新載入的內容再掃一輪「展開 / 廣告詳情 / 廣告要點」
        click_expand_targets()

        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == previous_height:
            break
        previous_height = new_height

    # 再回到最上方，讓 PDF 從頁面開頭開始
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)

# --- 模式一：單一網址 ---
def generate_single_pdf(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        # 加大 Viewport
        context = browser.new_context(
            viewport={"width": 1280, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
        )
        page = context.new_page()
        try:
            st.info(f"正在連接：{url}")
            # 改回 domcontentloaded 避免被廣告卡死
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.emulate_media(media="screen")

            st.info("正在執行深度挖掘 (滾動加載 + 自動展開廣告要點)...")
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
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev]()
