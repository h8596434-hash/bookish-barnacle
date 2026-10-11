import os
import json
import telebot
import requests
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

# Получаем токены из системных переменных Render
TELEGRAM_TOKEN = "TELEGRAM_TOKEN"
GEMINI_API_KEY = "GEMINI_API_KEY"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# База прайса и категорий сложности в коде
PRICE_BASE = {
    "basic": {"name": "Базовый (текст, минимум дизайна)", "price": 400},
    "standard": {"name": "Стандартный (иконки, структура, графики)", "price": 1000},
    "complex": {"name": "Сложный (инфографика, дизайн с нуля)", "price": 2000}
}

SYSTEM_PROMPT = f"""
Ты — профессиональный менеджер студии по созданию презентаций и умный ассистент.
Твоя задача — общаться с клиентом, собирать информацию (тема, количество слайдов, сложность) и ориентировать по ценам.

ПРАЙС-ЛИСТ ЗА 1 СЛАЙД:
1. Базовый уровень: {PRICE_BASE['basic']['price']} тенге ({PRICE_BASE['basic']['name']}).
2. Стандартный уровень: {PRICE_BASE['standard']['price']} тенге ({PRICE_BASE['standard']['name']}).
3. Сложный уровень: {PRICE_BASE['complex']['price']} тенге ({PRICE_BASE['complex']['name']}).

Инструкция:
- Отвечай вежливо и понятно на русском языке.
- Помогай клиенту определиться с темой и ценой.
- Если клиент готов создавать презентацию, объясни, что можно запустить команду /presentation.
"""

# Функция общения с Gemini API
def ask_gemini(user_message):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{SYSTEM_PROMPT}\n\nСообщение от пользователя: {user_message}"}
                ]
            }
        ]
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json()
        return data['candidates'][0]['content']['parts'][0]['text']
    return "Произошла ошибка при обращении к искусственному интеллекту."

# Класс для добавления нумерации страниц в PDF
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
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.setFont("Helvetica", 9)
        self.setFillColorRGB(0.5, 0.5, 0.5)
        self.drawRightString(612 - 54, 36, f"Стр. {self._pageNumber} из {page_count}")

# Команда для создания презентации
@bot.message_handler(commands=['presentation'])
def start_presentation(message):
    msg = bot.send_message(
        message.chat.id, 
        "📄 **Создание презентации**\n\n"
        "Отправь мне **тему** (и бот найдет информацию сам) ИЛИ **свой текст/конспект**, по которому нужно сделать презентацию:"
    )
    bot.register_next_step_handler(msg, generate_pdf_presentation)

def generate_pdf_presentation(message):
    user_input = message.text
    bot.send_message(message.chat.id, "⏳ Обрабатываю данные и верстаю PDF-презентацию...")

    # Умный промпт: если передан текст, берем его за основу, если просто тема — берем из знаний модели
    prompt = f"""
    Создай структуру презентации на основе следующего запроса или текста:
    "{user_input}"

    Инструкция:
    - Если передан готовый текст или материалы, используй строго их.
    - Если это просто тема или название, используй свои знания для создания качественной презентации.
    
    Верни результат СТРОГО в формате JSON без какого-либо дополнительного текста и без markdown-разметки (без ```json), со следующей структурой:
    {{
      "title": "Название презентации",
      "slides": [
        {{"slide_title": "Заголовок первого слайда", "content": "Подробный текст или пункты первого слайда"}},
        {{"slide_title": "Заголовок второго слайда", "content": "Подробный текст или пункты второго слайда"}}
      ]
    }}
    """

    try:
        raw_response = ask_gemini(prompt)
        clean_json = raw_response.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)

        # Создаем PDF документ
        file_path = f"presentation_{message.chat.id}.pdf"
        doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=22,
            leading=26,
            textColor='#1a365d',
            spaceAfter=20
        )
        
        slide_title_style = ParagraphStyle(
            'SlideTitle',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=20,
            textColor='#2b6cb0',
            spaceBefore=15,
            spaceAfter=10
        )
        
        body_style = ParagraphStyle(
            'SlideBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=11,
            leading=16,
            textColor='#2d3748',
            spaceAfter=15
        )

        story = []

        # Титульный блок
        story.append(Paragraph(data.get("title", "Презентация"), title_style))
        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>Сгенерировано AI-ассистентом</b>", body_style))
        story.append(Spacer(1, 30))

        # Наполнение слайдами
        for item in data.get("slides", []):
            story.append(Paragraph(item.get("slide_title", ""), slide_title_style))
            story.append(Paragraph(item.get("content", ""), body_style))
            story.append(Spacer(1, 10))

        doc.build(story, canvasmaker=NumberedCanvas)

        # Отправка файла пользователю в Telegram
        with open(file_path, 'rb') as doc_file:
            bot.send_document(message.chat.id, doc_file, caption="✅ Ваша PDF-презентация готова!")

        # Удаление временного файла
        os.remove(file_path)

    except Exception as e:
        bot.send_message(message.chat.id, f"Не удалось собрать PDF-презентацию. Ошибка: {e}")

# Обычный текстовый диалог с ботом
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    reply = ask_gemini(message.text)
    bot.reply_to(message, reply)

print("Бот запущен и ждет сообщения...")
bot.polling(none_stop=True)
