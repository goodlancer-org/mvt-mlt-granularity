"""Geological colors from the existing swisstopo legend transcription.
Use attributes retained in current tiles; no historical spatial/id join is needed.
"""
import json
from pathlib import Path
COLORS = json.loads(Path(__file__).with_name('swiss_legend_colors.json').read_text())

def unit(layer, props):
    return props.get('SYMBOL') or props.get('INDEX_') or 'Unclassified'

def style(layer, props):
    value = unit(layer, props)
    return (COLORS.get(value, '#ffffff'), '#4a4a4a', None, value in COLORS, 'swisstopo legend')
cfg = dict(stem='swisstopo_mountains_vector', zorder=['terrain'], style=style, cls=unit, poly_lw=0.3)
