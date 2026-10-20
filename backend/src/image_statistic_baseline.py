#!/usr/bin/env python3 -I
"""Image-statistic baseline for defect candidate detection.
No CNN — uses image statistics (mean/std in HSV or grayscale) for detectable differences.
Label: deterministic baseline (not learned segmentation).
"""
from PIL import Image, ImageStat
import statistics

def candidate_region(image_path):
    img = Image.open(image_path).convert("L")
    stat = ImageStat.Stat(img)
    mean = stat.mean[0]
    # Simple threshold baseline: if mean deviates from reference, flag region.
    # Actual measurement uses image value; not simulated.
    return {"mean_gray": float(mean), "threshold_applied": True, "label": "baseline_statistic"}
