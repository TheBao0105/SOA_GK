"""
Đóng gói mã nguồn để nộp bài: tạo file .zip SẠCH, không đụng tới thư mục dự án.

File zip KHÔNG chứa:
  - .venv, __pycache__, *.pyc         (môi trường và file biên dịch, máy khác tự cài lại)
  - .env của từng service             (cấu hình riêng máy; .env.example vẫn được giữ)
  - keys/, *.pem                      (khóa JWT, đặc biệt là khóa BÍ MẬT của Identity)
  - .backup_*/, work/                 (bản sao lưu cá nhân, kết quả kiểm thử, database tạm)
  - *.sqlite3, *.log, *.zip           (database cũ của Portal, log, file nén cũ)
  - .git, .vs, .vscode, .idea         (thư mục của công cụ)

Cách dùng (chạy tại thư mục gốc dự án):
    .venv\\Scripts\\python.exe -B scripts\\dong_goi_nop_bai.py
    .venv\\Scripts\\python.exe -B scripts\\dong_goi_nop_bai.py --ten SOA_Nhom5

File zip được tạo ở thư mục CHA của dự án (cạnh thư mục SOA_GK).
"""
import argparse
import fnmatch
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Thư mục bỏ qua (so khớp theo tên từng thư mục trên đường dẫn)
THU_MUC_BO_QUA = {".venv", "venv", "__pycache__", "keys", "work", ".git", ".vs", ".vscode", ".idea", "node_modules"}
MAU_THU_MUC_BO_QUA = (".backup_*",)

# File bỏ qua (so khớp theo tên file)
MAU_FILE_BO_QUA = ("*.pyc", "*.pyo", "*.pem", "*.key", "*.sqlite3", "*.sqlite3-journal", "*.log", "*.zip", ".env", "Thumbs.db", "desktop.ini")


def bi_loai(rel: Path) -> bool:
    *thu_muc, ten = rel.parts
    for part in thu_muc:
        if part in THU_MUC_BO_QUA or any(fnmatch.fnmatch(part, m) for m in MAU_THU_MUC_BO_QUA):
            return True
    return any(fnmatch.fnmatch(ten, m) for m in MAU_FILE_BO_QUA)


def main():
    parser = argparse.ArgumentParser(description="Tạo file zip sạch để nộp bài.")
    parser.add_argument("--ten", default=f"{ROOT.name}_nop_bai_{datetime.now():%Y%m%d}",
                        help="Tên file zip (không cần đuôi .zip)")
    args = parser.parse_args()

    dich = ROOT.parent / f"{args.ten}.zip"
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and not bi_loai(p.relative_to(ROOT)))

    with zipfile.ZipFile(dich, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            # Đặt mọi file trong một thư mục gốc cùng tên dự án để giải nén ra gọn gàng
            zf.write(p, Path(ROOT.name) / p.relative_to(ROOT))

    # Kiểm tra lại file zip vừa tạo: không được lọt file nhạy cảm
    with zipfile.ZipFile(dich) as zf:
        ten_trong_zip = zf.namelist()
    lot = [n for n in ten_trong_zip if bi_loai(Path(*Path(n).parts[1:]))]
    if lot:
        dich.unlink()
        print("LỖI: file nhạy cảm lọt vào zip, đã hủy file zip:", *lot, sep="\n  ")
        return 1

    kich_thuoc = dich.stat().st_size / 1024
    print(f"Đã tạo: {dich}")
    print(f"Số file: {len(ten_trong_zip)} | Dung lượng: {kich_thuoc:.0f} KB")
    print("Đã loại: .venv, .env, keys/*.pem, .backup_*, work/, *.sqlite3, __pycache__.")
    print("Người nhận cài lại theo README.md (tạo .env từ .env.example, chạy generate_jwt_keys).")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # để console Windows in được tiếng Việt
    sys.exit(main())
