# Foundation Batch B: F7O Obsidian and Personal Digital Map

## Status

`PILOT_VALIDATED_SEPARATE_FROM_OBSIDIAN_APP`.

Golden already has two local, non-cloud knowledge surfaces:

1. `GoldenMemoryEngine` projects approved PUBLIC/INTERNAL V2 records to the
   SQLite-first vault at `C:\GoldenAI\memory\vault`.
2. `jarvis_core.context_index` builds deterministic project/context indexes in
   the older `C:\GoldenAI\vault\Segundo Cerebro` layout.

Neither surface requires the Obsidian application, and no Obsidian connector,
full-PC scanner, or bidirectional sync was found. The two vault roots must not
be silently merged in a future gate.

## Role and authority

- Obsidian role: human-visible memory interface and optional local projection.
- Obsidian canonical: `NO`.
- Canonical source: V2 SQLite records, provenance, privacy, versions and
  graph state.
- Sync direction: `Jarvis -> approved local vault`.
- Human edits: classify as drift/conflict; do not import automatically.
- Cloud upload: prohibited by this design.

## Personal digital map design

### Scan policy

No scan runs by default. A later pilot must receive an explicit allowlist of
roots and file classes, operate incrementally, enforce a bounded budget, and
write only an index/manifest under an approved local destination. Full-PC
scans, registry modification, application crawling and hidden/background
collection are out of scope.

### Secret exclusion

Exclude `.env*`, credential/key/token material, private keys, browser profiles,
cookies, auth stores, runtime databases, logs, caches, build artifacts and
anything classified SECRET/SENSITIVE. Apply the canonical security/redaction
policy before indexing names, paths or content. Never upload excluded data.

### Identity and incremental indexing

Use a stable file identity composed of normalized approved-root-relative path,
size, modification time and content hash when content is explicitly allowed.
Persist a manifest of identity, policy decision and last scan result. Reuse
unchanged entries and mark moved/deleted entries; do not duplicate by filename
alone.

### Content and media policy

- Documents: metadata-only by default; bounded UTF-8 extraction only for an
  explicit text allowlist, with secret scanning and provenance.
- Photos: metadata-only in the pilot; no OCR, face recognition, thumbnails or
  cloud transfer without a separate consent gate.
- Programs: read-only inventory of explicitly approved application roots or
  known-folder metadata; no registry writes, installation or execution.

## Pilot boundary

The safe future pilot is limited to projecting existing V2 PUBLIC/INTERNAL
memory and project indexes into one explicitly selected local vault, plus a
manifest/idempotency check. It must not scan personal folders, import human
notes, alter original user files, open applications, access microphone/camera,
or contact a cloud service.

The F7.3 boundary now gives the pilot an explicit owner: V2 SQLite remains
canonical and the Markdown vault is a one-way projection. The pilot is still
temporary/test-owned; it does not open the Obsidian application, scan personal
folders or modify the real user vault.

## Validation evidence

- Existing context-index and V2 vault tests are the relevant regression
  coverage. They exercise PUBLIC/INTERNAL projection, SECRET/SENSITIVE
  exclusion, relation wikilinks, managed-note separation, drift detection,
  rebuild, invalid/unavailable vault degradation and SQLite preservation.
- The pilot uses temporary vault/database roots only and verifies that
  projection failures remain isolated from canonical SQLite writes.
- No full-PC scan, Obsidian process interaction, user-file modification,
  cloud upload, database migration, or new dependency was performed.

```yaml
PILOT_VAULT: TEMPORARY_TEST_ROOT
PROJECTION_OWNER: GoldenMemoryEngine_V2
SYNC_DIRECTION: JARVIS_TO_APPROVED_LOCAL_VAULT
OBSIDIAN_CANONICAL: NO
OBSIDIAN_REQUIRED: NO
EXPORTED_CLASSIFICATIONS: PUBLIC,INTERNAL
SECRET_EXCLUSION: PASS
GENERATED_USER_CONTENT_SEPARATION: PASS
LINKS: PASS
FAILURE_ISOLATION: PASS
FULL_PC_SCAN: NO
REAL_USER_FILES_MODIFIED: NO
```
