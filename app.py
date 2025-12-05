import streamlit as st
from playwright.sync_api import sync_playwright
import time
import subprocess
import zipfile
import io
import re
import os
from datetime import datetime

# --- 初始化頁面設定 ---
st.set_page_config(page_title="網頁情資擷取助手 (Ultimate)", layout="centered")
st.title("🛡️ 網頁情資擷取助手")
st.markdown("### 戰略記錄專用工具\n支援：FB/IG 自動展開、Pixnet 抗干擾模式、批量網址自動過濾。")

# --- 1. 部署與環境處理 (檔案旗標優化) ---
def ensure_browsers_installed():
    """檢查並安裝 Playwright 瀏覽器，使用檔案標記避免重複執行"""
    # 如果標記檔案存在，代表已經安裝過，直接跳過
    if os.path.exists(".playwright_ready"):
        return

    try:
        with st.spinner("正在初始化核心引擎 (首次執行需時約 60 秒，請稍候)..."):
            # check=True 確保失敗時會報錯
            subprocess.run(["playwright", "install", "chromium"], check=True)
            subprocess.run(["playwright", "install-deps"], check=True)
            
            # 建立標記檔案，下次就不會再跑這段
            with open(".playwright_ready", "w") as f:
                f.write("ready")
            st.success("核心就緒！")
    except subprocess.CalledProcessError as e:
        st.error(f"核心安裝失敗，請檢查系統日誌。錯誤代碼：{e}")
        st.stop() # 停止執行以避免後續錯誤

if 'browser_checked' not in st.session_state:
    ensure_browsers_installed()
    st.session_state['browser_checked'] = True

# --- 2. Browser / Context 重構 (統一工廠模式) ---
def create_browser_context(p):
    """統一建立 Browser 和 Context，模擬大螢幕以觸發完整內容"""
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 1080}, # 1280x1080 能看到更多內容
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    )
    return browser, context

# --- 3. 智慧互動引擎 (滾動 + 點擊展開) ---
def smart_scroll_and_expand(page, max_scrolls=15, delay=2.0):
    """
    參數化且具備防誤判機制的智慧滾動
    """
    st.caption(f"啟動智慧挖掘引擎：預計嘗試滾動 {max_scrolls} 次...")
    
    # 嘗試點擊展開 (針對 FB/IG 的 '查看更多')
    try:
        page.evaluate("""
            () => {
                const keywords = ['查看更多', '顯示更多', 'See more', 'Read more', '更多', '展開'];
                // 擴大搜尋範圍：找 div[role=button], span, a, button
                const elements = document.querySelectorAll('div[role="button"], span, a, button'); 
                elements.forEach(el => {
                    if (keywords.some(keyword => el.innerText.includes(keyword))) {
                        try { el.click(); } catch(e) {}
                    }
                });
            }
        """)
    except:
        pass

    previous_height = page.evaluate("document.body.scrollHeight")
    no_change_count = 0 
    
    # 滾動迴圈
    for i in range(max_scrolls):
        # 滾到底部
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(delay)
        
        # 再次嘗試點擊新載入的內容
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

        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == previous_height:
            no_change_count += 1
            # 連續 2 次高度沒變才認定到底，避免網路延遲誤判
            if no_change_count >= 2:
                break
        else:
            no_change_count = 0 # 高度有變，重置計數
            previous_height = new_height

    # 滾回頂部，並稍等一下讓 Header 歸位
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1.0)

# --- 4. 通用工具 (檔名清理) ---
def get_safe_filename(url, index=None):
    clean_url = re.sub(r'^https?://', '', url)
    # [新增] 去除網址尾端常見的標點符號，避免 Regex 抓太寬
    clean_url = clean_url.rstrip('，。；,:;)]】』」》')
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', clean_url)
    
    # 限制檔名長度避免報錯
    safe_name = safe_name[:80]
    
    if index is not None:
        return f"{index+1:02d}_{safe_name}.pdf"
    return f"{safe_name}.pdf"

# --- 5. 核心邏輯 (統一處理單頁與批次) ---
def generate_pdf_logic(url_list, is_batch=False):
    results = [] # 紀錄執行結果 (Log)
    zip_buffer = io.BytesIO() if is_batch else None
    single_pdf = None
    
    with sync_playwright() as p:
        browser, context = create_browser_context(p)
        
        try:
            # === 批次模式邏輯 ===
            if is_batch:
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    total = len(url_list)
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, url in enumerate(url_list):
                        status_text.text(f"處理中 ({i+1}/{total}): {url}")
                        page = context.new_page()
                        try:
                            # 1. 前往網址 (使用 domcontentloaded 抗廣告)
                            page.goto(url, wait_until="domcontentloaded", timeout=60000)
                            page.emulate_media(media="screen")
                            
                            # 2. 智慧滾動
                            smart_scroll_and_expand(page, max_scrolls=15, delay=2.0)
                            
                            # 3. 產出 PDF
                            pdf_bytes = page.pdf(
                                format="A4", 
                                print_background=True,
                                margin={"top": "1cm", "bottom": "1cm", "left": "1cm", "right": "1cm"}
                            )
                            
                            filename = get_safe_filename(url, i)
                            zip_file.writestr(filename, pdf_bytes)
                            results.append({"status": "success", "url": url})
                            
                        except Exception as e:
                            # 收集錯誤，不直接中斷
                            err_msg = str(e)[:100]
                            results.append({"status": "error", "url": url, "msg": err_msg})
                        finally:
                            page.close()
                        progress_bar.progress((i + 1) / total)
                    
                    status_text.text("佇列處理完成。")

            # === 單頁模式邏輯 ===
            else:
                page = context.new_page()
                url = url_list[0]
                try:
                    st.info(f"正在連接：{url}")
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.emulate_media(media="screen")
                    
                    st.info("正在執行深度挖掘...")
                    smart_scroll_and_expand(page, max_scrolls=20, delay=2.5) # 單頁給多一點耐心
                    
                    st.info("正在渲染 PDF...")
                    single_pdf = page.pdf(
                        format="A4", 
                        print_background=True,
                        margin={"top": "1cm", "bottom": "1cm", "left": "1cm", "right": "1cm"}
                    )
                    results.append({"status": "success", "url": url})
                except Exception as e:
                    st.error(f"載入失敗：{url}。\n原因：{str(e)[:200]}")
                    results.append({"status": "error", "url": url, "msg": str(e)})
                finally:
                    page.close()

        finally:
            browser.close()
            
    return zip_buffer, results, single_pdf

# --- UI 介面佈局 ---
tab1, tab2 = st.tabs(["🔍 單一精確擷取", "📚 批量戰略歸檔"])

# === Tab 1: 單一模式 ===
with tab1:
    st.header("單一網頁轉 PDF")
    single_url = st.text_input("輸入網址", placeholder="https://www.facebook.com/ads/library/...")
    
    if st.button("執行轉換", key="btn_single"):
        if single_url:
            with st.spinner('AI 正在讀取頁面並展開內容...'):
                _, logs, pdf = generate_pdf_logic([single_url], is_batch=False)
                
            if pdf:
                st.success("轉換成功！")
                fname = get_safe_filename(single_url)
                st.download_button(
                    label="下載 PDF", 
                    data=pdf, 
                    file_name=fname, 
                    mime="application/pdf"
                )

# === Tab 2: 批次模式 ===
with tab2:
    st.header("批量網頁轉 PDF (自動過濾雜訊)")
    batch_text = st.text_area(
        "貼上包含網址的文字 (系統會自動過濾出連結)", 
        height=200,
        placeholder="可以直接貼上Excel內容、Line對話紀錄或帶有中文說明的清單..."
    )
    
    if st.button("執行批次轉換", key="btn_batch"):
        # Regex: 抓取 http/https 開頭，直到遇到空白或換行為止
        raw_urls = re.findall(r'(https?://\S+)', batch_text)
        # 去重並保持順序
        url_list = list(dict.fromkeys(raw_urls))
        
        # 額外清理：去除尾端可能誤抓的標點
        url_list = [u.rstrip('，。；,:;)]】』」》') for u in url_list]

        if not url_list:
            st.warning("⚠️ 未偵測到有效網址")
        else:
            st.info(f"已識別 {len(url_list)} 個有效網址，開始作業...")
            
            with st.spinner('批次作業引擎運行中...'):
                zip_buf, logs, _ = generate_pdf_logic(url_list, is_batch=True)
            
            # --- 顯示結果摘要 (優化 UX) ---
            success_count = sum(1 for r in logs if r['status'] == 'success')
            fail_count = len(logs) - success_count
            
            if fail_count == 0:
                st.balloons()
                st.success(f"全數完成！成功處理 {success_count} 個頁面。")
            else:
                st.warning(f"作業結束。成功: {success_count} / 失敗: {fail_count}")
                with st.expander("查看失敗清單與原因"):
                    for r in logs:
                        if r['status'] == 'error':
                            st.write(f"❌ **{r['url']}**")
                            st.caption(f"原因: {r['msg']}")
            
            # 提供下載
            if zip_buf:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M")
                zip_buf.seek(0)
                st.download_button(
                    label="📦 下載 ZIP 壓縮檔",
                    data=zip_buf,
                    file_name=f"strategic_snapshot_{timestamp}.zip",
                    mime="application/zip"
                )
