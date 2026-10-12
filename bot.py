import sys
import subprocess

# Автоматическая проверка и установка библиотек при первом запуске
required_libraries = ["pyTelegramBotAPI", "requests", "reportlab"]
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
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas

# Настройки: токен телеграм-бота и твой API-ключ от Google AI Studio (начинается с AIzaSy...)
TELEGRAM_TOKEN = os.getenv("8823906621:AAHA0JBJIAvGwVM-vM_1AMIYdBDrkWGnjCA")
GEMINI_API_KEY = os.getenv("AQ.Ab8RN6JxE3en3T2p1NlSoLsjMypMNjqKuqj_bl4G5zpgOi61cw")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Прайс-лист студии в тенге
PRICE_BASE = {
    "basic": {"name": "Базовый (текст, структура)", "price": 400},
    "standard": {"name": "Стандартный (структура + акценты)", "price": 1000},
    "complex": {"name": "Сложный (глубокий анализ, детальная инфографика)", "price": 2000}
}

SYSTEM_PROMPT = f"""
Ты — профессиональный старший менеджер студии по созданию презентаций и экспертный AI-помощник.
Твоя задача — консультировать клиентов, подбирать оптимальный формат и помогать с расчетом стоимости.

АКТУАЛЬНЫЙ ПРАЙС-ЛИСТ (за 1 слайд):
1. Базовый уровень: {PRICE_BASE['basic']['price']} тенге ({PRICE_BASE['basic']['name']}).
2. Стандартный уровень: {PRICE_BASE['standard']['price']} тенге ({PRICE_BASE['standard']['name']}).
3. Сложный уровень: {PRICE_BASE['complex']['price']} тенге ({PRICE_BASE['complex']['name']}).

Инструкция для общения:
- Отвечай вежливо, развернуто и профессионально на русском языке.
- Помогай клиенту определиться с объемом работы и ценой.
- Если клиент готов заказать презентацию, направляй его на команду /presentation.
"""

def ask_gemini(user_message):
    # Автоматический перебор моделей (fallback) для защиты от ошибок 404
    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-pro"
    ]
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{SYSTEM_PROMPT}\n\nЗапрос пользователя: {user_message}"}
                ]
            }
        ]
    }

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
            response = requests.post(url, headers=headers, json=payload)
            print(f"Используем модель: {model} | Статус: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                return data['candidates'][0]['content']['parts'][0]['text']
            elif response.status_code == 404:
                continue
            else:
                print(f"Ошибка от Google ({response.status_code}): {response.text}")
                return f"Ошибка Google API ({response.status_code}). Проверь правильность ключа GEMINI_API_KEY."
        except Exception as e:
            print(f"Исключение при запросе к {model}: {e}")

    return "Не удалось найти рабочую модель Gemini API. Проверь свой GEMINI_API_KEY в Google AI Studio."

# Класс для автоматического добавления нумерации страниц в PDF
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
        self.drawString(54, 36, "Презентация подготовлена AI-студией")
        self.drawRightString(612 - 54, 36, f"Стр. {self._pageNumber} из {page_count}")
        self.restoreState()

# Словарь для сохранения шагов пользователя в процессе диалога
user_data_storage = {}

@bot.message_handler(commands=['presentation'])
def cmd_presentation(message):
    msg = bot.send_message(
        message.chat.id,
        "📊 **Создание презентации**\n\n"
        "Шаг 1 из 3: Отправьте **тему** презентации ИЛИ загрузите **свои материалы/конспект** (режим NotebookLM):"
    )
    bot.register_next_step_handler(msg, step_get_source)

def step_get_source(message):
    user_id = message.from_user.id
    user_data_storage[user_id] = {"source": message.text}
    
    msg = bot.send_message(
        message.chat.id,
        "📌 Шаг 2 из 3: Укажите **количество слайдов** (например: 5, 8, 10):"
    )
    bot.register_next_step_handler(msg, step_get_slides_count)

def step_get_slides_count(message):
    user_id = message.from_user.id
    user_data_storage[user_id]["slides_count"] = message.text

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Базовый (400 ₸)", "Стандартный (1000 ₸)", "Сложный (2000 ₸)")

    msg = bot.send_message(
        message.chat.id,
        "⚙️ Шаг 3 из 3: Выберите **уровень сложности** презентации:",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, step_finalize_and_generate)

def step_finalize_and_generate(message):
    user_id = message.from_user.id
    complexity_choice = message.text
    
    remove_markup = telebot.types.ReplyKeyboardRemove()
    
    data = user_data_storage.get(user_id, {})
    source = data.get("source", "Общая тема")
    slides_count = data.get("slides_count", "5")

    bot.send_message(message.chat.id, "⏳ Анализирую материалы и верстаю чистый PDF...", reply_markup=remove_markup)

    prompt = f"""
    Создай структурированную презентацию со следующими параметрами:
    - Материалы/Тема: {source}
    - Количество слайдов: {slides_count}
    - Уровень проработки: {complexity_choice}

    Инструкция:
    - Если передан текст или конспект, опирайся строго на него (режим NotebookLM).
    - Если это общая тема, раскрой её подробно, используя общие знания.
    - Подготовь ровно столько слайдов, сколько запрошено.

    Верни результат СТРОГО в формате JSON без дополнительного текста и без markdown-разметки (без ```json), со следующей структурой:
    {{
      "title": "Главное название презентации",
      "subtitle": "Подзаголовок или описание",
      "slides": [
        {{
          "slide_title": "Заголовок слайда", 
          "content": "Подробный структурированный текст или пункты слайда."
        }}
      ]
    }}
    """

    try:
        raw_response = ask_gemini(prompt)
        clean_json = raw_response.replace("```json", "").replace("```", "").strip()
        parsed_data = json.loads(clean_json)

        file_path = f"presentation_{user_id}.pdf"
        doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
        
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=24,
            leading=28,
            textColor=colors.HexColor('#1A365D'),
            spaceAfter=10
        )
        
        subtitle_style = ParagraphStyle(
            'DocSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=13,
            leading=17,
            textColor=colors.HexColor('#4A5568'),
            spaceAfter=25
        )

        slide_title_style = ParagraphStyle(
            'SlideTitle',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=15,
            leading=19,
            textColor=colors.HexColor('#2B6CB0'),
            spaceBefore=15,
            spaceAfter=8
        )
        
        body_style = ParagraphStyle(
            'SlideBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=11,
            leading=16,
            textColor=colors.HexColor('#2D3748'),
            spaceAfter=15
        )

        story = []

        story.append(Paragraph(parsed_data.get("title", source), title_style))
        story.append(Paragraph(parsed_data.get("subtitle", f"Сложность: {complexity_choice}"), subtitle_style))
        story.append(Spacer(1, 10))

        for idx, item in enumerate(parsed_data.get("slides", []), start=1):
            s_title = f"{idx}. {item.get('slide_title', 'Слайд')}"
            story.append(Paragraph(s_title, slide_title_style))
            story.append(Paragraph(item.get("content", ""), body_style))
            story.append(Spacer(1, 8))

        doc.build(story, canvasmaker=NumberedCanvas)

        with open(file_path, 'rb') as doc_file:
            bot.send_document(message.chat.id, doc_file, caption="✅ Ваша профессиональная PDF-презентация готова!")

        os.remove(file_path)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Не удалось сформировать PDF. Ошибка: {e}")

# Обработка всех остальных текстовых сообщений (диалог с менеджером)
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    reply = ask_gemini(message.text)
    bot.reply_to(message, reply)

print("Бот успешно запущен на ПК и ожидает сообщения...")
bot.polling(none_stop=True)
