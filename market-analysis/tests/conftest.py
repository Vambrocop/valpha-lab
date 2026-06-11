"""把 scripts/ 加进导入路径——测试直接 import 生产模块，不复制逻辑"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
