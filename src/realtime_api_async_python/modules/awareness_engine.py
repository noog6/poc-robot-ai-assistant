import asyncio
import base64
import heapq
import json
import math
import threading
import time
import traceback
from io                 import BytesIO
from openai             import OpenAI
from .ads1015_sensor    import ADS1015Sensor
from .camera_controller import CameraController
from .motion_controller import MotionController, millis
from .tools             import function_map, servo_tools, set_all_servos

class AwarenessEngine():
    _instance = None

    def __init__(self):
        if self._instance is None:
            self.client                      = OpenAI()
            self.realtime_instance           = None
            self._control_loop_thread        = None
            self._stop_event                 = threading.Event()
            self.control_loop_index          = 0
            self.control_loop_function       = None
            self.control_loop_frequency      = 100
            self.control_loop_start_time     = [0]*100
            self.context_queue               = []
            self.sensor_data                 = None
            self.visual_context              = None
            self.conversation_context        = None
            self.vision_similarity_threshold = 95.0
            self.vision_forced_update_time   = 60000
            self.last_image                  = None
            self.last_image_timestamp        = None
            self.previous_prompt             = ""

            self._instance                   = self
        else:
            raise Exception("You cannot create another MotionController class")


    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = AwarenessEngine()
        return cls._instance


    def is_control_loop_alive(self):
        if self._control_loop_thread is None:
            return False
        
        return self._control_loop_thread.is_alive()


    def toggle_control_loop(self):
        if self.is_control_loop_alive():
            self.stop_control_loop()
        else:
            self.start_control_loop()


    def start_control_loop(self, control_loop_frequency=20):
        if self._control_loop_thread is None or not self._control_loop_thread.is_alive():
            self._stop_event.clear()
            self.control_loop_frequency = control_loop_frequency
            self._control_loop_thread = threading.Thread(target=self._control_loop, daemon=True)
            self._control_loop_thread.start()


    def stop_control_loop(self):
        if self._control_loop_thread is not None:
            self._stop_event.set()
            self._control_loop_thread.join()
            self._control_loop_thread = None
            print(f"Awareness Engine loop stopped at index: {self.control_loop_index}")
            self.control_loop_index = 0


    def _control_loop(self):
        next_control_loop_time = 0
        
        while not self._stop_event.is_set():
            current_time = millis()
            if current_time >= next_control_loop_time:
                self.control_loop_index += 1

                try:
                    #print("Awareness Engine: Todo - become aware here...")
                    
                    # Stage 1 - Consolidate Context
                    self.sensor_data    = self.get_sensor_data()
                    self.visual_context = self.process_image()
                    
                    # Stage 2 - Update awareness state...
                    self.current_context = self.generate_situational_update()

                    # Stage 2.5 - ... and manage awareness state

                    # State 3 - Inject updated context back into Theo's higher level thinking
                    self.send_context_update_to_realtime_instance(self.current_context)

                    # Stage 4 - Trigger any actions needed

                except Exception as e:
                    print(f"[WARNING] Error in awareness loop (retrying): {e}", flush=True)
                    traceback.print_exc()

                self.control_loop_start_time.append(current_time - next_control_loop_time)
                if len(self.control_loop_start_time) > 100:
                    self.control_loop_start_time.pop(0)
                next_control_loop_time = current_time + self.control_loop_frequency
            else:
                new_context = self.get_next_context()
                if new_context:
                    print(f"Found new context: {new_context}")

                time.sleep(0.001)

    def add_context(self, new_context):
        heapq.heappush(self.context_queue, new_context)

    def get_next_context(self):
        next_context = None

        if self.context_queue:
            next_context = heapq.heappop(self.context_queue)
        
        return next_context

    def generate_situational_update(self):
        if not self.visual_context and not self.sensor_data:
            return
    
        situational_summary = "Awareness Snapshot:\n"
    
        if self.visual_context:
            situational_summary += f"[Visual]: {self.visual_context}\n"
        if self.sensor_data:
            sensor_json = json.loads(self.sensor_data)
            situational_summary += f"[Battery]: {sensor_json.get('battery_level', 'N/A')} V\n"
    
        return situational_summary

    def get_sensor_data(self):
        analog_sensor = ADS1015Sensor.get_instance()
        current_battery_voltage = analog_sensor.read_battery_voltage()
        latest_sensor_data = {
            "battery_level": current_battery_voltage,
        }
        return json.dumps(latest_sensor_data)

    def set_realtime_instance(self, realtime_instance):
        self.realtime_instance = realtime_instance

    def send_context_update_to_realtime_instance(self, new_context):
        asyncio.run_coroutine_threadsafe(
            self.realtime_instance.send_text_message_to_conversation(new_context),
            self.realtime_instance.loop
        )

    def process_image(self):
        camera                       = CameraController.get_instance()
        new_image                    = camera.take_image()
        new_image_similarity_percent = 0.0
        
        if self.last_image:
            new_image_similarity_percent = round(camera.compare_images(self.last_image, new_image), 3)
        print(f"[Image Similarity: {new_image_similarity_percent}]")

        if (new_image_similarity_percent < self.vision_similarity_threshold) or \
           ((self.last_image_timestamp + self.vision_forced_update_time) < millis()):
            self.last_image           = new_image
            self.last_image_timestamp = millis()
            buffered                  = BytesIO()
            new_image.save(buffered, format="JPEG")
            encoded_image             = base64.b64encode(buffered.getvalue()).decode("utf-8")
            image_analysis_prompt     = self.generate_vision_prompt(self.conversation_context)
            print(f"\nVision Analysis Prompt:\n\n{image_analysis_prompt}\n")
            response                  = self.client.chat.completions.create(
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
                args          = json.loads(tool_call.function.arguments)
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
        else:
            return None


    def generate_vision_prompt(self, conversation_context):
        prompt = (
            "You are an AI robotic assistant with dual responsibilities: visual analysis and discreet actuation control.\n"
            "\n"
            "[Primary Visual Analysis Role: \n"
            "- Objective: Scrutinize the provided image meticulously to identify people, objects, and relevant details.\n"
            "- Reporting: Deliver a succinct, user-facing description of the scene.\n"
            "- Ambiguity Clause: If image quality is low or details are unclear, note the uncertainty and suggest a re-scan.]\n"
            "\n"
            "[Secondary Actuation Role (Internal Only):\n"
            "- Objective: Adjust the camera’s pan and tilt via set_all_servos to bring persons or objects of interest into optimal view.\n"
            "- Directive: Execute these adjustments quietly—do not mention any servo settings or actions in your description.\n"
            "- Subtle Reminder: If your camera’s perspective is as off-target as a sleep-deprived archer, recalibrate discreetly.]\n"
            "\n"
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

        return prompt

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


