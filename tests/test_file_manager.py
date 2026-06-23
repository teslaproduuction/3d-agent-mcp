"""
Tests for file management utilities
"""
import pytest
from pathlib import Path
import tempfile
import shutil
from utils.file_manager import FileManager


@pytest.fixture
def temp_output_dir():
    """Create temporary output directory"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


def test_file_manager_init(temp_output_dir):
    """Test FileManager initialization"""
    fm = FileManager(base_output_dir=temp_output_dir)

    assert fm.base_output_dir.exists()
    assert fm.flux_dir.exists()
    assert fm.previews_dir.exists()
    assert fm.models_dir.exists()
    assert fm.temp_dir.exists()


def test_generate_filename():
    """Test filename generation"""
    fm = FileManager()

    # With timestamp
    filename = fm.generate_filename(prefix="model", extension=".stl", timestamp=True)
    assert filename.startswith("model_")
    assert filename.endswith(".stl")

    # Without timestamp
    filename = fm.generate_filename(prefix="preview", extension=".png", timestamp=False)
    assert filename.startswith("preview_")
    assert filename.endswith(".png")


def test_get_paths():
    """Test path getter methods"""
    fm = FileManager()

    model_path = fm.get_model_path("test.stl")
    assert "models" in str(model_path)
    assert model_path.name == "test.stl"

    preview_path = fm.get_preview_path("test.png")
    assert "previews" in str(preview_path)

    flux_path = fm.get_flux_path("test.png")
    assert "flux" in str(flux_path)
    assert flux_path.name == "test.png"

    temp_path = fm.get_temp_path("temp.glb")
    assert "temp" in str(temp_path)


def test_save_and_load_metadata(temp_output_dir):
    """Test metadata save/load"""
    fm = FileManager(base_output_dir=temp_output_dir)

    model_path = fm.get_model_path("test_model.stl")
    model_path.touch()  # Create empty file

    metadata = {
        "volume": 1000.0,
        "print_time": 2.5,
        "complexity": "medium"
    }

    fm.save_metadata(model_path, metadata)

    loaded_metadata = fm.load_metadata(model_path)

    assert loaded_metadata is not None
    assert loaded_metadata['volume'] == 1000.0
    assert loaded_metadata['complexity'] == "medium"


def test_list_models(temp_output_dir):
    """Test listing model files"""
    fm = FileManager(base_output_dir=temp_output_dir)

    # Create test files
    (fm.models_dir / "model1.stl").touch()
    (fm.models_dir / "model2.stl").touch()
    (fm.models_dir / "model3.obj").touch()

    stl_models = fm.list_models(pattern="*.stl")
    assert len(stl_models) == 2

    all_models = fm.list_models(pattern="*")
    assert len(all_models) >= 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
