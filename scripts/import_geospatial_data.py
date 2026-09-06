#!/usr/bin/env python3
"""Import the World EEZ v12 GeoPackage into Supabase/PostGIS.

Fresh replacement for ORCA's geospatial importer.
- Reads the GeoPackage with sqlite3 (no Fiona/GDAL dependency).
- Introspects the actual EEZ layer schema instead of assuming metadata column names.
- Uses PostGIS objects/functions from the gis schema, matching Supabase's setup.
- Imports Polygon/MultiPolygon features into gis.eez_boundaries.
- Safe to rerun: the target table is recreated each run.
"""

from __future__ import annotations

import os
import sqlite3
import struct
import sys
from pathlib import Path
from typing import Any

import psycopg2
from dotenv import load_dotenv
from shapely import wkb
from shapely.geometry import MultiPolygon, Polygon

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPOSITORY_ROOT / ".env")

EEZ_PATH = Path(os.getenv(
    "POSTGIS_EEZ_DATASET_PATH",
    str(REPOSITORY_ROOT / "data" / "geospatial" / "World_EEZ_v12_20231025_gpkg" / "eez_v12.gpkg"),
))
EEZ_LAYER = os.getenv("POSTGIS_EEZ_LAYER", "eez_v12")
TARGET_SCHEMA = os.getenv("POSTGIS_EEZ_SCHEMA", "gis")
TARGET_TABLE = os.getenv("POSTGIS_EEZ_TABLE", "eez_boundaries")
DATABASE_URL = os.getenv("DATABASE_URL")


def quote_ident(value: str) -> str:
    if not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return f'"{value}"'


def decode_gpkg_geometry(blob: bytes):
    """Decode a GeoPackage geometry BLOB to Shapely, stripping the GP header."""
    if not blob:
        raise ValueError("Empty geometry BLOB")

    # GeoPackageBinary header: magic GP + version + flags + optional envelope + srs_id.
    if blob[:2] != b"GP":
        # Accept plain WKB as a fallback.
        return wkb.loads(blob)

    if len(blob) < 8:
        raise ValueError("Invalid GeoPackage geometry header")

    flags = blob[3]
    envelope_indicator = (flags >> 1) & 0b111
    header_len = 8
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    if envelope_indicator not in envelope_sizes:
        raise ValueError(f"Unsupported GeoPackage envelope indicator: {envelope_indicator}")
    header_len += envelope_sizes[envelope_indicator]
    return wkb.loads(blob[header_len:])


def inspect_layer(conn: sqlite3.Connection) -> tuple[list[str], int, str]:
    tables = [row[0] for row in conn.execute(
        "SELECT table_name FROM gpkg_contents WHERE data_type='features'"
    )]
    if EEZ_LAYER not in tables:
        raise RuntimeError(f"Layer {EEZ_LAYER!r} not found. Feature layers: {tables}")

    columns = [row[1] for row in conn.execute(f"PRAGMA table_info({quote_ident(EEZ_LAYER)})")]
    if not columns:
        raise RuntimeError(f"Layer {EEZ_LAYER!r} has no columns")

    geom_row = conn.execute(
        "SELECT column_name, geometry_type_name, srs_id "
        "FROM gpkg_geometry_columns WHERE table_name=?",
        (EEZ_LAYER,),
    ).fetchone()
    if not geom_row:
        raise RuntimeError(f"No GeoPackage geometry metadata found for {EEZ_LAYER!r}")

    geom_column, geometry_type, srid = geom_row
    if srid != 4326:
        raise RuntimeError(f"Expected EPSG:4326, found EPSG:{srid}")
    if geometry_type.upper() not in {"POLYGON", "MULTIPOLYGON"}:
        raise RuntimeError(f"Expected polygon geometry, found {geometry_type}")

    count = conn.execute(f"SELECT COUNT(*) FROM {quote_ident(EEZ_LAYER)}").fetchone()[0]
    return columns, count, geom_column


def choose_column(columns: list[str], candidates: list[str]) -> str | None:
    lower = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in lower:
            return lower[candidate.lower()]
    return None


def read_features(conn: sqlite3.Connection, columns: list[str], geom_column: str):
    fid_col = choose_column(columns, ["fid", "id", "MRGID"])
    if fid_col is None:
        raise RuntimeError("Could not find a source feature id column (expected fid, id, or MRGID)")

    # World EEZ versions use different metadata field names. We discover what this
    # particular file actually contains and preserve whichever fields are present.
    name_col = choose_column(columns, ["EEZ", "GEONAME", "NAME", "EEZ_NAME", "TERRITORY1"])
    sovereign_col = choose_column(columns, ["SOVEREIGN", "SOVEREIGN1", "SOVEREIGNTY"])
    mrgid_col = choose_column(columns, ["MRGID_EEZ", "MRGID"])

    selected = [fid_col, geom_column]
    for col in (name_col, sovereign_col, mrgid_col):
        if col and col not in selected:
            selected.append(col)

    sql = f"SELECT {', '.join(quote_ident(c) for c in selected)} FROM {quote_ident(EEZ_LAYER)}"
    index = {col: i for i, col in enumerate(selected)}

    for row in conn.execute(sql):
        fid = row[index[fid_col]]
        geom_blob = row[index[geom_column]]
        shape = decode_gpkg_geometry(geom_blob)
        if not isinstance(shape, (Polygon, MultiPolygon)):
            raise RuntimeError(f"Feature {fid} is {shape.geom_type}, not Polygon/MultiPolygon")
        if isinstance(shape, Polygon):
            shape = MultiPolygon([shape])

        yield {
            "source_fid": int(fid) if fid is not None else None,
            "mrgid_eez": row[index[mrgid_col]] if mrgid_col else None,
            "eez_name": row[index[name_col]] if name_col else None,
            "sovereign": row[index[sovereign_col]] if sovereign_col else None,
            "geom_wkb": shape.wkb,
        }

    print("Source metadata mapping:")
    print(f"  id       = {fid_col}")
    print(f"  name     = {name_col or 'not present'}")
    print(f"  sovereign= {sovereign_col or 'not present'}")
    print(f"  mrgid    = {mrgid_col or 'not present'}")


def create_target_table(pg):
    with pg.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(TARGET_SCHEMA)}")
        cur.execute(f"DROP TABLE IF EXISTS {quote_ident(TARGET_SCHEMA)}.{quote_ident(TARGET_TABLE)} CASCADE")
        cur.execute(f"""
            CREATE TABLE {quote_ident(TARGET_SCHEMA)}.{quote_ident(TARGET_TABLE)} (
                id BIGSERIAL PRIMARY KEY,
                source_fid BIGINT NOT NULL,
                mrgid_eez BIGINT,
                eez_name TEXT,
                sovereign TEXT,
                geom gis.geometry(MultiPolygon, 4326) NOT NULL,
                source TEXT NOT NULL,
                dataset_version TEXT NOT NULL
            )
        """)
        cur.execute(f"""
            CREATE INDEX {quote_ident(TARGET_TABLE + '_geom_gix')}
            ON {quote_ident(TARGET_SCHEMA)}.{quote_ident(TARGET_TABLE)}
            USING GIST (geom)
        """)
        cur.execute(f"""
            CREATE INDEX {quote_ident(TARGET_TABLE + '_mrgid_idx')}
            ON {quote_ident(TARGET_SCHEMA)}.{quote_ident(TARGET_TABLE)} (mrgid_eez)
        """)
    pg.commit()
    print(f"Created {TARGET_SCHEMA}.{TARGET_TABLE} with GiST spatial index.")


def insert_features(pg, features: list[dict[str, Any]]):
    sql = f"""
        INSERT INTO {quote_ident(TARGET_SCHEMA)}.{quote_ident(TARGET_TABLE)}
            (source_fid, mrgid_eez, eez_name, sovereign, geom, source, dataset_version)
        VALUES (
            %s, %s, %s,
            %s,
            gis.ST_Multi(gis.ST_SetSRID(gis.ST_GeomFromWKB(%s), 4326)),
            %s, %s
        )
    """
    with pg.cursor() as cur:
        for feature in features:
            cur.execute(sql, (
                feature["source_fid"], feature["mrgid_eez"], feature["eez_name"],
                feature["sovereign"], psycopg2.Binary(feature["geom_wkb"]),
                "Marine Regions World EEZ v12", "v12",
            ))
    pg.commit()


def validate_target(pg, expected_count: int):
    table = f"{quote_ident(TARGET_SCHEMA)}.{quote_ident(TARGET_TABLE)}"
    with pg.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE gis.ST_SRID(geom)=4326")
        srid_count = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE gis.ST_GeometryType(geom) <> 'ST_MultiPolygon'")
        bad_type = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE NOT gis.ST_IsValid(geom)")
        invalid = cur.fetchone()[0]

    if count != expected_count:
        raise RuntimeError(f"Imported feature count {count} != source count {expected_count}")
    if srid_count != count:
        raise RuntimeError(f"Only {srid_count}/{count} geometries have SRID 4326")
    if bad_type:
        raise RuntimeError(f"Found {bad_type} non-MultiPolygon geometries")
    if invalid:
        raise RuntimeError(f"Found {invalid} invalid geometries")

    print(f"Imported features: {count}")
    print(f"Validation: {count} valid MultiPolygon geometries in EPSG:4326.")


def main() -> int:
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL is not configured")
        return 1
    if not EEZ_PATH.exists():
        print(f"ERROR: EEZ dataset not found: {EEZ_PATH}")
        return 1

    print(f"EEZ dataset: {EEZ_PATH}")
    print(f"GeoPackage layer: {EEZ_LAYER}")
    print(f"Target table: {TARGET_SCHEMA}.{TARGET_TABLE}")

    try:
        with sqlite3.connect(EEZ_PATH) as src:
            columns, source_count, geom_column = inspect_layer(src)
            print(f"Source features: {source_count}")
            geom_meta = src.execute(
                "SELECT geometry_type_name FROM gpkg_geometry_columns WHERE table_name=?",
                (EEZ_LAYER,),
            ).fetchone()[0]
            print(f"Source geometry: {geom_meta}")
            print("Actual columns:")
            print("  " + ", ".join(columns))

            features = list(read_features(src, columns, geom_column))

        pg = psycopg2.connect(DATABASE_URL)
        try:
            with pg.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname='postgis'")
                if not cur.fetchone():
                    raise RuntimeError("PostGIS extension is not installed")
            print("PostGIS: available")
            create_target_table(pg)
            insert_features(pg, features)
            validate_target(pg, source_count)
        finally:
            pg.close()

        print("EEZ import completed successfully.")
        return 0
    except Exception as exc:
        print(f"ERROR: EEZ import failed: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
