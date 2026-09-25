"""微信 4.x 本地库密钥提取 + 解密（M0-06 验证工具，自包含实现）。

用法（管理员终端、微信 4.x 已登录）：
    python scripts/decrypt_wechat4.py                 # 全自动：找库→取钥→解密→报告表结构
    python scripts/decrypt_wechat4.py --data-root D:\\xwechat_files
    python scripts/decrypt_wechat4.py --internal-key <64hex>   # 个别库需要内部密钥 XOR 时

原理（对齐 WeChatDataAnalysis/DbkeyHook 的公开实现）：
- 4.x 数据目录：Documents/xwechat_files/<账号>/db_storage/**.db，SQLCipher 4 参数：
  页 4096B、PBKDF2-SHA512 256000 轮（口令派生变体）、AES-256-CBC、每页 reserve=80
  （IV 16B + HMAC-SHA512 64B）、页 1 前 16B 为 salt；
- 密钥在 Weixin.exe 进程内存中，以「指针桩」模式定位（32B 固定模式，见 _STUB_PATTERN），
  候选经熵过滤后对样本库页 1 做 HMAC 校验（raw 与口令派生两种变体）；
- 解密输出 data/wechat4_plain/<账号>/**.db（普通 SQLite，供采集端 wechat4 源读取）。

仅用于本人账号的本地归档（项目合规边界见 docs/compliance-plan.md）。
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import hmac
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

from Crypto.Cipher import AES

PAGE_SIZE = 4096
SALT_SIZE = 16
IV_SIZE = 16
HMAC_SIZE = 64
KEY_SIZE = 32
KDF_ROUNDS = 256_000
RESERVE_SIZE = ((IV_SIZE + HMAC_SIZE) + 15) // 16 * 16  # 80
SQLITE_HEADER = b"SQLite format 3\x00"
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x2000

# 指针桩模式（源自 WeChatDataAnalysis key_v4.py 的 yara 规则）：
# 6 任意字节 + 10 个 0x00 + 0x20,0x00*7 + 0x2f,0x00*6
_STUB_PATTERN = re.compile(rb"[\x00-\xff]{6}\x00{10}\x20\x00{7}\x2f\x00{6}", re.DOTALL)


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------- 进程与内存 ----------

def find_weixin_pid() -> int:
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Weixin.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, check=True,
    ).stdout
    for line in out.splitlines():
        if line.lower().startswith('"weixin.exe"'):
            return int(line.split('","')[1].strip('"'))
    raise RuntimeError(
        "未找到运行中的 Weixin.exe——请先安装并登录微信 4.x（登录后保持在线）"
    )


class ProcessMemory:
    def __init__(self, pid: int):
        self.handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid
        )
        if not self.handle:
            raise RuntimeError(
                f"OpenProcess({pid}) 失败（错误码 {ctypes.GetLastError()}）——"
                "请用管理员身份运行终端后重试"
            )

    def regions(self) -> list[tuple[int, int]]:
        class MBI(ctypes.Structure):
            _fields_ = [
                ("BaseAddress", ctypes.c_void_p),
                ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", ctypes.c_ulong),
                ("RegionSize", ctypes.c_size_t),
                ("State", ctypes.c_ulong),
                ("Protect", ctypes.c_ulong),
                ("Type", ctypes.c_ulong),
            ]

        regions, addr, mbi = [], 0, MBI()
        while ctypes.windll.kernel32.VirtualQueryEx(
            self.handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)
        ):
            if mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE and mbi.RegionSize <= 64 << 20:
                regions.append((mbi.BaseAddress, mbi.RegionSize))
            addr += mbi.RegionSize
        return regions

    def read(self, address: int, size: int) -> bytes | None:
        buf = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t(0)
        ok = ctypes.windll.kernel32.ReadProcessMemory(
            self.handle, ctypes.c_void_p(address), buf, size, ctypes.byref(read)
        )
        return buf.raw[: read.value] if ok and read.value else None

    def close(self) -> None:
        ctypes.windll.kernel32.CloseHandle(self.handle)


# ---------- 密钥候选与验证 ----------

def candidate_keys(pm: ProcessMemory) -> list[bytes]:
    """扫内存：指针桩 → 指针 → 32 字节候选，熵过滤。"""
    stub_addrs: list[int] = []
    total = 0
    for base, size in pm.regions():
        memory = pm.read(base, size)
        total += size or 0
        if not memory:
            continue
        for m in _STUB_PATTERN.finditer(memory):
            stub_addrs.append(struct.unpack_from("<Q", memory, m.start())[0])
    log(f"[*] 指针桩 {len(stub_addrs)} 个（扫描私有内存 {total >> 20} MB）")
    keys: list[bytes] = []
    seen: set[bytes] = set()
    for addr in stub_addrs:
        key = pm.read(addr, KEY_SIZE)
        if key and key not in seen and _is_crypto_material(key):
            seen.add(key)
            keys.append(key)
    log(f"[*] 熵过滤后的密钥候选 {len(keys)} 个")
    return keys


def _is_crypto_material(key: bytes) -> bool:
    """普通文本过滤：相异字节 <15 或可打印字符 >24 的不是密钥。"""
    return len(set(key)) >= 15 and sum(32 <= b <= 126 for b in key) <= 24


def _mac_key_variants(enc_key: bytes, salt: bytes) -> list[bytes]:
    mac_salt = bytes(b ^ 0x3A for b in salt)
    return [hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, dklen=KEY_SIZE)]


def _page1_hmac_ok(enc_key: bytes, page1: bytes, include_iv: bool) -> bool:
    salt = page1[:SALT_SIZE]
    for mk in _mac_key_variants(enc_key, salt):
        data_end = PAGE_SIZE - RESERVE_SIZE + (IV_SIZE if include_iv else 0)
        mac = hmac.new(mk, page1[SALT_SIZE:data_end], hashlib.sha512)
        mac.update(struct.pack("<I", 1))
        start = PAGE_SIZE - RESERVE_SIZE + IV_SIZE
        if mac.digest() == page1[start : start + HMAC_SIZE]:
            return True
    return False


def recover_key(pm: ProcessMemory, sample_db: Path, internal_key: bytes | None) -> str | None:
    page1 = sample_db.read_bytes()[:PAGE_SIZE]
    salt = page1[:SALT_SIZE]
    def derived(raw: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha512", raw, salt, KDF_ROUNDS, dklen=KEY_SIZE)
    combos: list[tuple[str, bytes]] = []
    seen: set[bytes] = set()
    for cand in candidate_keys(pm):
        for xored in (False, True) if internal_key else (False,):
            material = bytes(a ^ b for a, b in zip(cand, internal_key, strict=True)) if xored else cand
            for name, enc in (("raw", material), ("derived", derived(material))):
                if enc in seen:
                    continue
                seen.add(enc)
                combos.append((f"{name}{'^internal' if xored else ''}", enc))
    log(f"[*] 待验证组合 {len(combos)} 个（raw/派生×内部密钥）")
    for i, (name, enc) in enumerate(combos):
        for include_iv in (True, False):
            if _page1_hmac_ok(enc, page1, include_iv):
                log(f"[+] 命中：{name}（mac {'含IV' if include_iv else '不含IV'}）")
                return enc.hex()
        if (i + 1) % 20 == 0:
            log(f"[*] 已验证 {i + 1}/{len(combos)}")
    return None


# ---------- 数据目录与解密 ----------

def find_data_roots(explicit: str | None) -> list[Path]:
    if explicit:
        return [Path(explicit)]
    roots = []
    for base in (
        Path.home() / "Documents",
        Path.home() / "OneDrive" / "Documents",
        Path.home() / "文档",
    ):
        root = base / "xwechat_files"
        if root.is_dir():
            roots.append(root)
    if not roots:
        raise RuntimeError(
            "未找到 xwechat_files 数据目录——首次登录后才会生成；"
            "若迁移过目录请用 --data-root 指定"
        )
    return roots


def pick_account(root: Path) -> Path:
    accounts = [d for d in root.iterdir() if (d / "db_storage").is_dir()]
    if not accounts:
        raise RuntimeError(f"{root} 下没有含 db_storage 的账号目录（登录后生成）")
    accounts.sort(
        key=lambda d: max((f.stat().st_mtime for f in (d / "db_storage").rglob("*.db")), default=0),
        reverse=True,
    )
    if len(accounts) > 1:
        log(f"[*] 多个账号目录，取最近活跃：{accounts[0].name}（其余：{[a.name for a in accounts[1:]]}）")
    return accounts[0]


def pick_sample_db(db_storage: Path) -> Path:
    cands = sorted(
        (f for f in db_storage.rglob("*.db") if f.stat().st_size >= PAGE_SIZE * 4
         and not f.name.endswith(("-wal", "-shm"))),
        key=lambda f: f.stat().st_size,
    )
    for f in cands:
        if f.read_bytes()[:16] != SQLITE_HEADER:
            return f
    raise RuntimeError("db_storage 下未找到加密库文件")


def decrypt_db(src: Path, dst: Path, enc_key: bytes) -> tuple[int, int]:
    """逐页解密；返回 (成功页, HMAC 不匹配页)。HMAC 不匹配的页仍尝试解密。"""
    data = src.read_bytes()
    if len(data) < PAGE_SIZE:
        raise ValueError("文件小于一页")
    salt = data[:SALT_SIZE]
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, dklen=KEY_SIZE)
    pages = []
    ok = bad = 0
    total = len(data) // PAGE_SIZE
    for num in range(1, total + 1):
        page = data[(num - 1) * PAGE_SIZE : num * PAGE_SIZE]
        if len(page) < PAGE_SIZE:
            pages.append(page)
            continue
        start = SALT_SIZE if num == 1 else 0
        iv = page[PAGE_SIZE - RESERVE_SIZE : PAGE_SIZE - RESERVE_SIZE + IV_SIZE]
        plain = AES.new(enc_key, AES.MODE_CBC, iv).decrypt(page[start : PAGE_SIZE - RESERVE_SIZE])
        data_end = PAGE_SIZE - RESERVE_SIZE + IV_SIZE
        mac = hmac.new(mac_key, page[start:data_end], hashlib.sha512)
        mac.update(struct.pack("<I", num))
        stored = page[data_end : data_end + HMAC_SIZE]
        if stored and hmac.compare_digest(mac.digest(), stored):
            ok += 1
        else:
            bad += 1
        pages.append(
            (SQLITE_HEADER if num == 1 else b"") + plain + b"\x00" * RESERVE_SIZE
        )
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(b"".join(pages))
    return ok, bad


def summarize(plain_dir: Path) -> list[dict]:
    import sqlite3

    report = []
    for db in sorted(plain_dir.rglob("*.db")):
        try:
            conn = sqlite3.connect(str(db))
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            ]
            counts = {}
            for t in tables:
                try:
                    counts[t] = conn.execute(f"SELECT COUNT(*) FROM \"{t}\"").fetchone()[0]
                except sqlite3.Error:
                    counts[t] = "?"
            conn.close()
            report.append({"db": db.name, "tables": counts})
        except sqlite3.Error as exc:
            report.append({"db": db.name, "error": str(exc)})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="微信 4.x 取钥+解密（M0-06）")
    parser.add_argument("--data-root", default=None, help="xwechat_files 路径（默认自动找 Documents）")
    parser.add_argument("--internal-key", default=None, help="内部数据库密钥（64 hex，个别库需要）")
    parser.add_argument("--out", default="./data/wechat4_plain", help="解密输出目录")
    args = parser.parse_args()

    pid = find_weixin_pid()
    log(f"[*] Weixin.exe PID={pid}")
    pm = ProcessMemory(pid)
    try:
        root = find_data_roots(args.data_root)[0]
        account = pick_account(root)
        db_storage = account / "db_storage"
        log(f"[*] 账号目录：{account}")
        sample = pick_sample_db(db_storage)
        log(f"[*] 验证样本库：{sample.name}")
        internal = bytes.fromhex(args.internal_key) if args.internal_key else None
        key_hex = recover_key(pm, sample, internal)
    finally:
        pm.close()
    if not key_hex:
        log("[-] 未找到有效密钥：确认微信 4.x 已登录且收发过消息；换一个 --data-root 或提供 --internal-key")
        return 1
    log("[+] 密钥已取得（不回显）")

    enc_key = bytes.fromhex(key_hex)
    out_dir = Path(args.out) / account.name
    log(f"[*] 解密 {db_storage} → {out_dir}")
    results = []
    for src in sorted(db_storage.rglob("*.db")):
        if src.name.endswith(("-wal", "-shm")):
            continue
        if src.read_bytes()[:16] == SQLITE_HEADER:
            log(f"  - {src.name}：已是明文库，跳过")
            continue
        rel = src.relative_to(db_storage)
        try:
            ok, bad = decrypt_db(src, out_dir / rel, enc_key)
            results.append(f"  + {rel}: 页 OK {ok} / HMAC 异常 {bad}")
            log(results[-1])
        except Exception as exc:  # 单库失败不阻断
            log(f"  - {rel}: 解密失败 {exc}")

    log("[*] 解密库表结构摘要（用于采集端字段映射）：")
    report = summarize(out_dir)
    log(json.dumps(report, ensure_ascii=False, indent=1)[:4000])
    (out_dir / "_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    log(f"[✓] 完成。明文库在 {out_dir}，表结构摘要见 _summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
