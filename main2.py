import keyboard
from PIL import ImageGrab
from rapidocr_onnxruntime import RapidOCR
from plyer import notification
import requests
from bs4 import BeautifulSoup
import time

# 1. 内存缓存字典：记录已经查过的价格，避免重复爬取被封 IP
# 格式类似: {"力量护腕": "均价: 150金", "铁剑": "均价: 20金"}
PRICE_CACHE = {}

# 2. 初始化 OCR
print("正在加载 OCR 模型...")
ocr = RapidOCR()
print("模型加载完成！")

# 3. 核心爬虫函数：只爬取单个物品的 48 小时均价
def fetch_item_price(item_name):
    # 如果缓存里有，直接秒回！不发网络请求！
    if item_name in PRICE_CACHE:
        return PRICE_CACHE[item_name]
    
    print(f"🌍 正在联网查询【{item_name}】的最新价格...")
    
    # 【注意！】这里需要替换成那个网站真实的搜索链接或物品链接拼接规则
    # 假设网站的物品页面是 https://www.jiaoyi.com/item/力量护腕
    url = f"https://warframe.market/zh-hans/items/venka_prime_blueprint/statistics{item_name}" 
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # 发送请求去获取网页内容
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        # 使用 BeautifulSoup 解析网页 HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 【极其关键的一步】：你需要去网页 F12 里看那个 48小时均价的 HTML 标签是什么
        # 假设均价写在一个 class 叫 "price-48h-avg" 的 span 标签里
        # 类似这样： <span class="price-48h-avg">150 金币</span>
        price_tag = soup.find('span', class_='price-48h-avg') 
        
        if price_tag:
            price_text = price_tag.text.strip()
            result_str = f"48小时均价: {price_text}"
            
            # 存入缓存，下次再查就不用联网了
            PRICE_CACHE[item_name] = result_str
            return result_str
        else:
            return "未在网页中找到价格标签"
            
    except Exception as e:
        return f"查询失败: 网络错误或物品不存在"

# 4. 你的核心游戏交互逻辑
def analyze_and_notify():
    print("\n📸 快捷键触发，正在截取并识别...")
    bbox = (500, 400, 1400, 460)  # 你的截图坐标
    img = ImageGrab.grab(bbox)
    
    result, _ = ocr(img)
    
    if result:
        # 你的按空格分词逻辑
        recognized_items = []
        for line in result:
            recognized_items.extend(line[1].split())
            
        print(f"✅ 画面中检测到: {recognized_items}")
        
        # 遍历屏幕上的每一个物品，去查价格
        for item_name in recognized_items:
            # 去掉一些太短的乱码文字，比如长度大于1才查
            if len(item_name) > 1 and item_name!="Forma蓝图":
                # 调用上面的爬虫函数
                price_info = fetch_item_price(item_name)
                
                print(f"💰 【{item_name}】 -> {price_info}")
                
                # 弹出系统通知给用户
                notification.notify(
                    title=f"物品估价: {item_name}",
                    message=price_info,
                    app_name="Game Assistant",
                    timeout=5
                )
                
                # 稍微停顿0.5秒，防止同时查4个物品时发包太快被网站拦截
                time.sleep(0.5) 
    else:
        print("未识别到文字。")

# 5. 绑定快捷键并保持运行
hotkey = 'alt+q'
keyboard.add_hotkey(hotkey, analyze_and_notify)

print(f"\n🚀 估价辅助已启动！请在游戏中按下 【 {hotkey} 】 进行实时估价。")
keyboard.wait('esc')