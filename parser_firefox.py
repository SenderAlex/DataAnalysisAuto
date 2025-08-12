import json
import re
import time
import random
import os
from transliterate import translit
from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import zipfile


def save_to_json(data, filename="items.json"):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def create_firefox_proxy_auth_extension(proxy_host, proxy_port, proxy_username, proxy_password, extension_path):
    """
    Создаёт временное расширение .xpi для Firefox с прокси и авторизацией
    """
    manifest_json = """
    {
      "manifest_version": 2,
      "name": "Firefox Proxy",
      "version": "1.0.0",
      "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"],
      "background": {"scripts": ["background.js"]},
      "applications": { "gecko": { "id": "proxy-auth@example.com"} }
    }
    """
    background_js = f"""
    var config = {{
            mode: "fixed_servers",
            rules: {{
            singleProxy: {{
                scheme: "http",
                host: "{proxy_host}",
                port: parseInt({proxy_port})
            }},
            bypassList: ["localhost"]
            }}
        }};
    browser.proxy.settings.set({{value: config}});
    function callbackFn(details) {{
        return {{
            authCredentials: {{
                username: "{proxy_username}",
                password: "{proxy_password}"
            }}
        }};
    }}
    browser.webRequest.onAuthRequired.addListener(
        callbackFn,
        {{urls: ["<all_urls>"]}},
        ['blocking']
    );
    """
    with zipfile.ZipFile(extension_path, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)


def get_firefox_options(user_agent=None, extension_path=None):
    options = FirefoxOptions()
    options.add_argument('-headless')

    if user_agent:
        options.set_preference("general.useragent.override", user_agent)

    # Скроем webdriver
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference('useAutomationExtension', False)
    options.set_preference("privacy.resistFingerprinting", True)

    if extension_path:
        options.set_preference("xpinstall.signatures.required", False)
        options.add_argument(f'-install-addon={extension_path}')

    return options


def parse_avito(driver, city, car_brand, car_model, car_year=None, max_mileage=None, max_pages=5):
    base_url = f"https://www.avito.ru/{city}/avtomobili/{car_brand}/{car_model}?p={{page}}"
    page = 1
    results = []

    while page <= max_pages:
        url = base_url.format(page=page)
        driver.get(url)
        time.sleep(random.uniform(5, 15))

        try:
            wait = WebDriverWait(driver, 15)
            blocks = wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[data-marker='item']"))
            )
        except Exception:
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

                    if car_year and str(car_year) != car_year_text:
                        continue

                    price_text = block.find_element(By.CSS_SELECTOR, "[itemprop='offers']").text
                    price = int(''.join(filter(str.isdigit, price_text))) if price_text else 0

                    image_links = block.find_elements(By.CSS_SELECTOR, "[itemprop='image']")
                    image_link = image_links[-1].get_attribute('srcset').split(',')[-1].strip().split()[0]

                    properties = block.find_element(By.CSS_SELECTOR, "[data-marker='item-specific-params']").text.split(',')
                    props = [p.strip() for p in properties]

                    if len(props) > 0 and "км" not in props[0]:
                        props.insert(0, '')

                    horse_power = props[1] if len(props) > 1 else ""
                    match_horse_power = re.search(r'(\d+)\s*л\.с\.', horse_power)
                    horsepower = int(match_horse_power.group(1)) if match_horse_power else 0

                    body = props[2] if len(props) > 2 else ""
                    drive = props[3] if len(props) > 3 else ""
                    fuel = props[4] if len(props) > 4 else ""

                    mileage = None
                    for prop in props:
                        if 'км' in prop:
                            mileage_str = ''.join(filter(str.isdigit, prop))
                            mileage = int(mileage_str) if mileage_str else None

                    if max_mileage and mileage is not None and mileage > max_mileage:
                        continue

                    link = block.find_element(By.CSS_SELECTOR, "[itemprop='url']").get_attribute('href')

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
                        'city': city
                    })
            except Exception:
                continue
        page += 1
    return results


def monitor_prices(driver, selected_ads, check_interval_sec=3600):
    print(f"Запущен мониторинг {len(selected_ads)} объявлений. Проверка раз в {check_interval_sec // 60} минут.")
    prices = {ad['url']: ad['price'] for ad in selected_ads}
    save_to_json(selected_ads, "monitoring_selected_avto.json")
    print("Данные выбранных объявлений сохранены в monitoring_selected_avto.json\n")

    try:
        while True:
            for ad in selected_ads:
                driver.get(ad['url'])
                time.sleep(5)
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

            print(f"Следующая проверка через {check_interval_sec // 60} минут...")
            time.sleep(check_interval_sec)
    except KeyboardInterrupt:
        print("Мониторинг остановлен пользователем.")


def main():
    proxy_ip = '212.193.162.92'
    proxy_port = '63555'
    proxy_user = 'EnxeHnz3'
    proxy_pass = '7jGeSJkP'

    # Интерактивный ввод пользователя
    brand = input("Введите марку автомобиля (например, toyota): ").strip().replace(" ", "_").lower()
    model = input("Введите модель автомобиля (например, camry): ").strip().replace(" ", "_").lower()
    city = input("Введите город расположения автомобиля (например, Москва): ").strip().lower()
    city = translit(city, 'ru', reversed=True)
    year = input("Введите год выпуска (опционально, Enter чтобы пропустить): ").strip()
    max_mileage = input("Введите максимальный пробег (опционально, Enter чтобы пропустить): ").strip()

    year = int(year) if year.isdigit() else None
    max_mileage = int(max_mileage) if max_mileage.isdigit() else None

    extension_path = os.path.abspath('proxy_auth.xpi')
    create_firefox_proxy_auth_extension(proxy_ip, proxy_port, proxy_user, proxy_pass, extension_path)

    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0"
    options = get_firefox_options(user_agent=user_agent, extension_path=extension_path)

    geckodriver_path = 'geckodriver.exe'  # Измените на ваш путь к geckodriver
    service = FirefoxService(executable_path=geckodriver_path)

    driver = Firefox(service=service, options=options)
    driver.delete_all_cookies()

    try:
        print("Ищу подходящие объявления на Avito... Подождите...")

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
        if os.path.exists(extension_path):
            os.remove(extension_path)


if __name__ == "__main__":
    main()
