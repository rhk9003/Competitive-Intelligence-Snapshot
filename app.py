# --- [關鍵修正] 針對 "..." 與符號的深度互動滾動邏輯 ---
def smart_scroll_and_expand(page):
    """
    針對 Infinite Scroll 網站的智慧滾動與點擊展開
    修正：增加對 "..." 與 "…" 符號的識別
    """
    # 定義通用的展開邏輯 JS (包含符號識別)
    expand_logic = """
        () => {
            // 新增 '...', '…' 以及常見的英文變體
            const keywords = ['查看更多', '顯示更多', 'See more', 'Read more', '展開', '更多', '...', '…', 'See details'];
            
            // 擴大選取範圍，有時候按鈕只是一個普通的 div 或 span
            const elements = document.querySelectorAll('div[role="button"], span, a, button, div[class*="SeeMore"], div');
            
            elements.forEach(el => {
                // 檢查文字是否包含關鍵字
                const text = el.innerText ? el.innerText.trim() : "";
                
                // 額外檢查：如果是純符號的按鈕，通常文字很短
                const isSymbolButton = (text === '...' || text === '…');
                
                if (keywords.some(keyword => text.includes(keyword)) || isSymbolButton) {
                    // 避免點擊到太長的段落 (防止誤觸內文中剛好有 ... 的長文章)
                    if (text.length < 50 || isSymbolButton) {
                        try { 
                            el.click(); 
                            // 點擊後稍微標記一下避免重複點擊 (非必要但保險)
                            el.setAttribute('data-clicked', 'true');
                        } catch(e) {}
                    }
                }
            });
        }
    """

    # 1. 初始嘗試點擊
    try:
        page.evaluate(expand_logic)
    except:
        pass 

    # 2. 智慧無限捲動
    previous_height = page.evaluate("document.body.scrollHeight")
    
    # 最多嘗試滾動 20 次
    for i in range(20):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        
        # FB 需要較長的載入緩衝
        time.sleep(2.5)
        
        # 再次嘗試點擊新載入內容 (包含 ...)
        try:
            page.evaluate(expand_logic)
        except:
            pass

        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == previous_height:
            # 如果高度沒變，再多等一下確認是不是網速慢
            time.sleep(2)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == previous_height:
                break
        previous_height = new_height

    # 滾動回頂部以便截圖
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)
