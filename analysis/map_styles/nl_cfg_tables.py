from .drawing import W, G

OFF = {
 "land_use": {   # bgt-fysiekVoorkomen; sld-0010-begroeidterreindeel / sld-0011-onbegroeidterreindeel
  "grasland overig": ("#c9eb70", "#c9eb70", "0010", None), "grasland agrarisch": ("#c9eb70", "#c9eb70", "0010", None),
  "groenvoorziening": ("#8ca800", "#8ca800", "0010", None), "houtwal": ("#8ca800", "#8ca800", "0010", None),
  "bouwland": ("#ffffcc", "#ffffcc", "0010", None), "duin": ("#c9eb70", "#c9eb70", "0010", None),
  "kwelder": ("#c9eb70", "#c9eb70", "0010", None), "heide": ("#fcb3fb", "#fcb3fb", "0010", None),
  "boomteelt": (None, "#ffffcc", "0010", "....."), "fruitteelt": (None, "#ffffcc", "0010", "....."),
  "loofbos": (None, "#8ca800", "0010", "ooo"), "naaldbos": (None, "#8ca800", "0010", "ooo"),
  "gemengd bos": (None, "#8ca800", "0010", "ooo"), "struiken": (None, "#8ca800", "0010", "xxx"),
  "moeras": (None, "#c9eb70", "0010", "---"), "rietland": (None, "#c9eb70", "0010", "|||"),
  "erf": (W, G, "0011", None), "gesloten verharding": (W, G, "0011", None),
  "open verharding": (W, G, "0011", None), "half verhard": (W, G, "0011", None),
  "onverhard": ("#f3f5f6", "#f3f5f6", "0011", None), "zand": ("#ffff99", "#ffff99", "0011", None),
  "transitie": ("#f2f2f2", G, "0010", None)},
 "transportation": {  # bgt-functie; sld-0021-wegdeel / sld-0022-ondersteunendwegdeel / sld-0020-spoor
  "rijbaan lokale weg": (W, G, "0021", None), "rijbaan regionale weg": ("#ffaa00", G, "0021", None),
  "rijbaan autoweg": ("#e60000", G, "0021", None), "rijbaan autosnelweg": ("#996089", G, "0021", None),
  "fietspad": (W, G, "0021", None), "voetpad": ("#ff9999", G, "0021", None),
  "voetpad op trap": ("#ff9999", G, "0021", None), "voetgangersgebied": ("#ff9999", G, "0021", None),
  "parkeervlak": (W, G, "0021", None), "inrit": (W, G, "0021", None), "woonerf": (W, G, "0021", None),
  "ruiterpad": (W, G, "0021", None), "baan voor vliegverkeer": (W, G, "0021", None),
  "OV-baan": ("#CCCCCC", G, "0021", None), "spoorbaan": ("#c0c0c0", G, "0021", None),
  "overweg": ("#c0c0c0", G, "0021", None), "berm": ("#ff9999", "#ff9999", "0022", None),
  "verkeerseiland": ("#ff9999", "#ff9999", "0022", None), "transitie": ("#f2f2f2", G, "0021", None),
  "trein": (None, G, "0020", "line"), "tram": (None, G, "0020", "line"), "sneltram": (None, G, "0020", "line")},
 "hydrography": {  # bgt-type; sld-0030-waterdeel / sld-0031-ondersteunendwaterdeel
  "watervlakte": ("#bee8ff", "#bee8ff", "0030", None), "waterloop": ("#73e9ff", "#73e9ff", "0030", None),
  "zee": ("#99CCFF", "#99CCFF", "0030", None), "greppel, droge sloot": (None, "#73e9ff", "0030", "line"),
  "oever, slootkant": ("#C9EB70", "#C9EB70", "0031", None), "slik": ("#73e9ff", "#73e9ff", "0031", None),
  "transitie": ("#f2f2f2", G, "0030", None)},
 "buildings": {  # sld-0044-pand (all pand features) / sld-0043-overigbouwwerk
  "_pand": ("#cc0000", "#D73939", "0044", None),
  "overkapping": ("#CC0000", "#CC0000", "0043", None), "bassin": ("#BEE8FF", "#CC0000", "0043", None),
  "bezinkbak": ("#BEE8FF", "#CC0000", "0043", None), "lage trafo": ("#CC0000", "#CC0000", "0043", None),
  "open loods": ("#CC0000", "#CC0000", "0043", None), "opslagtank": ("#CC0000", "#CC0000", "0043", None),
  "windturbine": ("#990000", "#990000", "0043", None)},
 "infrastructure": {  # only the few PLUS values that do have an official symbol
  "hek": (None, "#000000", "0045", "line"), "draadraster": (None, "#000000", "0045", "line"),
  "duiker": (None, "#CC0000", "0041", "line")},
 "functioneelgebied": {"kering": (None, "#002750", "0060", "line")},   # sld-0060
 "overigescheiding": {"hek": (None, "#000000", "0080", "line"), "geluidsscherm": (None, "#6600cc", "0080", "line"),
                      "muur": (None, "#cc0000", "0080", "line"), "kademuur": (None, "#CC0000", "0080", "line")},
 "ongeclassificeerdobject": {"_all": (W, G, "0900", None)},
 "openbareruimtelabel": {"Weg": (None, "#000000", "0071", "pt"), "Water": (None, "#002750", "0071", "pt"),
                         "Terrein": (None, "#000000", "0071", "pt"), "Kunstwerk": (None, "#000000", "0071", "pt"),
                         "Administratief gebied": (None, "#000000", "0071", "pt"),
                         "Landschappelijk gebied": (None, "#425000", "0071", "pt")},
}
FALLBACK = ("#8a8a8a", "#535353")   # classes with no official style (PLUS objects etc.)
PROP = {"land_use": "bgt-fysiekVoorkomen", "transportation": "bgt-functie", "hydrography": "bgt-type",
        "buildings": "bgt-type", "functioneelgebied": "bgt-type", "overigescheiding": "plus-type",
        "infrastructure": "plus-type", "weginrichtingselement": "plus-type", "openbareruimtelabel": "openbareRuimteType",
        "ongeclassificeerdobject": None}
ZORDER = ["land_use", "hydrography", "functioneelgebied", "transportation", "infrastructure", "weginrichtingselement",
          "ongeclassificeerdobject", "buildings", "overigescheiding", "openbareruimtelabel"]

def style(layer, props):
    """-> (fill, outline, hatch, official?)"""
    if layer not in PROP:
        return (*FALLBACK, None, False, "unmapped layer")
    v = props.get(PROP[layer]) if PROP[layer] else None
    t = OFF.get(layer, {})
    if layer == "buildings": t_ = t.get(v) or t["_pand"]; return (*t_[:2], t_[3], True, "sld-" + t_[2])
    if layer == "ongeclassificeerdobject": t_ = t["_all"]; return (*t_[:2], t_[3], True, "sld-" + t_[2])
    if v in t: return (*t[v][:2], t[v][3], True, "sld-" + t[v][2])
    if layer == "functioneelgebied": return (None, "#9a9a9a", "line", False, "")
    return (FALLBACK[0], FALLBACK[1], None, False, "")


EN = {"erf": "yard / plot", "groenvoorziening": "green space", "grasland overig": "grassland (other)", "grasland agrarisch": "grassland (agricultural)",
      "open verharding": "open paving", "gesloten verharding": "closed paving", "half verhard": "semi-paved", "zand": "sand", "onverhard": "unpaved",
      "bouwland": "arable land", "transitie": "transition (edge between data sets)", "loofbos": "deciduous forest", "naaldbos": "coniferous forest",
      "gemengd bos": "mixed forest", "boomteelt": "tree nursery", "fruitteelt": "orchard", "struiken": "shrubs", "heide": "heath", "duin": "dune",
      "moeras": "marsh", "rietland": "reed bed", "kwelder": "salt marsh", "houtwal": "wooded bank",
      "rijbaan lokale weg": "local road carriageway", "rijbaan regionale weg": "regional road carriageway", "rijbaan autoweg": "motorway-type road carriageway",
      "rijbaan autosnelweg": "motorway carriageway", "voetpad": "footpath", "fietspad": "cycle path", "berm": "verge", "trein": "train track (line)",
      "spoorbaan": "railway bed", "voetgangersgebied": "pedestrian area", "parkeervlak": "parking area", "OV-baan": "public-transport lane",
      "inrit": "driveway", "overweg": "level crossing", "woonerf": "shared-space street", "verkeerseiland": "traffic island", "voetpad op trap": "footpath on stairs",
      "watervlakte": "water surface", "waterloop": "watercourse", "oever, slootkant": "bank / ditch edge", "greppel, droge sloot": "dry ditch / gully",
      "slik": "mudflat", "zee": "sea", "kering": "barrier (dike / flood defence)", "overkapping": "canopy / covered structure", "bassin": "basin",
      "hek": "fence", "kolk": "street gully / drain", "lichtmast": "lamp post", "inspectie- / rioolput": "manhole", "verkeersbordpaal": "traffic-sign post",
      "verkeersbord": "traffic sign", "afsluitpaal": "bollard", "speelvoorziening": "playground equipment", "brandkraan / -put": "fire hydrant",
      "container": "container", "afvalbak": "waste bin", "bank": "bench", "verkeersregelinstallatiepaal": "traffic-light pole", "rooster": "grate",
      "balustrade": "balustrade", "geleideconstructie": "guard rail", "Weg": "road", "Water": "water", "Terrein": "terrain", "Kunstwerk": "engineering structure",
      "Landschappelijk gebied": "landscape area", "Administratief gebied": "administrative area", "niet-bgt": "not a BGT class (generic)", "ruiterpad": "bridle path",
      "wegwijzer": "signpost", "elektrakast": "electrical cabinet", "portaal": "gantry", "fietsenrek": "bicycle rack", "CAI-kast": "cable-TV cabinet",
      "rioolkast": "sewer cabinet", "waterleidingput": "water-main pit", "verklikker transportleiding": "pipeline marker", "drukknoppaal": "push-button pole",
      "lichtpunt": "light point", "duiker": "culvert", "kunstobject": "art object", "waarschuwingshek": "warning fence",
      "verkeersregelinstallatiekast": "traffic-control cabinet", "openbare verlichtingkast": "street-lighting cabinet", "draadraster": "wire grid fence",
      "abri": "bus shelter", "informatiebord": "information board", "haltepaal": "stop pole", "telpaal": "counting post", "sirene": "siren",
      "lage trafo": "low transformer station", "open loods": "open shed", "opslagtank": "storage tank", "bezinkbak": "settling tank", "windturbine": "wind turbine"}
LAYER_EN = {"land_use": "Land use", "transportation": "Roads & rail", "hydrography": "Water", "buildings": "Buildings",
            "functioneelgebied": "Functional areas", "infrastructure": "Infrastructure", "overigescheiding": "Other separations (fences, walls)",
            "weginrichtingselement": "Road furniture", "ongeclassificeerdobject": "Unclassified objects", "openbareruimtelabel": "Name-label points"}
