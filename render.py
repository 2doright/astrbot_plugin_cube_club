import os
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
from pathlib import Path

try:
    import resvg_py
    HAS_RESVG = True
except ImportError:
    HAS_RESVG = False

class SVGRenderer:
    def __init__(self, template_dir: str):
        self.env = Environment(loader=FileSystemLoader(template_dir))
        self.rank_template_name = "rank_template.svg"
        self.heatmap_template_name = "heatmap_template.svg"

    def render_rank(self, data: dict) -> bytes:
        """
        Render rank data to SVG and then convert to PNG bytes.
        """
        template = self.env.get_template(self.rank_template_name)
        
        # Add timestamp
        render_data = {
            **data,
            "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        svg_content = template.render(**render_data)
        
        if not HAS_RESVG:
            raise ImportError("resvg-py is not installed. Please run 'pip install resvg-py'.")
        
        # Convert SVG string to PNG bytes
        png_bytes = resvg_py.svg_to_bytes(svg_string=svg_content)
        return png_bytes

    def render_heatmap(self, data: dict) -> bytes:
        """
        Render heatmap data to SVG and then convert to PNG bytes.
        """
        template = self.env.get_template(self.heatmap_template_name)
        
        render_data = {
            **data,
            "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        svg_content = template.render(**render_data)
        
        if not HAS_RESVG:
            raise ImportError("resvg-py is not installed. Please run 'pip install resvg-py'.")
        
        png_bytes = resvg_py.svg_to_bytes(svg_string=svg_content)
        return png_bytes

def get_renderer():
    """Factory function to get a renderer with the correct template path."""
    curr_dir = Path(__file__).parent
    template_dir = curr_dir / "templates"
    return SVGRenderer(str(template_dir))
