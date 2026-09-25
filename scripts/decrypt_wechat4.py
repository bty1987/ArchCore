"""微信 4.x 本地库密钥提取 + 解密（M0-06 验证工具，自包含实现）。

用法（管理员终端、微信 4.x 已登录）：
    python scripts/decrypt_wechat4.py                 # 全自动：找库→取钥→解密→报告表结构
    python scripts/decrypt_wechat4.py --data-root D:\\xwechat_files

原理（对齐 WeChatDataAnalysis/DbkeyHook 的公开实现）：
- 4.x 数据目录：xwechat_files/<账号>/db_storage/**.db，SQLCipher 4 参数：
  页 4096B、PBKDF2-SHA512 256000 轮（口令派生变体）、AES-256-CBC、每页 reserve=80
  （IV 16B + HMAC-SHA512 64B）、页 1 前 16B 为 salt；
- 真实密钥 = 内存密钥 XOR 内部密钥（internal_db_key）。内部密钥藏在安装目录 Weixin.dll
  代码段中：四条 `mov rdx, imm64` 指令各载入 8 字节，拼成 32 字节（dll_key_scan 模式）；
- 内存密钥在 Weixin.exe 私有内存中以「指针桩」模式定位（32B 固定模式，key_v4 的 yara
  规则转正则），候选经熵过滤后与内部密钥组合，对样本库页 1 做 HMAC 校验（raw 与口令
  派生两种变体，多进程验证）；
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
from ctypes import wintypes
from multiprocessing import Pool, cpu_count
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
MEM_PRIVATE = 0x20000
CODE_SECTION_CHARACTERISTIC = 0x20000000

# 指针桩模式（key_v4.py 的 yara 规则）：6 任意字节 + 10 个 0x00 + 0x20,0x00*7 + 0x2f,0x00*6
_STUB_PATTERN = re.compile(rb"[\x00-\xff]{6}\x00{10}\x20\x00{7}\x2f\x00{6}", re.DOTALL)

# Weixin.dll 内部密钥模式（dll_key_scan.py）：四条 mov rdx, imm64 + test rax, rax
_DLL_KEY_PATTERN = re.compile(
    b"\x48\xBA(.{8})" b".{3,8}?" b"\x48\xBA(.{8})" b".{3,8}?"
    b"\x48\xBA(.{8})" b".{3,8}?" b"\x48\xBA(.{8})" b".{3,8}?"
    b"\x48\x85\xC0",
    re.DOTALL,
)


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------- 进程与内存 ----------

def find_weixin_pids() -> list[int]:
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Weixin.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, check=True,
    ).stdout
    pids = [
        int(line.split('","')[1].strip('"'))
        for line in out.splitlines()
        if line.lower().startswith('"weixin.exe"')
    ]
    if not pids:
        raise RuntimeError(
            "未找到运行中的 Weixin.exe——请先安装并登录微信 4.x（登录后保持在线）"
        )
    return pids


def find_weixin_install(pid: int) -> Path:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {pid}).Path"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if not out:
        raise RuntimeError("无法获取 Weixin.exe 路径（进程可能已退出）")
    return Path(out).parent


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

        vqe = ctypes.windll.kernel32.VirtualQueryEx
        vqe.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
        vqe.restype = ctypes.c_size_t
        mbi = MBI()
        regions, addr = [], 0
        while vqe(self.handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            if mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE:
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


# ---------- 密钥候选 ----------

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
    log(f"[*] 熵过滤后的内存密钥候选 {len(keys)} 个")
    return keys


def scan_dll_internal_keys(dll_path: Path) -> list[bytes]:
    """扫 Weixin.dll 代码段：mov rdx, imm64 ×4 拼出 32 字节内部密钥候选。"""
    import pefile

    pe = pefile.PE(str(dll_path), fast_load=True)
    keys: list[bytes] = []
    seen: set[bytes] = set()
    try:
        data = dll_path.read_bytes()
        for section in pe.sections:
            if not (int(section.Characteristics) & CODE_SECTION_CHARACTERISTIC):
                continue
            off = int(section.PointerToRawData)
            chunk = data[off : off + int(section.SizeOfRawData)]
            idx = 0
            while True:
                pos = chunk.find(b"\x48\xBA", idx)
                if pos == -1:
                    break
                m = _DLL_KEY_PATTERN.match(chunk[pos : pos + 85])
                if m:
                    key = m.group(1) + m.group(2) + m.group(3) + m.group(4)
                    if key not in seen:
                        seen.add(key)
                        keys.append(key)
                    idx = pos + len(m.group(0))
                else:
                    idx = pos + 1
    finally:
        pe.close()
    log(f"[*] Weixin.dll 内部密钥候选 {len(keys)} 个（{dll_path.name}）")
    return keys


def _is_crypto_material(key: bytes) -> bool:
    """普通文本过滤：相异字节 <15 或可打印字符 >24 的不是密钥。"""
    return len(set(key)) >= 15 and sum(32 <= b <= 126 for b in key) <= 24


# ---------- 验证 ----------

def _mac_key(enc_key: bytes, salt: bytes) -> bytes:
    mac_salt = bytes(b ^ 0x3A for b in salt)
    return hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, dklen=KEY_SIZE)


def _page1_hmac_ok(enc_key: bytes, page1: bytes, include_iv: bool) -> bool:
    salt = page1[:SALT_SIZE]
    mk = _mac_key(enc_key, salt)
    data_end = PAGE_SIZE - RESERVE_SIZE + (IV_SIZE if include_iv else 0)
    mac = hmac.new(mk, page1[SALT_SIZE:data_end], hashlib.sha512)
    mac.update(struct.pack("<I", 1))
    start = PAGE_SIZE - RESERVE_SIZE + IV_SIZE
    return hmac.compare_digest(mac.digest(), page1[start : start + HMAC_SIZE])


def _derive(raw: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha512", raw, salt, KDF_ROUNDS, dklen=KEY_SIZE)


def _verify_task(args: tuple[str, str, bytes, bytes]) -> tuple[str, str, bytes] | None:
    name, mat_hex, enc, page1 = args
    for include_iv in (True, False):
        if _page1_hmac_ok(enc, page1, include_iv):
            return name, mat_hex, enc
    return None


def build_combos(
    mem_keys: list[bytes], salt: bytes, internal_keys: list[bytes]
) -> list[tuple[str, str, bytes]]:
    """按已命中形式优先排序：derived^(mem^dll) → raw^(mem^dll) → 无 XOR 变体。"""
    combos: list[tuple[str, str, bytes]] = []
    seen: set[bytes] = set()

    def add(name: str, mat_hex: str, enc: bytes) -> None:
        if enc not in seen:
            seen.add(enc)
            combos.append((name, mat_hex, enc))

    ik_list: list[tuple[str, bytes | None]] = [(f"dll#{i}", ik) for i, ik in enumerate(internal_keys)] + [
        ("无XOR", None)
    ]
    for cand in mem_keys:
        for ik_name, ik in ik_list:
            material = (
                bytes(a ^ b for a, b in zip(cand, ik, strict=True)) if ik is not None else cand
            )
            mat_hex = material.hex()
            add(f"derived^{ik_name}", mat_hex, _derive(material, salt))
            add(f"raw^{ik_name}", mat_hex, material)
    return combos


def verify_combos(
    pool: Pool, combos: list[tuple[str, str, bytes]], page1: bytes
) -> tuple[str, str, bytes] | None:
    """返回 (命中名称, passphrase 十六进制, 该库派生密钥)。"""
    tasks = [(name, mat_hex, enc, page1) for name, mat_hex, enc in combos]
    for i, result in enumerate(pool.imap_unordered(_verify_task, tasks, chunksize=4)):
        if (i + 1) % 100 == 0:
            log(f"    已验证 {i + 1}/{len(combos)}")
        if result is not None:
            return result
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


def _is_encrypted_db(f: Path) -> bool:
    return (
        f.suffix.lower() == ".db"
        and not f.name.endswith(("-wal", "-shm"))
        and f.stat().st_size >= PAGE_SIZE * 2
        and f.read_bytes()[:16] != SQLITE_HEADER
    )


def pick_sample_db(db_storage: Path) -> Path:
    """优先 favorite/session/contact 等主库（bizchat 等可能用独立密钥）。"""
    all_dbs = [f for f in db_storage.rglob("*.db") if _is_encrypted_db(f)]
    if not all_dbs:
        raise RuntimeError("db_storage 下未找到加密库文件")
    for name in ("favorite.db", "session.db", "contact.db", "general.db", "message_0.db"):
        for f in all_dbs:
            if f.name == name:
                return f
    return min(all_dbs, key=lambda f: f.stat().st_size)


def decrypt_db(src: Path, dst: Path, enc_key: bytes) -> tuple[int, int]:
    """逐页解密；返回 (成功页, HMAC 不匹配页)。HMAC 不匹配的页仍尝试解密。"""
    data = src.read_bytes()
    if len(data) < PAGE_SIZE:
        raise ValueError("文件小于一页")
    salt = data[:SALT_SIZE]
    mac_key = _mac_key(enc_key, salt)
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
    parser.add_argument("--internal-key", default=None, help="手工指定内部密钥（64 hex，通常不需要）")
    parser.add_argument("--out", default="./data/wechat4_plain", help="解密输出目录")
    parser.add_argument("--db-filter", default=None, help="只处理文件名含该子串的库")
    args = parser.parse_args()
    saved_passphrase = None
    key_file = Path("./data/wechat4_key.json")
    if key_file.exists():
        saved_passphrase = bytes.fromhex(
            json.loads(key_file.read_text(encoding="utf-8"))["passphrase_hex"]
        )
        log("[*] 已加载保存的 passphrase（data/wechat4_key.json）")

    pids = find_weixin_pids()
    log(f"[*] Weixin.exe 进程：{pids}（逐个尝试，密钥在主进程）")
    install_dir = find_weixin_install(pids[0])
    dlls = sorted(install_dir.rglob("Weixin.dll"), key=lambda f: f.stat().st_size, reverse=True)
    internal_keys = scan_dll_internal_keys(dlls[0]) if dlls else []
    if not dlls:
        log(f"[!] 安装目录下未找到 Weixin.dll：{install_dir}")
    if not internal_keys:
        log("[!] 未从 Weixin.dll 扫到内部密钥候选（继续用无 XOR 组合尝试）")

    root = find_data_roots(args.data_root)[0]
    account = pick_account(root)
    db_storage = account / "db_storage"
    log(f"[*] 账号目录：{account}")
    sample = pick_sample_db(db_storage)
    log(f"[*] 验证样本库：{sample.relative_to(db_storage)}")

    mem_keys_by_pid: dict[int, list[bytes]] = {}
    for pid in pids:
        pm = ProcessMemory(pid)
        try:
            log(f"[*] 扫描 PID {pid} …")
            mem_keys_by_pid[pid] = candidate_keys(pm)
        finally:
            pm.close()

    out_dir = Path(args.out) / account.name
    encrypted = [
        f for f in sorted(db_storage.rglob("*.db"))
        if _is_encrypted_db(f) and (args.db_filter is None or args.db_filter in f.name)
    ]
    log(f"[*] 待解密库 {len(encrypted)} 个（逐库验证密钥——4.1.15 每库独立密钥）")
    out_dir.mkdir(parents=True, exist_ok=True)
    with Pool(processes=max(1, cpu_count() // 2)) as pool:
        for src_db in encrypted:
            rel = src_db.relative_to(db_storage)
            dst = out_dir / rel
            if dst.is_file() and dst.read_bytes()[:16] == SQLITE_HEADER:
                log(f"  = {rel}: 已解密，跳过")
                continue
            key_hex = None
            page1 = src_db.read_bytes()[:PAGE_SIZE]
            if saved_passphrase is not None:
                for enc in (
                    _derive(saved_passphrase, page1[:SALT_SIZE]),
                    saved_passphrase,
                ):
                    if _page1_hmac_ok(enc, page1, include_iv=True):
                        key_hex = enc.hex()
                        log("    用已保存 passphrase 直接命中")
                        break
            if key_hex is None:
                for pid in pids:
                    mem_keys = mem_keys_by_pid.get(pid) or []
                    if not mem_keys:
                        continue
                    combos = build_combos(mem_keys, page1[:SALT_SIZE], internal_keys)
                    result = verify_combos(pool, combos, page1)
                    if result is not None:
                        hit_name, mat_hex, enc = result
                        key_hex = enc.hex()
                        log(f"[+] {rel} 命中：{hit_name}")
                        if saved_passphrase is None:
                            saved_passphrase = bytes.fromhex(mat_hex)
                            key_file.write_text(
                                json.dumps(
                                    {"passphrase_hex": saved_passphrase.hex(),
                                     "account": account.name},
                                    ensure_ascii=False, indent=1,
                                ),
                                encoding="utf-8",
                            )
                            log("[+] passphrase 已保存到 data/wechat4_key.json（不回显）")
                        break
            if not key_hex:
                log(f"  ! {rel}: 未找到该库的密钥")
                continue
            try:
                ok, bad = decrypt_db(src_db, dst, bytes.fromhex(key_hex))
                log(f"  + {rel}: 解密成功（页 OK {ok} / HMAC 异常 {bad}）")
            except Exception as exc:  # 单库失败不阻断
                log(f"  - {rel}: 解密失败 {exc}")

    log("[*] 解密库表结构摘要（用于采集端字段映射）：")
    report = summarize(out_dir)
    log(json.dumps(report, ensure_ascii=False, indent=1)[:4000])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    log(f"[✓] 完成。明文库在 {out_dir}，表结构摘要见 _summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
