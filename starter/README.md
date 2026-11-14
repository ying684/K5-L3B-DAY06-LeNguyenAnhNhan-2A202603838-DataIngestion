# Chạy pipeline Day 06

## Setup

Môi trường đã chạy: Python 3.11.18, pypdf 6.21.4, psycopg 3.3.8, python-dotenv 1.2.4; PostgreSQL 16.16 và pgvector 0.8.7.

Chạy từ thư mục `starter/`:

```powershell
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose -p day6_student_starter up -d --wait
python -B scripts/check_setup.py
```

Điền `OPENROUTER_API_KEY` và `EMBEDDING_MODEL=baai/bge-m3` vào .env local. Giữ DATABASE_URL theo cấu hình Docker, cổng local 55433. Không commit .env hoặc key.

Đặt PDF tại `data/raw/book_ML_color.pdf`. Dùng bản sách 400 trang, cập nhật 27/03/2018; nguồn, quyền sử dụng, SHA-256 và phạm vi trang ghi trong [manifest](../data/manifest.json). Cách lấy và kiểm tra bản sách tại [README chính](../README.md).

## Chạy thí nghiệm

```powershell
python -B -m src.run prepare
python -B -m src.run dev --allow-api
python -B -m src.run test --allow-api
python -B -m src.run audit
python -B scripts/finalize_results.py
```

- `prepare`: đọc 32 trang PDF 78–109, chuẩn hóa, chia chunk, kiểm tra evidence, lưu stats và hash.
- `dev`: embedding OpenRouter `baai/bge-m3`, 1024 chiều; lưu PostgreSQL, kiểm tra nạp lại không trùng, truy xuất cosine exact top-3 và chọn cấu hình.
- `test`: chạy sau khi chốt dev và khi hash còn khớp.
- `audit`: tạo bảng coherence, grounding và metadata nếu file chưa tồn tại.
- `finalize_results.py`: đối chiếu trace/summary, tổng hợp nhãn audit và cập nhật experiment log; không gọi API.

A dùng cửa sổ 500 ký tự/overlap 50; B nhóm đoạn tối đa 1000/overlap 0; C dùng chunk/vector B và thêm chapter filter từ câu hỏi. Model, corpus, store và benchmark giữ nguyên giữa ba cấu hình.

API chỉ được gọi khi có `--allow-api`; batch tối đa 16, không retry hoặc fallback model. Alias response `parasail-bge-m3` được ghi cùng model yêu cầu và provider. Cache ở `.cache/embeddings/` giúp tái sử dụng vector, không cần gọi API riêng cho C.

Project đã có kết quả dev/test. CLI từ chối chạy lại tập đã có trace. Để kiểm tra kết quả hiện tại, chỉ chạy:

```powershell
python -B scripts/finalize_results.py
python -B -m unittest discover -s tests -v
```

Tests dùng response giả lập offline; kết quả retrieval lấy từ các lượt API thật đã lưu.

## Kết quả và audit

- `results/prepared/`: text chuẩn hóa, chunk A/B và plan. C dùng chung chunk B.
- `results/runs/`: log cả thất bại/thành công, usage, trace và summary.
- `results/audit/`: 30 dòng coherence, 15 grounding, 45 metadata, kèm nhãn và lý do.
- `results/summary.csv`, `results/consolidated.json`: kết quả tổng hợp.
- `../artifacts/`: protocol, lựa chọn dev và experiment log.

Coherence/grounding dùng thang 0–2; metadata/filter dùng 0/1, không yêu cầu filter ghi N/A. Phương pháp, kết quả và giới hạn đánh giá nằm trong [báo cáo](../report/individual/2A202603838_LeNguyenAnhNhan.md). Sau khi sửa nhãn, chạy lại script tổng hợp; không sửa trace hoặc gold.

Giữ raw PDF và cache ở local theo .gitignore. Dừng database nhưng giữ dữ liệu:

```powershell
docker compose -p day6_student_starter stop
```
