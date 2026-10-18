"""Parquet tile measurements; DuckDB is a disposable SQL workspace, never a release file."""
from contextlib import closing
from decimal import Decimal
import json
from pathlib import Path
import re
import sqlite3

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def sql_types(sql):
    """Match SQLite's 64-bit integer/double storage, without row-store pragmas."""
    sql = re.sub(r'PRAGMA[^;]*;', '', sql, flags=re.I)
    sql = re.sub(r'\bWITHOUT ROWID\b|\bSTRICT\b|\bON DELETE CASCADE\b', '', sql, flags=re.I)
    sql = re.sub(r'\bINTEGER\b', 'BIGINT', sql, flags=re.I)
    return re.sub(r'\bREAL\b', 'DOUBLE', sql, flags=re.I)


class Connection:
    """Small cursor facade shared by the measurement writer and SQL readers."""

    def __init__(self, path=':memory:'):
        self.db = duckdb.connect(str(path))
        self.lastrowid = None
        self.schemas = {}

    @property
    def description(self):
        return self.db.description

    def execute(self, sql, params=()):
        generated = re.match(r'\s*INSERT INTO (maps|archives)\s*\(', sql, re.I)
        if generated:
            self.db.execute(sql+' RETURNING id', params)
            self.lastrowid = self.db.fetchone()[0]
            return self
        self.db.execute(sql, params)
        return self

    def executescript(self, sql):
        sql = sql_types(sql)
        for table in ('maps', 'archives', 'analysis_errors'):
            pattern = rf'(CREATE TABLE {table}\s*\(\s*id BIGINT PRIMARY KEY)'
            if re.search(pattern, sql, re.I):
                self.db.execute(f'CREATE SEQUENCE {table}_ids START 1')
                sql = re.sub(pattern, rf"\1 DEFAULT nextval('{table}_ids')", sql, flags=re.I)
        self.db.execute(sql)
        return self

    def executemany(self, sql, rows):
        # Arrow ingestion avoids millions of individual DuckDB INSERT statements.
        rows = list(rows)
        if not rows:
            return self
        match = re.fullmatch(r'\s*INSERT INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\([^;]+\)\s*', sql, re.I)
        if not match:
            self.db.executemany(sql, rows)
            return self
        table, columns = match.groups()
        names = [name.strip() for name in columns.split(',')]
        key = (table, tuple(names))
        if key not in self.schemas:
            self.schemas[key] = self.db.execute(f'SELECT {columns} FROM {quote(table)} LIMIT 0').to_arrow_table().schema
        schema = self.schemas[key]
        batch = pa.Table.from_arrays([pa.array([r[i] for r in rows], type=f.type)
                                      for i, f in enumerate(schema)], schema=schema)
        self.db.register('_insert_batch', batch)
        try:
            self.db.execute(f'INSERT INTO {quote(table)} ({columns}) SELECT * FROM _insert_batch')
        finally:
            self.db.unregister('_insert_batch')
        return self

    @staticmethod
    def _row(row):
        return None if row is None else tuple(float(v) if isinstance(v, Decimal) else v for v in row)

    def fetchone(self):
        return self._row(self.db.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self.db.fetchall()]

    def fetchmany(self, size=65536):
        return [self._row(row) for row in self.db.fetchmany(size)]

    def __iter__(self):
        while rows := self.fetchmany():
            yield from rows

    def commit(self):
        self.db.commit()

    def close(self):
        self.db.close()


def connect(directory):
    """Query Parquet directly; views refer to these files without importing their rows."""
    directory = Path(directory).resolve()
    if not (directory/'schema.json').is_file():
        raise FileNotFoundError(directory/'schema.json')
    con = Connection()
    try:
        for name in json.loads((directory/'schema.json').read_text()):
            if Path(name).name != name:
                raise ValueError(f'Invalid table name: {name}')
            file = directory/f'{name}.parquet'
            if not file.is_file():
                raise FileNotFoundError(file)
            con.execute(f'CREATE VIEW {quote(name)} AS SELECT * FROM read_parquet({literal(file)})')
        # Only views are needed: table DDL remains documentation of the measured schema.
        with sqlite3.connect(':memory:') as catalogue:
            catalogue.executescript((directory/'schema.sql').read_text())
            for (sql,) in catalogue.execute("SELECT sql FROM sqlite_master WHERE type='view' ORDER BY name"):
                con.executescript(sql)
        return con
    except BaseException:
        con.close()
        raise


def write(con, directory, schema_sql):
    """Write all tables including typed empty ones, with logical key metadata."""
    directory = Path(directory)
    directory.mkdir(parents=True)
    schemas = {}
    with closing(sqlite3.connect(':memory:')) as catalogue:
        catalogue.executescript(schema_sql)
        for (name,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name").fetchall():
            file = directory/f'{name}.parquet'
            fields = con.db.execute(f'SELECT * FROM {quote(name)} LIMIT 0').description
            # DuckDB accumulates integer SUMs in 128 bits. Store measured counts as
            # int64, raising on overflow instead of silently converting to float.
            columns_sql = ','.join(f'CAST({quote(c[0])} AS BIGINT) AS {quote(c[0])}' if str(c[1])=='HUGEINT' else quote(c[0]) for c in fields)
            con.execute(f'COPY (SELECT {columns_sql} FROM {quote(name)}) TO {literal(file)} (FORMAT PARQUET, COMPRESSION ZSTD)')
            pf = pq.ParquetFile(file)
            original = {row[1]:row for row in catalogue.execute(f'PRAGMA table_info({quote(name)})')}
            columns = []
            for field in pf.schema_arrow:
                row = original.get(field.name)
                columns.append(dict(name=field.name, sqlite_type=row[2] if row else '',
                                    parquet_type=str(field.type), nullable=not bool(row and row[3]),
                                    primary_key=bool(row and row[5])))
            schemas[name] = dict(rows=pf.metadata.num_rows, columns=columns)
    (directory/'schema.json').write_text(json.dumps(schemas, indent=2)+'\n', encoding='utf-8')
    (directory/'schema.sql').write_text(schema_sql, encoding='utf-8')
    return schemas


def logical_schema(con):
    """Portable schema catalogue (no build-time ID sequences or file paths)."""
    tables = con.execute("SELECT sql FROM duckdb_tables() WHERE schema_name='main' AND NOT internal ORDER BY table_name").fetchall()
    # DuckDB adds casts to arithmetic literals in its normalized view definitions.
    # Preserve the original, portable view SQL from the measurement implementation.
    from . import output_analysis_core as core
    with closing(sqlite3.connect(':memory:')) as catalogue:
        core._create_schema(catalogue)
        core._create_indexes_and_views(catalogue)
        original_views = [r[0] for r in catalogue.execute("SELECT sql FROM sqlite_master WHERE type='view' ORDER BY name")]
    indexes = [r[0] for r in con.execute("SELECT sql FROM duckdb_indexes() WHERE schema_name='main' ORDER BY index_name").fetchall()]
    return '\n\n'.join(re.sub(r"\s+DEFAULT\s*\(?nextval\('[^']+'\)\)?", '', r[0], flags=re.I) for r in tables)+'\n\n'+'\n'.join(indexes)+'\n\n'+';\n\n'.join(original_views)+';\n'


def import_sqlite(con, path, alias):
    """Import the smaller inventories without downloading a SQLite extension."""
    con.execute(f'CREATE SCHEMA {quote(alias)}')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)) as src:
        for (name,) in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
            fields = src.execute(f'PRAGMA table_info({quote(name)})').fetchall()
            types = []
            for row in fields:
                declared = row[2].upper()
                if 'INT' in declared or 'BOOL' in declared:
                    dtype = 'BIGINT'
                elif any(t in declared for t in ('REAL','FLOAT','DOUBLE')):
                    dtype = 'DOUBLE'
                elif 'BLOB' in declared:
                    dtype = 'BLOB'
                elif declared:
                    dtype = 'VARCHAR'
                else:
                    kinds = {r[0] for r in src.execute(f'SELECT DISTINCT typeof({quote(row[1])}) FROM {quote(name)}')} - {'null'}
                    dtype = 'BIGINT' if kinds == {'integer'} else 'DOUBLE' if kinds and kinds <= {'integer','real'} else 'BLOB' if kinds == {'blob'} else 'VARCHAR'
                types.append(dtype)
            decl = ','.join(f'{quote(r[1])} {t}' for r,t in zip(fields,types))
            con.execute(f'CREATE TABLE {quote(alias)}.{quote(name)} ({decl})')
            cur = src.execute(f'SELECT * FROM {quote(name)}')
            while rows := cur.fetchmany(65536):
                # Source inventories have declared SQLite affinities.
                schema = con.db.execute(f'SELECT * FROM {quote(alias)}.{quote(name)} LIMIT 0').to_arrow_table().schema
                batch = pa.Table.from_arrays([pa.array([r[i] for r in rows], type=f.type) for i,f in enumerate(schema)], schema=schema)
                con.db.register('_sqlite_batch', batch)
                try:
                    con.execute(f'INSERT INTO {quote(alias)}.{quote(name)} SELECT * FROM _sqlite_batch')
                finally:
                    con.db.unregister('_sqlite_batch')


def export_sqlite(con, target):
    """Materialize only derived results for readers that need a single SQLite file."""
    with closing(sqlite3.connect(target)) as dst, dst:
        for (name,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name").fetchall():
            cur = con.execute(f'SELECT * FROM {quote(name)}')
            names = [c[0] for c in cur.description]
            # Explicit affinities also preserve types for empty result tables.
            types = [str(c[1]) for c in cur.description]
            declarations = [f'{quote(n)} '+('INTEGER' if 'INT' in t or t=='BOOLEAN' else 'REAL' if any(k in t for k in ('FLOAT','DOUBLE','DECIMAL')) else 'BLOB' if t=='BLOB' else 'TEXT') for n,t in zip(names,types)]
            dst.execute(f'CREATE TABLE {quote(name)} ({",".join(declarations)})')
            while rows := cur.fetchmany():
                dst.executemany(f'INSERT INTO {quote(name)} VALUES ({",".join("?" for _ in names)})', rows)
