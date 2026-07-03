import os
import IPython.display
import svgutils.transform as sg
import gdstk

TEMP_DIR = os.getcwd()
GDS_PATH = os.path.join(TEMP_DIR, "out.gds")
SVG_PATH = os.path.join(TEMP_DIR, "out.svg")


def clean_param(val_str):
    if not val_str or val_str == "-":
        return 1
    if isinstance(val_str, str) and val_str.lower().endswith('u'):
        return float(val_str[:-1])
    try:
        return float(val_str)
    except ValueError:
        return int(val_str) if val_str.isdigit() else val_str


def display_gds(gds_file, scale=3):
    try:
        top_level_cell = gdstk.read_gds(gds_file).top_level()[0]
        top_level_cell.write_svg(SVG_PATH)
        fig = sg.fromfile(SVG_PATH)
        fig.set_size((str(float(fig.width) * scale), str(float(fig.height) * scale)))
        fig.save(SVG_PATH)
        IPython.display.display(IPython.display.SVG(SVG_PATH))
    except Exception as e:
        print(f"Error rendering SVG: {e}")


def display_component(component, scale=3):
    try:
        component.write_gds(GDS_PATH)
        display_gds(GDS_PATH, scale)
    except Exception as e:
        print(f"Error writing GDS: {e}")
