#!/usr/bin/env python3
"""
Image to SVG converter using vtracer for vectorization.
Converts raster images (PNG, JPG, BMP, etc.) to scalable vector graphics.
"""

import argparse
import sys
from pathlib import Path

try:
    import vtracer
except ImportError:
    print("Error: vtracer library not found.")
    print("Install it with: pip install vtracer")
    sys.exit(1)


def convert_to_svg(
    input_path: str,
    output_path: str = None,
    colormode: str = "color",
    hierarchical: str = "stacked",
    mode: str = "spline",
    filter_speckle: int = 4,
    color_precision: int = 6,
    layer_difference: int = 16,
    corner_threshold: int = 60,
    length_threshold: float = 4.0,
    max_iterations: int = 10,
    splice_threshold: int = 45,
    path_precision: int = 3,
) -> str:
    """
    Convert a raster image to SVG.

    Args:
        input_path: Path to the input image file
        output_path: Path for the output SVG file (default: same name with .svg extension)
        colormode: 'color' or 'binary' (black and white)
        hierarchical: 'stacked' or 'cutout' - how overlapping shapes are handled
        mode: 'spline', 'polygon', or 'none' - curve fitting mode
        filter_speckle: Remove speckles smaller than this (in pixels)
        color_precision: Number of significant bits for color quantization (1-8)
        layer_difference: Color difference threshold for layer separation
        corner_threshold: Angle threshold for corner detection (in degrees)
        length_threshold: Minimum segment length
        max_iterations: Max iterations for curve fitting
        splice_threshold: Angle threshold for splicing splines
        path_precision: Decimal precision for path coordinates

    Returns:
        Path to the generated SVG file
    """
    input_file = Path(input_path)

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if output_path is None:
        output_path = str(input_file.with_suffix(".svg"))

    # Convert the image
    vtracer.convert_image_to_svg_py(
        input_path,
        output_path,
        colormode=colormode,
        hierarchical=hierarchical,
        mode=mode,
        filter_speckle=filter_speckle,
        color_precision=color_precision,
        layer_difference=layer_difference,
        corner_threshold=corner_threshold,
        length_threshold=length_threshold,
        max_iterations=max_iterations,
        splice_threshold=splice_threshold,
        path_precision=path_precision,
    )

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Convert raster images to SVG vector graphics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s image.png                    # Basic conversion
  %(prog)s image.jpg -o output.svg      # Specify output file
  %(prog)s logo.png --colormode binary  # Black and white conversion
  %(prog)s photo.jpg --color-precision 8 --filter-speckle 2  # High detail
        """,
    )

    parser.add_argument("input", help="Input image file (PNG, JPG, BMP, etc.)")
    parser.add_argument("-o", "--output", help="Output SVG file path")
    parser.add_argument(
        "--colormode",
        choices=["color", "binary"],
        default="color",
        help="Color mode: 'color' or 'binary' (default: color)",
    )
    parser.add_argument(
        "--hierarchical",
        choices=["stacked", "cutout"],
        default="stacked",
        help="Shape hierarchy: 'stacked' or 'cutout' (default: stacked)",
    )
    parser.add_argument(
        "--mode",
        choices=["spline", "polygon", "none"],
        default="spline",
        help="Curve fitting mode (default: spline)",
    )
    parser.add_argument(
        "--filter-speckle",
        type=int,
        default=4,
        help="Filter out speckles smaller than N pixels (default: 4)",
    )
    parser.add_argument(
        "--color-precision",
        type=int,
        default=6,
        choices=range(1, 9),
        metavar="[1-8]",
        help="Color precision in bits (default: 6)",
    )
    parser.add_argument(
        "--layer-difference",
        type=int,
        default=16,
        help="Color difference for layer separation (default: 16)",
    )
    parser.add_argument(
        "--corner-threshold",
        type=int,
        default=60,
        help="Corner detection angle threshold in degrees (default: 60)",
    )
    parser.add_argument(
        "--length-threshold",
        type=float,
        default=4.0,
        help="Minimum segment length (default: 4.0)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Max iterations for curve fitting (default: 10)",
    )
    parser.add_argument(
        "--splice-threshold",
        type=int,
        default=45,
        help="Angle threshold for splicing splines (default: 45)",
    )
    parser.add_argument(
        "--path-precision",
        type=int,
        default=3,
        help="Decimal precision for path coordinates (default: 3)",
    )

    args = parser.parse_args()

    try:
        output_file = convert_to_svg(
            args.input,
            args.output,
            colormode=args.colormode,
            hierarchical=args.hierarchical,
            mode=args.mode,
            filter_speckle=args.filter_speckle,
            color_precision=args.color_precision,
            layer_difference=args.layer_difference,
            corner_threshold=args.corner_threshold,
            length_threshold=args.length_threshold,
            max_iterations=args.max_iterations,
            splice_threshold=args.splice_threshold,
            path_precision=args.path_precision,
        )
        print(f"Successfully converted to: {output_file}")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Conversion failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
