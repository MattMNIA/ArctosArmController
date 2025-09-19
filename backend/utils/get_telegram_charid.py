import requests
TOKEN ="8415178136:AAFQtIujZJKtluwfQncbC-3ailAxscR3-aM"
url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
print(requests.get(url).json())