# License Plate Crawler

Crawl ảnh biển số xe từ [platesmania.com](https://platesmania.com).

Mặc định crawl Lào, Campuchia, Việt Nam, Trung Quốc.

## Cài đặt

```bash
pip install -r requirements.txt
```

## Cách chạy

```bash
# Lần đầu: dừng để giải captcha, gõ "ok" vào terminal để tiếp tục
python3 crawler.py --captcha
```

```bash
# Sau khi đã giải captcha, chạy giới hạn số trang
python3 crawler.py --pages 20
```

```bash
# Sau khi đã giải captcha, chạy đủ 100 trang
python3 crawler.py
```

## Tuỳ chọn

| Flag | Mô tả |
|------|-------|
| `--pages N` | Số trang cần crawl (mặc định 100) |
| `--headless` | Chạy ẩn trình duyệt |
| `--timeout N` | Thời gian chờ tối đa mỗi trang (giây) |
| `--captcha` | Dừng ở trang đầu để giải captcha tay |
| `--output-dir` | Thư mục lưu ảnh (mặc định `downloads/`) |

## Cấu trúc output

```
downloads/
├── la/
│   ├── gallery/
│   │   ├── vehicles/   (ảnh xe)
│   │   ├── plates/     (ảnh biển số)
│   │   └── metadata.csv
│   ├── gallery-1/
│   └── ...
├── kh/
├── vn/
└── cn/
```

Profile Chrome tự động tạo ở `chrome_profile/` trong thư mục hiện tại.
