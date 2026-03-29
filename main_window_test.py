import tkinter as tk
from tkinter import scrolledtext
import keyboard
from PIL import ImageGrab
from rapidocr_onnxruntime import RapidOCR
import requests
import json
import threading
import time

# ====== 配置区域 ======
HOTKEY = 'alt+q'           # 快捷键
WFM_DICT_PATH = "wfm_dictionary.json" # 字典路径
SCAN_BBOX = (500, 400, 1400, 460)     # 截图区域
# =====================

class WFPriceHelperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Warframe 价格查询助手 (GUI版)")
        self.root.geometry("600x450")
        self.root.attributes("-topmost", False) # 主窗口不需要一直置顶

        # 1. 界面布局
        self.setup_ui()

        # 2. 数据初始化
        self.price_cache = {}
        self.part_dict = {
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
        
        # 3. 异步加载资源 (防止启动卡顿)
        self.log("正在初始化系统，请稍候...")
        threading.Thread(target=self.init_resources, daemon=True).start()

    def setup_ui(self):
        # 顶部说明
        lbl_info = tk.Label(self.root, text=f"快捷键: [{HOTKEY}]  |  截图区域: {SCAN_BBOX}", font=("微软雅黑", 10, "bold"))
        lbl_info.pack(pady=5)

        # 日志滚动框
        self.log_text = scrolledtext.ScrolledText(self.root, height=15, state='disabled', font=("Consolas", 9))
        self.log_text.pack(fill='both', expand=True, padx=10, pady=5)
        
        # 底部状态栏
        self.status_var = tk.StringVar()
        self.status_var.set("状态: 正在启动...")
        lbl_status = tk.Label(self.root, textvariable=self.status_var, anchor='w', relief='sunken')
        lbl_status.pack(fill='x')

    def log(self, msg):
        """ 线程安全的日志输出 """
        def _update():
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, f"{msg}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        self.root.after(0, _update)

    def update_status(self, msg):
        self.root.after(0, lambda: self.status_var.set(f"状态: {msg}"))

    def init_resources(self):
        # 加载 OCR
        try:
            self.ocr = RapidOCR()
            self.log("✅ OCR 引擎加载完成")
        except Exception as e:
            self.log(f"❌ OCR 加载失败: {e}")
            return

        # 加载字典
        try:
            with open(WFM_DICT_PATH, 'r', encoding='utf-8') as f:
                self.wfm_dict = json.load(f)
            self.log(f"📖 词典加载完成，收录物品数: {len(self.wfm_dict)}")
            # 按长度排序键，方便后续匹配
            self.sorted_keys = sorted(self.wfm_dict.keys(), key=len, reverse=True)
        except Exception as e:
            self.log(f"❌ 无法读取字典 ({WFM_DICT_PATH}): {e}")
            self.wfm_dict = {}

        # 注册快捷键
        keyboard.add_hotkey(HOTKEY, self.on_hotkey)
        self.log(f"🚀 系统就绪！请在游戏中按 {HOTKEY} 进行查询。")
        self.update_status("等待指令...")

    def on_hotkey(self):
        """ 快捷键触发的回调，必须在独立线程运行以免卡住 GUI """
        self.update_status("正在识别...")
        threading.Thread(target=self.process_screenshot, daemon=True).start()

    def show_overlay(self, title, content):
        """ 创建一个漂亮的悬浮窗显示结果 """
        def _show():
            # 创建顶级窗口
            top = tk.Toplevel(self.root)
            top.overrideredirect(True) # 无边框
            top.attributes('-topmost', True) # 永远置顶
            top.attributes('-alpha', 0.90)   #稍微透明一点
            top.configure(bg='#1c1c1c')      # 深色背景

            # 居中显示或者显示在屏幕左上角
            # 这里设置为屏幕左上角稍微靠下的位置，避免遮挡准星
            screen_x = 100 
            screen_y = 200
            top.geometry(f"+{screen_x}+{screen_y}")

            # 内容框架
            frame = tk.Frame(top, bg='#1c1c1c', padx=15, pady=10, highlightbackground="#d4af37", highlightthickness=2) # 金色边框
            frame.pack()

            # 物品名称
            lbl_title = tk.Label(frame, text=title, fg='#d4af37', bg='#1c1c1c', font=("微软雅黑", 14, "bold"))
            lbl_title.pack(anchor='w')

            # 价格信息
            lbl_content = tk.Label(frame, text=content, fg='white', bg='#1c1c1c', font=("微软雅黑", 11))
            lbl_content.pack(anchor='w', pady=(5, 0))

            # 5秒后自动销毁
            top.after(5000, top.destroy)
        
        self.root.after(0, _show)

    def fetch_price(self, url_name):
        if url_name in self.price_cache:
            return self.price_cache[url_name]
        
        url = f"https://api.warframe.market/v1/items/{url_name}/statistics"
        headers = {"Language": "zh-hans", "Platform": "pc"}
        
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            # 容错处理 grip/handle
            if resp.status_code == 404 and "_handle" in url:
                url = url.replace("_handle", "_grip")
                resp = requests.get(url, headers=headers, timeout=5)

            if resp.status_code == 200:
                stats = resp.json()['payload']['statistics_closed']['48hours']
                if not stats: return "暂无近期数据"
                latest = stats[-1]
                res = f"均价: {latest.get('avg_price', '?')} P | 销量: {latest.get('volume', 0)}"
                self.price_cache[url_name] = res
                return res
            return "查无此物 (404)"
        except:
            return "网络超时"

    def process_screenshot(self):
        self.log(f"\n📸 [{time.strftime('%H:%M:%S')}] 开始截取...")
        try:
            img = ImageGrab.grab(SCAN_BBOX)
            result, _ = self.ocr(img)
            
            if not result:
                self.log("   ⚠️ 未识别到文字")
                self.update_status("未识别到文字")
                return

            found_any = False
            for line in result:
                raw_text = line[1]
                clean_ocr = raw_text.replace(" ", "").lower()
                
                for dict_key in self.sorted_keys:
                    if dict_key in clean_ocr:
                        # 匹配成功
                        base_url = self.wfm_dict[dict_key]['url_name']
                        real_name = self.wfm_dict[dict_key]['real_cn_name']
                        
                        # 检查零件
                        leftover = clean_ocr.replace(dict_key, "")
                        final_url = base_url
                        final_name = real_name

                        if leftover:
                            for cn, en in self.part_dict.items():
                                if cn in leftover:
                                    final_url += f"_{en}"
                                    final_name += f" {cn}"
                                    break
                        
                        self.log(f"   🔎 匹配: {final_name} -> 查询中...")
                        price_info = self.fetch_price(final_url)
                        self.log(f"   💰 结果: {price_info}")
                        
                        # 触发悬浮窗
                        self.show_overlay(final_name, price_info)
                        
                        found_any = True
                        self.update_status(f"完成: {final_name}")
                        return # 找到一个就退出，避免重复弹窗

            if not found_any:
                self.log("   ❌ 无法匹配字典中的物品")
                self.update_status("无法匹配")

        except Exception as e:
            self.log(f"❌ 运行出错: {e}")
            self.update_status("运行出错")

if __name__ == "__main__":
    root = tk.Tk()
    app = WFPriceHelperApp(root)
    # 处理关闭窗口事件，确保彻底退出
    root.protocol("WM_DELETE_WINDOW", lambda: (keyboard.unhook_all(), root.destroy()))
    root.mainloop()