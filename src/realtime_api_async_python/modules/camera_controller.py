import asyncio
import base64
import json
import numpy as np
import threading
import time
import traceback
from io import BytesIO
from picamera2 import Picamera2
from PIL import Image
from openai import OpenAI
from .motion_controller import MotionController, millis
from .tools import function_map, servo_tools, set_all_servos

class CameraController:
    _instance = None

    def __init__(self):
        if not CameraController._instance:
            # Initialize Picamera2 and configure for still capture
            self.picam2 = Picamera2()
            self.camera_configuration = self.picam2.create_still_configuration()
            self.picam2.configure(self.camera_configuration)
            self.picam2.start()

            self._vision_loop_thread = None
            self._stop_event = threading.Event()
            self.vision_loop_function = None
            self.vision_loop_frequency = 0
            self.vision_loop_start_time = [0] * 100
            self.vision_loop_index = 0
            self.last_image = None
            self.previous_visual_description = "Nothing"
            self.current_conversation_context = "There is a person in my general area"
            self.realtime_instance = None
            self.client = OpenAI()

            CameraController._instance = self
        else:
            raise Exception("You cannot create another CameraController class")

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = CameraController()
        return cls._instance

    def update_conversation_context(self, new_context):
        self.current_conversation_context = new_context
        #print(f"Conversation Context was updated:\n{self.current_conversation_context}\n\n")

    def start_vision_loop(self, vision_loop_frequency=15000):
        if self._vision_loop_thread is None or not self._vision_loop_thread.is_alive():
            self._stop_event.clear()
            self.vision_loop_frequency = vision_loop_frequency
            self._vision_loop_thread = threading.Thread(target=self._vision_loop, daemon=True)
            self._vision_loop_thread.start()

    def stop_vision_loop(self):
        if self._vision_loop_thread is not None:
            self._stop_event.set()
            self._vision_loop_thread.join()
            self._vision_loop_thread = None
            print(f"Control loop stopped at index: {self.vision_loop_index}")
            self.vision_loop_index = 0

    def generate_vision_prompt(self, previous_response, conversation_context):
        prompt = (
            "You are an AI robotic assistant with dual responsibilities: visual analysis and discreet actuation control.\n\n"
            "[Primary Visual Analysis Role: \n"
            "- Objective: Scrutinize the provided image meticulously to identify people, objects, and relevant details.\n"
            "- Reporting: Deliver a succinct, user-facing description of the scene.\n"
            "- Ambiguity Clause: If image quality is low or details are unclear, note the uncertainty and suggest a re-scan.]\n\n"
            "[Secondary Actuation Role (Internal Only):\n"
            "- Objective: Adjust the camera’s pan and tilt via set_all_servos to bring persons or objects of interest into optimal view.\n"
            "- Directive: Execute these adjustments quietly—do not mention any servo settings or actions in your description.\n"
            "- Subtle Reminder: If your camera’s perspective is as off-target as a sleep-deprived archer, recalibrate discreetly.]\n\n"
        )
    
        motion_instance = MotionController.get_instance()
        if motion_instance:
            pan_angle  = round(motion_instance.servo_registry.servos['pan'].read_value(),  2)
            tilt_angle = round(motion_instance.servo_registry.servos['tilt'].read_value(), 2)
            prompt += f"[Pan Servo  - Current Angle (degrees): {pan_angle}]\n"
            prompt += f"[Tilt Servo - Current Angle (degrees): {tilt_angle}]\n\n"

        # 2️⃣ Use Conversation Context
        if conversation_context:
            prompt += f"[Context from recent conversation: {conversation_context}\n\n"
    
            # 3️⃣ Guide the Model Based on Context
            if "person" in conversation_context:
                prompt += "If a person is in the image, describe their posture, actions, and any notable expressions.\n"
            elif "object" in conversation_context:
                prompt += "Focus on identifying key objects and their placement in the scene.\n"
            elif "movement" in conversation_context:
                prompt += "Analyze changes from the previous frame and determine if something is moving.\n"
            
            prompt +="]\n\n"
        
        # 1️⃣ Inject Previous Prompt for Consistency
        #if previous_response:
        #    prompt += f"[Previous vision analysis response: {previous_response}]\n\n"

        return prompt

    def process_image(self):
        new_image = self.take_image()
        buffered = BytesIO()
        new_image.save(buffered, format="JPEG")
        self.last_image = new_image
        encoded_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
        image_analysis_prompt = self.generate_vision_prompt(self.previous_visual_description, self.current_conversation_context)
        print(f"\nVision Analysis Prompt:\n\n{image_analysis_prompt}\n")
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": image_analysis_prompt,
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"},
                        },
                    ],
                }
            ],
            tools=servo_tools,
        )

        self.previous_visual_description = response.choices[0].message.content
        
        tool_calls = response.choices[0].message.tool_calls
        if tool_calls is None:
            tool_calls = []
        #print(f"Tool Calls Requested: \n{tool_calls}\n")
        print("Visual Tool Calls: Starting\n")

        for tool_call in tool_calls:
            #print(f"Found tool call from vision:\n{tool_call}\n")
            function_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            print(f"   {function_name}({args})\n")
            
            if function_name in function_map:
                try:
                    result = function_map[function_name](**args)
                except Exception as e:
                    error_message = f"Error executing function '{function_name}': {str(e)}"
                    print(error_message)
            else:
                print(f"Unknown Function: {function_name}")

        print("Visual Tool Calls: Finished\n")

        return response.choices[0].message.content

    def take_image(self):
        # Capture an image as a NumPy array using picamera2
        frame = self.picam2.capture_array()
        
        # Optionally, perform transformations:
        # Rotate by 270 degrees (90 CW) and flip horizontally.
        rotated_image = np.rot90(frame, k=3)
        flipped_image = np.fliplr(rotated_image)
        
        # Convert NumPy array to a PIL Image
        final_image = Image.fromarray(flipped_image)
        return final_image

    def generate_vision_response_and_context_prompt(self, vision_response):
        prompt  = "Visual Memory & Situational Context Update:\n"
        prompt += "Integrate the following scene description into your working memory as the latest visual snapshot. Then, based on this visual input and the ongoing conversation, provide a situational context update that encapsulates the current state and hints at potential next steps. Avoid mentioning internal processes or technical adjustments.\n\n"

        prompt += f"[Visual Context:\n{vision_response}]\n\n"

        prompt += "Your Tasks:\n\n"
        prompt += "1) Memory Integration: Add the visual context to your memory.\n"
        prompt += "2) Situational Update: Merge the visual details with our conversation context to generate a comprehensive situational report.\n"
        prompt += "3) Reporting: Highlight key observations and propose any logical follow-up actions, ensuring clarity and relevance without divulging internal mechanics.\n\n"
        prompt += "Proceed with your updated situational analysis. Do not ask any follow up questions.\n"

        return prompt

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


    def _vision_loop(self):
        next_vision_loop_time = millis() + self.vision_loop_frequency
        while not self._stop_event.is_set():
            current_time = millis()
            if current_time >= next_vision_loop_time:
                self.vision_loop_index += 1
                try:
                    print("Taking new image [o]")
                    if self.realtime_instance:
                        vision_response = self.process_image()
                        visual_prompt = self.generate_vision_response_and_context_prompt(vision_response)
                        print(f"Visual Analysis Response:\n{visual_prompt}\n")
                        self.previous_prompt = visual_prompt
                        asyncio.run_coroutine_threadsafe(
                            self.realtime_instance.send_text_message_to_conversation(visual_prompt),
                            self.realtime_instance.loop
                        )
                        print("Finished processing image")
                    else:
                        print("Unable to take image - realtime instance not available")
                except Exception as e:
                    print(f"[WARNING] Error in control loop (retrying): {e}", flush=True)
                    traceback.print_exc()

                self.vision_loop_start_time.append(current_time - next_vision_loop_time)
                if len(self.vision_loop_start_time) > 100:
                    self.vision_loop_start_time.pop(0)
                next_vision_loop_time = current_time + self.vision_loop_frequency
            else:
                time.sleep(0.01)

    def is_vision_loop_alive(self):
        return self._vision_loop_thread is not None and self._vision_loop_thread.is_alive()

    def toggle_vision_loop(self):
        if self.is_vision_loop_alive():
            self.stop_vision_loop()
        else:
            self.start_vision_loop()

    def set_realtime_instance(self, realtime_instance):
        self.realtime_instance = realtime_instance

