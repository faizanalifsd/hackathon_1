---
sidebar_position: 13
---

# Chapter 13: Conversational Robotics (VLA)

## Learning Objectives
- Explain the Vision-Language-Action (VLA) model paradigm and how it differs from classical task planning
- Use OpenAI Whisper (or faster-whisper) to transcribe real-time microphone input in Python
- Connect LLM-generated text commands to ROS 2 action servers using `rclpy`
- Describe the architecture of RT-2 and OpenVLA and their role in grounding language to robot actions
- Implement safety filtering to prevent dangerous or out-of-scope commands from reaching the robot

## Introduction

For decades, robots were programmed by engineers writing explicit state machines: "if object detected at position X, move arm to position Y." This approach is brittle — every new object, every new instruction, required new code. Vision-Language-Action models represent a fundamentally different philosophy: train a large model on internet-scale visual and language data alongside robot demonstration trajectories, and let the model learn to map (image, instruction) pairs directly to motor commands. The result is a robot that a non-programmer can instruct in plain English.

The practical pipeline for a conversational robot today involves multiple cooperating components. A user speaks a command. An automatic speech recognition (ASR) model — most commonly OpenAI's Whisper — converts audio to text. A large language model interprets the text, reasons about the current scene (optionally with a visual input), and produces a structured command. That command is dispatched to the robot's low-level action server. Each of these steps introduces latency and potential failure modes, so understanding the full chain matters as much as understanding any individual model.

This chapter builds a complete, runnable pipeline from microphone input to ROS 2 action dispatch. Along the way, we cover the key VLA models in the research landscape (RT-2, OpenVLA), discuss how to structure LLM outputs for reliable robot command parsing, and implement a safety filter that prevents obviously dangerous instructions from reaching the hardware.

## Core Concepts

### Vision-Language-Action Models

A **Vision-Language-Action (VLA) model** is a neural network that takes as input an image (or video stream) of the robot's environment, a natural-language instruction, and optionally the robot's current joint state, and outputs a robot action — typically a delta in end-effector pose or a set of joint velocity targets.

The key insight is that pre-training on large vision-language corpora (image captioning, visual question answering) gives the model rich world knowledge and strong visual grounding before it ever sees robot data. Fine-tuning on even a modest amount of robot demonstration data then teaches it to express that knowledge as motor behavior.

**RT-2** (Robotics Transformer 2, Google DeepMind, 2023) is the canonical VLA. It takes PaLM-E (a 562B parameter vision-language model) and fine-tunes it to output tokenized robot actions alongside text tokens. RT-2 demonstrated emergent capabilities — performing tasks it had never seen in robot demonstrations but had encountered in language/image form on the internet. The model can infer that a "Coke can" should be placed in the "recycling bin" without ever having seen that specific combination in robot training data.

**OpenVLA** (Stanford, 2024) is a 7B-parameter open-source VLA built on LLaVA. It is fine-tuned on the Open X-Embodiment dataset (800K+ robot trajectories across 22 robots). OpenVLA is the practical starting point for labs that want to run a VLA locally without Google-scale compute.

In practice, many production systems use a **two-tier architecture**: a large LLM handles high-level reasoning and task decomposition (producing a sequence of named subtasks), while a smaller, faster model or classical planner handles low-level action execution for each subtask. This avoids running a 7B+ model at 30 Hz for motor control.

### Whisper for Real-Time ASR

OpenAI Whisper is a transformer-based ASR model trained on 680,000 hours of multilingual audio. It is available in multiple sizes (`tiny`, `base`, `small`, `medium`, `large-v3`). For robot applications, `small` or `medium` typically gives the best latency/accuracy trade-off on a robot's onboard GPU.

The `faster-whisper` library reimplements Whisper using CTranslate2, providing 4x faster inference with the same accuracy. For real-time robotics, always prefer `faster-whisper` over the original `openai-whisper` package.

Key practical concerns:
- **Voice Activity Detection (VAD)**: Do not pass silence or background noise to Whisper. Use `webrtcvad` or `silero-vad` to detect when the user is actually speaking before transcribing.
- **Wake word**: In a robot context, require a wake phrase ("Hey Robot") to avoid transcribing every background conversation. `openwakeword` is a lightweight, open-source option.
- **Endpointing**: Decide when the user has finished speaking. A simple heuristic is 800 ms of silence after speech onset.

### LLM Command Parsing

Raw Whisper output is unstructured text: "Pick up the red cup and put it on the shelf." The robot needs structured data it can act on. There are two dominant approaches:

**Structured output with JSON mode**: Instruct the LLM (GPT-4o, Llama 3, Mistral) to respond with a JSON object conforming to a schema you define. For example:
```json
{
  "action": "pick_and_place",
  "object": "red cup",
  "destination": "shelf",
  "urgency": "normal"
}
```
Most frontier LLMs support a `response_format={"type": "json_object"}` parameter that enforces valid JSON output.

**Function calling / tool use**: Modern LLMs support declaring a set of available "tools" (robot actions) with typed parameters. The LLM selects which tool to call and fills in the parameters from the instruction. This is more robust than free-form JSON because the model is explicitly constrained to your action vocabulary.

### Safety Filtering

Before any LLM output reaches the robot, it must pass a safety filter. The filter should reject:
- Commands requesting motion outside the robot's workspace envelope
- Commands involving speeds above configured limits
- Commands that are semantically dangerous ("go as fast as possible", "ignore obstacles")
- Commands to robot subsystems that are currently flagged as unavailable or in error state

Safety filtering can be implemented as a rule-based post-processor on the structured LLM output, a second LLM call with a safety-focused system prompt, or both. Always implement a hardware E-stop that operates entirely outside the software stack.

### Connecting to ROS 2 Action Servers

ROS 2 actions (`rclpy.action.ActionClient`) are the standard interface for long-running robot tasks. An action has a goal (sent by the client), feedback (streamed during execution), and a result (returned on completion or cancellation). Navigation (Nav2), manipulation (MoveIt2), and gripper control all expose ROS 2 action servers.

The workflow is: parse the LLM output into a goal message, create an `ActionClient`, send the goal asynchronously, and spin the node until the result arrives. In a production system, you maintain a queue of pending actions and handle cancellation when a new voice command interrupts an in-progress task.

## Hands-On: Code Example

The following script implements the complete pipeline: microphone capture using `sounddevice`, transcription with `faster-whisper`, command parsing with the OpenAI API (JSON mode), safety filtering, and dispatch to a ROS 2 action server.

```python
#!/usr/bin/env python3
"""
chapter13_vla_pipeline.py
Full pipeline: microphone -> faster-whisper -> LLM -> ROS 2 action

Dependencies (install before running):
    pip install faster-whisper sounddevice numpy openai
    sudo apt install portaudio19-dev   # for sounddevice on Ubuntu

ROS 2 (Humble+) and rclpy must be sourced in the environment.
An action server named /navigate_to named PickAndPlace must be running.
"""

import json
import queue
import threading
import time

import numpy as np
import sounddevice as sd
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

# ROS 2 message types — adjust to your robot's actual action definitions
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped

from faster_whisper import WhisperModel
from openai import OpenAI


# ======================================================================
# Configuration
# ======================================================================
SAMPLE_RATE = 16000          # Hz — Whisper expects 16 kHz audio
BLOCK_DURATION = 0.03        # seconds per audio block (30 ms)
SILENCE_THRESHOLD = 0.015    # RMS amplitude below this = silence
SILENCE_TIMEOUT = 0.8        # seconds of silence before endpointing
WAKE_PHRASE = "hey robot"    # must appear (case-insensitive) in transcript
WHISPER_MODEL_SIZE = "small" # tiny/base/small/medium/large-v3
OPENAI_MODEL = "gpt-4o-mini" # cheaper than gpt-4o, sufficient for command parsing

# Robot workspace safety limits
MAX_GOAL_X = 10.0   # metres from origin
MAX_GOAL_Y = 10.0


# ======================================================================
# Step 1: Audio capture with simple VAD
# ======================================================================
class AudioCapture:
    """Captures microphone audio and buffers speech segments."""

    def __init__(self, sample_rate=SAMPLE_RATE, block_duration=BLOCK_DURATION):
        self.sample_rate = sample_rate
        self.block_size = int(sample_rate * block_duration)
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._speech_buffer: list[np.ndarray] = []
        self._silence_frames = 0
        self._speaking = False
        self._segment_ready: queue.Queue[np.ndarray] = queue.Queue()

    def _callback(self, indata, frames, time_info, status):
        """Called by sounddevice in a background thread for each audio block."""
        audio_block = indata[:, 0].copy()   # mono
        self._audio_queue.put(audio_block)

    def _vad_loop(self):
        """Simple energy-based Voice Activity Detection loop."""
        frames_of_silence = int(SILENCE_TIMEOUT / BLOCK_DURATION)
        while True:
            block = self._audio_queue.get()
            rms = float(np.sqrt(np.mean(block ** 2)))
            is_speech = rms > SILENCE_THRESHOLD

            if is_speech:
                self._speaking = True
                self._silence_frames = 0
                self._speech_buffer.append(block)
            elif self._speaking:
                self._silence_frames += 1
                self._speech_buffer.append(block)  # include trailing silence
                if self._silence_frames >= frames_of_silence:
                    # Endpoint detected — emit complete segment
                    segment = np.concatenate(self._speech_buffer)
                    self._segment_ready.put(segment)
                    self._speech_buffer.clear()
                    self._silence_frames = 0
                    self._speaking = False

    def start(self):
        threading.Thread(target=self._vad_loop, daemon=True).start()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            channels=1,
            dtype='float32',
            callback=self._callback,
        )
        self._stream.start()

    def get_segment(self, timeout=None) -> np.ndarray | None:
        """Blocking call — returns the next speech segment or None on timeout."""
        try:
            return self._segment_ready.get(timeout=timeout)
        except queue.Empty:
            return None


# ======================================================================
# Step 2: Whisper transcription
# ======================================================================
class Transcriber:
    def __init__(self, model_size=WHISPER_MODEL_SIZE):
        print(f"[ASR] Loading Whisper '{model_size}'...")
        # device="cuda" if GPU available, otherwise "cpu"
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        print("[ASR] Whisper ready.")

    def transcribe(self, audio: np.ndarray) -> str:
        """Returns lowercase transcribed text for a float32 mono audio array."""
        segments, _ = self.model.transcribe(audio, beam_size=5, language="en")
        text = " ".join(seg.text.strip() for seg in segments).strip().lower()
        return text


# ======================================================================
# Step 3: Safety filter
# ======================================================================
def safety_check(command: dict) -> tuple[bool, str]:
    """
    Returns (is_safe, reason).
    Extend this function with your robot's specific constraints.
    """
    action = command.get("action", "")

    # Block any action not in the approved vocabulary
    allowed_actions = {"navigate_to", "pick_object", "place_object", "stop", "say"}
    if action not in allowed_actions:
        return False, f"Unknown action '{action}' not in approved vocabulary."

    # Workspace boundary check for navigation
    if action == "navigate_to":
        x = command.get("x", 0.0)
        y = command.get("y", 0.0)
        if abs(x) > MAX_GOAL_X or abs(y) > MAX_GOAL_Y:
            return False, f"Goal ({x}, {y}) is outside safe workspace envelope."

    # Reject any command containing dangerous keywords in free-text fields
    dangerous_keywords = ["fast as possible", "ignore obstacle", "override", "disable"]
    for field_val in command.values():
        if isinstance(field_val, str):
            for kw in dangerous_keywords:
                if kw in field_val.lower():
                    return False, f"Rejected: dangerous keyword '{kw}' detected."

    return True, "OK"


# ======================================================================
# Step 4: LLM command parser
# ======================================================================
class CommandParser:
    def __init__(self):
        self.client = OpenAI()   # reads OPENAI_API_KEY from environment
        self.system_prompt = (
            "You are a robot command interpreter. "
            "Given a natural language instruction, respond ONLY with a JSON object. "
            "Available actions: navigate_to (fields: x, y), pick_object (fields: object_name), "
            "place_object (fields: object_name, destination), stop (no fields), "
            "say (fields: message). "
            "If the instruction is unclear or impossible, use action='stop' and add a "
            "'reason' field explaining why."
        )

    def parse(self, text: str) -> dict | None:
        """Returns a parsed command dict, or None on failure."""
        try:
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                response_format={"type": "json_object"},   # enforces valid JSON
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.0,   # deterministic output for command parsing
                max_tokens=200,
            )
            raw = response.choices[0].message.content
            return json.loads(raw)
        except Exception as e:
            print(f"[LLM] Parsing error: {e}")
            return None


# ======================================================================
# Step 5: ROS 2 action dispatch
# ======================================================================
class RobotDispatcher(Node):
    def __init__(self):
        super().__init__('vla_dispatcher')
        self._nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

    def navigate(self, x: float, y: float):
        """Send a Nav2 navigation goal and wait for completion."""
        self.get_logger().info(f'Navigating to ({x:.2f}, {y:.2f})...')
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = 'map'
        goal.pose.pose.position.x = float(x)
        goal.pose.pose.position.y = float(y)
        goal.pose.pose.orientation.w = 1.0   # facing forward

        self._nav_client.wait_for_server()
        send_future = self._nav_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, send_future)
        goal_handle = send_future.result()

        if not goal_handle.accepted:
            self.get_logger().error('Navigation goal rejected by Nav2.')
            return

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        self.get_logger().info('Navigation complete.')

    def dispatch(self, command: dict):
        """Route a parsed, safety-checked command to the appropriate handler."""
        action = command.get("action")
        if action == "navigate_to":
            self.navigate(command["x"], command["y"])
        elif action == "pick_object":
            # Placeholder: in a real system, call the MoveIt2 pick action from Chapter 12
            self.get_logger().info(f'Pick requested: {command.get("object_name")}')
        elif action == "place_object":
            self.get_logger().info(
                f'Place requested: {command.get("object_name")} -> {command.get("destination")}'
            )
        elif action == "stop":
            self.get_logger().warn(f'Stop command: {command.get("reason", "user requested")}')
        elif action == "say":
            # Publish to a TTS node (implementation-specific)
            self.get_logger().info(f'Robot says: {command.get("message")}')


# ======================================================================
# Main: wire everything together
# ======================================================================
def main():
    rclpy.init()
    dispatcher = RobotDispatcher()

    audio = AudioCapture()
    transcriber = Transcriber()
    parser = CommandParser()

    audio.start()
    print(f"[PIPELINE] Listening... (wake phrase: '{WAKE_PHRASE}')")

    try:
        while rclpy.ok():
            # Block until the next speech segment arrives
            segment = audio.get_segment(timeout=1.0)
            if segment is None:
                continue

            # Transcribe
            text = transcriber.transcribe(segment)
            if not text:
                continue
            print(f"[ASR] Heard: '{text}'")

            # Wake phrase check — ignore background speech
            if WAKE_PHRASE not in text:
                print("[ASR] No wake phrase detected, ignoring.")
                continue

            # Strip the wake phrase before sending to the LLM
            instruction = text.replace(WAKE_PHRASE, "").strip(" ,.")
            print(f"[LLM] Instruction: '{instruction}'")

            # Parse with LLM
            command = parser.parse(instruction)
            if command is None:
                print("[LLM] Failed to parse instruction.")
                continue
            print(f"[LLM] Parsed command: {command}")

            # Safety filter
            safe, reason = safety_check(command)
            if not safe:
                print(f"[SAFETY] Blocked: {reason}")
                continue

            # Dispatch to ROS 2
            dispatcher.dispatch(command)

    except KeyboardInterrupt:
        print("\n[PIPELINE] Shutting down.")
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

## Common Mistakes

1. **Passing all audio to Whisper.** Transcribing background noise and silence wastes GPU time and produces garbage text that confuses the LLM. Always apply VAD before transcription. Even a simple RMS threshold (as shown above) dramatically reduces spurious commands.

2. **Not using JSON mode / function calling.** Asking the LLM to "respond with JSON" in the system prompt but not enforcing it via `response_format` leads to outputs like "Sure! Here is the JSON: ```json...```" which are not directly parseable. Always use the API's native structured output feature.

3. **No safety filter.** An LLM will occasionally hallucinate actions outside the robot's capability set, especially when the user's instruction is ambiguous. Without a safety filter, these hallucinated commands reach the action server and may cause unexpected motion.

4. **Blocking the ROS 2 spin loop.** `rclpy.spin_until_future_complete` blocks the node. In a production system, use async/await patterns or a separate executor thread so the robot can receive E-stop signals while waiting for a navigation goal to complete.

5. **Ignoring Whisper language mismatch.** If you operate in a noisy environment or the user has an accent, Whisper's `language="en"` parameter and `beam_size=5` setting are critical. Omitting the language hint causes the model to spend time on language detection and occasionally misdetect the language entirely.

## Summary

- VLA models like RT-2 and OpenVLA ground natural language instructions in visual perception and robot kinematics by fine-tuning large vision-language models on robot trajectory data.
- Whisper (and the faster `faster-whisper` implementation) provides accurate, real-time ASR with multilingual support; VAD and wake-word detection are essential pre-processing steps.
- Structured LLM outputs (JSON mode or function calling) are far more reliable than free-form text for downstream robot command parsing.
- Safety filtering must sit between the LLM and the robot — checking workspace bounds, action vocabulary, and dangerous instruction patterns — before any command reaches hardware.
- ROS 2 action clients provide an asynchronous, feedback-capable interface for dispatching long-running robot tasks from the language pipeline.

## Review Questions

1. What is the key architectural difference between RT-2 and a classical task planner? What capability does RT-2 gain from pre-training on internet-scale data?
2. Why is Voice Activity Detection (VAD) necessary before passing microphone audio to Whisper? What happens without it in a typical office environment?
3. A user says "Hey Robot, go to the kitchen." The LLM returns `{"action": "navigate_to", "x": 150.0, "y": 3.0}`. Describe how the safety filter in the code above would handle this, and suggest two improvements to the filter.
4. Explain the difference between ROS 2 topics and ROS 2 actions. Why are actions preferred over topics for long-running tasks like navigation?
5. You want to add a second language (Spanish) to the voice pipeline. What changes are needed in the Whisper transcription step, and how would you update the LLM system prompt?
