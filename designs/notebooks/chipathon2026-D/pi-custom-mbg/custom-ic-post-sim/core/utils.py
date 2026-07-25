"""
@Owner: Ahmad Jabar Ilmi (Physical Verification & Automation Engineer)
@Role: Utility functions, path management, SVG display, parameter cleaning.
"""
import os, tempfile

TEMP_DIR = tempfile.gettempdir()
GDS_PATH = os.path.join(TEMP_DIR, "out.gds")
SVG_PATH = os.path.join(TEMP_DIR, "out.svg")


def clean_param(val_str):
    if val_str is None or val_str == "-":
        return 1
    if isinstance(val_str, str) and val_str.lower().endswith('u'):
        return float(val_str[:-1])
    if isinstance(val_str, str) and val_str.lower().endswith('f'):
        return float(val_str[:-1])
    try:
        return float(val_str)
    except (ValueError, TypeError):
        try:
            return int(val_str)
        except (ValueError, TypeError):
            return val_str


def display_gds(gds_file, scale=3):
    try:
        import gdstk
        top_level_cell = gdstk.read_gds(gds_file).top_level()[0]
        svg_path = os.path.join(TEMP_DIR, f"display_{os.getpid()}.svg")
        top_level_cell.write_svg(svg_path)
        try:
            import svgutils.transform as sg
            fig = sg.fromfile(svg_path)
            fig.set_size((str(float(fig.width) * scale), str(float(fig.height) * scale)))
            fig.save(svg_path)
        except ImportError:
            pass
        import IPython.display
        IPython.display.display(IPython.display.SVG(svg_path))
    except Exception as e:
        print(f"Error rendering SVG: {e}")


def display_component(component, scale=3):
    try:
        gds_path = os.path.join(TEMP_DIR, f"comp_{os.getpid()}.gds")
        component.write_gds(gds_path)
        display_gds(gds_path, scale)
    except Exception as e:
        print(f"Error writing GDS: {e}")
