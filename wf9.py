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
import unicodedata

# ====== 閰嶇疆鍖哄煙 ======
DEFAULT_CONFIG = {
    "hotkey": "alt+q",
    "bbox": [0,0,1920,1080],
    "proxy": "",
    "sound_file": "default", 
    "sound_volume": 0.5 
}
CONFIG_FILE = "config.json"
WFM_DICT_PATH = "items.json"
QR_IMAGE_PATH = "qr.png" 
SOUND_DIR = "sound"

THEME = {
    "bg": "#070b14", "card_bg": "#101a2f", "text": "#eaf1ff",
    "gold": "#ff9f1c", "gold_hover": "#f18701",
    "fast_text": "#34d399", "live_text": "#38bdf8",
    "info_btn": "#2563eb", "info_hover": "#1d4ed8",
    "progress_bg": "#1f2a44", "progress_fill": "#22d3ee", "progress_err": "#ef4444",
    "panel_border": "#24365b", "input_bg": "#0e1830", "muted": "#92a3c3"
}

PART_MAP = {
    "蓝图": "blueprint", "总图": "blueprint",
    "机体": "chassis", "系统": "systems", "神经光元": "neuroptics", "视光器": "neuroptics",
    "枪机": "receiver", "枪管": "barrel", "枪托": "stock", "连接器": "link",
    "刀刃": "blade", "握柄": "handle", "握把": "handle",
    "护手": "gauntlet", "圆盘": "disc", "饰物": "ornament",
    "弓臂": "limb", "上弓臂": "upper_limb", "下弓臂": "lower_limb",
    "弓弦": "string", "握把套": "grip",
    "缰绳": "harness", "机翼": "wings", "引擎": "engine",
    "外壳": "carapace", "脑部": "cerebrum",
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
        self.title("Warframe 开核桃助手 [V5.3.2]")
        self.geometry("520x700")
        self.minsize(500, 800)
        self.configure(fg_color=THEME["bg"]) 

        self.wfinfo_prices = {} 
        self.price_mode = "fast"
        self.sync_running = False
        self.hotkey_registered = None
        self.part_map_entries = []
        self.init_state = "loading"
        self.init_error = ""
        self.is_ready = False
        self.init_lock = threading.Lock()
        
        # 1. 鍔犺浇閰嶇疆
        self.load_config()
        
        # 2. 初始化音效
        pygame.mixer.init()
        self.current_sound = None
        self.sound_files = []
        self.scan_sound_files()
        self.load_custom_sound() 
        
        # 3. 鏋勫缓鐣岄潰
        self.setup_ui()
        self.set_price_mode("fast")
        self.register_hotkey(self.config["hotkey"])
        self.part_map_entries = [
            (self.normalize_text(k), v, k)
            for k, v in PART_MAP.items()
        ]
        
        self.log("正在初始化系统...")
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

    # ====== 鐣岄潰鍥炶皟鍑芥暟 ======

    @staticmethod
    def normalize_text(text):
        if text is None:
            return ""
        s = unicodedata.normalize("NFKC", str(text)).lower()
        # 保留中文/字母/数字，去掉空格和各类符号，统一 OCR 与字典键格式
        return "".join(ch for ch in s if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"))

    def register_hotkey(self, hotkey):
        try:
            if self.hotkey_registered:
                keyboard.remove_hotkey(self.hotkey_registered)
        except:
            pass

        try:
            keyboard.add_hotkey(hotkey, self.on_hotkey)
            self.hotkey_registered = hotkey
            return True
        except Exception as e:
            self.hotkey_registered = None
            self.log(f"❌ 热键注册失败: {e}")
            return False

    def resolve_part_suffix(self, leftover_text):
        matches = []
        for cn_norm, en, cn_display in self.part_map_entries:
            if cn_norm and cn_norm in leftover_text:
                matches.append((cn_norm, en, cn_display))

        if not matches:
            return "set", ""

        # 优先非蓝图部件，避免“机体蓝图/系统蓝图”被错误识别成仅蓝图
        non_blueprint = [m for m in matches if m[1] != "blueprint"]
        chosen = None
        if non_blueprint:
            chosen = max(non_blueprint, key=lambda x: len(x[0]))
        else:
            chosen = max(matches, key=lambda x: len(x[0]))

        return chosen[1], chosen[2]

    def update_hotkey(self):
        new_hk = self.entry_hotkey.get().strip()
        try:
            if self.register_hotkey(new_hk):
                self.config['hotkey'] = new_hk
                self.save_config()
                self.log(f"✅ 热键更新为: {new_hk}")
            else:
                self.log("❌ 热键格式错误")
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
        self.log("✅ 代理配置已保存")
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
        self.log(f"🔔 音效已切换: {choice}")
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
        self.log("📁 音效列表已刷新")

    def select_sound_file(self):
        self.log("📂 请把音频文件放进 sound 文件夹，再点击刷新。")
        try:
            os.startfile(get_sound_dir())
        except:
            pass

    def update_wfm_dict(self):
        def _update_task():
            self.log("📡 正在连接 Warframe Market 更新字典...")
            self.update_status("更新字典中...")
            try:
                target_url = "https://api.warframe.market/v2/items"
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
                            key = self.normalize_text(item_name)
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
【快速上手】
1. 游戏建议使用无边框窗口模式，若使用窗口模式，且除游戏主窗口外也存在与游戏内容有关的文本，可能产生误识别，此种情况下推荐设置截图范围为游戏窗口范围；
一般来说无需注意。
3. 按下快捷键（默认 =）。
4. 等待 1-2 秒，左侧会弹出价格结果。

【模式选择】
1. 极速模式：提前加载Wfinfo的价格数据，查询时间约1秒。
2. 实时模式：识别到物品后再向Warframe Market查询物品价格，总查询时间首先与网络状况有关，其次与物品数量有关，若极速模式可用，不推荐使用本模式。

【均价算法】
均价=Warframe Market内该物品卖价去掉最低价后的最低五位的平均数

【自定义音效】
1. 软件目录下会自动生成 sound 文件夹。
2. 把 MP3 / WAV / OGG 放进该文件夹。
3. 点击界面里的「刷新」按钮。
4. 在下拉框里切换并试听。


【同步说明】
程序启动后会自动同步市场缓存，代理变更后会自动重试同步。
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
            ctk.CTkLabel(top, text="欢迎扫码支持", font=("微软雅黑", 12)).pack()
        except: pass

    def log(self, msg):
        self.after(0, lambda: self._log_thread_safe(msg))

    def _log_thread_safe(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_init_state(self, state, error=""):
        with self.init_lock:
            self.init_state = state
            self.init_error = error
            self.is_ready = (state == "ready")

    def _create_ocr_with_timeout(self, timeout_sec=20):
        result = {"ocr": None, "error": None}

        def _worker():
            try:
                result["ocr"] = RapidOCR()
            except Exception as e:
                result["error"] = e

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout_sec)
        if t.is_alive():
            return None, f"OCR 初始化超时（>{timeout_sec}s）"
        if result["error"] is not None:
            return None, str(result["error"])
        return result["ocr"], None

    def set_price_mode(self, mode, log_change=False):
        if mode not in ("fast", "live"):
            return
        self.price_mode = mode
        mode_text = "极速模式" if mode == "fast" else "实时模式"
        mode_color = THEME["gold"] if mode == "fast" else THEME["live_text"]

        if hasattr(self, "mode_value_label"):
            self.mode_value_label.configure(text=mode_text, text_color=mode_color)
        if hasattr(self, "mode_toggle_btn"):
            self.mode_toggle_btn.configure(text="切到实时" if mode == "fast" else "切到极速")
        if log_change:
            self.log(f"🎛 已切换为{mode_text}")

    def toggle_price_mode(self):
        next_mode = "live" if self.price_mode == "fast" else "fast"
        self.set_price_mode(next_mode, log_change=True)
        self.update_status(f"当前{ '实时模式' if next_mode == 'live' else '极速模式' }")
        if next_mode == "fast":
            self.log("📡 切换到极速模式，正在重新同步价格库...")
            self.start_sync_task()

    def update_status(self, msg):
        self.after(0, lambda: self.status_label.configure(text=msg))

    # ====== 缃戠粶閫昏緫 ======
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
        if self.sync_running:
            self.log("⏳ 价格库同步进行中，请稍候...")
            return
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
        self.update_sync_text("正在连接云端服务...")
        
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
                self.update_status("价格库已同步")
                time.sleep(1.2)
                self.after(0, lambda: self.progress_bar.pack_forget())
                self.after(0, lambda: self.progress_label.pack_forget())
            else:
                self.after(0, lambda: self.progress_bar.configure(progress_color=THEME["progress_err"]))
                self.update_sync_text("❌ 同步失败，可切换实时模式")
                self.update_status("同步失败")
                time.sleep(3.0)
                self.after(0, lambda: self.progress_bar.pack_forget())
                self.after(0, lambda: self.progress_label.pack_forget())

        threading.Thread(target=_finish_anim, daemon=True).start()

    def download_price_table_smart(self):
        target_url = "https://api.warframestat.us/wfinfo/prices/"
        encoded_url = urllib.parse.quote(target_url)
        
        sources = [
            (f"https://api.allorigins.win/raw?url={encoded_url}", "云线路 A"),
            (f"https://api.codetabs.com/v1/proxy?quest={encoded_url}", "云线路 B"),
            (target_url, "官方直连")
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
                        self.log("   ❌ 解析错误")
                        continue
                else:
                    self.log(f"   ❌ 失败: HTTP {resp.status_code}")
            except Exception:
                self.log("   ❌ 连接异常")

        if not success:
            self.log("⚠️ 所有线路失败，切换到实时模式")
            self.finish_progress(False)

    # ====== 鐣岄潰鏋勫缓 ======
    def setup_ui(self):
        self.progress_bar = ctk.CTkProgressBar(
            self,
            height=12,
            corner_radius=999,
            fg_color=THEME["progress_bg"],
            progress_color=THEME["progress_fill"],
            border_width=0
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=24, pady=(14, 8))

        self.header_frame = ctk.CTkFrame(
            self,
            fg_color=THEME["card_bg"],
            corner_radius=18,
            border_width=1,
            border_color=THEME["panel_border"]
        )
        self.header_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(
            self.header_frame,
            text="WARFRAME PRIME SCAN",
            font=("Segoe UI", 12, "bold"),
            text_color=THEME["live_text"]
        ).pack(anchor="w", padx=18, pady=(14, 0))
        ctk.CTkLabel(
            self.header_frame,
            text="开核桃助手 V5.3.2",
            font=("微软雅黑", 26, "bold"),
            text_color=THEME["text"]
        ).pack(anchor="w", padx=18, pady=(2, 0))
        ctk.CTkLabel(
            self.header_frame,
            text="一键识别遗物奖励，极速给出市场价格。",
            font=("微软雅黑", 12),
            text_color=THEME["muted"]
        ).pack(anchor="w", padx=18, pady=(2, 10))
        ctk.CTkLabel(
            self.header_frame,
            text="by RanAway22",
            font=("Segoe UI", 11, "bold"),
            text_color=THEME["gold"]
        ).pack(anchor="w", padx=18, pady=(0, 10))

        status_chip = ctk.CTkFrame(
            self.header_frame,
            fg_color=THEME["input_bg"],
            corner_radius=999,
            border_width=1,
            border_color=THEME["panel_border"]
        )
        status_chip.pack(anchor="e", padx=14, pady=(0, 12))
        self.status_label = ctk.CTkLabel(status_chip, text="Initializing...", text_color=THEME["gold"], font=("Consolas", 11, "bold"))
        self.status_label.grid(row=0, column=0, padx=(10, 8), pady=4)
        ctk.CTkLabel(status_chip, text="模式:", font=("微软雅黑", 11), text_color=THEME["muted"]).grid(row=0, column=1, padx=(0, 4), pady=4)
        self.mode_value_label = ctk.CTkLabel(status_chip, text="极速模式", text_color=THEME["gold"], font=("微软雅黑", 11, "bold"))
        self.mode_value_label.grid(row=0, column=2, padx=(0, 8), pady=4)
        self.mode_toggle_btn = ctk.CTkButton(
            status_chip,
            text="切到实时",
            width=74,
            height=24,
            corner_radius=999,
            fg_color=THEME["info_btn"],
            hover_color=THEME["info_hover"],
            font=("微软雅黑", 10, "bold"),
            command=self.toggle_price_mode
        )
        self.mode_toggle_btn.grid(row=0, column=3, padx=(0, 8), pady=4)

        action_row = ctk.CTkFrame(
            self,
            fg_color=THEME["card_bg"],
            corner_radius=12,
            border_width=1,
            border_color=THEME["panel_border"]
        )
        action_row.pack(fill="x", padx=20, pady=(2, 10))
        action_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            action_row,
            text="📘 新手教程",
            height=40,
            corner_radius=12,
            fg_color=THEME["info_btn"],
            hover_color=THEME["info_hover"],
            font=("微软雅黑", 13, "bold"),
            command=self.show_tutorial
        ).grid(row=0, column=0, padx=(10, 6), pady=10, sticky="ew")
        ctk.CTkButton(
            action_row,
            text="☕ 支持作者",
            height=40,
            corner_radius=12,
            fg_color=THEME["gold"],
            hover_color=THEME["gold_hover"],
            text_color="#111111",
            font=("微软雅黑", 13, "bold"),
            command=self.show_donate_qr
        ).grid(row=0, column=1, padx=(6, 10), pady=10, sticky="ew")

        ctk.CTkLabel(self, text="控制台设置", font=("微软雅黑", 14, "bold"), text_color=THEME["live_text"]).pack(anchor="w", padx=24, pady=(0, 6))

        self.settings_frame = ctk.CTkFrame(
            self,
            fg_color=THEME["card_bg"],
            corner_radius=14,
            border_width=1,
            border_color=THEME["panel_border"]
        )
        self.settings_frame.pack(fill="x", padx=20, pady=2)
        self.settings_frame.grid_columnconfigure(1, weight=1)

        label_font = ("微软雅黑", 13)
        input_font = ("Consolas", 12)
        input_style = {
            "fg_color": THEME["input_bg"],
            "border_color": THEME["panel_border"],
            "text_color": THEME["text"],
            "font": input_font,
            "height": 34
        }
        action_btn_style = {
            "width": 88,
            "height": 34,
            "corner_radius": 10,
            "fg_color": THEME["gold"],
            "hover_color": THEME["gold_hover"],
            "text_color": "#0b0f1a",
            "font": ("微软雅黑", 12, "bold")
        }

        ctk.CTkLabel(self.settings_frame, text="触发热键", font=label_font, text_color=THEME["text"]).grid(row=0, column=0, padx=14, pady=10, sticky="w")
        self.entry_hotkey = ctk.CTkEntry(self.settings_frame, **input_style)
        self.entry_hotkey.insert(0, self.config['hotkey'])
        self.entry_hotkey.grid(row=0, column=1, padx=8, sticky="ew")
        ctk.CTkButton(self.settings_frame, text="应用", command=self.update_hotkey, **action_btn_style).grid(row=0, column=2, padx=10)

        ctk.CTkLabel(self.settings_frame, text="截图范围", font=label_font, text_color=THEME["text"]).grid(row=1, column=0, padx=14, pady=10, sticky="w")
        self.bbox_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.bbox_frame.grid(row=1, column=1, sticky="w", padx=8)
        self.bbox_entries = []
        for val in self.config['bbox']:
            e = ctk.CTkEntry(self.bbox_frame, width=64, justify="center", **input_style)
            e.insert(0, str(val))
            e.pack(side="left", padx=3)
            self.bbox_entries.append(e)
        ctk.CTkButton(self.settings_frame, text="保存", command=self.update_bbox, **action_btn_style).grid(row=1, column=2, padx=10)

        ctk.CTkLabel(self.settings_frame, text="本地代理", font=label_font, text_color=THEME["text"]).grid(row=2, column=0, padx=14, pady=10, sticky="w")
        self.entry_proxy = ctk.CTkEntry(self.settings_frame, placeholder_text="留空使用直连或云加速", **input_style)
        self.entry_proxy.insert(0, self.config.get('proxy', ''))
        self.entry_proxy.grid(row=2, column=1, padx=8, sticky="ew")
        ctk.CTkButton(self.settings_frame, text="保存", command=self.update_proxy, **action_btn_style).grid(row=2, column=2, padx=10)

        ctk.CTkLabel(self.settings_frame, text="提示音效", font=label_font, text_color=THEME["text"]).grid(row=3, column=0, padx=14, pady=10, sticky="w")
        sound_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        sound_frame.grid(row=3, column=1, padx=8, sticky="ew")
        sound_frame.grid_columnconfigure(0, weight=1)
        self.combo_sound = ctk.CTkComboBox(
            sound_frame,
            values=self.sound_files,
            command=self.change_sound,
            fg_color=THEME["input_bg"],
            border_color=THEME["panel_border"],
            button_color=THEME["info_btn"],
            button_hover_color=THEME["info_hover"],
            dropdown_fg_color=THEME["card_bg"],
            dropdown_hover_color=THEME["input_bg"],
            dropdown_text_color=THEME["text"],
            font=input_font,
            height=34
        )
        self.combo_sound.set(self.config.get("sound_file", "default"))
        self.combo_sound.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            sound_frame,
            text="刷新",
            width=60,
            height=34,
            corner_radius=10,
            fg_color="transparent",
            hover_color=THEME["input_bg"],
            border_width=1,
            border_color=THEME["panel_border"],
            command=self.refresh_sounds
        ).grid(row=0, column=1, padx=(6, 0))
        ctk.CTkButton(self.settings_frame, text="打开目录", command=lambda: os.startfile(get_sound_dir()), **action_btn_style).grid(row=3, column=2, padx=10)

        ctk.CTkLabel(self.settings_frame, text="音量调节", font=label_font, text_color=THEME["text"]).grid(row=4, column=0, padx=14, pady=10, sticky="w")
        vol_f = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        vol_f.grid(row=4, column=1, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        vol_f.grid_columnconfigure(0, weight=1)
        self.slider_volume = ctk.CTkSlider(
            vol_f,
            from_=0,
            to=1,
            number_of_steps=100,
            command=self.update_volume,
            progress_color=THEME["live_text"],
            button_color=THEME["gold"],
            button_hover_color=THEME["gold_hover"]
        )
        self.slider_volume.set(self.config.get("sound_volume", 0.5))
        self.slider_volume.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(vol_f, text="🔊 试听", command=self.play_trigger_sound, **action_btn_style).grid(row=0, column=1)

        ctk.CTkLabel(self, text="运行日志", font=("微软雅黑", 14, "bold"), text_color=THEME["live_text"]).pack(anchor="w", padx=24, pady=(0, 6))
        log_wrap = ctk.CTkFrame(self, fg_color=THEME["card_bg"], corner_radius=12, border_width=1, border_color=THEME["panel_border"])
        log_wrap.pack(fill="both", expand=True, padx=20, pady=0)
        self.log_text = ctk.CTkTextbox(
            log_wrap,
            font=("Consolas", 12),
            activate_scrollbars=True,
            fg_color=THEME["card_bg"],
            border_width=0,
            text_color=THEME["text"]
        )
        self.log_text.pack(fill="both", expand=True, padx=8, pady=8)
        self.log_text.configure(state="disabled")
        ctk.CTkLabel(self, text="Designed for Tenno · RanAway22", font=("Segoe UI", 10, "bold"), text_color=THEME["muted"]).pack(pady=8)

    def init_resources(self):
        try:
            self._set_init_state("loading")
            self.update_status("系统初始化中...")

            ocr, ocr_error = self._create_ocr_with_timeout(timeout_sec=20)
            if ocr_error:
                self._set_init_state("failed", f"OCR: {ocr_error}")
                self.log(f"❌ OCR 初始化失败: {ocr_error}")
                self.update_status("初始化失败")
                return
            self.ocr = ocr
            self.log("✅ OCR 引擎就绪")
            if not os.path.exists(WFM_DICT_PATH):
                self.log(f"❌ 找不到字典文件: {WFM_DICT_PATH}")
                self._set_init_state("failed", f"缺少字典文件: {WFM_DICT_PATH}")
                self.update_status("初始化失败")
                return
            with open(WFM_DICT_PATH, 'r', encoding='utf-8') as f:
                raw_dict = json.load(f)
            # 统一键格式，避免 Prime/prime 大小写与空格导致无法匹配
            self.wfm_dict = {
                self.normalize_text(k): v
                for k, v in raw_dict.items()
                if isinstance(v, dict) and "url_name" in v and "real_cn_name" in v
            }
            self.log(f"📖 字典加载: {len(self.wfm_dict)} 条目")
            self.sorted_keys = sorted(self.wfm_dict.keys(), key=len, reverse=True)
            if not self.wfm_dict:
                self._set_init_state("failed", "字典为空或格式不匹配")
                self.log("❌ 字典为空或格式不匹配")
                self.update_status("初始化失败")
                return

            self._set_init_state("ready")

            self.log(f"🚀 等待指令 (按 {self.config['hotkey']})")
            self.update_status("系统就绪")
        except Exception as e:
            self._set_init_state("failed", str(e))
            self.log(f"❌ 初始化失败: {e}")
            self.update_status("初始化失败")

    def on_hotkey(self):
        with self.init_lock:
            is_ready = self.is_ready
            init_state = self.init_state
            init_error = self.init_error

        if not is_ready:
            if init_state == "failed":
                self.log(f"❌ 系统初始化失败: {init_error}")
                self.log("🔄 正在尝试重新初始化...")
                self._set_init_state("loading")
                self.update_status("重试初始化中...")
                threading.Thread(target=self.init_resources, daemon=True).start()
            else:
                self.log("⏳ 系统加载中...")
            return
        self.play_trigger_sound()
        self.update_status("扫描中...")
        threading.Thread(target=self.process_screenshot, daemon=True).start()

    def fetch_price_hybrid(self, url_name):
        mem_key = url_name.replace("_", "").lower().strip()
        found_price = 0
        if self.price_mode == "fast":
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

        if self.price_mode == "live":
            self.log("   ☁️ 实时模式：直接分析订单...")
        else:
            self.log("   ☁️ 缓存未命中，实时分析订单...")
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

            win_w, win_h = 460, 120
            screen_h = self.winfo_screenheight()
            start_y = (screen_h // 2) - 180 + (index * 130)
            
            hidden_x = -win_w - 20 
            target_x = 30 
            top.geometry(f"{win_w}x{win_h}+{hidden_x}+{int(start_y)}")

            main_frame = tk.Frame(top, bg=THEME["card_bg"])
            main_frame.pack(fill="both", expand=True, padx=2, pady=2)

            strip = tk.Frame(main_frame, bg=THEME["gold"], width=10)
            strip.pack(side="left", fill="y")

            content_frame = tk.Frame(main_frame, bg=THEME["card_bg"], padx=18, pady=6)
            content_frame.pack(side="left", fill="both", expand=True)
            
            tk.Label(content_frame, text=title, fg=THEME["gold"], bg=THEME["card_bg"], 
                     font=("微软雅黑", 17, "bold"), anchor="w").pack(fill="x", pady=(6, 4))
            
            text_color = THEME["fast_text"] if is_fast else THEME["live_text"]
            tk.Label(content_frame, text=content, fg=text_color, bg=THEME["card_bg"], 
                     font=("Segoe UI", 16, "bold"), anchor="w").pack(fill="x", pady=(0, 6))

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
                            top.after(9500, animate) 

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

    def build_ocr_candidates(self, ocr_result):
        candidates = []
        blocks = []

        for line in ocr_result:
            if not isinstance(line, (list, tuple)) or len(line) < 2:
                continue

            raw_text = line[1]
            clean_text = self.normalize_text(raw_text)
            if clean_text:
                candidates.append(clean_text)

            box = line[0]
            if not isinstance(box, (list, tuple)) or len(box) < 4:
                continue

            try:
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
                cx = sum(xs) / len(xs)
                cy = sum(ys) / len(ys)
                width = max(xs) - min(xs)
                height = max(ys) - min(ys)
                if clean_text:
                    blocks.append({
                        "clean": clean_text,
                        "cx": cx,
                        "cy": cy,
                        "width": width,
                        "height": height,
                    })
            except Exception:
                continue

        # 单行数据不足时直接返回
        if len(blocks) < 2:
            return list(dict.fromkeys(candidates))

        # 先按 x 聚类到“列”，再按 y 拼接同列相邻文本
        blocks.sort(key=lambda b: b["cx"])
        columns = []
        for block in blocks:
            placed = False
            for col in columns:
                x_threshold = max(55.0, col["avg_w"] * 0.9)
                if abs(block["cx"] - col["avg_cx"]) <= x_threshold:
                    col["items"].append(block)
                    n = len(col["items"])
                    col["avg_cx"] = (col["avg_cx"] * (n - 1) + block["cx"]) / n
                    col["avg_w"] = (col["avg_w"] * (n - 1) + max(block["width"], 1.0)) / n
                    col["avg_h"] = (col["avg_h"] * (n - 1) + max(block["height"], 1.0)) / n
                    placed = True
                    break
            if not placed:
                columns.append({
                    "items": [block],
                    "avg_cx": block["cx"],
                    "avg_w": max(block["width"], 1.0),
                    "avg_h": max(block["height"], 1.0),
                })

        for col in columns:
            items = sorted(col["items"], key=lambda b: b["cy"])
            if not items:
                continue

            group = [items[0]["clean"]]
            prev_cy = items[0]["cy"]
            line_gap_threshold = max(18.0, col["avg_h"] * 1.8)

            for item in items[1:]:
                if (item["cy"] - prev_cy) <= line_gap_threshold:
                    group.append(item["clean"])
                else:
                    merged = "".join(group)
                    if merged:
                        candidates.append(merged)
                    group = [item["clean"]]
                prev_cy = item["cy"]

            merged = "".join(group)
            if merged:
                candidates.append(merged)

        # 去重并保持顺序
        return list(dict.fromkeys(candidates))

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

            text_candidates = self.build_ocr_candidates(result)

            for clean_ocr in text_candidates:
                if len(clean_ocr) < 2: continue

                for dict_key in self.sorted_keys:
                    if dict_key in clean_ocr:
                        base_url = self.wfm_dict[dict_key]['url_name']
                        real_name = self.wfm_dict[dict_key]['real_cn_name']
                        
                        leftover = clean_ocr.replace(dict_key, "", 1)
                        final_suffix, cn_part_name = self.resolve_part_suffix(leftover)
                        
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


