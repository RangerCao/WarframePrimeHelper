import requests
from bs4 import BeautifulSoup
import json
import re

# 灰机 Wiki 的国服/国际服/英文名称对照表
url = "https://warframe.huijiwiki.com/wiki/%E5%9B%BD%E6%9C%8D%E5%90%8D%E7%A7%B0%E5%AF%B9%E7%85%A7"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

print("🌍 正在前往 灰机Wiki 抓取【国际服中文 ↔ 英文】对照表...")

try:
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    wfm_dict = {}
    
    # 找到网页上所有的表格 (wikitable)
    tables = soup.find_all('table', class_='wikitable')
    
    for table in tables:
        # 获取这一列表头的所有文字
        ths = table.find_all('th')
        header_texts = [th.get_text(strip=True) for th in ths]
        
        # 寻找“国际服名称”和“英文名称”在第几列
        zh_idx = -1
        en_idx = -1
        
        for i, text in enumerate(header_texts):
            if "国际服" in text or text == "中文名称":
                zh_idx = i
            if "英文" in text:
                en_idx = i
                
        # 如果这个表格里同时有 中文和英文，说明是我们要的！
        if zh_idx != -1 and en_idx != -1:
            rows = table.find_all('tr')
            for row in rows[1:]: # 跳过第一行的表头
                tds = row.find_all('td')
                if len(tds) > max(zh_idx, en_idx):
                    zh_name = tds[zh_idx].get_text(strip=True)
                    en_name = tds[en_idx].get_text(strip=True)
                    
                    if zh_name and en_name:
                        # 1. 中文名处理：去空格、转小写，完美配合我们的 OCR 容错逻辑
                        clean_zh = zh_name.replace(" ", "").lower()
                        
                        # 2. 【核心黑科技】：把 Wiki 的英文名，转换成 WFM 的网址格式！
                        # 例如: "Lex Prime Receiver" -> "lex_prime_receiver"
                        # 替换空格、连字符为下划线，去掉单引号
                        url_name = en_name.lower().replace(" ", "_").replace("-", "_").replace("'", "")
                        
                        wfm_dict[clean_zh] = {
                            "url_name": url_name,
                            "real_cn_name": zh_name
                        }
                        
    # 保存为本地文件，直接覆盖我们之前那个小词典
    with open('wfm_dictionary.json', 'w', encoding='utf-8') as f:
        json.dump(wfm_dict, f, ensure_ascii=False, indent=2)
        
    print(f"🎉 简直完美！成功从 Wiki 扒取了 {len(wfm_dict)} 个物品的翻译！")
    print("已经自动将英文名转换成了 WFM 的网址格式，并生成了 wfm_dictionary.json！")
    
except Exception as e:
    print(f"❌ 抓取失败: {e}")