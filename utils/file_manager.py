"""
File management utilities for 3D Agent Generation System
"""
import os
import shutil
import hashlib
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import json


class FileManager:
    """Manager for handling file operations"""

    def __init__(self, base_output_dir: str = "./outputs"):
        self.base_output_dir = Path(base_output_dir)
        self.flux_dir = self.base_output_dir / "flux"
        self.previews_dir = self.base_output_dir / "previews"
        self.models_dir = self.base_output_dir / "models"
        self.temp_dir = self.base_output_dir / "temp"

        self._ensure_directories()

    def _ensure_directories(self):
        """Create necessary directories"""
        self.base_output_dir.mkdir(parents=True, exist_ok=True)
        self.flux_dir.mkdir(parents=True, exist_ok=True)
        self.previews_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def generate_filename(
        self,
        prefix: str = "model",
        extension: str = ".stl",
        timestamp: bool = True
    ) -> str:
        """Generate unique filename"""
        if timestamp:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"{prefix}_{ts}{extension}"
        else:
            import uuid
            unique_id = uuid.uuid4().hex[:8]
            return f"{prefix}_{unique_id}{extension}"

    def get_model_path(self, filename: str) -> Path:
        """Get full path for model file"""
        return self.models_dir / filename

    def get_preview_path(self, filename: str) -> Path:
        """Get full path for preview image"""
        return self.previews_dir / filename

    def get_flux_path(self, filename: str) -> Path:
        """Get full path for Flux image"""
        return self.flux_dir / filename

    def get_temp_path(self, filename: str) -> Path:
        """Get full path for temporary file"""
        return self.temp_dir / filename

    def save_metadata(self, model_path: Path, metadata: dict):
        """Save metadata JSON alongside model file"""
        metadata_path = model_path.with_suffix('.json')

        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    def load_metadata(self, model_path: Path) -> Optional[dict]:
        """Load metadata JSON for a model file"""
        metadata_path = model_path.with_suffix('.json')

        if not metadata_path.exists():
            return None

        with open(metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def calculate_file_hash(self, file_path: Path, algorithm: str = "sha256") -> str:
        """Calculate hash of a file"""
        hash_func = hashlib.new(algorithm)

        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hash_func.update(chunk)

        return hash_func.hexdigest()

    def list_models(self, pattern: str = "*.stl") -> List[Path]:
        """List all model files in models directory"""
        return sorted(self.models_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    def list_previews(self, pattern: str = "*.png") -> List[Path]:
        """List all preview images"""
        return sorted(self.previews_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    def cleanup_temp_files(self, older_than_hours: int = 24):
        """Remove temporary files older than specified hours"""
        import time

        current_time = time.time()
        cutoff_time = current_time - (older_than_hours * 3600)

        for temp_file in self.temp_dir.glob("*"):
            if temp_file.stat().st_mtime < cutoff_time:
                try:
                    if temp_file.is_file():
                        temp_file.unlink()
                    elif temp_file.is_dir():
                        shutil.rmtree(temp_file)
                except Exception as e:
                    print(f"Error cleaning up {temp_file}: {e}")

    def get_file_size_mb(self, file_path: Path) -> float:
        """Get file size in megabytes"""
        return file_path.stat().st_size / (1024 * 1024)

    def copy_to_output(self, source_path: Path, destination_name: Optional[str] = None) -> Path:
        """Copy file to models output directory"""
        if destination_name is None:
            destination_name = source_path.name

        dest_path = self.get_model_path(destination_name)
        shutil.copy2(source_path, dest_path)

        return dest_path

    def export_batch(self, model_paths: List[Path], export_dir: Path) -> List[Path]:
        """Export multiple models to a directory"""
        export_dir.mkdir(parents=True, exist_ok=True)

        exported_paths = []
        for model_path in model_paths:
            dest_path = export_dir / model_path.name
            shutil.copy2(model_path, dest_path)
            exported_paths.append(dest_path)

            # Also copy metadata if exists
            metadata_path = model_path.with_suffix('.json')
            if metadata_path.exists():
                dest_metadata = dest_path.with_suffix('.json')
                shutil.copy2(metadata_path, dest_metadata)

        return exported_paths

    def __repr__(self):
        return f"FileManager(base_output_dir='{self.base_output_dir}')"
