# Document Parser tool

A tool that parses document from PDF or images using a DeepSeek OCR (or compatible) Server. 

## What the tool can do

**Inputs**

```
Local file path (PDF / image)
URL (downloads bytes first)
```

**Server interaction**

```
Calls an OCR server endpoint and parses the OCRResponse schema (sections, tables, metadata)
```

**Outputs**

- Returns a structured Python dict with:
```
doc_id
markdown (concatenated sections)
sections (name + text)
tables
metadata
```

- Optionally saves artifacts to output_dir:

```
{doc_id}.md (markdown)
{doc_id}.json (full response)
```