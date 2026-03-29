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
    "bbox": [500, 400, 1400, 460]
}
CONFIG_FILE = "config.json"
WFM_DICT_PATH = "wfm_dictionary.json"
QR_IMAGE_PATH = "qr.png" 

# ====== 🎨 Warframe 主题配色 ======
THEME = {
    "bg": "#1a1a1a",           
    "card_bg": "#2b2b2b",      
    "text": "#ffffff",         
    "gold": "#d4af37",         
    "gold_hover": "#b8952b",   
}

ctk.set_appearance_mode("Dark") 
ctk.set_default_color_theme("dark-blue")

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class WFPriceHelperApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Warframe 交易助手 [Pro]")
        self.geometry("700x650")
        self.configure(fg_color=THEME["bg"]) 

        self.price_cache = {}
        self.load_config()
        self.init_dictionary_data()
        self.setup_ui()

        self.log("正在初始化神经光元 (System)...")
        threading.Thread(target=self.init_ocr, daemon=True).start()

    def init_dictionary_data(self):
        self.part_dict = {
    # === 通用/核心 ===
    "蓝图": ["blueprint"],
    "总图": ["blueprint"],
    
    # === 战甲 ===
    "机体": ["chassis"],
    "系统": ["systems"],
    "头部神经光元": ["neuroptics"],
    "视光器": ["neuroptics"], # 国服旧翻译
    
    # === 枪械 (步枪/散弹/手枪) ===
    "枪机": ["receiver"],
    "枪管": ["barrel"],
    "枪托": ["stock"],
    "连接器": ["link"],
    
    # === 近战 (刀/剑/长柄) ===
    "刀刃": ["blade"],
    "握柄": ["handle", "grip"], # 智能重试：先查 handle，不行查 grip
    "握把": ["handle", "grip"],
    "拳套": ["gauntlet"],
    "圆盘": ["disc"],
    "饰物": ["ornament"],
    
    # === 弓箭 (最复杂的重灾区) ===
    "弓臂": ["limb", "lower_limb", "upper_limb"], # 先试 limb，不行就试上下
    "上弓臂": ["upper_limb"],
    "下弓臂": ["lower_limb"],
    "弓弦": ["string"],
    "弓身": ["limb", "riser"], # 偶尔有叫 riser 的
    
    # === Archwing/宠物 ===
    "飞翼": ["harness"],
    "翅膀": ["wings"],
    "引擎": ["engine"],
    "外壳": ["carapace"],
    "脑池": ["cerebrum"],
}

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except:
                self.config = DEFAULT_CONFIG
        else:
            self.config = DEFAULT_CONFIG
            self.save_config()

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            self.log(f"⚠️ 保存失败: {e}")

    def setup_ui(self):
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(20, 5))
        
        ctk.CTkLabel(self.header_frame, text="开核桃助手V1.0", 
                     font=("微软雅黑", 24, "bold"), text_color=THEME["gold"]).pack(side="left")
        
        self.status_label = ctk.CTkLabel(self.header_frame, text="System Ready", text_color="gray")
        self.status_label.pack(side="right", anchor="s")

        self.settings_frame = ctk.CTkFrame(self, fg_color=THEME["card_bg"], corner_radius=10, 
                                         border_width=1, border_color=THEME["gold"])
        self.settings_frame.pack(fill="x", padx=20, pady=10)

        self.settings_frame.grid_columnconfigure(1, weight=1)
        self.settings_frame.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(self.settings_frame, text="触发热键:", font=("微软雅黑", 12, "bold")).grid(row=0, column=0, padx=15, pady=15, sticky="w")
        self.entry_hotkey = ctk.CTkEntry(self.settings_frame, placeholder_text="例如: alt+q")
        self.entry_hotkey.insert(0, self.config['hotkey'])
        self.entry_hotkey.grid(row=0, column=1, padx=5, sticky="ew")
        
        ctk.CTkButton(self.settings_frame, text="更新", width=60, fg_color=THEME["gold"], hover_color=THEME["gold_hover"], text_color="black",
                      command=self.update_hotkey).grid(row=0, column=2, padx=15)

        ctk.CTkLabel(self.settings_frame, text="截图范围 (L,T,R,B):", font=("微软雅黑", 12, "bold")).grid(row=1, column=0, padx=15, pady=(0, 15), sticky="w")
        
        self.bbox_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.bbox_frame.grid(row=1, column=1, columnspan=2, sticky="w", padx=5, pady=(0, 15))
        
        self.bbox_entries = []
        for val in self.config['bbox']:
            entry = ctk.CTkEntry(self.bbox_frame, width=50, justify="center")
            entry.insert(0, str(val))
            entry.pack(side="left", padx=2)
            self.bbox_entries.append(entry)
            
        ctk.CTkButton(self.settings_frame, text="保存范围", width=80, fg_color="transparent", border_width=1, border_color=THEME["gold"], text_color=THEME["gold"],
                      command=self.update_bbox).grid(row=1, column=2, padx=15, pady=(0, 15))

        btn_donate = ctk.CTkButton(self, text="☕ 觉得好用？请作者喝杯咖啡 ❤️", 
                                 height=40,
                                 font=("微软雅黑", 14, "bold"),
                                 fg_color=THEME["gold"],
                                 text_color="black",
                                 hover_color=THEME["gold_hover"],
                                 corner_radius=8,
                                 command=self.show_donate_qr)
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
            top.resizable(False, False)
            top.attributes("-topmost", True) 
            
            img_path = resource_path(QR_IMAGE_PATH)
            if not os.path.exists(img_path):
                ctk.CTkLabel(top, text="找不到 qr.png 图片", text_color="red").pack(expand=True)
                return

            pil_image = Image.open(img_path)
            my_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(250, 250))
            
            ctk.CTkLabel(top, image=my_image, text="").pack(pady=(20, 10))
            ctk.CTkLabel(top, text="欢迎扫码投喂！", font=("微软雅黑", 12)).pack()
            
        except Exception as e:
            self.log(f"无法加载图片: {e}")

    def log(self, msg):
        self.after(0, lambda: self._log_thread_safe(msg))

    def _log_thread_safe(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def update_status(self, msg):
        self.after(0, lambda: self.status_label.configure(text=msg))

    def update_hotkey(self):
        new_hk = self.entry_hotkey.get().strip()
        try:
            keyboard.remove_hotkey(self.config['hotkey'])
        except: pass
        try:
            keyboard.add_hotkey(new_hk, self.on_hotkey)
            self.config['hotkey'] = new_hk
            self.save_config()
            self.log(f"✅ 热键更新为: {new_hk}")
        except:
            self.log("❌ 热键格式错误")

    def update_bbox(self):
        try:
            vals = [int(e.get()) for e in self.bbox_entries]
            self.config['bbox'] = vals
            self.save_config()
            self.log(f"✅ 范围已保存: {vals}")
        except:
            self.log("❌ 坐标必须是整数")

    def init_ocr(self):
        try:
            self.ocr = RapidOCR()
            self.log("✅ OCR 引擎就绪")
            
            with open(resource_path(WFM_DICT_PATH), 'r', encoding='utf-8') as f:
                self.wfm_dict = json.load(f)
            self.log(f"📖 字典已加载: {len(self.wfm_dict)} 条目")
            self.sorted_keys = sorted(self.wfm_dict.keys(), key=len, reverse=True)
            
            keyboard.add_hotkey(self.config['hotkey'], self.on_hotkey)
            self.log(f"🚀 等待指令 (按 {self.config['hotkey']})")
            self.update_status("System Ready")
        except Exception as e:
            self.log(f"❌ 初始化失败: {e}")

    def on_hotkey(self):
        self.update_status("Scanning...")
        threading.Thread(target=self.process_screenshot, daemon=True).start()

    def fetch_price(self, url_name):
        if url_name in self.price_cache: return self.price_cache[url_name]
        url = f"https://api.warframe.market/v1/items/{url_name}/statistics"
        try:
            headers = {"Language": "zh-hans", "Platform": "pc"}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 404 and "_handle" in url:
                resp = requests.get(url.replace("_handle", "_grip"), headers=headers)
            
            if resp.status_code == 200:
                stats = resp.json()['payload']['statistics_closed']['48hours']
                if not stats: return "暂无数据"
                price = stats[-1].get('avg_price', '?')
                res = f"均价: {price} P"
                self.price_cache[url_name] = res
                return res
            return "404 Not Found"
        except: return "Network Error"

    # ==========================================
    # 🚀 核心修改：NVIDIA 风格滑入滑出动画
    # ==========================================
    def show_overlay(self, title, content, index=0):
        def _show():
            # 1. 窗口初始化（在屏幕外）
            top = tk.Toplevel(self)
            top.overrideredirect(True)      # 无边框
            top.attributes('-topmost', True)# 置顶
            top.attributes('-alpha', 0.92)  # 稍微透明
            top.config(bg=THEME["bg"]) 

            # 窗口尺寸
            win_w, win_h = 280, 75 
            
            # 计算 Y 轴位置 (屏幕垂直居中，多物品时向下排列)
            screen_h = self.winfo_screenheight()
            start_y = (screen_h // 2) - 100 + (index * 85)
            
            # 初始 X 轴位置 (完全隐藏在屏幕左侧外)
            hidden_x = -win_w - 10 
            target_x = 20  # 最终停留在屏幕左侧 20px 处
            
            # 初始 geometry
            top.geometry(f"{win_w}x{win_h}+{hidden_x}+{start_y}")

            # 2. 内容布局 (NVIDIA 风格)
            # 主容器
            main_frame = tk.Frame(top, bg=THEME["card_bg"])
            main_frame.pack(fill="both", expand=True)

            # 左侧金色竖条 (装饰)
            strip = tk.Frame(main_frame, bg=THEME["gold"], width=6)
            strip.pack(side="left", fill="y")

            # 内容容器
            content_frame = tk.Frame(main_frame, bg=THEME["card_bg"], padx=12)
            content_frame.pack(side="left", fill="both", expand=True)
            
            # 居中对齐内容
            tk.Label(content_frame, text=title, fg=THEME["gold"], bg=THEME["card_bg"], 
                     font=("微软雅黑", 12, "bold"), anchor="w").pack(fill="x", pady=(12, 0))
            
            tk.Label(content_frame, text=content, fg="white", bg=THEME["card_bg"], 
                     font=("Arial", 10), anchor="w").pack(fill="x", pady=(2, 0))

            # 3. 动画逻辑变量
            anim_data = {
                "curr_x": hidden_x,
                "state": "in", # in:进场, wait:停留, out:退场
                "velocity": 25 # 移动速度 (像素/帧)
            }

            def animate():
                try:
                    if not top.winfo_exists(): return
                except: return

                if anim_data["state"] == "in":
                    # === 进场阶段 ===
                    if anim_data["curr_x"] < target_x:
                        anim_data["curr_x"] += anim_data["velocity"]
                        # 减速缓冲效果 (快到时减速)
                        if target_x - anim_data["curr_x"] < 50: 
                             anim_data["curr_x"] -= (anim_data["velocity"] // 2) 
                             
                        top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{start_y}")
                        top.after(16, animate) # 约 60 FPS
                    else:
                        anim_data["state"] = "wait"
                        top.after(5000, animate) # 停留 5 秒后继续动画

                elif anim_data["state"] == "wait":
                    # === 停留结束，准备退场 ===
                    anim_data["state"] = "out"
                    animate()

                elif anim_data["state"] == "out":
                    # === 退场阶段 ===
                    if anim_data["curr_x"] > hidden_x:
                        anim_data["curr_x"] -= anim_data["velocity"]
                        top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{start_y}")
                        top.after(16, animate)
                    else:
                        top.destroy() # 彻底离开屏幕后销毁

            # 启动动画
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
                self.update_status("No Text Detected")
                return

            found_count = 0
            seen_items = set()

            for line in result:
                clean_ocr = line[1].replace(" ", "").lower()
                if len(clean_ocr) < 2: continue

                for dict_key in self.sorted_keys:
                    if dict_key in clean_ocr:
                        leftover = clean_ocr.replace(dict_key, "")
                        final_url = self.wfm_dict[dict_key]['url_name']
                        final_name = self.wfm_dict[dict_key]['real_cn_name']

                        if leftover:
                            for cn, en in self.part_dict.items():
                                if cn in leftover:
                                    final_url += f"_{en}"
                                    final_name += f" {cn}"
                                    break
                        
                        if final_name in seen_items: break

                        self.log(f"🔎 识别: {final_name}")
                        price = self.fetch_price(final_url)
                        self.log(f"   -> {price}")
                        
                        self.show_overlay(final_name, price, index=found_count)
                        
                        seen_items.add(final_name)
                        found_count += 1
                        break
            
            msg = f"完成 (找到 {found_count} 个)" if found_count else "未匹配到物品"
            self.update_status(msg)
            self.log(msg)

        except Exception as e:
            self.log(f"❌ Error: {e}")

if __name__ == "__main__":
    app = WFPriceHelperApp()
    app.protocol("WM_DELETE_WINDOW", lambda: (keyboard.unhook_all(), app.destroy()))
    app.mainloop()