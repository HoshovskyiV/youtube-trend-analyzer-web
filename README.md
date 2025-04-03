# YouTube Trend Analyzer - Веб-додаток

Система для аналізу популярних трендів та генерації ідей для YouTube відео з веб-інтерфейсом.

![YouTube Trend Analyzer](https://github.com/HoshovskyiV/youtube-trend-analyzer-web/raw/main/static/img/preview.png)

## 📝 Опис проекту

Ця веб-система дозволяє:

- Автоматично аналізувати популярні пошукові запити в Google Trends
- Генерувати детальні ідеї для створення YouTube контенту
- Отримувати готові заголовки, описи та ключові слова для відео
- Працювати з українськими трендами та тематиками

## 🚀 Технології

- **Фронтенд**: HTML, CSS, JavaScript, Bootstrap
- **Бекенд**: Python, Flask
- **API**: Google Trends API, Gemini API (Google AI)
- **Розгортання**: Render.com

## 🛠️ Встановлення та запуск

### Локальний запуск

1. Клонуйте репозиторій:
   ```bash
   git clone https://github.com/HoshovskyiV/youtube-trend-analyzer-web.git
   cd youtube-trend-analyzer-web
   ```

2. Створіть віртуальне середовище:
   ```bash
   python -m venv venv
   
   # Активація на Windows
   venv\Scripts\activate
   
   # Активація на Linux/Mac
   source venv/bin/activate
   ```

3. Встановіть залежності:
   ```bash
   pip install -r requirements.txt
   ```

4. Створіть файл `.env` з вашим API ключем Gemini:
   ```
   GEMINI_API_KEY=ваш_api_ключ
   ```

5. Запустіть додаток:
   ```bash
   python app.py
   ```

6. Відкрийте браузер і перейдіть за адресою http://localhost:5000

### Розгортання на Render.com

1. Зареєструйтесь на [Render.com](https://render.com)

2. Підключіть свій GitHub акаунт до Render

3. Натисніть "New" > "Blueprint" та виберіть свій репозиторій

4. Render автоматично визначить конфігурацію з файлу `render.yaml`

5. Обов'язково додайте змінну середовища `GEMINI_API_KEY` з вашим API ключем Gemini

## 🔑 Отримання API ключів

### Gemini API (обов'язково)

1. Відвідайте [Google AI Studio](https://ai.google.dev/)
2. Створіть обліковий запис або увійдіть
3. Перейдіть до налаштувань API і отримайте API ключ

## 📁 Структура проекту

```
youtube-trend-analyzer-web/
├── static/              # Статичні файли (CSS, JS, зображення)
│   ├── css/             # Стилі CSS
│   ├── js/              # Скрипти JavaScript
│   └── img/             # Зображення
├── templates/           # HTML шаблони
├── app.py               # Основний файл додатку (Flask)
├── requirements.txt     # Залежності Python
├── Procfile             # Конфігурація для Render.com
├── render.yaml          # Blueprint для Render.com
└── README.md            # Документація проекту
```

## 🤝 Внесок у проект

Якщо ви хочете вдосконалити цей проект:

1. Створіть форк репозиторію
2. Створіть гілку для вашої функції (`git checkout -b feature/amazing-feature`)
3. Зробіть коміт ваших змін (`git commit -m 'Add some amazing feature'`)
4. Відправте у гілку (`git push origin feature/amazing-feature`)
5. Відкрийте Pull Request

## 📃 Ліцензія

Цей проект розповсюджується за ліцензією MIT. Див. файл `LICENSE` для отримання додаткової інформації.

## 📧 Контакти

Якщо у вас виникли питання, будь ласка, відкрийте issue в цьому репозиторії.
