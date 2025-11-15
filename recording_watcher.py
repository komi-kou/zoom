"""
録画ファイルの監視モジュール
ローカル録画ファイルの作成をリアルタイムで検知
"""
import os
import time
import asyncio
from pathlib import Path
from typing import Optional, Callable
import logging

logger = logging.getLogger(__name__)

# watchdogはオプショナル
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logger.warning("watchdogモジュールがインストールされていません。リアルタイム監視は無効です。")


if WATCHDOG_AVAILABLE:
    class RecordingFileHandler(FileSystemEventHandler):
        """録画ファイルの作成・変更を監視するハンドラー"""
        
        def __init__(self, callback: Callable, min_size_mb: float = 1.0, stable_time: int = 10):
            """
            初期化
            
            Args:
                callback: ファイル検出時に呼び出すコールバック関数
                min_size_mb: 最小ファイルサイズ（MB）
                stable_time: ファイルが安定するまでの待機時間（秒）
            """
            self.callback = callback
            self.min_size_bytes = min_size_mb * 1024 * 1024
            self.stable_time = stable_time
            self.pending_files = {}  # ファイルパス: 検出時刻
        
        def on_created(self, event):
            """ファイル作成イベント"""
            if not event.is_directory:
                self._handle_file(event.src_path)
        
        def on_modified(self, event):
            """ファイル変更イベント"""
            if not event.is_directory:
                self._handle_file(event.src_path)
        
        def _handle_file(self, file_path: str):
            """ファイルを処理"""
            # 録画ファイルの拡張子をチェック
            ext = Path(file_path).suffix.lower()
            if ext not in [".mp4", ".mov", ".m4a", ".mp3", ".wav", ".avi", ".mkv"]:
                return
            
            # ファイルサイズをチェック
            try:
                file_size = os.path.getsize(file_path)
                if file_size < self.min_size_bytes:
                    return
                
                # ファイルが安定するまで待機（書き込み中の可能性があるため）
                current_time = time.time()
                
                if file_path in self.pending_files:
                    # 既に検出済みのファイル
                    first_seen = self.pending_files[file_path]
                    elapsed = current_time - first_seen
                    
                    if elapsed >= self.stable_time:
                        # ファイルが安定したと判断
                        # 再度サイズを確認（書き込みが完了しているか）
                        new_size = os.path.getsize(file_path)
                        if new_size == file_size:
                            # サイズが変わっていない = 書き込み完了
                            logger.info(f"録画ファイルの作成を検知: {file_path} ({new_size / 1024 / 1024:.2f}MB)")
                            self.callback(file_path)
                            del self.pending_files[file_path]
                else:
                    # 新規検出
                    self.pending_files[file_path] = current_time
                    logger.debug(f"録画ファイルを検知（監視中）: {file_path}")
            
            except Exception as e:
                logger.warning(f"ファイル処理エラー: {file_path} - {e}")


class RecordingWatcher:
    """録画ファイルの監視クラス"""
    
    def __init__(self, recording_directory: Path, callback: Callable, min_size_mb: float = 1.0):
        """
        初期化
        
        Args:
            recording_directory: 監視するディレクトリ
            callback: ファイル検出時に呼び出すコールバック関数
            min_size_mb: 最小ファイルサイズ（MB）
        """
        self.recording_directory = recording_directory
        self.callback = callback
        self.min_size_mb = min_size_mb
        self.observer = None
        self.handler = None
    
    def start(self):
        """監視を開始"""
        if not WATCHDOG_AVAILABLE:
            logger.warning("watchdogモジュールがインストールされていません。リアルタイム監視は無効です。")
            logger.info("インストール方法: pip install watchdog")
            return
        
        if not self.recording_directory.exists():
            logger.warning(f"監視ディレクトリが存在しません: {self.recording_directory}")
            return
        
        self.handler = RecordingFileHandler(
            callback=self.callback,
            min_size_mb=self.min_size_mb,
            stable_time=10  # 10秒待機してファイルが安定するのを確認
        )
        
        self.observer = Observer()
        self.observer.schedule(self.handler, str(self.recording_directory), recursive=True)
        self.observer.start()
        
        logger.info(f"録画ファイルの監視を開始: {self.recording_directory}")
    
    def stop(self):
        """監視を停止"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("録画ファイルの監視を停止しました")
    
    def is_alive(self) -> bool:
        """監視が動作中かどうか"""
        if not WATCHDOG_AVAILABLE:
            return False
        return self.observer is not None and self.observer.is_alive()

