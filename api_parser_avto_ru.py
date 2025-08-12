import requests

TOKEN = "TOKEN"

headers = {
    'x-authorization': TOKEN,
    'Content-Type': 'application/json'}


def get_all_marks():
    url = 'https://apiauto.ru/1.0/reference/catalog/cars/marks'
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # проверка статуса
        return response.json().get("items", [])  # если True, то получишь словарь по ключу "items", если нет, то пустой []
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при получении марок авто: {e}")
        return []


def get_models_by_mark(mark_id):
    url = f'https://apiauto.ru/1.0/reference/catalog/cars/models?mark_id={mark_id}'
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get("items", [])
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при получении моделей mark_id {mark_id}: {e}")
        return []


def search_car_by_filter(mark_id, model_id, year_from=None, year_to=None, price_from=None, price_to=None,
                         mileage_from=None, mileage_to=None):
    url = f'https://apiauto.ru/1.0/search/cars/'

    payload = {
        'mark_id': mark_id,
        'model_id': model_id
    }

    if year_from is not None: payload['year_from'] = year_from
    if year_to is not None: payload['year_to'] = year_to
    if price_from is not None: payload['price_from'] = price_from
    if price_to is not None: payload['price_to'] = price_to
    if mileage_from is not None: payload['mileage_from'] = mileage_from
    if mileage_to is not None: payload['mileage_to'] = mileage_to

    try:
        response = requests.get(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json().get("items", [])
    except requests.exceptions.RequestException as e:
        print(f'Ошибка при поиске авто {e}')
        return []


def main():
    while True:
        user_mark_name = input('Введите марку автомобиля').strip().lower()

        mark_name = get_all_marks()
        mark_name_id = None

        for mark in mark_name:
            if mark.get('name', '') == user_mark_name:
                mark_name_id = mark.get('id', '')
                print(f'Найдена марка автомобиля {mark.get('name', '')} c ID: {mark_name_id}')
                break

        if mark_name_id is None:
            print(f'Марка автомобиля {user_mark_name} не найдена. Пожалуйста, введите корректное название.')

        user_model_name = input('Введите модель автомобиля').strip().lower()

        model_name = get_models_by_mark(mark_name_id)
        model_name_id = None

        for model in model_name:
            if model.get('name', '') == user_model_name:
                model_name_id = model.get('id', '')
                print(f'Найдена модель {model.get('name', '')} автомобиля {user_mark_name} c ID: {model_name_id}')
                break

        if model_name_id is None:
            print(f'Модель автомобиля {user_model_name} не найдена. Пожалуйста, введите корректное название.')

        year_from_input = input('Введите начальный год поиска. (Оставьте пустым для пропуска)')
        year_from = int(year_from_input) if year_from_input.isdigit() else None

        year_to_input = input('Введите конечный год поиска. (Оставьте пустым для пропуска)')
        year_to = int(year_to_input) if year_to_input.isdigit() else None

        price_from_input = input('Введите начальную цену поиска. (Оставьте пустым для пропуска)')
        price_from = int(price_from_input) if price_from_input.isdigit() else None

        price_to_input = input('Введите конечную цену поиска. (Оставьте пустым для пропуска)')
        price_to = int(price_to_input) if price_to_input.isdigit() else None

        mileage_from_input = input('Введите начальный пробег поиска. (Оставьте пустым для пропуска)')
        mileage_from = int(mileage_from_input) if mileage_from_input.isdigit() else None

        mileage_to_input = input('Введите конечный пробег поиска. (Оставьте пустым для пропуска)')
        mileage_to = int(mileage_to_input) if mileage_to_input.isdigit() else None

        print('\n Ищу объявления...')
        search_results = search_car_by_filter(mark_name_id, model_name_id, year_from, year_to, price_from, price_to,
                                              mileage_from, mileage_to)

        if search_results:
            print(f"Найдено {len(search_results)} объявлений")
            for index, result in enumerate(search_results):
                print(f'{index} | {result.get('title', 'None')} | {result.get('price', 'None')} рублей ')


if __name__ == '__main__':
    main()