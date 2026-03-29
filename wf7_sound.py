import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageGrab, ImageTk 
import keyboard
from rapidocr_onnxruntime import RapidOCR
import requests
import json
import threading
import time
import os
import sys
import urllib.parse
import pygame 

# ====== 配置区域 ======
DEFAULT_CONFIG = {
    "hotkey": "alt+q",
    "bbox": [0,0,1920,1080],
    "proxy": "",
    "sound_file": "default", 
    "sound_volume": 0.5 
}
CONFIG_FILE = "config.json"
WFM_DICT_PATH = "wfm_dictionary.json"
QR_IMAGE_PATH = "qr.png" 
SOUND_DIR = "sound"

THEME = {
    "bg": "#1a1a1a", "card_bg": "#2b2b2b", "text": "#ffffff", 
    "gold": "#d4af37", "gold_hover": "#b8952b",
    "fast_text": "#00ff7f", "live_text": "#00bfff",
    "info_btn": "#4a90e2", "info_hover": "#357abd",
    "progress_bg": "#404040", "progress_fill": "#00ff7f", "progress_err": "#ff4444"
}

PART_MAP = {
    "蓝图": "blueprint", "总图": "blueprint",
    "机体": "chassis", "系统": "systems", "头部神经光元": "neuroptics", "视光器": "neuroptics",
    "枪机": "receiver", "枪管": "barrel", "枪托": "stock", "连接器": "link",
    "刀刃": "blade", "握柄": "handle", "握把": "handle",
    "拳套": "gauntlet", "圆盘": "disc", "饰物": "ornament",
    "弓臂": "limb", "上弓臂": "upper_limb", "下弓臂": "lower_limb", 
    "弓弦": "string", "弓身": "grip", 
    "飞翼": "harness", "翅膀": "wings", "引擎": "engine",
    "外壳": "carapace", "脑池": "cerebrum",
}

ctk.set_appearance_mode("Dark") 
ctk.set_default_color_theme("dark-blue")

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_sound_dir():
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    sound_path = os.path.join(base_dir, SOUND_DIR)
    if not os.path.exists(sound_path):
        try:
            os.makedirs(sound_path)
        except:
            pass
    return sound_path

class WFPriceHelperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Warframe 开核桃助手 [V4.7 稳定版]")
        self.geometry("700x780") 
        self.configure(fg_color=THEME["bg"]) 

        self.wfinfo_prices = {} 
        self.is_ready = False
        self.init_lock = threading.Lock()
        
        # 1. 加载配置
        self.load_config()
        
        # 2. 初始化音频
        pygame.mixer.init()
        self.current_sound = None
        self.sound_files = []
        self.scan_sound_files()
        self.load_custom_sound() 
        
        # 3. 构建界面
        self.setup_ui()
        
        self.log("正在初始化神经光元 (System)...")
        threading.Thread(target=self.init_resources, daemon=True).start()
        self.start_sync_task()

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
        
        defaults = {"proxy":"", "sound_file":"default", "sound_volume":0.5}
        for k, v in defaults.items():
            if k not in self.config:
                self.config[k] = v

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
        except:
            pass

    # ====== 音频功能 ======
    
    def scan_sound_files(self):
        self.sound_files = ["default"]
        sound_dir = get_sound_dir()
        if os.path.exists(sound_dir):
            for f in os.listdir(sound_dir):
                if f.lower().endswith(('.mp3', '.wav', '.ogg')):
                    self.sound_files.append(f)

    def load_custom_sound(self):
        filename = self.config.get("sound_file", "default")
        volume = self.config.get("sound_volume", 0.5)
        
        if filename == "default":
            self.current_sound = None
            return

        full_path = os.path.join(get_sound_dir(), filename)
        
        if os.path.exists(full_path):
            try:
                self.current_sound = pygame.mixer.Sound(full_path)
                self.current_sound.set_volume(volume)
            except Exception as e:
                self.log(f"音效加载失败: {e}")
                self.current_sound = None 
        else:
            self.current_sound = None

    def play_trigger_sound(self):
        if self.current_sound:
            self.current_sound.play()
        else:
            try:
                import winsound
                winsound.Beep(1000, 100)
            except:
                pass

    # ====== 界面回调函数 ======

    def update_hotkey(self):
        new_hk = self.entry_hotkey.get().strip()
        try:
            keyboard.remove_hotkey(self.config['hotkey'])
        except:
            pass
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

    def update_proxy(self):
        proxy = self.entry_proxy.get().strip()
        self.config['proxy'] = proxy
        self.save_config()
        self.log(f"✅ 代理配置已保存")
        self.start_sync_task()

    def update_volume(self, value):
        self.config["sound_volume"] = float(value)
        if self.current_sound:
            self.current_sound.set_volume(float(value))
        self.save_config()

    def change_sound(self, choice):
        self.config["sound_file"] = choice
        self.save_config()
        self.load_custom_sound()
        self.log(f"🎵 音效已切换: {choice}")
        self.play_trigger_sound()

    def refresh_sounds(self):
        self.scan_sound_files()
        self.combo_sound.configure(values=self.sound_files)
        current = self.config.get("sound_file", "default")
        if current not in self.sound_files:
            current = "default"
            self.config["sound_file"] = "default"
            self.save_config()
        self.combo_sound.set(current)
        self.log(f"🔄 音效库已刷新")

    def select_sound_file(self):
        self.log("💡 请将音频文件放入软件目录下的 sound 文件夹，然后点击刷新按钮")
        try:
            os.startfile(get_sound_dir())
        except:
            pass

    def update_wfm_dict(self):
        def _update_task():
            self.log("📡 正在连接 Warframe Market 更新字典...")
            self.update_status("更新字典中...")
            try:
                target_url = "https://api.warframe.market/v1/items"
                proxy_url = f"https://api.allorigins.win/raw?url={urllib.parse.quote(target_url)}"
                headers = {"Language": "zh-hans", "Platform": "pc"}
                resp = requests.get(proxy_url, headers=headers, timeout=60)
                
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get('payload', {}).get('items', [])
                    final_dict = {}
                    count = 0
                    for item in items:
                        item_name = item.get('item_name', '')
                        url_name = item.get('url_name', '')
                        if "Prime" in item_name and "Set" not in item_name and "套装" not in item_name:
                            if any(x in url_name for x in ['_blueprint', '_chassis', '_systems', '_neuroptics', '_harness', '_wings']):
                                continue
                            key = item_name.replace(" ", "").lower()
                            final_dict[key] = {"url_name": url_name, "real_cn_name": item_name}
                            count += 1
                    
                    with open(WFM_DICT_PATH, 'w', encoding='utf-8') as f:
                        json.dump(final_dict, f, ensure_ascii=False, indent=4)
                    
                    with self.init_lock:
                        self.wfm_dict = final_dict
                        self.sorted_keys = sorted(self.wfm_dict.keys(), key=len, reverse=True)
                    
                    self.log(f"✅ 字典更新成功！收录 {count} 个 Prime 本体")
                    self.update_status("字典已更新")
                    messagebox.showinfo("成功", f"字典已更新至最新版\n共收录 {count} 个物品")
                else:
                    self.log(f"❌ 更新失败: HTTP {resp.status_code}")
            except Exception as e:
                self.log(f"❌ 更新错误: {e}")
                self.update_status("更新失败")

        if messagebox.askyesno("更新字典", "确定要从 Warframe Market 下载最新字典吗？\n这可能需要几十秒。"):
            threading.Thread(target=_update_task, daemon=True).start()

    def show_tutorial(self):
        try:
            top = ctk.CTkToplevel(self)
            top.title("使用说明")
            top.geometry("500x550")
            top.attributes("-topmost", True) 
            text_area = ctk.CTkTextbox(top, font=("微软雅黑", 13), activate_scrollbars=True)
            text_area.pack(fill="both", expand=True, padx=15, pady=15)
            
            tutorial_content = """
【自定义音效】
1. 在本软件同级目录下，会自动生成一个 "sound" 文件夹。
2. 将你的 MP3 / WAV / OGG 音效文件丢进去。
3. 点击界面上的 "↻" 刷新按钮。
4. 在下拉框中选择你的音效。

【快速入门】
1. 游戏设置为 "无边框窗口" 或 "窗口模式"。
2. 在遗物选择界面，确保物品名称清晰可见。
3. 按下快捷键 (默认 Alt+Q)。
4. 等待 1-2 秒，屏幕左侧会出现价格弹窗。

【字典更新】
点击底部的 [更新字典] 按钮，可自动获取最新的物品列表（支持新甲）。
            """
            text_area.insert("0.0", tutorial_content)
            text_area.configure(state="disabled") 
        except: pass

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

    def log(self, msg):
        self.after(0, lambda: self._log_thread_safe(msg))

    def _log_thread_safe(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def update_status(self, msg):
        self.after(0, lambda: self.status_label.configure(text=msg))

    # ====== 网络逻辑 ======
    def get_clean_session(self):
        s = requests.Session()
        proxy_url = self.config.get("proxy", "").strip()
        if proxy_url:
            if not proxy_url.startswith("http"): proxy_url = "http://" + proxy_url
            s.proxies = {"http": proxy_url, "https": proxy_url}
            s.trust_env = True
        else:
            s.trust_env = False 
            s.proxies = {}
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        return s

    def start_sync_task(self):
        self.progress_bar.set(0)
        self.progress_bar.configure(progress_color=THEME["progress_fill"])
        self.progress_bar.pack(fill="x", padx=15, pady=(15, 0), before=self.header_frame)
        self.progress_label = ctk.CTkLabel(self, text="正在准备同步...", font=("Arial", 11), text_color="gray")
        self.progress_label.pack(fill="x", padx=15, pady=(2, 5), before=self.header_frame)
        
        self.sync_running = True
        self.target_progress = 0.0
        self.current_progress = 0.0
        
        threading.Thread(target=self.smooth_animation_loop, daemon=True).start()
        threading.Thread(target=self.download_price_table_smart, daemon=True).start()

    def update_sync_text(self, text):
        try: self.after(0, lambda: self.progress_label.configure(text=text))
        except: pass

    def smooth_animation_loop(self):
        self.target_progress = 0.2
        self.update_sync_text("正在连接云端服务器...")
        
        while self.sync_running:
            if self.target_progress < 0.85:
                self.target_progress += 0.002
            
            if 0.3 < self.current_progress < 0.6:
                self.update_sync_text("正在下载 WFInfo 价格表...")
            elif self.current_progress > 0.6:
                self.update_sync_text("正在解析数据...")

            diff = self.target_progress - self.current_progress
            if diff > 0.001:
                self.current_progress += diff * 0.1
                self.update_progress(self.current_progress)
            
            time.sleep(0.03)

    def update_progress(self, value):
        try: self.after(0, lambda: self.progress_bar.set(value))
        except: pass

    def finish_progress(self, success=True):
        self.sync_running = False
        
        def _finish_anim():
            current = self.current_progress
            while current < 1.0:
                current += (1.05 - current) * 0.2
                self.update_progress(min(1.0, current))
                time.sleep(0.03)
            
            self.update_progress(1.0)
            
            if success:
                self.update_sync_text("✅ 同步完成")
                self.update_status("极速模式")
                time.sleep(1.2)
                self.after(0, lambda: self.progress_bar.pack_forget())
                self.after(0, lambda: self.progress_label.pack_forget())
            else:
                self.after(0, lambda: self.progress_bar.configure(progress_color=THEME["progress_err"]))
                self.update_sync_text("❌ 同步失败，切换至实时模式")
                self.update_status("实时模式")
                time.sleep(3.0)
                self.after(0, lambda: self.progress_bar.pack_forget())
                self.after(0, lambda: self.progress_label.pack_forget())

        threading.Thread(target=_finish_anim, daemon=True).start()

    def download_price_table_smart(self):
        target_url = "https://api.warframestat.us/wfinfo/prices/"
        encoded_url = urllib.parse.quote(target_url)
        
        sources = [
            (target_url, "官方直连"),
            (f"https://api.allorigins.win/raw?url={encoded_url}", "云线路 A"),
            (f"https://api.codetabs.com/v1/proxy?quest={encoded_url}", "云线路 B"),
            (f"https://thingproxy.freeboard.io/fetch/{target_url}", "云线路 C")
        ]

        self.log("📡 开始同步价格库...")
        session = self.get_clean_session()
        success = False
        
        for i, (url, name) in enumerate(sources):
            try:
                self.log(f"   🔄 正在尝试线路 {i+1}: {name}")
                resp = session.get(url, timeout=15)
                
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if "contents" in data and isinstance(data["contents"], str):
                             data = json.loads(data["contents"])

                        new_prices = {}
                        count = 0
                        data_list = data if isinstance(data, list) else data.get("prices", [])
                        
                        for item in data_list:
                            if not isinstance(item, dict): continue
                            name_val = item.get("name") or item.get("item_name")
                            if not name_val: continue
                            
                            clean_name = name_val.lower().replace(" ", "").replace("_", "").strip()
                            price_val = item.get("custom_avg") or item.get("plat") or item.get("platinum")
                            
                            if price_val:
                                try:
                                    if float(price_val) > 0: 
                                        new_prices[clean_name] = int(float(price_val))
                                        count += 1
                                except: pass
                        
                        if count > 0:
                            self.wfinfo_prices = new_prices
                            self.log(f"✅ 成功! 线路: {name}")
                            self.log(f"   已缓存 {count} 个物品")
                            success = True
                            self.finish_progress(True)
                            break 
                    except Exception:
                        self.log(f"   ❌ 解析错误")
                        continue
                else:
                    self.log(f"   ❌ 失败: HTTP {resp.status_code}")
            except Exception:
                self.log(f"   ❌ 连接异常")

        if not success:
            self.log("⚠️ 所有线路失败，切换 [实时模式]")
            self.finish_progress(False)

    # ====== 界面构建 ======
    def setup_ui(self):
        self.progress_bar = ctk.CTkProgressBar(self, height=15, corner_radius=5, fg_color=THEME["progress_bg"], progress_color=THEME["progress_fill"], border_width=0)
        self.progress_bar.set(0)

        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(5, 0))
        ctk.CTkLabel(self.header_frame, text="开核桃助手 V4.6", font=("微软雅黑", 24, "bold"), text_color=THEME["gold"]).pack(side="left")
        self.status_label = ctk.CTkLabel(self.header_frame, text="Initializing...", text_color="gray")
        self.status_label.pack(side="right", anchor="s")

        btn_tutorial = ctk.CTkButton(self, text="📘 新手必读：使用教程", height=36, fg_color=THEME["info_btn"], hover_color=THEME["info_hover"], font=("微软雅黑", 13, "bold"), command=self.show_tutorial)
        btn_tutorial.pack(fill="x", padx=20, pady=(15, 10))

        self.settings_frame = ctk.CTkFrame(self, fg_color=THEME["card_bg"], corner_radius=10, border_width=1, border_color=THEME["gold"])
        self.settings_frame.pack(fill="x", padx=20, pady=5)
        self.settings_frame.grid_columnconfigure(1, weight=1)
        self.settings_frame.grid_columnconfigure(3, weight=1)

        # 1. 快捷键
        ctk.CTkLabel(self.settings_frame, text="触发热键:", font=("微软雅黑", 12)).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.entry_hotkey = ctk.CTkEntry(self.settings_frame)
        self.entry_hotkey.insert(0, self.config['hotkey'])
        self.entry_hotkey.grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkButton(self.settings_frame, text="更新", width=60, fg_color=THEME["gold"], text_color="black", hover_color=THEME["gold_hover"], command=self.update_hotkey).grid(row=0, column=2, padx=10)

        # 2. 截图范围
        ctk.CTkLabel(self.settings_frame, text="截图范围:", font=("微软雅黑", 12)).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.bbox_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.bbox_frame.grid(row=1, column=1, sticky="w", padx=5)
        self.bbox_entries = []
        for val in self.config['bbox']:
            e = ctk.CTkEntry(self.bbox_frame, width=50, justify="center")
            e.insert(0, str(val))
            e.pack(side="left", padx=2)
            self.bbox_entries.append(e)
        ctk.CTkButton(self.settings_frame, text="保存", width=60, fg_color=THEME["gold"], text_color="black", hover_color=THEME["gold_hover"], command=self.update_bbox).grid(row=1, column=2, padx=10)

        # 3. 代理设置
        ctk.CTkLabel(self.settings_frame, text="本地代理:", font=("微软雅黑", 12)).grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.entry_proxy = ctk.CTkEntry(self.settings_frame, placeholder_text="留空以使用云加速")
        self.entry_proxy.insert(0, self.config.get('proxy', ''))
        self.entry_proxy.grid(row=2, column=1, padx=5, sticky="ew")
        ctk.CTkButton(self.settings_frame, text="保存", width=60, fg_color=THEME["gold"], text_color="black", hover_color=THEME["gold_hover"], command=self.update_proxy).grid(row=2, column=2, padx=10)

        # 4. 音效选择
        ctk.CTkLabel(self.settings_frame, text="提示音效:", font=("微软雅黑", 12)).grid(row=3, column=0, padx=10, pady=5, sticky="w")
        sound_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        sound_frame.grid(row=3, column=1, padx=5, sticky="ew")
        sound_frame.grid_columnconfigure(0, weight=1)
        self.combo_sound = ctk.CTkComboBox(sound_frame, values=self.sound_files, command=self.change_sound)
        self.combo_sound.set(self.config.get("sound_file", "default"))
        self.combo_sound.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(sound_frame, text="↻", width=30, fg_color="transparent", border_width=1, border_color="gray", command=self.refresh_sounds).grid(row=0, column=1, padx=(5,0))
        ctk.CTkButton(self.settings_frame, text="打开文件夹", width=60, fg_color=THEME["gold"], text_color="black", hover_color=THEME["gold_hover"], command=lambda: os.startfile(get_sound_dir())).grid(row=3, column=2, padx=10)

        # 5. 音量调节
        ctk.CTkLabel(self.settings_frame, text="音量调节:", font=("微软雅黑", 12)).grid(row=4, column=0, padx=10, pady=5, sticky="w")
        vol_f = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        vol_f.grid(row=4, column=1, columnspan=2, sticky="ew", padx=5)
        vol_f.grid_columnconfigure(0, weight=1)
        self.slider_volume = ctk.CTkSlider(vol_f, from_=0, to=1, number_of_steps=100, command=self.update_volume)
        self.slider_volume.set(self.config.get("sound_volume", 0.5))
        self.slider_volume.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkButton(vol_f, text="🔊 试听", width=60, fg_color=THEME["gold"], text_color="black", hover_color=THEME["gold_hover"], command=self.play_trigger_sound).grid(row=0, column=1)

        # 6. 字典更新
        ctk.CTkLabel(self.settings_frame, text="数据字典:", font=("微软雅黑", 12)).grid(row=5, column=0, padx=10, pady=5, sticky="w")
        ctk.CTkLabel(self.settings_frame, text="如果查不到新物品，请点击更新", font=("Arial", 10), text_color="gray").grid(row=5, column=1, sticky="w", padx=5)
        ctk.CTkButton(self.settings_frame, text="更新字典", width=60, fg_color=THEME["info_btn"], hover_color=THEME["info_hover"], command=self.update_wfm_dict).grid(row=5, column=2, padx=10)

        btn_donate = ctk.CTkButton(self, text="☕ 觉得好用？请作者喝杯咖啡 ❤️", height=40, font=("微软雅黑", 14, "bold"), fg_color=THEME["gold"], text_color="black", hover_color=THEME["gold_hover"], corner_radius=8, command=self.show_donate_qr)
        btn_donate.pack(fill="x", padx=20, pady=(15, 10))

        ctk.CTkLabel(self, text="📊 运行日志", font=("微软雅黑", 12)).pack(anchor="w", padx=25, pady=(0, 0))
        self.log_text = ctk.CTkTextbox(self, font=("Consolas", 12), activate_scrollbars=True)
        self.log_text.pack(fill="both", expand=True, padx=20, pady=5)
        self.log_text.configure(state="disabled")
        ctk.CTkLabel(self, text="Designed for Tenno", font=("Arial", 10), text_color="#555").pack(pady=5)

    def init_resources(self):
        try:
            self.ocr = RapidOCR()
            self.log("✅ OCR 引擎就绪")
            if not os.path.exists(WFM_DICT_PATH):
                self.log(f"❌ 找不到字典文件: {WFM_DICT_PATH}")
                return
            with open(WFM_DICT_PATH, 'r', encoding='utf-8') as f:
                self.wfm_dict = json.load(f)
            self.log(f"📖 字典加载: {len(self.wfm_dict)} 条目")
            self.sorted_keys = sorted(self.wfm_dict.keys(), key=len, reverse=True)
            
            with self.init_lock:
                self.is_ready = True
                
            keyboard.add_hotkey(self.config['hotkey'], self.on_hotkey)
            self.log(f"🚀 等待指令 (按 {self.config['hotkey']})")
            self.update_status("System Ready")
        except Exception as e:
            self.log(f"❌ 初始化失败: {e}")

    def on_hotkey(self):
        with self.init_lock:
            if not self.is_ready:
                self.log("⏳ 系统加载中...")
                return
        self.play_trigger_sound()
        self.update_status("Scanning...")
        threading.Thread(target=self.process_screenshot, daemon=True).start()

    def fetch_price_hybrid(self, url_name):
        mem_key = url_name.replace("_", "").lower().strip()
        found_price = 0
        if mem_key in self.wfinfo_prices:
            found_price = self.wfinfo_prices[mem_key]
        if found_price == 0:
            if "blueprint" in mem_key:
                alt = mem_key.replace("blueprint", "")
                if alt in self.wfinfo_prices:
                    found_price = self.wfinfo_prices[alt]
            else:
                alt = f"{mem_key}blueprint"
                if alt in self.wfinfo_prices:
                    found_price = self.wfinfo_prices[alt]

        if found_price > 0:
            return f"⚡ 极速均价: {found_price} P", True

        self.log(f"   ☁️ 缓存未命中，实时分析订单...")
        api_url = f"https://api.warframe.market/v1/items/{url_name}/orders"
        try:
            session = self.get_clean_session()
            resp = session.get(api_url, headers={"Platform":"pc"}, timeout=8)
            if resp.status_code == 200:
                orders = resp.json()['payload']['orders']
                sell_orders = [x for x in orders if x['order_type'] == 'sell' and x['user']['status'] in ['ingame', 'online']]
                if not sell_orders:
                    return "无在线卖家", False
                sell_orders.sort(key=lambda x: x['platinum'])
                top_orders = sell_orders[:5]
                prices = [x['platinum'] for x in top_orders]
                final_price = 0
                if len(prices) >= 3:
                    filtered_prices = prices[1:] 
                    final_price = sum(filtered_prices) / len(filtered_prices)
                else:
                    final_price = sum(prices) / len(prices)
                return f"☁️ 实时均价: {int(final_price)} P", False
        except:
            pass
        return None, False

    def show_overlay(self, title, content, is_fast, index=0):
        def _show():
            top = tk.Toplevel(self)
            top.overrideredirect(True)
            top.attributes('-topmost', True)
            top.attributes('-alpha', 0.90) 
            top.config(bg=THEME["bg"]) 

            win_w, win_h = 340, 85 
            screen_h = self.winfo_screenheight()
            start_y = (screen_h // 2) - 150 + (index * 95)
            
            hidden_x = -win_w - 20 
            target_x = 30 
            top.geometry(f"{win_w}x{win_h}+{hidden_x}+{int(start_y)}")

            main_frame = tk.Frame(top, bg=THEME["card_bg"])
            main_frame.pack(fill="both", expand=True, padx=2, pady=2)

            strip = tk.Frame(main_frame, bg=THEME["gold"], width=8)
            strip.pack(side="left", fill="y")

            content_frame = tk.Frame(main_frame, bg=THEME["card_bg"], padx=15)
            content_frame.pack(side="left", fill="both", expand=True)
            
            tk.Label(content_frame, text=title, fg=THEME["gold"], bg=THEME["card_bg"], 
                     font=("微软雅黑", 13, "bold"), anchor="w").pack(fill="x", pady=(15, 3))
            
            text_color = THEME["fast_text"] if is_fast else THEME["live_text"]
            tk.Label(content_frame, text=content, fg=text_color, bg=THEME["card_bg"], 
                     font=("Arial", 12), anchor="w").pack(fill="x")

            anim_data = {"curr_x": hidden_x, "state": "in", "velocity": 40}

            def animate():
                try:
                    if not top.winfo_exists(): return
                    if anim_data["state"] == "in":
                        dist = target_x - anim_data["curr_x"]
                        if dist > 1:
                            move = max(dist * 0.15, 2) 
                            anim_data["curr_x"] += move
                            top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{int(start_y)}")
                            top.after(10, animate)
                        else:
                            anim_data["curr_x"] = target_x
                            top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{int(start_y)}")
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
                            top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{int(start_y)}")
                            top.after(10, animate)
                        else:
                            top.destroy()
                except:
                    pass

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
                        base_url = self.wfm_dict[dict_key]['url_name']
                        real_name = self.wfm_dict[dict_key]['real_cn_name']
                        
                        leftover = clean_ocr.replace(dict_key, "")
                        final_suffix = "set" 
                        cn_part_name = ""    
                        
                        for cn, en in PART_MAP.items():
                            if cn in leftover:
                                final_suffix = en
                                cn_part_name = cn
                                break
                        
                        if final_suffix == "set":
                            final_url = f"{base_url}_set"
                            final_name = f"{real_name} 套装"
                        else:
                            final_url = f"{base_url}_{final_suffix}"
                            final_name = f"{real_name} {cn_part_name}"
                        
                        if final_name in seen_items: break

                        self.log(f"🔎 识别: {final_name}")
                        price_str, is_fast = self.fetch_price_hybrid(final_url)
                        
                        if price_str:
                            self.log(f"   -> {price_str}")
                            overlay_items.append((final_name, price_str, is_fast))
                            seen_items.add(final_name)
                            found_count += 1
                        else:
                            self.log("   -> ❌ 未找到价格数据")
                            
                        break 
            
            for idx, (name, price, is_fast) in enumerate(overlay_items):
                self.show_overlay(name, price, is_fast, index=idx)
            
            msg = f"完成 (找到 {found_count} 个)" if found_count else "未匹配到物品"
            self.update_status(msg)
            self.log(msg)

        except Exception as e:
            self.log(f"❌ Error: {e}")

if __name__ == "__main__":
    app = WFPriceHelperApp()
    app.protocol("WM_DELETE_WINDOW", lambda: (keyboard.unhook_all(), app.destroy()))
    app.mainloop()