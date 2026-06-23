"""
Image processing utilities including background removal
"""
from pathlib import Path
from typing import Union, Optional
import logging
import os
import io
import time

from PIL import Image
from rembg import remove, new_session

from utils.logger import get_logger

logger = get_logger(__name__)

# Pre-load rembg session with faster model for better performance
# Using u2netp (smaller, faster) instead of u2net (larger, slower)
try:
    # Set environment variable to use faster model
    os.environ.setdefault('U2NET_HOME', str(Path.home() / '.u2net'))
    _rembg_session = new_session("u2netp")  # Faster model
    logger.info("Initialized rembg with u2netp model (fast)")
except Exception as e:
    logger.warning(f"Could not pre-load rembg session: {e}")
    _rembg_session = None


def _get_rembg_session():
    """Return a ready rembg session, creating it lazily if needed."""
    global _rembg_session

    if _rembg_session is not None:
        return _rembg_session

    os.environ.setdefault('U2NET_HOME', str(Path.home() / '.u2net'))
    _rembg_session = new_session("u2netp")
    logger.info("Initialized rembg with u2netp model (fast)")
    return _rembg_session


def warmup_rembg_session() -> float:
    """Warm up rembg once so first user request is faster.

    Returns:
        Warmup duration in seconds.
    """
    started_at = time.perf_counter()
    session = _get_rembg_session()

    # Tiny synthetic image to trigger model/runtime initialization.
    sample = Image.new('RGB', (64, 64), (255, 255, 255))
    sample_buf = io.BytesIO()
    sample.save(sample_buf, format='PNG')

    remove(
        sample_buf.getvalue(),
        session=session,
        alpha_matting=False,
    )

    elapsed = time.perf_counter() - started_at
    logger.info(f"rembg warmup completed in {elapsed:.2f}s")
    return elapsed


class ImageProcessor:
    """Image processing utilities for 3D generation workflow"""

    @staticmethod
    def remove_background(
        input_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
        alpha_matting: bool = False,  # Disabled by default for speed
        alpha_matting_foreground_threshold: int = 240,
        alpha_matting_background_threshold: int = 10,
        alpha_matting_erode_size: int = 10
    ) -> str:
        """
        Remove background from an image using AI-powered rembg

        Args:
            input_path: Path to input image
            output_path: Path to save output (if None, auto-generates name)
            alpha_matting: Enable alpha matting for better edge quality
            alpha_matting_foreground_threshold: Foreground threshold (0-255)
            alpha_matting_background_threshold: Background threshold (0-255)
            alpha_matting_erode_size: Erosion kernel size

        Returns:
            Path to the output image with removed background

        Example:
            >>> processor = ImageProcessor()
            >>> output = processor.remove_background("input.jpg")
            >>> print(f"Background removed: {output}")
        """
        input_path = Path(input_path)

        if not input_path.exists():
            raise FileNotFoundError(f"Input image not found: {input_path}")

        # Generate output path if not provided
        if output_path is None:
            output_path = input_path.parent / f"{input_path.stem}_nobg{input_path.suffix}"
        else:
            output_path = Path(output_path)

        logger.info(f"Removing background from {input_path}")

        try:
            # Load image
            with open(input_path, 'rb') as input_file:
                input_data = input_file.read()

            # Remove background (use pre-loaded session if available)
            output_data = remove(
                input_data,
                session=_get_rembg_session(),
                alpha_matting=alpha_matting,
                alpha_matting_foreground_threshold=alpha_matting_foreground_threshold,
                alpha_matting_background_threshold=alpha_matting_background_threshold,
                alpha_matting_erode_size=alpha_matting_erode_size
            )

            # Save output
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as output_file:
                output_file.write(output_data)

            logger.info(f"Background removed successfully: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Failed to remove background: {e}")
            raise

    @staticmethod
    def remove_background_pil(
        image: Image.Image,
        alpha_matting: bool = False,  # Disabled by default for speed
        alpha_matting_foreground_threshold: int = 240,
        alpha_matting_background_threshold: int = 10,
        alpha_matting_erode_size: int = 10
    ) -> Image.Image:
        """
        Remove background from PIL Image object

        Args:
            image: PIL Image object
            alpha_matting: Enable alpha matting for better edge quality
            alpha_matting_foreground_threshold: Foreground threshold (0-255)
            alpha_matting_background_threshold: Background threshold (0-255)
            alpha_matting_erode_size: Erosion kernel size

        Returns:
            PIL Image with removed background (RGBA mode)
        """
        logger.info("Removing background from PIL Image")

        try:
            # Convert to bytes
            import io
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()

            # Remove background (use pre-loaded session if available)
            output_data = remove(
                img_byte_arr,
                session=_get_rembg_session(),
                alpha_matting=alpha_matting,
                alpha_matting_foreground_threshold=alpha_matting_foreground_threshold,
                alpha_matting_background_threshold=alpha_matting_background_threshold,
                alpha_matting_erode_size=alpha_matting_erode_size
            )

            # Convert back to PIL Image
            output_image = Image.open(io.BytesIO(output_data))
            logger.info("Background removed successfully")
            return output_image

        except Exception as e:
            logger.error(f"Failed to remove background from PIL Image: {e}")
            raise

    @staticmethod
    def create_white_background(
        input_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None
    ) -> str:
        """
        Remove background and add white background (useful for 3D generation)

        Args:
            input_path: Path to input image
            output_path: Path to save output

        Returns:
            Path to output image
        """
        input_path = Path(input_path)

        if output_path is None:
            output_path = input_path.parent / f"{input_path.stem}_white_bg{input_path.suffix}"
        else:
            output_path = Path(output_path)

        logger.info(f"Creating white background for {input_path}")

        try:
            # Remove background first
            temp_nobg = ImageProcessor.remove_background_pil(
                Image.open(input_path)
            )

            # Create white background
            if temp_nobg.mode != 'RGBA':
                temp_nobg = temp_nobg.convert('RGBA')

            white_bg = Image.new('RGBA', temp_nobg.size, (255, 255, 255, 255))
            white_bg.paste(temp_nobg, (0, 0), temp_nobg)

            # Convert to RGB (remove alpha channel)
            white_bg = white_bg.convert('RGB')

            # Save
            output_path.parent.mkdir(parents=True, exist_ok=True)
            white_bg.save(output_path)

            logger.info(f"White background created: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Failed to create white background: {e}")
            raise

    @staticmethod
    def auto_crop_transparent(
        input_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
        padding: int = 10
    ) -> str:
        """
        Auto-crop transparent areas from an image

        Args:
            input_path: Path to input image (must have transparency)
            output_path: Path to save output
            padding: Padding around the cropped object (pixels)

        Returns:
            Path to cropped image
        """
        input_path = Path(input_path)

        if output_path is None:
            output_path = input_path.parent / f"{input_path.stem}_cropped{input_path.suffix}"
        else:
            output_path = Path(output_path)

        logger.info(f"Auto-cropping {input_path}")

        try:
            image = Image.open(input_path)

            if image.mode != 'RGBA':
                logger.warning("Image has no alpha channel, converting to RGBA")
                image = image.convert('RGBA')

            # Get bounding box of non-transparent area
            bbox = image.getbbox()

            if bbox is None:
                logger.warning("Image is fully transparent, skipping crop")
                return str(input_path)

            # Add padding
            bbox = (
                max(0, bbox[0] - padding),
                max(0, bbox[1] - padding),
                min(image.width, bbox[2] + padding),
                min(image.height, bbox[3] + padding)
            )

            # Crop
            cropped = image.crop(bbox)

            # Save
            output_path.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(output_path)

            logger.info(f"Image cropped: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Failed to crop image: {e}")
            raise
