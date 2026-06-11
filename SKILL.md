---
name: image-enhance
description: Preprocess images before AI analysis — auto-splits composite images, upscales, runs OCR with domain-aware correction, and assembles structured context. Compensates for vision model weaknesses on small text, dense UIs, and multi-page mockups.
---

# Image Enhancement & Preprocessing Skill

When the user sends an image and needs accurate understanding (especially text extraction, UI element identification, or detail recognition), run the preprocessing pipeline BEFORE attempting interpretation.

## Quick start (full pipeline)

```bash
# Step 1: Run enhancement + OCR pipeline
python3 ~/.claude/skills/image-enhance/scripts/enhance_ocr.py "$IMAGE_PATH"

# Step 2: Apply domain-aware correction
python3 ~/.claude/skills/image-enhance/scripts/context_correct.py /tmp/image_enhance_pipeline/results.json
```

The pipeline auto-detects grid layouts (2x2, 2x1, 1x2), splits into regions, upscales 3x with sharpening, runs macOS Vision OCR, and outputs structured JSON. The correction script fixes common CJK misrecognitions using domain vocabulary.

## Adding domain vocabulary

Edit `~/.claude/skills/image-enhance/scripts/context_correct.py` CORRECTIONS dict to add project-specific terms. Format: `"OCR_error": "correct_text"`

## When to trigger

- User sends an image with small or dense text
- User sends a complex UI screenshot for analysis
- User sends a low-resolution or compressed image
- User sends handwritten content
- User explicitly asks for OCR or image enhancement
- Previous image interpretation was inaccurate and user corrects you

## Pipeline steps

### 1. Assess image quality

```bash
# Get image metadata
sips -g all "$IMAGE_PATH"
# Or with ImageMagick if available
identify -verbose "$IMAGE_PATH"
```

Determine: resolution, format, compression level, whether text is present.

### 2. Enhance if needed

```bash
# Upscale low-res images (macOS sips)
sips --resampleWidth 2400 "$IMAGE_PATH" --out "$OUTPUT_PATH"

# Or with ImageMagick for more control
convert "$IMAGE_PATH" -resize 200% -sharpen 0x1.5 -contrast "$OUTPUT_PATH"

# For text-heavy images: increase contrast and convert to grayscale
convert "$IMAGE_PATH" -colorspace Gray -contrast-stretch 2%x2% -sharpen 0x2 "$OUTPUT_PATH"
```

### 3. Smart cropping for large images

```bash
# Split into quadrants for separate analysis
convert "$IMAGE_PATH" -crop 2x2@ +rw +adjoin "$OUTPUT_DIR/region_%d.png"

# Or crop a specific region (x, y, width, height)
convert "$IMAGE_PATH" -crop WxH+X+Y "$OUTPUT_PATH"

# macOS native crop
sips --cropToHeightWidth H W "$IMAGE_PATH" --out "$OUTPUT_PATH"
```

### 4. OCR text extraction

```bash
# macOS native Vision framework (best for CJK + English mixed text)
shortcuts run "Extract Text from Image" -i "$IMAGE_PATH"

# Or use a Python script with macOS Vision
python3 - <<'EOF'
import sys
import Quartz
from Foundation import NSURL
import Vision

def ocr_image(path):
    url = NSURL.fileURLWithPath_(path)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLanguages_(["zh-Hans", "zh-Hant", "en"])
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    handler.performRequests_error_([request], None)
    
    results = []
    for obs in request.results():
        text = obs.topCandidates_(1)[0].string()
        conf = obs.topCandidates_(1)[0].confidence()
        bbox = obs.boundingBox()
        results.append(f"[{conf:.2f}] ({bbox.origin.x:.2f},{bbox.origin.y:.2f}) {text}")
    return "\n".join(results)

if __name__ == "__main__":
    print(ocr_image(sys.argv[1]))
EOF
```

```bash
# Alternative: Tesseract (if installed)
# Good for pure English, weaker on CJK
tesseract "$IMAGE_PATH" stdout -l chi_sim+eng --psm 6
```

### 5. Assemble structured context

After preprocessing, combine results into a structured prompt:

```
## Image Analysis Context

**Resolution:** {width}x{height}
**OCR Extracted Text:**
{ocr_output}

**Regions of interest:**
- Top-left: {description}
- Center: {description}
...

**Now analyzing the enhanced image with this context.**
```

## Decision matrix

| Scenario | Action |
|----------|--------|
| Text < 12px in image | Upscale 2-3x → OCR → combine |
| Dense UI (>20 elements) | Split into regions → analyze each |
| Handwritten | Enhance contrast → OCR with accurate mode |
| Code screenshot | OCR only, skip image analysis |
| Low-res (<800px wide) | Upscale → sharpen → then analyze |
| Mixed text+diagram | OCR for text + separate visual analysis |

## Dependencies check

Run on first use:

```bash
# Check available tools
which convert && echo "ImageMagick: OK" || echo "ImageMagick: missing (brew install imagemagick)"
which tesseract && echo "Tesseract: OK" || echo "Tesseract: missing (brew install tesseract tesseract-lang)"
python3 -c "import Vision" 2>/dev/null && echo "PyObjC Vision: OK" || echo "PyObjC: missing (pip3 install pyobjc-framework-Vision)"
sips --help >/dev/null 2>&1 && echo "sips: OK (macOS native)"
```

## Usage patterns

**User sends a screenshot with small text:**
1. Save/locate the image
2. Run OCR → extract all text with positions
3. Upscale the image 2x
4. Read the enhanced version + OCR text together
5. Provide accurate interpretation

**User sends a complex UI for analysis:**
1. Get dimensions
2. If >1500px in either dimension, split into regions
3. OCR each region
4. Analyze regions individually
5. Synthesize a complete description

**User sends handwritten notes:**
1. Convert to grayscale, boost contrast
2. Run OCR in accurate mode
3. Present OCR results with confidence scores
4. Flag low-confidence segments for user verification

## Important notes

- Always tell the user what preprocessing you're doing
- If OCR confidence is below 0.7, flag that segment as uncertain
- For CJK text, prefer macOS Vision over Tesseract
- Keep enhanced/temporary files in /tmp and clean up after
- If no preprocessing tools are available, tell the user what to install
