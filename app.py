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
import pandas as pd
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
    Клієнт для отримання трендових пошуків через скрапінг
    """
    def __init__(self, language='uk', geo='UA'):
        """
        Ініціалізація клієнта для скрапінгу Google Trends

        :param language: мова (default: 'uk' - українська)
        :param geo: регіон (default: 'UA' - Україна)
        """
        self.language = language
        self.geo = geo
        
        # Потенційні джерела для скрапінгу
        self.scraping_sources = [
            "https://trends.google.com/trends/trendingsearches/daily?geo=UA&hl=uk",
            "https://trends.google.com/trends/trendingsearches/daily?geo=US&hl=uk"
        ]
        
        # Список українських новинних сайтів для скрапінгу
        self.news_sites = [
            "https://www.pravda.com.ua/",
            "https://www.unian.ua/",
            "https://tsn.ua/",
            "https://suspilne.media/",
            "https://www.bbc.com/ukrainian"
        ]
        
        logger.info(f"Ініціалізовано клієнт для скрапінгу трендів з мовою {language} та регіоном {geo}")

    @retry(tries=3, delay=2, backoff=2)
    def get_trending_searches(self, count=20):
        """
        Отримати список трендових пошуків для заданого регіону

        :param count: кількість трендових запитів для повернення
        :return: список трендових запитів
        """
        # Список для зберігання трендів
        all_trends = []
        
        # 1. Скрапінг Google Trends веб-сторінки
        try:
            logger.info("Скрапінг Google Trends веб-сторінки для України")
            scraped_trends = self._scrape_google_trends_page()
            if scraped_trends:
                logger.info(f"Скрапінг Google Trends повернув {len(scraped_trends)} трендів")
                all_trends.extend(scraped_trends)
        except Exception as e:
            logger.warning(f"Помилка при скрапінгу Google Trends: {str(e)}")
        
        # 2. Скрапінг українських новинних сайтів, якщо недостатньо трендів
        if len(all_trends) < count:
            try:
                logger.info("Скрапінг українських новинних сайтів")
                news_trends = self._scrape_news_sites()
                if news_trends:
                    logger.info(f"Скрапінг новинних сайтів повернув {len(news_trends)} трендів")
                    all_trends.extend(news_trends)
            except Exception as e:
                logger.warning(f"Помилка при скрапінгу новинних сайтів: {str(e)}")
        
        # 3. Якщо все ще недостатньо трендів, використовуємо запасний список
        if len(all_trends) < count:
            logger.info("Використовуємо запасний список питальних конструкцій")
            fallback_trends = self._get_fallback_trends()
            all_trends.extend(fallback_trends)
        
        # Видаляємо дублікати
        unique_trends = list(dict.fromkeys(all_trends))
        
        # Обмеження до заданої кількості та перемішування для різноманіття
        if len(unique_trends) > count:
            # Перемішуємо список, щоб отримати різноманітні тренди
            random.shuffle(unique_trends)
            result = unique_trends[:count]
        else:
            result = unique_trends
        
        logger.info(f"Повернено {len(result)} трендових запитів")
        return result
    
    def _scrape_google_trends_page(self):
        """
        Скрапінг Google Trends веб-сторінки для отримання трендів
        
        :return: список трендів
        """
        trends = []
        
        for url in self.scraping_sources:
            try:
                # Додаємо User-Agent, щоб імітувати звичайний браузер
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                # Робимо запит
                response = requests.get(url, headers=headers, timeout=10)
                
                # Перевіряємо статус відповіді
                if response.status_code == 200:
                    # Парсимо HTML
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Шукаємо тренди в HTML структурі
                    # Це основний селектор для трендів у Google Trends
                    trend_elements = soup.select('div.feed-item-header')
                    
                    if not trend_elements:
                        # Спробуємо альтернативні селектори, якщо структура сторінки змінилася
                        trend_elements = soup.select('.title a')
                        
                    if not trend_elements:
                        trend_elements = soup.select('.feed-item .title')
                    
                    for element in trend_elements:
                        trend_text = element.text.strip()
                        if trend_text and len(trend_text) > 2 and len(trend_text) < 100:
                            # Очищення тексту від зайвих символів
                            trend_text = re.sub(r'\d+\s*[KkMmBb]\+?\s*searches', '', trend_text).strip()
                            trend_text = re.sub(r'\n', ' ', trend_text).strip()
                            
                            if trend_text:
                                trends.append(trend_text)
                    
                    # Якщо знайшли тренди, виходимо з циклу
                    if trends:
                        break
            except Exception as e:
                logger.warning(f"Помилка при скрапінгу {url}: {str(e)}")
        
        return trends
    
    def _scrape_news_sites(self):
        """
        Скрапінг українських новинних сайтів для отримання актуальних тем
        
        :return: список трендів на основі заголовків новин
        """
        trends = []
        
        for site in self.news_sites:
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                response = requests.get(site, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    # Парсимо HTML
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Шукаємо заголовки новин
                    headlines = soup.find_all(['h1', 'h2', 'h3', 'h4'])
                    
                    for headline in headlines:
                        text = headline.text.strip()
                        if text and len(text) > 5 and len(text) < 100:
                            # Перетворюємо заголовок новини у пошуковий запит
                            # Видаляємо зайві символи
                            clean_text = re.sub(r'[^\w\s]', '', text)
                            clean_text = clean_text.strip()
                            
                            # Трансформуємо в питальну конструкцію для кращих результатів
                            if len(clean_text.split()) <= 5 and self._is_likely_ukrainian(clean_text):
                                # Для коротких заголовків додаємо питальні форми
                                trends.append(f"що таке {clean_text}")
                                trends.append(f"як {clean_text}")
                            else:
                                # Для довших заголовків використовуємо оригінальний текст
                                if self._is_likely_ukrainian(clean_text):
                                    trends.append(clean_text)
                    
                    # Якщо знайшли достатньо, виходимо з циклу
                    if len(trends) >= 30:
                        break
            except Exception as e:
                logger.warning(f"Помилка при скрапінгу {site}: {str(e)}")
        
        return trends[:30]  # Обмежуємо кількість трендів

    def _get_fallback_trends(self):
        """
        Надає запасний список трендів на випадок, якщо скрапінг не працює
        
        :return: список трендів
        """
        fallback_trends = [
            # Базові питальні слова
            "як вирішити проблему",
            "чому сталася помилка",
            "де знайти рішення",
            "коли починається",
            "що робити якщо",
            "хто допоможе",
            "скільки коштує",
            "навіщо потрібно",
            "куди звернутися",
            "звідки походить",
            "який вибрати",
            "яка найкраща програма",
            "яке рішення підійде",
            "які документи потрібні",
            
            # Поширені конструкції з "як"
            "як захиститися від кібератак",
            "як встановити захищене підключення",
            "як налаштувати VPN",
            "як використовувати Starlink",
            "як приготувати консерви",
            "як відновити пошкоджені файли",
            "як видалити шкідливе ПЗ",
            "як вибрати генератор",
            "як знайти роботу онлайн",
            "як створити резервне копіювання",
            "як заробити під час кризи",
            "як змінити налаштування безпеки",
            "як дізнатися про відключення світла",
            "як вирішити проблему з інтернетом",
            "як купити валюту",
            "як перевірити безпеку пристрою",
            
            # Актуальні для України 
            "де купити генератор",
            "скільки коштує Starlink",
            "чому не працює електрика",
            "коли буде світло",
            "як заощадити енергію",
            "що робити під час повітряної тривоги",
            "як відновити пошкоджене житло",
            "як оформити допомогу"
        ]
        return fallback_trends
    
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
        Отримати пов'язані запити для заданого ключового слова через скрапінг
        
        :param keyword: ключове слово для пошуку пов'язаних запитів
        :return: словник з топовими та зростаючими запитами
        """
        # Спробуємо знайти схожі тренди зі списку скрапінга
        try:
            logger.info(f"Пошук пов'язаних запитів для '{keyword}' через скрапінг")
            
            # Отримуємо більше трендів для пошуку
            all_trends = self._scrape_google_trends_page() + self._scrape_news_sites()
            
            # Фільтруємо тренди, які можуть бути пов'язані з ключовим словом
            related_top = []
            related_rising = []
            
            keyword_lower = keyword.lower()
            keyword_words = set(keyword_lower.split())
            
            for trend in all_trends:
                trend_lower = trend.lower()
                
                # Простий алгоритм для визначення пов'язаності:
                # 1. Якщо тренд містить ключове слово - додаємо до топових
                if keyword_lower in trend_lower:
                    related_top.append(trend)
                    continue
                
                # 2. Якщо є перетин ключових слів - додаємо до зростаючих
                trend_words = set(trend_lower.split())
                if keyword_words.intersection(trend_words):
                    related_rising.append(trend)
            
            logger.info(f"Знайдено {len(related_top)} топових та {len(related_rising)} зростаючих запитів")
            
            # Якщо знайшли достатньо пов'язаних запитів, повертаємо їх
            if related_top or related_rising:
                return {
                    'top': related_top[:5],  # Обмежуємо до 5 результатів
                    'rising': related_rising[:5]
                }
            
            # Якщо не знайшли, перетворюємо ключове слово в різні форми запитів
            generated_queries = self._generate_related_queries(keyword)
            logger.info(f"Згенеровано {len(generated_queries['top'])} пов'язаних запитів")
            
            return generated_queries
            
        except Exception as e:
            logger.error(f"Помилка при отриманні пов'язаних запитів: {str(e)}")
            # У випадку помилки генеруємо фіктивні дані
            return self._generate_related_queries(keyword)
    
    def _generate_related_queries(self, keyword):
        """
        Генерує список пов'язаних запитів на базі ключового слова
        
        :param keyword: ключове слово
        :return: словник з топовими та зростаючими запитами
        """
        # Базові шаблони для різних типів питань
        if keyword.startswith("як"):
            return {
                'top': [
                    f"{keyword} швидко", 
                    f"{keyword} в домашніх умовах", 
                    f"{keyword} без спеціальних інструментів", 
                    f"{keyword} правильно", 
                    f"{keyword} своїми руками"
                ],
                'rising': [
                    f"{keyword} під час війни", 
                    f"найкращий спосіб {keyword}", 
                    f"покрокова інструкція {keyword}", 
                    f"відео як {keyword}", 
                    f"поради експертів як {keyword}"
                ]
            }
        elif keyword.startswith("що"):
            return {
                'top': [
                    f"{keyword} простими словами", 
                    f"{keyword} насправді", 
                    f"{keyword} означає", 
                    f"{keyword} в Україні", 
                    f"{keyword} науковий погляд"
                ],
                'rising': [
                    f"{keyword} під час війни", 
                    f"{keyword} нові дослідження", 
                    f"{keyword} сучасний підхід", 
                    f"{keyword} цікаві факти", 
                    f"{keyword} міфи і реальність"
                ]
            }
        elif keyword.startswith("де"):
            return {
                'top': [
                    f"{keyword} в Україні", 
                    f"{keyword} онлайн", 
                    f"{keyword} недорого", 
                    f"{keyword} відгуки", 
                    f"{keyword} рейтинг"
                ],
                'rising': [
                    f"{keyword} під час війни", 
                    f"{keyword} в умовах кризи", 
                    f"{keyword} в Європі", 
                    f"{keyword} кращі місця", 
                    f"{keyword} перевірені джерела"
                ]
            }
        else:
            # Для інших типів питань
            return {
                'top': [
                    f"{keyword} в Україні", 
                    f"як {keyword}", 
                    f"що таке {keyword}", 
                    f"{keyword} приклади", 
                    f"{keyword} для початківців"
                ],
                'rising': [
                    f"{keyword} під час війни", 
                    f"{keyword} в умовах кризи", 
                    f"найкраще {keyword}", 
                    f"{keyword} поради", 
                    f"{keyword} відео"
                ]
            }


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
            trends_str = "Поточні тренди в Україні:\n- " + "\n- ".join(trends[:5])
            
            # Отримання пов'язаних запитів для збагачення контексту
            related = self.get_related_queries(keyword)
            related_str = ""
            
            if related['top'] or related['rising']:
                related_str = "Пов'язані запити:\n"
                if related['top']:
                    related_str += "Топові: " + ", ".join(related['top'][:5]) + "\n"
                if related['rising']:
                    related_str += "Зростаючі: " + ", ".join(related['rising'][:5]) + "\n"
            
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
            
            ВАЖЛИВО: Створи ідеї саме на основі реального тренду "{keyword}", а не вигадуй нові теми! Ідеї мають бути конкретно пов'язані з цим пошуковим запитом і відповідати на потреби користувачів, які шукають інформацію за цією темою.
            
            Для кожної ідеї обов'язково надай:
            1. Привабливий заголовок для відео (до 60 символів), який обов'язково включає оригінальний пошуковий запит
            2. Короткий опис (до 160 символів), що добре оптимізований для SEO
            3. 5-7 ключових моментів для сценарію, з практичною користю для глядача
            4. Список із 5-8 ключових слів українською мовою для оптимізації SEO (включно з оригінальним запитом)
            5. Рекомендований формат відео (наприклад, туторіал, огляд, список, історія, тощо)
            
            Формат відповіді:
            
            ## Ідея 1: [ЗАГОЛОВОК з включенням оригінального запиту]
            
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
