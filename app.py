#!/usr/bin/env python3
"""
Web application for converting images to SVG.
Features: batch conversion, live preview, preset profiles.
"""

import os
import uuid
import base64
import re
from io import StringIO
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_file, render_template_string
from werkzeug.utils import secure_filename
import requests
import vtracer
import scour.scour

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['OUTPUT_FOLDER'] = Path(__file__).parent / 'outputs'

# Create folders if they don't exist
app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)
app.config['OUTPUT_FOLDER'].mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'gif', 'webp', 'tiff'}

# Preset profiles for different image types
PRESETS = {
    'default': {
        'colormode': 'color',
        'hierarchical': 'stacked',
        'mode': 'spline',
        'filter_speckle': 4,
        'color_precision': 6,
        'layer_difference': 16,
        'corner_threshold': 60,
        'length_threshold': 4.0,
        'max_iterations': 10,
        'splice_threshold': 45,
        'path_precision': 3,
    },
    'logo': {
        'colormode': 'color',
        'hierarchical': 'stacked',
        'mode': 'spline',
        'filter_speckle': 8,
        'color_precision': 4,
        'layer_difference': 24,
        'corner_threshold': 60,
        'length_threshold': 4.0,
        'max_iterations': 10,
        'splice_threshold': 45,
        'path_precision': 2,
    },
    'photo': {
        'colormode': 'color',
        'hierarchical': 'stacked',
        'mode': 'spline',
        'filter_speckle': 2,
        'color_precision': 8,
        'layer_difference': 8,
        'corner_threshold': 60,
        'length_threshold': 2.0,
        'max_iterations': 10,
        'splice_threshold': 45,
        'path_precision': 4,
    },
    'lineart': {
        'colormode': 'binary',
        'hierarchical': 'stacked',
        'mode': 'spline',
        'filter_speckle': 4,
        'color_precision': 6,
        'layer_difference': 16,
        'corner_threshold': 60,
        'length_threshold': 4.0,
        'max_iterations': 10,
        'splice_threshold': 45,
        'path_precision': 3,
    },
    'sketch': {
        'colormode': 'binary',
        'hierarchical': 'stacked',
        'mode': 'spline',
        'filter_speckle': 2,
        'color_precision': 6,
        'layer_difference': 16,
        'corner_threshold': 45,
        'length_threshold': 2.0,
        'max_iterations': 15,
        'splice_threshold': 45,
        'path_precision': 3,
    },
    'minimal': {
        'colormode': 'color',
        'hierarchical': 'stacked',
        'mode': 'polygon',
        'filter_speckle': 16,
        'color_precision': 3,
        'layer_difference': 32,
        'corner_threshold': 60,
        'length_threshold': 6.0,
        'max_iterations': 10,
        'splice_threshold': 45,
        'path_precision': 2,
    },
}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def convert_image(input_path, output_path, settings):
    """Convert an image to SVG with given settings."""
    vtracer.convert_image_to_svg_py(
        str(input_path),
        str(output_path),
        colormode=settings.get('colormode', 'color'),
        hierarchical=settings.get('hierarchical', 'stacked'),
        mode=settings.get('mode', 'spline'),
        filter_speckle=int(settings.get('filter_speckle', 4)),
        color_precision=int(settings.get('color_precision', 6)),
        layer_difference=int(settings.get('layer_difference', 16)),
        corner_threshold=int(settings.get('corner_threshold', 60)),
        length_threshold=float(settings.get('length_threshold', 4.0)),
        max_iterations=int(settings.get('max_iterations', 10)),
        splice_threshold=int(settings.get('splice_threshold', 45)),
        path_precision=int(settings.get('path_precision', 3)),
    )
    return output_path


def add_viewbox(svg_content):
    """Add viewBox to SVG if missing, to enable proper scaling."""
    if 'viewBox' in svg_content:
        return svg_content

    # Extract width and height
    width_match = re.search(r'width="(\d+)"', svg_content)
    height_match = re.search(r'height="(\d+)"', svg_content)

    if width_match and height_match:
        width = width_match.group(1)
        height = height_match.group(1)
        # Add viewBox after the opening svg tag
        svg_content = re.sub(
            r'(<svg[^>]*)(>)',
            rf'\1 viewBox="0 0 {width} {height}"\2',
            svg_content,
            count=1
        )
    return svg_content


def optimize_svg(svg_content):
    """Optimize SVG content using scour."""
    try:
        # Ensure we have a string
        if isinstance(svg_content, bytes):
            svg_content = svg_content.decode('utf-8')

        options = scour.scour.parse_args([
            '--enable-viewboxing',
            '--enable-id-stripping',
            '--enable-comment-stripping',
            '--shorten-ids',
            '--indent=none',
        ])
        options.infilename = None
        options.outfilename = None

        input_stream = StringIO(svg_content)
        output_stream = StringIO()

        scour.scour.start(options, input_stream, output_stream)
        return output_stream.getvalue()
    except Exception as e:
        # If optimization fails, return original content
        print(f"SVG optimization failed: {e}")
        return svg_content


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/presets')
def get_presets():
    return jsonify(PRESETS)


@app.route('/api/convert', methods=['POST'])
def convert():
    """Convert uploaded image(s) to SVG."""
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400

    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'No files selected'}), 400

    # Get settings from form data
    preset = request.form.get('preset', 'default')
    settings = PRESETS.get(preset, PRESETS['default']).copy()

    # Override with custom settings if provided
    for key in settings.keys():
        if key in request.form:
            settings[key] = request.form[key]

    # Check if optimization is requested
    should_optimize = request.form.get('optimize', 'false').lower() == 'true'

    results = []
    for file in files:
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_id = str(uuid.uuid4())[:8]
            input_filename = f"{unique_id}_{filename}"
            input_path = app.config['UPLOAD_FOLDER'] / input_filename

            output_filename = f"{unique_id}_{Path(filename).stem}.svg"
            output_path = app.config['OUTPUT_FOLDER'] / output_filename

            try:
                file.save(input_path)

                # Read original image as base64 for comparison
                with open(input_path, 'rb') as f:
                    original_data = base64.b64encode(f.read()).decode('utf-8')

                # Determine mime type
                ext = Path(filename).suffix.lower()
                mime_types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                              '.gif': 'image/gif', '.bmp': 'image/bmp', '.webp': 'image/webp'}
                mime_type = mime_types.get(ext, 'image/png')
                original_base64 = f"data:{mime_type};base64,{original_data}"

                convert_image(input_path, output_path, settings)

                # Read SVG content for preview
                with open(output_path, 'r', encoding='utf-8') as f:
                    svg_content = f.read()

                # Add viewBox for proper scaling
                svg_content = add_viewbox(svg_content)

                # Optimize SVG if requested
                if should_optimize:
                    svg_content = optimize_svg(svg_content)

                # Save updated SVG
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(svg_content)

                # Get file sizes
                input_size = os.path.getsize(input_path)
                output_size = os.path.getsize(output_path)

                results.append({
                    'original_name': filename,
                    'svg_filename': output_filename,
                    'svg_content': svg_content,
                    'original_image': original_base64,
                    'input_size': input_size,
                    'output_size': output_size,
                    'success': True,
                })

                # Clean up input file
                os.remove(input_path)

            except Exception as e:
                results.append({
                    'original_name': filename,
                    'error': str(e),
                    'success': False,
                })
                if input_path.exists():
                    os.remove(input_path)

    return jsonify({'results': results})


@app.route('/api/download/<filename>')
def download(filename):
    """Download a converted SVG file."""
    filename = secure_filename(filename)
    file_path = app.config['OUTPUT_FOLDER'] / filename
    if file_path.exists():
        return send_file(file_path, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404


@app.route('/api/preview', methods=['POST'])
def preview():
    """Generate a preview of the conversion with current settings."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file'}), 400

    # Get settings
    preset = request.form.get('preset', 'default')
    settings = PRESETS.get(preset, PRESETS['default']).copy()

    for key in settings.keys():
        if key in request.form:
            settings[key] = request.form[key]

    filename = secure_filename(file.filename)
    unique_id = str(uuid.uuid4())[:8]
    input_path = app.config['UPLOAD_FOLDER'] / f"{unique_id}_{filename}"
    output_path = app.config['OUTPUT_FOLDER'] / f"{unique_id}_preview.svg"

    try:
        file.save(input_path)
        convert_image(input_path, output_path, settings)

        with open(output_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()

        # Clean up
        os.remove(input_path)
        os.remove(output_path)

        return jsonify({'svg': svg_content, 'success': True})

    except Exception as e:
        if input_path.exists():
            os.remove(input_path)
        if output_path.exists():
            os.remove(output_path)
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/convert-url', methods=['POST'])
def convert_url():
    """Convert an image from a URL or data URI to SVG."""
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'No URL provided'}), 400

    url = data['url'].strip()

    # Get settings
    preset = data.get('preset', 'default')
    settings = PRESETS.get(preset, PRESETS['default']).copy()

    for key in settings.keys():
        if key in data:
            settings[key] = data[key]

    # Check if optimization is requested
    should_optimize = str(data.get('optimize', 'false')).lower() == 'true'

    unique_id = str(uuid.uuid4())[:8]

    # Check if it's a data URI
    if url.startswith('data:'):
        # Parse data URI: data:[<mediatype>][;base64],<data>
        try:
            header, encoded_data = url.split(',', 1)
            # Extract mime type
            mime_match = re.match(r'data:([^;]+)', header)
            mime_type = mime_match.group(1) if mime_match else 'image/png'

            if not mime_type.startswith('image/'):
                return jsonify({'error': f'Data URI is not an image (got {mime_type})'}), 400

            # Determine extension from mime type
            ext_map = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/gif': '.gif',
                       'image/bmp': '.bmp', 'image/webp': '.webp'}
            ext = ext_map.get(mime_type, '.png')
            filename = f"image{ext}"

            # Decode base64
            if ';base64' in header:
                image_data = base64.b64decode(encoded_data)
            else:
                image_data = encoded_data.encode('utf-8')

        except Exception as e:
            return jsonify({'error': f'Invalid data URI: {str(e)}'}), 400

        input_path = app.config['UPLOAD_FOLDER'] / f"{unique_id}_{filename}"
        output_filename = f"{unique_id}_image.svg"
        output_path = app.config['OUTPUT_FOLDER'] / output_filename
        original_image = url  # Keep original data URI for comparison

        # Save the decoded image
        with open(input_path, 'wb') as f:
            f.write(image_data)

    else:
        # Regular URL - validate and download
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return jsonify({'error': 'Invalid URL format'}), 400
        except Exception:
            return jsonify({'error': 'Invalid URL'}), 400

        # Extract filename from URL
        url_path = parsed.path
        filename = os.path.basename(url_path) or 'image'
        if '.' not in filename:
            filename += '.jpg'
        filename = re.sub(r'[^\w\-_\.]', '_', filename)

        input_path = app.config['UPLOAD_FOLDER'] / f"{unique_id}_{filename}"
        output_filename = f"{unique_id}_{Path(filename).stem}.svg"
        output_path = app.config['OUTPUT_FOLDER'] / output_filename
        original_image = url

        try:
            # Download the image
            response = requests.get(url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()

            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                return jsonify({'error': f'URL does not point to an image (got {content_type})'}), 400

            with open(input_path, 'wb') as f:
                f.write(response.content)

        except requests.exceptions.Timeout:
            return jsonify({'error': 'Request timed out'}), 504
        except requests.exceptions.RequestException as e:
            return jsonify({'error': f'Failed to download image: {str(e)}'}), 400

    try:
        # Convert to SVG
        convert_image(input_path, output_path, settings)

        # Read SVG content
        with open(output_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()

        # Add viewBox for proper scaling
        svg_content = add_viewbox(svg_content)

        # Optimize SVG if requested
        if should_optimize:
            svg_content = optimize_svg(svg_content)

        # Save updated SVG
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)

        input_size = os.path.getsize(input_path)
        output_size = os.path.getsize(output_path)

        # Clean up input file
        os.remove(input_path)

        return jsonify({
            'success': True,
            'original_name': filename,
            'svg_filename': output_filename,
            'svg_content': svg_content,
            'original_image': original_image,
            'input_size': input_size,
            'output_size': output_size,
        })

    except Exception as e:
        if input_path.exists():
            os.remove(input_path)
        if output_path.exists():
            os.remove(output_path)
        return jsonify({'error': str(e), 'success': False}), 500


HTML_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Image to SVG Converter</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            text-align: center;
            padding: 40px 0;
        }

        .header-content {
            display: flex;
            justify-content: center;
            align-items: center;
            position: relative;
        }

        .theme-toggle {
            position: absolute;
            right: 0;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 50%;
            width: 44px;
            height: 44px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
        }

        .theme-toggle:hover {
            background: rgba(255, 255, 255, 0.2);
            transform: scale(1.1);
        }

        .theme-icon {
            font-size: 1.3rem;
        }

        h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .subtitle {
            color: #888;
            font-size: 1.1rem;
        }

        /* Light theme */
        body.light-theme {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            color: #333;
        }

        body.light-theme .theme-toggle {
            background: rgba(0, 0, 0, 0.1);
            border-color: rgba(0, 0, 0, 0.2);
        }

        body.light-theme .upload-section,
        body.light-theme .settings-panel,
        body.light-theme .result-card {
            background: rgba(255, 255, 255, 0.8);
            border-color: rgba(0, 0, 0, 0.1);
        }

        body.light-theme .drop-zone {
            border-color: rgba(0, 0, 0, 0.2);
            background: rgba(0, 0, 0, 0.02);
        }

        body.light-theme .drop-zone:hover {
            border-color: #3a7bd5;
            background: rgba(58, 123, 213, 0.05);
        }

        body.light-theme .drop-zone-hint,
        body.light-theme .subtitle {
            color: #666;
        }

        body.light-theme .setting-input,
        body.light-theme .url-input {
            background: rgba(0, 0, 0, 0.05);
            border-color: rgba(0, 0, 0, 0.2);
            color: #333;
        }

        body.light-theme select.setting-input {
            background: #fff;
        }

        body.light-theme select.setting-input option {
            background: #fff;
            color: #333;
        }

        body.light-theme .preset-btn {
            background: rgba(0, 0, 0, 0.05);
            border-color: rgba(0, 0, 0, 0.2);
            color: #333;
        }

        body.light-theme .preset-btn:hover {
            background: rgba(58, 123, 213, 0.1);
        }

        body.light-theme .result-btn {
            background: rgba(0, 0, 0, 0.05);
            border-color: rgba(0, 0, 0, 0.2);
            color: #333;
        }

        body.light-theme .result-btn:hover {
            background: rgba(58, 123, 213, 0.1);
        }

        body.light-theme .divider::before,
        body.light-theme .divider::after {
            border-color: rgba(0, 0, 0, 0.1);
        }

        body.light-theme .file-item {
            background: rgba(0, 0, 0, 0.05);
        }

        body.light-theme .checkbox-label {
            color: #333;
        }

        body.light-theme .setting-label {
            color: #555;
        }

        .main-content {
            display: grid;
            grid-template-columns: 1fr 300px;
            gap: 20px;
        }

        @media (max-width: 900px) {
            .main-content {
                grid-template-columns: 1fr;
            }

            .settings-panel {
                order: -1;
            }
        }

        @media (max-width: 600px) {
            .container {
                padding: 10px;
            }

            header {
                padding: 20px 0;
            }

            h1 {
                font-size: 1.8rem;
            }

            .subtitle {
                font-size: 0.95rem;
            }

            .upload-section {
                padding: 15px;
            }

            .drop-zone {
                padding: 30px 15px;
            }

            .drop-zone-icon {
                font-size: 36px;
            }

            .drop-zone-text {
                font-size: 1rem;
            }

            .url-input-group {
                flex-direction: column;
            }

            .url-convert-btn {
                width: 100%;
            }

            .preset-buttons {
                grid-template-columns: repeat(3, 1fr);
            }

            .result-actions {
                flex-direction: column;
            }

            .result-btn {
                width: 100%;
            }

            .comparison-container {
                height: 200px;
            }

            .results-grid {
                grid-template-columns: 1fr;
            }

            .theme-toggle {
                width: 38px;
                height: 38px;
            }
        }

        .upload-section {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 30px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .drop-zone {
            border: 2px dashed rgba(255, 255, 255, 0.3);
            border-radius: 12px;
            padding: 60px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            background: rgba(255, 255, 255, 0.02);
        }

        .drop-zone:hover, .drop-zone.drag-over {
            border-color: #3a7bd5;
            background: rgba(58, 123, 213, 0.1);
        }

        .drop-zone-icon {
            font-size: 48px;
            margin-bottom: 20px;
        }

        .drop-zone-text {
            font-size: 1.2rem;
            margin-bottom: 10px;
        }

        .drop-zone-hint {
            color: #666;
            font-size: 0.9rem;
        }

        .file-input {
            display: none;
        }

        .url-section {
            margin-top: 20px;
        }

        .divider {
            display: flex;
            align-items: center;
            text-align: center;
            margin: 15px 0;
            color: #666;
        }

        .divider::before,
        .divider::after {
            content: '';
            flex: 1;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .divider span {
            padding: 0 15px;
            font-size: 0.85rem;
        }

        .url-input-group {
            display: flex;
            gap: 10px;
        }

        .url-input {
            flex: 1;
            padding: 12px 15px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            background: rgba(255, 255, 255, 0.05);
            color: #fff;
            border-radius: 8px;
            font-size: 0.9rem;
        }

        .url-input:focus {
            outline: none;
            border-color: #3a7bd5;
        }

        .url-input::placeholder {
            color: #666;
        }

        .url-convert-btn {
            padding: 12px 20px;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            border: none;
            border-radius: 8px;
            color: #fff;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            white-space: nowrap;
        }

        .url-convert-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(58, 123, 213, 0.3);
        }

        .url-convert-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }

        .checkbox-group {
            margin-top: 15px;
        }

        .checkbox-label {
            display: flex;
            align-items: center;
            cursor: pointer;
            font-size: 0.9rem;
            color: #ccc;
            gap: 10px;
        }

        .checkbox-label input[type="checkbox"] {
            width: 18px;
            height: 18px;
            accent-color: #3a7bd5;
            cursor: pointer;
        }

        .settings-panel {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .settings-title {
            font-size: 1.2rem;
            margin-bottom: 20px;
            color: #3a7bd5;
        }

        .preset-buttons {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin-bottom: 20px;
        }

        .preset-btn {
            padding: 12px 16px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            background: rgba(255, 255, 255, 0.05);
            color: #fff;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            font-size: 0.85rem;
        }

        .preset-btn:hover {
            background: rgba(58, 123, 213, 0.2);
            border-color: #3a7bd5;
        }

        .preset-btn.active {
            background: #3a7bd5;
            border-color: #3a7bd5;
        }

        .setting-group {
            margin-bottom: 15px;
        }

        .setting-label {
            display: block;
            font-size: 0.85rem;
            color: #aaa;
            margin-bottom: 5px;
        }

        .setting-input {
            width: 100%;
            padding: 10px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            background: rgba(255, 255, 255, 0.05);
            color: #fff;
            border-radius: 6px;
            font-size: 0.9rem;
        }

        .setting-input:focus {
            outline: none;
            border-color: #3a7bd5;
        }

        select.setting-input {
            cursor: pointer;
            background: #1a1a2e;
            appearance: none;
            -webkit-appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%23888' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6h10l-5 5z'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 10px center;
            padding-right: 30px;
        }

        select.setting-input option {
            background: #1a1a2e;
            color: #fff;
            padding: 10px;
        }

        select.setting-input option:hover,
        select.setting-input option:checked {
            background: #3a7bd5;
        }

        .convert-btn {
            width: 100%;
            padding: 15px;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            border: none;
            border-radius: 8px;
            color: #fff;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            margin-top: 20px;
        }

        .convert-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(58, 123, 213, 0.3);
        }

        .convert-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }

        .results-section {
            margin-top: 30px;
        }

        .results-title {
            font-size: 1.3rem;
            margin-bottom: 20px;
            color: #3a7bd5;
        }

        .results-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
        }

        .result-card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .result-preview {
            background: #fff;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 200px;
            max-height: 300px;
            overflow: hidden;
        }

        .result-preview svg {
            max-width: 100%;
            max-height: 260px;
            height: auto;
        }

        .comparison-container {
            position: relative;
            width: 100%;
            height: 250px;
            overflow: hidden;
            background: #fff;
        }

        .comparison-svg {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 10px;
            box-sizing: border-box;
            z-index: 1;
            background: #fff;
        }

        .comparison-original {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 10px;
            box-sizing: border-box;
            z-index: 2;
            clip-path: inset(0 50% 0 0);
        }

        .comparison-original img,
        .comparison-svg svg {
            max-width: 100%;
            max-height: 230px;
            object-fit: contain;
        }

        .comparison-svg svg {
            width: auto !important;
            height: auto !important;
            max-width: 100%;
            max-height: 230px;
        }

        .comparison-slider {
            position: absolute;
            top: 0;
            bottom: 0;
            width: 4px;
            background: #3a7bd5;
            left: 50%;
            transform: translateX(-50%);
            cursor: ew-resize;
            z-index: 10;
        }

        .comparison-slider::before {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 40px;
            height: 40px;
            background: #3a7bd5;
            border-radius: 50%;
            border: 3px solid #fff;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        }

        .comparison-slider::after {
            content: '◀ ▶';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: #fff;
            font-size: 10px;
            letter-spacing: -2px;
            white-space: nowrap;
        }

        .comparison-labels {
            position: absolute;
            bottom: 8px;
            left: 0;
            right: 0;
            display: flex;
            justify-content: space-between;
            padding: 0 10px;
            font-size: 11px;
            font-weight: 600;
            pointer-events: none;
            z-index: 5;
        }

        .comparison-labels span {
            background: rgba(0,0,0,0.6);
            color: #fff;
            padding: 3px 8px;
            border-radius: 4px;
        }

        .result-info {
            padding: 15px;
        }

        .result-filename {
            font-weight: 600;
            margin-bottom: 8px;
            word-break: break-all;
        }

        .result-stats {
            font-size: 0.85rem;
            color: #888;
            margin-bottom: 12px;
        }

        .result-actions {
            display: flex;
            gap: 10px;
        }

        .result-btn {
            flex: 1;
            padding: 10px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            background: rgba(255, 255, 255, 0.05);
            color: #fff;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s ease;
            font-size: 0.85rem;
        }

        .result-btn:hover {
            background: rgba(58, 123, 213, 0.2);
            border-color: #3a7bd5;
        }

        .result-btn.primary {
            background: #3a7bd5;
            border-color: #3a7bd5;
        }

        .file-list {
            margin-top: 20px;
        }

        .file-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            margin-bottom: 8px;
        }

        .file-item-name {
            font-size: 0.9rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            flex: 1;
            margin-right: 10px;
        }

        .file-item-remove {
            background: rgba(255, 100, 100, 0.2);
            border: none;
            color: #ff6464;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            cursor: pointer;
            font-size: 1.2rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .loading {
            display: none;
            text-align: center;
            padding: 40px;
        }

        .loading.active {
            display: block;
        }

        .spinner {
            width: 50px;
            height: 50px;
            border: 3px solid rgba(255, 255, 255, 0.1);
            border-top-color: #3a7bd5;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .error-message {
            background: rgba(255, 100, 100, 0.2);
            border: 1px solid rgba(255, 100, 100, 0.3);
            color: #ff6464;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
        }

        .advanced-toggle {
            color: #3a7bd5;
            cursor: pointer;
            font-size: 0.9rem;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .advanced-settings {
            display: none;
        }

        .advanced-settings.show {
            display: block;
        }

        .download-all-btn {
            display: none;
            margin-bottom: 20px;
        }

        .download-all-btn.show {
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-content">
                <div>
                    <h1>Image to SVG Converter</h1>
                    <p class="subtitle">Convert raster images to scalable vector graphics</p>
                </div>
                <button class="theme-toggle" id="themeToggle" title="Toggle theme">
                    <span class="theme-icon">🌙</span>
                </button>
            </div>
        </header>

        <div class="main-content">
            <div class="upload-section">
                <div class="drop-zone" id="dropZone">
                    <div class="drop-zone-icon">🖼️</div>
                    <div class="drop-zone-text">Drop images here or click to upload</div>
                    <div class="drop-zone-hint">Supports PNG, JPG, BMP, GIF, WebP, TIFF</div>
                </div>
                <input type="file" id="fileInput" class="file-input" multiple accept=".png,.jpg,.jpeg,.bmp,.gif,.webp,.tiff">

                <div class="url-section">
                    <div class="divider"><span>OR</span></div>
                    <div class="url-input-group">
                        <input type="text" id="urlInput" class="url-input" placeholder="Paste image URL here...">
                        <button id="urlConvertBtn" class="url-convert-btn">Convert URL</button>
                    </div>
                </div>

                <div class="file-list" id="fileList"></div>

                <div class="loading" id="loading">
                    <div class="spinner"></div>
                    <p>Converting images...</p>
                </div>

                <div class="results-section" id="resultsSection" style="display: none;">
                    <button class="convert-btn download-all-btn" id="downloadAllBtn">Download All SVGs</button>
                    <h2 class="results-title">Results</h2>
                    <div class="results-grid" id="resultsGrid"></div>
                </div>
            </div>

            <div class="settings-panel">
                <h2 class="settings-title">Settings</h2>

                <div class="preset-buttons" id="presetButtons">
                    <button class="preset-btn active" data-preset="default">Default</button>
                    <button class="preset-btn" data-preset="logo">Logo</button>
                    <button class="preset-btn" data-preset="photo">Photo</button>
                    <button class="preset-btn" data-preset="lineart">Line Art</button>
                    <button class="preset-btn" data-preset="sketch">Sketch</button>
                    <button class="preset-btn" data-preset="minimal">Minimal</button>
                </div>

                <div class="setting-group">
                    <label class="setting-label">Color Mode</label>
                    <select class="setting-input" id="colormode">
                        <option value="color">Color</option>
                        <option value="binary">Black & White</option>
                    </select>
                </div>

                <div class="setting-group">
                    <label class="setting-label">Curve Mode</label>
                    <select class="setting-input" id="mode">
                        <option value="spline">Spline (Smooth)</option>
                        <option value="polygon">Polygon</option>
                        <option value="none">None</option>
                    </select>
                </div>

                <div class="advanced-toggle" id="advancedToggle">
                    ▶ Advanced Settings
                </div>

                <div class="advanced-settings" id="advancedSettings">
                    <div class="setting-group">
                        <label class="setting-label">Filter Speckle (1-100)</label>
                        <input type="number" class="setting-input" id="filter_speckle" value="4" min="1" max="100">
                    </div>

                    <div class="setting-group">
                        <label class="setting-label">Color Precision (1-8)</label>
                        <input type="number" class="setting-input" id="color_precision" value="6" min="1" max="8">
                    </div>

                    <div class="setting-group">
                        <label class="setting-label">Layer Difference (1-100)</label>
                        <input type="number" class="setting-input" id="layer_difference" value="16" min="1" max="100">
                    </div>

                    <div class="setting-group">
                        <label class="setting-label">Corner Threshold (1-180)</label>
                        <input type="number" class="setting-input" id="corner_threshold" value="60" min="1" max="180">
                    </div>

                    <div class="setting-group">
                        <label class="setting-label">Length Threshold</label>
                        <input type="number" class="setting-input" id="length_threshold" value="4.0" step="0.5" min="0">
                    </div>

                    <div class="setting-group">
                        <label class="setting-label">Path Precision (1-10)</label>
                        <input type="number" class="setting-input" id="path_precision" value="3" min="1" max="10">
                    </div>
                </div>

                <div class="setting-group checkbox-group">
                    <label class="checkbox-label">
                        <input type="checkbox" id="optimize" checked>
                        <span class="checkmark"></span>
                        Optimize SVG (reduce file size)
                    </label>
                </div>

                <button class="convert-btn" id="convertBtn" disabled>Convert to SVG</button>
            </div>
        </div>
    </div>

    <script>
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const fileList = document.getElementById('fileList');
        const convertBtn = document.getElementById('convertBtn');
        const loading = document.getElementById('loading');
        const resultsSection = document.getElementById('resultsSection');
        const resultsGrid = document.getElementById('resultsGrid');
        const presetButtons = document.getElementById('presetButtons');
        const advancedToggle = document.getElementById('advancedToggle');
        const advancedSettings = document.getElementById('advancedSettings');
        const downloadAllBtn = document.getElementById('downloadAllBtn');
        const urlInput = document.getElementById('urlInput');
        const urlConvertBtn = document.getElementById('urlConvertBtn');
        const themeToggle = document.getElementById('themeToggle');
        const themeIcon = themeToggle.querySelector('.theme-icon');

        let selectedFiles = [];
        let currentPreset = 'default';
        let presets = {};
        let convertedFiles = [];

        // Theme toggle
        const savedTheme = localStorage.getItem('theme') || 'dark';
        if (savedTheme === 'light') {
            document.body.classList.add('light-theme');
            themeIcon.textContent = '☀️';
        }

        themeToggle.addEventListener('click', () => {
            document.body.classList.toggle('light-theme');
            const isLight = document.body.classList.contains('light-theme');
            themeIcon.textContent = isLight ? '☀️' : '🌙';
            localStorage.setItem('theme', isLight ? 'light' : 'dark');
        });

        // Fetch presets
        fetch('/api/presets')
            .then(res => res.json())
            .then(data => {
                presets = data;
                applyPreset('default');
            });

        // Drop zone events
        dropZone.addEventListener('click', () => fileInput.click());

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('drag-over');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            handleFiles(e.dataTransfer.files);
        });

        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files);
        });

        function handleFiles(files) {
            for (const file of files) {
                if (isValidFile(file) && !selectedFiles.some(f => f.name === file.name)) {
                    selectedFiles.push(file);
                }
            }
            updateFileList();
        }

        function isValidFile(file) {
            const validTypes = ['image/png', 'image/jpeg', 'image/bmp', 'image/gif', 'image/webp', 'image/tiff'];
            return validTypes.includes(file.type);
        }

        function updateFileList() {
            fileList.innerHTML = selectedFiles.map((file, index) => `
                <div class="file-item">
                    <span class="file-item-name">${file.name}</span>
                    <button class="file-item-remove" onclick="removeFile(${index})">×</button>
                </div>
            `).join('');
            convertBtn.disabled = selectedFiles.length === 0;
        }

        function removeFile(index) {
            selectedFiles.splice(index, 1);
            updateFileList();
        }

        // Preset buttons
        presetButtons.addEventListener('click', (e) => {
            if (e.target.classList.contains('preset-btn')) {
                const preset = e.target.dataset.preset;
                document.querySelectorAll('.preset-btn').forEach(btn => btn.classList.remove('active'));
                e.target.classList.add('active');
                currentPreset = preset;
                applyPreset(preset);
            }
        });

        function applyPreset(preset) {
            if (presets[preset]) {
                const settings = presets[preset];
                document.getElementById('colormode').value = settings.colormode;
                document.getElementById('mode').value = settings.mode;
                document.getElementById('filter_speckle').value = settings.filter_speckle;
                document.getElementById('color_precision').value = settings.color_precision;
                document.getElementById('layer_difference').value = settings.layer_difference;
                document.getElementById('corner_threshold').value = settings.corner_threshold;
                document.getElementById('length_threshold').value = settings.length_threshold;
                document.getElementById('path_precision').value = settings.path_precision;
            }
        }

        // Advanced settings toggle
        advancedToggle.addEventListener('click', () => {
            const isOpen = advancedSettings.classList.toggle('show');
            advancedToggle.innerHTML = (isOpen ? '▼' : '▶') + ' Advanced Settings';
        });

        // Convert button
        convertBtn.addEventListener('click', async () => {
            if (selectedFiles.length === 0) return;

            loading.classList.add('active');
            convertBtn.disabled = true;
            resultsSection.style.display = 'none';

            const formData = new FormData();
            selectedFiles.forEach(file => formData.append('files', file));
            formData.append('preset', currentPreset);
            formData.append('colormode', document.getElementById('colormode').value);
            formData.append('mode', document.getElementById('mode').value);
            formData.append('filter_speckle', document.getElementById('filter_speckle').value);
            formData.append('color_precision', document.getElementById('color_precision').value);
            formData.append('layer_difference', document.getElementById('layer_difference').value);
            formData.append('corner_threshold', document.getElementById('corner_threshold').value);
            formData.append('length_threshold', document.getElementById('length_threshold').value);
            formData.append('path_precision', document.getElementById('path_precision').value);
            formData.append('optimize', document.getElementById('optimize').checked);

            try {
                const response = await fetch('/api/convert', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                displayResults(data.results);
            } catch (error) {
                alert('Conversion failed: ' + error.message);
            } finally {
                loading.classList.remove('active');
                convertBtn.disabled = false;
            }
        });

        function displayResults(results) {
            convertedFiles = results.filter(r => r.success);
            resultsGrid.innerHTML = results.map((result, index) => {
                if (result.success) {
                    const reduction = ((1 - result.output_size / result.input_size) * 100).toFixed(1);
                    return `
                        <div class="result-card">
                            <div class="comparison-container" data-index="${index}">
                                <div class="comparison-svg">${result.svg_content}</div>
                                <div class="comparison-original">
                                    <img src="${result.original_image}" alt="Original">
                                </div>
                                <div class="comparison-slider"></div>
                                <div class="comparison-labels">
                                    <span>Original</span>
                                    <span>SVG</span>
                                </div>
                            </div>
                            <div class="result-info">
                                <div class="result-filename">${result.original_name}</div>
                                <div class="result-stats">
                                    ${formatBytes(result.input_size)} → ${formatBytes(result.output_size)}
                                    (${reduction > 0 ? '-' : '+'}${Math.abs(reduction)}%)
                                </div>
                                <div class="result-actions">
                                    <button class="result-btn primary" onclick="downloadSvg('${result.svg_filename}')">SVG</button>
                                    <button class="result-btn" onclick="downloadPng(\`${encodeURIComponent(result.svg_content)}\`, '${result.svg_filename}')">PNG</button>
                                    <button class="result-btn" onclick="copySvg(\`${encodeURIComponent(result.svg_content)}\`)">Copy</button>
                                </div>
                            </div>
                        </div>
                    `;
                } else {
                    return `
                        <div class="result-card">
                            <div class="result-info">
                                <div class="result-filename">${result.original_name}</div>
                                <div class="error-message">${result.error}</div>
                            </div>
                        </div>
                    `;
                }
            }).join('');

            resultsSection.style.display = 'block';
            downloadAllBtn.classList.toggle('show', convertedFiles.length > 1);
            initComparisonSliders();
        }

        function formatBytes(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        }

        function downloadSvg(filename) {
            window.location.href = '/api/download/' + filename;
        }

        function copySvg(encodedContent) {
            const content = decodeURIComponent(encodedContent);
            navigator.clipboard.writeText(content).then(() => {
                alert('SVG copied to clipboard!');
            });
        }

        function downloadPng(svgContent, filename) {
            const svg = new Blob([decodeURIComponent(svgContent)], {type: 'image/svg+xml'});
            const url = URL.createObjectURL(svg);
            const img = new Image();

            img.onload = function() {
                const canvas = document.createElement('canvas');
                canvas.width = img.width || 800;
                canvas.height = img.height || 600;
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = '#ffffff';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(img, 0, 0);

                canvas.toBlob(function(blob) {
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = filename.replace('.svg', '.png');
                    a.click();
                    URL.revokeObjectURL(a.href);
                }, 'image/png');

                URL.revokeObjectURL(url);
            };

            img.src = url;
        }

        function initComparisonSliders() {
            document.querySelectorAll('.comparison-container').forEach(container => {
                const slider = container.querySelector('.comparison-slider');
                const original = container.querySelector('.comparison-original');
                let isDragging = false;

                function updateSlider(x) {
                    const rect = container.getBoundingClientRect();
                    let percent = ((x - rect.left) / rect.width) * 100;
                    percent = Math.max(0, Math.min(100, percent));
                    slider.style.left = percent + '%';
                    original.style.clipPath = `inset(0 ${100 - percent}% 0 0)`;
                }

                slider.addEventListener('mousedown', (e) => {
                    isDragging = true;
                    e.preventDefault();
                });

                document.addEventListener('mousemove', (e) => {
                    if (isDragging) updateSlider(e.clientX);
                });

                document.addEventListener('mouseup', () => {
                    isDragging = false;
                });

                // Touch support
                slider.addEventListener('touchstart', (e) => {
                    isDragging = true;
                    e.preventDefault();
                });

                document.addEventListener('touchmove', (e) => {
                    if (isDragging) updateSlider(e.touches[0].clientX);
                });

                document.addEventListener('touchend', () => {
                    isDragging = false;
                });

                // Click to move slider
                container.addEventListener('click', (e) => {
                    if (e.target !== slider) updateSlider(e.clientX);
                });
            });
        }

        downloadAllBtn.addEventListener('click', () => {
            convertedFiles.forEach(file => {
                downloadSvg(file.svg_filename);
            });
        });

        // URL conversion
        urlConvertBtn.addEventListener('click', convertFromUrl);
        urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') convertFromUrl();
        });

        async function convertFromUrl() {
            const url = urlInput.value.trim();
            if (!url) {
                alert('Please enter an image URL');
                return;
            }

            loading.classList.add('active');
            urlConvertBtn.disabled = true;
            resultsSection.style.display = 'none';

            const settings = {
                url: url,
                preset: currentPreset,
                colormode: document.getElementById('colormode').value,
                mode: document.getElementById('mode').value,
                filter_speckle: document.getElementById('filter_speckle').value,
                color_precision: document.getElementById('color_precision').value,
                layer_difference: document.getElementById('layer_difference').value,
                corner_threshold: document.getElementById('corner_threshold').value,
                length_threshold: document.getElementById('length_threshold').value,
                path_precision: document.getElementById('path_precision').value,
                optimize: document.getElementById('optimize').checked,
            };

            try {
                const response = await fetch('/api/convert-url', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(settings)
                });

                const data = await response.json();

                if (data.success) {
                    displayResults([data]);
                    urlInput.value = '';
                } else {
                    alert('Conversion failed: ' + data.error);
                }
            } catch (error) {
                alert('Conversion failed: ' + error.message);
            } finally {
                loading.classList.remove('active');
                urlConvertBtn.disabled = false;
            }
        }
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    print("Starting Image to SVG Converter...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000)
