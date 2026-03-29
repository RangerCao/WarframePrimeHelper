from bs4 import BeautifulSoup
import json

print("📂 正在解析本地的 wiki.html 文件...")

try:
    # 1. 不连网了！直接读取刚才保存到本地的网页源代码
    with open('wiki.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
        
    soup = BeautifulSoup(html_content, 'html.parser')
    wfm_dict = {}
    
    # 2. 寻找所有的表格
    tables = soup.find_all('table', class_='wikitable')
    print(f"🔍 在网页中找到了 {len(tables)} 个数据表格。")
    
    for table in tables:
        # 获取表头
        ths = table.find_all('th')
        header_texts = [th.get_text(strip=True) for th in ths]
        
        zh_idx = -1
        en_idx = -1
        
        # 智能寻找“国际服”和“英文”所在的列数
        for i, text in enumerate(header_texts):
            if "国际服" in text or text == "中文名称":
                zh_idx = i
            if "英文" in text:
                en_idx = i
                
        # 只要找到了包含中英文的表格，就开始提取
        if zh_idx != -1 and en_idx != -1:
            rows = table.find_all('tr')
            for row in rows[1:]: # 跳过第一行表头
                tds = row.find_all('td')
                if len(tds) > max(zh_idx, en_idx):
                    zh_name = tds[zh_idx].get_text(strip=True)
                    en_name = tds[en_idx].get_text(strip=True)
                    
                    if zh_name and en_name:
                        # 清洗中文名，适应我们的 OCR (去空格、转小写)
                        clean_zh = zh_name.replace(" ", "").lower()
                        
                        # 转换英文名为 WFM 网址格式 (去空格、连字符改下划线，去单引号)
                        url_name = en_name.lower().replace(" ", "_").replace("-", "_").replace("'", "")
                        
                        wfm_dict[clean_zh] = {
                            "url_name": url_name,
                            "real_cn_name": zh_name
                        }
                        
    # 3. 生成最终的完美词典
    with open('wfm_dictionary.json', 'w', encoding='utf-8') as f:
        json.dump(wfm_dict, f, ensure_ascii=False, indent=2)
        
    print(f"\n🎉 简直完美！成功从本地文件解析了 {len(wfm_dict)} 个物品的翻译！")
    print("你的 wfm_dictionary.json 已经生成完毕！")
    print("现在你可以把 wiki.html 删掉了。")
    
except FileNotFoundError:
    print("❌ 找不到 wiki.html 文件！请确保你按 Ctrl+S 保存的网页名字对，并且放在了这个脚本同一个文件夹下！")
except Exception as e:
    print(f"❌ 解析失败: {e}")