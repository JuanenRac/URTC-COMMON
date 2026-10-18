// =============================================================================
// URTC-COMMON - tests/ts/run_vectors.mjs
// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
// GPL-3.0-or-later - see LICENSE
// =============================================================================
// Runs the shared conformance vectors against the generated TypeScript module and prints
// the list of vectors it does not reproduce as JSON. Needs a Node that strips types (22.18 or newer).
import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..');
const p = await import(pathToFileURL(path.join(root, 'generated', 'urtcCanIds.ts')).href);
const vectors = JSON.parse(readFileSync(path.join(root, 'conformance', 'can_vectors.json'), 'utf-8'));

const problems = [];
const hexToBytes = (hex) => (hex.match(/../g) ?? []).map((h) => Number.parseInt(h, 16));
const bytesToHex = (bytes) => bytes.map((b) => b.toString(16).padStart(2, '0')).join('').toUpperCase();
const typesOf = (layout) => Object.fromEntries(p.LAYOUTS[layout].fields.map((f) => [f.name, f.type]));

function callFields(layout, fields) {
  const types = typesOf(layout);
  return Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, types[k] === 'bytes' && v !== null ? hexToBytes(v) : v]));
}
function resultFields(layout, fields) {
  if (fields === null) return null;
  const types = typesOf(layout);
  return Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, types[k] === 'bytes' && v !== null ? bytesToHex(v) : v]));
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

for (const e of vectors.identifiers_all) {
  if (p[`CAN_ID_${e.name}`] !== Number.parseInt(e.id, 16)) problems.push(`identifiers_all: CAN_ID_${e.name}`);
}
if (vectors.identifiers_all.length !== Object.keys(p.MESSAGES).length) problems.push('identifiers_all: count differs from MESSAGES');
for (const e of vectors.magic_payloads) {
  if (bytesToHex(p[`MAGIC_${e.name.toUpperCase()}`] ?? []) !== e.data) problems.push(`magic_payloads: ${e.name}`);
}
for (const e of vectors.frames_encode) {
  try {
    const got = p.encode(e.layout, callFields(e.layout, e.fields));
    if (got.id !== Number.parseInt(e.frame.id, 16) || bytesToHex(got.data) !== e.frame.data) problems.push(`frames_encode: ${e.name}`);
  } catch (err) {
    problems.push(`frames_encode: ${e.name}: ${err}`);
  }
}
for (const e of vectors.frames_decode) {
  const got = resultFields(e.layout, p.decode(e.layout, hexToBytes(e.frame.data), Boolean(e.strict)));
  if (!same(got, e.fields)) problems.push(`frames_decode: ${e.name}: ${JSON.stringify(got)}`);
}
for (const e of vectors.frames_rejected) {
  let accepted = true;
  try {
    p.encode(e.layout, callFields(e.layout, e.fields));
  } catch {
    accepted = false;
  }
  if (accepted) problems.push(`frames_rejected: ${e.name}`);
}
for (const e of vectors.minor_field) {
  const got = e.bootloader_accepts_patch && e.patch !== null && e.patch >= 0 && e.patch <= p.PATCH_MAX ? p.minorFieldPack(e.minor, e.patch) : e.minor;
  if (got !== e.expect) problems.push(`minor_field: ${JSON.stringify(e)}`);
  if (e.expect > 255 && (p.minorFieldMinor(e.expect) !== e.minor || p.minorFieldPatch(e.expect) !== e.patch)) problems.push(`minor_field split: ${JSON.stringify(e)}`);
}
for (const e of vectors.version_order) {
  if (p.versionCompare(e.installed, e.candidate) !== e.expect) problems.push(`version_order: ${JSON.stringify(e)}`);
}
console.log(JSON.stringify({ checked: vectors.frames_encode.length + vectors.frames_decode.length + vectors.frames_rejected.length, problems }));
