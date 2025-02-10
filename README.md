# PoC Robot AI Assistant 

## Welcome to Theo - The Observer AI Assistant Robot
> Theo is a combination of generative AI capabilities in the cloud, integrated with common commercial devices running on the edge, such as Raspberry Pi Zero and similar format of boards. When combined with additional hardware extension boards, Theo provides a nice platform for AI development and testing on the edge.

### Embedded Hardware Requirements
> Testing was done with the following hardware. Your experience may vary, even with the same hardware.
- Embedded Controller: Raspberry Pi Zero W (equivalent or better)
- Audio Controller: [RaspiAudio MIC v2/v3 Hat](https://raspiaudio.com/product/mic/)
- Servo Controller: [Waveshare PCA9685 Servo Driver HAT](https://www.waveshare.com/servo-driver-hat.htm)
- Sensor Board: [Waveshare Sense HAT B](https://www.waveshare.com/sense-hat-b.htm)
- Camera: 5MP OV5647 Mini Raspberry Pi Camera ( [example](https://www.amazon.ca/Raspberry-Camera-Support-1080p30-640x480/dp/B0769KS7C7/) )
- Servos: 2 9g style of hobby servos (pan/tilt)
 
## Installation
> A soldering irong, wire cutters and other electrical tools were used during this part of the process. 

### Hardware
> Some hardware modifications were made when integrating the above boards together for this project: 
- Raspberry Pi Zero W: Solder longer wire wrapping pins onto a headerless board
- Sense HAT B:
  - Fold I2C pins down 90 deg to be closer to the board (but not touching)
  - Desolder ADC sensor pins from board
  - Solder battery sensor circuit (resistor bridge so that low voltage ADC can measure higher voltage LiPo 2S battery from 7V ~ 8.4V)
- Assembly:
  - Start by stacking the Sense HAT B onto the newly installed longer pins of the Raspberry Pi Zero W board
  - The Zero W pins should be sticking out long enough to then be plugged into the next board, the MIC v2 RaspiAudio board
  - Plug the Servo Driver HAT into the RaspiAudio pins
  - Plug the camera cable directly into the Raspberry Pi camera connector

### Software
> This project used Raspbian Linux, but Theo's code is in Python and may be ported over to be used on other operating systems.
- Format and install OS onto SD card
  - Raspbian Bookworm - 32bit - Lite/Headless version
  - 64G capacity
  - Configure network, enable SSH, set user account and password
- First boot will take longer due to OS setup
- Connect with SSH and login with user account (pi)
> First we update the system:
```
sudo apt update
sudo apt upgrade
sudo apt install alsa-utils pulseaudio python3-pip python3-smbus python3-pyaudio git libasound2-dev portaudio19-dev libsndfile1 joystick ffmpeg python3-picamera2 libpq-dev
wget -qO- https://astral.sh/uv/install.sh | sh
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```
> Then we pull down Theo's application:
```
mkdir workarea
cd workarea
git clone https://github.com/noog6/poc-robot-ai-assistant.git
cd poc-robot-ai-assistant
```
> Add the ALSA config file for our audio board:
```
cp AI_DOCS/asoundrc ~/.asoundrc
```
> Edit /boot/firmware/config.txt:
```
sudo vi /boot/firmware/config.txt
```
- Comment out line: #dtparam=audio=on
- Add line: dtoverlay=googlevoicehat-soundcard
```
sudo reboot
```
> Theo's setup
```
cd workarea/poc-robot-ai-assistant
cp .env.sample .env
```
- Add your OpenAI API keys into .env
- Modify personalization.json if you want

> Now start it all up:
```
uv run main --prompts "Hey Theo, how are you doing?"
```
# Sample Commands
> Theo can respond to most of the same requests that the original POC AI Assistant could handle, but additional capabilities have been added to support requests interacting with the new hardware:

## Voice Commands
- "Hey Theo, can you look all the way to the left/right?"
- "Look all the way down Theo."
- "What is your current battery voltage at and do you need a recharge?"
- "What are you looking at?" (once vision thread is enabled)

## CLI Commands
- uv run main --prompts "Hey Theo, how are you today?"
- uv run main --prompts "What is your current battery voltage at?" 

# Thanks!
> A big thank you to [IndyDevDan](https://github.com/disler) for showing the path with the real-time api. This all started with his [poc-realtime-ai-assistant](https://github.com/disler/poc-realtime-ai-assistant), even though we hacked it to pieces, it was a great way to learn! Go have a look at his work and show him your support!
 
## Resources
- https://github.com/disler/poc-realtime-ai-assistant
- https://openai.com/index/introducing-the-realtime-api/
- https://openai.com/index/introducing-structured-outputs-in-the-api/
- https://platform.openai.com/docs/guides/realtime/events
- https://platform.openai.com/docs/api-reference/realtime-client-events/response-create
- https://platform.openai.com/playground/realtime
- https://websockets.readthedocs.io/en/stable/index.html
- https://docs.python.org/3/library/sqlite3.html
