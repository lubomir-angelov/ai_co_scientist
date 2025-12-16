def is_jpeg(data: bytes) -> bool:
    jpeg_signature = b"\xFF\xD8\xFF"
    return data.startswith(jpeg_signature)

def is_png(data: bytes) -> bool:
    png_signature = b"\x89\x50\x4E\x47\x0D\x0A\x1A\x0A"
    return data.startswith(png_signature)

def is_pdf(data: bytes) -> bool:
    # PDF files start with: %PDF-
    return data.startswith(b"%PDF-")

def get_image_type_from_bytes(data: bytes) -> str:
    if is_jpeg(data):
        return "jpeg"
    elif is_png(data):
        return "png"
    else:
        raise ValueError("Image type not supported, only jpeg and png supported.")

def get_file_type_from_bytes(data: bytes) -> str:
    if is_pdf(data):
        return "pdf"
    if is_jpeg(data):
        return "jpeg"
    if is_png(data):
        return "png"
    raise ValueError("File type not supported, only pdf, jpeg and png supported.")
