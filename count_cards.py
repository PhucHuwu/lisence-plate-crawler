"""Download gallery images from Platesmania pages with Selenium."""

import argparse
import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse, urlunparse

import requests

from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


TABLE_SELECTOR = "body > div.wrapper > div.container.content > div > div.col-md-9"
CARD_SELECTOR = (
    "body > div.wrapper > div.container.content > div > div.col-md-9 "
    "> div:nth-child(5) > div:nth-child(1)"
)
IMAGE_SELECTOR = (
    "body > div.wrapper > div.container.content > div > div.col-md-9 "
    ".panel.panel-grey > .panel-body > div.row:first-child a > img"
)
FALLBACK_IMAGE_SELECTOR = (
    "body > div.wrapper > div.container.content > div > div.col-md-9 "
    ".panel.panel-grey img[src*='/m/']"
)

IMAGE_ATTRIBUTES = ("src", "data-src", "data-original", "data-lazy-src")
DEFAULT_GALLERY_URLS = [
    "https://platesmania.com/la/gallery",
    "https://platesmania.com/kh/gallery",
    "https://platesmania.com/vn/gallery",
    "https://platesmania.com/cn/gallery",
]


def count_cards(url: str, timeout: int, headless: bool) -> int:
    """Count card containers on one gallery page."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")

    driver = Chrome(options=options)
    try:
        driver.get(url)

        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, TABLE_SELECTOR))
        )

        cards = driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR)
        return len(cards)
    finally:
        driver.quit()


def get_image_urls(driver: Chrome, page_url: str) -> list[str]:
    """Collect image URLs from the rendered gallery page."""
    images = driver.find_elements(By.CSS_SELECTOR, IMAGE_SELECTOR)
    if not images:
        images = driver.find_elements(By.CSS_SELECTOR, FALLBACK_IMAGE_SELECTOR)

    urls = []
    seen = set()

    for image in images:
        image_url = None
        for attribute in IMAGE_ATTRIBUTES:
            image_url = image.get_attribute(attribute)
            if image_url:
                break

        if not image_url:
            continue

        absolute_url = urljoin(page_url, image_url)
        if "/m/" not in urlparse(absolute_url).path:
            continue

        if absolute_url not in seen:
            urls.append(absolute_url)
            seen.add(absolute_url)

    return urls


def safe_filename(url: str, index: int, content_type: str | None) -> str:
    """Build a safe local filename for one downloaded image."""
    parsed = urlparse(url)
    name = Path(unquote(parsed.path)).name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)

    if not name or "." not in name:
        extension = mimetypes.guess_extension(content_type or "") or ".jpg"
        name = f"image_{index:03d}{extension}"

    return f"{index:03d}_{name}"


def download_image(session: requests.Session, url: str, output_dir: Path, index: int) -> Path:
    """Download one image and return its saved path."""
    response = session.get(url, timeout=30)
    response.raise_for_status()

    filename = safe_filename(url, index, response.headers.get("content-type"))
    output_path = output_dir / filename
    output_path.write_bytes(response.content)
    return output_path


def country_code_from_url(url: str) -> str:
    """Extract the country code path segment from a gallery URL."""
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    if path_parts:
        return re.sub(r"[^A-Za-z0-9._-]", "_", path_parts[0])

    host = urlparse(url).netloc or "unknown"
    return re.sub(r"[^A-Za-z0-9._-]", "_", host)


def page_slug_from_url(url: str) -> str:
    """Extract the gallery page slug from a URL for output folders."""
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    if len(path_parts) >= 2:
        return re.sub(r"[^A-Za-z0-9._-]", "_", path_parts[1])

    return "gallery"


def paginated_gallery_urls(url: str, pages: int) -> list[str]:
    """Build gallery pagination URLs like gallery, gallery-1, gallery-2."""
    parsed = urlparse(url)
    base_path = re.sub(r"/gallery(?:-\d+)?/?$", "/gallery", parsed.path)
    urls = []

    for page in range(pages):
        path = base_path if page == 0 else f"{base_path}-{page}"
        urls.append(urlunparse(parsed._replace(path=path)))

    return urls


def expand_gallery_urls(urls: list[str], pages: int) -> list[str]:
    """Expand each gallery URL into its requested pagination range."""
    expanded_urls = []
    seen = set()

    for url in urls:
        for paginated_url in paginated_gallery_urls(url, pages):
            if paginated_url not in seen:
                expanded_urls.append(paginated_url)
                seen.add(paginated_url)

    return expanded_urls


def download_images(
    url: str,
    timeout: int,
    headless: bool,
    output_dir: Path,
    driver: Chrome | None = None,
) -> list[Path]:
    """Download all selected images from one gallery page."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")

    owns_driver = driver is None
    if driver is None:
        driver = Chrome(options=options)

    try:
        driver.get(url)

        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, TABLE_SELECTOR))
        )

        image_urls = get_image_urls(driver, url)
        if not image_urls:
            print(f"Warning: no matching images found on {url}")
            return []

        output_dir.mkdir(parents=True, exist_ok=True)

        session = requests.Session()
        session.headers.update(
            {"User-Agent": driver.execute_script("return navigator.userAgent;")}
        )
        for cookie in driver.get_cookies():
            session.cookies.set(cookie["name"], cookie["value"])

        return [
            download_image(session, image_url, output_dir, index)
            for index, image_url in enumerate(image_urls, start=1)
        ]
    finally:
        if owns_driver:
            driver.quit()


def download_galleries(
    urls: list[str], timeout: int, headless: bool, output_dir: Path
) -> dict[str, list[Path]]:
    """Download selected images from multiple gallery pages."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")

    driver = Chrome(options=options)
    try:
        results = {}
        for url in urls:
            country_code = country_code_from_url(url)
            country_output_dir = output_dir / country_code / page_slug_from_url(url)
            try:
                results[url] = download_images(
                    url,
                    timeout,
                    headless,
                    country_output_dir,
                    driver=driver,
                )
            except TimeoutException:
                print(f"Warning: timed out waiting for page content on {url}")
                results[url] = []
        return results
    finally:
        driver.quit()


def main() -> None:
    """Parse CLI arguments and download gallery images."""
    parser = argparse.ArgumentParser(
        description="Download images from a page using Selenium and a CSS selector."
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="URLs of gallery pages to inspect. Defaults to Laos, Cambodia, Vietnam, and China.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("downloads"),
        help="Directory where downloaded images will be saved",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="Seconds to wait for the page content to appear",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="Number of gallery pages to download: gallery, gallery-1, gallery-2...",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Run Chrome with a visible browser window instead of headless mode",
    )
    args = parser.parse_args()

    urls = expand_gallery_urls(args.urls or DEFAULT_GALLERY_URLS, args.pages)
    results = download_galleries(
        urls,
        args.timeout,
        not args.show_browser,
        args.output_dir,
    )

    total = sum(len(paths) for paths in results.values())
    print(f"Downloaded {total} image(s).")
    for url, paths in results.items():
        print(f"{url}: {len(paths)} image(s)")
        for path in paths:
            print(path)


if __name__ == "__main__":
    main()
