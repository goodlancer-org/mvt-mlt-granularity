"""Exact MVT multiset aggregation. No geometry library, clipping or type coercion."""
from __future__ import annotations
from collections import Counter
from array import array
import hashlib
import struct
import sys
from mapbox_vector_tile.Mapbox import vector_tile_pb2


def tile_message(raw):
    tile = vector_tile_pb2.tile()
    tile.ParseFromString(raw)
    return tile


def translated_commands(commands, dx, dy):
    out = list(commands)
    if not out:
        return out
    if out[0] & 7 != 1 or out[0] >> 3 < 1 or len(out) < 3:
        raise ValueError('MVT geometry must begin with MoveTo')
    for index, shift in ((1, dx), (2, dy)):
        value = out[index]
        signed = (value >> 1) ^ -(value & 1)
        signed += shift
        out[index] = (signed << 1) ^ (signed >> 31)
        if not 0 <= out[index] <= 0xffffffff:
            raise ValueError('translated MVT coordinate overflows sint32')
    return out


def geometry_counts(commands):
    vertices = parts = 0
    pos = 0
    while pos < len(commands):
        command = commands[pos]; pos += 1
        kind, count = command & 7, command >> 3
        if count < 1 or kind not in (1, 2, 7):
            raise ValueError('invalid MVT geometry command')
        if kind in (1, 2):
            vertices += count
            if kind == 1: parts += count
            pos += 2 * count
        if pos > len(commands): raise ValueError('truncated MVT geometry')
    return vertices, parts


def feature_key(layer, feature, dx=0, dy=0):
    """Typed protobuf values, ID presence, topology commands and translated coordinates."""
    if len(feature.tags) % 2: raise ValueError('unpaired MVT property tag')
    props = sorted((layer.keys[feature.tags[i]],
                    layer.values[feature.tags[i+1]].SerializeToString(deterministic=True))
                   for i in range(0, len(feature.tags), 2))
    digest = hashlib.sha256()
    for value in (layer.name.encode(), str(layer.version).encode(),
                  str(feature.type).encode(), str(feature.id if feature.HasField('id') else None).encode()):
        digest.update(struct.pack('<I', len(value))); digest.update(value)
    digest.update(struct.pack('<I',len(props)))
    for key, value in props:
        encoded = key.encode(); digest.update(struct.pack('<I',len(encoded))); digest.update(encoded)
        digest.update(struct.pack('<I',len(value))); digest.update(value)
    geometry=translated_commands(feature.geometry, dx, dy)
    digest.update(struct.pack('<I',len(geometry)))
    packed=array('I',geometry)
    if packed.itemsize!=4:raise RuntimeError('MVT hash requires 32-bit unsigned words')
    if sys.byteorder!='little':packed.byteswap()
    digest.update(packed.tobytes())
    return digest.digest()


def aggregate_tiles(children, factor):
    """children = [(child_x_mod_n, child_y_mod_n, raw_mvt), ...].

    Returns a verified aggregate and its exact feature/vertex/fragment counts.
    A partial edge block retains only its present children; no empty tiles invented.
    """
    if factor not in (2, 4): raise ValueError('factor must be 2 or 4')
    result = vector_tile_pb2.tile()
    layers = {}; dictionaries = {}
    expected = Counter()
    vertices = fragments = features = 0
    for cx, cy, raw in sorted(children, key=lambda c: (c[1],c[0])):
        if not (0 <= cx < factor and 0 <= cy < factor): raise ValueError('child outside block')
        for layer in tile_message(raw).layers:
            if layer.extent != 4096: raise ValueError('Standard MVT extent must be 4096')
            if layer.name not in layers:
                target = result.layers.add(); target.CopyFrom(layer)
                target.ClearField('features'); target.ClearField('keys'); target.ClearField('values')
                target.extent = 4096 * factor
                layers[layer.name] = target
                dictionaries[layer.name] = ({},{})
            target = layers[layer.name]
            if target.version != layer.version: raise ValueError('inconsistent layer version')
            # MVT shares key/value dictionaries within a layer too. Intern them
            # across children so the MVT control receives the same enlarged
            # dictionary scope; concatenating dictionaries would handicap MVT.
            keys,values=dictionaries[layer.name]; key_map=[]; value_map=[]
            for key in layer.keys:
                if key not in keys:
                    keys[key]=len(target.keys);target.keys.append(key)
                key_map.append(keys[key])
            for value in layer.values:
                wire=value.SerializeToString(deterministic=True)
                if wire not in values:
                    values[wire]=len(target.values);target.values.add().CopyFrom(value)
                value_map.append(values[wire])
            dx, dy = cx * 4096, cy * 4096
            for feature in layer.features:
                expected[feature_key(layer, feature, dx, dy)] += 1
                output = target.features.add(); output.CopyFrom(feature)
                output.ClearField('tags')
                output.tags.extend((key_map if i % 2 == 0 else value_map)[t]
                                   for i,t in enumerate(feature.tags))
                output.ClearField('geometry'); output.geometry.extend(translated_commands(feature.geometry,dx,dy))
                v, f = geometry_counts(feature.geometry)
                vertices += v; fragments += f; features += 1
    raw = result.SerializeToString(deterministic=True)
    # Parse the serialized result independently, so writer mistakes fail this gate.
    actual = Counter(feature_key(layer,feature) for layer in tile_message(raw).layers for feature in layer.features)
    if actual != expected: raise ValueError('aggregate feature multiset differs from Standard')
    return raw, {'features':features,'vertices':vertices,'fragments':fragments,
                 'children':len(children),'equivalent':True}
