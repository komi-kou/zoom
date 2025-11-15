#!/usr/bin/env python3
"""インポートテストスクリプト"""
import sys
import time

print("app.pyのインポートを開始...")
start_time = time.time()

try:
    import app
    elapsed = time.time() - start_time
    print(f"✅ インポート成功（{elapsed:.2f}秒）")
    sys.exit(0)
except Exception as e:
    elapsed = time.time() - start_time
    print(f"❌ インポート失敗（{elapsed:.2f}秒）: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

