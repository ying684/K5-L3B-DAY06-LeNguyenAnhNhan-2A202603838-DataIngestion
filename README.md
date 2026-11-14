# Day 06 · Data Ingestion Engineering

Bài lab dùng 32 trang tiếng Việt của *Machine Learning cơ bản* (Vũ Hữu Tiệp, bản 27/03/2018) để so sánh ba cấu hình chunking/retrieval. Embedding: OpenRouter `baai/bge-m3`, 1024 chiều; lưu trữ: PostgreSQL + pgvector, cosine exact search.

## Kết quả hiện có

| Cấu hình | Số chunk | Dev Hit@1 | Dev Hit@3 | Test Hit@1 | Test Hit@3 |
|---|---:|---:|---:|---:|---:|
| A: fixed 500, overlap 50 | 167 | 9/15 | 12/15 | 4/5 | 4/5 |
| B: nhóm đoạn, tối đa 1000 | 97 | 12/15 | 14/15 | 4/5 | 4/5 |
| C: B + chapter filter | 97 | 12/15 | 14/15 | 4/5 | 4/5 |

B được chọn trên dev trước test theo quy tắc đã lưu. B/C bằng điểm; không kết luận metadata filter cải thiện Hit@3 trên bộ này. Ba bảng audit đã điền nhãn, lý do và reviewer; phương pháp đánh giá trình bày trong báo cáo.

## Đọc và kiểm tra bài làm

- [Báo cáo theo mẫu bốn mục](report/individual/2A202603838_LeNguyenAnhNhan.md).
- [Hướng dẫn setup/run](starter/README.md).
- [Manifest corpus](data/manifest.json): 32 trang PDF vật lý 78–109, chương 5–8.
- [Benchmark](benchmark/questions.json): 15 dev, 5 test; 3 câu filter dev, 1 câu filter test.
- [Protocol trước thí nghiệm](artifacts/protocol.json), [quyết định chọn B](artifacts/dev_selection.json), [experiment log](artifacts/experiment_log.csv).
- [Tổng hợp JSON](starter/results/consolidated.json), [bảng retrieval CSV](starter/results/summary.csv).
- [Trace, usage và log lỗi](starter/results/runs/), [nhãn audit](starter/results/audit/).
- [Thông tin học viên](STUDENT.md).

Từ thư mục `starter/`, tổng hợp và đối chiếu artifacts đã có, không gọi API:

```powershell
python -B scripts/finalize_results.py
python -B -m unittest discover -s tests -v
```

## Corpus và tái lập

PDF gốc giữ ở `starter/data/raw/book_ML_color.pdf` và không được Git theo dõi theo quy tắc ignore. Lấy bản sách qua nguồn tác giả tại https://machinelearningcoban.com/ebook/ theo quyền truy cập hợp lệ, dùng bản 400 trang cập nhật 27/03/2018. Đối chiếu SHA-256 với manifest trước khi chạy; bản khác có thể lệch trang và evidence.

```powershell
Get-FileHash -Algorithm SHA256 .\starter\data\raw\book_ML_color.pdf
```

Corpus, benchmark và code được khóa bằng hash trong log dev/test để đối chiếu khi tái lập.

## Tài liệu đề bài

Các quy định đề gốc được giữ trong [GUIDE](GUIDE.md), [BENCHMARK](BENCHMARK.md), [RULES](RULES.md), [RUBRIC](RUBRIC.md), [SUBMISSION](SUBMISSION.md), [CHECKPOINTS](CHECKPOINTS.md). Không bắt buộc xây chatbot hoặc hybrid retrieval.
