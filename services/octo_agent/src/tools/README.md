
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
   export PYTHONPATH="$(pwd)/src"
   ```


   Execute the tool using the following command:

   ```sh
   python -m tools.document_parser_ocr.tool
   ```

## File Structure

The project is organized as follows:

```sh
├── __init__.py                       # Initializes the tools package and possibly exposes submodules
├── base.py                           # Base class for tools, providing common functionality
├── document_parser_ocr/              # Directory for the document parsing tool
│   ├── readme.md                     # Documentation for the document parsing tool
│   └── tool.py                       # Implementation of the document parsing tool
├── advanced_object_detector/         # Directory for the object detection tool
│   ├── readme.md                     # Documentation for the object detection tool
│   └── tool.py                       # Implementation of the object detection tool
```