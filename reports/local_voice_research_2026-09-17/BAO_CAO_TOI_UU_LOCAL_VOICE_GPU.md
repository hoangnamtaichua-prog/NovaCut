# Báo cáo cải tiến VieNeu / Local Voice cho NovaCut

Ngày khảo sát: **17/09/2026**. Mục tiêu: chuyển 5.000 mục phụ đề thành giọng đọc trong **tối đa 30 phút**, hướng tới 15 phút, trên máy hiện tại. Tài liệu này là đặc tả bàn giao cho AI triển khai; chưa thay đổi engine hoặc cài lại môi trường ứng dụng.

## 1. Kết luận và quyết định đề xuất

**Có cơ sở kỹ thuật để theo đuổi mục tiêu, nhưng chưa có benchmark TTS trên RTX 5060 để cam kết thời gian.** Ưu tiên giữ VieNeu v3 Turbo, chuyển sang PyTorch CUDA và suy luận theo batch, đồng thời sửa pipeline âm thanh. Chỉ tăng số luồng trong giao diện sẽ không giải quyết được giới hạn hiện tại.

Phương án chính: **một tiến trình GPU riêng, một model được giữ trong bộ nhớ, batch khởi đầu 8 câu, thử tăng lên 16/32 theo kết quả đo**. Bổ sung cache đặc trưng giọng clone, cache âm thanh có phiên bản, hàng đợi có giới hạn và ghép PCM bằng NumPy. Engine ONNX CPU hiện tại tiếp tục là lựa chọn tương thích.

**Ràng buộc bắt buộc: cách ly Python và thư viện của VieNeu GPU khỏi môi trường hiện tại của NovaCut/OCR/ASR/RVC.** Không nâng hoặc thay Python, torch, transformers, NumPy hay ONNX Runtime dùng chung chỉ để bật TTS GPU. App gọi worker bằng giao thức riêng, không import bộ thư viện GPU mới vào tiến trình chính. Mục tiêu là tránh xung đột dependency và cho phép gỡ/rollback gói GPU độc lập; vẫn phải điều phối GPU/VRAM dùng chung và kiểm thử các chức năng khác.

Hiểu “5.000 SRT” là **5.000 mục/câu trong phụ đề**, không phải 5.000 tệp. Thời gian còn phụ thuộc số chữ, tổng giây giọng sinh ra, giọng clone, tốc độ đọc, retry và độ dài timeline. Nếu thực tế là 5.000 tệp, cần xác định lại khối lượng bằng tổng ký tự và tổng thời lượng.

## 2. Bằng chứng tại máy và trong mã nguồn

### Phần cứng, môi trường

| Hạng mục | Quan sát trực tiếp | Ý nghĩa |
|---|---|---|
| GPU | NVIDIA GeForce RTX 5060; 8.151 MiB VRAM; trống 6.360 MiB tại thời điểm đo | Có GPU NVIDIA để thử CUDA; VRAM trống thay đổi theo ứng dụng đang chạy |
| Driver | 591.86 | Cần xác nhận bằng phép chạy CUDA thực tế trong runtime mới |
| CPU | Intel Core i5-14400F; 16 luồng logic | Có thể xử lý chuẩn hóa, ghi file và hậu xử lý song song với GPU |
| RAM | 47,8 GiB; còn khoảng 29,5 GiB tại lần đọc | Đủ dư địa thử nghiệm nhưng vẫn phải giới hạn RAM theo độ dài timeline |
| Bản đóng gói | Metadata trong `release/NovaCut/_internal`: VieNeu 3.3.0; torch 2.6.0+cu124; onnxruntime-directml 1.24.4 | Không nên coi môi trường hiện tại đã hỗ trợ GPU đời mới |
| Model phân phối trong `models/vieneu` và bản release | Có ONNX, config, tokenizer, speaker encoder, denoiser; không tìm thấy checkpoint PyTorch ở hai cây này | Chuyển backend cần bổ sung tài nguyên PyTorch và codec phù hợp |
| Hugging Face cache của tài khoản phát triển | Có `update/model.safetensors` tại snapshot `d0c7ea3951eaaca27bdcf53ff9fa9eaf8ed5893a` | Có thể kiểm tra để tái sử dụng; chưa xác nhận đầy đủ, hash hoặc tương thích |

Đây là kiểm tra phần cứng và tệp cục bộ, **không phải xác nhận toàn bộ các gói trên đang được tiến trình app đang mở import**. AI triển khai phải ghi `sys.executable`, `module.__file__`, backend và phiên bản thực tế từ worker/app. `.asr_venv` không khởi chạy được trong phiên khảo sát vì đường dẫn Python gốc không khả dụng; Python NuGet là 3.10.11. Không sử dụng lại `.asr_venv` làm nền cho TTS GPU.

### Nút thắt đã xác định

Các vị trí dưới đây là số dòng tại thời điểm khảo sát; nếu code đổi, tìm theo tên hàm.

| Vị trí | Hiện trạng | Cải tiến cần làm |
|---|---|---|
| `local_voice_engine.py:382`, `_create_single_engine()` | Ép `backend="onnx"` tại dòng 409 | Tách lựa chọn CPU và GPU, không dùng chung cấu hình đường dẫn ONNX |
| `release/NovaCut/_internal/vieneu/_v3_turbo_engine/onnx_runtime_lite.py:150` | Các session backbone/acoustic/codec dùng `CPUExecutionProvider` | Cài thêm CUDA hoặc ONNX GPU đơn thuần không tự đổi đường chạy này |
| `local_voice_engine.py:439`, `get_engine_pool()` | Hàng đợi chỉ chứa tối đa hai engine CPU | 8–16 tác vụ bên ngoài vẫn chỉ có hai engine thực sự suy luận |
| `local_voice_engine.py:596`, `synthesize()` | Gọi `tts.infer()` từng câu | Tạo API batch để nhiều câu chia sẻ một lượt suy luận GPU |
| `ai_dubbing.py:473–588` | Tạo 8 worker local mặc định, có thể 16; submit toàn bộ danh sách | Thay nhánh local bằng scheduler batch, không tạo nhiều bản model GPU |
| `routes/tts.py:503`, `:629` | Nghe thử hàng loạt và tạo kịch bản cũng gọi từng câu qua thread pool | Chuyển các đường local này sang cùng dịch vụ batch |
| `local_voice_engine.py:641` và SDK `v3turbo.py:316` | Với clone, mỗi câu truyền lại `ref_audio`; SDK lại chuẩn bị reference | Enroll một lần rồi dùng speaker embedding/ref codes đã lưu |
| `ai_dubbing.py:620` trở đi | Ghép stereo 44.100 Hz bằng vòng lặp Python trên từng sample | Cộng theo mảng NumPy, theo block khi timeline dài |
| `local_voice_engine.py:665` trở đi | Đổi tốc độ bằng thay số mẫu với `scipy.signal.resample` | Kiểm tra cao độ: cách này thay đổi pitch; dùng time-stretch giữ pitch nếu yêu cầu |
| `ai_dubbing.py:506` | Cache dựa trên voice ID, speed làm tròn hai chữ số, text | Thêm model/voice hash/cấu hình âm thanh và version; tránh dùng nhầm audio cũ |

Local Voice đã có resample trong RAM và bỏ FFmpeg từng câu trong nhánh dubbing thông thường. Không tính việc “bỏ FFmpeg từng câu” là cải tiến mới cho nhánh này. Phoneme cache cũng đã có tại `local_voice_engine.py:362`; cần kiểm tra hiệu lực của monkey patch khi nâng SDK, không cộng speedup giả định lần nữa.

Luồng dubbing còn có dịch bổ sung câu chứa chữ Hán trước khi tạo giọng. Cần đo riêng giai đoạn đó; GPU TTS không giải quyết thời gian chờ dịch.

## 3. Nghiên cứu upstream và lựa chọn công nghệ

VieNeu công bố benchmark v3.8.x trên Windows 11, RTX 3060 12 GB: batch GPU đạt RTF khoảng **0,011–0,02**, một câu GPU khoảng **0,10**. Đây là số của tác giả, không phải số đo trên RTX 5060 và không bao gồm toàn bộ pipeline NovaCut. Tài liệu hiện tại cũng ghi LMDeploy là đường legacy v2. Vì vậy không chọn LMDeploy làm nền cho app v3 Turbo. [Nguồn VieNeu](https://github.com/pnnbao97/VieNeu-TTS#-4-benchmarks).

SDK đóng gói tại máy đã có `infer_batch()` trong `v3turbo.py:511`: trả một waveform cho mỗi text, giữ thứ tự; CPU vẫn xử lý tuần tự. `_infer_chunks()` đã nhóm theo độ dài phoneme. Nên tận dụng API này, tránh tự ghép nhiều câu thành một đoạn dài rồi phải cắt âm thanh trở lại từng SRT. API upstream có thể đối chiếu tại [mã v3turbo.py](https://github.com/pnnbao97/VieNeu-TTS/blob/main/src/vieneu/v3turbo.py).

Bản 3.3.0 tại máy đã có acoustic CUDA graph trong package `v3_turbo_serve`; không được viết báo cáo triển khai rằng SDK cũ hoàn toàn không có graph/batch. Bản mới có các tối ưu tiếp theo; cần A/B trên cùng dữ liệu. [Mã CUDA graph](https://github.com/pnnbao97/VieNeu-TTS/blob/main/src/vieneu/v3_turbo_serve/cudagraph.py).

RTX 5060 thuộc compute capability **12.0**. PyTorch công bố hỗ trợ Blackwell cùng CUDA 12.8 từ dòng 2.7. Do đó không chọn torch 2.6/cu124 làm runtime GPU cho máy này. Khuyến nghị nền thử nghiệm cụ thể là **torch 2.8.0/cu128**, rồi xác nhận bằng CUDA smoke test. [NVIDIA](https://developer.nvidia.com/cuda/gpus), [PyTorch Blackwell](https://pytorch.org/blog/pytorch-2-7/), [wheel Linux/Windows](https://pytorch.org/get-started/previous-versions/#v280).

| Phương án | Đánh giá cho máy hiện tại |
|---|---|
| PyTorch CUDA + `infer_batch` + sửa pipeline | Ưu tiên số 1; giữ họ model và mapping giọng, tận dụng API sẵn có |
| Chỉ đổi sang GPU nhưng tiếp tục gọi từng câu | Bước chẩn đoán hữu ích; chưa khai thác đầy đủ throughput |
| Chỉ tăng thread/engine CPU | Có thể tranh CPU, tăng RAM; không có cơ sở kỳ vọng tăng 4–12 lần |
| ONNX CUDA/DirectML | Nhánh nghiên cứu sau; phải đổi provider, xác minh kernel/graph, giảm sao chép CPU↔GPU |
| VieNeu Nano CPU | Phương án tùy chọn nếu chấp nhận đánh đổi chất lượng và giọng; chưa thử ở máy này |
| API từ xa | Dự phòng khi người dùng muốn; cần xét giá, tốc độ, giọng và quyền gửi nội dung |
| WSL2, TensorRT, viết lại engine | Chưa cần trong vòng đầu; chỉ xét khi profile chứng minh PyTorch là giới hạn |

ONNX CUDA yêu cầu runtime CUDA/cuDNN tương thích và có cơ chế I/O binding; đổi tên provider không phải bằng chứng đã tăng tốc. [Tài liệu ONNX Runtime](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html).

## 4. Mục tiêu thời gian và điều kiện đạt

Từ thời gian người dùng báo 120–180 phút, cần tăng tốc toàn quy trình **4–6 lần** để đạt 30 phút; **8–12 lần** để đạt 15 phút.

Với 5.000 câu, tổng ngân sách trung bình là **0,36 giây/câu** ở mốc 30 phút hoặc **0,18 giây/câu** ở mốc 15 phút. Đây là thông lượng toàn job, không phải độ trễ riêng từng câu trong batch.

Định nghĩa `D` là tổng thời lượng audio giọng được sinh, không gồm khoảng im lặng timeline. Dùng công thức:

`T_total = T_load + T_prepare + T_infer + T_postprocess + T_mix + T_retry + T_other`

`RTF_infer = T_infer / D`

Nếu các công đoạn chạy chồng nhau, đo `T_total` bằng đồng hồ toàn job; không cộng các khoảng thời gian đã chồng lấp để đánh giá SLA.

Ví dụ lập ngân sách, **không phải dự báo đã benchmark**: dành 5 phút cho mọi việc ngoài inference.

| Giọng trung bình mỗi câu | Tổng D cho 5.000 câu | RTF inference tối đa để tổng ≤30 phút | RTF inference tối đa để tổng ≤15 phút |
|---|---:|---:|---:|
| 3 giây | 250 phút | 0,100 | 0,040 |
| 5 giây | 416,7 phút | 0,060 | 0,024 |
| 8 giây | 666,7 phút | 0,0375 | 0,015 |

Mốc 30 phút là mục tiêu nghiệm thu đầu tiên hợp lý để thử. Mốc 15 phút phụ thuộc dữ liệu mạnh hơn; không thể bảo đảm chỉ từ số câu. Không suy luận RTX 5060 chắc chắn nhanh hơn benchmark RTX 3060: hai GPU khác VRAM, băng thông, tải nền và batch thực dùng.

## 5. Thiết kế triển khai đề xuất

### 5.1 Runtime GPU riêng — yêu cầu bắt buộc để tránh xung đột

Tạo worker Python riêng trong `runtimes/vieneu_gpu`, giao tiếp với app bằng JSON Lines qua stdin/stdout hoặc IPC tương đương. Chọn subprocess để tách torch/transformers khỏi OCR, ASR, RVC và DLL của app đóng gói. App giữ worker/model sống giữa các job khi đủ tài nguyên; phải hỗ trợ giải phóng hoặc dừng worker khi chức năng khác cần VRAM. Khởi chạy ẩn cửa sổ Windows; stderr dành cho log, stdout chỉ dành cho protocol.

Ranh giới triển khai:

```text
NovaCut / các môi trường OCR, ASR, RVC hiện có
    │  Giữ Python, site-packages và DLL hiện có
    │  IPC: job ID + text/options → trạng thái + đường dẫn WAV
    ▼
VieNeu GPU worker — tiến trình riêng
    Python riêng + site-packages riêng + thư viện CUDA đi kèm riêng
    Model/config/cache theo phiên bản riêng

Tài nguyên vẫn dùng chung: driver NVIDIA, GPU/VRAM, CPU/RAM và ổ đĩa
```

| Thành phần | Quy tắc cách ly |
|---|---|
| Python executable | Gọi đường dẫn tuyệt đối tới Python của runtime GPU; không gọi `python`/`pip` theo PATH, không dùng `sys.executable` của app frozen làm Python worker |
| Môi trường phát triển | Tạo venv riêng không bật `--system-site-packages`; không tái sử dụng `.asr_venv`, `rvc_env` hoặc site-packages của app |
| Tiến trình chính | Client IPC dùng thư viện hiện có/standard library; không thêm thư mục runtime GPU vào `sys.path` của app và không import torch/VieNeu mới ở đây |
| Biến môi trường | Tạo môi trường riêng cho child; loại bỏ giá trị `PYTHONHOME`, `PYTHONPATH` và đường dẫn thư viện từ app có thể làm lẫn runtime. Không sửa PATH hay biến môi trường toàn máy |
| DLL khi chạy bản đóng gói | Kiểm tra và xử lý cơ chế kế thừa đường dẫn tìm DLL từ launcher/frozen app theo cách đóng gói thực tế; tránh worker nạp CUDA/cuDNN/DLL từ `_internal` của app. Không chỉ kiểm thử từ terminal |
| Driver / CUDA | Thư viện CUDA phía ứng dụng nằm trong runtime worker theo gói đã khóa. Driver NVIDIA vẫn dùng chung; không tự cập nhật driver hoặc CUDA Toolkit hệ thống trong trình cài gói TTS |
| Model và cache | Namespace riêng theo revision, file manifest/hash; không ghi đè model/config hoặc cache mà engine CPU hay chức năng khác đang dùng |
| Cài đặt/cập nhật | Chỉ cài vào thư mục runtime GPU riêng. Không chạy `pip install --upgrade` trong môi trường chính, không chép đè DLL vào `release/NovaCut/_internal` |

Venv dành cho phát triển có thể phụ thuộc đường dẫn Python gốc; **không coi việc copy nguyên venv từ máy dev là gói phân phối độc lập**. Bản phát hành cần đóng gói Python runtime thích hợp hoặc bộ cài tái tạo môi trường từ lockfile và wheel đã kiểm chứng, bảo đảm chạy trên máy không cài Python. Kiểm tra thư mục cài đặt có dấu cách/ký tự tiếng Việt và không phụ thuộc đường dẫn tài khoản dev.

Do app và worker ở hai tiến trình khác nhau, cập nhật torch của worker không cần đổi torch của OCR/ASR/RVC. Tuy nhiên, cách ly không đồng nghĩa không có mọi xung đột: GPU/VRAM, CPU/RAM, driver và đường dẫn DLL khởi chạy vẫn cần kiểm chứng. Không cam kết “không ảnh hưởng chức năng khác” trước khi qua ma trận kiểm thử ở mục 7.

Kiểm tra handshake phải trả: phiên bản protocol, executable, SDK, torch, CUDA build, device, backend, model revision, dtype, capabilities, batch limit và sample rate. `cuda.is_available()` đơn lẻ chưa đủ; phải chạy phép tính CUDA và một batch audio ngắn, kiểm tra output hữu hạn, không rỗng.

Gói thử nghiệm đề xuất: Python 3.12 x64 riêng; VieNeu 3.8.1; torch/torchaudio 2.8.0 cu128; transformers 4.57.6. Đây là cấu hình ứng viên cần khóa sau khi kiểm tra dependency và audio, không phải môi trường đã cài/đã xác nhận trong phiên này. [VieNeu 3.8.1 trên PyPI](https://pypi.org/project/vieneu/3.8.1/).

Lệnh cho AI triển khai, chỉ chạy trong **venv mới** bằng đúng Python riêng đã kiểm tra:

```powershell
& $voicePython -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
& $voicePython -m pip install vieneu==3.8.1 transformers==4.57.6
& $voicePython -m pip check
```

`$voicePython` là đường dẫn tuyệt đối tới `python.exe` của venv mới, không phải biến hệ thống. Trước khi cài, kiểm tra `sys.executable`, `sys.prefix`, đường dẫn pip/site-packages đều thuộc môi trường GPU đã chọn. Sau khi thử thành công, lưu lockfile toàn bộ dependency, hash wheel và manifest model; kiểm tra cài lại từ đầu. Các lệnh này không được áp dụng vào Python đang chạy chức năng khác.

Tài nguyên GPU cần checkpoint PyTorch, config/tokenizer tương ứng và **MOSS codec PyTorch**, không chỉ thư mục codec ONNX hiện có. Khảo sát loader của đúng phiên bản được pin: local path, `model_subfolder`, denoiser/speaker encoder và mã remote cần được đóng gói nhất quán. Một số loader cũ vẫn gọi Hugging Face dù truyền local path; phải test offline thật. Chỉ tái sử dụng cache khi đủ file, đúng revision/hash; chuẩn bị download trước job và không tính tải lần đầu vào số đo inference, nhưng hiển thị thời gian setup riêng.

### 5.2 Một GPU owner và scheduler batch

Đề xuất giao diện mới (tên mới, chưa tồn tại):

```text
synthesize_batch(items, voice_profile, options, cancel_token)
items: [{id, text, start_seconds, end_seconds, output_path}]
result: [{id, path, sample_rate, channels, duration, error}]
```

Pipeline:

```text
SRT → chuẩn hóa một lần → cache/deduplicate → nhóm cùng giọng/cấu hình
    → cửa sổ hữu hạn 64–128 câu → GPU infer_batch(batch 8/16/32)
    → hậu xử lý/ghi file 2–4 worker CPU → checkpoint → ghép theo timestamp
```

Batch là nhiều text độc lập; luôn ánh xạ bằng ID về câu gốc. Cửa sổ 64–128 và 2–4 worker chỉ là điểm bắt đầu để đo. SDK đã có length bucketing nội bộ; chỉ thêm bucketing ngoài nếu cần tránh câu quá dài làm nghẽn cửa sổ hoặc nếu phiên bản pin thiếu tính năng này.

Một GPU worker xử lý tuần tự các lệnh batch; không cho nhiều thread gọi cùng model/graph cùng lúc. Batch mặc định 8; thử 16 và 32, ghi peak VRAM và tốc độ. Giữ khoảng trống VRAM cho desktop và tải nền; con số giới hạn phải lấy từ phép đo, không hard-code tổng 8 GB là toàn bộ có thể dùng.

Khi OOM: giải phóng tensor không còn dùng, hạ batch còn một nửa, retry phần chưa hoàn tất với giới hạn; nếu context hỏng thì restart worker rồi resume. Nếu batch 1 vẫn lỗi, trả lỗi rõ. Không âm thầm đổi sang CPU khi đang chọn GPU và tiếp tục báo ETA GPU. Khi không có CUDA, lựa chọn Auto có thể dùng CPU kèm trạng thái rõ ràng; người dùng đã chọn GPU thì báo runtime/driver cần sửa.

Cancel kiểm tra trước mỗi batch và trong lúc ghi kết quả; ngừng enqueue, không gửi trước toàn bộ 5.000 future. Đo độ trễ hủy; yêu cầu hủy mạnh có thể dừng worker riêng và tái tạo ở job sau. Preview ưu tiên ở ranh giới batch, không tạo thêm model chỉ để nghe thử.

### 5.2.1 Điều phối GPU giữa VieNeu, OCR, ASR và RVC

Thêm cơ chế điều phối ở cấp app cho các công đoạn thực sự dùng GPU. Bản đầu trên RTX 5060 8 GB ưu tiên **xếp hàng các công đoạn GPU nặng**; chỉ bật chạy đồng thời sau khi đã đo peak VRAM và độ ổn định cho từng tổ hợp. Các công đoạn CPU/I/O có thể tiếp tục nếu không làm cạn RAM hoặc nghẽn CPU.

Giữ model resident phải có điều kiện. Dừng inference không tự giải phóng bộ nhớ model; khi chuyển sang tác vụ GPU khác, worker cần checkpoint rồi unload model hoặc kết thúc tiến trình tại ranh giới an toàn. Không coi `empty_cache()` là cách giải phóng tensor/model còn được giữ tham chiếu. Tính thời gian reload vào phép đo thực tế khi có chuyển tác vụ.

Trình điều phối cần trạng thái chờ, đang chạy, nhường GPU, resume và lỗi; thu hồi quyền sử dụng GPU khi worker chết hoặc job bị hủy. Nếu workflow cần nhiều công đoạn GPU nối tiếp, giải phóng quyền ở ranh giới công đoạn, tránh giữ quyền TTS trong lúc chờ công đoạn ASR/RVC gây deadlock. Giao diện hiển thị lý do chờ và ETA cập nhật bằng hệ thống thông báo của app.

Ứng dụng ngoài NovaCut không chịu điều phối này. Đọc VRAM trống trước khi nhận batch chỉ là một tín hiệu; luôn xử lý OOM khi tài nguyên thay đổi. Không tự đóng ứng dụng ngoài hoặc hủy job OCR/ASR/RVC đang chạy để giành VRAM.

### 5.2.2 Vòng đời worker, cài đặt và rollback độc lập

App quản lý một worker TTS theo phiên sử dụng, heartbeat/timeout và job ID; khi app đóng phải dọn tiến trình con thuộc phiên đó. Worker crash chỉ làm job TTS chuyển trạng thái lỗi/resume, không được làm tiến trình chính thoát. Giới hạn số lần restart để tránh vòng lặp crash vô hạn.

Đóng gói runtime theo thư mục có phiên bản. Cài bản mới vào thư mục staging riêng, kiểm tra hash, handshake, preset/clone smoke test và đường dẫn DLL; chỉ chuyển cấu hình sang bản mới khi không có job đang dùng bản cũ. Giữ bản trước để rollback bằng cấu hình. Gỡ gói VieNeu GPU chỉ xóa tài nguyên thuộc gói đó; giữ output, giọng người dùng và các môi trường khác.

Nếu worker không khởi động, giữ app và các tính năng khác hoạt động; báo đúng nguyên nhân và cho chọn engine CPU hiện có. Giữ nguyên nguyên tắc không âm thầm fallback khi đã chọn GPU. TTS được coi là nâng cấp thành công chỉ sau khi kiểm thử chạy từ launcher của bản đóng gói và chạy lại sau rollback.

### 5.3 Cache clone, cache audio và resume

Giọng clone: chuẩn bị embedding/ref codes một lần bằng API enroll của SDK, rồi truyền voice đã enroll vào các batch. Khóa cache gồm hash nội dung reference, model/codec revision, denoise, trim và phiên bản tiền xử lý. Không chỉ khóa theo tên hoặc đường dẫn file. Nếu giữ hai engine CPU, enroll một lần cho mỗi engine hoặc chia sẻ dữ liệu bất biến khi API cho phép.

Cache audio nên dùng SHA-256 trên biểu diễn JSON chuẩn gồm: normalized text, voice identity/reference hash, SDK/model revision, backend/dtype khi cần phân biệt output, sampling parameters/seed, watermark, speed chính xác, resample/time-stretch version, sample rate, channels. Có thể cache raw audio và bản hậu xử lý riêng để thay speed không bắt buộc chạy model lại.

Ghi file tạm rồi atomic rename; kiểm tra header, frames, sample rate/channels và finite values trước khi nhận cache. Deduplicate câu trùng trong cùng job bằng một tác vụ đang chạy cho mỗi key. Manifest lưu input hash, options, câu hoàn tất và đường dẫn file để resume sau khi app/worker dừng. Cache hit phải được báo riêng, không dùng job toàn cache để chứng minh đạt tốc độ sinh mới.

### 5.4 Ghép âm thanh và chất lượng

Thay vòng lặp sample bằng phép cộng NumPy trên lát cắt. Dùng int32 hoặc float cho phép cộng để tránh int16 overflow. Trong bước đầu bảo toàn clipping hiện tại `[-32767, 32767]`, thứ tự chồng clip và timestamp; đổi sang tích lũy float rồi limiter là thay đổi âm thanh riêng cần kiểm thử.

Với timeline dài, dùng block hoặc memmap, giữ clip đang giao block, không cấp phát nhiều bản toàn track. Timeline 3 giờ stereo 44.100 Hz PCM16 khoảng 1,78 GiB; int32 khoảng 3,55 GiB, chưa tính bản copy và audio từng câu. WAV RIFF thông thường còn có giới hạn kích thước khoảng 4 GiB; cần kiểm tra trước khi ghi, chọn RF64/chia file có chủ đích nếu vượt giới hạn.

Giữ mono đến gần đầu ra chỉ khi yêu cầu sản phẩm cho phép và test mapping kênh; không đổi định dạng cache âm thầm. Đo riêng resample và time-stretch. Thay đổi tốc độ bằng resample số mẫu hiện tại làm đổi pitch; nếu sửa thì phải nghiệm thu độ giống giọng, không dùng tăng speed để đánh tráo mục tiêu tăng tốc tính toán.

Không cắt đuôi câu dài, không giảm `max_new_frames` tùy tiện để đẹp benchmark. Phụ đề có overlap hoặc câu đọc dài hơn slot phải theo chính sách timeline đã có; batching không được tự dồn câu hoặc gộp timestamp.

## 6. Phép đo đã thực hiện

Đã chạy microbenchmark trên máy này với Python 3.12.14, NumPy 2.3.5: ba clip stereo PCM16, mỗi clip 10 giây, 44.100 Hz, chồng lên nhau; lặp ba lần. So sánh đúng quy tắc cộng/clamp của code hiện tại.

| Cách ghép | Trung vị |
|---|---:|
| Vòng lặp Python | 0,605576 giây |
| NumPy theo mảng | 0,012175 giây |
| Tỷ lệ | 49,74 lần |

Kết quả PCM **giống chính xác từng mẫu**, bao gồm dữ liệu có clipping. Script và JSON nằm cùng thư mục báo cáo. Đây là phép đo tổng hợp của riêng phép overlay, **không gồm TTS, ghi đĩa, dịch, hoặc ghép 5.000 câu thực**. Không suy ra app sẽ nhanh hơn 49,74 lần và không ngoại suy RAM/cache của clip nhỏ sang timeline dài.

Chưa đo TTS GPU vì phiên này tập trung khảo sát/bàn giao, chưa dựng runtime GPU và chưa có bộ SRT 5.000 câu được xác định làm dữ liệu nghiệm thu. Thời gian 2–3 giờ là số người dùng cung cấp, chưa tái hiện.

## 7. Kế hoạch benchmark và tiêu chí nghiệm thu

### Đo theo ba cấp

1. **Smoke test:** kiểm tra CUDA, device capability, một preset và một clone; batch 1/8; kiểm tra output và chạy khi ngắt mạng sau khi đã chuẩn bị assets.
2. **Pilot đại diện 200–500 câu:** lấy câu ngắn/vừa/dài, số, tên riêng, dấu câu, Việt–Anh; chạy cùng nội dung và speed ở CPU hiện tại, GPU batch 1/4/8/16/32. Nếu đủ runtime, so sánh SDK 3.3.0 và 3.8.1 nhưng giữ model revision nhất quán để tách tác động phần mềm.
3. **Toàn bộ 5.000 câu:** chạy cấu hình tốt nhất trên dữ liệu thực, cache audio riêng ban đầu rỗng; chạy thêm lần resume/cache để đo trải nghiệm nhưng báo kết quả riêng. Chạy ít nhất hai lượt đầy đủ nếu thời gian cho phép nhằm phát hiện dao động và rò VRAM.

Ghi JSON/CSV: input SHA-256, số câu, ký tự, tổng audio D, timeline duration, model revision, package versions, hardware/driver, batch size thực, cold/warm model, cache hit, seed, peak VRAM/RAM, lỗi/retry, và thời gian từng giai đoạn. Dùng `perf_counter`; khi đo kernel GPU thuần phải synchronize đúng chỗ, tránh chỉ đo thời gian enqueue. Toàn job bắt đầu trước load/prepare và kết thúc sau khi file cuối được đóng.

Nghiệm thu hiệu năng chính: **≤1.800 giây end-to-end** cho bộ 5.000 câu đã thống nhất, model/assets đã cài sẵn, cache audio rỗng. Báo cold start và warm start riêng. ≤900 giây là mục tiêu mở rộng. Nếu còn dịch hoặc encode video, hiển thị thời gian riêng và thống nhất phạm vi; không bỏ thời gian ghép âm thanh khỏi SLA tạo voice.

Phép đo chuẩn phải ghi rõ tải GPU nền và chạy khi NovaCut chưa có job GPU khác. Với phép đo đa tác vụ, báo thêm thời gian chờ GPU, unload/reload và thời gian tổng từ lúc người dùng bấm chạy; không loại các khoảng này để tuyên bố đạt 15–30 phút. Kết quả chạy riêng không phải cam kết thời gian khi đồng thời OCR/ASR/RVC.

Nghiệm thu tính đúng: mọi mục đầu vào có audio hợp lệ hoặc trạng thái bỏ qua/lỗi rõ; không mất câu, đổi giọng, đảo thứ tự, cắt cuối, sai sample rate; start timestamp sai không quá một sample do làm tròn; giữ minimum timeline duration. Nghe A/B 30–50 câu đại diện, có clone, câu dài và speed khác 1.0. Batch sampling không yêu cầu waveform bit-identical với inference từng câu; kiểm tra nội dung đọc và giọng bằng nghe, có thể bổ sung ASR như tín hiệu hỗ trợ.

Nghiệm thu vận hành: cancel/resume, lỗi CUDA, OOM, cache hỏng, đổi file clone cùng tên, hai job đồng thời, preview trong lúc render, offline và app đóng gói đều được xử lý. Thêm kiểm thử có ý nghĩa cho mapping batch/ID, clip overlap/clipping, cache invalidation và resume; không chạy 5.000 câu trước khi pilot đạt thông lượng cần thiết.

### Ma trận bắt buộc: tránh xung đột với chức năng hiện có

Trước khi thay đổi, ghi phiên bản/đường dẫn Python và package thực tế của app, OCR, ASR, RVC; chạy tác vụ mẫu làm baseline. Ghi riêng lỗi có sẵn, không coi chức năng vốn lỗi là regression mới hoặc tự ý nâng cả môi trường để sửa ngoài phạm vi.

| Tình huống | Kết quả bắt buộc |
|---|---|
| Trước/sau cài gói GPU | Python, package và DLL của môi trường hiện có không bị cài lại hoặc đổi phiên bản; diagnostics chứng minh app/worker import từ đúng nơi |
| OCR, ASR, RVC chạy riêng | Tác vụ mẫu đang pass trước thay đổi vẫn pass sau thay đổi; so sánh output và thời gian với baseline |
| TTS đang chạy rồi yêu cầu OCR/ASR/RVC GPU | Xếp hàng/nhường GPU theo chính sách, không OOM hàng loạt, treo UI hoặc mất kết quả |
| OCR/ASR/RVC đang chạy rồi yêu cầu TTS | TTS chờ hoặc nhận cấu hình đã được chứng minh đủ VRAM; không tự chiếm hết bộ nhớ |
| TTS → chức năng khác → TTS | Model unload/reload đúng, quyền GPU được giải phóng, không deadlock hoặc tăng VRAM qua nhiều vòng |
| Hai job TTS và nghe thử | Một worker/model được điều phối, output không lẫn giọng/job, hủy một job không hủy job còn lại |
| Worker crash, timeout hoặc thiếu DLL | App còn hoạt động; lỗi nằm ở TTS, job có thể resume; OCR/ASR/RVC không bị đổi môi trường |
| Chạy từ EXE/launcher trên máy không có Python | Worker dùng Python đã đóng gói; không dựa vào PATH, Python hệ thống hoặc thư mục máy dev |
| Rollback hoặc gỡ gói GPU | Khôi phục engine/runtime trước; output và giọng người dùng còn nguyên; tính năng khác tiếp tục pass |

Nếu một tổ hợp đồng thời không ổn định thì giữ xếp hàng, không xem việc tăng concurrency là điều kiện bắt buộc. Báo cáo nghiệm thu phải kèm kết quả ma trận này trước khi chấp nhận tích hợp GPU.

## 8. Danh sách công việc bàn giao

| Thứ tự | Công việc | Điều kiện hoàn tất |
|---|---|---|
| P0 | Ghi diagnostics từ runtime app/OCR/ASR/RVC thực; chốt SRT nghiệm thu | Xác định module/backend thật, baseline từng giai đoạn và lỗi có sẵn |
| P1 | Dựng runtime GPU cách ly hoàn toàn dependency, khóa package/model; smoke test | RTX 5060 chạy preset + clone; Python/package của chức năng khác giữ nguyên |
| P2 | Thêm worker/client, API batch và điều phối GPU cấp app | Một model, IDs đúng; batch/VRAM/queue, nhường GPU, unload/reload và crash được kiểm soát |
| P3 | Đổi nhánh local trong dubbing và các route TTS | Cả SRT, kịch bản và preview dùng dịch vụ chung; provider khác hoạt động như cũ |
| P4 | Cache clone/audio, deduplicate, checkpoint/resume | Cache không lẫn revision/giọng/speed; restart không mất kết quả đã hoàn tất |
| P5 | Mixer NumPy và block/memmap; đo hậu xử lý | Test overlap/tail/clipping pass; không tăng RAM theo nhiều bản whole track |
| P6 | Pilot, hiệu chỉnh batch, chạy 5.000 câu, QA nghe | Báo thời gian thật, chất lượng và giới hạn; không tuyên bố đạt trước phép đo |
| P7 | Kiểm thử gói chạy, ma trận OCR/ASR/RVC, cài/gỡ/rollback độc lập | Pass từ launcher trên máy không cài Python; không thay dependency cũ, không regression; backend hiện rõ trong UI |

File cần xem/sửa: `local_voice_engine.py`, `ai_dubbing.py`, `routes/tts.py`, phần settings/progress frontend tương ứng. File mới đề xuất: `local_voice_worker.py`, `local_voice_worker_client.py`, `requirements-vieneu-gpu.txt`, script benchmark TTS riêng. Đây là tên thiết kế, chưa được tạo bởi khảo sát.

Kiểm tra cơ chế `web_app.py:40–56`: khi chạy source, root ưu tiên; bản frozen ưu tiên `patches/active`. Đồng bộ bản overlay theo quy trình dự án khi thực sự triển khai và log đường dẫn module để tránh sửa nhầm bản không chạy. Không chỉ chép `.py` khi thay runtime chứa DLL/native package.

Giữ kiểm tra permission frontend/backend hiện có. Sau khi sửa chức năng, ghi `TODO.md` theo quy định dự án. Workspace hiện có nhiều thay đổi chưa commit: không reset/revert hoặc ghi đè công việc khác. Yêu cầu hiện tại chỉ là nghiên cứu và báo cáo; chưa được hiểu là lệnh phát hành patch/release.

## 9. Prompt giao cho AI triển khai

> Đọc toàn bộ báo cáo này và các quy tắc dự án. Tối ưu NovaCut Local Voice/VieNeu v3 Turbo cho RTX 5060 8 GB, mục tiêu ≤30 phút cho 5.000 mục SRT thực với cache audio rỗng, hướng tới 15 phút. Trước tiên xác định runtime/module đang chạy và đo baseline cả TTS/OCR/ASR/RVC. BẮT BUỘC dùng Python, site-packages và tiến trình worker riêng cho VieNeu GPU; không nâng/thay Python, torch, transformers, NumPy, ONNX Runtime hay DLL trong môi trường chính, .asr_venv hoặc rvc_env. App chỉ gọi IPC; kiểm tra môi trường child và DLL khi khởi chạy từ EXE, đóng gói để người dùng không phải cài Python. Triển khai một model resident có khả năng unload/reload + infer_batch, điều phối GPU cấp app với OCR/ASR/RVC, cache reference clone, cache audio có version, queue có giới hạn, cancel/resume và mixer NumPy theo block. Bao phủ cả ai_dubbing và route TTS/preview, giữ ID/timestamp/giọng/chất lượng, license checks và provider khác. Thử batch 4/8/16/32 theo VRAM thực; xếp hàng công đoạn GPU nặng trước khi cho chạy đồng thời. Worker crash không làm app thoát; runtime cập nhật/gỡ/rollback độc lập. Không âm thầm fallback CPU, không cắt audio/tăng speed đọc để đạt KPI, không dùng cache nóng làm bằng chứng tốc độ sinh mới. Chạy smoke → pilot → 5.000 câu và toàn bộ ma trận regression ở mục 7; báo thời gian chờ GPU/reload riêng trong thử đa tác vụ. Bàn giao số thực, source diff, dependency/model lock và kết quả test. Tôn trọng thay đổi đang có, cập nhật TODO sau sửa và không tự phát hành.
