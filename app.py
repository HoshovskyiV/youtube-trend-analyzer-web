from flask import Flask, request, jsonify, render_template
import os
import json
import time
import logging
import google.generativeai as genai  # SDK для Gemini API
from flask_cors import CORS
from retry import retry
import requests
from bs4 import BeautifulSoup
import random
import re

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TrendAnalyzer")

class GoogleTrendsClient:
    """
    Клієнт для отримання трендових пошуків через скрапінг Google Trends
    """
    def __init__(self, language='uk', geo='UA'):
        """
        Ініціалізація клієнта для скрапінгу Google Trends

        :param language: мова (default: 'uk' - українська)
        :param geo: регіон (default: 'UA' - Україна)
        """
        self.language = language
        self.geo = geo
        
        # Джерела для скрапінгу Google Trends з різними регіонами та мовами
        self.scraping_sources = [
            # Українські тренди
            "https://trends.google.com/trends/trendingsearches/daily?geo=UA&hl=uk",
            "https://trends.google.com/trends/trendingsearches/realtime?geo=UA&hl=uk&category=all",
            
            # Додаємо інші регіони, але з українською мовою інтерфейсу
            "https://trends.google.com/trends/trendingsearches/daily?geo=RU&hl=uk",
            "https://trends.google.com/trends/trendingsearches/daily?geo=PL&hl=uk",
            "https://trends.google.com/trends/trendingsearches/daily?geo=US&hl=uk",
            "https://trends.google.com/trends/trendingsearches/daily?geo=GB&hl=uk",
            "https://trends.google.com/trends/trendingsearches/daily?geo=DE&hl=uk",
            
            # Глобальні тренди з українською мовою
            "https://trends.google.com/trends/trendingsearches/daily?geo=&hl=uk",
            
            # Тренди для суміжних категорій
            "https://trends.google.com/trends/trendingsearches/daily?geo=UA&hl=uk&category=b",  # Бізнес
            "https://trends.google.com/trends/trendingsearches/daily?geo=UA&hl=uk&category=e",  # Розваги
            "https://trends.google.com/trends/trendingsearches/daily?geo=UA&hl=uk&category=t",  # Технології
            "https://trends.google.com/trends/trendingsearches/daily?geo=UA&hl=uk&category=h"   # Здоров'я
        ]
        
        logger.info(f"Ініціалізовано клієнт для скрапінгу Google Trends з мовою {language} та регіоном {geo}")

    @retry(tries=5, delay=2, backoff=2)
    def get_trending_searches(self, count=20):
        """
        Отримати список трендових пошуків з Google Trends через скрапінг

        :param count: кількість трендових запитів для повернення
        :return: список трендових запитів
        """
        # Список для зберігання трендів
        all_trends = []
        
        # Скрапінг Google Trends веб-сторінок
        for url in self.scraping_sources:
            try:
                logger.info(f"Скрапінг Google Trends: {url}")
                trends = self._scrape_google_trends_url(url)
                
                if trends:
                    logger.info(f"Знайдено {len(trends)} трендів з {url}")
                    all_trends.extend(trends)
                    
                    # Якщо маємо достатньо трендів, можемо зупинитися
                    if len(all_trends) >= count * 2:  # Збираємо з запасом для фільтрації
                        break
                        
            except Exception as e:
                logger.warning(f"Помилка при скрапінгу {url}: {str(e)}")
        
        # Видаляємо дублікати і фільтруємо
        unique_trends = []
        seen = set()
        
        for trend in all_trends:
            # Нормалізуємо текст для порівняння (нижній регістр, видалення зайвих пробілів)
            normalized = re.sub(r'\s+', ' ', trend.lower().strip())
            
            if normalized not in seen and len(normalized) > 2:
                seen.add(normalized)
                unique_trends.append(trend)
        
        # Перемішуємо для різноманіття і обмежуємо кількість
        random.shuffle(unique_trends)
        result = unique_trends[:count] if len(unique_trends) > count else unique_trends
        
        # Якщо не знайдено жодного тренду, логуємо помилку
        if not result:
            logger.error("Не вдалося отримати жодного тренду з Google Trends")
        else:
            logger.info(f"Успішно отримано {len(result)} трендів з Google Trends")
            
        return result
    
    def _scrape_google_trends_url(self, url):
        """
        Скрапінг конкретного URL Google Trends
        
        :param url: URL для скрапінгу
        :return: список трендів
        """
        trends = []
        
        try:
            # Додаємо User-Agent, щоб імітувати звичайний браузер
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
                'Referer': 'https://www.google.com/'
            }
            
            # Робимо запит з збільшеним таймаутом
            response = requests.get(url, headers=headers, timeout=15)
            
            # Перевіряємо статус відповіді
            if response.status_code == 200:
                # Парсимо HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Спробуємо різні селектори, які використовуються в Google Trends
                selectors = [
                    'div.feed-item-header',  # Основний селектор
                    '.title a',              # Альтернативний селектор
                    '.feed-item .title',     # Ще один альтернативний селектор
                    '.title',                # Простий селектор для заголовків
                    'md-card .details',      # Селектор для карток
                    '.trending-searches-item',  # Селектор для трендових пошуків
                    '.details-top',          # Селектор для деталей
                    'feed-list-item .details-text', # Селектор для списку
                    'a[href*="explore"]',    # Посилання на сторінку тренду
                    '.feed-load-more-button'  # Кнопка "завантажити більше"
                ]
                
                trend_elements = []
                
                # Перебираємо селектори, поки не знайдемо тренди
                for selector in selectors:
                    trend_elements = soup.select(selector)
                    if trend_elements:
                        break
                
                # Якщо не знайшли через селектори, спробуємо витягти з JSON даних
                if not trend_elements:
                    # Шукаємо вбудовані JSON дані
                    scripts = soup.find_all('script')
                    for script in scripts:
                        script_text = script.string
                        if script_text and ('trend' in script_text.lower() or 'search' in script_text.lower()):
                            # Спроба витягти JSON
                            try:
                                # Шукаємо JSON-подібний контент
                                json_match = re.search(r'({[\s\S]*})', script_text)
                                if json_match:
                                    json_data = json.loads(json_match.group(1))
                                    # Шукаємо тренди в JSON структурі
                                    if 'items' in json_data:
                                        for item in json_data['items']:
                                            if 'title' in item:
                                                trends.append(item['title'])
                            except Exception as e:
                                logger.debug(f"Помилка витягнення JSON: {str(e)}")
                
                # Обробка елементів, знайдених через селектори
                for element in trend_elements:
                    trend_text = element.text.strip()
                    
                    # Очищаємо текст від зайвих символів
                    trend_text = re.sub(r'\d+\s*[KkMmBb]\+?\s*searches', '', trend_text)
                    trend_text = re.sub(r'\n', ' ', trend_text)
                    trend_text = re.sub(r'\s+', ' ', trend_text)
                    
                    if trend_text and len(trend_text) > 2 and len(trend_text) < 100:
                        trends.append(trend_text.strip())
                
                # Якщо селектори не спрацювали, пробуємо витягти будь-який текст з тегів h2, h3, h4
                if not trends:
                    headlines = soup.find_all(['h2', 'h3', 'h4'])
                    for headline in headlines:
                        text = headline.text.strip()
                        if text and len(text) > 3 and len(text) < 100:
                            trends.append(text)
        
        except Exception as e:
            logger.warning(f"Помилка при скрапінгу {url}: {str(e)}")
        
        return trends
    
    def _is_likely_ukrainian(self, text):
        """
        Спрощена перевірка, чи текст схожий на українську мову
        
        :param text: текст для перевірки
        :return: True якщо схожий на українську, False інакше
        """
        # Українські символи
        ukrainian_chars = set('абвгґдеєжзиіїйклмнопрстуфхцчшщьюяАБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ')
        
        # Якщо текст містить українські символи, вважаємо його українським
        text_chars = set(text.lower())
        return bool(text_chars.intersection(ukrainian_chars))
    
    def get_related_queries(self, keyword):
        """
        Отримати пов'язані запити для заданого ключового слова через додатковий скрапінг
        
        :param keyword: ключове слово для пошуку пов'язаних запитів
        :return: словник з топовими та зростаючими запитами
        """
        try:
            logger.info(f"Пошук пов'язаних запитів для '{keyword}' через Google Trends")
            
            # Формуємо URL для сторінки Google Trends з пошуком конкретного ключового слова
            encoded_keyword = requests.utils.quote(keyword)
            related_url = f"https://trends.google.com/trends/explore?geo=UA&hl=uk&q={encoded_keyword}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
                'Referer': 'https://www.google.com/'
            }
            
            response = requests.get(related_url, headers=headers, timeout=15)
            
            top_queries = []
            rising_queries = []
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Спроба знайти пов'язані запити в HTML структурі
                related_sections = soup.find_all('div', class_='related-queries')
                for section in related_sections:
                    queries = section.find_all('div', class_='queries-list')
                    if queries:
                        for query in queries:
                            query_text = query.text.strip()
                            if query_text:
                                if 'top' in section.attrs.get('class', []):
                                    top_queries.append(query_text)
                                else:
                                    rising_queries.append(query_text)
                
                # Якщо не знайшли через стандартні селектори, шукаємо в скриптах
                if not top_queries and not rising_queries:
                    scripts = soup.find_all('script')
                    for script in scripts:
                        if script.string and 'relatedQueries' in script.string:
                            try:
                                # Пошук JSON даних у скрипті
                                json_data = re.search(r'google\.visualization\.Query\.setResponse\((.*)\);', script.string)
                                if json_data:
                                    data = json.loads(json_data.group(1))
                                    if 'table' in data and 'rows' in data['table']:
                                        for row in data['table']['rows']:
                                            if 'c' in row and len(row['c']) >= 2:
                                                query_text = row['c'][0]['v']
                                                if query_text:
                                                    top_queries.append(query_text)
                            except Exception as e:
                                logger.warning(f"Помилка при витягненні JSON: {str(e)}")
            
            # Отримуємо додаткові тренди для порівняння
            additional_trends = self.get_trending_searches(count=50)
            
            # Знаходимо схожі тренди
            if not top_queries and not rising_queries:
                keyword_lower = keyword.lower()
                for trend in additional_trends:
                    trend_lower = trend.lower()
                    # Якщо тренд містить ключове слово - додаємо до топових
                    if keyword_lower in trend_lower:
                        top_queries.append(trend)
                    # Якщо ключове слово є частиною тренду - додаємо до зростаючих
                    elif any(word in trend_lower for word in keyword_lower.split()):
                        rising_queries.append(trend)
            
            logger.info(f"Знайдено {len(top_queries)} топових та {len(rising_queries)} зростаючих запитів")
            
            # Обмежуємо кількість результатів
            return {
                'top': top_queries[:5],
                'rising': rising_queries[:5]
            }
            
        except Exception as e:
            logger.error(f"Помилка при отриманні пов'язаних запитів: {str(e)}")
            # У випадку помилки повертаємо пусті списки
            return {'top': [], 'rising': []}


class TrendAnalyzer:
    def __init__(self, gemini_api_key, language='uk', region='UA'):
        """
        Ініціалізація системи аналізу трендів
        
        :param gemini_api_key: API ключ для Gemini
        :param language: мова для аналізу трендів (default: 'uk' - українська)
        :param region: регіон для аналізу (default: 'UA' - Україна)
        """
        # Налаштування Gemini API з новим SDK
        self.gemini_api_key = gemini_api_key
        genai.configure(api_key=gemini_api_key)
        
        # Ініціалізуємо клієнт для скрапінгу трендів
        self.trends_client = GoogleTrendsClient(
            language=language,
            geo=region
        )
        
        # Налаштування мови та регіону
        self.language = language
        self.region = region
        
        # Кешування трендів для зменшення кількості запитів
        self.trends_cache = {
            'trends': [],
            'timestamp': 0
        }
        
        # Ініціалізуємо модель Gemini
        self._initialize_gemini_model()
        
        logger.info("Систему аналізу трендів ініціалізовано")
    
    def _initialize_gemini_model(self):
        """
        Ініціалізація моделі Gemini з отриманням доступних моделей
        """
        try:
            # Отримуємо список доступних моделей
            # Зберігаємо список моделей, конвертуючи генератор у список
            available_models = list(genai.list_models())
            logger.info(f"Доступні моделі Gemini: {[model.name for model in available_models]}")
            
            # Шукаємо відповідну модель
            model_found = False
            
            # Спочатку шукаємо Flash-модель
            for model in available_models:
                # Шукаємо Gemini 2.0 Flash або 1.5 Flash або будь-яку Flash-модель
                if ("flash" in model.name.lower() and 
                    ("2.0" in model.name.lower() or "1.5" in model.name.lower())):
                    self.model = genai.GenerativeModel(model.name)
                    logger.info(f"Використовуємо Gemini Flash модель: {model.name}")
                    model_found = True
                    break
            
            # Якщо Flash не знайдено, шукаємо Pro-модель
            if not model_found:
                for model in available_models:
                    if ("pro" in model.name.lower() and 
                        ("2.0" in model.name.lower() or "1.5" in model.name.lower())):
                        self.model = genai.GenerativeModel(model.name)
                        logger.info(f"Використовуємо Gemini Pro модель: {model.name}")
                        model_found = True
                        break
            
            # Якщо ні Flash, ні Pro не знайдено, використовуємо першу доступну
            if not model_found and available_models:
                self.model = genai.GenerativeModel(available_models[0].name)
                logger.info(f"Використовуємо доступну Gemini модель: {available_models[0].name}")
                model_found = True
            
            if not model_found:
                raise ValueError("Не вдалося знайти доступні моделі Gemini")
                
        except Exception as e:
            logger.error(f"Помилка ініціалізації моделі Gemini: {str(e)}")
            raise
    
    def get_trending_searches(self, count=20):
        """
        Отримати трендові пошуки з кешуванням для зменшення запитів
        
        :param count: кількість трендів
        :return: список трендових запитів
        """
        # Перевіряємо, чи є актуальний кеш (не старіше 30 хвилин)
        current_time = time.time()
        cache_lifetime = 30 * 60  # 30 хвилин
        
        if (self.trends_cache['trends'] and 
            current_time - self.trends_cache['timestamp'] < cache_lifetime):
            logger.info("Використовуємо кешовані тренди")
            return self.trends_cache['trends'][:count]
        
        # Якщо кеш не актуальний, отримуємо нові тренди
        trending_searches = self.trends_client.get_trending_searches(count=count)
        
        # Оновлюємо кеш
        self.trends_cache['trends'] = trending_searches
        self.trends_cache['timestamp'] = current_time
        
        return trending_searches
    
    def get_related_queries(self, keyword):
        """
        Отримати пов'язані запити для ключового слова
        
        :param keyword: ключове слово
        :return: словник з топовими та зростаючими запитами
        """
        related_queries = self.trends_client.get_related_queries(keyword)
        return related_queries
    
    @retry(tries=3, delay=2, backoff=2)
    def generate_video_ideas(self, keyword, count=3, category=None):
        """
        Генерувати ідеї для відео на основі ключового слова
        
        :param keyword: ключове слово
        :param count: кількість ідей
        :param category: категорія (опціонально)
        :return: згенерований текст ідей
        """
        try:
            logger.info(f"Генерація {count} ідей для відео на основі '{keyword}'")
            
            # Отримання трендів для контексту
            trends = self.get_trending_searches(count=10)
            # Логуємо тренди для аналізу
            logger.info(f"Поточні тренди з Google: {trends}")
            
            trends_str = "Поточні тренди в Google Trends Україна:\n- " + "\n- ".join(trends[:5])
            
            # Отримання пов'язаних запитів для збагачення контексту
            related = self.get_related_queries(keyword)
            related_str = ""
            
            if related['top'] or related['rising']:
                related_str = "Пов'язані запити:\n"
                if related['top']:
                    related_str += "Топові: " + ", ".join(related['top'][:5]) + "\n"
                    # Логуємо для аналізу
                    logger.info(f"Пов'язані топові запити: {related['top'][:5]}")
                if related['rising']:
                    related_str += "Зростаючі: " + ", ".join(related['rising'][:5]) + "\n"
                    # Логуємо для аналізу
                    logger.info(f"Пов'язані зростаючі запити: {related['rising'][:5]}")
            
            # Формуємо промпт для Gemini з урахуванням категорії, якщо вона вказана
            category_str = f"в категорії {category}" if category else ""
            
            generation_config = {
                "temperature": 0.7,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 4096,
            }
            
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
            
            # Додаткові рекомендації для актуальних відео в Україні
            current_context = """
            Актуальний контекст для українських YouTube відео (2025 рік):
            - Війна з Росією триває, багато людей шукають практичні поради
            - Електропостачання часто нестабільне, актуальні відео про економію енергії та альтернативні джерела
            - Інфляція та економічні труднощі, популярні відео про заощадження грошей
            - Відновлення та реконструкція країни, теми будівництва, ремонту популярні
            - Зростає інтерес до української культури, мови, традицій, вітчизняних виробників
            - Велика кількість українців за кордоном шукає зв'язок з домом
            - Збільшується попит на відео про психологічну підтримку, подолання стресу, ПТСР
            - Важливі теми про освіту та можливості для молоді, працевлаштування
            """
            
            prompt = f"""
            Ти - аналітик контенту для українських YouTube блогерів. Створи {count} детальних ідей для YouTube відео українською мовою на основі РЕАЛЬНОГО пошукового запиту/тренду: "{keyword}" {category_str}.
            
            {trends_str}
            
            {related_str}
            
            {current_context}
            
            ДУЖЕ ВАЖЛИВО: Не вигадуй нові теми! Створи ідеї виключно на основі конкретного пошукового запиту "{keyword}" та пов'язаних з ним запитів, які наведені вище. Ідеї повинні відповідати на конкретні запитання/потреби користувачів, які шукають інформацію за цим запитом.
            
            Для кожної ідеї обов'язково надай:
            1. Привабливий заголовок для відео (до 60 символів), який обов'язково включає оригінальний пошуковий запит: "{keyword}"
            2. Короткий опис (до 160 символів), що добре оптимізований для SEO
            3. 5-7 ключових моментів для сценарію, з практичною користю для глядача
            4. Список із 5-8 ключових слів українською мовою для оптимізації SEO (включно з оригінальним запитом)
            5. Рекомендований формат відео (наприклад, туторіал, огляд, список, історія, тощо)
            
            Формат відповіді:
            
            ## Ідея 1: [ЗАГОЛОВОК ОБОВ'ЯЗКОВО ВКЛЮЧАЄ "{keyword}"]
            
            **Опис**: [ОПИС]
            
            **Ключові моменти**:
            - [МОМЕНТ 1]
            - [МОМЕНТ 2]
            ...
            
            **Ключові слова**: [СЛОВО1], [СЛОВО2], ..., [ОРИГІНАЛЬНИЙ ЗАПИТ]
            
            **Формат**: [ФОРМАТ]
            
            ---
            
            Переконайся, що ідеї дуже конкретні, актуальні та практичні. Відповідай на реальні потреби українців у 2025 році. Фокусуйся на практичній користі, а не загальних темах.
            """
            
            # Використовуємо SDK для генерації відповіді
            response = self.model.generate_content(
                contents=prompt,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            # Отримуємо текст відповіді
            if hasattr(response, 'candidates') and response.candidates:
                content = response.candidates[0].content.parts[0].text
            else:
                content = response.text
            
            logger.info(f"Ідеї успішно згенеровано для '{keyword}'")
            return content
            
        except Exception as e:
            logger.error(f"Помилка генерації ідей для '{keyword}': {str(e)}")
            raise

# Створення Flask додатку
app = Flask(__name__,
            static_folder='static',
            template_folder='templates')

# Налаштування CORS
CORS(app)

# Глобальна змінна для аналізатора трендів
analyzer = None

# Для Render.com ми не можемо використовувати @app.before_first_request
# оскільки це застаріла функція у Flask 2.2.x, тому створимо функцію ініціалізації
def initialize_analyzer():
    """Ініціалізація аналізатора трендів"""
    global analyzer
    # Отримуємо API ключ з змінних середовища
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    
    if not gemini_api_key:
        logger.error("GEMINI_API_KEY відсутній у змінних середовища")
        return
    
    try:
        analyzer = TrendAnalyzer(
            gemini_api_key=gemini_api_key,
            language='uk',  # Українська мова
            region='UA'     # Україна
        )
        logger.info("Аналізатор трендів ініціалізовано")
    except Exception as e:
        logger.error(f"Помилка ініціалізації аналізатора трендів: {str(e)}")

# Ініціалізуємо аналізатор при запуску
initialize_analyzer()

@app.route('/')
def index():
    """Головна сторінка"""
    return render_template('index.html')

@app.route('/api/trends', methods=['GET'])
def get_trends():
    """Отримання популярних трендів"""
    global analyzer
    
    if not analyzer:
        return jsonify({"error": "Аналізатор трендів не ініціалізовано. Перевірте GEMINI_API_KEY"}), 500
    
    try:
        count = request.args.get('count', default=10, type=int)
        trends = analyzer.get_trending_searches(count=count)
        return jsonify({"trends": trends})
    except Exception as e:
        logger.error(f"Помилка при отриманні трендів: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
def analyze_trend():
    """Аналіз тренду та генерація ідей для відео"""
    global analyzer
    
    if not analyzer:
        return jsonify({"error": "Аналізатор трендів не ініціалізовано. Перевірте GEMINI_API_KEY"}), 500
    
    try:
        data = request.json
        keyword = data.get('keyword')
        count = data.get('count', 3)
        category = data.get('category')
        
        if not keyword:
            return jsonify({"error": "Ключове слово не вказано"}), 400
        
        # Генерація ідей для відео
        ideas = analyzer.generate_video_ideas(
            keyword=keyword,
            count=count,
            category=category
        )
        
        return jsonify({
            "keyword": keyword,
            "category": category,
            "ideas": ideas
        })
    except Exception as e:
        logger.error(f"Помилка при аналізі тренду: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
