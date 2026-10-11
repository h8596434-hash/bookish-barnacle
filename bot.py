import telebot
import requests

TELEGRAM_BOT_TOKEN = ""
GEMINI_API_KEY = ""

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Словарь для хранения истории сообщений каждого пользователя
# Ключ — ID чата, Значение — список сообщений
chats_history = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    # Очищаем историю при новом старте
    chats_history[chat_id] = []
    bot.reply_to(message, "Привет! Я твой ИИ-агент на базе Gemini с поддержкой памяти чата. Напиши мне что-нибудь!")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    user_text = message.text
    bot.send_chat_action(chat_id, 'typing')
    
    # Инициализируем историю для чата, если её еще нет
    if chat_id not in chats_history:
        chats_history[chat_id] = []
    
    # Добавляем сообщение пользователя в историю
    chats_history[chat_id].append({
        "role": "user",
        "parts": [{"text": user_text}]
    })
    
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={GEMINI_API_KEY.strip()}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Передаем всю накопленную историю диалога в Gemini
        data = {
            "contents": chats_history[chat_id]
        }
        
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        
        if "error" in result:
            error_msg = result["error"].get("message", "Неизвестная ошибка API")
            bot.reply_to(message, f"Ошибка Gemini API: {error_msg}")
        elif "candidates" in result:
            ai_reply = result['candidates'][0]['content']['parts'][0]['text']
            
            # Добавляем ответ модели в историю чата, чтобы бот помнил, что он ответил
            chats_history[chat_id].append({
                "role": "model",
                "parts": [{"text": ai_reply}]
            })
            
            bot.reply_to(message, ai_reply)
        else:
            bot.reply_to(message, f"Получен странный ответ от сервера: {result}")
            
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка в коде: {e}")

if __name__ == "__main__":
    print("Бот с памятью чата запущен и ждет сообщения...")
    bot.infinity_polling()
