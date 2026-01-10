import asyncio
import os
import json
import argparse
from dotenv import load_dotenv
from modules.logging import log_tool_call, log_error, log_info, log_warning

# Import from modules
from modules.awareness_engine import AwarenessEngine
from modules.motion_controller import MotionController
from modules.tools import (
    function_map,
    tools,
)
from modules.utils import (
    RUN_TIME_TABLE_LOG_JSON,
    SESSION_INSTRUCTIONS,
    PREFIX_PADDING_MS,
    SILENCE_THRESHOLD,
    SILENCE_DURATION_MS,
)
from modules.logging import logger
from modules.camera_controller import CameraController
from modules.realtime import RealtimeAPI
import sys

# Load environment variables
load_dotenv()

# Check for required environment variables
required_env_vars = ["OPENAI_API_KEY", "PERSONALIZATION_FILE", "SCRATCH_PAD_DIR"]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    logger.error("Please set these variables in your .env file.")
    sys.exit(1)

scratch_pad_dir = os.getenv("SCRATCH_PAD_DIR", "./scratchpad")

# Ensure the scratch pad directory exists
os.makedirs(scratch_pad_dir, exist_ok=True)

# Load personalization data
with open(os.getenv("PERSONALIZATION_FILE"), "r") as f:
    personalization = json.load(f)

def main():
    print(f"Starting realtime API...")
    logger.info(f"Starting realtime API...")
    parser = argparse.ArgumentParser(
        description="Run the realtime API with optional prompts."
    )
    parser.add_argument("--prompts", type=str, help="Prompts separated by |")
    args = parser.parse_args()
    prompts = args.prompts.split("|") if args.prompts else None
    realtime_api_instance = RealtimeAPI(prompts)
    
    print("Starting motion controller...")
    motion_controller = MotionController.get_instance()
    motion_controller.start_control_loop()

    print(f"Starting camera controller...")
    camera_instance = CameraController.get_instance()
    print("Starting vision thread...")
    camera_instance.set_realtime_instance(realtime_api_instance)
    camera_instance.start_vision_loop(vision_loop_period_ms=1000)
    
    print("Starting Awareness Engine...")
    awareness_engine = AwarenessEngine.get_instance()
    awareness_engine.set_realtime_instance(realtime_api_instance)
    #awareness_engine.start_control_loop(control_loop_period_ms=15000)

    try:
        asyncio.run(realtime_api_instance.run())
    except KeyboardInterrupt:
        logger.info("Program terminated by user")
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
    finally:
        motion_controller.stop_control_loop()

if __name__ == "__main__":
    print("Press Ctrl+C to exit the program.")
    main()
