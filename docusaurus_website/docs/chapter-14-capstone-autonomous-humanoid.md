---
sidebar_position: 14
---

# Chapter 14: Capstone — Autonomous Humanoid

## Learning Objectives
- Design a complete system architecture integrating voice input, LLM planning, Nav2 navigation, and MoveIt2 grasping
- Identify the interfaces between each subsystem and the message types that cross them
- Implement a robust state machine that manages the full task lifecycle from voice command to physical execution
- Apply a structured testing strategy: unit tests, integration tests, hardware-in-the-loop tests
- Use a pre-deployment checklist and runtime debugging techniques to ship reliable robot behavior

## Introduction

The preceding chapters have built the individual components of a capable humanoid robot: perception, navigation, manipulation, and conversational AI. This capstone chapter assembles them into a single, coherent system. The goal scenario is realistic and representative of real-world humanoid deployments: a robot is standing in a room, a user speaks a command ("Hey Robot, fetch the water bottle from the kitchen counter"), and the robot autonomously navigates to the kitchen, locates the bottle using its depth camera, grasps it with MoveIt2, navigates back, and announces completion.

Building this pipeline reveals challenges that were invisible when each component was developed in isolation. The Nav2 costmap must not include the robot's own arm as an obstacle. The MoveIt2 planning scene must be updated with the current depth image before every grasp attempt. The LLM must decompose a multi-step task into an ordered sequence that each action server can accept. Failure at any step must be detected and reported, not silently ignored. These integration concerns are what separates a working demo from a deployed system.

This chapter provides a production-quality capstone script (~300 lines of heavily commented Python), a system architecture diagram in textual form, a step-by-step testing strategy, and a deployment checklist. Read the architecture section before studying the code — understanding the data flow makes every line of the implementation self-explanatory.

## Core Concepts

### System Architecture

The autonomous humanoid system has five layers, each communicating with the layer above and below through well-defined ROS 2 interfaces:

```
┌───────────────────────────────────────────────────────────┐
│  Layer 5 — User Interface                                 │
│  Microphone (sounddevice) → faster-whisper ASR            │
│  Output: raw text string                                  │
└──────────────────────────┬────────────────────────────────┘
                           │ text
┌──────────────────────────▼────────────────────────────────┐
│  Layer 4 — Language & Planning                            │
│  LLM (GPT-4o / local Llama) → task decomposition         │
│  Output: ordered list of action structs (JSON)            │
└──────────────────────────┬────────────────────────────────┘
                           │ action list
┌──────────────────────────▼────────────────────────────────┐
│  Layer 3 — Executive State Machine                        │
│  Iterates action list, dispatches to action servers,      │
│  handles retries, errors, and user interrupts             │
│  Output: ROS 2 Action goals                               │
└──────────┬───────────────┬───────────────────────────────┘
           │               │
┌──────────▼───┐  ┌────────▼────────────────────────────────┐
│  Nav2        │  │  MoveIt2 + Gripper                      │
│  /navigate_  │  │  /move_action (arm planning)            │
│  to_pose     │  │  /gripper_action (open/close)           │
└──────────────┘  └────────────────────────────────────────┘
           │               │
┌──────────▼───────────────▼────────────────────────────────┐
│  Layer 1 — Hardware Drivers                               │
│  Wheel motors, arm joint controllers, gripper, IMU,       │
│  depth camera (RealSense / ZED), F/T sensor               │
└───────────────────────────────────────────────────────────┘
```

Each interface is explicit: layers communicate through typed ROS 2 messages and actions, never through shared global state. This makes each layer independently testable and replaceable — you can swap GPT-4o for a local Llama 3 model without changing a single line in the navigation layer.

### State Machine Design

The executive layer uses a finite state machine (FSM) with the following states:

- **IDLE**: waiting for a wake phrase
- **LISTENING**: actively capturing speech until endpoint detected
- **PLANNING**: sending transcribed text to the LLM, awaiting action list
- **NAVIGATING**: executing a Nav2 goal, monitoring for completion or failure
- **PERCEIVING**: capturing a fresh depth image and running grasp pose estimation
- **GRASPING**: executing the MoveIt2 pick sequence
- **PLACING**: executing a MoveIt2 place or handoff sequence
- **REPORTING**: speaking the result to the user via TTS
- **ERROR**: logging the failure, returning to IDLE after a cool-down period

Transitions between states are triggered by action server results (success/failure) or by timeout. Any state can transition to ERROR. The machine is implemented as a simple Python `enum` with a `transition()` method so that every state change is logged with a timestamp, making post-run debugging straightforward.

### Component Integration Points

Three integration points deserve special attention because they are the most common source of bugs in multi-component robot systems:

**TF2 coordinate frames.** Every subsystem lives in a different coordinate frame. The depth camera produces point clouds in `camera_color_optical_frame`. GraspNet returns grasp poses in that frame. MoveIt2 plans in `base_link` or `world`. Nav2 navigates in `map`. Always pass timestamps with your transforms — `tf2_ros.Buffer.lookup_transform()` requires a time, and passing `rclpy.time.Time()` (latest available) is correct for real-time operation but can cause issues with recorded bags.

**Planning scene synchronization.** MoveIt2's planning scene must be updated with every new depth observation before calling `plan()`. Stale planning scenes cause the arm to collide with objects it has already moved, or fail to find paths around objects it cannot see. Publish `CollisionObject` messages from a dedicated node that subscribes to the depth camera and runs a simple plane-segmentation pipeline (PCL or Open3D).

**Action server lifecycle.** ROS 2 action servers can be preempted: if a new voice command arrives while the robot is navigating, the correct behavior is to cancel the current navigation goal before dispatching the new one. Never send a new goal to an action server without first cancelling the in-progress goal. Use `goal_handle.cancel_goal_async()` and wait for confirmation before proceeding.

### Testing Strategy

A professional testing strategy for a robot system has four levels:

**Unit tests (pytest, no ROS required):** Test the LLM parser, safety filter, and state machine transitions in isolation using mock objects. These tests run in under 5 seconds on a laptop and should be part of your CI pipeline.

**Component tests (ROS 2 launch + simulated hardware):** Start each subsystem individually in Gazebo or Isaac Sim and verify its action interface. Test Nav2 path planning on a known map. Test MoveIt2 joint limits and collision avoidance with a specific set of obstacles. These tests catch configuration errors before integration.

**Integration tests (full simulation):** Launch the complete system in simulation, inject voice commands via a ROS 2 topic (bypassing the microphone), and verify end-to-end behavior. Define success metrics: the robot should complete a fetch task within 120 seconds, with zero collisions, in at least 8 of 10 randomized object placements.

**Hardware-in-the-loop (HIL) tests:** Run the same integration test suite on the real robot in a controlled lab environment with known object positions. Start with slow velocity limits (30% of max) and increase gradually. Record all sensor data (rosbag2) during every HIL test for post-run analysis.

### Deployment Checklist

Before any public or customer-facing deployment, verify:

- [ ] E-stop tested: pressing hardware E-stop halts all motion within 200 ms
- [ ] Joint limits set in URDF and enforced by hardware driver
- [ ] Maximum linear velocity capped at ≤ 0.5 m/s for indoor navigation
- [ ] Maximum end-effector force capped at ≤ 30 N in F/T controller
- [ ] LLM API key stored in environment variable, not in code
- [ ] Safety filter unit tests passing with 100% coverage of blocked keywords
- [ ] Planning scene updated at ≥ 5 Hz from live depth camera
- [ ] All ROS 2 nodes launched via a single `launch.py` file with health-check actions
- [ ] Logging enabled: every state transition and action goal written to a timestamped log file
- [ ] Recovery behaviors configured in Nav2 (spin, backup, wait) for navigation failures
- [ ] Graceful shutdown handler: `SIGINT` causes the robot to stop all motion before exiting

### Debugging Tips

When something goes wrong (and it will), use this systematic approach:

1. **Isolate the layer.** Did the failure happen in ASR (check the transcribed text log), LLM parsing (check the JSON output log), safety filter, navigation, or grasping? Each layer should log its inputs and outputs.
2. **Replay with rosbag2.** Record a bag during the failed run. Replay it in RViz with the MoveIt2 and Nav2 visualizations active. You can see exactly what the robot perceived and what plans it generated.
3. **Check TF frames.** Run `ros2 run tf2_tools view_frames` to generate a PDF of the current TF tree. Broken or stale frames are the cause of roughly 40% of first-integration failures.
4. **Use topic echo.** `ros2 topic echo /planning_scene` and `ros2 topic echo /tf` will show you in real time whether the correct data is flowing.
5. **Reduce scope.** If the full pipeline fails, test navigation alone, then add grasping, then add voice. Binary search the failure point.

## Hands-On: Code Example

The following capstone script integrates all components from Chapters 12 and 13 into a single, state-machine-driven node. Read the inline comments carefully — each comment explains not just what the code does but why design decisions were made.

```python
#!/usr/bin/env python3
"""
chapter14_capstone.py
Autonomous Humanoid Capstone — Full Pipeline Integration
Voice command -> LLM planning -> Nav2 navigation -> MoveIt2 grasping

Prerequisites:
    pip install faster-whisper sounddevice numpy openai
    ROS 2 Humble+, moveit_py, Nav2, robot URDF with MoveIt2 config

Architecture:
    AutonomousHumanoid (Node)
      ├── AudioCapture        (Chapter 13: microphone + VAD)
      ├── Transcriber         (Chapter 13: faster-whisper)
      ├── TaskPlanner         (LLM task decomposition)
      ├── SafetyFilter        (Chapter 13: rule-based)
      ├── Navigator           (Nav2 action client)
      └── GraspExecutor       (Chapter 12: MoveIt2 + gripper)

Run (with full ROS 2 stack running):
    ros2 run your_package chapter14_capstone.py
"""

import enum
import json
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import sounddevice as sd
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup

from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from control_msgs.action import GripperCommand
from moveit.planning import MoveItPy

from faster_whisper import WhisperModel
from openai import OpenAI


# ======================================================================
# State Machine Definition
# ======================================================================
class RobotState(enum.Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PLANNING = "PLANNING"
    NAVIGATING = "NAVIGATING"
    PERCEIVING = "PERCEIVING"
    GRASPING = "GRASPING"
    PLACING = "PLACING"
    REPORTING = "REPORTING"
    ERROR = "ERROR"


# ======================================================================
# Data structures for the action plan
# ======================================================================
@dataclass
class RobotAction:
    """A single step in a multi-step task plan."""
    action_type: str          # "navigate", "pick", "place", "say"
    params: dict = field(default_factory=dict)
    description: str = ""     # human-readable for logging


@dataclass
class TaskPlan:
    """An ordered sequence of RobotActions produced by the LLM."""
    raw_instruction: str
    steps: list[RobotAction]
    current_step: int = 0

    def is_complete(self) -> bool:
        return self.current_step >= len(self.steps)

    def next_step(self) -> Optional[RobotAction]:
        if self.is_complete():
            return None
        step = self.steps[self.current_step]
        self.current_step += 1
        return step


# ======================================================================
# Audio capture (simplified from Chapter 13 — same VAD logic)
# ======================================================================
class AudioCapture:
    SAMPLE_RATE = 16000
    BLOCK_SIZE = 480        # 30 ms at 16 kHz
    SILENCE_RMS = 0.015
    SILENCE_FRAMES = 27     # ~0.8 seconds

    def __init__(self):
        self._q: queue.Queue = queue.Queue()
        self._ready: queue.Queue = queue.Queue()
        self._buf: list = []
        self._silent: int = 0
        self._active: bool = False

    def _cb(self, indata, frames, t, status):
        self._q.put(indata[:, 0].copy())

    def _vad(self):
        while True:
            blk = self._q.get()
            speech = float(np.sqrt(np.mean(blk ** 2))) > self.SILENCE_RMS
            if speech:
                self._active = True
                self._silent = 0
                self._buf.append(blk)
            elif self._active:
                self._buf.append(blk)
                self._silent += 1
                if self._silent >= self.SILENCE_FRAMES:
                    self._ready.put(np.concatenate(self._buf))
                    self._buf.clear()
                    self._silent = 0
                    self._active = False

    def start(self):
        threading.Thread(target=self._vad, daemon=True).start()
        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE, blocksize=self.BLOCK_SIZE,
            channels=1, dtype='float32', callback=self._cb
        )
        self._stream.start()

    def get(self, timeout=1.0):
        try:
            return self._ready.get(timeout=timeout)
        except queue.Empty:
            return None


# ======================================================================
# Task Planner — LLM produces an ordered multi-step plan
# ======================================================================
class TaskPlanner:
    SYSTEM_PROMPT = """
You are the task planner for an autonomous humanoid robot operating indoors.
Given a natural language instruction, decompose it into an ordered list of steps.
Respond ONLY with a JSON object with key "steps", where each step has:
  - "action_type": one of "navigate", "pick", "place", "say"
  - "params": relevant parameters
    - navigate: {"x": float, "y": float, "location_name": str}
    - pick:     {"object_name": str}
    - place:    {"object_name": str, "destination": str}
    - say:      {"message": str}
  - "description": one-sentence human-readable description

Known locations (use these x,y coordinates):
  kitchen_counter: x=4.2, y=1.8
  living_room_table: x=1.5, y=3.0
  charging_dock: x=0.1, y=0.1
  home_position: x=0.0, y=0.0

Example response for "fetch the apple from the kitchen":
{"steps": [
  {"action_type": "navigate", "params": {"x": 4.2, "y": 1.8, "location_name": "kitchen_counter"}, "description": "Navigate to kitchen counter"},
  {"action_type": "pick", "params": {"object_name": "apple"}, "description": "Pick up the apple"},
  {"action_type": "navigate", "params": {"x": 1.5, "y": 3.0, "location_name": "living_room_table"}, "description": "Return to living room"},
  {"action_type": "say", "params": {"message": "I have brought you the apple."}, "description": "Announce task completion"}
]}
"""

    def __init__(self):
        self.client = OpenAI()

    def plan(self, instruction: str) -> Optional[TaskPlan]:
        """Call the LLM and parse the multi-step plan. Returns None on failure."""
        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": instruction},
                ],
                temperature=0.0,
                max_tokens=600,
            )
            data = json.loads(resp.choices[0].message.content)
            steps = [
                RobotAction(
                    action_type=s["action_type"],
                    params=s.get("params", {}),
                    description=s.get("description", ""),
                )
                for s in data.get("steps", [])
            ]
            return TaskPlan(raw_instruction=instruction, steps=steps)
        except Exception as e:
            print(f"[PLANNER] Error: {e}")
            return None


# ======================================================================
# Safety Filter (extends Chapter 13 version for multi-step plans)
# ======================================================================
class SafetyFilter:
    ALLOWED_ACTIONS = {"navigate", "pick", "place", "say"}
    MAX_COORD = 10.0
    BLOCKED_PHRASES = [
        "as fast as possible", "ignore obstacle", "override", "disable safety"
    ]

    def validate_plan(self, plan: TaskPlan) -> tuple[bool, str]:
        """Check every step in the plan before execution begins."""
        for i, step in enumerate(plan.steps):
            if step.action_type not in self.ALLOWED_ACTIONS:
                return False, f"Step {i}: unknown action '{step.action_type}'"
            if step.action_type == "navigate":
                x, y = step.params.get("x", 0), step.params.get("y", 0)
                if abs(x) > self.MAX_COORD or abs(y) > self.MAX_COORD:
                    return False, f"Step {i}: coordinate ({x},{y}) out of bounds"
            # Check all string values for dangerous phrases
            for v in step.params.values():
                if isinstance(v, str):
                    for phrase in self.BLOCKED_PHRASES:
                        if phrase in v.lower():
                            return False, f"Step {i}: blocked phrase '{phrase}'"
        return True, "OK"


# ======================================================================
# Navigator — wraps Nav2 NavigateToPose action
# ======================================================================
class Navigator:
    def __init__(self, node: Node):
        self._node = node
        self._client = ActionClient(node, NavigateToPose, 'navigate_to_pose')

    def go_to(self, x: float, y: float, yaw: float = 0.0) -> bool:
        """
        Block until the robot reaches (x, y) or navigation fails.
        Returns True on success. Yaw is in radians.
        """
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = 'map'
        goal.pose.pose.position.x = float(x)
        goal.pose.pose.position.y = float(y)
        # Convert yaw to quaternion (rotation around Z axis)
        import math
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)

        self._client.wait_for_server(timeout_sec=5.0)
        future = self._client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self._node, future)
        handle = future.result()

        if not handle.accepted:
            self._node.get_logger().error('Nav goal rejected.')
            return False

        result_future = handle.get_result_async()
        rclpy.spin_until_future_complete(self._node, result_future)
        status = result_future.result().status
        # Status 4 = SUCCEEDED in rclpy action interface
        return status == 4

    def cancel(self):
        """Cancel any in-progress navigation goal."""
        # In production: call goal_handle.cancel_goal_async() on the active handle
        self._node.get_logger().info('Navigation cancelled.')


# ======================================================================
# GraspExecutor — reuses the Chapter 12 MoveIt2 pick logic
# ======================================================================
class GraspExecutor:
    def __init__(self, node: Node):
        self._node = node
        # MoveItPy wraps the move_group action server
        self._moveit = MoveItPy(node_name='capstone_moveit')
        self._arm = self._moveit.get_planning_component('right_arm')
        self._gripper = ActionClient(
            node, GripperCommand, '/right_gripper/gripper_action'
        )

    def _set_gripper(self, position: float, effort: float = 40.0):
        goal = GripperCommand.Goal()
        goal.command.position = position
        goal.command.max_effort = effort
        self._gripper.wait_for_server(timeout_sec=5.0)
        future = self._gripper.send_goal_async(goal)
        rclpy.spin_until_future_complete(self._node, future)
        time.sleep(0.4)

    def _move_arm(self, pose: PoseStamped, speed: float = 0.3) -> bool:
        self._arm.set_start_state_to_current_state()
        self._arm.set_goal_state(pose_stamped_msg=pose, pose_link='right_hand')
        plan = self._arm.plan()
        if not plan:
            return False
        return bool(self._moveit.execute(plan.trajectory, controllers=[]))

    def pick(self, grasp_pose: PoseStamped) -> bool:
        """
        Full pick sequence — identical to Chapter 12 but wrapped for the
        capstone state machine. Returns True on success.
        """
        # Pre-grasp: 10 cm above
        pre = PoseStamped()
        pre.header = grasp_pose.header
        pre.pose = grasp_pose.pose
        pre.pose.position.z += 0.10
        if not self._move_arm(pre, speed=0.4):
            return False

        self._set_gripper(0.085, effort=10.0)  # open

        if not self._move_arm(grasp_pose, speed=0.15):  # slow descent
            return False

        self._set_gripper(0.0, effort=40.0)    # close on object

        # Retreat with object
        retreat = PoseStamped()
        retreat.header = grasp_pose.header
        retreat.pose = grasp_pose.pose
        retreat.pose.position.z += 0.20
        return self._move_arm(retreat, speed=0.2)

    def get_grasp_pose_from_camera(self, object_name: str) -> Optional[PoseStamped]:
        """
        In a real system: subscribe to /camera/depth/points, run GraspNet,
        return the best grasp pose transformed to the world frame.
        Here we return a hardcoded pose for demonstration.
        Replace this method with your perception pipeline.
        """
        self._node.get_logger().info(
            f'[PERCEIVE] Estimating grasp pose for "{object_name}"...'
        )
        # TODO: integrate GraspNet or GPD here (see Chapter 12)
        pose = PoseStamped()
        pose.header.frame_id = 'world'
        pose.pose.position.x = 4.15
        pose.pose.position.y = 1.82
        pose.pose.position.z = 0.95
        pose.pose.orientation.x = 1.0
        pose.pose.orientation.w = 0.0
        return pose


# ======================================================================
# AutonomousHumanoid — the top-level state machine node
# ======================================================================
class AutonomousHumanoid(Node):
    WAKE_PHRASE = "hey robot"

    def __init__(self):
        super().__init__('autonomous_humanoid')

        # Component initialization
        self._audio = AudioCapture()
        self._asr = WhisperModel("small", device="cpu", compute_type="int8")
        self._planner = TaskPlanner()
        self._safety = SafetyFilter()
        self._nav = Navigator(self)
        self._grasp = GraspExecutor(self)

        # State machine
        self._state = RobotState.IDLE
        self._current_plan: Optional[TaskPlan] = None

        # Log every state transition for post-run debugging
        self._log_file = open(
            f'/tmp/humanoid_{int(time.time())}.log', 'w'
        )
        self._transition(RobotState.IDLE, reason="startup")
        self.get_logger().info('AutonomousHumanoid ready.')

    def _transition(self, new_state: RobotState, reason: str = ""):
        """Log every state transition with timestamp."""
        ts = time.strftime('%H:%M:%S')
        msg = f"[{ts}] {self._state.value} -> {new_state.value}"
        if reason:
            msg += f" ({reason})"
        self._log_file.write(msg + "\n")
        self._log_file.flush()
        self.get_logger().info(msg)
        self._state = new_state

    def _transcribe(self, audio: np.ndarray) -> str:
        segs, _ = self._asr.transcribe(audio, beam_size=5, language="en")
        return " ".join(s.text.strip() for s in segs).strip().lower()

    # ------------------------------------------------------------------
    # Step handlers — one method per state
    # ------------------------------------------------------------------
    def _handle_idle(self):
        """In IDLE, wait for a speech segment containing the wake phrase."""
        seg = self._audio.get(timeout=1.0)
        if seg is None:
            return
        text = self._transcribe(seg)
        if self.WAKE_PHRASE in text:
            self._transition(RobotState.LISTENING, reason="wake phrase detected")

    def _handle_listening(self):
        """In LISTENING, capture one full speech segment as the command."""
        self.get_logger().info('[LISTEN] Listening for command...')
        seg = self._audio.get(timeout=8.0)
        if seg is None:
            self._transition(RobotState.IDLE, reason="listen timeout")
            return
        text = self._transcribe(seg)
        # Strip the wake phrase if repeated
        instruction = text.replace(self.WAKE_PHRASE, "").strip(" ,.")
        self.get_logger().info(f'[ASR] Instruction: "{instruction}"')

        if not instruction:
            self._transition(RobotState.IDLE, reason="empty instruction")
            return

        # Store instruction for the planning step
        self._pending_instruction = instruction
        self._transition(RobotState.PLANNING, reason=f'instruction="{instruction}"')

    def _handle_planning(self):
        """Call the LLM, validate the plan through the safety filter."""
        self.get_logger().info('[PLAN] Generating task plan...')
        plan = self._planner.plan(self._pending_instruction)

        if plan is None or not plan.steps:
            self.get_logger().error('[PLAN] LLM returned no valid plan.')
            self._transition(RobotState.ERROR, reason="planning failed")
            return

        # Log the full plan before execution
        for i, step in enumerate(plan.steps):
            self.get_logger().info(f'  Step {i+1}: {step.description}')

        # Safety validation of the complete plan before any motion starts
        safe, reason = self._safety.validate_plan(plan)
        if not safe:
            self.get_logger().error(f'[SAFETY] Plan blocked: {reason}')
            self._transition(RobotState.ERROR, reason=f"safety: {reason}")
            return

        self._current_plan = plan
        # Start executing — the execute loop will pick the first step
        self._transition(RobotState.NAVIGATING, reason="plan accepted")

    def _handle_execution(self):
        """
        Execute the current plan step by step.
        This method is called repeatedly from run_loop() until the plan completes.
        Each call processes one action from the plan.
        """
        if self._current_plan is None or self._current_plan.is_complete():
            self._transition(RobotState.REPORTING, reason="plan complete")
            return

        step = self._current_plan.next_step()
        self.get_logger().info(f'[EXEC] {step.description}')

        if step.action_type == "navigate":
            self._transition(RobotState.NAVIGATING, reason=step.description)
            success = self._nav.go_to(
                step.params["x"], step.params["y"]
            )
            if not success:
                self.get_logger().error('[NAV] Navigation failed.')
                self._transition(RobotState.ERROR, reason="navigation failure")
                return
            # After arriving, determine if next step needs perception
            next_s = (
                self._current_plan.steps[self._current_plan.current_step]
                if not self._current_plan.is_complete() else None
            )
            if next_s and next_s.action_type == "pick":
                self._transition(RobotState.PERCEIVING, reason="arrived at pick location")
            else:
                # Stay in execution loop for next non-pick step
                self._transition(RobotState.NAVIGATING, reason="continuing plan")

        elif step.action_type == "pick":
            self._transition(RobotState.GRASPING, reason=step.description)
            grasp_pose = self._grasp.get_grasp_pose_from_camera(
                step.params.get("object_name", "object")
            )
            if grasp_pose is None:
                self.get_logger().error('[GRASP] Could not estimate grasp pose.')
                self._transition(RobotState.ERROR, reason="perception failure")
                return
            success = self._grasp.pick(grasp_pose)
            if not success:
                self.get_logger().error('[GRASP] Pick sequence failed.')
                self._transition(RobotState.ERROR, reason="grasp failure")
                return

        elif step.action_type == "place":
            self._transition(RobotState.PLACING, reason=step.description)
            # Simplified: open gripper to place
            self._grasp._set_gripper(0.085, effort=10.0)
            self.get_logger().info(
                f'[PLACE] Placed {step.params.get("object_name")} '
                f'at {step.params.get("destination")}'
            )

        elif step.action_type == "say":
            message = step.params.get("message", "Task complete.")
            self.get_logger().info(f'[SAY] {message}')
            # In production: publish to /tts/say topic for speech synthesis
            # e.g., self._tts_pub.publish(String(data=message))

    def _handle_reporting(self):
        """Announce task completion and return to IDLE."""
        instruction = getattr(self, '_pending_instruction', 'the task')
        self.get_logger().info(f'[REPORT] Task complete: "{instruction}"')
        self._current_plan = None
        self._transition(RobotState.IDLE, reason="task complete")

    def _handle_error(self):
        """Log the error state and recover to IDLE after a brief pause."""
        self.get_logger().error('[ERROR] Entering error recovery. Waiting 3 seconds...')
        time.sleep(3.0)
        self._current_plan = None
        self._transition(RobotState.IDLE, reason="error recovery")

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------
    def run_loop(self):
        """
        Main event loop. Call this from main() in a while rclpy.ok() block.
        Each call processes the current state and triggers the appropriate handler.
        """
        state = self._state
        if state == RobotState.IDLE:
            self._handle_idle()
        elif state == RobotState.LISTENING:
            self._handle_listening()
        elif state == RobotState.PLANNING:
            self._handle_planning()
        elif state in (
            RobotState.NAVIGATING, RobotState.PERCEIVING,
            RobotState.GRASPING, RobotState.PLACING
        ):
            # All execution states share the same handler —
            # the plan step's action_type determines what actually runs.
            self._handle_execution()
        elif state == RobotState.REPORTING:
            self._handle_reporting()
        elif state == RobotState.ERROR:
            self._handle_error()

    def destroy_node(self):
        self._log_file.close()
        super().destroy_node()


# ======================================================================
# Entry point
# ======================================================================
def main():
    rclpy.init()
    robot = AutonomousHumanoid()

    # Start audio capture in background before entering the main loop
    robot._audio.start()
    print(f"[CAPSTONE] System ready. Say '{AutonomousHumanoid.WAKE_PHRASE}' to begin.")

    try:
        while rclpy.ok():
            robot.run_loop()
            # Allow ROS 2 callbacks (TF, action feedback) to process
            rclpy.spin_once(robot, timeout_sec=0.01)
    except KeyboardInterrupt:
        print("\n[CAPSTONE] Shutting down gracefully...")
    finally:
        robot.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

## Common Mistakes

1. **Sending a new navigation goal without cancelling the current one.** If a second voice command arrives while the robot is navigating, calling `send_goal_async` on an active action server queues or replaces the goal depending on the server's implementation — behavior that varies between Nav2 versions. Always cancel explicitly and wait for confirmation.

2. **Running all blocking calls on the same thread as `rclpy.spin`.** The code above uses `rclpy.spin_until_future_complete`, which blocks the main thread. In production, use a `MultiThreadedExecutor` with a `ReentrantCallbackGroup` so action feedback continues arriving while the main logic waits for a result. Failing to do this causes TF transforms to go stale and timeouts on the action server.

3. **No planning scene updates during execution.** Between navigating to the pick location and grasping, the robot's physical position has changed. The MoveIt2 planning scene must be re-published with the current robot pose and fresh depth data. Systems that update the planning scene only at startup consistently fail when grasping from positions other than the initial one.

4. **Treating the LLM plan as infallible.** The LLM may produce a syntactically valid but semantically wrong plan — for example, planning to place an object at a location the robot has not yet navigated to. Validate the plan's logical ordering (navigate before pick, pick before place) in the safety filter, not just parameter bounds.

5. **Not logging state transitions.** When a robot fails silently in a production environment, the first question is always "what state was it in when it failed?" Without timestamped state transition logs, debugging requires reproducing the failure from scratch. The `_transition()` method in the capstone code makes this a first-class concern — never skip it.

## Summary

- A complete autonomous humanoid pipeline connects ASR, LLM task planning, safety filtering, Nav2 navigation, depth-based grasp estimation, and MoveIt2 arm control through a finite state machine that logs every transition.
- Coordinate frame management (TF2) and planning scene synchronization are the two most common sources of integration failures and must be treated as explicit architectural concerns, not implementation details.
- A four-level testing strategy (unit → component → integration simulation → hardware-in-the-loop) provides confidence at each integration step before risking hardware.
- Safety must be enforced at two independent levels: a software safety filter on the LLM output before any motion begins, and a hardware E-stop that operates entirely outside the software stack.
- Structured logging of every state transition, action goal, and sensor reading is not optional — it is the primary debugging tool when the system behaves unexpectedly in the field.

## Review Questions

1. Draw the state machine defined in this chapter. For the "fetch the water bottle" scenario, trace the complete path through states from IDLE to the final return to IDLE, labeling each transition with its trigger.
2. The robot successfully navigates to the kitchen but the grasp pose estimator returns `None`. Describe exactly what happens in the capstone code and what the user would observe. How would you implement a retry strategy?
3. A second voice command ("Come back now") arrives while the robot is in the NAVIGATING state executing a pick-location approach. What changes to the `run_loop` and `_handle_idle` methods would be needed to support mid-task interruption safely?
4. Explain why `rclpy.spin_until_future_complete` is problematic in a production multi-subsystem robot. What alternative architecture would you use, and what ROS 2 primitives does it rely on?
5. Your robot passes all simulation integration tests but fails 30% of real-world pick attempts at a new location. Using only the tools described in the debugging section (rosbag2, `ros2 topic echo`, `view_frames`, log files), describe a systematic investigation plan to isolate and fix the failure.
