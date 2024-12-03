# photo_processing.py

import os
from PIL import Image
from werkzeug.utils import secure_filename
import logging

# Configure logging for this module
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'png'}
MAX_IMAGE_SIZE = (500, 500)  # Width, Height in pixels


def allowed_file(filename):
    """
    Check if the file has an allowed extension.
    """
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def process_and_save_image(file, save_directory, question_number):
    """
    Validate, resize, and save the uploaded image.

    Parameters:
    - file: The uploaded file object from Flask.
    - save_directory: Directory where the image will be saved.
    - question_number: The current question number for naming the image.

    Returns:
    - The filename of the saved image if successful.
    - None if no image was uploaded.

    Raises:
    - ValueError: If the file is invalid or processing fails.
    """
    if not allowed_file(file.filename):
        logger.debug("File type not allowed.")
        raise ValueError("Invalid file type. Only PNG images are allowed.")

    filename = secure_filename(file.filename)
    photo_filename = f"question_{question_number}_photo.png"
    photo_path = os.path.join(save_directory, photo_filename)

    try:
        # Save the uploaded file temporarily
        temp_path = os.path.join(save_directory, f"temp_{filename}")
        file.save(temp_path)
        logger.debug(f"Temporary file saved to {temp_path}")

        # Open and process the image
        with Image.open(temp_path) as img:
            img = img.convert('RGBA')
            img = img.resize(MAX_IMAGE_SIZE, Image.LANCZOS)
            img.save(photo_path)
            logger.debug(f"Image resized and saved to {photo_path}")

        # Remove the temporary file
        os.remove(temp_path)
        logger.debug(f"Temporary file {temp_path} removed.")

        return photo_filename

    except Exception as e:
        logger.error(f"Error processing image: {e}")
        # Clean up any saved files in case of error
        if os.path.exists(photo_path):
            os.remove(photo_path)
            logger.debug(f"Corrupted image file {photo_path} removed.")
        if os.path.exists(temp_path):
            os.remove(temp_path)
            logger.debug(f"Temporary file {temp_path} removed.")
        raise ValueError("Error processing image.")
