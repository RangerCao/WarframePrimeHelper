import keyboard
from PIL import ImageGrab
from rapidocr_onnxruntime import RapidOCR
from plyer import notification
import requests
import json
import time

# 1. 读取你通过 Wiki 生成的完美本体字典
with open("wfm_dictionary.json", 'r', encoding='utf-8') as f:
    WFM_DICT = json.load(f)
print(f"📖 成功读取 Wiki 词典！当前收录武器/战甲本体数: {len(WFM_DICT)}")

# ====== 👑 核心黑科技：零件翻译机 ======
# 将国服的零件中文名，直接映射为 WFM 的网址后缀
PART_DICT = {
    "蓝图": "blueprint", "总图": "blueprint",
    "枪机": "receiver", "枪管": "barrel", "枪托": "stock",
    "刀刃": "blade", "握柄": "handle", 
    "上弓臂": "upper_limb", "下弓臂": "lower_limb", "弓臂": "limb", "弓弦": "string",
    "护手": "guard", "圆盘": "disc", "饰物": "ornament", "外壳": "carapace",
    "锁链": "chain", "链条": "chain", 
    "头部神经光元": "neuroptics", "视光器": "neuroptics",
    "机体": "chassis", "系统": "systems", 
    "飞翼": "harness", "翅膀": "wings", "引擎": "engine",
    "握把": "grip"
}

# 2. 初始化 OCR
print("正在加载 OCR 引擎...")
ocr = RapidOCR()
print("OCR 加载完成！")

# 3. 查价格的函数
PRICE_CACHE = {} 
def fetch_48h_avg_price(url_name):
    if url_name in PRICE_CACHE:
        return PRICE_CACHE[url_name]
        
    url = f"https://api.warframe.market/v1/items/{url_name}/statistics"
    headers = {
        "Language": "zh-hans", "Platform": "pc", "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        
        # 【智能容错】：近战武器的握柄有时候叫 handle，有时候叫 grip
        if response.status_code == 404 and "_handle" in url:
            url = url.replace("_handle", "_grip")
            response = requests.get(url, headers=headers, timeout=5)
            
        print(f"   📡 请求状态: {response.status_code} -> {url}")
            
        if response.status_code == 200:
            data = response.json()
            stats_48h = data['payload']['statistics_closed']['48hours']
            if not stats_48h: return "暂无近期交易数据"
            
            latest_stat = stats_48h[-1]
            avg_price = latest_stat.get('avg_price', '未知')
            volume = latest_stat.get('volume', 0) 
            
            result_str = f"48h均价: {avg_price} 白金 (交易量: {volume})"
            PRICE_CACHE[url_name] = result_str
            return result_str
        elif response.status_code == 404:
            return "WFM 查无此物 (可能是特殊零件翻译问题)"
        else:
            return f"查询失败 (错误码: {response.status_code})"
    except Exception as e:
        return f"查询异常或网络超时"

# 4. 截图与识别逻辑 (加入零件组装逻辑)
def analyze_and_notify():
    print("\n📸 快捷键触发，正在截取并识别...")
    bbox = (500, 400, 1400, 460)  
    img = ImageGrab.grab(bbox)
    
    result, _ = ocr(img)
    if result:
        # 将本体名字按长度“从长到短”排序，确保优先匹配完整的名字
        sorted_keys = sorted(WFM_DICT.keys(), key=len, reverse=True)
        
        for line in result:
            raw_text = line[1]
            clean_ocr = raw_text.replace(" ", "").lower()
            print(f"   ▶️ 正在处理: '{clean_ocr}'")
            
            found = False
            for dict_key in sorted_keys:
                if dict_key in clean_ocr: # 比如 "雷克斯prime" 匹配上了
                    # 1. 获取本体的 url
                    base_url = WFM_DICT[dict_key]['url_name']
                    real_name = WFM_DICT[dict_key]['real_cn_name']
                    
                    # 2. 看看识别出来的字里，除了本体还剩下什么？（比如剩下 "枪机"）
                    leftover = clean_ocr.replace(dict_key, "")
                    
                    final_url = base_url
                    final_real_name = real_name
                    
                    # 3. 如果有剩下的字，去“零件翻译机”里找后缀！
                    if leftover:
                        for part_cn, part_en in PART_DICT.items():
                            if part_cn in leftover:
                                final_url = f"{base_url}_{part_en}"
                                final_real_name = f"{real_name} {part_cn}"
                                print(f"   🧩 零件组装成功: {final_real_name}")
                                break
                                
                    print(f"   🔗 准备联网查询: {final_url}")
                    price_info = fetch_48h_avg_price(final_url)
                    print(f"   💎 【{final_real_name}】 -> {price_info}")
                    
                    notification.notify(
                        title=f"WFM 估价: {final_real_name}",
                        message=price_info,
                        app_name="WF Assistant",
                        timeout=5
                    )
                    
                    found = True
                    break # 匹配到一个完整的物品后，立刻停止，去处理下一个 OCR 词
                    
            if not found:
                print("   ❌ 无法在字典中匹配该物品。")
    else:
        print("未识别到文字。")

# 5. 启动
hotkey = 'alt+q'
keyboard.add_hotkey(hotkey, analyze_and_notify)

print(f"\n🚀 完美组装版估价器已启动！按下 【 {hotkey} 】 进行测试。")
keyboard.wait('esc')