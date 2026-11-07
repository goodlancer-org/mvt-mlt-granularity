//! Framed CLI adapter; all codec decisions belong to the pinned MapLibre core.
use std::io::{self, Read, Write};
use anyhow::{Result, bail};
use mlt_core::encoder::{EncoderConfig, Network, Profile, Tessellation, WireVersion};
use mlt_core::mvt::mvt_to_tile_layers_with_max_size;
use mlt_core::dump::{annotate_tile_with_max_size, RegionKind};
use mlt_core::wire::{LogicalEncoding, IntLogical, RleMeta};
use serde_json::{Value, json};
mod verify;

pub fn budget() -> u32 {
    std::env::var("MLT_DECODE_MEMORY_MIB").unwrap_or_else(|_| "256".into())
        .parse::<u32>().ok().filter(|v| (1..=4095).contains(v))
        .expect("MLT_DECODE_MEMORY_MIB must be 1..4095") * 1024 * 1024
}
fn frame(out: &mut impl Write, bytes: &[u8]) -> Result<()> {
    out.write_all(&u32::try_from(bytes.len())?.to_le_bytes())?;
    out.write_all(bytes)?;
    Ok(())
}
fn inspect(bytes: &[u8]) -> Result<Value> {
    let (tree, err) = annotate_tile_with_max_size(bytes, budget());
    if let Some(err) = err { bail!("MLT annotation: {err}") }
    let mut layers = Vec::<Value>::new();
    let mut streams = Vec::<Value>::new();
    let mut layer_idx = 0;
    let mut coverage = 0;
    for r in tree.regions {
        if r.container && r.label.starts_with("layer[") {
            layer_idx = layers.len();
            layers.push(json!({"label":r.label,"offset":r.offset,"frame_bytes":r.len}));
        }
        if !r.container {
            if r.offset != coverage { bail!("overlapping or incomplete annotation") }
            coverage += r.len;
            if r.kind == RegionKind::DataBlob {
                if let Some(blob) = r.blob {
                    let mut meta = serde_json::to_value(blob)?;
                    // v1 RLE counts encoded run words, v2 counts expanded values.
                    // Compare expanded logical cardinality across wire versions.
                    let count = match blob.meta.encoding.logical {
                        LogicalEncoding::Int(IntLogical::Rle(r) | IntLogical::DeltaRle(r)) => match r {
                            RleMeta::Split { num_rle_values, .. } | RleMeta::Interleaved { num_rle_values } => num_rle_values,
                        },
                        _ => meta["numValues"].as_u64().unwrap() as u32,
                    };
                    meta["logical_values"] = json!(count);
                    meta["layer"] = json!(layer_idx);
                    meta["offset"] = json!(r.offset);
                    meta["payload_bytes"] = json!(r.len);
                    meta["label"] = json!(r.label);
                    streams.push(meta);
                } else { bail!("unclassified MLT data region: {}", r.label) }
            }
        }
    }
    if coverage != bytes.len() { bail!("incomplete annotation") }
    Ok(json!({"layers":layers,"streams":streams}))
}
fn encode(raw: Vec<u8>) -> Result<(Value, Vec<Vec<u8>>)> {
    let source = mvt_to_tile_layers_with_max_size(raw, budget() as usize)?;
    let mut outputs = Vec::new();
    let mut stats = Vec::new();
    for version in [WireVersion::V01, WireVersion::V02] {
        let cfg = EncoderConfig::from_profile(Profile::Native(Network::Cellular4G))
            .with_wire_version(version).with_tessellation(Tessellation::Off)
            .with_spatial_morton_sort(false).with_spatial_hilbert_sort(false).with_id_sort(false)
            .with_fsst(true).with_fastpfor(true).with_shared_dict(true);
        let mut bytes = Vec::new();
        let mut differences = Vec::new();
        for layer in &source {
            let encoded = layer.clone().encode(cfg)?;
            if let Err(e) = verify::check_round_trip(layer, &encoded, Ok) {
                differences.push(format!("{e:#}"));
            }
            bytes.extend_from_slice(&encoded);
        }
        let mut stat = inspect(&bytes)?;
        stat["roundtrip_differences"] = json!(differences);
        stat["imported_layers"] = json!(source.iter().map(|l| json!({
            "name":l.name(), "extent":l.extent().get(), "features":l.feature_count(),
            "vertices":l.features().iter().map(|f| f.vertex_count()).sum::<usize>(),
            "property_names":l.property_names(),
            "property_kinds":l.property_kinds().iter().map(|k| format!("{k:?}")).collect::<Vec<_>>()
        })).collect::<Vec<_>>());
        stats.push(stat);
        outputs.push(bytes);
    }
    Ok((json!({"formats":stats}), outputs))
}
fn main() -> Result<()> {
    if std::env::args().any(|a| a == "--version") {
        println!("mlt-experiment 0.1.0; maplibre-tiles 0.4.1; mlt-core 0.22.1; source dd35bb6771b59006efd505afb102334e37e1af53b17e640d3a6438e917663aa3");
        return Ok(())
    }
    let mut input = io::stdin().lock();
    let mut output = io::BufWriter::new(io::stdout().lock());
    loop {
        let mut len = [0; 4];
        match input.read_exact(&mut len) {
            Ok(()) => (),
            Err(e) if e.kind() == io::ErrorKind::UnexpectedEof => break,
            Err(e) => return Err(e.into()),
        }
        let mut bytes = vec![0; u32::from_le_bytes(len) as usize];
        input.read_exact(&mut bytes)?;
        match encode(bytes) {
            Ok((stats, outputs)) => {
                frame(&mut output, &serde_json::to_vec(&stats)?)?;
                for bytes in outputs { frame(&mut output, &bytes)?; }
            }
            Err(e) => { frame(&mut output, &serde_json::to_vec(&json!({"error":format!("{e:#}")}))?)?; }
        }
        output.flush()?;
    }
    Ok(())
}
