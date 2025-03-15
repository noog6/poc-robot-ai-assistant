import numpy as np
from picamera2 import Picamera2
from PIL import Image

class CameraController:
    _instance = None

    def __init__(self):
        if not CameraController._instance:
            # Initialize Picamera2 and configure for still capture
            self.picam2                = Picamera2()
            self.camera_configuration  = self.picam2.create_still_configuration()
            self.picam2.configure(self.camera_configuration)
            self.picam2.start()
            self.last_image            = None

            CameraController._instance = self
        else:
            raise Exception("You cannot create another CameraController class")

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = CameraController()
        return cls._instance

    def take_image(self):
        # Capture an image as a NumPy array using picamera2
        frame = self.picam2.capture_array()
        
        # Optionally, perform transformations:
        # Rotate by 270 degrees (90 CW) and flip horizontally.
        rotated_image = np.rot90(frame, k=3)
        flipped_image = np.fliplr(rotated_image)
        
        # Convert NumPy array to a PIL Image
        self.last_image = Image.fromarray(flipped_image)
        return self.last_image

    def compare_images(self, img1, img2):
        """Compare two images and return a similarity percentage (0 to 100)."""
        # Load images if file paths are provided
        if isinstance(img1, str):
            img1 = Image.open(img1)
        if isinstance(img2, str):
            img2 = Image.open(img2)
        
        # Convert images to the same mode (e.g., RGB) to handle differences in channels
        img1 = img1.convert('RGB')
        img2 = img2.convert('RGB')
        
        # If sizes differ, optionally resize the second image to match the first
        if img1.size != img2.size:
            img2 = img2.resize(img1.size)
        
        # Convert images to NumPy arrays for fast computation
        arr1 = np.array(img1)
        arr2 = np.array(img2)
        
        # Ensure the arrays have the same shape (same width, height, channels)
        if arr1.shape != arr2.shape:
            raise ValueError("Images must have the same dimensions for comparison")
        
        # Compute the Mean Squared Error (MSE) between the image arrays
        diff = arr1.astype(np.float32) - arr2.astype(np.float32)
        mse = np.mean(np.square(diff))
        
        # Compute similarity percentage from MSE
        if mse == 0:
            similarity = 100.0  # images are identical
        else:
            max_mse = (255.0 ** 2)  # maximum MSE for 8-bit images
            similarity = (1 - mse / max_mse) * 100
            if similarity < 0:
                similarity = 0.0   # clamp lower bound
        return similarity

