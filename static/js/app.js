/**
 * YouTube Trend Analyzer - Frontend JavaScript
 * Відповідає за взаємодію з користувачем та API
 */

// Основні елементи сторінки
const analyzeForm = document.getElementById('analyze-form');
const trendSelect = document.getElementById('trend-select');
const customKeyword = document.getElementById('custom-keyword');
const categorySelect = document.getElementById('category');
const ideasCount = document.getElementById('ideas-count');
const analyzeBtn = document.getElementById('analyze-btn');
const refreshTrendsBtn = document.getElementById('refresh-trends');
const copyResultsBtn = document.getElementById('copy-results');

// Контейнери для відображення
const welcomeContainer = document.getElementById('welcome-container');
const resultsContainer = document.getElementById('results-container');
const resultsTitle = document.getElementById('results-title');
const resultsContent = document.getElementById('results');
const loader = document.getElementById('loader');
const errorContainer = document.getElementById('error-container');
const errorMessage = document.getElementById('error-message');

// API URL - адаптується залежно від середовища
const BASE_URL = window.location.origin;

/**
 * Ініціалізує сторінку після завантаження
 */
document.addEventListener('DOMContentLoaded', async () => {
    try {
        // Завантажуємо список трендів при завантаженні сторінки
        await loadTrends();
        
        // Налаштування обробників подій
        analyzeForm.addEventListener('submit', handleAnalyzeSubmit);
        refreshTrendsBtn.addEventListener('click', loadTrends);
        copyResultsBtn.addEventListener('click', copyResults);
        
        // Логіка перемикання між вибором тренду і власним ключовим словом
        trendSelect.addEventListener('change', () => {
            if (trendSelect.value) {
                customKeyword.value = '';
            }
        });
        
        customKeyword.addEventListener('input', () => {
            if (customKeyword.value) {
                trendSelect.selectedIndex = 0;
            }
        });
    } catch (error) {
        console.error('Помилка ініціалізації:', error);
        showError('Не вдалося ініціалізувати додаток. Будь ласка, перезавантажте сторінку.');
    }
});

/**
 * Завантажує список трендів з API
 */
async function loadTrends() {
    try {
        // Показуємо завантаження в селекті
        trendSelect.innerHTML = '<option value="" selected>-- Завантаження трендів... --</option>';
        refreshTrendsBtn.disabled = true;
        
        // Отримуємо тренди з API
        const response = await fetch(`${BASE_URL}/api/trends?count=10`);
        
        if (!response.ok) {
            throw new Error(`Помилка отримання трендів: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Очищаємо селект і додаємо дефолтну опцію
        trendSelect.innerHTML = '<option value="" selected>-- Оберіть тренд --</option>';
        
        // Додаємо отримані тренди до селекту
        if (data.trends && data.trends.length > 0) {
            data.trends.forEach(trend => {
                const option = document.createElement('option');
                option.value = trend;
                option.textContent = trend;
                trendSelect.appendChild(option);
            });
        } else {
            trendSelect.innerHTML = '<option value="" selected>-- Тренди не знайдено --</option>';
        }
    } catch (error) {
        console.error('Помилка завантаження трендів:', error);
        trendSelect.innerHTML = '<option value="" selected>-- Помилка завантаження трендів --</option>';
        showError('Не вдалося завантажити тренди. Спробуйте ще раз пізніше.');
    } finally {
        refreshTrendsBtn.disabled = false;
    }
}

/**
 * Обробляє відправку форми аналізу
 */
async function handleAnalyzeSubmit(event) {
    event.preventDefault();
    
    // Отримуємо ключове слово (або з селекту, або з поля введення)
    const keyword = customKeyword.value || trendSelect.value;
    const category = categorySelect.value;
    const count = parseInt(ideasCount.value) || 3;
    
    // Перевіряємо, що ключове слово вказано
    if (!keyword) {
        showError('Будь ласка, оберіть тренд або введіть власне ключове слово');
        return;
    }
    
    try {
        // Показуємо анімацію завантаження
        showLoader();
        
        // Формуємо тіло запиту
        const requestBody = {
            keyword,
            count,
            category: category || undefined
        };
        
        // Відправляємо запит на аналіз
        const response = await fetch(`${BASE_URL}/api/analyze`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Помилка аналізу: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Відображаємо результати
        showResults(data);
    } catch (error) {
        console.error('Помилка аналізу:', error);
        showError(`Помилка при аналізі: ${error.message}`);
        hideLoader();
    }
}

/**
 * Показує анімацію завантаження
 */
function showLoader() {
    welcomeContainer.classList.add('d-none');
    resultsContainer.classList.remove('d-none');
    resultsContent.innerHTML = '';
    loader.classList.remove('d-none');
    errorContainer.classList.add('d-none');
    analyzeBtn.disabled = true;
}

/**
 * Приховує анімацію завантаження
 */
function hideLoader() {
    loader.classList.add('d-none');
    analyzeBtn.disabled = false;
}

/**
 * Показує результати аналізу
 */
function showResults(data) {
    hideLoader();
    
    // Форматуємо заголовок результатів
    const categoryText = data.category ? ` (${data.category})` : '';
    resultsTitle.textContent = `Результати аналізу: ${data.keyword}${categoryText}`;
    
    // Використовуємо бібліотеку marked.js для рендерингу Markdown
    resultsContent.innerHTML = marked.parse(data.ideas);
    
    // Приховуємо привітальне повідомлення
    welcomeContainer.classList.add('d-none');
    
    // Показуємо контейнер результатів
    resultsContainer.classList.remove('d-none');
}

/**
 * Показує повідомлення про помилку
 */
function showError(message) {
    errorMessage.textContent = message;
    errorContainer.classList.remove('d-none');
    
    // Автоматично приховуємо повідомлення через 5 секунд
    setTimeout(() => {
        errorContainer.classList.add('d-none');
    }, 5000);
}

/**
 * Копіює результати аналізу в буфер обміну
 */
function copyResults() {
    // Перевіряємо, чи є результати для копіювання
    if (!resultsContent.textContent.trim()) {
        showError('Немає результатів для копіювання');
        return;
    }
    
    try {
        // Створюємо елемент для копіювання
        const tempElement = document.createElement('textarea');
        tempElement.value = resultsContent.textContent;
        document.body.appendChild(tempElement);
        
        // Виділяємо і копіюємо текст
        tempElement.select();
        document.execCommand('copy');
        
        // Видаляємо тимчасовий елемент
        document.body.removeChild(tempElement);
        
        // Змінюємо текст кнопки на короткий час
        const originalText = copyResultsBtn.innerHTML;
        copyResultsBtn.innerHTML = '<i class="fas fa-check"></i> Скопійовано';
        
        setTimeout(() => {
            copyResultsBtn.innerHTML = originalText;
        }, 2000);
    } catch (error) {
        console.error('Помилка копіювання:', error);
        showError('Не вдалося скопіювати результати');
    }
}
