import requests

class TelegramNotifier:
    def __init__(self, bot_token: str = "8415178136:AAFQtIujZJKtluwfQncbC-3ailAxscR3-aM", chat_id: str = "7945684367"):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def send_message(self, message: str) -> bool:
        payload = {
            "chat_id": self.chat_id,
            "text": message
        }
        try:
            response = requests.post(self.api_url, data=payload, timeout=10)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            print(f"Failed to send Telegram message: {e}")
            return False
