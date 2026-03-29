import customtkinter as ctk
import tkinter as tk
from PIL import Image, ImageGrab, ImageTk 
import keyboard
from rapidocr_onnxruntime import RapidOCR
import requests
import json
import threading
import time
import os
import sys

# ====== 配置区域 ======
DEFAULT_CONFIG = {
    "hotkey": "alt+q",
    "bbox": [0,0,1920,1080]
}
CONFIG_FILE = "config.json"
WFM_DICT_PATH = "wfm_dictionary.json"
QR_IMAGE_PATH = "qr.png" 

# ====== 🎨 零件翻译映射表 ======
# 这里的用途改为：如果字典里的 url 只是本体（如 ash_prime），才用这个表去拼后缀
PART_MAP = {
    "蓝图": "blueprint", "总图": "blueprint",
    "机体": "chassis", "系统": "systems", "头部神经光元": "neuroptics",
    "枪机": "receiver", "枪管": "barrel", "枪托": "stock", "连接器": "link",
    "刀刃": "blade", "握柄": "handle", "握把": "handle",
    "拳套": "gauntlet", "圆盘": "disc", "饰物": "ornament",
    "弓臂": "limb", "上弓臂": "upper limb", "下弓臂": "lower limb", 
    "弓弦": "string", "弓身": "grip", 
    "飞翼": "harness", "翅膀": "wings", "引擎": "engine",
    "外壳": "carapace", "脑池": "cerebrum",
}

# ====== 主题配色 ======
THEME = {
    "bg": "#1a1a1a", "card_bg": "#2b2b2b", "text": "#ffffff", 
    "gold": "#d4af37", "gold_hover": "#b8952b"
}

ctk.set_appearance_mode("Dark") 
ctk.set_default_color_theme("dark-blue")

def resource_path(relative_path):
    try: base_path = sys._MEIPASS
    except: base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class WFPriceHelperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Warframe 开核桃助手 [V3.1 修复版]")
        self.geometry("700x650")
        self.configure(fg_color=THEME["bg"]) 

        self.wfinfo_prices = {} 
        self.load_config()
        self.setup_ui()
        
        self.log("正在初始化神经光元 (System)...")
        threading.Thread(target=self.init_resources, daemon=True).start()
        threading.Thread(target=self.update_prices_from_wfinfo, daemon=True).start()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f: self.config = json.load(f)
            except: self.config = DEFAULT_CONFIG
        else:
            self.config = DEFAULT_CONFIG
            self.save_config()

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(self.config, f, indent=4)
        except: pass

    # 🔴 核心功能：下载价格表
    def update_prices_from_wfinfo(self):
        self.log("📡 正在同步今日价格表...")
        try:
            url = "https://api.warframestat.us/wfinfo/prices/"
            resp = requests.get(url, timeout=15)
            
            if resp.status_code == 200:
                data = resp.json()
                new_prices = {}
                for item in data:
                    name = item.get("name", "").lower()
                    price = item.get("plat", 0)
                    new_prices[name] = price
                
                self.wfinfo_prices = new_prices
                self.log(f"✅ 价格同步完成! 收录 {len(new_prices)} 条数据")
                self.update_status(f"价格库已更新")
            else:
                self.log(f"❌ 价格同步失败: {resp.status_code}")
        except Exception as e:
            self.log(f"❌ 网络错误: {e}")

    def setup_ui(self):
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(20, 5))
        ctk.CTkLabel(self.header_frame, text="开核桃助手 V3.1", font=("微软雅黑", 24, "bold"), text_color=THEME["gold"]).pack(side="left")
        self.status_label = ctk.CTkLabel(self.header_frame, text="Initializing...", text_color="gray")
        self.status_label.pack(side="right", anchor="s")

        self.settings_frame = ctk.CTkFrame(self, fg_color=THEME["card_bg"], corner_radius=10, border_width=1, border_color=THEME["gold"])
        self.settings_frame.pack(fill="x", padx=20, pady=10)
        self.settings_frame.grid_columnconfigure(1, weight=1)
        self.settings_frame.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(self.settings_frame, text="触发热键:", font=("微软雅黑", 12, "bold")).grid(row=0, column=0, padx=15, pady=15, sticky="w")
        self.entry_hotkey = ctk.CTkEntry(self.settings_frame, placeholder_text="例如: alt+q")
        self.entry_hotkey.insert(0, self.config['hotkey'])
        self.entry_hotkey.grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkButton(self.settings_frame, text="更新", width=60, fg_color=THEME["gold"], hover_color=THEME["gold_hover"], text_color="black", command=self.update_hotkey).grid(row=0, column=2, padx=15)

        ctk.CTkLabel(self.settings_frame, text="截图范围:", font=("微软雅黑", 12, "bold")).grid(row=1, column=0, padx=15, pady=(0, 15), sticky="w")
        self.bbox_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.bbox_frame.grid(row=1, column=1, columnspan=2, sticky="w", padx=5, pady=(0, 15))
        self.bbox_entries = []
        for val in self.config['bbox']:
            entry = ctk.CTkEntry(self.bbox_frame, width=50, justify="center")
            entry.insert(0, str(val))
            entry.pack(side="left", padx=2)
            self.bbox_entries.append(entry)
        ctk.CTkButton(self.settings_frame, text="保存范围", width=80, fg_color="transparent", border_width=1, border_color=THEME["gold"], text_color=THEME["gold"], command=self.update_bbox).grid(row=1, column=2, padx=15, pady=(0, 15))

        btn_donate = ctk.CTkButton(self, text="☕ 觉得好用？请作者喝杯咖啡 ❤️", height=40, font=("微软雅黑", 14, "bold"), fg_color=THEME["gold"], text_color="black", hover_color=THEME["gold_hover"], corner_radius=8, command=self.show_donate_qr)
        btn_donate.pack(fill="x", padx=20, pady=(5, 10))

        ctk.CTkLabel(self, text="📊 运行日志", font=("微软雅黑", 12)).pack(anchor="w", padx=25, pady=(0, 0))
        self.log_text = ctk.CTkTextbox(self, font=("Consolas", 12), activate_scrollbars=True)
        self.log_text.pack(fill="both", expand=True, padx=20, pady=5)
        self.log_text.configure(state="disabled")
        ctk.CTkLabel(self, text="Designed for Tenno | Designed by github@RanAway22", font=("Arial", 10), text_color="#555").pack(pady=5)

    def show_donate_qr(self):
        try:
            top = ctk.CTkToplevel(self)
            top.title("感谢支持")
            top.geometry("300x380")
            top.attributes("-topmost", True) 
            img_path = resource_path(QR_IMAGE_PATH)
            if not os.path.exists(img_path): return
            pil_image = Image.open(img_path)
            my_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(250, 250))
            ctk.CTkLabel(top, image=my_image, text="").pack(pady=(20, 10))
            ctk.CTkLabel(top, text="欢迎扫码投喂！", font=("微软雅黑", 12)).pack()
        except: pass

    def log(self, msg): self.after(0, lambda: self._log_thread_safe(msg))
    def _log_thread_safe(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
    def update_status(self, msg): self.after(0, lambda: self.status_label.configure(text=msg))

    def update_hotkey(self):
        new_hk = self.entry_hotkey.get().strip()
        try: keyboard.remove_hotkey(self.config['hotkey'])
        except: pass
        try:
            keyboard.add_hotkey(new_hk, self.on_hotkey)
            self.config['hotkey'] = new_hk
            self.save_config()
            self.log(f"✅ 热键更新为: {new_hk}")
        except: self.log("❌ 热键格式错误")

    def update_bbox(self):
        try:
            vals = [int(e.get()) for e in self.bbox_entries]
            self.config['bbox'] = vals
            self.save_config()
            self.log(f"✅ 范围已保存: {vals}")
        except: self.log("❌ 坐标必须是整数")

    def init_resources(self):
        try:
            self.ocr = RapidOCR()
            self.log("✅ OCR 引擎就绪")
            if not os.path.exists(WFM_DICT_PATH):
                self.log(f"❌ 找不到字典文件: {WFM_DICT_PATH}")
                return
            with open(WFM_DICT_PATH, 'r', encoding='utf-8') as f: self.wfm_dict = json.load(f)
            self.log(f"📖 词典加载: {len(self.wfm_dict)} 条目")
            self.sorted_keys = sorted(self.wfm_dict.keys(), key=len, reverse=True)
            keyboard.add_hotkey(self.config['hotkey'], self.on_hotkey)
            self.log(f"🚀 等待指令 (按 {self.config['hotkey']})")
            self.update_status("System Ready")
        except Exception as e: self.log(f"❌ 初始化失败: {e}")

    def on_hotkey(self):
        self.update_status("Scanning...")
        threading.Thread(target=self.process_screenshot, daemon=True).start()

    # ====== 核心修复：离线极速查价 (修复0P问题) ======
    def fetch_price_offline(self, item_url_name):
        if not self.wfinfo_prices:
            return "价格表下载中..."
        
        # 1. 转换下划线为 API 格式 (空格分隔)
        # 例如 url_name: "ash_prime_systems" -> query: "ash prime systems"
        query_name = item_url_name.replace("_", " ").lower().strip()
        
        # 2. 直接查询
        if query_name in self.wfinfo_prices:
            price = self.wfinfo_prices[query_name]
            if price == 0: return "暂无交易数据" # 修复显示0P
            return f"均价: {price} P"
            
        return "暂无数据"

    def show_overlay(self, title, content, index=0):
        def _show():
            top = tk.Toplevel(self)
            top.overrideredirect(True)
            top.attributes('-topmost', True)
            top.attributes('-alpha', 0.90) 
            top.config(bg=THEME["bg"]) 

            win_w, win_h = 340, 90 
            screen_h = self.winfo_screenheight()
            start_y = (screen_h // 2) - 150 + (index * 100)
            
            hidden_x = -win_w - 20 
            target_x = 30 
            top.geometry(f"{win_w}x{win_h}+{hidden_x}+{start_y}")

            main_frame = tk.Frame(top, bg=THEME["card_bg"])
            main_frame.pack(fill="both", expand=True, padx=2, pady=2)

            strip = tk.Frame(main_frame, bg=THEME["gold"], width=8)
            strip.pack(side="left", fill="y")

            content_frame = tk.Frame(main_frame, bg=THEME["card_bg"], padx=15)
            content_frame.pack(side="left", fill="both", expand=True)
            
            tk.Label(content_frame, text=title, fg=THEME["gold"], bg=THEME["card_bg"], 
                     font=("微软雅黑", 13, "bold"), anchor="w").pack(fill="x", pady=(15, 3))
            
            tk.Label(content_frame, text=content, fg="#99ff99", bg=THEME["card_bg"], 
                     font=("Arial", 12), anchor="w").pack(fill="x")

            anim_data = {"curr_x": hidden_x, "state": "in", "velocity": 40}

            def animate():
                try:
                    if not top.winfo_exists(): return
                except: return

                if anim_data["state"] == "in":
                    dist = target_x - anim_data["curr_x"]
                    if dist > 1:
                        move = max(dist * 0.15, 2) 
                        anim_data["curr_x"] += move
                        top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{start_y}")
                        top.after(10, animate)
                    else:
                        anim_data["curr_x"] = target_x
                        top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{start_y}")
                        anim_data["state"] = "wait"
                        top.after(8000, animate) 

                elif anim_data["state"] == "wait":
                    anim_data["state"] = "out"
                    animate()

                elif anim_data["state"] == "out":
                    dist = anim_data["curr_x"] - hidden_x
                    if dist > 1:
                        move = max(dist * 0.15, 2)
                        anim_data["curr_x"] -= move
                        top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{start_y}")
                        top.after(10, animate)
                    else:
                        top.destroy()

            top.after(10, animate)
        self.after(0, _show)

    def process_screenshot(self):
        bbox = tuple(self.config['bbox'])
        self.log(f"\n📸 正在扫描区域: {bbox}")
        try:
            img = ImageGrab.grab(bbox)
            result, _ = self.ocr(img)
            
            if not result:
                self.log("⚠️ 画面无文字")
                return

            found_count = 0
            seen_items = set()
            overlay_items = []

            for line in result:
                clean_ocr = line[1].replace(" ", "").lower()
                if len(clean_ocr) < 2: continue

                for dict_key in self.sorted_keys:
                    if dict_key in clean_ocr:
                        # 1. 直接获取字典里的完整 URL (如 'ash_prime_systems')
                        url_name = self.wfm_dict[dict_key]['url_name']
                        real_name = self.wfm_dict[dict_key]['real_cn_name']
                        
                        # 2. 注意：这里不再尝试拼接 PART_MAP 的后缀
                        # 只有当你的字典很不完整（只有 "Ash Prime" 这种本体名）的时候才需要拼接
                        # 现在的字典已经是全量部件了，直接查即可
                        
                        if real_name in seen_items: break

                        self.log(f"🔎 识别: {real_name}")
                        
                        # 3. 极速离线查价 (直接查 url_name)
                        price = self.fetch_price_offline(url_name)
                        self.log(f"   -> {price}")
                        
                        overlay_items.append((real_name, price))
                        seen_items.add(real_name)
                        found_count += 1
                        break
            
            for idx, (name, price) in enumerate(overlay_items):
                self.show_overlay(name, price, index=idx)
            
            msg = f"完成 (找到 {found_count} 个)" if found_count else "未匹配到物品"
            self.update_status(msg)
            self.log(msg)

        except Exception as e:
            self.log(f"❌ Error: {e}")

if __name__ == "__main__":
    app = WFPriceHelperApp()
    app.protocol("WM_DELETE_WINDOW", lambda: (keyboard.unhook_all(), app.destroy()))
    app.mainloop()