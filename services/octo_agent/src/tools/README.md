
## Testing the Tools

To test the document parsing tool, follow these steps:

1. **Navigate to the Project Directory:**

   Change your current directory to where the tools are located. Replace `your_path` with the actual path to your project directory.

   ```sh
   cd your_path/ai_co_scientist/services
   ```

2. **Run the document parsing Tool:**

   ```sh
   cd octo_agent
   
   # Add the octo_agent source code to the PYTHONPATH 
   export PYTHONPATH="$(pwd)/src:$(pwd)/../common/src"
   ```


   Execute the tool using the following command:

   ```sh
   python -m tools.document_parser_ocr.tool
   ```

## File Structure

```sh
├── __init__.py
├── base.py                    # BaseTool: metadata + execute() contract
├── document_parser_ocr/       # Document_Parser_OCR_Tool -> OCR service
│   ├── README.md
│   └── tool.py
└── memory_graph/              # Memory_Graph_Tool -> memory service
    └── tool.py
```

The initializer discovers tools by directory name: class `Foo_Bar_Tool` lives in `foo_bar/tool.py`.
