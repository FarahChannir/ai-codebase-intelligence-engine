from LibraryCore.ingestion import ingest

records = ingest(
    source=r"C:\Kabbani\boardgames",
    source_type="folder"
)

print(f"total records: {len(records)}")
for r in records[:5]:
    print(r)