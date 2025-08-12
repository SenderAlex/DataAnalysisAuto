import json
import re
import time
import random
from transliterate import translit
from seleniumwire import webdriver
from selenium_stealth import stealth
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def save_to_json(data, filename="items.json"):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def parse_avito(driver, city, car_brand, car_model, car_year=None, max_mileage=None, max_pages=5):
    base_url = f"https://www.avito.ru/{city}/avtomobili/s_probegom/{car_brand}/{car_model}?p={{page}}"
    page = 1
    results = []

    car_brand = car_brand.replace("_", " ")
    car_model = car_model.replace("_", " ")

    while page <= max_pages:
        url = base_url.format(page=page)
        driver.get(url)
        time.sleep(random.uniform(5, 15))

        try:
            wait = WebDriverWait(driver, 15)
            blocks = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[data-marker='item']")))
        except:
            break

        if not blocks:
            break

        for block in blocks:
            try:
                title_text = block.find_element(By.CSS_SELECTOR, "[itemprop='name']").text.lower()
                if car_brand.lower() in title_text and car_model.lower() in title_text:
                    title_parts = [part.strip() for part in title_text.split(',')]
                    car_brand_text = title_parts[0] if len(title_text) > 0 else ""
                    car_year_text = title_parts[1] if len(title_parts) > 1 else ""

                    # Если введён год, фильтруем
                    if car_year and str(car_year) != car_year_text:
                        continue

                    price_text = block.find_element(By.CSS_SELECTOR, "[itemprop='offers']").text
                    price = int(''.join(filter(str.isdigit, price_text))) if price_text else 0

                    # image_links = block.find_elements(By.CSS_SELECTOR, "[itemprop='image']")
                    # image_link = image_links[-1].get_attribute('srcset').split(',')[-1].strip().split()[0]

                    # image_links = []
                    # try:
                    #     slider_list = block.find_element(By.CSS_SELECTOR,
                    #                                      "div.photo-slider-photoSlider-u7UAa > ul.photo-slider-list-R0jle")
                    #     list_items = slider_list.find_elements(By.TAG_NAME, "li")
                    #     for item in list_items:
                    #         img = item.find_element(By.TAG_NAME, "img")
                    #         src = img.get_attribute("src")
                    #         if src and src not in image_links:
                    #             image_links.append(src)
                    #         srcset = img.get_attribute("srcset")
                    #         if srcset:
                    #             srcset_urls = [s.strip().split()[0] for s in srcset.split(",")]
                    #             # Добавляем самые большие картинки из srcset
                    #             largest_img_url = srcset_urls[-1]
                    #             if largest_img_url not in image_links:
                    #                 image_links.append(largest_img_url)
                    # except Exception:
                    #     pass
                    #
                    # image_link = list(set(image_links))

                    properties = block.find_element(By.CSS_SELECTOR, "[data-marker='item-specific-params']").text.split(',')
                    props = [p.strip() for p in properties]

                    if len(props) > 0 and "км" not in props[0]:
                        props.insert(0, '')

                    horse_power = props[1] if len(props) > 1 else ""
                    match_horse_power = re.search(r'(\d+)\s*л\.с\.', horse_power)
                    horsepower = 0
                    if match_horse_power:
                        horsepower = int(match_horse_power.group(1))

                    body = props[2] if len(props) > 2 else ""
                    drive = props[3] if len(props) > 3 else ""
                    fuel = props[4] if len(props) > 4 else ""

                    mileage = None
                    for prop in props:
                        if 'км' in prop:
                            mileage_str = ''.join(filter(str.isdigit, prop))
                            mileage = int(mileage_str) if mileage_str else None

                    # Фильтрация по пробегу
                    if max_mileage and mileage is not None and mileage > max_mileage:
                        continue

                    link = block.find_element(By.CSS_SELECTOR, "[itemprop='url']").get_attribute('href')

                    driver.get(link)
                    time.sleep(3)

                    image_links = set()

                    # Найти правую кнопку для переключения слайдов
                    next_button = driver.find_element(By.CSS_SELECTOR,
                                                      'div[data-marker="extended-gallery-frame/control-right"] button')

                    # Найти контейнер с текущим изображением
                    image_container = driver.find_element(By.CSS_SELECTOR,
                                                          'div[data-marker="extended-gallery/frame-img"] img')

                    # Собираем первую картинку
                    image_links.add(image_container.get_attribute('src'))

                    # Чтобы не зациклиться, ограничим количество переключений, например, 50
                    max_swipes = 50

                    for _ in range(max_swipes):
                        next_button.click()
                        time.sleep(1)  # Ждем прогрузки новой картинки
                        url = image_container.get_attribute('src')
                        if url in image_links:
                            # Если ссылка уже была, значит карусель зациклиться, прекращаем
                            break
                        image_links.add(url)

                    image_link = list(image_links)


                    results.append({
                        "title": car_brand_text,
                        "year": car_year_text,
                        "price": price,
                        "mileage": mileage,
                        "url": link,
                        'horse_power': horsepower,
                        'body': body,
                        'drive': drive,
                        'fuel': fuel,
                        'image_link': image_link,
                        'city': translit(city, 'ru', reversed=False).capitalize()
                    })
            except Exception:
                continue
        page += 1
    return results


def monitor_prices(driver, selected_ads, check_interval_sec=3600):
    print(f"Запущен мониторинг {len(selected_ads)} объявлений. Проверка раз в {check_interval_sec//60} минут.")
    prices = {}
    for ad in selected_ads:
        prices[ad['url']] = ad['price']
    save_to_json(selected_ads, "monitoring_selected_avito_ru.json")

    try:
        while True:
            for ad in selected_ads:
                driver.get(ad['url'])
                time.sleep(5)  # ждём загрузки
                try:
                    price_el = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "[itemprop='price']"))
                    )
                    price_text = price_el.get_attribute('content') or price_el.text
                    current_price = int(''.join(filter(str.isdigit, price_text)))
                except Exception:
                    print(f"Не удалось получить цену для {ad['url']}")
                    continue

                old_price = prices.get(ad['url'])
                if current_price != old_price:
                    print(f"Цена изменилась!\nОбъявление: {ad['title']}\nURL: {ad['url']}\nСтарая цена: {old_price}\nНовая цена: {current_price}\n")
                    prices[ad['url']] = current_price
                else:
                    print(f"Цена без изменений для {ad['title']} - {current_price}")

            print(f"Следующая проверка через {check_interval_sec//60} минут...")
            time.sleep(check_interval_sec)
    except KeyboardInterrupt:
        print("Мониторинг остановлен пользователем.")


def main():
    options = webdriver.ChromeOptions()
    options.add_argument("start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    ### прокси
    proxy_ip = '212.193.162.92'
    proxy_port = '63555'
    proxy_user = 'EnxeHnz3'
    proxy_pass = '7jGeSJkP'

    proxy_string = f'socks5://{proxy_user}:{proxy_pass}@{proxy_ip}:{proxy_port}'

    # Настройка прокси с авторизацией (selenium-wire)
    seleniumwire_options = {
        'proxy': {
            'http': proxy_string,
            'https': proxy_string,
            'no_proxy': 'localhost,127.0.0.1'
        }
    }

    driver = webdriver.Chrome(seleniumwire_options=seleniumwire_options, options=options)
    ###
    #driver = webdriver.Chrome(options=options)

    stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win64",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True)

    try:
        brand = input("Введите марку автомобиля (например, toyota): ").strip().replace(" ", "_").lower()
        model = input("Введите модель автомобиля (например, camry): ").strip().replace(" ", "_").lower()
        city = input("Введите город расположения автомобиля (например, Москва): ").strip().lower()
        city = translit(city, 'ru', reversed=True)
        year = input("Введите год выпуска (опционально, Enter чтобы пропустить): ").strip()
        max_mileage = input("Введите максимальный пробег (опционально, Enter чтобы пропустить): ").strip()

        year = int(year) if year.isdigit() else None
        max_mileage = int(max_mileage) if max_mileage.isdigit() else None

        print("Ищу подходящие объявления на avito.ru... Подождите...")

        ads = parse_avito(driver, city, brand, model, year, max_mileage)

        if not ads:
            print("Объявления по запросу не найдены.")
            return

        print("\nНайденные объявления:")
        for idx, ad in enumerate(ads):
            print(f"[{idx}] {ad['title']} | Год: {ad['year']} | Цена: {ad['price']} | Пробег: {ad['mileage']} |"
                  f" Фото: {ad['image_link']} | Л.С. {ad['horse_power']} | Кузов: {ad['body']} | "
                  f"Привод: {ad['drive']} | Вид топлива: {ad['fuel']} | URL: {ad['url']} | Город: {ad['city']}")

        selected = input("Введите индексы объявлений для мониторинга, через запятую (например: 1,2,3): ").strip()
        selected_indexes = [int(s) for s in selected.split(",") if s.strip().isdigit() and int(s.strip()) < len(ads)]

        selected_ads = [ads[i] for i in selected_indexes]
        if not selected_ads:
            print("Вы ничего не выбрали для мониторинга, завершаю.")
            return

        monitor_prices(driver, selected_ads)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
