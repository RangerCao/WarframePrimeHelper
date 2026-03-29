import keyboard
from PIL import ImageGrab
from rapidocr_onnxruntime import RapidOCR
from plyer import notification
import json
import os

# 1. 读取本地 JSON 数据
def load_data():
    if os.path.exists('data.json'):
        with open('data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

LOCAL_DATABASE = load_data()

# 2. 初始化 OCR 引擎
print("正在加载 OCR 模型，请稍候...")
ocr = RapidOCR()
print("模型加载完成！")

def analyze_and_notify():
    print("快捷键触发，截取画面...")
    
    # 3. 设定截图区域 (左, 上, 右, 下)，请根据实际情况修改
    bbox = (500, 400, 1400, 460) 
    img = ImageGrab.grab(bbox)
    
    print("正在识别文字...")
    result, _ = ocr(img)
    
    if result:
        # 1. 提取并智能分词
        recognized_items = []
        for line in result:
            text = line[1] # 提取这一行的文字
            # 使用 split() 自动按空格切分，并加入到我们的列表中
            recognized_items.extend(text.split()) 
            
        print(f"✅ 成功提取到 {len(recognized_items)} 个道具: {recognized_items}")
        
        # 2. 精确匹配逻辑
        matched_count = 0
        # 遍历我们提取出来的每一个道具名字
        for item_name in recognized_items:
            # 直接去数据库字典里找，是不是刚好有这个名字 (精确匹配)
            if item_name in LOCAL_DATABASE:
                description = LOCAL_DATABASE[item_name]
                print(f"🎯 发现目标: 【{item_name}】 -> {description}")
                
                # 弹出提示
                notification.notify(
                    title=f"发现目标: {item_name}",
                    message=description,
                    app_name="Game Assistant",
                    timeout=5
                )
                matched_count += 1
                
        if matched_count == 0:
            print("没有在截图中发现需要提示的物品。")
    else:
        print("未识别到任何文字。")

# 6. 绑定快捷键 (你可以改成 alt+e, ctrl+q 等)
hotkey = 'alt+q'
keyboard.add_hotkey(hotkey, analyze_and_notify)

print("-" * 30)
print(f"🚀 辅助软件已启动运行！")
print(f"👉 请在游戏中按下 【 {hotkey} 】 进行识别。")
print(f"⏹️ 按下 【 ESC 】 退出软件。")
print("-" * 30)

keyboard.wait('esc')