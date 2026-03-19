---
sidebar_position: 3
---

# Chapter 3: ROS 2 Architecture

## Learning Objectives
- Understand the core architectural components of ROS 2: nodes, topics, services, actions, and parameters
- Explain why ROS 2 uses DDS (Data Distribution Service) middleware and what advantages it provides over ROS 1
- Write functional ROS 2 nodes in Python using the rclpy library
- Distinguish between the appropriate use cases for topics, services, and actions
- Set up a ROS 2 workspace and run basic communication examples

## Introduction

The Robot Operating System (ROS) is not an operating system in the traditional sense. It is a middleware framework — a collection of tools, libraries, and conventions that provide the communication infrastructure, hardware abstraction, and development utilities that robotics engineers need to build complex systems from modular components. ROS has been the dominant robotics middleware framework since its introduction at Willow Garage in 2007, and understanding it is as essential for a robotics engineer as understanding HTTP is for a web developer.

ROS 2 is a complete redesign of ROS 1, released in 2017 and reaching production maturity with the Humble Hawksbill LTS release in 2022. The redesign was motivated by the limitations of ROS 1 in production environments: ROS 1 required a central master process whose failure brought down the entire system, it had weak real-time support, poor security, and limited support for distributed systems across multiple machines. ROS 2 addresses all of these limitations by building on the industry-standard DDS (Data Distribution Service) middleware, eliminating the central master, and providing first-class support for real-time systems.

For Python developers entering robotics, rclpy (the ROS 2 Python client library) provides a familiar, Pythonic interface to all of ROS 2's capabilities. You will write classes that inherit from `rclpy.node.Node`, create publishers and subscribers, and use ROS 2's built-in type system to exchange structured data between processes — all using Python patterns that will feel natural if you have worked with frameworks like Flask or Django. This chapter walks through the entire ROS 2 architecture from first principles, with working code you can run immediately.

## Core Concepts

### The Node: ROS 2's Fundamental Unit

A ROS 2 node is a single process (or a component within a process) that performs a specific function. The design principle is separation of concerns: rather than building a monolithic robot control program, you build a collection of focused nodes that communicate through well-defined interfaces. A humanoid robot system might have separate nodes for:

- Camera image acquisition
- Object detection (consuming camera images, publishing detections)
- Joint state reading (publishing current joint angles at 1 kHz)
- Motion planning (consuming detections and goals, publishing trajectories)
- Joint control (consuming trajectories, writing to hardware drivers)

This architecture provides modularity (you can swap out the object detection node without touching the camera node), testability (you can run a node in isolation with recorded data), and fault isolation (a crash in the object detection node does not crash the joint control node).

Every node has a unique name within the ROS 2 graph and can be run on any machine connected to the same DDS domain. The ROS 2 graph is the runtime view of all nodes and their connections.

### Topics: Publish-Subscribe Communication

Topics implement the publish-subscribe pattern — the most common communication pattern in ROS 2. A publisher node sends messages on a named topic; any number of subscriber nodes can receive those messages. Publishers and subscribers are decoupled: the publisher does not know who is listening, and subscribers do not know who is publishing.

Key properties:
- Topics are typed: every topic carries messages of a specific type (e.g., `sensor_msgs/msg/Image`, `geometry_msgs/msg/Twist`). ROS 2 enforces type safety at connection time.
- Topics are many-to-many: multiple publishers can publish to the same topic, and multiple subscribers can receive from it.
- Topics are best-effort or reliable depending on the QoS (Quality of Service) profile configured.

Topics are appropriate for **continuous streams of data**: sensor readings, robot state, video frames, point clouds.

### Services: Request-Reply Communication

Services implement synchronous request-reply communication. A service server waits for requests and sends back responses. A service client sends a request and blocks (or registers a callback) waiting for the response.

Services are appropriate for **discrete operations that need a result**: asking the robot to move to a position and confirming completion, requesting the current map, triggering a sensor calibration.

Services are not appropriate for long-running operations because the client blocks while waiting. If a service call takes 10 seconds, the calling node's execution is stalled for 10 seconds.

### Actions: Long-Running Operations with Feedback

Actions are ROS 2's solution for long-running operations where you want progress feedback. An action has three components:
- **Goal**: the initial request (e.g., "navigate to position X, Y")
- **Feedback**: periodic updates during execution (e.g., current distance remaining)
- **Result**: the final outcome when the action completes or fails

Actions are appropriate for: navigation to a goal, executing a multi-step manipulation, running a full robot calibration routine.

### Parameters: Node Configuration

ROS 2 parameters allow nodes to be configured at runtime without recompilation. Each node can declare parameters with default values; these can be overridden from launch files, the command line, or other nodes.

### DDS Middleware

ROS 2's most architecturally significant change from ROS 1 is its use of DDS (Data Distribution Service) as the underlying communication middleware. DDS is an industry-standard protocol widely used in aerospace, defense, and industrial systems. It provides:

- **Decentralized discovery**: Nodes discover each other automatically on the network without a central broker. Eliminating the ROS 1 master removes a single point of failure.
- **Quality of Service (QoS) policies**: Publishers and subscribers can negotiate reliability (reliable vs. best-effort), durability (should late-joining subscribers receive recent messages?), and deadline (how often must a message arrive?). This is critical for sensor data with different latency/reliability requirements.
- **Built-in security**: DDS-Security provides authentication, access control, and encryption — essential for robots operating in shared or adversarial environments.

The most common DDS implementations used with ROS 2 are Fast DDS (the default, from eProsima) and Cyclone DDS (favored for real-time performance).

## Hands-On: Code Example

The following examples build a complete minimal ROS 2 system: a publisher that simulates joint state data, and a subscriber that monitors the data and logs warnings when joint temperatures are too high. This pattern maps directly to real humanoid robot monitoring systems.

First, the publisher node — save as `joint_state_publisher.py`:

```python
# joint_state_publisher.py
# Simulates a robot joint state publisher — one of the most fundamental
# nodes in any real robot system. Publishes joint angles, velocities,
# and effort (torque) at a fixed rate.
#
# Run: ros2 run your_package joint_state_publisher
# (After building with colcon — see Chapter 4)

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState  # Standard ROS 2 message type
import math
import time

class JointStatePublisher(Node):
    """
    Publishes simulated joint states for a simplified humanoid robot.
    
    In a real system, this node would read from hardware via EtherCAT or CAN
    and publish the actual encoder readings. Here we simulate sinusoidal motion
    to generate interesting test data.
    """

    def __init__(self):
        # Initialize the node with a unique name.
        # The node name appears in 'ros2 node list' output.
        super().__init__('joint_state_publisher')

        # ── Publisher setup ───────────────────────────────────────────────────
        # Create a publisher on the '/joint_states' topic.
        # JointState is the standard ROS 2 message for joint data.
        # Queue size 10: if subscribers are slow, buffer up to 10 messages.
        self.publisher_ = self.create_publisher(
            JointState,
            '/joint_states',
            10  # QoS history depth
        )

        # ── Parameters ────────────────────────────────────────────────────────
        # Declare a parameter with a default value.
        # Can be overridden at launch: --ros-args -p publish_rate:=500.0
        self.declare_parameter('publish_rate', 100.0)  # Hz
        rate = self.get_parameter('publish_rate').get_parameter_value().double_value

        # ── Timer ─────────────────────────────────────────────────────────────
        # Create a timer that calls publish_joint_states at the specified rate.
        # ROS 2 timers are the standard way to run periodic callbacks.
        timer_period = 1.0 / rate  # seconds
        self.timer = self.create_timer(timer_period, self.publish_joint_states)

        # ── State ─────────────────────────────────────────────────────────────
        self.joint_names = [
            'left_hip_pitch', 'left_hip_roll', 'left_hip_yaw',
            'left_knee', 'left_ankle_pitch', 'left_ankle_roll',
            'right_hip_pitch', 'right_hip_roll', 'right_hip_yaw',
            'right_knee', 'right_ankle_pitch', 'right_ankle_roll',
            'torso_pitch', 'torso_roll',
            'left_shoulder_pitch', 'left_shoulder_roll', 'left_elbow',
            'right_shoulder_pitch', 'right_shoulder_roll', 'right_elbow',
        ]
        self.start_time = time.time()
        self.get_logger().info(
            f'JointStatePublisher started, publishing {len(self.joint_names)} '
            f'joints at {rate} Hz'
        )

    def publish_joint_states(self):
        """
        Callback called by the timer at each publish cycle.
        Constructs and publishes a JointState message.
        """
        msg = JointState()

        # ROS 2 messages use the built-in ROS time, not Python's time.time().
        # This ensures timestamps are synchronized across the ROS 2 graph.
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'

        msg.name = self.joint_names

        # Simulate sinusoidal joint motion (mimics a slow walking gait)
        t = time.time() - self.start_time
        positions = []
        velocities = []
        efforts = []

        for i, name in enumerate(self.joint_names):
            # Each joint oscillates at a slightly different phase
            phase = i * (2 * math.pi / len(self.joint_names))
            freq = 0.5  # 0.5 Hz walking gait
            amplitude = 0.3 if 'knee' in name else 0.15

            pos = amplitude * math.sin(2 * math.pi * freq * t + phase)
            vel = amplitude * 2 * math.pi * freq * math.cos(
                2 * math.pi * freq * t + phase
            )
            # Effort: simulate load-dependent torque
            effort = 30.0 * math.sin(2 * math.pi * freq * t + phase + 0.1)

            positions.append(pos)
            velocities.append(vel)
            efforts.append(effort)

        msg.position = positions
        msg.velocity = velocities
        msg.effort = efforts

        self.publisher_.publish(msg)


def main(args=None):
    # Initialize the rclpy library — must be called before any ROS 2 operations
    rclpy.init(args=args)

    node = JointStatePublisher()

    # spin() blocks and processes callbacks (timer, subscriber, etc.)
    # until the node is shut down (Ctrl+C or ros2 node kill)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # Clean up resources
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

Next, the subscriber node — save as `joint_monitor.py`:

```python
# joint_monitor.py
# Subscribes to joint states and performs health monitoring.
# Also demonstrates ROS 2 services by providing a 'get_status' service
# and actions by implementing a 'move_to_zero' action server.

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from sensor_msgs.msg import JointState
from std_srvs.srv import Trigger           # Standard service: request=empty, response=bool+string
from rclpy.callback_groups import ReentrantCallbackGroup
import threading

class JointMonitorNode(Node):
    """
    Monitors joint states published by JointStatePublisher.
    Provides:
      - Subscriber for /joint_states
      - Service '/robot/get_status' — returns current robot health summary
    """

    def __init__(self):
        super().__init__('joint_monitor')

        # ── Subscriber ────────────────────────────────────────────────────────
        # Subscribe to the same topic the publisher uses.
        # The callback is called every time a new message arrives.
        self.subscription = self.create_subscription(
            JointState,
            '/joint_states',
            self.joint_state_callback,
            10  # QoS depth
        )

        # ── Service server ────────────────────────────────────────────────────
        # Creates a service that other nodes can call to get robot status.
        # Trigger is a built-in service type: request is empty, response has
        # a bool 'success' and a string 'message'.
        self.status_service = self.create_service(
            Trigger,
            '/robot/get_status',
            self.get_status_callback
        )

        # ── Internal state ────────────────────────────────────────────────────
        self.latest_joint_state: JointState = None
        self.warning_count = 0
        self.message_count = 0

        # Thresholds for health monitoring
        self.EFFORT_WARN_THRESHOLD = 70.0   # Nm
        self.EFFORT_CRIT_THRESHOLD = 90.0   # Nm

        self.get_logger().info('JointMonitorNode started and listening...')

    def joint_state_callback(self, msg: JointState):
        """
        Called every time a new JointState message is received.
        Performs health checks and logs warnings.
        """
        self.latest_joint_state = msg
        self.message_count += 1

        # Check all joint efforts for limit violations
        for i, name in enumerate(msg.name):
            if i < len(msg.effort):
                effort = abs(msg.effort[i])

                if effort >= self.EFFORT_CRIT_THRESHOLD:
                    self.warning_count += 1
                    self.get_logger().error(
                        f'CRITICAL: Joint {name} effort {effort:.1f} Nm '
                        f'exceeds maximum limit {self.EFFORT_CRIT_THRESHOLD} Nm!'
                    )
                elif effort >= self.EFFORT_WARN_THRESHOLD:
                    self.warning_count += 1
                    self.get_logger().warn(
                        f'WARNING: Joint {name} effort {effort:.1f} Nm '
                        f'approaching limit'
                    )

        # Log a summary every 100 messages
        if self.message_count % 100 == 0:
            self.get_logger().info(
                f'Processed {self.message_count} joint state messages, '
                f'{self.warning_count} warnings issued.'
            )

    def get_status_callback(self, request, response):
        """
        Service callback: returns the current robot status as a string.
        Called when another node (or CLI) sends a request to /robot/get_status.

        Test from terminal: ros2 service call /robot/get_status std_srvs/srv/Trigger
        """
        if self.latest_joint_state is None:
            response.success = False
            response.message = 'No joint state data received yet.'
            return response

        # Build a status summary
        n_joints = len(self.latest_joint_state.name)
        stamp = self.latest_joint_state.header.stamp
        
        response.success = True
        response.message = (
            f'Robot status: {n_joints} joints active. '
            f'Last update: {stamp.sec}s. '
            f'Total messages: {self.message_count}. '
            f'Warnings: {self.warning_count}.'
        )
        return response


def main(args=None):
    rclpy.init(args=args)
    node = JointMonitorNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

To run this system (after building your package as shown in Chapter 4):

```bash
# Terminal 1: Start the publisher
ros2 run your_package joint_state_publisher

# Terminal 2: Start the monitor
ros2 run your_package joint_monitor

# Terminal 3: Inspect the ROS 2 graph
ros2 node list
ros2 topic list
ros2 topic echo /joint_states
ros2 topic hz /joint_states   # Verify publish rate

# Terminal 3: Call the status service
ros2 service call /robot/get_status std_srvs/srv/Trigger

# View topic info including message type and QoS settings
ros2 topic info /joint_states --verbose
```

## Common Mistakes

1. **Blocking inside callbacks**: ROS 2 executes subscriber and timer callbacks sequentially in the default single-threaded executor. Any blocking call (sleep, blocking I/O, long computation) inside a callback starves all other callbacks. Use `MultiThreadedExecutor` with `ReentrantCallbackGroup` for callbacks that need to block or run concurrently.

2. **Mismatching QoS profiles**: A publisher using `RELIABLE` QoS will not connect to a subscriber using `BEST_EFFORT` QoS. ROS 2 will silently fail to connect them. Always verify connections with `ros2 topic info --verbose` and intentionally specify QoS profiles rather than relying on defaults.

3. **Using Python time instead of ROS time**: `time.time()` gives wall clock time; `self.get_clock().now()` gives ROS time. In simulation, ROS time can be paused, rewound, or sped up. Code that uses `time.time()` for timestamps will break in simulation. Always use `self.get_clock().now()` for timestamps in ROS 2 nodes.

4. **Topic name collisions**: Multiple robots or multiple instances of a package using the same topic names will receive each other's messages. Use namespacing (`--ros-args -r __ns:=/robot1`) and fully qualified topic names to avoid this in multi-robot systems.

5. **Forgetting to declare parameters before getting them**: In ROS 2, calling `get_parameter()` on a parameter that was not declared with `declare_parameter()` raises an exception. Always declare parameters with default values in `__init__` before reading them anywhere else.

## Summary

- ROS 2 is a middleware framework that provides communication, hardware abstraction, and development tooling for robotics; it is not an operating system.
- The core communication primitives are topics (publish-subscribe for continuous streams), services (request-reply for discrete operations), and actions (long-running operations with feedback).
- ROS 2's use of DDS middleware eliminates the single-point-of-failure master process of ROS 1 and adds configurable QoS policies critical for real-time sensor data.
- rclpy nodes inherit from `rclpy.node.Node`, use `create_publisher` and `create_subscription` for topic communication, and `create_timer` for periodic callbacks.
- Proper ROS 2 development requires understanding QoS profiles, the executor model, and the distinction between ROS time and wall time.

## Review Questions

1. You are building a robot arm system where an operator sends a "pick up object" command and expects the arm to report progress (percentage complete) as it moves, then confirm success or failure when done. Which ROS 2 communication primitive (topic, service, or action) is most appropriate? Justify your answer by explaining why the other two primitives are unsuitable.

2. Explain the "ROS master problem" in ROS 1 and describe exactly how ROS 2's DDS-based architecture solves it. What specific failure scenarios are now impossible in ROS 2 that were possible in ROS 1?

3. A subscriber node is receiving messages from a LiDAR topic at 20 Hz but also needs to call a slow computer vision model that takes 150 ms per frame. Describe the problem this creates in a single-threaded executor and write pseudocode showing how you would restructure the system using ROS 2's `MultiThreadedExecutor` and callback groups.

4. Write the rclpy code for a node that publishes the robot's battery voltage (a `Float32` message) at 1 Hz on the topic `/robot/battery_voltage`, with the publish rate configurable as a ROS 2 parameter named `voltage_publish_rate`.

5. Two instances of the same robot node are running on the same ROS 2 network, both publishing to `/joint_states`. Describe the problem this causes, and explain two different ROS 2 mechanisms you could use to isolate the two robots' communication.
```

---

```markdown