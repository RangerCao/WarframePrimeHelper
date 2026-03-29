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

# 新增：导入 pywmapi 相关模块
import pywmapi as wm
from pywmapi.common import OrderType
from pywmapi.orders import OrderNewItem

# ====== 配置区域 ======
DEFAULT_CONFIG = {
    "hotkey": "alt+q",
    "bbox": [0, 0, 1920, 1080]
}
CONFIG_FILE = "config.json"
WFM_DICT_PATH = "wfm_dictionary.json"
QR_IMAGE_PATH = "qr.png"

# ====== 主题配色 ======
THEME = {
    "bg": "#1a1a1a",
    "card_bg": "#2b2b2b",
    "text": "#ffffff",
    "gold": "#d4af37",
    "gold_hover": "#b8952b",
    "fast_text": "#00ff7f"
}

# ====== 零件后缀映射表 ======
PART_MAP = {
    "蓝图": "blueprint",
    "总图": "blueprint",
    "机体": "chassis",
    "系统": "systems",
    "头部神经光元": "neuroptics",
    "视光器": "neuroptics",
    "枪机": "receiver",
    "枪管": "barrel",
    "枪托": "stock",
    "连接器": "link",
    "刀刃": "blade",
    "握柄": "handle",
    "握把": "handle",
    "拳套": "gauntlet",
    "圆盘": "disc",
    "饰物": "ornament",
    "弓臂": "limb",
    "上弓臂": "upper_limb",
    "下弓臂": "lower_limb",
    "弓弦": "string",
    "弓身": "grip",
    "飞翼": "harness",
    "翅膀": "wings",
    "引擎": "engine",
    "外壳": "carapace",
    "脑池": "cerebrum",
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
    """鼠标悬停显示文字提示"""
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
        self.title("Warframe 开核桃助手 v2.3 (WM一键上架版)")
        self.geometry("750x700")  # 稍微调高一点容纳登录行
        self.configure(fg_color=THEME["bg"])

        self.wfinfo_prices = {}
        self.load_config()
        self.setup_ui()

        self.is_ready = False
        self.init_lock = threading.Lock()

        # Warframe Market 登录状态
        self.wm_session = None
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
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=30)

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
                    self.log("⚠️ 收录数为 0，可能API格式有变，将使用实时查询")
            else:
                self.log(f"⚠️ 同步失败 (HTTP {resp.status_code})，将使用实时查询")
        except Exception as e:
            self.log(f"⚠️ 网络错误，将使用实时查询: {e}")

    def setup_ui(self):
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(20, 5))
        ctk.CTkLabel(self.header_frame, text="开核桃助手 v2.3 (WM一键上架版)",
                     font=("微软雅黑", 24, "bold"), text_color=THEME["gold"]).pack(side="left")
        self.status_label = ctk.CTkLabel(self.header_frame, text="Initializing...", text_color="gray")
        self.status_label.pack(side="right", anchor="s")

        # 设置主框架（热键、截图范围）
        self.settings_frame = ctk.CTkFrame(self, fg_color=THEME["card_bg"], corner_radius=10,
                                           border_width=1, border_color=THEME["gold"])
        self.settings_frame.pack(fill="x", padx=20, pady=10)

        # 列权重配置
        self.settings_frame.grid_columnconfigure(1, weight=1)
        self.settings_frame.grid_columnconfigure(2, weight=0)
        self.settings_frame.grid_columnconfigure(3, weight=0)

        # 热键行
        ctk.CTkLabel(self.settings_frame, text="触发热键:", font=("微软雅黑", 12, "bold")).grid(
            row=0, column=0, padx=15, pady=15, sticky="w")
        self.entry_hotkey = ctk.CTkEntry(self.settings_frame, placeholder_text="例如: alt+q")
        self.entry_hotkey.insert(0, self.config['hotkey'])
        self.entry_hotkey.grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkButton(self.settings_frame, text="更新", width=60,
                      fg_color=THEME["gold"], hover_color=THEME["gold_hover"],
                      text_color="black", command=self.update_hotkey).grid(row=0, column=2, padx=15)

        # 截图范围行
        ctk.CTkLabel(self.settings_frame, text="截图范围:", font=("微软雅黑", 12, "bold")).grid(
            row=1, column=0, padx=15, pady=(0, 15), sticky="w")
        self.bbox_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.bbox_frame.grid(row=1, column=1, sticky="w", padx=5, pady=(0, 15))
        self.bbox_entries = []
        for val in self.config['bbox']:
            entry = ctk.CTkEntry(self.bbox_frame, width=50, justify="center")
            entry.insert(0, str(val))
            entry.pack(side="left", padx=2)
            self.bbox_entries.append(entry)

        ctk.CTkButton(self.settings_frame, text="保存", width=60,
                      fg_color=THEME["gold"], border_width=1, border_color=THEME["gold"],
                      text_color="black", hover_color=THEME["gold_hover"],
                      command=self.update_bbox).grid(row=1, column=2, padx=15, pady=(0, 15))

        # 帮助图标
        self.help_icon = ctk.CTkLabel(self.settings_frame, text="❓",
                                       font=("微软雅黑", 16, "bold"),
                                       text_color=THEME["gold"],
                                       cursor="question_arrow")
        self.help_icon.grid(row=1, column=3, padx=(0, 15), pady=(0, 15), sticky="w")
        tooltip_text = ("设置截图区域坐标 (x1, y1, x2, y2)。\n"
                        "这些坐标定义了屏幕截图的范围。\n"
                        "你可以使用截图工具获取坐标，或手动调整。\n"
                        "确保区域包含要识别的物品名称。")
        self.tooltip = ToolTip(self.help_icon, tooltip_text)

        # ========== Warframe Market 登录区域（新行） ==========
        login_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        login_frame.grid(row=2, column=0, columnspan=4, sticky="ew", padx=15, pady=(5, 15))
        login_frame.grid_columnconfigure(0, weight=0)
        login_frame.grid_columnconfigure(1, weight=1)
        login_frame.grid_columnconfigure(2, weight=1)
        login_frame.grid_columnconfigure(3, weight=0)
        login_frame.grid_columnconfigure(4, weight=0)
        login_frame.grid_columnconfigure(5, weight=0)

        ctk.CTkLabel(login_frame, text="WM账号:", font=("微软雅黑", 12)).grid(row=0, column=0, padx=5, sticky="w")
        self.wm_username = ctk.CTkEntry(login_frame, placeholder_text="用户名/邮箱", width=140)
        self.wm_username.grid(row=0, column=1, padx=5, sticky="ew")

        ctk.CTkLabel(login_frame, text="密码:", font=("微软雅黑", 12)).grid(row=0, column=2, padx=5, sticky="w")
        self.wm_password = ctk.CTkEntry(login_frame, placeholder_text="密码", width=140, show="*")
        self.wm_password.grid(row=0, column=3, padx=5, sticky="ew")

        self.login_btn = ctk.CTkButton(login_frame, text="登录", width=60,
                                        fg_color=THEME["gold"], text_color="black",
                                        hover_color=THEME["gold_hover"],
                                        command=self.login_wm)
        self.login_btn.grid(row=0, column=4, padx=5)

        self.login_status = ctk.CTkLabel(login_frame, text="未登录", text_color="red", font=("微软雅黑", 10))
        self.login_status.grid(row=0, column=5, padx=5)

        # 捐赠按钮
        btn_donate = ctk.CTkButton(self, text="☕ 觉得好用？请作者喝杯咖啡 ❤️", height=40,
                                    font=("微软雅黑", 14, "bold"), fg_color=THEME["gold"],
                                    text_color="black", hover_color=THEME["gold_hover"],
                                    corner_radius=8, command=self.show_donate_qr)
        btn_donate.pack(fill="x", padx=20, pady=(5, 10))

        # 日志区域
        ctk.CTkLabel(self, text="📊 运行日志", font=("微软雅黑", 12)).pack(anchor="w", padx=25, pady=(0, 0))
        self.log_text = ctk.CTkTextbox(self, font=("Consolas", 12), activate_scrollbars=True)
        self.log_text.pack(fill="both", expand=True, padx=20, pady=5)
        self.log_text.configure(state="disabled")
        ctk.CTkLabel(self, text="Designed for Tenno | Designed by github@RanAway22",
                     font=("Arial", 10), text_color="#555").pack(pady=5)

    def show_donate_qr(self):
        try:
            top = ctk.CTkToplevel(self)
            top.title("感谢支持")
            top.geometry("300x380")
            top.attributes("-topmost", True)
            img_path = resource_path(QR_IMAGE_PATH)
            if not os.path.exists(img_path):
                return
            pil_image = Image.open(img_path)
            my_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(250, 250))
            ctk.CTkLabel(top, image=my_image, text="").pack(pady=(20, 10))
            ctk.CTkLabel(top, text="欢迎扫码投喂！", font=("微软雅黑", 12)).pack()
        except:
            pass

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

    def on_hotkey(self):
        with self.init_lock:
            if not self.is_ready:
                self.log("⏳ 系统加载中，请稍后再试...")
                return
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
            return f"⚡ 均价: {found_price} P", True

        headers = {"Language": "zh-hans", "Platform": "pc"}
        api_url = f"https://api.warframe.market/v1/items/{url_name}/statistics"
        try:
            resp = requests.get(api_url, headers=headers, timeout=5)
            if resp.status_code == 200:
                stats = resp.json()['payload']['statistics_closed']['48hours']
                if not stats:
                    return None, False
                real_price = stats[-1].get('avg_price', 0)
                if real_price == 0:
                    return None, False
                return f"☁️ 均价: {real_price} P", False
        except:
            pass
        return None, False

    # ---------- Warframe Market 相关功能 ----------
    def login_wm(self):
        """登录 Warframe Market"""
        username = self.wm_username.get().strip()
        password = self.wm_password.get().strip()

        if not username or not password:
            tkinter.messagebox.showerror("错误", "请输入用户名和密码")
            return

        try:
            # 使用 pywmapi 登录
            self.wm_session = wm.auth.signin(username, password)
            self.wm_logged_in = True
            self.login_status.configure(text="已登录", text_color="green")
            self.log(f"✅ 已登录 Warframe Market: {username}")
        except Exception as e:
            self.log(f"❌ 登录失败: {e}")
            tkinter.messagebox.showerror("登录失败", f"无法登录 Warframe Market: {e}")

    def _get_item_id_by_url_name(self, url_name):
        """
        根据 url_name 获取物品的 item_id (用于创建订单)
        注意：pywmapi 的返回值可能随版本变化，需根据实际情况调整
        """
        try:
            # items.get_item 返回物品详情
            item_info = wm.items.get_item(url_name)
            # 假设 item_info 包含 'id' 字段（需要验证）
            # 如果不存在，可能需要从 item_info['item']['id'] 获取
            # 这里给出一个保守的获取方式
            if isinstance(item_info, dict):
                # 尝试常见路径
                if 'id' in item_info:
                    return item_info['id']
                elif 'item' in item_info and isinstance(item_info['item'], dict) and 'id' in item_info['item']:
                    return item_info['item']['id']
            # 如果无法获取，返回 None
            self.log(f"⚠️ 无法解析物品ID: {url_name}, 返回数据结构: {item_info}")
            return None
        except Exception as e:
            self.log(f"❌ 获取物品ID失败: {e}")
            return None

    def _create_wm_order(self, item_name, url_name, price):
        """在 Warframe Market 创建出售订单"""
        if not self.wm_logged_in:
            tkinter.messagebox.showerror("未登录", "请先登录 Warframe Market")
            return False

        try:
            # 1. 获取物品ID
            item_id = self._get_item_id_by_url_name(url_name)
            if not item_id:
                self.log(f"❌ 无法获取物品ID，上架失败: {url_name}")
                return False

            # 2. 创建订单对象（出售，数量1，公开）
            new_order = OrderNewItem(
                item_id=item_id,
                order_type=OrderType.sell,
                platinum=price,
                quantity=1,
                visible=True
            )

            # 3. 提交订单
            result = wm.orders.add_order(self.wm_session, new_order)
            self.log(f"✅ 订单创建成功: {item_name} {price}p")
            # 可选：设置在线状态
            self._set_online_status(True)
            return True

        except Exception as e:
            self.log(f"❌ 创建订单失败: {e}")
            return False

    def _set_online_status(self, online=True):
        """设置在线状态（让买家能看到你的订单）"""
        try:
            status = "online" if online else "invisible"
            wm.profile.set_online_status(self.wm_session, status)
            self.log(f"📡 在线状态已设置为: {status}")
        except Exception as e:
            self.log(f"⚠️ 设置在线状态失败: {e}")

    def _show_sell_dialog(self, item_name, url_name):
        """弹出价格输入对话框，并调用 WM 上架"""
        # 检查是否已登录
        if not self.wm_logged_in:
            result = tkinter.messagebox.askyesno("未登录",
                                                 "发布到 Warframe Market 需要登录账号。\n是否现在登录？")
            if result:
                self.login_wm()
                if not self.wm_logged_in:
                    return
            else:
                return

        # 输入价格
        price = tkinter.simpledialog.askstring("上架价格",
                                                f"请输入 {item_name} 的出售价格：",
                                                parent=self, initialvalue="")
        if price and price.strip():
            try:
                p = int(price.strip())
                if p <= 0:
                    self.log("❌ 价格必须为正整数")
                    return

                # 发布到 WM
                success = self._create_wm_order(item_name, url_name, p)

                if success:
                    # 同时复制交易文本到剪贴板（方便手动发送）
                    text = f"WTS {item_name} {p}p"
                    self.clipboard_clear()
                    self.clipboard_append(text)
                    self.log(f"✅ 已复制交易文本到剪贴板: {text}")
            except ValueError:
                self.log("❌ 价格必须是整数")

    # ---------- 弹窗显示 ----------
    def show_overlay(self, title, content, is_fast, url_name, index=0):
        def _show():
            top = tk.Toplevel(self)
            top.overrideredirect(True)
            top.attributes('-topmost', True)
            top.attributes('-alpha', 0.90)
            top.config(bg=THEME["bg"])

            win_w, win_h = 360, 130  # 高度增加以容纳按钮

            screen_h = self.winfo_screenheight()
            center_y = screen_h * 0.4
            start_y_base = center_y - (len(self.overlay_items_buffer) * 100 / 2)
            start_y = start_y_base + (index * 100)

            hidden_x, target_x = -win_w - 20, 30
            top.geometry(f"{win_w}x{win_h}+{hidden_x}+{int(start_y)}")

            main_frame = tk.Frame(top, bg=THEME["card_bg"])
            main_frame.pack(fill="both", expand=True, padx=2, pady=2)
            strip = tk.Frame(main_frame, bg=THEME["gold"], width=8)
            strip.pack(side="left", fill="y")

            content_frame = tk.Frame(main_frame, bg=THEME["card_bg"], padx=15)
            content_frame.pack(side="left", fill="both", expand=True)

            tk.Label(content_frame, text=title, fg=THEME["gold"], bg=THEME["card_bg"],
                     font=("微软雅黑", 13, "bold"), anchor="w").pack(fill="x", pady=(15, 3))
            text_color = THEME["fast_text"] if is_fast else "white"
            tk.Label(content_frame, text=content, fg=text_color, bg=THEME["card_bg"],
                     font=("Arial", 12), anchor="w").pack(fill="x")

            # 上架按钮
            btn_frame = tk.Frame(content_frame, bg=THEME["card_bg"])
            btn_frame.pack(fill="x", pady=(5, 5))
            sell_btn = tk.Button(btn_frame, text="⚡上架WM", bg=THEME["gold"], fg="black",
                                 font=("微软雅黑", 10), relief=tk.FLAT,
                                 command=lambda: self.after(0, lambda t=title, u=url_name: self._show_sell_dialog(t, u)))
            sell_btn.pack(side="right")

            # 动画部分（与之前相同）
            anim_data = {"curr_x": hidden_x, "state": "in"}

            def animate():
                try:
                    if not top.winfo_exists():
                        return
                except:
                    return
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
            self.overlay_items_buffer = []  # 存储 (名称, 价格字符串, 是否极速, url_name)

            for line in result:
                clean_ocr = line[1].replace(" ", "").lower()
                if len(clean_ocr) < 2:
                    continue
                for dict_key in self.sorted_keys:
                    if dict_key in clean_ocr:
                        base_url = self.wfm_dict[dict_key]['url_name']
                        real_name = self.wfm_dict[dict_key]['real_cn_name']
                        leftover = clean_ocr.replace(dict_key, "")
                        final_suffix, cn_part_name = "set", ""
                        for cn, en in PART_MAP.items():
                            if cn in leftover:
                                final_suffix, cn_part_name = en, cn
                                break
                        final_url = f"{base_url}_set" if final_suffix == "set" else f"{base_url}_{final_suffix}"
                        final_name = f"{real_name} 套装" if final_suffix == "set" else f"{real_name} {cn_part_name}"
                        if final_name in seen_items:
                            break

                        self.log(f"🔎 识别: {final_name} -> {final_url}")
                        price_str, is_fast = self.fetch_price_hybrid(final_url)
                        if price_str:
                            self.log(f"   -> {price_str}")
                            self.overlay_items_buffer.append((final_name, price_str, is_fast, final_url))
                            seen_items.add(final_name)
                            found_count += 1
                        else:
                            self.log("   -> ❌ 未找到价格数据")
                        break

            for idx, (name, price, is_fast, url) in enumerate(self.overlay_items_buffer):
                self.show_overlay(name, price, is_fast, url, index=idx)

            msg = f"完成 (找到 {found_count} 个)" if found_count else "未匹配到物品"
            self.update_status(msg)
            self.log(msg)

        except Exception as e:
            self.log(f"❌ Error: {e}")


if __name__ == "__main__":
    app = WFPriceHelperApp()
    app.protocol("WM_DELETE_WINDOW", lambda: (keyboard.unhook_all(), app.destroy()))
    app.mainloop()