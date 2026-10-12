import sys
import subprocess

# Автоматическая проверка и установка библиотек при старте
required_libraries = ["pyTelegramBotAPI", "requests", "reportlab", "python-pptx"]
for lib in required_libraries:
    try:
        __import__(lib)
    except ImportError:
        print(f"Библиотека {lib} не найдена. Устанавливаем...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

import os
import json
import telebot
import requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from pptx import Presentation

# Токены из переменных окружения (Railway / Render)
TELEGRAM_TOKEN = os.environ.get("8823906621:AAHA0JBJIaVGwVM-vM_1AMIYdBDrkWGnjCA")
GEMINI_API_KEY = os.environ.get("AQ.Ab8RN6KmcFZ--4tsPlJfrAM457IOBZk_u8UL4Eep2Jawm4TeBQ")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Функция обращения к Gemini с автоподбором актуальной модели
def ask_gemini(prompt_text):
    models_to_try = [
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-pro"
    ]
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{
            "parts": [{"text": prompt_text}]
        }]
    }

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                return data['candidates'][0]['content']['parts'][0]['text']
            elif response.status_code == 404:
                continue
        except Exception:
            pass

    return "Слушай, сейчас не получается обработать запрос, давай еще раз попробуем."

# Нумерованный холст для PDF
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            super().showPage()
        super().save()

    def draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#718096"))
        self.drawString(54, 36, "Материал подготовлен ассистентом")
        self.drawRightString(612 - 54, 36, f"Стр. {self._pageNumber} из {page_count}")
        self.restoreState()

# Генератор PDF
def create_pdf(parsed_data, source_topic):
    file_path = f"document.pdf"
    doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=22, leading=26, textColor=colors.HexColor('#1A365D'), spaceAfter=10)
    subtitle_style = ParagraphStyle('DocSubtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=12, leading=16, textColor=colors.HexColor('#4A5568'), spaceAfter=20)
    slide_title_style = ParagraphStyle('SlideTitle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=14, leading=18, textColor=colors.HexColor('#2B6CB0'), spaceBefore=12, spaceAfter=6)
    body_style = ParagraphStyle('SlideBody', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=14, textColor=colors.HexColor('#2D3748'), spaceAfter=10)

    story = []
    story.append(Paragraph(parsed_data.get("title", source_topic), title_style))
    story.append(Paragraph(parsed_data.get("subtitle", "Подробный разбор материала"), subtitle_style))
    story.append(Spacer(1, 10))

    for idx, item in enumerate(parsed_data.get("slides", []), start=1):
        s_title = f"{idx}. {item.get('slide_title', 'Раздел')}"
        story.append(Paragraph(s_title, slide_title_style))
        story.append(Paragraph(item.get("content", ""), body_style))
        story.append(Spacer(1, 6))

    doc.build(story, canvasmaker=NumberedCanvas)
    return file_path

# Генератор PPTX
def create_pptx(parsed_data):
    prs = Presentation()
    slides_data = parsed_data.get("slides", [])
    
    for item in slides_data:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        title_shape = slide.shapes.title
        body_shape = slide.placeholders[1]
        
        title_shape.text = item.get('slide_title', 'Слайд')[:50]
        body_shape.text = item.get('content', '')

    file_path = "presentation.pptx"
    prs.save(file_path)
    return file_path

# Хранилище сессий пользователей
user_sessions = {}
user_last_data = {}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    chat_id = message.chat.id
    user_sessions[chat_id] = {"step": "waiting_topic"}
    bot.reply_to(message, "Привет! Напиши тему, по которой нужно подготовить материал, или прикрепи текстовый файл (.txt).")

# Обработка файлов (.txt)
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
        
        prompt = f"""
        Проанализируй этот материал и создай подробную структуру для документа/презентации:
        {file_text}

        Верни результат СТРОГО в формате JSON без markdown-разметки (без ```json), со структурой:
        {{
          "title": "Главное название",
          "subtitle": "Краткое описание",
          "slides": [
            {{
              "slide_title": "Заголовок раздела", 
              "content": "Подробный текст или пункты."
            }}
          ]
        }}
        """
        
        raw_response = ask_gemini(prompt)
        clean_json = raw_response.replace("```json", "").replace("```", "").strip()
        parsed_data = json.loads(clean_json)
        
        user_last_data[chat_id] = {"parsed": parsed_data, "topic": "Материал из файла"}

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("📄 Скачать PDF", callback_data="get_pdf"),
            InlineKeyboardButton("📊 Скачать PPTX", callback_data="get_pptx")
        )
        bot.send_message(chat_id, "Материал изучен и структурирован. Выбирай формат:", reply_markup=markup)
        
    except Exception as e:
        bot.send_message(chat_id, "Не получилось обработать этот файл. Попробуй текстовый формат (.txt).")

# Пошаговый диалог (опросник)
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
        
        prompt = f"""
        Создай структурированный материал по заданию:
        - Тема: {session['topic']}
        - Класс/Уровень: {session['grade']}
        - Пожелания: {session['details']}

        Верни результат СТРОГО в формате JSON без markdown-разметки (без ```json), со структурой:
        {{
          "title": "{session['topic']}",
          "subtitle": "Уровень: {session['grade']}",
          "slides": [
            {{
              "slide_title": "Заголовок блока/слайда", 
              "content": "Подробный текст."
            }}
          ]
        }}
        """

        bot.reply_to(message, "Готовлю материал...")
        
        raw_response = ask_gemini(prompt)
        
        try:
            clean_json = raw_response.replace("```json", "").replace("```", "").strip()
            parsed_data = json.loads(clean_json)
            user_last_data[chat_id] = {"parsed": parsed_data, "topic": session["topic"]}
            
            user_sessions[chat_id] = {"step": "waiting_topic"}

            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("📄 Скачать PDF", callback_data="get_pdf"),
                InlineKeyboardButton("📊 Скачать PPTX", callback_data="get_pptx")
            )
            bot.send_message(chat_id, "Всё готово! Выбирай формат файла:", reply_markup=markup)
            
        except Exception:
            bot.send_message(chat_id, "Что-то пошло не так при формировании. Давай попробуем заново через /start.")
            user_sessions[chat_id] = {"step": "waiting_topic"}

# Обработка кнопок скачивания
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    data = user_last_data.get(chat_id)

    if not data:
        bot.answer_callback_query(call.id, "Данные устарели. Начни заново через /start.")
        return

    parsed_data = data["parsed"]
    topic = data["topic"]

    if call.data == "get_pdf":
        bot.answer_callback_query(call.id, "Собираю PDF...")
        file_path = create_pdf(parsed_data, topic)
        with open(file_path, 'rb') as f:
            bot.send_document(chat_id, f, caption="Держи готовый PDF-документ.")
        os.remove(file_path)
        
    elif call.data == "get_pptx":
        bot.answer_callback_query(call.id, "Собираю презентацию...")
        file_path = create_pptx(parsed_data)
        with open(file_path, 'rb') as f:
            bot.send_document(chat_id, f, caption="Держи готовую презентацию PPTX.")
        os.remove(file_path)

if __name__ == "__main__":
    print("Бот успешно запущен и ждет сообщения...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
