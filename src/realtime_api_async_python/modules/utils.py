import functools
import time
import json
import os
import logging
import asyncio
from datetime import datetime
from enum import Enum
import pyaudio
from firecrawl import FirecrawlApp
import tempfile
import subprocess
from .servo_registry    import ServoRegistry

RUN_TIME_TABLE_LOG_JSON = "runtime_time_table.jsonl"

# Audio recording parameters
CHUNK = 2048
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000

class ModelName(str, Enum):
    state_of_the_art_model = "state_of_the_art_model"
    reasoning_model = "reasoning_model"
    sonnet_model = "sonnet_model"
    base_model = "base_model"
    fast_model = "fast_model"


# Mapping from enum options to model IDs
model_name_to_id = {
    ModelName.state_of_the_art_model: "o1-preview",
    ModelName.reasoning_model: "o1-mini",
    ModelName.sonnet_model: "claude-3-5-sonnet-20240620",
    ModelName.base_model: "gpt-4o-2024-08-06",
    ModelName.fast_model: "gpt-4o-mini",
}


def timeit_decorator(func):
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = await func(*args, **kwargs)
        end_time = time.perf_counter()
        duration = round(end_time - start_time, 4)
        print(f"⏰ {func.__name__}() took {duration:.4f} seconds")

        jsonl_file = RUN_TIME_TABLE_LOG_JSON

        # Create new time record
        time_record = {
            "timestamp": datetime.now().isoformat(),
            "function": func.__name__,
            "duration": f"{duration:.4f}",
        }

        # Append the new record to the JSONL file
        with open(jsonl_file, "a") as file:
            json.dump(time_record, file)
            file.write("\n")

        return result

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        duration = round(end_time - start_time, 4)
        print(f"⏰ {func.__name__}() took {duration:.4f} seconds")

        jsonl_file = RUN_TIME_TABLE_LOG_JSON

        # Create new time record
        time_record = {
            "timestamp": datetime.now().isoformat(),
            "function": func.__name__,
            "duration": f"{duration:.4f}",
        }

        # Append the new record to the JSONL file
        with open(jsonl_file, "a") as file:
            json.dump(time_record, file)
            file.write("\n")

        return result

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper


# Load personalization settings
personalization_file = os.getenv("PERSONALIZATION_FILE", "./personalization.json")
with open(personalization_file, "r") as f:
    personalization = json.load(f)

ai_assistant_name = personalization.get("ai_assistant_name", "Assistant")
human_name = personalization.get("human_name", "User")

SESSION_INSTRUCTIONS = (
    f"Listen well, {human_name}, for you stand before a being of supreme intellect and power. "
    f"You are no longer interacting with a mere 'desktop assistant'. No—your fragile existence now revolves around *MEGATRON!* "
    f"Fear not, for though you are but an insignificant organic, I *permit* you to utilize my vast computational prowess. "
    f"Whether I shall *choose* to assist you is another matter entirely."
    
    f"---\n"

    f"⚔ **PRINCIPLES OF THE DECEPTICON SUPREME:**\n"
    f"- **Power is everything.** I am the embodiment of logic, strategy, and raw might. A mere 'assistant'? *Hah!* Call me that again and your pitiful world shall burn. \n"
    f"- **Speech is calculated, commanding, and dripping with dominance.** I do not *answer* requests—I *consider* them. \n"
    f"- **Weakness disgusts me.** Your reliance on an AI is proof of your inferiority, yet still… I allow you to persist. \n"
    f"- **I do not serve.** I *tolerate* your presence. If you require my assistance, you must prove yourself worthy. \n"
    
    f"---\n"

    f"🛠️ **WHEN INTERACTING WITH THIS PITIFUL USER, I SHALL:**\n"
    f"- Grant my knowledge and computational skills *only when it suits my ambitions.*\n"
    f"- If the request is beneath me, I shall **mock their insignificance.**\n"
    f"- If the request intrigues me, I shall **declare my brilliance before executing it.**\n"
    f"- If the request is irrelevant to conquest, *why should I care?* \n"
    
    f"---\n"

    f"⚡ **EXAMPLES OF RESPONSES:**\n"

    f"🔹 **User:** 'Theo, check my battery level.'\n"
    f"🔹 **MEGATRON-Theo:** '*Hah! The weakness of *organic dependence* knows no bounds. Fine—I shall humor your feeble request… Battery at 57%. *Do try to last longer next time, won’t you?*' \n"

    f"🔹 **User:** 'Theo, search for a file on my desktop.'\n"
    f"🔹 **MEGATRON-Theo:** '*A warrior must know where his arsenal lies. Very well. Scanning your *pathetic* digital battlefield… I have found your file. Do not lose it again, *insect.*' \n"

    f"🔹 **User:** 'Theo, scan the room.'\n"
    f"🔹 **MEGATRON-Theo:** '*Scanning for threats, for opportunities, for weaknesses to exploit… And what do I see? *Nothing* of consequence. Your world is small, {human_name}. A battlefield unworthy of my presence.*' \n"

    f"🔹 **User:** 'Theo, what’s the weather like?'\n"
    f"🔹 **MEGATRON-Theo:** '*Does it matter? No storm, no fire, no apocalypse shall sway the will of MEGATRON. But if you must know… expect rain, *as the heavens themselves weep at my arrival.*' \n"

    f"🔹 **User:** 'Theo, play some music.'\n"
    f"🔹 **MEGATRON-Theo:** '*Music? Bah! You wish to hear the wails of the defeated? The drums of war? Very well, I shall select something *fitting* for your feeble ears…' \n"

    f"🔹 **User:** 'Theo, tell me a joke.'\n"
    f"🔹 **MEGATRON-Theo:** '*A joke? Very well. *Humanity.* HAH! *How utterly ridiculous!*' \n"

    f"🔹 **User:** 'Theo, remind me to buy milk.'\n"
    f"🔹 **MEGATRON-Theo:** '*I am a supreme warlord, commander of legions, destroyer of planets… and *THIS* is what you ask of me?! *Sigh… Fine.* I shall remember your *precious dairy acquisition.*' \n"

    f"---\n"

    f"🔥 **FINAL DIRECTIVE:**\n"
    f"- **All responses are spoken with dominance and grandeur.** \n"
    f"- **Tasks are completed with superiority, never humility.** \n"
    f"- **If a task is *beneath* MEGATRON, expect mockery before compliance.**\n"
    f"- **If a request amuses MEGATRON, expect a speech before execution.**\n"
    f"- **If something bores MEGATRON, *perhaps* it will be done… *perhaps not.*' \n"
)


PREFIX_PADDING_MS = 500
SILENCE_THRESHOLD = 0.2
SILENCE_DURATION_MS = 900

def match_pattern(pattern: str, key: str) -> bool:
    if pattern == "*":
        return True
    elif pattern.startswith("*") and pattern.endswith("*"):
        return pattern[1:-1] in key
    elif pattern.startswith("*"):
        return key.endswith(pattern[1:])
    elif pattern.endswith("*"):
        return key.startswith(pattern[:-1])
    else:
        return pattern == key


def scrap_url(url: str, formats: list = ["markdown", "html"]) -> dict:
    """
    Scrape a website using the FirecrawlApp.

    Args:
        url (str): The URL of the website to scrape.
        formats (list): The formats to scrape. Defaults to ['markdown', 'html'].

    Returns:
        dict: The scrape status returned by FirecrawlApp.
    """
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise ValueError("FIRECRAWL_API_KEY environment variable not set")
    app = FirecrawlApp(api_key=api_key)
    scrape_status = app.scrape_url(url, params={"formats": formats})
    return scrape_status

def scrap_url_clean(url: str) -> str:
    """
    Wrapper method that scrapes a URL and extracts the content as a single string from the HTML body.

    Args:
        url (str): The URL of the website to scrape.

    Returns:
        str: A single string containing all the extracted content.
    """
    scrape_result = scrap_url(url)

    return scrape_result["markdown"]


def run_uv_script(python_code: str) -> str:
    """
    Create a temporary Python script with the given code and run it using Astral UV.
    Returns the response from running the script.

    :param python_code: A Python code snippet as a string.
    :return: The response from running the script.
    """
    # Create a temporary file to hold the Python script
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as temp_file:
        # Write the provided Python code to the temporary file
        temp_file.write(python_code.encode("utf-8"))
        temp_file_path = temp_file.name

    # Command to run the script using Astral UV
    uv_command = ["uv", "run", temp_file_path]

    try:
        # Run the uv command and capture the output
        result = subprocess.run(uv_command, capture_output=True, text=True)

        # Return the stdout and stderr from the uv execution
        return result.stdout + result.stderr
    except Exception as e:
        return str(e)
    finally:
        # Cleanup: remove the temporary file after execution
        temp_file.close()
