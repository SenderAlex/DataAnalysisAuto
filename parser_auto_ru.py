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
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


def save_to_json(data, filename="items.json"):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def check_captcha(driver):
    try:
        # auto.ru использует div с классом captcha или iframe
        captcha = driver.find_element(By.CSS_SELECTOR, "div.captcha, iframe[src*='captcha']")
        if captcha.is_displayed():
            print("Обнаружена капча, ожидаем ручного решения...")
            while captcha.is_displayed():
                time.sleep(5)
            print("Капча решена.")
            return True
    except:
        return False


def parse_auto(driver, city, car_brand, car_model, car_year=None, max_mileage=None, max_pages=5):
    base_url = f"https://www.auto.ru/{city}/cars/{car_brand}/{car_model}/all/?page={{page}}"
    page = 1
    results = []

    car_brand = car_brand.replace("_", " ")
    car_model = car_brand.replace("_", " ")

    while page <= max_pages:
        url = base_url.format(page=page)
        driver.get(url)
        time.sleep(random.uniform(5, 10))

        if check_captcha(driver):
            print("Далее продолжаем после капчи")

        try:
            wait = WebDriverWait(driver, 15)
            blocks = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[data-seo='listing-item']")))
        except:
            break

        if not blocks:
            break

        for block in blocks:
            time.sleep(random.uniform(1, 3))
            try:
                title_text = block.find_element(By.CSS_SELECTOR, "a.ListingItemTitle__link").text.lower()
                if car_brand.lower() in title_text and car_model.lower() in title_text:
                    title_parts = [part.strip() for part in title_text.split(' ')]
                    car_brand_text = " ".join(title_parts[:2])

                    tech_summary = block.find_elements(By.CSS_SELECTOR, "div.ListingItemTechSummaryDesktop__cell")
                    tech_characteristics = [tech.text for tech in tech_summary]
                    engine_str = tech_characteristics[0]
                    parts = [part.strip() for part in engine_str.replace('\u2009', ' ').split('/')]
                    engine_volume = float(parts[0].split()[0])

                    horsepower_match = re.search(r'\d+', parts[1])
                    horse_power = int(horsepower_match.group()) if horsepower_match else None

                    fuel = parts[2].lower()
                    transmission = tech_characteristics[1]
                    body = tech_characteristics[2].split()[0]
                    drive = tech_characteristics[3]
                    color = tech_characteristics[4]

                    price_text = block.find_element(By.CSS_SELECTOR, "div.ListingItem__priceBlock").text.strip()
                    separate_price = price_text.split('\n')[0]
                    price = int(''.join(separate for separate in separate_price if separate.isdigit() or separate == ' ')
                                .replace(' ', ''))

                    car_year_text = block.find_element(By.CSS_SELECTOR, "div.ListingItem__yearBlock").text.strip()

                    # Если введён год, фильтруем
                    if car_year and str(car_year) != car_year_text:
                        continue

                    link = block.find_element(By.CSS_SELECTOR, "a.ListingItemTitle__link").get_attribute('href')

                    image_links = block.find_elements(By.CSS_SELECTOR, "img.LazyImage__image")
                    image_link = image_links[-1].get_attribute('srcset').split(',')[-1].strip().split()[0]
                    image_link = 'https:' + image_link

                    mileage = None
                    mileage_html = block.find_element(By.CSS_SELECTOR, "div.ListingItem__kmAge").text.strip()

                    if 'км' in mileage_html:
                        mileage_str = ''.join(filter(str.isdigit, mileage_html))
                        mileage = int(mileage_str) if mileage_str else None

                    # Фильтрация по пробегу
                    if max_mileage and mileage is not None and mileage > max_mileage:
                        continue

                    results.append({
                        "title": car_brand_text,
                        "year": car_year_text,
                        "price": price,
                        "mileage": mileage,
                        "url": link,
                        'horse_power': horse_power,
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
    save_to_json(selected_ads, "monitoring_selected_auto_ru.json")

    try:
        while True:
            for ad in selected_ads:
                driver.get(ad['url'])
                time.sleep(5)  # ждём загрузки
                try:
                    price_el = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "span.OfferPriceCaption__price"))
                    )

                    price_text = price_el.text
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
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)" \
                 " Chrome/100.0.4896.127 Safari/537.36"
    options.add_argument(f'user-agent={user_agent}')
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--no-sandbox")  # на случай запуска в Linux-серверах
    options.add_argument("start-maximized")

    ### прокси
    # proxy_ip = '212.193.162.92'
    # proxy_port = '63555'
    # proxy_user = 'EnxeHnz3'
    # proxy_pass = '7jGeSJkP'
    #
    # proxy_string = f'socks5://{proxy_user}:{proxy_pass}@{proxy_ip}:{proxy_port}'
    #
    # # Настройка прокси с авторизацией (selenium-wire)
    # seleniumwire_options = {
    #     'proxy': {
    #         'http': proxy_string,
    #         'https': proxy_string,
    #         'no_proxy': 'localhost,127.0.0.1'
    #     }
    # }
    #
    # driver = webdriver.Chrome(seleniumwire_options=seleniumwire_options,
    #                           service=Service(ChromeDriverManager().install()), options=options)
    ###

    seleniumwire_options = {
        'request_storage': 'memory',
    }

    driver = webdriver.Chrome(seleniumwire_options=seleniumwire_options,
                              service=Service(ChromeDriverManager().install()), options=options)


    stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win64",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
            run_on_insecure_origins=False
    )

    try:
        brand = input("Введите марку автомобиля (например, toyota): ").strip().replace(" ", "_").lower()
        model = input("Введите модель автомобиля (например, camry): ").strip().replace(" ", "_").lower()
        city = input("Введите город расположения автомобиля (например, Москва): ").strip().lower()
        city = translit(city, 'ru', reversed=True)
        year = input("Введите год выпуска (опционально, Enter чтобы пропустить): ").strip()
        max_mileage = input("Введите максимальный пробег (опционально, Enter чтобы пропустить): ").strip()

        year = int(year) if year.isdigit() else None
        max_mileage = int(max_mileage) if max_mileage.isdigit() else None

        print("Ищу подходящие объявления на auto.ru... Подождите...")

        ads = parse_auto(driver, city, brand, model, year, max_mileage)

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
