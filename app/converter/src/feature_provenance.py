"""Assign globally unique source IDs with verified geometry/attribute preservation."""
from __future__ import annotations
import json
from pathlib import Path
import sqlite3
import time
import shutil
import os
import xml.etree.ElementTree as ET


def prepare_provenance(source, output):
    """Return a verified derived GPKG and a separate source-feature lookup database.

    IDs are original GPKG FIDs plus disjoint per-source-layer offsets. The VRT
    projects the generated ID as the OGR feature ID, never as an attribute.
    """
    from osgeo import ogr
    source, output = Path(source).resolve(), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    original_source=source;release_output=output
    # SQLite random writes over Docker Desktop's Windows bind mount are costly.
    # Work on the container's disk-backed Linux filesystem, then export artifacts.
    output=Path(os.environ.get('MLT_EXPERIMENT_SCRATCH','/tmp/mlt-experiment'))/source.stem/'provenance'
    output.mkdir(parents=True,exist_ok=True)
    local_source=output/(source.stem+'.original.gpkg')
    shutil.copyfile(source,local_source);source=local_source
    artifact_stem=original_source.stem
    vrt_path = output/(artifact_stem+'.provenance.vrt')
    lookup = output/(artifact_stem+'.provenance.sqlite')
    db = ogr.Open(str(source), 0)
    if db is None: raise RuntimeError(f'Cannot open normalized source: {source}')
    root = ET.Element('OGRVRTDataSource')
    temporary = lookup.with_suffix('.sqlite.partial')
    temporary.unlink(missing_ok=True)
    with sqlite3.connect(temporary) as con, sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src:
        con.executescript('''CREATE TABLE source_layers(name TEXT PRIMARY KEY, fid_column TEXT, id_offset INTEGER, source_features INTEGER);
          CREATE TABLE feature_provenance(id INTEGER PRIMARY KEY, source_layer TEXT NOT NULL, source_fid INTEGER NOT NULL);
          CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);''')
        con.execute('INSERT INTO meta VALUES (?,?)',('normalized_source',str(original_source)))
        offset = 0
        for layer in db:
            if layer.GetGeomType() == ogr.wkbNone: continue
            name = layer.GetName(); fid = layer.GetFIDColumn()
            if not fid: raise ValueError(f'Source layer has no stable GPKG FID: {name}')
            qname = '"'+name.replace('"','""')+'"'
            qfid = '"'+fid.replace('"','""')+'"'
            minimum, maximum, count = src.execute(f'SELECT MIN({qfid}),MAX({qfid}),COUNT(*) FROM {qname}').fetchone()
            if minimum is not None and minimum < 0: raise ValueError('negative source FID')
            con.execute('INSERT INTO source_layers VALUES (?,?,?,?)',(name,fid,offset,count))
            con.executemany('INSERT INTO feature_provenance VALUES (?,?,?)',
                ((int(row[0])+offset,name,int(row[0])) for row in src.execute(f'SELECT {qfid} FROM {qname}')))
            node = ET.SubElement(root,'OGRVRTLayer',name=name)
            ET.SubElement(node,'SrcDataSource',relativeToVRT='0',shared='1').text = str(original_source)
            ET.SubElement(node,'SrcSQL',dialect='SQLite').text = f'SELECT {qfid}+{offset} AS __experiment_id, * FROM {qname}'
            ET.SubElement(node,'FID').text = '__experiment_id'
            # Explicit fields prevent the generated ID from entering the attribute schema.
            definition = layer.GetLayerDefn()
            for i in range(definition.GetFieldCount()):
                field = definition.GetFieldDefn(i)
                ET.SubElement(node,'Field',name=field.GetName(),src=field.GetName(),type=field.GetTypeName())
            offset += int(maximum or 0)+1
        con.execute('CREATE INDEX provenance_layer ON feature_provenance(source_layer,source_fid)')
    con.close();src.close()
    temporary.replace(lookup)
    # Docker Desktop Windows bind mounts can briefly retain a negative dentry
    # after a host-visible atomic rename; require the final path to be readable.
    for attempt in range(100):
        try:
            with lookup.open('rb') as handle:handle.read(16)
            break
        except FileNotFoundError:
            if attempt==99:raise
            time.sleep(.1)
    ET.ElementTree(root).write(vrt_path,encoding='utf-8',xml_declaration=True)
    # Materialize only FID remapping: VRT/SQL disables GDAL's fast GPKG reader
    # on some layers. Geometry BLOBs and attribute cells remain byte-for-byte
    # unchanged in this disposable derived copy.
    derived=output/(artifact_stem+'.provenance.gpkg')
    partial=derived.with_suffix('.gpkg.partial')
    shutil.copy2(source,partial)
    with sqlite3.connect(partial) as target, sqlite3.connect(lookup) as ids:
        triggers=target.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'").fetchall()
        for name,_ in triggers:target.execute('DROP TRIGGER "'+name.replace('"','""')+'"')
        for name,fid,offset,_ in ids.execute('SELECT * FROM source_layers'):
            if not offset:continue
            qname='"'+name.replace('"','""')+'"';qfid='"'+fid.replace('"','""')+'"'
            target.execute(f'UPDATE {qname} SET {qfid}=-{qfid}-1')
            target.execute(f'UPDATE {qname} SET {qfid}=-{qfid}-1+?',(offset,))
            for geometry, in target.execute('SELECT column_name FROM gpkg_geometry_columns WHERE table_name=?',(name,)).fetchall():
                index='rtree_'+name+'_'+geometry
                if target.execute('SELECT 1 FROM sqlite_master WHERE name=?',(index,)).fetchone():
                    quoted='"'+index.replace('"','""')+'"'
                    target.execute(f'UPDATE {quoted} SET id=-id-1')
                    target.execute(f'UPDATE {quoted} SET id=-id-1+?',(offset,))
        for _,sql in triggers:target.execute(sql)
        # Exhaustive cell equality, keyed through the sidecar mapping.
        target.execute('ATTACH DATABASE ? AS original',(str(source),))
        for name,fid,offset,_ in ids.execute('SELECT * FROM source_layers'):
            qname='"'+name.replace('"','""')+'"';qfid='"'+fid.replace('"','""')+'"'
            columns=[r[1] for r in target.execute(f'PRAGMA table_info({qname})') if r[1]!=fid]
            differences=' OR '.join('s."'+c.replace('"','""')+'" IS NOT d."'+c.replace('"','""')+'"' for c in columns)
            count=target.execute(f'SELECT COUNT(*) FROM original.{qname} s LEFT JOIN main.{qname} d ON d.{qfid}=s.{qfid}+? WHERE d.{qfid} IS NULL OR ({differences})',(offset,)).fetchone()[0]
            if count:raise ValueError(f'Provenance materialization changed geometry/attributes in {name}: {count} rows')
    target.close();ids.close()
    partial.replace(derived)
    for attempt in range(100):
        if derived.exists():break
        time.sleep(.1)
    for artifact in (vrt_path,lookup,derived):
        staged=release_output/(artifact.name+'.partial')
        shutil.copyfile(artifact,staged)
        staged.replace(release_output/artifact.name)
    return derived, release_output/lookup.name
