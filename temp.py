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
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException


def save_to_json(data, filename="items.json"):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def parse_avito(driver, city, car_brand, car_model, car_year=None, max_mileage=None, max_pages=5):
    base_url = f"https://www.avito.ru/{city}/avtomobili/s_probegom/{car_brand}/{car_model}?p={{page}}"
    results = []
    page = 1

    car_brand = car_brand.replace("_", " ")
    car_model = car_model.replace("_", " ")

    wait = WebDriverWait(driver, 15)

    while page <= max_pages:
        driver.get(base_url.format(page=page))
        time.sleep(random.uniform(5, 8))

        try:
            blocks = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[data-marker='item']")))
        except TimeoutException:
            print(f"Page {page}: объявления не найдены, прекращаем парсинг.")
            break

        if not blocks:
            print(f"Page {page}: блоки не найдены, останавливаемся.")
            break

        for block in blocks:
            try:
                link = block.find_element(By.CSS_SELECTOR, "[itemprop='url']").get_attribute('href')

                driver.get(link)

                # Ждем, пока загрузится заголовок
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1[data-marker='item-view/title-info']")))

                title_text = driver.find_element(By.CSS_SELECTOR, "h1[data-marker='item-view/title-info']").text.strip()
                title_parts = [part.strip() for part in title_text.split(',')]
                car_brand_text = title_parts[0] if title_parts else ""
                car_year_text = title_parts[1] if len(title_parts) > 1 else ""

                if car_year and str(car_year) != car_year_text:
                    continue

                try:
                    price_elem = driver.find_element(By.CSS_SELECTOR, "[itemprop='price']")
                    price_text = price_elem.get_attribute('content') or price_elem.text
                    price = int(''.join(filter(str.isdigit, price_text))) if price_text else 0
                except:
                    price = 0

                mileage = None
                car_params = {}

                try:
                    params_block = driver.find_element(By.CSS_SELECTOR,
                                                      "div#bx_item-params[data-marker='item-view/item-params']")
                    items = params_block.find_elements(By.CSS_SELECTOR, "ul.HRzg1 > li.cHzV4")
                except:
                    items = []

                for item in items:
                    try:
                        label = item.find_element(By.CSS_SELECTOR, "span.Lg7Ax").text.strip().replace(":", "")
                    except:
                        label = ""

                    full_text = item.text.strip()
                    value = full_text[len(label):].strip().lstrip(":").strip()

                    if label == "Тип двигателя":
                        car_params["fuel"] = value
                    elif label == "Привод":
                        car_params["drive"] = value
                    elif label == "Тип кузова":
                        car_params["body_type"] = value
                    elif label == "Модификация":
                        car_params["modification"] = value
                        hp_match = re.search(r"\((\d+)\s?л\.с\.?\)", value)
                        car_params["horse_power"] = int(hp_match.group(1)) if hp_match else None
                    elif label == "Пробег":
                        mileage_str = ''.join(filter(str.isdigit, value))
                        mileage = int(mileage_str) if mileage_str else None

                if mileage is None:
                    try:
                        desc_text = driver.find_element(By.CSS_SELECTOR, "[data-marker='item-description-text']").text
                        match = re.search(r"(\d[\d\s]*)\s?км", desc_text)
                        if match:
                            mileage_str = ''.join(filter(str.isdigit, match.group(1)))
                            mileage = int(mileage_str) if mileage_str else None
                    except:
                        pass

                if max_mileage and mileage is not None and mileage > max_mileage:
                    continue

                image_links = set()
                # Инициализация для обхода галереи
                max_swipes = 50
                last_image = None

                for i in range(max_swipes):
                    # Каждый раз пытаемся найти кнопку и картинку заново, чтобы избежать stale element
                    try:
                        next_button = wait.until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, 'div[data-marker="extended-gallery-frame/control-right"] button'))
                        )
                        image_container = wait.until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-marker="image-frame/image-wrapper"] img'))
                        )

                        current_image = image_container.get_attribute('src')
                        if current_image == last_image:
                            break
                        image_links.add(current_image)
                        last_image = current_image

                        next_button.click()
                        time.sleep(1)
                    except (StaleElementReferenceException, TimeoutException):
                        # Попробовать заново найти элементы на следующей итерации
                        time.sleep(0.5)
                        continue
                    except Exception:
                        break

                # Если не было картинок, попытаться добавить хотя бы первую картинку
                if not image_links:
                    try:
                        first_img = driver.find_element(By.CSS_SELECTOR, 'div[data-marker="image-frame/image-wrapper"] img').get_attribute('src')
                        if first_img:
                            image_links.add(first_img)
                    except:
                        pass

                results.append({
                    "title": car_brand_text,
                    "year": car_year_text,
                    "price": price,
                    "mileage": mileage,
                    "url": link,
                    "horse_power": car_params.get("horse_power", None),
                    "body": car_params.get("body_type", None),
                    "drive": car_params.get("drive", None),
                    "fuel": car_params.get("fuel", None),
                    "image_link": list(image_links),
                    "city": translit(city, 'ru', reversed=False).capitalize()
                })

            except Exception as e:
                print(f"Error processing listing at {link if 'link' in locals() else 'unknown URL'}: {e}")
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
