from core.ingestion import ingest

records = ingest(
    source=r"Path\to\your\folder",
    source_type="folder"
)

print(f"total records: {len(records)}")
for r in records[:5]:
    print(r)