#!/usr/bin/env python3
"""
Image Enhancement Pipeline for Claude Code
Auto-detects page regions, splits, upscales, and runs high-accuracy OCR.
Handles composite design mockups with multiple pages in a single image.
"""

import sys
import os
import subprocess
import json
from pathlib import Path

try:
    import Vision
    from Foundation import NSURL
    HAS_VISION = True
except ImportError:
    HAS_VISION = False


def get_image_size(path):
    result = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", path],
        capture_output=True, text=True
    )
    width = height = 0
    for line in result.stdout.splitlines():
        if "pixelWidth" in line:
            width = int(line.split(":")[-1].strip())
        if "pixelHeight" in line:
            height = int(line.split(":")[-1].strip())
    return width, height


def detect_grid_layout(width, height):
    """Detect if image contains multiple pages in a grid layout."""
    ratio = width / height
    if ratio > 1.8:
        return (2, 1)  # 2 columns, 1 row
    elif ratio > 1.2:
        return (2, 2)  # 2x2 grid
    elif ratio < 0.6:
        return (1, 2)  # 1 column, 2 rows
    else:
        return (1, 1)  # single page


def split_image(path, output_dir, cols, rows):
    """Split image into grid cells using ImageMagick."""
    regions = []
    width, height = get_image_size(path)
    cell_w = width // cols
    cell_h = height // rows

    for r in range(rows):
        for c in range(cols):
            x = c * cell_w
            y = r * cell_h
            out_path = os.path.join(output_dir, f"region_{r}_{c}.png")
            subprocess.run([
                "magick", path,
                "-crop", f"{cell_w}x{cell_h}+{x}+{y}",
                "+repage", out_path
            ], capture_output=True)
            if os.path.exists(out_path):
                regions.append(out_path)
    return regions


def enhance_image(path, output_path, scale=3):
    """Upscale and sharpen for better OCR."""
    subprocess.run([
        "magick", path,
        "-resize", f"{scale * 100}%",
        "-sharpen", "0x2",
        "-contrast-stretch", "1%x1%",
        output_path
    ], capture_output=True)
    return output_path


def ocr_with_vision(path):
    """Run macOS Vision OCR with Chinese + English support."""
    if not HAS_VISION:
        return []

    url = NSURL.fileURLWithPath_(path)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLanguages_(["zh-Hans", "zh-Hant", "en"])
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)

    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    success, error = handler.performRequests_error_([request], None)

    if not success:
        return []

    results = []
    for obs in request.results():
        candidate = obs.topCandidates_(1)[0]
        text = candidate.string()
        conf = candidate.confidence()
        bbox = obs.boundingBox()
        results.append({
            "text": text,
            "confidence": round(conf, 3),
            "y": round(1 - bbox.origin.y - bbox.size.height, 3),
            "x": round(bbox.origin.x, 3),
        })

    results.sort(key=lambda r: (r["y"], r["x"]))
    return results


def ocr_with_tesseract(path):
    """Fallback OCR with Tesseract."""
    result = subprocess.run(
        ["tesseract", path, "stdout", "-l", "chi_sim+eng", "--psm", "6"],
        capture_output=True, text=True
    )
    return result.stdout


def merge_ocr_results(vision_results):
    """Group OCR results into logical lines by Y proximity."""
    if not vision_results:
        return ""

    lines = []
    current_line = []
    current_y = vision_results[0]["y"]

    for r in vision_results:
        if abs(r["y"] - current_y) < 0.015:
            current_line.append(r)
        else:
            current_line.sort(key=lambda x: x["x"])
            line_text = " ".join(item["text"] for item in current_line)
            avg_conf = sum(item["confidence"] for item in current_line) / len(current_line)
            lines.append({"text": line_text, "confidence": avg_conf})
            current_line = [r]
            current_y = r["y"]

    if current_line:
        current_line.sort(key=lambda x: x["x"])
        line_text = " ".join(item["text"] for item in current_line)
        avg_conf = sum(item["confidence"] for item in current_line) / len(current_line)
        lines.append({"text": line_text, "confidence": avg_conf})

    return lines


def process_image(image_path):
    """Full pipeline: detect layout → split → enhance → OCR → merge."""
    output_dir = "/tmp/image_enhance_pipeline"
    os.makedirs(output_dir, exist_ok=True)

    width, height = get_image_size(image_path)
    print(f"Image: {width}x{height}")

    cols, rows = detect_grid_layout(width, height)
    print(f"Detected layout: {cols}x{rows} grid")

    if cols == 1 and rows == 1:
        regions = [image_path]
    else:
        regions = split_image(image_path, output_dir, cols, rows)
        print(f"Split into {len(regions)} regions")

    all_results = []
    for i, region_path in enumerate(regions):
        enhanced_path = os.path.join(output_dir, f"enhanced_{i}.png")
        enhance_image(region_path, enhanced_path, scale=3)

        ocr_results = ocr_with_vision(enhanced_path)
        lines = merge_ocr_results(ocr_results)

        high_conf = [l for l in lines if l["confidence"] > 0.7]
        med_conf = [l for l in lines if 0.4 <= l["confidence"] <= 0.7]
        low_conf = [l for l in lines if l["confidence"] < 0.4]

        region_data = {
            "region": i + 1,
            "total_lines": len(lines),
            "high_confidence": len(high_conf),
            "medium_confidence": len(med_conf),
            "low_confidence": len(low_conf),
            "content": lines
        }
        all_results.append(region_data)

        print(f"\n--- Region {i+1} ---")
        print(f"Lines: {len(lines)} (high:{len(high_conf)} med:{len(med_conf)} low:{len(low_conf)})")
        print("Content:")
        for line in lines:
            marker = "✓" if line["confidence"] > 0.7 else "~" if line["confidence"] >= 0.4 else "?"
            print(f"  {marker} {line['text']}")

    output_json = os.path.join(output_dir, "results.json")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nFull results saved to: {output_json}")

    # Cleanup region files (keep enhanced for reference)
    for region_path in regions:
        if region_path != image_path and os.path.exists(region_path):
            os.remove(region_path)

    return all_results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 enhance_ocr.py <image_path>")
        sys.exit(1)
    process_image(sys.argv[1])
