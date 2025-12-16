
## Testing the Tools

To test the pdf parsing tool, follow these steps:

1. **Navigate to the Project Directory:**

   Change your current directory to where the tools are located. Replace `your_path` with the actual path to your project directory.

   ```sh
   cd your_path/ai_co_scientist/services
   ```

2. **Run the Text Detection Tool:**

   ```sh
   cd octo_agent
   export PYTHONPATH=$(pwd)
   ```


   Execute the tool using the following command:

   ```sh
   python tools/pdf_parser/tool.py

   python tools/advanced_object_detector/tool.py

   ```

## File Structure

The project is organized as follows:

```sh
├── __init__.py                       # Initializes the tools package and possibly exposes submodules
├── base.py                           # Base class for tools, providing common functionality
├── pdf_parser/                       # Directory for the text detection tool
│   ├── readme.md                     # Documentation for the text detection tool
│   └── tool.py                       # Implementation of the text detection tool
├── advanced_object_detector/         # Directory for the object detection tool
│   ├── readme.md                     # Documentation for the object detection tool
│   └── tool.py                       # Implementation of the object detection tool
```