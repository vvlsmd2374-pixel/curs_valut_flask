from flask import Flask, render_template, request, jsonify
import requests
from xml.etree import ElementTree as ET
from datetime import datetime

app = Flask(__name__)


def get_currency_data():
    """Основная функция для получения данных о валютах с сайта ЦБ РФ"""
    try:
        # Получаем данные с сайта ЦБ РФ
        url = 'https://www.cbr.ru/scripts/XML_daily.asp'

        # Добавляем параметр даты для получения актуальных данных
        current_date = datetime.now().strftime('%d/%m/%Y')
        params = {'date_req': current_date}

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()

        # Парсим XML
        root = ET.fromstring(response.content)

        currencies = []

        # Словарь для перевода названий валют
        currency_names_ru = {
            'USD': 'Доллар США',
            'EUR': 'Евро',
            'GBP': 'Фунт стерлингов',
            'CNY': 'Китайский юань',
            'JPY': 'Японская иена',
            'CHF': 'Швейцарский франк',
            'TRY': 'Турецкая лира',
            'PLN': 'Польский злотый',
            # 'UAH': 'Гривна',
            'KZT': 'Казахский тенге',
            'CAD': 'Канадский доллар',
            'AUD': 'Австралийский доллар',
            'SGD': 'Сингапурский доллар',
            'HKD': 'Гонконгский доллар',
            'NOK': 'Норвежская крона',
            'SEK': 'Шведская крона',
            'DKK': 'Датская крона',
            'INR': 'Индийская рупия',
            'BRL': 'Бразильский реал',
            'ZAR': 'Южноафриканский рэнд',
            'BYN': 'Белорусский рубль'
        }

        # Обрабатываем основные валюты из XML
        for valute in root.findall('Valute'):
            char_code = valute.find('CharCode').text
            name_ru = valute.find('Name').text

            # Используем наше отображение или оригинальное название
            display_name = currency_names_ru.get(char_code, name_ru)

            nominal = int(valute.find('Nominal').text)
            value = float(valute.find('Value').text.replace(',', '.'))

            # Рассчитываем курс в RUB (прямой курс от ЦБ РФ)
            # Это курс иностранной валюты в рублях
            rub_per_unit = value / nominal

            # Создаем спред (разницу между покупкой и продажей) - обычно 1-2%
            spread = 0.015  # 1.5% спред

            buy_rate = rub_per_unit * (1 - spread / 2)  # Для покупки немного меньше
            sell_rate = rub_per_unit * (1 + spread / 2)  # Для продажи немного больше

            # Форматируем значения
            currency_data = {
                'name': f'{display_name} ({char_code})',
                'buy': f'{buy_rate:.4f}',
                'sell': f'{sell_rate:.4f}',
                'central_bank': f'{rub_per_unit:.4f}',
                'buy_float': round(buy_rate, 6),
                'sell_float': round(sell_rate, 6),
                'cb_float': round(rub_per_unit, 6)
            }

            currencies.append(currency_data)

        # Добавляем российский рубль (RUB) как базовую валюту ПЕРВЫМ
        currencies.insert(0, {
            'name': 'Российский рубль (RUB)',
            'buy': '1.0000',
            'sell': '1.0000',
            'central_bank': '1.0000',
            'buy_float': 1.0,
            'sell_float': 1.0,
            'cb_float': 1.0
        })

        # Добавляем белорусский рубль (BYN) отдельно, если его нет в данных ЦБ
        has_byn = any('BYN' in currency['name'] for currency in currencies)
        if not has_byn:
            # Примерный курс BYN к RUB
            byn_to_rub = 28.5
            currencies.append({
                'name': 'Белорусский рубль (BYN)',
                'buy': f'{byn_to_rub * 0.99:.4f}',
                'sell': f'{byn_to_rub * 1.01:.4f}',
                'central_bank': f'{byn_to_rub:.4f}',
                'buy_float': round(byn_to_rub * 0.99, 6),
                'sell_float': round(byn_to_rub * 1.01, 6),
                'cb_float': round(byn_to_rub, 6)
            })

        # Сортируем валюты по популярности, но RUB остается первым
        popular_order = ['RUB', 'USD', 'EUR', 'BYN', 'GBP', 'CNY', 'PLN', 'TRY', 'JPY']

        def get_priority(currency_name):
            for i, code in enumerate(popular_order):
                if f'({code})' in currency_name:
                    return i
            return len(popular_order)

        # Сортируем все валюты кроме первой (RUB)
        other_currencies = currencies[1:]
        other_currencies.sort(key=lambda x: get_priority(x['name']))
        currencies = [currencies[0]] + other_currencies

        print(f"Успешно получено {len(currencies)} валют")
        return currencies

    except Exception as e:
        print(f"Ошибка при получении данных с ЦБ РФ: {e}")
        # Возвращаем пустой список в случае ошибки
        return []


def calculate_exchange(amount, from_currency, to_currency, currencies, rate_type='cb'):
    """
    Рассчитывает конвертацию между валютами

    rate_type: 'cb' - курс ЦБ, 'buy' - покупка, 'sell' - продажа
    """
    if not currencies or amount <= 0:
        return None

    # Находим валюты в списке
    from_curr = next((c for c in currencies if c['name'] == from_currency), None)
    to_curr = next((c for c in currencies if c['name'] == to_currency), None)

    if not from_curr or not to_curr:
        return None

    # Если конвертируем из RUB в другую валюту
    if from_currency == 'Российский рубль (RUB)':
        if rate_type == 'buy':
            # Для покупки иностранной валюты за RUB используем курс продажи банка
            rate = 1 / to_curr['sell_float'] if to_curr['sell_float'] > 0 else 0
        elif rate_type == 'sell':
            # Для продажи иностранной валюты за RUB используем курс покупки банка
            rate = 1 / to_curr['buy_float'] if to_curr['buy_float'] > 0 else 0
        else:  # cb
            rate = 1 / to_curr['cb_float'] if to_curr['cb_float'] > 0 else 0
        result = amount * rate

    # Если конвертируем в RUB из другой валюты
    elif to_currency == 'Российский рубль (RUB)':
        if rate_type == 'buy':
            rate = from_curr['buy_float']
        elif rate_type == 'sell':
            rate = from_curr['sell_float']
        else:  # cb
            rate = from_curr['cb_float']
        result = amount * rate

    # Если конвертируем между двумя иностранными валютами
    else:
        # Сначала конвертируем из исходной валюты в RUB
        if rate_type == 'buy':
            rub_amount = amount * from_curr['buy_float']
            # Затем из RUB в целевую валюту
            result = rub_amount / to_curr['sell_float'] if to_curr['sell_float'] > 0 else 0
        elif rate_type == 'sell':
            rub_amount = amount * from_curr['sell_float']
            result = rub_amount / to_curr['buy_float'] if to_curr['buy_float'] > 0 else 0
        else:  # cb
            rub_amount = amount * from_curr['cb_float']
            result = rub_amount / to_curr['cb_float'] if to_curr['cb_float'] > 0 else 0

    return round(result, 4) if result else None


@app.route('/')
def index():
    """Главная страница с курсами валют и калькулятором"""
    currencies = get_currency_data()
    return render_template('index.html', currencies=currencies)


@app.route('/calculate', methods=['POST'])
def calculate():
    """API endpoint для расчета конвертации"""
    try:
        data = request.json
        amount = float(data.get('amount', 0))
        from_currency = data.get('from_currency')
        to_currency = data.get('to_currency')
        rate_type = data.get('rate_type', 'cb')

        currencies = get_currency_data()

        result = calculate_exchange(amount, from_currency, to_currency, currencies, rate_type)

        if result is not None:
            return jsonify({
                'success': True,
                'result': result,
                'from_amount': amount,
                'from_currency': from_currency,
                'to_currency': to_currency,
                'rate_type': rate_type
            })
        else:
            return jsonify({'success': False, 'error': 'Ошибка расчета'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/refresh')
def refresh():
    """Маршрут для обновления данных"""
    currencies = get_currency_data()
    return render_template('index.html', currencies=currencies)


@app.route('/status')
def status():
    """Проверка статуса подключения к ЦБ"""
    try:
        currencies = get_currency_data()
        status_message = f"Успешно! Получено {len(currencies)} валют"
        if len(currencies) > 0:
            status_message += f"<br>Первая валюта: {currencies[0]['name']}"
        return status_message
    except Exception as e:
        return f"Ошибка: {str(e)}"


if __name__ == '__main__':
    # Для работы в Docker/Render используйте 0.0.0.0
    import os
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5954))
    app.run(debug=False, host=host, port=port)
