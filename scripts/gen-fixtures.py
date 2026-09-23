"""gen-fixtures：生成脱敏合成样本库（开发/测试/演示专用，真实数据红线）。

用法：python scripts/gen-fixtures.py [--out ./data/fixture_wechat.db] [--days 120]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector" / "src"))

from archcore_collector.fixtures import generate

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="生成脱敏合成微信样本库")
    parser.add_argument("--out", default="./data/fixture_wechat.db")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(generate(args.out, args.days, args.seed), ensure_ascii=False, indent=2))
