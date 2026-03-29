import requests
import json
import time

# ====== 🔴 在这里修改你的代理端口 ======
PROXY_URL = "http://127.0.0.1:7897"  # Clash默认7890，V2RayN默认10809
# ====================================

def generate_wfm_dict_proxy():
    print("🚀 开始生成字典 (代理模式)...")
    print(f"📡 正在通过 {PROXY_URL} 连接 Warframe Market...")
    
    target_url = "https://api.warframe.market/v2/items"
    
    # 我们需要请求两次：一次中文，一次英文，然后合并
    # 这样既能匹配 "Ash Prime"，也能匹配 "灰烬之兴 Prime" (假设有这种翻译)
    
    headers = {"Platform": "pc", "User-Agent": "Mozilla/5.0"}
    proxies = {"http": PROXY_URL, "https": PROXY_URL}
    
    final_dict = {}
    count = 0
    
    try:
        # 1. 获取中文数据
        print("   ⬇️ 正在下载中文数据...")
        headers["Language"] = "zh-hans"
        resp_cn = requests.get(target_url, headers=headers, proxies=proxies, timeout=30)
        
        # 2. 获取英文数据 (作为补充)
        print("   ⬇️ 正在下载英文数据...")
        headers["Language"] = "en"
        resp_en = requests.get(target_url, headers=headers, proxies=proxies, timeout=30)
        
        if resp_cn.status_code != 200 or resp_en.status_code != 200:
            print(f"❌ 请求失败: CN={resp_cn.status_code}, EN={resp_en.status_code}")
            return

        items_cn = resp_cn.json()['payload']['items']
        items_en = resp_en.json()['payload']['items']
        
        print(f"📦 数据获取成功，开始合并处理...")
        
        # 构建 url -> item_en 的映射
        url_to_en = {item['url_name']: item['item_name'] for item in items_en}
        
        # 遍历中文列表进行处理
        for item in items_cn:
            url_name = item.get('url_name', '')
            item_name_cn = item.get('item_name', '')
            item_name_en = url_to_en.get(url_name, item_name_cn) # 对应的英文名
            
            # 筛选 Prime 本体
            # 逻辑：必须含 Prime，且是 Set (套装)
            if "prime" in url_name and "_set" in url_name:
                
                # 提取本体 URL: "ash_prime_set" -> "ash_prime"
                base_url = url_name.replace("_set", "")
                
                # 处理中文名: "Ash Prime 套装" -> "Ash Prime"
                # 注意：有些中文名本身就是英文 (如 Ash Prime)，有些是中文 (如 伯斯顿 Prime)
                real_cn_name = item_name_cn.replace(" Set", "").replace("套装", "").strip()
                
                # 处理英文名: "Ash Prime Set" -> "Ash Prime"
                real_en_name = item_name_en.replace(" Set", "").strip()
                
                # === 关键：生成多个 Key 以提高匹配率 ===
                
                # Key 1: 中文 Key (去除空格小写) -> "伯斯顿prime"
                key_cn = real_cn_name.replace(" ", "").lower()
                final_dict[key_cn] = {
                    "url_name": base_url,
                    "real_cn_name": real_cn_name
                }
                
                # Key 2: 英文 Key (去除空格小写) -> "bratonprime"
                # 这样无论 OCR 识别出的是中文还是英文都能匹配
                key_en = real_en_name.replace(" ", "").lower()
                if key_en not in final_dict:
                    final_dict[key_en] = {
                        "url_name": base_url,
                        "real_cn_name": real_cn_name # 显示名还是用中文比较好
                    }
                
                count += 1
                # print(f"   ➕ 收录: {real_cn_name} / {real_en_name}")

        # 补漏逻辑 (针对只有蓝图没有套装的，比如新甲)
        # ... (此处省略，通常 Set 已经覆盖了绝大多数)

        # 保存
        with open('wfm_dictionary.json', 'w', encoding='utf-8') as f:
            json.dump(final_dict, f, ensure_ascii=False, indent=4)
            
        print("-" * 30)
        print(f"✅ 完美字典生成完毕！")
        print(f"📊 共收录词条: {len(final_dict)} (包含中英双语索引)")
        print(f"📂 文件已保存至: wfm_dictionary.json")

    except Exception as e:
        print(f"❌ 发生错误: {e}")
        print("💡 提示: 请检查代理端口是否正确 (Clash=7890, V2Ray=10809)")

if __name__ == "__main__":
    generate_wfm_dict_proxy()
    input("\n按回车键退出...")