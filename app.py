
from flask import Flask, request, jsonify, render_template
import os
import json
import time
import logging
import google.generativeai as genai  # SDK для Gemini API
from pytrends.request import TrendReq  # Бібліотека PyTrends замість SerpAPI
from flask_cors import CORS
from retry import retry

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

    @retry(tries=3, delay=2, backoff=2)
    def get_trending_searches(self, count=20):
        """
        Отримати список трендових пошуків для заданого регіону

        :param count: кількість трендових запитів для повернення
        :return: список трендових запитів
        """
        try:
            # Треба адаптувати залежно від регіону - для України використовуємо США 
            # оскільки PyTrends не має прямого методу для України
            country = 'ukraine'  # Будемо намагатись отримати дані для українських трендів
            
            logger.info(f"Запит трендових пошуків через PyTrends")
            
            # Спочатку спробуємо отримати щоденні тренди для своєї країни, якщо доступно
            try:
                trending_searches_df = self.pytrends.trending_searches(pn=country)
                trending_searches = trending_searches_df[0].tolist()
                logger.info(f"Отримано {len(trending_searches)} трендових запитів для {country}")
            except Exception as e:
                logger.warning(f"Не вдалося отримати тренди для {country}, використовуємо US: {str(e)}")
                # Якщо не вдається отримати для України, використовуємо US
                trending_searches_df = self.pytrends.trending_searches(pn='united_states')
                trending_searches = trending_searches_df[0].tolist()
                logger.info(f"Отримано {len(trending_searches)} трендових запитів для US")
            
            # Додатково можемо отримати дані real-time трендів для обраного регіону
            try:
                realtime_trends_df = self.pytrends.realtime_trending_searches(pn=country)
                if not realtime_trends_df.empty:
                    # Витягуємо унікальні заголовки з даних real-time трендів
                    realtime_trends = realtime_trends_df['title'].unique().tolist()
                    # Додаємо їх до основного списку
                    trending_searches = list(dict.fromkeys(trending_searches + realtime_trends))
                    logger.info(f"Додано {len(realtime_trends)} real-time трендів")
            except Exception as e:
                logger.warning(f"Не вдалося отримати real-time тренди: {str(e)}")
            
            # Обмеження до заданої кількості
            result = trending_searches[:count] if len(trending_searches) > count else trending_searches
            logger.info(f"Повернено {len(result)} трендових запитів")
            
            return result
        except Exception as e:
            logger.error(f"Неочікувана помилка при отриманні трендових запитів: {str(e)}")
            # У випадку помилки спробуємо отримати хоча б якісь загальні тренди
            fallback_trends = [
                "війна в Україні", 
                "новини сьогодні", 
                "погода на завтра",
                "курс валют",
                "вакансії",
                "футбол онлайн",
                "рецепти",
                "серіали онлайн",
                "ціни на паливо",
                "шопінг онлайн"
            ]
            logger.info(f"Використовуємо запасний список трендів")
            return fallback_trends[:count]

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
            
            return {
                'top': top_queries,
                'rising': rising_queries
            }
        except Exception as e:
            logger.error(f"Помилка при отриманні пов'язаних запитів: {str(e)}")
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
            available_models = genai.list_models()
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
            
            prompt = f"""
            Створи {count} детальних ідей для YouTube відео на основі трендового запиту: "{keyword}" {category_str}.
            
            {related_str}
            
            Для кожної ідеї надай:
            1. Привабливий заголовок для відео (до 60 символів)
            2. Короткий опис (до 160 символів)
            3. 5-7 ключових моментів для сценарію
            4. Список із 5-8 ключових слів для оптимізації SEO
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
            
            Будь творчим, але реалістичним. Фокусуйся на якісному контенті, який буде цікавий українській аудиторії.
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

@app.before_first_request
def initialize_analyzer():
    """Ініціалізація аналізатора трендів перед першим запитом"""
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
