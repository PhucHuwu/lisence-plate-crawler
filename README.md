# License Plate Crawler

Crawl ảnh biển số xe từ [platesmania.com](https://platesmania.com) bằng `undetected-chromedriver`.

## Cài đặt

```bash
pip install -r requirements.txt
```

## Cách chạy

Mặc định crawl Lào, Campuchia, Việt Nam, Trung Quốc, mỗi nước 100 trang:

```bash
# Chạy lần đầu, dừng để giải captcha, sau đó nhập "ok" vào terminal để tiếp tục
python3 crawler.py --captcha
```
```bash
# Chạy sau khi đã giải captcha, có giới hạn số trang cần crawl
python3 crawler.py --pages 20
```
```bash
# Chạy sau khi đã giải captcha, chạy đủ 100 trang
python3 crawler.py
```

## Cấu trúc thư mục output

```
downloads/
├── la/
│   ├── gallery/
│   │   ├── vehicles/ (ảnh xe)
│   │   ├── plates/   (ảnh biển số)
│   │   └── metadata.csv
│   ├── gallery-1/
│   └── ...
├── kh/
├── vn/
└── cn/
```
