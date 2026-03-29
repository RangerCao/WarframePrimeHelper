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
import urllib.parse

# ====== 配置区域 ======
DEFAULT_CONFIG = {
    "hotkey": "alt+q",
    "bbox": [0,0,1920,1080],
    "proxy": "" 
}
CONFIG_FILE = "config.json"
WFM_DICT_PATH = "wfm_dictionary.json"
QR_IMAGE_PATH = "qr.png" 

THEME = {
    "bg": "#1a1a1a", "card_bg": "#2b2b2b", "text": "#ffffff", 
    "gold": "#d4af37", "gold_hover": "#b8952b",
    "fast_text": "#00ff7f", "live_text": "#00bfff"
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
    try: base_path = sys._MEIPASS
    except: base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class WFPriceHelperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Warframe 开核桃助手 v3.5")
        self.geometry("700x620") 
        self.configure(fg_color=THEME["bg"]) 

        self.wfinfo_prices = {} 
        self.load_config()
        self.setup_ui()
        
        self.is_ready = False
        self.init_lock = threading.Lock()
        
        self.log("正在初始化神经光元 (System)...")
        threading.Thread(target=self.init_resources, daemon=True).start()
        threading.Thread(target=self.download_price_table_smart, daemon=True).start()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f: self.config = json.load(f)
            except: self.config = DEFAULT_CONFIG
        else:
            self.config = DEFAULT_CONFIG
            self.save_config()
        if "proxy" not in self.config: self.config["proxy"] = ""

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(self.config, f, indent=4)
        except: pass

    # 🟢 核心修复1：创建干净的 Session
    def get_clean_session(self):
        s = requests.Session()
        proxy_url = self.config.get("proxy", "").strip()
        
        if proxy_url:
            # 如果用户填了代理，使用即时代理
            if not proxy_url.startswith("http"): proxy_url = "http://" + proxy_url
            s.proxies = {"http": proxy_url, "https": proxy_url}
            s.trust_env = True # 信任用户配置
        else:
            # 🔴 关键修复：如果没有填代理，强制忽略系统环境变量
            # 这能解决 10061 报错（系统残留代理导致的问题）
            s.trust_env = False 
            s.proxies = {}
            
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        return s

    # 🔴 核心2：多线路云加速
    def download_price_table_smart(self):
        target_url = "https://api.warframestat.us/wfinfo/prices/"
        encoded_url = urllib.parse.quote(target_url)
        
        # 扩展的线路列表
        sources = [
            (target_url, "官方直连"),
            (f"https://api.allorigins.win/raw?url={encoded_url}", "云线路 A (AllOrigins)"),
            (f"https://api.codetabs.com/v1/proxy?quest={encoded_url}", "云线路 B (CodeTabs)"),
            (f"https://thingproxy.freeboard.io/fetch/{target_url}", "云线路 C (ThingProxy)")
        ]

        self.log("📡 正在寻找最佳线路同步数据库...")
        
        # 获取配置好的 Session
        session = self.get_clean_session()
        
        success = False
        for url, name in sources:
            try:
                self.log(f"   🔄 尝试: {name}...")
                
                # 如果是官方直连，且用户没配代理，可能会慢，给短一点超时
                # 如果是云线路，不需要本地代理，直接访问
                current_timeout = 15
                
                resp = session.get(url, timeout=current_timeout)
                
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        # 兼容 AllOrigins 有时返回的包装
                        if "contents" in data and isinstance(data["contents"], str):
                             data = json.loads(data["contents"])

                        new_prices = {}
                        count = 0
                        
                        # 兼容列表或字典结构
                        data_list = data if isinstance(data, list) else data.get("prices", [])
                        
                        for item in data_list:
                            # 鲁棒性解析
                            if not isinstance(item, dict): continue
                            name_val = item.get("name") or item.get("item_name")
                            if not name_val: continue
                            
                            clean_name = name_val.lower().replace(" ", "").replace("_", "").strip()
                            price_val = item.get("custom_avg") or item.get("plat") or item.get("platinum")
                            
                            if price_val:
                                if float(price_val) > 0: 
                                    new_prices[clean_name] = int(float(price_val))
                                    count += 1
                        
                        if count > 0:
                            self.wfinfo_prices = new_prices
                            self.log(f"✅ 同步成功! (线路: {name})")
                            self.log(f"   已缓存 {count} 个物品价格")
                            self.update_status("极速模式")
                            success = True
                            break 
                    except Exception as parse_error:
                        self.log(f"   ❌ 解析错误: {parse_error}")
                        continue
                else:
                    self.log(f"   ❌ 连接失败: HTTP {resp.status_code}")

            except requests.exceptions.ProxyError:
                self.log(f"   ❌ 代理配置错误 (请检查端口)")
            except requests.exceptions.ConnectionError:
                self.log(f"   ❌ 网络不通")
            except Exception as e:
                self.log(f"   ❌ 未知错误: {str(e)[:50]}")

        if not success:
            self.log("⚠️ 所有线路均不可用，已自动切换为 [实时模式]")
            self.update_status("实时模式")

    def setup_ui(self):
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(20, 5))
        ctk.CTkLabel(self.header_frame, text="开核桃助手 V3.5", font=("微软雅黑", 24, "bold"), text_color=THEME["gold"]).pack(side="left")
        self.status_label = ctk.CTkLabel(self.header_frame, text="Initializing...", text_color="gray")
        self.status_label.pack(side="right", anchor="s")

        self.settings_frame = ctk.CTkFrame(self, fg_color=THEME["card_bg"], corner_radius=10, border_width=1, border_color=THEME["gold"])
        self.settings_frame.pack(fill="x", padx=20, pady=10)
        self.settings_frame.grid_columnconfigure(1, weight=1)
        self.settings_frame.grid_columnconfigure(3, weight=1)

        # 1. 快捷键
        ctk.CTkLabel(self.settings_frame, text="触发热键:", font=("微软雅黑", 12)).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.entry_hotkey = ctk.CTkEntry(self.settings_frame, placeholder_text="例如: alt+q")
        self.entry_hotkey.insert(0, self.config['hotkey'])
        self.entry_hotkey.grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkButton(self.settings_frame, text="更新热键", width=80, fg_color=THEME["gold"], text_color="black", hover_color=THEME["gold_hover"], command=self.update_hotkey).grid(row=0, column=2, padx=10)

        # 2. 截图范围
        ctk.CTkLabel(self.settings_frame, text="截图范围:", font=("微软雅黑", 12)).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.bbox_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.bbox_frame.grid(row=1, column=1, sticky="w", padx=5)
        self.bbox_entries = []
        for val in self.config['bbox']:
            entry = ctk.CTkEntry(self.bbox_frame, width=50, justify="center")
            entry.insert(0, str(val))
            entry.pack(side="left", padx=2)
            self.bbox_entries.append(entry)
        ctk.CTkButton(self.settings_frame, text="保存范围", width=80, fg_color="transparent", border_width=1, border_color=THEME["gold"], text_color=THEME["gold"], command=self.update_bbox).grid(row=1, column=2, padx=10)

        # 3. 代理设置
        ctk.CTkLabel(self.settings_frame, text="本地代理:", font=("微软雅黑", 12)).grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.entry_proxy = ctk.CTkEntry(self.settings_frame, placeholder_text="若您未开启代理无需填写")
        self.entry_proxy.insert(0, self.config.get('proxy', ''))
        self.entry_proxy.grid(row=2, column=1, padx=5, sticky="ew")
        ctk.CTkButton(self.settings_frame, text="保存/重试", width=80, fg_color="transparent", border_width=1, border_color=THEME["gold"], text_color=THEME["gold"], command=self.update_proxy).grid(row=2, column=2, padx=10)

        ctk.CTkLabel(self.settings_frame, text="* 遇到 10061 错误请清空此栏并保存", font=("Arial", 10), text_color="gray").grid(row=3, column=1, sticky="w", padx=5)

        btn_donate = ctk.CTkButton(self, text="☕ 觉得好用？请作者喝杯咖啡 ❤️", height=40, font=("微软雅黑", 14, "bold"), fg_color=THEME["gold"], text_color="black", hover_color=THEME["gold_hover"], corner_radius=8, command=self.show_donate_qr)
        btn_donate.pack(fill="x", padx=20, pady=(5, 10))

        ctk.CTkLabel(self, text="📊 运行日志", font=("微软雅黑", 12)).pack(anchor="w", padx=25, pady=(0, 0))
        self.log_text = ctk.CTkTextbox(self, font=("Consolas", 12), activate_scrollbars=True)
        self.log_text.pack(fill="both", expand=True, padx=20, pady=5)
        self.log_text.configure(state="disabled")
        ctk.CTkLabel(self, text="Designed for Tenno", font=("Arial", 10), text_color="#555").pack(pady=5)

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

    def update_proxy(self):
        proxy = self.entry_proxy.get().strip()
        self.config['proxy'] = proxy
        self.save_config()
        self.log(f"✅ 代理配置已保存")
        if not proxy:
            self.log("   (已禁用本地代理，使用直连模式)")
        threading.Thread(target=self.download_price_table_smart, daemon=True).start()

    def init_resources(self):
        try:
            self.ocr = RapidOCR()
            self.log("✅ OCR 引擎就绪")
            if not os.path.exists(WFM_DICT_PATH):
                self.log(f"❌ 找不到字典文件: {WFM_DICT_PATH}")
                return
            with open(WFM_DICT_PATH, 'r', encoding='utf-8') as f: self.wfm_dict = json.load(f)
            self.log(f"📖 字典加载: {len(self.wfm_dict)} 条目")
            self.sorted_keys = sorted(self.wfm_dict.keys(), key=len, reverse=True)
            
            with self.init_lock:
                self.is_ready = True
                
            keyboard.add_hotkey(self.config['hotkey'], self.on_hotkey)
            self.log(f"🚀 等待指令 (按 {self.config['hotkey']})")
            self.update_status("System Ready")
        except Exception as e: self.log(f"❌ 初始化失败: {e}")

    def on_hotkey(self):
        with self.init_lock:
            if not self.is_ready:
                self.log("⏳ 系统加载中...")
                return
        self.update_status("Scanning...")
        threading.Thread(target=self.process_screenshot, daemon=True).start()

    # ====== 核心3：混合查询 + 实时智能均价 ======
    def fetch_price_hybrid(self, url_name):
        mem_key = url_name.replace("_", "").lower().strip()
        found_price = 0
        
        # 1. 内存极速
        if mem_key in self.wfinfo_prices:
            found_price = self.wfinfo_prices[mem_key]
        if found_price == 0:
            if "blueprint" in mem_key:
                alt = mem_key.replace("blueprint", "")
                if alt in self.wfinfo_prices: found_price = self.wfinfo_prices[alt]
            else:
                alt = f"{mem_key}blueprint"
                if alt in self.wfinfo_prices: found_price = self.wfinfo_prices[alt]

        if found_price > 0:
            return f"⚡ 均价: {found_price} ☁️", True

        # 2. 实时智能均价
        self.log(f"   ☁️ 缓存未命中，实时分析订单...")
        api_url = f"https://api.warframe.market/v1/items/{url_name}/orders"
        
        try:
            # 实时查询也使用干净的 session (带/不带代理)
            session = self.get_clean_session()
            resp = session.get(api_url, headers={"Platform":"pc"}, timeout=8)
            
            if resp.status_code == 200:
                orders = resp.json()['payload']['orders']
                sell_orders = [x for x in orders if x['order_type'] == 'sell' and x['user']['status'] in ['ingame', 'online']]
                
                if not sell_orders: return "无在线卖家", False
                
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
                
        except Exception as e:
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
                except: return

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