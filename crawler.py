"""Download gallery images from Platesmania pages with undetected-chromedriver."""

import argparse
import csv
import mimetypes
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse, urlunparse

import requests
import undetected_chromedriver as uc

from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait


driver_lock = threading.Lock()

CARD_SELECTOR = (
    "body > div.wrapper > div.container.content > div > div.col-md-9 "
    ".panel.panel-grey"
)
VEHICLE_IMAGE_SELECTOR = (
    ".panel-body > div.row:first-child a > img, "
    ".panel-body > div.row:first-of-type a > img"
)
PLATE_IMAGE_SELECTOR = (
    ".panel-body .col-xs-offset-3.col-xs-6.text-center a > img"
)
FALLBACK_PLATE_IMAGE_SELECTOR = (
    ".panel-body img[src*='/inf/'], "
    ".panel-body img[src$='.png']"
)

IMAGE_ATTRIBUTES = ("src", "data-src", "data-original", "data-lazy-src")
DEFAULT_GALLERY_URLS = [
    "https://platesmania.com/la/gallery",
    "https://platesmania.com/kh/gallery",
    "https://platesmania.com/vn/gallery",
    "https://platesmania.com/cn/gallery",
]


def create_chrome(headless: bool) -> uc.Chrome:
    profile_dir = os.path.join(os.getcwd(), "chrome_profile")
    os.makedirs(profile_dir, exist_ok=True)

    options = uc.ChromeOptions()
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless=new")

    with driver_lock:
        try:
            driver = uc.Chrome(
                options=options,
                user_data_dir=profile_dir,
            )
        except Exception:
            print("Chrome failed to start. Retrying in 180 seconds...")
            time.sleep(180)
            driver = uc.Chrome(
                options=options,
                user_data_dir=profile_dir,
            )

    return driver


def wait_for_document(driver: uc.Chrome, timeout: int) -> None:
    WebDriverWait(driver, timeout).until(
        lambda browser: browser.find_elements(By.CSS_SELECTOR, CARD_SELECTOR)
        or browser.find_elements(By.TAG_NAME, "body")
    )


def first_element(parent, selector: str):
    elements = parent.find_elements(By.CSS_SELECTOR, selector)
    return elements[0] if elements else None


def image_url_from_element(image, page_url: str) -> str:
    for attribute in IMAGE_ATTRIBUTES:
        image_url = image.get_attribute(attribute)
        if image_url:
            return urljoin(page_url, image_url)
    return ""


def text_from_first(parent, selector: str) -> str:
    element = first_element(parent, selector)
    return element.text.strip() if element else ""


def get_gallery_items(driver: uc.Chrome, page_url: str) -> list[dict[str, str]]:
    items = []
    cards = driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR)

    for card in cards:
        vehicle_image = first_element(card, VEHICLE_IMAGE_SELECTOR)
        plate_image = first_element(card, PLATE_IMAGE_SELECTOR)
        if plate_image is None:
            plate_image = first_element(card, FALLBACK_PLATE_IMAGE_SELECTOR)

        vehicle_image_url = image_url_from_element(vehicle_image, page_url) if vehicle_image else ""
        plate_image_url = image_url_from_element(plate_image, page_url) if plate_image else ""

        if not vehicle_image_url and not plate_image_url:
            continue

        items.append({
            "vehicle_name": text_from_first(card, ".panel-body h4.text-center a"),
            "vehicle_generation": text_from_first(card, ".panel-body h4 + small p"),
            "vehicle_image_url": vehicle_image_url,
            "plate_image_url": plate_image_url,
        })

    return items


def safe_filename(url: str, index: int, content_type: str | None) -> str:
    parsed = urlparse(url)
    name = Path(unquote(parsed.path)).name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)

    if not name or "." not in name:
        extension = mimetypes.guess_extension(content_type or "") or ".jpg"
        name = f"image_{index:03d}{extension}"

    return f"{index:03d}_{name}"


def download_image(session: requests.Session, url: str, output_dir: Path, index: int) -> Path:
    response = session.get(url, timeout=30)
    response.raise_for_status()

    filename = safe_filename(url, index, response.headers.get("content-type"))
    output_path = output_dir / filename
    output_path.write_bytes(response.content)
    return output_path


def write_metadata(output_dir: Path, rows: list[dict[str, str]]) -> Path:
    metadata_path = output_dir / "metadata.csv"
    fieldnames = [
        "source_url",
        "vehicle_name",
        "vehicle_generation",
        "vehicle_image_url",
        "vehicle_image_path",
        "plate_image_url",
        "plate_image_path",
    ]

    with metadata_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return metadata_path


def country_code_from_url(url: str) -> str:
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    if path_parts:
        return re.sub(r"[^A-Za-z0-9._-]", "_", path_parts[0])

    host = urlparse(url).netloc or "unknown"
    return re.sub(r"[^A-Za-z0-9._-]", "_", host)


def page_slug_from_url(url: str) -> str:
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    if len(path_parts) >= 2:
        return re.sub(r"[^A-Za-z0-9._-]", "_", path_parts[1])
    return "gallery"


def expand_gallery_urls(urls: list[str], pages: int) -> list[str]:
    expanded_urls = []
    seen = set()

    for url in urls:
        parsed = urlparse(url)
        base_path = re.sub(r"/gallery(?:-\d+)?/?$", "/gallery", parsed.path)
        for page in range(pages):
            path = base_path if page == 0 else f"{base_path}-{page}"
            paginated_url = urlunparse(parsed._replace(path=path))
            if paginated_url not in seen:
                expanded_urls.append(paginated_url)
                seen.add(paginated_url)

    return expanded_urls


def download_images(
    url: str,
    timeout: int,
    headless: bool,
    output_dir: Path,
    driver: uc.Chrome | None = None,
) -> list[dict[str, str]]:
    owns_driver = driver is None
    if driver is None:
        driver = create_chrome(headless)

    try:
        driver.get(url)
        wait_for_document(driver, timeout)
        time.sleep(2)

        items = get_gallery_items(driver, url)
        if not items:
            print(f"Warning: no matching gallery items found on {url}")
            return []

        vehicle_output_dir = output_dir / "vehicles"
        plate_output_dir = output_dir / "plates"
        vehicle_output_dir.mkdir(parents=True, exist_ok=True)
        plate_output_dir.mkdir(parents=True, exist_ok=True)

        session = requests.Session()
        session.headers.update({
            "User-Agent": driver.execute_script("return navigator.userAgent;")
        })
        for cookie in driver.get_cookies():
            session.cookies.set(cookie["name"], cookie["value"])

        rows = []
        for index, item in enumerate(items, start=1):
            vehicle_path = ""
            plate_path = ""

            if item["vehicle_image_url"]:
                vehicle_path = str(
                    download_image(session, item["vehicle_image_url"], vehicle_output_dir, index)
                )
            if item["plate_image_url"]:
                plate_path = str(
                    download_image(session, item["plate_image_url"], plate_output_dir, index)
                )

            rows.append({
                "source_url": url,
                "vehicle_name": item["vehicle_name"],
                "vehicle_generation": item["vehicle_generation"],
                "vehicle_image_url": item["vehicle_image_url"],
                "vehicle_image_path": vehicle_path,
                "plate_image_url": item["plate_image_url"],
                "plate_image_path": plate_path,
            })

        write_metadata(output_dir, rows)
        return rows
    finally:
        if owns_driver:
            driver.quit()


def download_galleries(
    urls: list[str],
    timeout: int,
    headless: bool,
    output_dir: Path,
    captcha: bool,
    pages_arg: int,
) -> dict[str, list[dict[str, str]]]:
    driver = create_chrome(headless)
    try:
        if captcha and urls:
            driver.get(urls[0])
            print(f"\nOpened {urls[0]}")
            print("Solve the captcha manually in the browser window.")
            print('Then type "ok" and press Enter to continue:')
            while input().strip().lower() != "ok":
                print('Type "ok" to continue:')

        expanded_urls = expand_gallery_urls(urls, pages_arg)

        results = {}
        for url in expanded_urls:
            country_code = country_code_from_url(url)
            country_output_dir = output_dir / country_code / page_slug_from_url(url)
            try:
                results[url] = download_images(
                    url, timeout, headless, country_output_dir, driver=driver,
                )
            except TimeoutException:
                print(f"Warning: timed out waiting for page content on {url}")
                results[url] = []
        return results
    finally:
        driver.quit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crawl ảnh biển số xe từ platesmania.com"
    )
    parser.add_argument(
        "urls", nargs="*",
        help="URLs gallery. Mặc định Lào, Campuchia, Việt Nam, Trung Quốc.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("downloads"))
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument(
        "--pages", type=int, default=100,
        help="Số trang cần crawl (mặc định 100 = gallery → gallery-99)",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Chạy ẩn trình duyệt (mặc định hiện cửa sổ)",
    )
    parser.add_argument(
        "--captcha", action="store_true",
        help="Dừng ở trang đầu để giải captcha, gõ 'ok' để tiếp tục",
    )
    args = parser.parse_args()

    urls = args.urls or DEFAULT_GALLERY_URLS
    results = download_galleries(
        urls, args.timeout, args.headless, args.output_dir, args.captcha, args.pages,
    )

    total = sum(len(items) for items in results.values())
    print(f"\nDone! Scraped {total} item(s).")
    for url, items in results.items():
        print(f"  {url}: {len(items)} item(s)")


if __name__ == "__main__":
    main()
