"""
Zoomローカル録画ファイルの自動検出モジュール
Zoomの設定ファイルから録画保存先を取得し、録画ファイルを検出する
"""
import os
import platform
import configparser
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class LocalRecordingDetector:
    """Zoomローカル録画ファイルの検出クラス"""
    
    def __init__(self):
        """初期化"""
        self.system = platform.system()
        self.zoom_config_path = self._get_zoom_config_path()
        self.default_recording_paths = self._get_default_recording_paths()
    
    def _get_zoom_config_path(self) -> Optional[Path]:
        """
        Zoom設定ファイルのパスを取得
        
        Returns:
            Zoom設定ファイルのパス（見つからない場合はNone）
        """
        home = Path.home()
        
        if self.system == "Darwin":  # macOS
            config_path = home / "Library" / "Application Support" / "zoom.us" / "Zoom.us.ini"
        elif self.system == "Windows":
            config_path = home / "AppData" / "Roaming" / "Zoom" / "data" / "Zoom.us.ini"
        elif self.system == "Linux":
            config_path = home / ".config" / "zoom" / "Zoom.us.ini"
        else:
            logger.warning(f"サポートされていないOS: {self.system}")
            return None
        
        return config_path if config_path.exists() else None
    
    def _get_default_recording_paths(self) -> List[Path]:
        """
        デフォルトの録画保存先パスを取得
        
        Returns:
            デフォルトの録画保存先パスのリスト
        """
        home = Path.home()
        default_paths = []
        
        if self.system == "Darwin":  # macOS
            default_paths = [
                home / "Documents" / "Zoom",
                home / "Desktop",
                home / "Downloads",
                home / "Movies" / "Zoom",  # macOSの一般的な録画保存先
                home / "Movies",  # Moviesディレクトリ全体も検索
            ]
        elif self.system == "Windows":
            default_paths = [
                home / "Documents" / "Zoom",
                home / "Desktop",
                home / "Downloads",
                home / "Videos" / "Zoom",  # Windowsの一般的な録画保存先
                home / "Videos",  # Videosディレクトリ全体も検索
            ]
        elif self.system == "Linux":
            default_paths = [
                home / "Documents" / "Zoom",
                home / "Desktop",
                home / "Downloads",
                home / "Videos" / "Zoom",  # Linuxの一般的な録画保存先
                home / "Videos",  # Videosディレクトリ全体も検索
            ]
        
        return default_paths
    
    def get_recording_directory(self) -> Optional[Path]:
        """
        Zoomの録画保存先ディレクトリを取得
        
        1. Zoom設定ファイルから取得を試みる
        2. デフォルトの保存先を確認
        
        Returns:
            録画保存先ディレクトリのパス（見つからない場合はNone）
        """
        # 1. Zoom設定ファイルから取得
        if self.zoom_config_path:
            try:
                config = configparser.ConfigParser()
                config.read(self.zoom_config_path, encoding='utf-8')
                
                # GeneralセクションのZoomPathを確認
                if "General" in config:
                    zoom_path = config["General"].get("ZoomPath")
                    if zoom_path:
                        recording_path = Path(zoom_path)
                        if recording_path.exists():
                            logger.info(f"Zoom設定ファイルから録画保存先を取得: {recording_path}")
                            return recording_path
                
                # RecordingセクションのLocalRecordingPathを確認
                if "Recording" in config:
                    local_recording_path = config["Recording"].get("LocalRecordingPath")
                    if local_recording_path:
                        recording_path = Path(local_recording_path)
                        if recording_path.exists():
                            logger.info(f"Zoom設定ファイルから録画保存先を取得: {recording_path}")
                            return recording_path
            except Exception as e:
                logger.warning(f"Zoom設定ファイルの読み込みに失敗: {e}")
        
        # 2. デフォルトの保存先を確認
        for default_path in self.default_recording_paths:
            if default_path.exists():
                logger.info(f"デフォルトの録画保存先を使用: {default_path}")
                return default_path
        
        logger.warning("録画保存先が見つかりませんでした")
        return None
    
    def find_recordings(
        self, 
        directory: Optional[Path] = None,
        hours: Optional[int] = 24,
        min_size_mb: float = 1.0,
        search_multiple_dirs: bool = True
    ) -> List[Dict[str, any]]:
        """
        録画ファイルを検索
        
        Args:
            directory: 検索するディレクトリ（Noneの場合は自動検出）
            hours: 検索する時間範囲（時間単位、Noneの場合は制限なし、デフォルト: 24時間）
            min_size_mb: 最小ファイルサイズ（MB、デフォルト: 1.0MB）
            search_multiple_dirs: Trueの場合、複数のデフォルトディレクトリも検索（デフォルト: True）
            
        Returns:
            録画ファイル情報のリスト
        """
        all_recordings = []
        
        # 検索対象ディレクトリのリスト
        search_directories = []
        
        if directory:
            search_directories.append(directory)
        else:
            # 自動検出: まず設定ファイルから取得したディレクトリを使用
            detected_dir = self.get_recording_directory()
            if detected_dir:
                search_directories.append(detected_dir)
            
            # 複数ディレクトリ検索が有効な場合、デフォルトパスも追加
            if search_multiple_dirs:
                for default_path in self.default_recording_paths:
                    if default_path.exists() and default_path not in search_directories:
                        search_directories.append(default_path)
        
        if not search_directories:
            logger.warning(f"録画保存先が見つかりません")
            return []
        
        # 各ディレクトリを検索
        for search_dir in search_directories:
            recordings = self._search_in_directory(search_dir, hours, min_size_mb)
            all_recordings.extend(recordings)
        
        # 重複を除去（同じファイルパスの場合）
        seen_paths = set()
        unique_recordings = []
        for rec in all_recordings:
            if rec['path'] not in seen_paths:
                seen_paths.add(rec['path'])
                unique_recordings.append(rec)
        
        # 更新日時でソート（新しい順）
        unique_recordings.sort(key=lambda x: x["modified_time"], reverse=True)
        
        logger.info(f"{len(unique_recordings)}件の録画ファイルが見つかりました（{len(search_directories)}個のディレクトリを検索）")
        return unique_recordings
    
    def _search_in_directory(
        self,
        directory: Path,
        hours: Optional[int],
        min_size_mb: float
    ) -> List[Dict[str, any]]:
        """
        指定されたディレクトリ内で録画ファイルを検索
        
        Args:
            directory: 検索するディレクトリ
            hours: 検索する時間範囲（時間単位、Noneの場合は制限なし）
            min_size_mb: 最小ファイルサイズ（MB）
            
        Returns:
            録画ファイル情報のリスト
        """
        if not directory or not directory.exists():
            return []
        
        # Pathオブジェクトに変換
        directory = Path(directory)
        
        if not directory.exists():
            logger.warning(f"録画保存先が存在しません: {directory}")
            return []
        
        recordings = []
        # hoursがNoneの場合は時間制限なし
        cutoff_time = None if hours is None else datetime.now() - timedelta(hours=hours)
        min_size_bytes = min_size_mb * 1024 * 1024
        
        time_range_str = "制限なし" if hours is None else f"過去{hours}時間"
        logger.info(f"録画ファイルを検索中: {directory}, 時間範囲: {time_range_str}, 最小サイズ: {min_size_mb}MB")
        
        # MP4、MOV、M4A、MP3、ZOOMファイルを検索（rglobで再帰的に検索）
        # .zoomファイルはZoomの独自形式で、通常はMP4に変換が必要ですが、検索対象に含めます
        for ext in ["*.mp4", "*.mov", "*.m4a", "*.mp3", "*.zoom"]:
            try:
                for file_path in directory.rglob(ext):
                    try:
                        stat = file_path.stat()
                        file_size_mb = stat.st_size / 1024 / 1024
                        file_mtime = datetime.fromtimestamp(stat.st_mtime)
                        
                        # サイズでフィルタリング
                        if stat.st_size < min_size_bytes:
                            continue
                        
                        # 時間でフィルタリング（cutoff_timeがNoneの場合はスキップ）
                        if cutoff_time is not None and file_mtime < cutoff_time:
                            continue
                        
                        recordings.append({
                            "path": str(file_path),
                            "name": file_path.name,
                            "size_mb": file_size_mb,
                            "modified_time": file_mtime,
                            "extension": file_path.suffix.lower()
                        })
                        logger.debug(f"録画ファイルを発見: {file_path.name} ({file_size_mb:.2f} MB, {file_mtime})")
                    except (OSError, PermissionError) as e:
                        logger.warning(f"ファイル情報の取得に失敗: {file_path} - {e}")
                    except Exception as e:
                        logger.warning(f"予期しないエラー: {file_path} - {e}")
            except Exception as e:
                logger.warning(f"拡張子 {ext} の検索中にエラー: {e}")
        
        return recordings
    
    def find_latest_recording(
        self,
        directory: Optional[Path] = None,
        hours: Optional[int] = 24,
        min_size_mb: float = 1.0
    ) -> Optional[Dict[str, any]]:
        """
        最新の録画ファイルを取得
        
        Args:
            directory: 検索するディレクトリ（Noneの場合は自動検出）
            hours: 検索する時間範囲（時間単位、Noneの場合は制限なし、デフォルト: 24時間）
            min_size_mb: 最小ファイルサイズ（MB、デフォルト: 1.0MB）
            
        Returns:
            最新の録画ファイル情報（見つからない場合はNone）
        """
        recordings = self.find_recordings(directory, hours, min_size_mb, search_multiple_dirs=True)
        return recordings[0] if recordings else None
    
    def find_recording_by_meeting_id(
        self,
        meeting_id: str,
        directory: Optional[Path] = None,
        hours: Optional[int] = None  # Noneの場合は全て検索
    ) -> Optional[Dict[str, any]]:
        """
        ミーティングIDに関連する録画ファイルを検索
        
        Args:
            meeting_id: ZoomミーティングID
            directory: 検索するディレクトリ（Noneの場合は自動検出）
            hours: 検索する時間範囲（時間単位、Noneの場合は制限なし、デフォルト: None）
            
        Returns:
            録画ファイル情報（見つからない場合はNone）
        """
        recordings = self.find_recordings(directory, hours, min_size_mb=1.0, search_multiple_dirs=True)
        
        # ファイル名にミーティングIDが含まれるものを検索
        for recording in recordings:
            if meeting_id in recording["name"]:
                logger.info(f"ミーティングID {meeting_id} に関連する録画ファイルを発見: {recording['path']}")
                return recording
        
        # ファイル名に含まれない場合は、最新の録画を返す
        if recordings:
            logger.info(f"ミーティングID {meeting_id} に直接関連する録画は見つかりませんでしたが、最新の録画を返します: {recordings[0]['path']}")
            return recordings[0]
        
        return None

