"""MLT decoding with an explicit native allocation budget (not process RSS)."""
import os
import maplibre_tiles


def memory_budget_bytes():
    mib = int(os.environ.get("MLT_DECODE_MEMORY_MIB", "256"))
    if not 1 <= mib <= 4095:
        raise ValueError("MLT_DECODE_MEMORY_MIB must be between 1 and 4095")
    return mib * 1024 * 1024


def decode_mlt(data, **kwargs):
    try:
        return maplibre_tiles.decode_mlt(data, max_memory_bytes=memory_budget_bytes(), **kwargs)
    except TypeError as error:
        if "max_memory_bytes" not in str(error):
            raise
        raise RuntimeError(
            "Install the budget-enabled maplibre-tiles 0.4.1 binding with "
            "python app/converter/build_mlt.py --install"
        ) from error
