from flask import Flask, request, jsonify, render_template
import os
import json
import time
import logging
import google.generativeai as genai  # SDK для Gemini API
from pytrends.request import TrendReq  # Бібліотека PyTrends замість SerpAPI
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
    Клієнт для доступу до даних Google Trends через PyTrends
    """
    def __init__(self, language='uk', geo='UA', tz=360):
        """
        Ініціалізація PyTrends клієнта для Google Trends

        :param language: мова (default: 'uk' - українська)
        :param geo: регіон (default: 'UA' - Україна)
        :param tz: часовий пояс (default: 360 - UTC+3)
        """
        self.language = language
        self.geo = geo
        self.tz = tz
        # Ініціалізація PyTrends з відповідними параметрами
        self.pytrends = TrendReq(hl=language, geo=geo, tz=tz)
        logger.info(f"Ініціалізовано PyTrends клієнт для Google Trends з мовою {language} та регіоном {geo}")
        
        # Список країн, які точно підтримуються в PyTrends
        self.supported_countries = ['united_states', 'japan', 'india']
        
        # Потенційні джерела для скрапінгу, якщо PyTrends не працює
        self.scraping_sources = [
            "https://trends.google.com/trends/trendingsearches/daily?geo=UA&hl=uk",
            "https://trends.google.com/trends/trendingsearches/daily?geo=US&hl=uk"
        ]

    @retry(tries=3, delay=2, backoff=2)
    def get_trending_searches(self, count=20):
        """
        Отримати список трендових пошуків для заданого регіону

        :param count: кількість трендових запитів для повернення
        :return: список трендових запитів
        """
        # Список для зберігання трендів, які ми спробуємо отримати з різних джерел
        all_trends = []
        
        # 1. Спробуємо отримати тренди для підтримуваних країн і відфільтрувати українські
        if len(all_trends) < count:
            for country in self.supported_countries:
                try:
                    logger.info(f"Спроба #1: Запит трендових пошуків через PyTrends для {country}")
                    trending_searches_df = self.pytrends.trending_searches(pn=country)
                    trends = trending_searches_df[0].tolist()
                    
                    # Додаємо до загального списку
                    all_trends.extend(trends)
                    logger.info(f"PyTrends повернув {len(trends)} трендів для {country}")
                    
                    # Якщо маємо достатньо трендів, виходимо з циклу
                    if len(all_trends) >= count * 2:  # Отримуємо більше, щоб потім відфільтрувати
                        break
                except Exception as e:
                    logger.warning(f"Не вдалося отримати тренди для {country}: {str(e)}")
        
        # 2. Спробуємо скрапінг Google Trends веб-сторінки для України
        if len(all_trends) < count:
            try:
                logger.info(f"Спроба #2: Скрапінг Google Trends веб-сторінки для України")
                scraped_trends = self._scrape_google_trends_page()
                if scraped_trends:
                    logger.info(f"Скрапінг повернув {len(scraped_trends)} трендів")
                    all_trends.extend(scraped_trends)
            except Exception as e:
                logger.warning(f"Помилка при скрапінгу Google Trends: {str(e)}")
        
        # 3. Якщо все ще недостатньо трендів, додаємо фіктивні дані на основі питальних конструкцій
        if len(all_trends) < count:
            logger.info(f"Спроба #3: Використовуємо запасний список питальних конструкцій")
            fallback_trends = [
                # Базові питальні слова
                "як",
                "чому",
                "де",
                "коли",
                "що",
                "хто",
                "скільки",
                "навіщо",
                "куди",
                "звідки",
                "який",
                "яка",
                "яке",
                "які",
                
                # Поширені конструкції з "як"
                "як зробити",
                "як встановити",
                "як налаштувати",
                "як використовувати",
                "як приготувати",
                "як відновити",
                "як видалити",
                "як вибрати",
                "як знайти",
                "як створити",
                "як заробити",
                "як змінити",
                "як дізнатися",
                "як вирішити",
                "як купити",
                "як перевірити",
                "як мені",
                "як правильно",
                
                # Конструкції з "що"
                "що таке",
                "що робити",
                "що означає",
                "що буде якщо",
                "що робити якщо",
                "що краще",
                "що вибрати",
                "що подарувати",
                
                # Конструкції з "чому"
                "чому не працює",
                "чому виникає",
                "чому болить",
                "чому не можна",
                
                # Конструкції з "де"
                "де знайти",
                "де купити",
                "де замовити",
                "де розташований",
                "де знаходиться",
                
                # Конструкції з "коли"
                "коли буде",
                "коли можна",
                "коли краще",
                "коли починається",
                "коли закінчується",
                
                # Конструкції з "скільки"
                "скільки коштує",
                "скільки потрібно",
                "скільки часу",
                "скільки триває",
                "скільки важить",
                
                # Конструкції з "хто"
                "хто такий",
                "хто така",
                "хто такі",
                "хто автор",
                "хто створив",
                "хто винайшов",
                
                # Конструкції з "який/яка/яке/які"
                "який кращий",
                "яка краща",
                "яке краще",
                "які кращі",
                "яка різниця",
                "які документи потрібні",
                
                # Інші конструкції
                "чи можна",
                "чи варто",
                "куди піти",
                "звідки походить",
                "з чого зроблено"
            ]
            all_trends.extend(fallback_trends)
        
        # Видаляємо дублікати і трансформуємо тренди для української локалізації
        unique_trends = list(dict.fromkeys(all_trends))
        
        # Якщо тренди не українською мовою, можна спробувати адаптувати їх
        # (це спрощений підхід; у реальному проекті можна використовувати переклад API)
        ukrainian_related_trends = []
        for trend in unique_trends:
            # Додаємо оригінальний тренд
            ukrainian_related_trends.append(trend)
            
            # Перевіряємо, чи тренд схожий на українське слово (спрощений підхід)
            if not self._is_likely_ukrainian(trend) and len(trend.split()) <= 2:
                # Додаємо варіанти з питальними словами
                ukrainian_related_trends.append(f"як {trend}")
                ukrainian_related_trends.append(f"що таке {trend}")
                ukrainian_related_trends.append(f"де купити {trend}")
        
        # Перемішуємо список, щоб не всі аналогічні конструкції йшли поспіль
        random.shuffle(ukrainian_related_trends)
        
        # Обмеження до заданої кількості
        result = ukrainian_related_trends[:count] if len(ukrainian_related_trends) > count else ukrainian_related_trends
        logger.info(f"Повернено {len(result)} трендових запитів")
        
        return result
    
    def _is_likely_ukrainian(self, text):
        """
        Спрощена перевірка, чи текст схожий на українську мову
        
        :param text: текст для перевірки
        :return: True якщо схожий на українську, False інакше
        """
        # Українські символи (спрощений підхід)
        ukrainian_chars = set('абвгґдеєжзиіїйклмнопрстуфхцчшщьюяАБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ')
        
        # Якщо текст містить українські символи, вважаємо його українським
        text_chars = set(text.lower())
        return bool(text_chars.intersection(ukrainian_chars))
    
    def _scrape_google_trends_page(self):
        """
        Спроба скрапінгу Google Trends веб-сторінки для отримання трендів
        
        :return: список трендів або порожній список в разі невдачі
        """
        trends = []
        
        for url in self.scraping_sources:
            try:
                # Додаємо User-Agent, щоб імітувати звичайний браузер
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                # Робимо запит
                response = requests.get(url, headers=headers, timeout=5)
                
                # Перевіряємо статус відповіді
                if response.status_code == 200:
                    # Парсимо HTML
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Шукаємо тренди в HTML структурі
                    # Примітка: цей селектор може змінитися, якщо Google змінить структуру сторінки
                    trend_elements = soup.select('div.feed-item-header')
                    
                    for element in trend_elements:
                        trend_text = element.text.strip()
                        if trend_text:
                            trends.append(trend_text)
                    
                    # Якщо знайшли тренди, виходимо з циклу
                    if trends:
                        break
            except Exception as e:
                logger.warning(f"Помилка при скрапінгу {url}: {str(e)}")
        
        # Додатковий метод: якщо скрапінг не працює, спробуємо проаналізувати українські новинні сайти
        if not trends:
            try:
                # Список українських новинних сайтів
                news_sites = [
                    "https://www.pravda.com.ua/",
                    "https://www.unian.ua/",
                    "https://tsn.ua/"
                ]
                
                for site in news_sites:
                    try:
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                        }
                        
                        response = requests.get(site, headers=headers, timeout=5)
                        
                        if response.status_code == 200:
                            # Парсимо HTML
                            soup = BeautifulSoup(response.text, 'html.parser')
                            
                            # Шукаємо заголовки новин
                            headlines = soup.find_all(['h1', 'h2', 'h3', 'h4'])
                            
                            for headline in headlines:
                                text = headline.text.strip()
                                if text and len(text) > 5 and len(text) < 50:  # Фільтруємо занадто короткі або довгі
                                    # Перетворюємо заголовок новини у пошуковий запит
                                    # Видаляємо зайві символи і обмежуємо довжину
                                    clean_text = re.sub(r'[^\w\s]', '', text)
                                    clean_text = clean_text.strip()
                                    
                                    if clean_text:
                                        trends.append(clean_text)
                            
                            # Якщо знайшли достатньо, виходимо з циклу
                            if len(trends) >= 20:
                                break
                    except Exception as e:
                        logger.warning(f"Помилка при скрапінгу {site}: {str(e)}")
            except Exception as e:
                logger.warning(f"Помилка при скрапінгу новинних сайтів: {str(e)}")
        
        return trends[:20]  # Обмежуємо кількість трендів
    
    @retry(tries=3, delay=2, backoff=2)
    def get_related_queries(self, keyword):
        """
        Отримати пов'язані запити для заданого ключового слова

        :param keyword: ключове слово для пошуку пов'язаних запитів
        :return: словник з топовими та зростаючими запитами
        """
        try:
            logger.info(f"Запит пов'язаних запитів для '{keyword}' через PyTrends")
            
            # Побудова запиту для PyTrends
            # timeframe='today 1-m' - за останній місяць
            self.pytrends.build_payload([keyword], cat=0, timeframe='today 1-m', geo=self.geo, gprop='')
            
            # Отримання пов'язаних запитів
            related_queries = self.pytrends.related_queries()
            
            top_queries = []
            rising_queries = []
            
            # Перевірка і витягування даних, якщо вони доступні
            if keyword in related_queries and related_queries[keyword]:
                if 'top' in related_queries[keyword] and not related_queries[keyword]['top'] is None:
                    top_df = related_queries[keyword]['top']
                    if not top_df.empty:
                        top_queries = top_df['query'].tolist()
                
                if 'rising' in related_queries[keyword] and not related_queries[keyword]['rising'] is None:
                    rising_df = related_queries[keyword]['rising']
                    if not rising_df.empty:
                        rising_queries = rising_df['query'].tolist()
            
            logger.info(f"Отримано {len(top_queries)} топових та {len(rising_queries)} зростаючих запитів")
            
            # Якщо запити успішно отримані - повертаємо їх
            if top_queries or rising_queries:
                return {
                    'top': top_queries,
                    'rising': rising_queries
                }
            
            # Якщо запити не отримані, генеруємо фіктивні дані
            # У випадку помилки повертаємо фіктивні дані для покращення генерації
            # Створюємо фіктивні пов'язані запити на основі питальної конструкції
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
                        f"{keyword} 2025", 
                        f"найкращий спосіб {keyword}", 
                        f"покрокова інструкція {keyword}", 
                        f"відео {keyword}", 
                        f"поради експертів {keyword}"
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
                        f"{keyword} 2025", 
                        f"{keyword} нові дослідження", 
                        f"{keyword} сучасний підхід", 
                        f"{keyword} цікаві факти", 
                        f"{keyword} міфи і реальність"
                    ]
                }
            elif keyword.startswith("чому"):
                return {
                    'top': [
                        f"{keyword} причини", 
                        f"{keyword} пояснення", 
                        f"{keyword} наукова точка зору", 
                        f"{keyword} дослідження", 
                        f"{keyword} експерти кажуть"
                    ],
                    'rising': [
                        f"{keyword} нові дані", 
                        f"{keyword} дослідження 2025", 
                        f"{keyword} статистика", 
                        f"{keyword} докази", 
                        f"{keyword} поради фахівців"
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
                        f"{keyword} 2025", 
                        f"{keyword} під час війни", 
                        f"{keyword} в Європі", 
                        f"{keyword} кращі місця", 
                        f"{keyword} перевірені джерела"
                    ]
                }
            elif keyword.startswith("коли"):
                return {
                    'top': [
                        f"{keyword} точні дати", 
                        f"{keyword} календар", 
                        f"{keyword} розклад", 
                        f"{keyword} терміни", 
                        f"{keyword} офіційно"
                    ],
                    'rising': [
                        f"{keyword} 2025", 
                        f"{keyword} новий закон", 
                        f"{keyword} зміни", 
                        f"{keyword} прогноз", 
                        f"{keyword} останні новини"
                    ]
                }
            elif keyword.startswith("скільки"):
                return {
                    'top': [
                        f"{keyword} в гривнях", 
                        f"{keyword} насправді", 
                        f"{keyword} порівняння", 
                        f"{keyword} ціни", 
                        f"{keyword} статистика"
                    ],
                    'rising': [
                        f"{keyword} 2025", 
                        f"{keyword} під час інфляції", 
                        f"{keyword} економія", 
                        f"{keyword} калькулятор", 
                        f"{keyword} розрахунок"
                    ]
                }
            else:
                # Для інших типів питань
                return {
                    'top': [
                        f"{keyword} пояснення", 
                        f"{keyword} інформація", 
                        f"{keyword} детально", 
                        f"{keyword} приклади", 
                        f"{keyword} українською"
                    ],
                    'rising': [
                        f"{keyword} 2025", 
                        f"{keyword} найновіша інформація", 
                        f"{keyword} докладніше", 
                        f"{keyword} поради", 
                        f"{keyword} відео"
                    ]
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
        
        # Ініціалізуємо клієнт PyTrends для Google Trends
        self.trends_client = GoogleTrendsClient(
            language=language,
            geo=region
        )
        
        # Налаштування мови та регіону
        self.language = language
        self.region = region
        
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
        Отримати трендові пошуки
        
        :param count: кількість трендів
        :return: список трендових запитів
        """
        trending_searches = self.trends_client.get_trending_searches(count=count)
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
            Створи {count} детальних ідей для YouTube відео українською мовою на основі пошукового запиту: "{keyword}" {category_str}.
            
            {related_str}
            
            {current_context}
            
            Для кожної ідеї обов'язково надай:
            1. Привабливий заголовок для відео (до 60 символів), який включає ключовий запит
            2. Короткий опис (до 160 символів), що добре оптимізований для SEO
            3. 5-7 ключових моментів для сценарію, з практичною користю для глядача
            4. Список із 5-8 ключових слів українською мовою для оптимізації SEO
            5. Рекомендований формат відео (наприклад, туторіал, огляд, список, історія, тощо)
            
            Формат відповіді:
            
            ## Ідея 1: [ЗАГОЛОВОК]
            
            **Опис**: [ОПИС]
            
            **Ключові моменти**:
            - [МОМЕНТ 1]
            - [МОМЕНТ 2]
            ...
            
            **Ключові слова**: [СЛОВО1], [СЛОВО2], ...
            
            **Формат**: [ФОРМАТ]
            
            ---
            
            Переконайся, що ідеї дуже конкретні, актуальні та дуже практичні. Відповідай на реальні потреби українців у 2025 році. Фокусуйся на практичній користі, а не загальних темах.
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
