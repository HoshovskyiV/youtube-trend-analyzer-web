from flask import Flask, request, jsonify, render_template
import os
import json
import time
import logging
import google.generativeai as genai  # SDK для Gemini API
from flask_cors import CORS
from serpapi import GoogleSearch
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
    Клієнт для отримання трендових пошуків через SerpAPI
    """
    def __init__(self, api_key, language='uk', geo='UA'):
        """
        Ініціалізація клієнта для SerpAPI

        :param api_key: SerpAPI ключ
        :param language: мова (default: 'uk' - українська)
        :param geo: регіон (default: 'UA' - Україна)
        """
        self.api_key = api_key
        self.language = language
        self.geo = geo
        
        # Запасний список українських трендів на випадок проблем з API
        self.fallback_trends = [
            # Базові питальні конструкції
            "як підготуватися до відключення світла",
            "як знайти роботу під час війни",
            "як зробити генератор своїми руками",
            "як економити електроенергію",
            "як перевести гроші за кордон",
            "як отримати компенсацію за зруйноване житло",
            "як подати заявку на відновлення документів",
            "як зарядити телефон без світла",
            "як отримати військову допомогу",
            "як навчатися онлайн в Україні",
            
            # Актуальні теми
            "що робити при повітряній тривозі",
            "що таке Starlink і як його підключити",
            "що означають нові закони для військовозобов'язаних",
            "що потрібно для перетину кордону",
            "що відбувається на фронті",
            
            # Економіка і фінанси
            "де найдешевше купити генератор",
            "де купити будівельні матеріали для відновлення",
            "де знайти безоплатну правову допомогу",
            "де купити автомобіль під час війни",
            "де купити квартиру в безпечному регіоні",
            
            # Соціальні питання
            "коли закінчиться війна в Україні",
            "коли буде наступне відключення світла",
            "коли виплатять компенсації постраждалим",
            "коли почнеться масштабне відновлення",
            "коли запрацюють нові соціальні програми",
            
            # Практичні потреби
            "скільки коштує укриття для будинку",
            "скільки можна заробити на фрілансі",
            "скільки триватиме віялове відключення",
            "скільки коштує оренда житла у західній Україні",
            "скільки грошей потрібно для переїзду"
        ]
        
        logger.info(f"Ініціалізовано клієнт для SerpAPI з мовою {language} та регіоном {geo}")

    @retry(tries=3, delay=2, backoff=2)
    def get_trending_searches(self, count=20):
        """
        Отримати список трендових пошуків з Google Trends через SerpAPI

        :param count: кількість трендових запитів для повернення
        :return: список трендових запитів
        """
        # Список для зберігання трендів
        all_trends = []
        
        try:
            logger.info("Отримання трендів через SerpAPI")
            
            # Параметри для запиту до SerpAPI - Daily Trending Searches
            params = {
                "engine": "google_trends",
                "api_key": self.api_key,
                "data_type": "TRENDING_SEARCHES",  # Trending Searches
                "geo": self.geo,
                "hl": self.language
            }
            
            # Запит до SerpAPI
            search = GoogleSearch(params)
            results = search.get_dict()
            
            logger.info(f"Отримано відповідь від SerpAPI: {results.keys()}")
            
            # Обробка результатів
            if "trending_searches" in results:
                trending = results["trending_searches"]
                for search_item in trending:
                    if "title" in search_item and "query" in search_item["title"]:
                        all_trends.append(search_item["title"]["query"])
            
            # Якщо не вдалося отримати тренди, спробуємо ще один варіант запиту
            if not all_trends:
                params = {
                    "engine": "google_trends",
                    "api_key": self.api_key,
                    "data_type": "REAL_TIME_TRENDS",  # Real-time Trends
                    "geo": self.geo,
                    "hl": self.language,
                    "category": "all"
                }
                
                search = GoogleSearch(params)
                results = search.get_dict()
                
                if "real_time_trends" in results:
                    trends = results["real_time_trends"]
                    for trend in trends:
                        if "title" in trend:
                            all_trends.append(trend["title"])
            
            # Додатково спробуємо отримати тренди для подібних регіонів, якщо українських недостатньо
            if len(all_trends) < count / 2:
                similar_regions = ["PL", "CZ", "SK"]  # Польща, Чехія, Словаччина
                
                for region in similar_regions:
                    if len(all_trends) >= count:
                        break
                        
                    params = {
                        "engine": "google_trends",
                        "api_key": self.api_key,
                        "data_type": "TRENDING_SEARCHES",
                        "geo": region,
                        "hl": self.language
                    }
                    
                    search = GoogleSearch(params)
                    results = search.get_dict()
                    
                    if "trending_searches" in results:
                        trending = results["trending_searches"]
                        for search_item in trending:
                            if "title" in search_item and "query" in search_item["title"]:
                                all_trends.append(search_item["title"]["query"])
            
            # Видаляємо дублікати
            unique_trends = list(dict.fromkeys(all_trends))
            
            # Якщо тренди отримано, повертаємо їх
            if unique_trends:
                logger.info(f"Отримано {len(unique_trends)} унікальних трендів через SerpAPI")
                result = unique_trends[:count] if len(unique_trends) > count else unique_trends
                return result
            
            # Якщо не вдалося отримати тренди через SerpAPI, використовуємо запасний список
            logger.warning("Не вдалося отримати тренди через SerpAPI, використовуємо запасний список")
            
        except Exception as e:
            logger.error(f"Помилка при отриманні трендів через SerpAPI: {str(e)}")
            
        # Повертаємо запасний список, якщо не вдалося отримати тренди через API
        fallback_result = random.sample(self.fallback_trends, min(count, len(self.fallback_trends)))
        logger.info(f"Використано {len(fallback_result)} трендів із запасного списку")
        return fallback_result
    
    def get_related_queries(self, keyword):
        """
        Отримати пов'язані запити для заданого ключового слова через SerpAPI
        
        :param keyword: ключове слово для пошуку пов'язаних запитів
        :return: словник з топовими та зростаючими запитами
        """
        try:
            logger.info(f"Пошук пов'язаних запитів для '{keyword}' через SerpAPI")
            
            # Параметри для запиту до SerpAPI
            params = {
                "engine": "google_trends",
                "api_key": self.api_key,
                "data_type": "RELATED_QUERIES",
                "geo": self.geo,
                "hl": self.language,
                "q": keyword,  # Ключове слово для пошуку
                "date": "today 12-m"  # За останній рік
            }
            
            # Запит до SerpAPI
            search = GoogleSearch(params)
            results = search.get_dict()
            
            top_queries = []
            rising_queries = []
            
            # Обробка результатів
            if "related_queries" in results:
                queries = results["related_queries"]
                
                # Топові запити
                if "top" in queries:
                    for query in queries["top"]:
                        if "query" in query:
                            top_queries.append(query["query"])
                
                # Зростаючі запити
                if "rising" in queries:
                    for query in queries["rising"]:
                        if "query" in query:
                            rising_queries.append(query["query"])
            
            logger.info(f"Знайдено {len(top_queries)} топових та {len(rising_queries)} зростаючих запитів")
            
            # Логуємо приклади запитів
            if top_queries:
                logger.info(f"Пов'язані топові запити: {top_queries[:5]}")
            if rising_queries:
                logger.info(f"Пов'язані зростаючі запити: {rising_queries[:5]}")
            
            # Якщо знайшли достатньо пов'язаних запитів, повертаємо їх
            if top_queries or rising_queries:
                return {
                    'top': top_queries[:10],  # Збільшуємо число запитів для кращого контексту
                    'rising': rising_queries[:10]
                }
            
            # Якщо не знайшли через SerpAPI, генеруємо пов'язані запити на основі ключового слова
            logger.info(f"Генерація пов'язаних запитів для '{keyword}'")
            return self._generate_related_queries(keyword)
            
        except Exception as e:
            logger.error(f"Помилка при отриманні пов'язаних запитів: {str(e)}")
            # У випадку помилки генеруємо запити
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
    def __init__(self, gemini_api_key, serpapi_key, language='uk', region='UA'):
        """
        Ініціалізація системи аналізу трендів
        
        :param gemini_api_key: API ключ для Gemini
        :param serpapi_key: API ключ для SerpAPI
        :param language: мова для аналізу трендів (default: 'uk' - українська)
        :param region: регіон для аналізу (default: 'UA' - Україна)
        """
        # Налаштування Gemini API з новим SDK
        self.gemini_api_key = gemini_api_key
        genai.configure(api_key=gemini_api_key)
        
        # Ініціалізуємо клієнт для отримання трендів через SerpAPI
        self.trends_client = GoogleTrendsClient(
            api_key=serpapi_key,
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
            logger.info(f"Поточні тренди: {trends}")
            
            # Отримання пов'язаних запитів для збагачення контексту
            related = self.get_related_queries(keyword)
            
            # Формуємо список ключових запитів для генерації ідей з пріоритетом на реальні пов'язані запити
            key_queries = []
            
            # Додаємо зростаючі запити (найвищий пріоритет)
            if related['rising']:
                key_queries.extend(related['rising'])
            
            # Додаємо топові запити
            if related['top']:
                key_queries.extend(related['top'])
                
            # Якщо запитів недостатньо, додаємо загальні тренди
            if len(key_queries) < 5 and trends:
                key_queries.extend([trend for trend in trends if keyword.lower() in trend.lower()])
            
            # Формуємо текст з ключовими запитами для промпту
            if key_queries:
                key_queries_text = "\n".join([f"- {query}" for query in key_queries[:10]])
                key_trends_str = f"Ключові пошукові запити, які необхідно використовувати для генерації ідей:\n{key_queries_text}\n"
            else:
                key_trends_str = ""
            
            # Формуємо текст з пов'язаними запитами
            related_str = ""
            if related['top'] or related['rising']:
                related_str = "Додаткові пов'язані запити:\n"
                if related['top']:
                    related_str += "Топові: " + ", ".join(related['top'][:8]) + "\n"
                if related['rising']:
                    related_str += "Зростаючі: " + ", ".join(related['rising'][:8]) + "\n"
            
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
            
            # Видалено додатковий контекст, щоб фокусуватися тільки на реальних пошукових запитах
            
            prompt = f"""
            Ти - аналітик контенту для українських YouTube блогерів. Створи {count} детальних ідей для YouTube відео українською мовою на основі конкретного запиту: "{keyword}" {category_str}.
            
            {key_trends_str}
            
            {related_str}
            
            ДУЖЕ ВАЖЛИВО: Створи ідеї ВИКЛЮЧНО на основі конкретних реальних пошукових запитів, які наведені вище! Не вигадуй нові теми, а використовуй точні формулювання з ключових пошукових запитів.
            
            Наприклад, якщо наведені такі запити як "як зробити скрін на компі" або "як зробити фото ші", то саме для них треба створити ідеї відео, а не для загальних тем.
            
            Для кожної ідеї обов'язково використовуй один з конкретних наведених запитів як основу заголовка відео!
            
            Для кожної ідеї обов'язково надай:
            1. Привабливий заголовок для відео (до 60 символів), який ОБОВ'ЯЗКОВО включає ТОЧНЕ формулювання одного з наведених пошукових запитів
            2. Короткий опис (до 160 символів), що добре оптимізований для SEO
            3. 5-7 ключових моментів для сценарію, з практичною користю для глядача
            4. Список із 5-8 ключових слів українською мовою для оптимізації SEO (включно з оригінальним запитом)
            5. Рекомендований формат відео (наприклад, туторіал, огляд, список, історія, тощо)
            
            Формат відповіді:
            
            ## Ідея 1: [ЗАГОЛОВОК ВКЛЮЧАЄ ТОЧНИЙ ПОШУКОВИЙ ЗАПИТ]
            
            **Опис**: [ОПИС]
            
            **Ключові моменти**:
            - [МОМЕНТ 1]
            - [МОМЕНТ 2]
            ...
            
            **Ключові слова**: [СЛОВО1], [СЛОВО2], ..., [ОРИГІНАЛЬНИЙ ЗАПИТ]
            
            **Формат**: [ФОРМАТ]
            
            ---
            
            Переконайся, що ідеї дуже конкретні, актуальні та практичні. Відповідай на реальні потреби українців у 2025 році.
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
    # Отримуємо API ключі з змінних середовища
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    serpapi_key = os.environ.get('SERPAPI_KEY', '4158b151b213f60f1959ccb2592bab29436f73fc91c62b695b86e8cce3789223')
    
    if not gemini_api_key:
        logger.error("GEMINI_API_KEY відсутній у змінних середовища")
        return
    
    try:
        analyzer = TrendAnalyzer(
            gemini_api_key=gemini_api_key,
            serpapi_key=serpapi_key,
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