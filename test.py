import requests
search_url = "https://api.warframe.market/v1/items?search=corvas prime stock"
resp = requests.get(search_url, headers={"Language": "zh-hans"})
print(resp.json())  # 查看返回结果中是否有匹配的物品