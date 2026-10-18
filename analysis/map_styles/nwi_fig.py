"""NWI palette adapted from bench/figures/nwi_fig.py.
Colors transcribe the USFWS wetlands map-service renderer, WETLAND_TYPE."""
from .drawing import W, G
OUT = '#6e6e6e'
NWI = {'Freshwater Forested/Shrub Wetland': '#008737', 'Freshwater Emergent Wetland': '#7fc319', 'Freshwater Pond': '#678bc0', 'Estuarine and Marine Wetland': '#66c2a5', 'Riverine': '#008fbf', 'Lake': '#12007c', 'Estuarine and Marine Deepwater': '#007c87', 'Other': '#b38753'}
NONE = ('#d9d9d9', OUT)

def style(layer, p):
    v = p.get('WETLAND_TYPE')
    if v in NWI:
        return (NWI[v], OUT, None, True, 'NWI renderer')
    return (*NONE, None, False, '')
cfg = dict(stem='usfws_luisiana_wetlands_geopackage', zorder=['hydrography'], style=style, cls=lambda l, p: p.get('WETLAND_TYPE'))
