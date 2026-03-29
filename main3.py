import keyboard
from PIL import ImageGrab
from rapidocr_onnxruntime import RapidOCR
from plyer import notification
import cloudscraper # <--- 引入新库
import json
import os
import time

# 创建一个全局的破盾请求器 (替代 requests)
scraper = cloudscraper.create_scraper(browser={
    'browser': 'chrome',
    'platform': 'windows',
    'desktop': True
})

# ================= 1. Warframe Market 专属词典加载器 =================
DICT_FILE = "wfm_dictionary.json"

def load_or_fetch_wfm_dict():
    if os.path.exists(DICT_FILE):
        print("📖 读取本地 WFM 物品词典...")
        with open(DICT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    print("🌍 首次运行，正在从 WFM 下载全量物品词典 (约需几秒钟)...")
    url = "https://api.warframe.market/v1/items"
    
    # 关键：language 小写，并且加上接受 JSON 的头部
    headers = {
        "Language": "zh-hans",    # 告诉它要中文
        "Platform": "pc",         # 👈 灵魂暗号：告诉它我是 PC 端玩家！不加必报 404
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        # 【修改点】用 scraper.get 替代 requests.get
        response = scraper.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        items_list = data['payload']['items']
        wfm_dict = {}
        
        for item in items_list:
            clean_cn_name = item['item_name'].replace(" ", "").lower()
            wfm_dict[clean_cn_name] = {
                "url_name": item['url_name'],
                "real_cn_name": item['item_name'] 
            }
            
        with open(DICT_FILE, 'w', encoding='utf-8') as f:
            json.dump(wfm_dict, f, ensure_ascii=False, indent=2)
            
        print(f"✅ 词典下载完成！共收录 {len(wfm_dict)} 个物品。")
        return wfm_dict
        
    except Exception as e:
        print(f"❌ 下载词典失败: {e}")
        # 【备用方案提示】
        print("💡 提示：如果你使用了游戏加速器，请尝试暂时关闭加速器后再运行本程序。")
        return {}

# ================= 2. 获取 48 小时均价的爬虫 =================
PRICE_CACHE = {} 

def fetch_48h_avg_price(url_name):
    if url_name in PRICE_CACHE:
        return PRICE_CACHE[url_name]
        
    print(f"🔍 正在查询: {url_name} ...")
    url = f"https://api.warframe.market/v1/items/{url_name}/statistics"
    
    headers = {
        "Language": "zh-hans",
        "Platform": "pc",         # 👈 这里也要加上
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        # 【修改点】同样使用 scraper.get
        response = scraper.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        stats_48h = data['payload']['statistics_closed']['48hours']
        
        if not stats_48h:
            return "暂无近期交易数据"
            
        latest_stat = stats_48h[-1]
        
        # 提取平均价、最高价等，让提示更丰富
        avg_price = latest_stat.get('avg_price', '未知')
        max_price = latest_stat.get('max_price', '未知')
        volume = latest_stat.get('volume', 0) 
        
        result_str = f"均价: {avg_price} 白金 (最高: {max_price}, 交易量: {volume})"
        
        PRICE_CACHE[url_name] = result_str
        return result_str
        
    except Exception as e:
        return f"查询价格失败 ({e})"


# ================= 3. 主程序初始化与运行 =================
# 初始化词典和 OCR
WFM_DICT = load_or_fetch_wfm_dict()
print("正在加载 OCR 引擎...")
ocr = RapidOCR()
print("OCR 加载完成！")

def analyze_and_notify():
    print("\n📸 快捷键触发，正在截取并识别...")
    # TODO: 这里务必改成你真实的 Warframe 遗物奖励界面的物品名字坐标！
    bbox = (500, 400, 1400, 460)  
    img = ImageGrab.grab(bbox)
    
    result, _ = ocr(img)
    
    if result:
        # 收集画面上的所有文字
        ocr_texts = []
        for line in result:
            ocr_texts.extend(line[1].split())
            
        print(f"📝 OCR 原始提取: {ocr_texts}")
        
        # 匹配逻辑
        for text in ocr_texts:
            if len(text) < 2: # 忽略太短的乱码
                continue
                
            # 清洗 OCR 文字以匹配词典：去空格、转小写
            clean_ocr = text.replace(" ", "").lower()
            
            # 在全量词典中寻找匹配
            if clean_ocr in WFM_DICT:
                item_data = WFM_DICT[clean_ocr]
                url_name = item_data['url_name']
                real_name = item_data['real_cn_name']
                
                # 查价格
                price_info = fetch_48h_avg_price(url_name)
                print(f"💎 【{real_name}】 -> {price_info}")
                
                # 弹窗提示
                notification.notify(
                    title=f"WFM 估价: {real_name}",
                    message=price_info,
                    app_name="WF Assistant",
                    timeout=6
                )
                time.sleep(0.5) # 防止同时查多个物品时并发太快
    else:
        print("未在区域内识别到物品名称。")

# 绑定快捷键
hotkey = 'alt+q'
keyboard.add_hotkey(hotkey, analyze_and_notify)

print(f"\n🚀 Warframe 估价器已启动！在游戏中按下 【 {hotkey} 】 进行识图估价。")
keyboard.wait('esc')