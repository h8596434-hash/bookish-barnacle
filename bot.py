import os
import io
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from pptx import Presentation

TELEGRAM_TOKEN = os.getenv("8823906621:AAHA0JBJIaVGwVM-vM_1AMIYdBDrkWGnjCA")
GEMINI_API_KEY = os.getenv("AQ.Ab8RN6KmcFZ--4tsPlJfrAM457IOBZk_u8UL4Eep2Jawm4TeBQ")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

user_sessions = {}
user_last_text = {}

def ask_gemini(prompt_text):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    headers = {
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [{
            "parts": [{"text": prompt_text}]
        }]
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        if response.status_code == 200:
            data = response.json()
            return data['candidates'][0]['content']['parts'][0]['text']
        else:
            return "Не получилось обработать запрос, давай попробуем еще раз."
    except Exception:
        return "Сеть упала на секунду, повтори сообщение."

def create_pdf(text_content):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 50, "Материал")
    p.setFont("Helvetica", 11)
    y_position = height - 90
    
    for line in text_content.split("\n"):
        if y_position < 50:
            p.showPage()
            p.setFont("Helvetica", 11)
            y_position = height - 50
        p.drawString(50, y_position, line[:80])
        y_position -= 18

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

def create_pptx(text_content):
    prs = Presentation()
    slides_data = text_content.split("\n\n")
    for block in slides_data:
        if not block.strip():
            continue
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        title_shape = slide.shapes.title
        body_shape = slide.placeholders[1]
        lines = block.strip().split("\n")
        title_shape.text = lines[0][:50]
        if len(lines) > 1:
            body_shape.text = "\n".join(lines[1:])
        else:
            body_shape.text = "Основной материал..."
    buffer = io.BytesIO()
    prs.save(buffer)
    buffer.seek(0)
    return buffer

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    chat_id = message.chat.id
    user_sessions[chat_id] = {"step": "waiting_topic"}
    bot.reply_to(
        message, 
        "Привет! Напиши тему, по которой нужно подготовить материал, или прикрепи готовый файл (например, в .txt)."
    )

# Обработка входящих текстовых файлов (.txt)
@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    bot.reply_to(message, "Изучаю файл...")
    
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        if message.document.file_name.endswith('.txt'):
            file_text = downloaded_file.decode('utf-8')
        else:
            file_text = f"Файл: {message.document.file_name}"
        
        prompt = f"Проанализируй этот материал и сделай подробный структурированный разбор:\n{file_text}"
        ai_response = ask_gemini(prompt)
        user_last_text[chat_id] = ai_response

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("📄 Скачать PDF", callback_data="get_pdf"),
            InlineKeyboardButton("📊 Презентация PPTX", callback_data="get_pptx")
        )

        if len(ai_response) > 4000:
            for x in range(0, len(ai_response), 4000):
                bot.send_message(chat_id, ai_response[x:x+4000])
            bot.send_message(chat_id, "Готово! Выбирай формат:", reply_markup=markup)
        else:
            bot.send_message(chat_id, ai_response, reply_markup=markup)
            
    except Exception as e:
        print(f"Ошибка с файлом: {e}")
        bot.send_message(chat_id, "Не получилось прочитать этот файл. Попробуй текстовый формат.")

@bot.message_handler(func=lambda message: True)
def handle_dialog(message):
    chat_id = message.chat.id
    text = message.text

    if chat_id not in user_sessions:
        user_sessions[chat_id] = {"step": "waiting_topic"}

    session = user_sessions[chat_id]
    step = session["step"]

    if step == "waiting_topic":
        session["topic"] = text
        session["step"] = "waiting_grade"
        bot.reply_to(message, "Для какого класса или уровня это нужно?")

    elif step == "waiting_grade":
        session["grade"] = text
        session["step"] = "waiting_details"
        bot.reply_to(message, "Есть ли конкретные пожелания или требования? (или просто напиши «нет»)")

    elif step == "waiting_details":
        session["details"] = text
        
        prompt = (
            f"Создай подробный материал по заданию:\n"
            f"- Тема: {session['topic']}\n"
            f"- Класс/Уровень: {session['grade']}\n"
            f"- Пожелания: {session['details']}\n"
            f"Сделай текст структурированным, с заголовками и абзацами."
        )

        bot.reply_to(message, "Понял, готовлю материал...")
        
        ai_response = ask_gemini(prompt)
        user_last_text[chat_id] = ai_response

        user_sessions[chat_id] = {"step": "waiting_topic"}

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("📄 Скачать PDF", callback_data="get_pdf"),
            InlineKeyboardButton("📊 Презентация PPTX", callback_data="get_pptx")
        )

        if len(ai_response) > 4000:
            for x in range(0, len(ai_response), 4000):
                bot.send_message(chat_id, ai_response[x:x+4000])
            bot.send_message(chat_id, "Готово! Выбирай формат:", reply_markup=markup)
        else:
            bot.send_message(chat_id, ai_response, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    text_content = user_last_text.get(chat_id, "Текст не найден. Начни заново через /start.")

    if call.data == "get_pdf":
        bot.answer_callback_query(call.id, "Собираю PDF...")
        pdf_file = create_pdf(text_content)
        bot.send_document(chat_id, document=('document.pdf', pdf_file), caption="Держи файл в PDF.")
        
    elif call.data == "get_pptx":
        bot.answer_callback_query(call.id, "Собираю презентацию...")
        pptx_file = create_pptx(text_content)
        bot.send_document(chat_id, document=('presentation.pptx', pptx_file), caption="Держи презентацию.")

if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
