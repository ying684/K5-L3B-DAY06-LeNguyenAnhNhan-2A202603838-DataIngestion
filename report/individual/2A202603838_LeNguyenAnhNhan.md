# Báo cáo cá nhân — Day 6

## Dữ liệu và pipeline

Tôi sử dụng sách *Machine Learning cơ bản* của Vũ Hữu Tiệp, bản 27/03/2018. Corpus gồm 32 trang PDF vật lý 78–109, tương ứng trang in 66–97, thuộc chương 5–8. Các trang được tính có nội dung chuyên môn, không gồm bìa, mục lục, trang trống hoặc trang chỉ có tài liệu tham khảo. Nguồn, quyền sử dụng đã xác nhận, SHA-256 và danh sách trang được ghi trong [manifest](../../data/manifest.json). PDF gốc lưu tại `starter/data/raw/book_ML_color.pdf`.

Pipeline: đọc từng trang bằng pypdf → chuẩn hóa NFC, khoảng trắng và ligature → bỏ header/footer → chia chunk → tạo embedding → lưu PostgreSQL → truy xuất top-3. Text sau chuẩn hóa có 69.392 ký tự. Trong 32 trang đã chọn không có trang rỗng; pipeline chưa OCR, còn hạn chế với công thức, chữ dính và nội dung trong hình.

Cấu hình môi trường:

- Python 3.11.18; pypdf 6.21.4; psycopg 3.3.8; python-dotenv 1.2.4.
- Embedding `baai/bge-m3` qua OpenRouter, provider Parasail, vector 1.024 chiều. Response dùng tên `parasail-bge-m3`; API không cung cấp revision weights. Query và document dùng cùng model, không thêm instruction riêng.
- PostgreSQL 16.16, pgvector 0.8.7; cosine exact search, lưu bền vững và hỗ trợ metadata filter.

Mỗi chunk lưu `document_id`, `source`, `page` (trang PDF), `printed_page`, `chapter`, `chapter_title`, `language`, `snapshot` và offset ký tự. Chapter là số nguyên từ tiêu đề chương, dùng để lọc khi câu hỏi yêu cầu một chương cụ thể. Source, page và offset dùng để truy vết. Trong phạm vi corpus, trang in bằng trang PDF trừ 12.


Lệnh chạy từ `starter/`; hướng dẫn setup tại [starter/README.md](../../starter/README.md):

```powershell
python -B -m src.run prepare
python -B -m src.run dev --allow-api
python -B -m src.run test --allow-api
python -B -m src.run audit
python -B scripts/finalize_results.py
```

## Cấu hình và benchmark

| Cấu hình | Chunking | Metadata filter |
|---|---|---|
| A | Cửa sổ 500 ký tự, overlap 50 | Không |
| B | Nhóm đoạn/heading, tối đa 1.000 ký tự, overlap 0 | Không |
| C | Cùng chunk và vector của B | Chapter, chỉ khi câu hỏi cung cấp |

Ba cấu hình giữ nguyên corpus, model, vector store, metric và benchmark. B–C chỉ thay filter. A–B thay cả cách chia, kích thước và overlap nên không tách riêng ảnh hưởng của từng yếu tố. Nạp lại hai lần giữ nguyên số bản ghi A/B/C là 167/97/97. Code có xóa chunk cũ khi tài liệu đổi, nhưng chưa có thí nghiệm riêng cho tình huống này.

[Benchmark](../../benchmark/questions.json) có 20 câu, tách trước khi chạy: 15 dev (q01–q15, chương 5–7) và 5 test (q16–q20, chương 8). Có câu trực tiếp, diễn đạt lại, điều kiện và ngoại lệ. Các câu filter là q08/q10/q14 trên dev và q19 trên test; giá trị chapter lấy từ tên chương trong câu hỏi. Mỗi câu có đáp án, source ID, trang và evidence quote. Tôi kiểm tra evidence tồn tại trong text chuẩn hóa; không đưa gold answer/source vào query hoặc filter.

Tiêu chí chọn được lưu trước trong [protocol](../../artifacts/protocol.json): ưu tiên dev Hit@3, rồi Hit@1, ít chunk hơn, cuối cùng thứ tự ID. B được chọn lúc 12:37:50 ngày 14/11/2026 (UTC+07), trước test bắt đầu lúc 12:38:05. Hash code, corpus, benchmark và protocol của hai lượt khớp nhau.

Một hit yêu cầu đúng nguồn/trang và toàn bộ evidence quote nằm trong một chunk. Hit@1 là số câu top-1 đạt yêu cầu chia tổng số câu; Hit@3 là số câu có ít nhất một hit trong top-3 chia tổng số câu. Bằng chứng tương đương hoặc hợp nhiều chunk được nhận xét riêng trong grounding, không sửa metric chính sau khi xem test.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 9/15 | 12/15 | 167 | Ingest 14,4141 s; retrieval 0,2996 s | Embedding 0,00021350 USD |
| B | dev | 12/15 | 14/15 | 97 | Ingest 8,5011 s; retrieval 0,3354 s | Embedding 0,00019052 USD |
| C | dev | 12/15 | 14/15 | 97 | Nạp cache 0,3407 s; retrieval 0,3082 s | Không phát sinh embedding riêng |
| A | test | 4/5 | 4/5 | 167 | Retrieval 0,1010 s | Query dùng chung A/B/C: 0,00000108 USD |
| B | test | 4/5 | 4/5 | 97 | Retrieval 0,1017 s | Dùng chung query |
| C | test | 4/5 | 4/5 | 97 | Retrieval 0,0808 s | Dùng chung query |

Query dev dùng chung A/B/C tốn 0,00000305 USD. Ingest gồm thời gian embedding, lưu và nạp lại để kiểm tra không trùng; C dùng vector cache của B. Retrieval là tổng thời gian truy xuất trong từng split/cấu hình, gồm mở kết nối DB, không gồm embedding query.


Tôi đánh giá coherence, metadata và grounding trên các mẫu dưới đây. Nhãn, lý do và người đánh giá đã được điền trong ba file audit. Công cụ hỗ trợ kiểm tra: Codex.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 1,0/2 (10) | 15/15 | 1/1; không áp dụng filter | 0/0/5; 2,0/2 |
| B | 1,7/2 (10) | 15/15 | 1/1; không áp dụng filter | 0/0/5; 2,0/2 |
| C | 1,7/2 (10) | 15/15 | 1/1; có áp dụng filter | 0/0/5; 2,0/2 |

Tôi chọn mẫu và đánh giá như sau:

- **Coherence:** cùng 10 vị trí là midpoint text của trang PDF 78–87, khóa trước retrieval. Nếu nhiều chunk chứa vị trí, chọn chunk có offset đầu nhỏ nhất. Thang 0: không hiểu do cắt ý; 1: hiểu một phần; 2: đủ ngữ cảnh và trọn ý. A có 10 mẫu mức 1; B/C có 3 mẫu mức 1 và 7 mẫu mức 2. Lý do từng mẫu tại [coherence.csv](../../starter/results/audit/coherence.csv).
- **Metadata:** kiểm tra source, page, chapter và offset trên 5 câu test × top-3 mỗi cấu hình, tổng 45 bản ghi; các trường khớp nguồn đã trích xuất. Chapter giúp giới hạn phạm vi nhưng chưa phân biệt các mục trong cùng chương. A/B tình cờ có top-3 cùng chương ở q19, không có nghĩa đã thực thi filter. Chi tiết tại [metadata.csv](../../starter/results/audit/metadata.csv).
- **Grounding:** đọc top-3 của cùng 5 câu test mỗi cấu hình; 0: không có bằng chứng, 1: thiếu điều kiện/ngữ cảnh, 2: đủ trả lời và truy nguồn. q17 của B/C có bằng chứng tương đương về việc lấy validation từ training; q20 của A đủ ý khi hợp hai chunk. Do đó grounding có thể đạt mức 2 dù không đạt metric gold quote trong một chunk. Đây là đánh giá evidence, không phải độ chính xác câu trả lời LLM. Chi tiết tại [grounding.csv](../../starter/results/audit/grounding.csv).

Trace gốc: [dev](../../starter/results/runs/20261114_123725_dev/) và [test](../../starter/results/runs/20261114_123805_test/), gồm 60 trace cấu hình–câu hỏi và 180 bản ghi truy xuất. Bảng tổng hợp: [summary.csv](../../starter/results/summary.csv), [consolidated.json](../../starter/results/consolidated.json) và [experiment_log.csv](../../artifacts/experiment_log.csv).

## Phân tích và kết luận

**A–B:** B tăng dev Hit@3 từ 12/15 lên 14/15 và Hit@1 từ 9/15 lên 12/15. Số chunk giảm từ 167 xuống 97, khoảng 41,9%. Trung vị độ dài A là 499 ký tự, B là 802; tổng ký tự chunk lần lượt 76.071 và 69.263. B giảm lặp do không overlap và giữ được đoạn dài hơn, nhưng vẫn có mẫu bị cắt khi đoạn vượt giới hạn.

**B–C:** B/C bằng điểm dev/test và có cùng top-3 trên test. Filter C chạy đúng nhưng chưa tạo khác biệt về Hit@3 trên bộ câu hỏi này. Chỉ có một câu test cần filter nên chưa đủ để kết luận hiệu quả ngoài corpus.

Hai ví dụ lỗi:

1. **q09, dev, B/C; gold PDF 88/trang in 76:** top-3 có ví dụ đếm từ và hạn chế BoW nhưng thiếu đoạn xử lý từ ngoài từ điển bằng Unknown. A đạt Hit@3 ở câu này; B không tốt hơn A trên mọi câu.
2. **q20, test, A; gold PDF 109/trang in 97:** evidence quote dài 569 ký tự, vượt cửa sổ A 500 ký tự. Hai chunk truy xuất cùng chứa đủ ý về hệ số bằng 0 và lựa chọn đặc trưng khi đọc kết hợp, nhưng không một chunk chứa trọn quote nên Hit@3=0. B/C chứa đủ quote và đạt hit.

Tôi chọn B theo tiêu chí dev đã chốt. B/C bằng điểm và số chunk nên B được chọn theo thứ tự ID. Cả ba đạt test 4/5 nhưng sai ở các câu khác nhau; kết quả chỉ áp dụng cho corpus và bộ câu hỏi này. Khi cần ràng buộc chương, có thể dùng C để thực thi filter.

Hạn chế: corpus một sách, test chỉ 5 câu thuộc chương Overfitting; các nhãn đánh giá chưa có vòng kiểm chứng độc lập; text nguồn chưa được đối chiếu trực quan toàn bộ với PDF. Công thức/chữ dính còn lỗi trích xuất. Thời gian chỉ đo một lượt và bị ảnh hưởng bởi cache; chi phí ba lần lỗi chưa xác định. Ba lần lỗi xuất phát từ kiểm tra tên response quá chặt, đã xử lý alias trước lượt dev thành công và giữ log.

Nếu làm lại, tôi sẽ mở rộng câu hỏi sang nhiều chương, bổ sung câu metadata có nguồn gây nhiễu và thử ranh giới câu/kích thước chunk trên dev của thí nghiệm mới. Test mới được giữ riêng để đánh giá sau khi cố định cấu hình.
