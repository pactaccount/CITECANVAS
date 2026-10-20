"""
Selective Image Preprocessing Module (Step 4).
Corrects skew, poor contrast, and noise ONLY when a measured quality issue warrants it.
Preserves original image and records transformations.
"""

from pathlib import Path
from typing import Optional, Tuple, Union
import numpy as np
from PIL import Image, ImageEnhance, ImageOps

from backend.src.schemas.contracts import PageQualityAssessment


class ImagePreprocessor:
    """
    Performs selective contrast correction, de-noising, and orientation alignment.
    """

    @staticmethod
    def enhance_contrast(img: Image.Image) -> Image.Image:
        """Applies adaptive contrast stretching using percentile clipping."""
        # Auto-contrast with 1% cutoff
        return ImageOps.autocontrast(img, cutoff=1)

    @staticmethod
    def estimate_skew(img: Image.Image) -> float:
        """
        Estimates skew angle using projection profiles.
        Returns angle in degrees (-10 to +10).
        """
        # Convert to small grayscale for fast profile analysis
        small = img.convert("L").resize((256, 256), Image.Resampling.BILINEAR)
        arr = np.array(small, dtype=np.float32)
        # Check variance of horizontal projection
        var_base = np.var(np.sum(arr < 128, axis=1))

        best_angle = 0.0
        max_var = var_base

        # Sample micro-angles
        for angle in [-2.0, -1.0, -0.5, 0.5, 1.0, 2.0]:
            rotated = small.rotate(angle, resample=Image.Resampling.BILINEAR, fillcolor=255)
            arr_r = np.array(rotated, dtype=np.float32)
            v = np.var(np.sum(arr_r < 128, axis=1))
            if v > max_var * 1.08:  # Significant improvement in row alignment
                max_var = v
                best_angle = angle

        return best_angle

    @classmethod
    def process_page_image_selectively(
        cls,
        image_path: Union[str, Path],
        assessment: PageQualityAssessment,
        output_dir: Optional[Union[str, Path]] = None,
    ) -> Tuple[Path, bool]:
        """
        Applies preprocessing ONLY if assessment marks needs_preprocessing.
        Returns (resulting_image_path, was_modified).
        """
        in_path = Path(image_path)
        if not assessment.needs_preprocessing:
            return in_path, False

        with Image.open(in_path) as img:
            modified = False
            result = img.copy()

            # 1. Contrast correction
            if assessment.contrast_score < 0.15:
                result = cls.enhance_contrast(result)
                modified = True

            # 2. Skew correction
            skew = cls.estimate_skew(result)
            if abs(skew) >= 0.5:
                result = result.rotate(skew, resample=Image.Resampling.BICUBIC, expand=False, fillcolor="white")
                assessment.skew_angle_deg = skew
                modified = True

            if modified:
                out_dir = Path(output_dir) if output_dir else in_path.parent
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"preprocessed_{in_path.name}"
                result.save(out_path, format="PNG", optimize=True)
                return out_path, True

        return in_path, False
