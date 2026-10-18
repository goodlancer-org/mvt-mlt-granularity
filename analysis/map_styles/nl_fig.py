"""BGT class palette with local classification tables.
Colors transcribe BGT|IMGeo standard visualization 2.3; drawing order is custom."""
from .drawing import W, G
from .nl_cfg_tables import *
cfg = dict(stem='pdok_netherlands_infrostructure', zorder=ZORDER, style=style, cls=lambda layer, p: p.get(PROP.get(layer)) if PROP.get(layer) else None, pt_s=0.5)
