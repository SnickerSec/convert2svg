#!/usr/bin/env python3
"""
Web application for converting images to SVG.
Features: batch conversion, live preview, preset profiles.
"""

import os
import uuid
import base64
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template_string
from werkzeug.utils import secure_filename
import vtracer

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
                convert_image(input_path, output_path, settings)

                # Read SVG content for preview
                with open(output_path, 'r') as f:
                    svg_content = f.read()

                # Get file sizes
                input_size = os.path.getsize(input_path)
                output_size = os.path.getsize(output_path)

                results.append({
                    'original_name': filename,
                    'svg_filename': output_filename,
                    'svg_content': svg_content,
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

        with open(output_path, 'r') as f:
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

        .main-content {
            display: grid;
            grid-template-columns: 1fr 300px;
            gap: 20px;
        }

        @media (max-width: 900px) {
            .main-content {
                grid-template-columns: 1fr;
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
            <h1>Image to SVG Converter</h1>
            <p class="subtitle">Convert raster images to scalable vector graphics</p>
        </header>

        <div class="main-content">
            <div class="upload-section">
                <div class="drop-zone" id="dropZone">
                    <div class="drop-zone-icon">🖼️</div>
                    <div class="drop-zone-text">Drop images here or click to upload</div>
                    <div class="drop-zone-hint">Supports PNG, JPG, BMP, GIF, WebP, TIFF</div>
                </div>
                <input type="file" id="fileInput" class="file-input" multiple accept=".png,.jpg,.jpeg,.bmp,.gif,.webp,.tiff">

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

        let selectedFiles = [];
        let currentPreset = 'default';
        let presets = {};
        let convertedFiles = [];

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
            resultsGrid.innerHTML = results.map(result => {
                if (result.success) {
                    const reduction = ((1 - result.output_size / result.input_size) * 100).toFixed(1);
                    return `
                        <div class="result-card">
                            <div class="result-preview">${result.svg_content}</div>
                            <div class="result-info">
                                <div class="result-filename">${result.original_name}</div>
                                <div class="result-stats">
                                    ${formatBytes(result.input_size)} → ${formatBytes(result.output_size)}
                                    (${reduction > 0 ? '-' : '+'}${Math.abs(reduction)}%)
                                </div>
                                <div class="result-actions">
                                    <button class="result-btn primary" onclick="downloadSvg('${result.svg_filename}')">Download</button>
                                    <button class="result-btn" onclick="copySvg(\`${encodeURIComponent(result.svg_content)}\`)">Copy SVG</button>
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

        downloadAllBtn.addEventListener('click', () => {
            convertedFiles.forEach(file => {
                downloadSvg(file.svg_filename);
            });
        });
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    print("Starting Image to SVG Converter...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000)
