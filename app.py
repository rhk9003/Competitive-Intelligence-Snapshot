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
        with st.spinner("正在初始化核心引擎 (下載瀏覽器 binary)..."):
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

# --- 小工具：用文字點擊一批按鈕 ---
def click_by_text(page, texts):
    for t in texts:
        try:
            loc = page.locator(f"text={t}")
            count = loc.count()
            for i in range(count):
                try:
                    loc.nth(i).click()
                except:
                    pass
        except:
            # 這個文字不存在就略過
            pass

# --- 深度互動滾動邏輯（簡化穩定版） ---
def smart_scroll_and_expand(page, max_scroll=8):
    """
    針對 Infinite Scroll 網站的智慧滾動與點擊展開。
    專門處理 FB Ad Library 裡的：
    - 廣告要點
    - 查看摘要詳情
    - 查看廣告詳情
    以及一般的「查看更多 / See more」。
    """

    # 先在目前畫面把能展開的都展開一次
    click_by_text(page, [
        "廣告要點", "查看摘要詳情", "查看廣告詳情",
        "查看更多", "顯示更多", "See more", "Read more", "展開", "更多"
    ])
    time.sleep(1)

    previous_height = page.evaluate("document.body.scrollHeight")

    for i in range(max_scroll):
        # 捲到最底
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2.0)

        # 捲完再把新出現的按鈕展開一次
        click_by_text(page, [
            "廣告要點", "查看摘要詳情", "查看廣告詳情",
            "查看更多", "顯示更多", "See more", "Read more", "展開", "更多"
        ])

        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == previous_height:
            break
        previous_height = new_height

    # 回到頂端，讓 PDF 從最上面開始
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)

# --- 模式一：單一網址 ---
def generate_single_pdf(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
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
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
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
        url_pattern = re.compile(r'(https?://\S+)')
        url_list = list(dict.fromkeys(url_pattern.findall(batch_urls)))

        if url_list:
            st.info(f"開始處理 {len(url_list)} 個網址...")
            zip_result = generate_batch_pdfs(url_list)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button(
                "📦 下載 ZIP",
                zip_result,
                f"batch_{timestamp}.zip",
                "application/zip"
            )
        else:
            st.warning("未偵測到有效網址")
