import customtkinter as ctk
import tkinter as tk
import tkinter.simpledialog
import tkinter.messagebox
from PIL import Image, ImageGrab
import keyboard
from rapidocr_onnxruntime import RapidOCR
import requests
import json
import threading
import os
import sys
import traceback
import re # 新增正则库用于提取Cookie

# ====== 配置区域 ======
DEFAULT_CONFIG = {
    "hotkey": "alt+q",
    "bbox": [0, 0, 1920, 1080]
}
CONFIG_FILE = "config.json"
WFM_DICT_PATH = "wfm_dictionary.json"
QR_IMAGE_PATH = "qr.png"

THEME = {
    "bg": "#1a1a1a",
    "card_bg": "#2b2b2b",
    "text": "#ffffff",
    "gold": "#d4af37",
    "gold_hover": "#b8952b",
    "fast_text": "#00ff7f"
}

# 零件后缀映射表
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

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind('<Enter>', self.enter)
        widget.bind('<Leave>', self.leave)

    def enter(self, event=None):
        self.showtip()

    def leave(self, event=None):
        self.hidetip()

    def showtip(self):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("微软雅黑", 10, "normal"))
        label.pack(ipadx=5, ipady=2)

    def hidetip(self):
        if self.tipwindow:
            self.tipwindow.destroy()
        self.tipwindow = None


class WFPriceHelperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Warframe 开核桃助手 v2.6 (强力登录版)")
        self.geometry("720x680")
        self.configure(fg_color=THEME["bg"])

        self.wfinfo_prices = {}
        self.load_config()
        self.setup_ui()

        self.is_ready = False
        self.init_lock = threading.Lock()

        # 核心修复：Session 不再全局复用，而是登录时重新创建
        self.http_session = None
        self.wm_auth_token = None
        self.wm_logged_in = False

        self.log("正在初始化神经光元 (System)...")
        threading.Thread(target=self.init_all_resources, daemon=True).start()

    def init_all_resources(self):
        try:
            self.ocr = RapidOCR()
            self.log("✅ OCR 引擎就绪")
        except Exception as e:
            self.log(f"❌ OCR 初始化失败: {e}")
            return

        try:
            if not os.path.exists(WFM_DICT_PATH):
                self.log(f"❌ 找不到字典文件: {WFM_DICT_PATH}")
                return
            with open(WFM_DICT_PATH, 'r', encoding='utf-8') as f:
                self.wfm_dict = json.load(f)
            self.log(f"📖 字典加载: {len(self.wfm_dict)} 条目")
            self.sorted_keys = sorted(self.wfm_dict.keys(), key=len, reverse=True)
        except Exception as e:
            self.log(f"❌ 字典加载失败: {e}")
            return

        self.download_price_table()

        with self.init_lock:
            self.is_ready = True

        keyboard.add_hotkey(self.config['hotkey'], self.on_hotkey)
        self.log(f"🚀 系统就绪! 等待指令 (按 {self.config['hotkey']})")
        self.update_status("System Ready")

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
        except:
            pass

    def download_price_table(self):
        self.log("📡 正在同步 WarframeMarket 价格库...")
        try:
            url = "https://api.warframestat.us/wfinfo/prices/"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)

            if resp.status_code == 200:
                data = resp.json()
                new_prices = {}
                count = 0
                data_list = data if isinstance(data, list) else data.get("prices", [])
                for item in data_list:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name") or item.get("item_name")
                    if not name:
                        continue
                    clean_name = name.lower().replace(" ", "").replace("_", "").strip()
                    price_val = item.get("custom_avg") or item.get("plat") or item.get("platinum")
                    if price_val:
                        try:
                            price = int(float(price_val))
                            if price > 0:
                                new_prices[clean_name] = price
                                count += 1
                        except:
                            continue

                self.wfinfo_prices = new_prices
                if count > 0:
                    self.log(f"✅ 价格库同步成功! 收录 {count} 条数据")
                    self.update_status(f"极速模式已就绪 ({count})")
                else:
                    self.log("⚠️ 收录数为 0，将使用实时查询")
            else:
                self.log(f"⚠️ 同步失败 (HTTP {resp.status_code})")
        except Exception as e:
            self.log(f"⚠️ 网络错误: {e}")

    def setup_ui(self):
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(self.header_frame, text="开核桃助手 v2.6 (强力登录版)",
                     font=("微软雅黑", 24, "bold"), text_color=THEME["gold"]).pack(side="left")
        self.status_label = ctk.CTkLabel(self.header_frame, text="Initializing...", text_color="gray")
        self.status_label.pack(side="right", anchor="s")

        main_settings = ctk.CTkFrame(self, fg_color=THEME["card_bg"], corner_radius=10,
                                     border_width=1, border_color=THEME["gold"])
        main_settings.pack(fill="x", padx=20, pady=5)

        basic_frame = ctk.CTkFrame(main_settings, fg_color="transparent")
        basic_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(basic_frame, text="⚙️ 基本设置", font=("微软雅黑", 14, "bold"),
                     text_color=THEME["gold"]).pack(anchor="w")

        grid_frame = ctk.CTkFrame(basic_frame, fg_color="transparent")
        grid_frame.pack(fill="x", pady=5)
        grid_frame.grid_columnconfigure(0, weight=0, minsize=80)
        grid_frame.grid_columnconfigure(1, weight=1)
        grid_frame.grid_columnconfigure(2, weight=0, minsize=70)
        grid_frame.grid_columnconfigure(3, weight=0, minsize=40)

        ctk.CTkLabel(grid_frame, text="触发热键:", font=("微软雅黑", 12, "bold"),
                     anchor="w").grid(row=0, column=0, padx=(0, 10), pady=8, sticky="w")
        self.entry_hotkey = ctk.CTkEntry(grid_frame, placeholder_text="例如: alt+q")
        self.entry_hotkey.insert(0, self.config['hotkey'])
        self.entry_hotkey.grid(row=0, column=1, padx=5, pady=8, sticky="ew")
        ctk.CTkButton(grid_frame, text="更新", width=60,
                      fg_color=THEME["gold"], hover_color=THEME["gold_hover"],
                      text_color="black", command=self.update_hotkey).grid(row=0, column=2, padx=5, pady=8)

        ctk.CTkLabel(grid_frame, text="截图范围:", font=("微软雅黑", 12, "bold"),
                     anchor="w").grid(row=1, column=0, padx=(0, 10), pady=8, sticky="w")
        self.bbox_frame = ctk.CTkFrame(grid_frame, fg_color="transparent")
        self.bbox_frame.grid(row=1, column=1, padx=5, pady=8, sticky="w")
        self.bbox_entries = []
        for val in self.config['bbox']:
            entry = ctk.CTkEntry(self.bbox_frame, width=50, justify="center")
            entry.insert(0, str(val))
            entry.pack(side="left", padx=2)
            self.bbox_entries.append(entry)

        ctk.CTkButton(grid_frame, text="保存", width=60,
                      fg_color=THEME["gold"], border_width=1, border_color=THEME["gold"],
                      text_color="black", hover_color=THEME["gold_hover"],
                      command=self.update_bbox).grid(row=1, column=2, padx=5, pady=8)

        self.help_icon = ctk.CTkLabel(grid_frame, text="❓", font=("微软雅黑", 16, "bold"), text_color=THEME["gold"])
        self.help_icon.grid(row=1, column=3, padx=(5, 0), pady=8, sticky="w")
        self.tooltip = ToolTip(self.help_icon, "设置坐标 (x1, y1, x2, y2)\n定义屏幕截图范围。")

        separator = ctk.CTkFrame(main_settings, height=2, fg_color="#444")
        separator.pack(fill="x", padx=15, pady=10)

        wm_frame = ctk.CTkFrame(main_settings, fg_color="transparent")
        wm_frame.pack(fill="x", padx=15, pady=(0, 15))
        ctk.CTkLabel(wm_frame, text="🔑 Warframe Market 账号", font=("微软雅黑", 14, "bold"),
                     text_color=THEME["gold"]).pack(anchor="w")

        wm_grid = ctk.CTkFrame(wm_frame, fg_color="transparent")
        wm_grid.pack(fill="x", pady=5)
        wm_grid.grid_columnconfigure(0, weight=0, minsize=80)
        wm_grid.grid_columnconfigure(1, weight=1)
        wm_grid.grid_columnconfigure(2, weight=0, minsize=70)
        wm_grid.grid_columnconfigure(3, weight=0, minsize=100)

        ctk.CTkLabel(wm_grid, text="WM账号:", font=("微软雅黑", 12, "bold"),
                     anchor="w").grid(row=0, column=0, padx=(0, 10), pady=8, sticky="w")

        login_input_frame = ctk.CTkFrame(wm_grid, fg_color="transparent")
        login_input_frame.grid(row=0, column=1, padx=5, pady=8, sticky="ew")
        login_input_frame.grid_columnconfigure(0, weight=1)
        login_input_frame.grid_columnconfigure(1, weight=0, minsize=40)
        login_input_frame.grid_columnconfigure(2, weight=1)

        self.wm_username = ctk.CTkEntry(login_input_frame, placeholder_text="邮箱/用户名")
        self.wm_username.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        ctk.CTkLabel(login_input_frame, text="密码:", font=("微软雅黑", 12)).grid(row=0, column=1, padx=5)
        self.wm_password = ctk.CTkEntry(login_input_frame, placeholder_text="密码", show="*")
        self.wm_password.grid(row=0, column=2, padx=(5, 0), sticky="ew")

        self.login_btn = ctk.CTkButton(wm_grid, text="登录", width=60,
                                        fg_color=THEME["gold"], text_color="black",
                                        hover_color=THEME["gold_hover"],
                                        command=self.login_wm)
        self.login_btn.grid(row=0, column=2, padx=5, pady=8)

        self.login_status = ctk.CTkLabel(wm_grid, text="未登录", text_color="red", font=("微软雅黑", 10))
        self.login_status.grid(row=0, column=3, padx=5, pady=8, sticky="w")

        btn_donate = ctk.CTkButton(self, text="☕ 觉得好用？请作者喝杯咖啡 ❤️", height=40,
                                    font=("微软雅黑", 14, "bold"), fg_color=THEME["gold"],
                                    text_color="black", hover_color=THEME["gold_hover"],
                                    corner_radius=8, command=self.show_donate_qr)
        btn_donate.pack(fill="x", padx=20, pady=(10, 5))

        ctk.CTkLabel(self, text="📊 运行日志", font=("微软雅黑", 12)).pack(anchor="w", padx=25, pady=(5, 0))
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

    def on_hotkey(self):
        with self.init_lock:
            if not self.is_ready:
                self.log("⏳ 系统加载中...")
                return
        self.update_status("Scanning...")
        threading.Thread(target=self.process_screenshot, daemon=True).start()

    # ====== 🔴 核心修复1：重写登录逻辑，强制获取 Cookie ======
    def login_wm(self):
        email = self.wm_username.get().strip()
        password = self.wm_password.get().strip()
        if not email or not password:
            tkinter.messagebox.showerror("错误", "请输入邮箱和密码")
            return

        def _do_login():
            try:
                # 1. 创建全新 Session，避免旧状态干扰
                self.http_session = requests.Session()
                self.http_session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://warframe.market/",
                    "Origin": "https://warframe.market"
                })

                self.log("📡 正在握手 WFM 服务器...")
                
                # 2. 访问登录页面，获取初始 Cookies
                # 使用 /login 页面比首页更容易触发 Set-Cookie
                resp_init = self.http_session.get("https://warframe.market/login", timeout=15)
                
                # 3. 提取 CSRF Token
                # 优先从 session.cookies 获取
                csrf_token = self.http_session.cookies.get("wfm_csrf")
                
                # 如果 session 里没有，尝试暴力解析 Header (应对特殊网络环境)
                if not csrf_token and 'Set-Cookie' in resp_init.headers:
                    match = re.search(r'wfm_csrf=([^;]+)', resp_init.headers['Set-Cookie'])
                    if match:
                        csrf_token = match.group(1)
                        self.log("⚠️ 暴力提取 Token 成功")

                if not csrf_token:
                    self.log("⚠️ 未获取到 CSRF Token，尝试通过 API 预检获取...")
                    # 备选方案：访问 API 节点
                    self.http_session.get("https://api.warframe.market/v1/items", timeout=10)
                    csrf_token = self.http_session.cookies.get("wfm_csrf")

                if not csrf_token:
                    self.log("❌ 致命错误：无法获取 CSRF Token，登录中止")
                    self.after(0, lambda: tkinter.messagebox.showerror("错误", "网络环境不支持，无法获取安全令牌"))
                    return

                self.log("✅ Token 获取成功，正在验证...")

                # 4. 构造登录请求
                login_url = "https://api.warframe.market/v1/auth/signin"
                payload = {"email": email, "password": password}
                
                # 更新 Header，必须带上 x-csrftoken
                self.http_session.headers.update({
                    "x-csrftoken": csrf_token,
                    "Content-Type": "application/json"
                })
                
                resp = self.http_session.post(login_url, json=payload, timeout=15)
                
                if resp.status_code == 200:
                    token = resp.headers.get("Authorization")
                    user_data = resp.json().get("payload", {}).get("user", {})
                    user_name = user_data.get("ingame_name") or "User"
                    
                    if token:
                        self.wm_auth_token = token
                        self.wm_logged_in = True
                        self.login_status.configure(text=f"已登录: {user_name}", text_color="green")
                        self.log(f"✅ 登录成功！用户: {user_name}")
                        
                        # 固化 Token 到 Header，后续请求通用
                        self.http_session.headers.update({"Authorization": token})
                    else:
                        self.log("❌ 登录成功但未返回 Token")
                else:
                    self.log(f"❌ 登录失败: {resp.status_code}")
                    self.log(f"Server Msg: {resp.text}")
                    self.after(0, lambda: tkinter.messagebox.showerror("登录失败", "账号或密码错误"))
                    
            except Exception as e:
                self.log(f"❌ 登录异常: {e}")
                
        threading.Thread(target=_do_login, daemon=True).start()

    def _get_item_id_precise(self, url_name):
        try:
            self.log(f"🔍 获取物品ID: {url_name}")
            url = f"https://api.warframe.market/v1/items/{url_name}"
            # 使用已初始化的 session (如果已登录) 或者 create new request
            if self.http_session:
                resp = self.http_session.get(url, timeout=10)
            else:
                resp = requests.get(url, headers={"Platform": "pc"}, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                item_id = data['payload']['item']['id']
                return item_id
            else:
                self.log(f"⚠️ 获取物品详情失败 (HTTP {resp.status_code})")
                return None
        except Exception as e:
            self.log(f"❌ 获取物品ID异常: {e}")
            return None

    def _create_wm_order(self, item_name, url_name, price):
        if not self.wm_logged_in or not self.http_session:
            tkinter.messagebox.showerror("未登录", "请先登录")
            return False

        try:
            item_id = self._get_item_id_precise(url_name)
            if not item_id:
                self.log("❌ 无法获取物品ID")
                return False

            order_url = "https://api.warframe.market/v1/profile/orders"
            payload = {
                "item_id": item_id,
                "order_type": "sell",
                "platinum": int(price),
                "quantity": 1,
                "visible": True,
                "rank": None 
            }
            
            # Session 中已经包含了 CSRF Token 和 Authorization，直接 POST 即可
            resp = self.http_session.post(order_url, json=payload, timeout=10)

            if resp.status_code == 200:
                self.log(f"✅ 上架成功！{item_name} -> {price}p")
                return True
            else:
                self.log(f"❌ 上架失败 (HTTP {resp.status_code}): {resp.text}")
                return False

        except Exception as e:
            self.log(f"❌ 上架异常: {e}")
            return False

    def _show_sell_dialog(self, item_name, url_name):
        if not self.wm_logged_in:
            if tkinter.messagebox.askyesno("提示", "需先登录 WM 账号，是否现在登录？"):
                return
            return

        price = tkinter.simpledialog.askstring("上架 WM", f"上架: {item_name}\n请输入单价(白金):", parent=self)
        if price and price.strip().isdigit():
            threading.Thread(target=lambda: self._create_wm_order(item_name, url_name, price), daemon=True).start()

    def fetch_price_hybrid(self, url_name):
        mem_key = url_name.replace("_", "").lower().strip()
        found_price = 0
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
            return f"⚡ 均价: {found_price} P", True

        api_url = f"https://api.warframe.market/v1/items/{url_name}/statistics"
        try:
            resp = requests.get(api_url, headers={"Platform": "pc"}, timeout=5)
            if resp.status_code == 200:
                stats = resp.json()['payload']['statistics_closed']['48hours']
                if stats:
                    real_price = stats[-1].get('avg_price', 0)
                    if real_price > 0: return f"☁️ 均价: {real_price} P", False
        except: pass
        return None, False

    def show_overlay(self, title, content, is_fast, url_name, index=0):
        def _show():
            top = tk.Toplevel(self)
            top.overrideredirect(True)
            top.attributes('-topmost', True)
            top.attributes('-alpha', 0.90)
            top.config(bg=THEME["bg"])

            win_w, win_h = 360, 130
            screen_h = self.winfo_screenheight()
            center_y = screen_h * 0.4
            start_y = center_y + (index * 140) 

            hidden_x, target_x = -win_w - 20, 30
            top.geometry(f"{win_w}x{win_h}+{hidden_x}+{int(start_y)}")

            main_frame = tk.Frame(top, bg=THEME["card_bg"])
            main_frame.pack(fill="both", expand=True, padx=2, pady=2)
            tk.Frame(main_frame, bg=THEME["gold"], width=8).pack(side="left", fill="y")

            content_frame = tk.Frame(main_frame, bg=THEME["card_bg"], padx=15)
            content_frame.pack(side="left", fill="both", expand=True)

            tk.Label(content_frame, text=title, fg=THEME["gold"], bg=THEME["card_bg"],
                     font=("微软雅黑", 13, "bold"), anchor="w").pack(fill="x", pady=(10, 0))
            
            fg_col = THEME["fast_text"] if is_fast else "white"
            tk.Label(content_frame, text=content, fg=fg_col, bg=THEME["card_bg"],
                     font=("Arial", 12), anchor="w").pack(fill="x")

            btn_frame = tk.Frame(content_frame, bg=THEME["card_bg"])
            btn_frame.pack(fill="x", pady=5)
            
            sell_cmd = lambda: self.after(0, lambda: self._show_sell_dialog(title, url_name))
            tk.Button(btn_frame, text="⚡ 上架 WM", bg=THEME["gold"], fg="black",
                      font=("微软雅黑", 10, "bold"), relief="flat", padx=10,
                      command=sell_cmd).pack(side="right")

            anim = {"x": hidden_x, "state": "in"}
            def _anim():
                try:
                    if not top.winfo_exists(): return
                    if anim["state"] == "in":
                        if anim["x"] < target_x:
                            anim["x"] += (target_x - anim["x"]) * 0.2 + 2
                            top.geometry(f"+{int(anim['x'])}+{int(start_y)}")
                            top.after(16, _anim)
                        else:
                            anim["state"] = "wait"
                            top.after(8000, _anim)
                    elif anim["state"] == "wait":
                        anim["state"] = "out"
                        _anim()
                    elif anim["state"] == "out":
                        if anim["x"] > hidden_x:
                            anim["x"] -= 5
                            top.geometry(f"+{int(anim['x'])}+{int(start_y)}")
                            top.after(16, _anim)
                        else:
                            top.destroy()
                except: pass
            _anim()

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
            overlay_data = []

            for line in result:
                clean_ocr = line[1].replace(" ", "").lower()
                if len(clean_ocr) < 2: continue
                
                for dict_key in self.sorted_keys:
                    if dict_key in clean_ocr:
                        base_url = self.wfm_dict[dict_key]['url_name']
                        real_name = self.wfm_dict[dict_key]['real_cn_name']
                        leftover = clean_ocr.replace(dict_key, "")
                        
                        final_suffix, cn_part = "set", "套装"
                        for cn, en in PART_MAP.items():
                            if cn in leftover:
                                final_suffix, cn_part = en, cn
                                break
                        
                        if final_suffix == "set":
                            final_url = f"{base_url}_set"
                            final_name = f"{real_name} {cn_part}"
                        else:
                            final_url = f"{base_url}_{final_suffix}"
                            final_name = f"{real_name} {cn_part}"

                        if final_name in seen_items: break

                        self.log(f"🔎 识别: {final_name}")
                        price_str, is_fast = self.fetch_price_hybrid(final_url)
                        
                        if price_str:
                            self.log(f"   -> {price_str}")
                            overlay_data.append((final_name, price_str, is_fast, final_url))
                            seen_items.add(final_name)
                            found_count += 1
                        else:
                            self.log("   -> ❌ 未找到价格")
                        break

            for idx, item in enumerate(overlay_data):
                self.show_overlay(*item, index=idx)

            self.update_status(f"完成 ({found_count}个)")

        except Exception as e:
            self.log(f"❌ Error: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    app = WFPriceHelperApp()
    app.protocol("WM_DELETE_WINDOW", lambda: (keyboard.unhook_all(), app.destroy()))
    app.mainloop()