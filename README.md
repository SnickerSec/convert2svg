# Image to SVG Converter

A web application that converts raster images (PNG, JPG, BMP, etc.) to scalable vector graphics (SVG) using advanced image tracing algorithms.

## Features

- **Drag & Drop Upload** - Simply drag images onto the page or click to browse
- **URL Conversion** - Convert images directly from URLs
- **Batch Processing** - Convert multiple images at once
- **Live Comparison** - Interactive slider to compare original vs SVG
- **SVG Optimization** - Reduce file size with built-in optimizer
- **Multiple Export Formats** - Download as SVG or PNG
- **6 Preset Profiles** - Default, Logo, Photo, Line Art, Sketch, Minimal
- **Advanced Settings** - Fine-tune conversion parameters
- **Dark/Light Theme** - Toggle between themes with persistence
- **Mobile Responsive** - Works on all device sizes

## Supported Formats

**Input:** PNG, JPG, JPEG, BMP, GIF, WebP, TIFF

**Output:** SVG, PNG

## Installation

### Option 1: Local Installation

```bash
# Clone the repository
git clone https://github.com/SnickerSec/convert2svg.git
cd convert2svg

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

Open http://localhost:5000 in your browser.

### Option 2: Docker

```bash
# Build and run with Docker Compose
docker-compose up -d

# Or build manually
docker build -t convert2svg .
docker run -p 5000:5000 convert2svg
```

## Usage

### Web Interface

1. Open http://localhost:5000
2. Drag and drop images or paste a URL
3. Select a preset or adjust settings
4. Click "Convert to SVG"
5. Use the comparison slider to preview
6. Download as SVG or PNG

### Command Line

```bash
# Basic conversion
python convert_to_svg.py image.png

# Specify output file
python convert_to_svg.py image.jpg -o output.svg

# Black and white conversion
python convert_to_svg.py logo.png --colormode binary

# High detail photo conversion
python convert_to_svg.py photo.jpg --color-precision 8 --filter-speckle 2
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--colormode` | `color` or `binary` | `color` |
| `--mode` | `spline`, `polygon`, or `none` | `spline` |
| `--filter-speckle` | Remove noise (pixels) | `4` |
| `--color-precision` | Color detail (1-8) | `6` |
| `--layer-difference` | Layer separation | `16` |
| `--corner-threshold` | Corner detection (degrees) | `60` |
| `--length-threshold` | Min segment length | `4.0` |
| `--path-precision` | Coordinate precision | `3` |

## Presets

| Preset | Best For |
|--------|----------|
| **Default** | General purpose |
| **Logo** | Simple logos, icons |
| **Photo** | Photographs, detailed images |
| **Line Art** | Black and white drawings |
| **Sketch** | Pencil sketches, hand-drawn |
| **Minimal** | Simplified, low-detail output |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web interface |
| `/api/presets` | GET | Get available presets |
| `/api/convert` | POST | Convert uploaded files |
| `/api/convert-url` | POST | Convert from URL |
| `/api/download/<filename>` | GET | Download SVG file |

## Dependencies

- Flask - Web framework
- vtracer - Image tracing engine
- scour - SVG optimizer
- requests - HTTP client

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
