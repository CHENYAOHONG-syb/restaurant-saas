import os
import uuid
from werkzeug.utils import secure_filename

def save_image(file):

    if not file or file.filename == "":
        return ""

    filename = str(uuid.uuid4()) + "_" + secure_filename(file.filename)

    os.makedirs("static/uploads", exist_ok=True)

    path = "static/uploads/" + filename

    file.save(path)

    return path