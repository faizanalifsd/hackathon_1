---
sidebar_position: 7
---

# Chapter 7: Unity for Robotics

## Learning Objectives
- Set up the Unity Robotics Hub and ROS-TCP Connector for bidirectional ROS 2 communication
- Import a URDF robot model into Unity using the URDF Importer package
- Configure Articulation Bodies for physically realistic robot joint simulation in Unity
- Design a human-robot interaction (HRI) scene with Unity's physics and animation systems
- Write a Python ROS 2 node that exchanges messages with a Unity simulation over TCP

## Introduction

While Gazebo remains the workhorse for sensor simulation and ROS-native workflows, Unity offers capabilities that are genuinely difficult to replicate elsewhere: photorealistic rendering via the High Definition Render Pipeline (HDRP), a mature animation system for human avatars, integration with XR devices for virtual and mixed reality, and a massive asset ecosystem. For humanoid robotics research — where the robot must operate alongside, interact with, and sometimes mimic humans — Unity provides an unmatched environment for generating synthetic training data, testing interaction policies, and exploring embodied AI scenarios.

The Unity Robotics Hub is an open-source initiative from Unity Technologies that bridges the gap between Unity and ROS/ROS 2. Its two main components are the **ROS-TCP Connector** (a Unity C# package plus a Python ROS node that relay messages over TCP) and the **URDF Importer** (which parses robot description files and constructs corresponding Unity GameObjects with Articulation Bodies). Together, they let a Python ROS 2 node send joint commands into Unity and receive sensor readings back, all with minimal boilerplate.

This chapter guides you from a blank Unity project to a running human-robot interaction simulation where a ROS 2 Python node commands a robot arm to track a moving human hand target. The workflow applies to Unity 2022 LTS and later with ROS 2 Humble.

---

## Core Concepts

### 7.1 Architecture Overview

```
┌──────────────────────────────────────────────────┐
│                  Unity Editor                     │
│                                                   │
│  ArticulationBody joints ← URDF Importer          │
│  ROSConnection (C#) ←→ TCP socket :10000          │
└───────────────────────┬──────────────────────────┘
                        │  TCP / JSON messages
                        │
┌───────────────────────▼──────────────────────────┐
│  ros_tcp_endpoint (Python ROS 2 node)             │
│  Listens on port 10000, routes to ROS topics      │
└───────────────────────┬──────────────────────────┘
                        │  ROS 2 DDS
                        │
┌───────────────────────▼──────────────────────────┐
│  Your Python ROS 2 node                           │
│  Publishes joint trajectories, subscribes sensors │
└──────────────────────────────────────────────────┘
```

Messages flow in both directions: Unity publishes synthetic sensor data (joint states, camera images, contact forces) into ROS 2, and your ROS 2 controllers publish commands that Unity executes on the simulated robot.

### 7.2 Project Setup

**Prerequisites:**
- Unity Hub + Unity 2022.3 LTS (any edition)
- ROS 2 Humble installed and sourced
- Python 3.10+ with `colcon` build tools

```bash
# ── Step 1: Install the ROS-TCP Endpoint Python package ───────────
# Create or navigate to your ROS 2 workspace
mkdir -p ~/ros2_unity_ws/src && cd ~/ros2_unity_ws/src

# Clone the endpoint (this is the Python bridge node)
git clone https://github.com/Unity-Technologies/ROS-TCP-Endpoint.git

cd ~/ros2_unity_ws
colcon build --symlink-install
source install/setup.bash

# ── Step 2: Verify the endpoint node exists ───────────────────────
ros2 run ros_tcp_endpoint default_server_endpoint \
     --ros-args -p ROS_IP:=127.0.0.1 -p ROS_PORT:=10000 &

# You should see: "Starting server on 127.0.0.1:10000"
```

In Unity, install the required packages via **Window → Package Manager → Add package from git URL**:

| Package | Git URL |
|---|---|
| ROS TCP Connector | `https://github.com/Unity-Technologies/ROS-TCP-Connector.git?path=/com.unity.robotics.ros-tcp-connector` |
| URDF Importer | `https://github.com/Unity-Technologies/URDF-Importer.git?path=/com.unity.robotics.urdf-importer` |

After installation, configure the ROS connection at **Robotics → ROS Settings**:
- Protocol: **ROS2**
- ROS IP Address: `127.0.0.1`
- ROS Port: `10000`

### 7.3 Importing a URDF into Unity

```
1. Copy your robot's URDF file and its mesh assets (STL/DAE) into
   Assets/Robots/my_robot/ inside the Unity project.

2. In Unity's Project window, right-click the .urdf file →
   Import Robot From URDF.

3. In the import dialog:
   - Mesh Decomposition: VHACD (convex decomposition for collision)
   - Axis: Y-Up (Unity convention; URDF is Z-Up — the importer rotates automatically)
   - Select "Use Gravity": Yes for free links, No for base if it will be fixed

4. A GameObject hierarchy is created matching the URDF tree:
   base_link
   └── shoulder_joint (ArticulationBody)
       └── upper_arm
           └── elbow_joint (ArticulationBody)
               └── forearm
```

Each movable joint becomes an **ArticulationBody** — Unity's high-fidelity joint solver that uses Featherstone's articulated-body algorithm, the same mathematics that underlies Boston Dynamics' control stack. It is dramatically more stable than Unity's older `ConfigurableJoint` system.

### 7.4 Articulation Bodies

An `ArticulationBody` component replaces Unity's `Rigidbody` for robots. Key properties:

| Property | Meaning |
|---|---|
| `jointType` | `None` (fixed), `RevoluteJoint`, `PrismaticJoint`, `SphericalJoint` |
| `xDrive` | Drive parameters for the primary axis (spring, damper, target position/velocity) |
| `anchorPosition` | Local-space pivot point (set automatically by URDF importer) |
| `mass` | Copied from URDF `<inertial>` |
| `jointPosition` | Read-only array: current joint angles in radians |

The drive model is a PD controller baked into the physics engine:

```
torque = spring * (targetPosition − currentPosition) − damper * velocity
```

For a robot arm that must track a position command:

```csharp
// RobotJointController.cs  (attach to each ArticulationBody)
using UnityEngine;
using Unity.Robotics.ROSTCPConnector;
using RosMessageTypes.Sensor;  // JointStateMsg

public class RobotJointController : MonoBehaviour
{
    // Drag-assign each joint ArticulationBody in the Inspector
    public ArticulationBody[] joints;

    // PD drive gains — tune per joint
    [SerializeField] private float stiffness = 10000f;
    [SerializeField] private float damping    = 100f;
    [SerializeField] private float forceLimit = 1000f;

    private ROSConnection ros;

    void Start()
    {
        ros = ROSConnection.GetOrCreateInstance();

        // Subscribe to joint commands coming from the ROS 2 Python node
        ros.Subscribe<JointStateMsg>("/unity/joint_command", OnJointCommand);

        // Apply drive settings to every joint
        foreach (var joint in joints)
            ConfigureDrive(joint);
    }

    private void ConfigureDrive(ArticulationBody ab)
    {
        // Only revolute joints have an xDrive; skip fixed
        if (ab.jointType == ArticulationJointType.RevoluteJoint)
        {
            var drive = ab.xDrive;
            drive.stiffness  = stiffness;
            drive.damping    = damping;
            drive.forceLimit = forceLimit;
            ab.xDrive = drive;
        }
    }

    private void OnJointCommand(JointStateMsg msg)
    {
        // msg.position[] contains target angles in radians (ROS convention)
        for (int i = 0; i < Mathf.Min(joints.Length, msg.position.Length); i++)
        {
            var drive = joints[i].xDrive;
            // Unity's ArticulationBody expects degrees internally
            drive.target = (float)(msg.position[i] * Mathf.Rad2Deg);
            joints[i].xDrive = drive;
        }
    }
}
```

### 7.5 Human-Robot Interaction Scene Setup

For HRI scenarios you need at least: a robot, a human avatar, a task object, and a camera. Unity's built-in Humanoid avatar system combined with the Animation Rigging package provides inverse-kinematics-driven hand control:

```
Scene hierarchy:
├── Directional Light
├── Floor (plane, static)
├── Robot (URDF imported, RobotJointController attached)
├── HumanAvatar
│   ├── Animator (Humanoid rig)
│   └── Rig (Animation Rigging)
│       └── TwoBoneIKConstraint (right hand → target)
├── HandTarget (empty Transform, driven by ROS 2 via Python)
├── TaskObject (a cup, grabbable)
└── Main Camera
```

### 7.6 Publishing Joint States Back to ROS 2

Unity should also publish the robot's current joint states so your ROS 2 controllers can close the loop:

```csharp
// JointStatePublisher.cs
using UnityEngine;
using Unity.Robotics.ROSTCPConnector;
using RosMessageTypes.Sensor;
using RosMessageTypes.Std;

public class JointStatePublisher : MonoBehaviour
{
    public ArticulationBody[] joints;
    public string[] jointNames;      // Match URDF joint names exactly
    public float publishRateHz = 50f;

    private ROSConnection ros;
    private float timer;

    void Start()
    {
        ros = ROSConnection.GetOrCreateInstance();
        ros.RegisterPublisher<JointStateMsg>("/unity/joint_states");
    }

    void Update()
    {
        timer += Time.deltaTime;
        if (timer < 1f / publishRateHz) return;
        timer = 0f;

        var msg = new JointStateMsg
        {
            header = new HeaderMsg
            {
                stamp = new RosMessageTypes.BuiltinInterfaces.TimeMsg
                {
                    sec     = (int)Time.realtimeSinceStartup,
                    nanosec = (uint)((Time.realtimeSinceStartup % 1) * 1e9),
                },
                frame_id = "world",
            },
            name     = jointNames,
            position = new double[joints.Length],
            velocity = new double[joints.Length],
            effort   = new double[joints.Length],
        };

        for (int i = 0; i < joints.Length; i++)
        {
            // jointPosition[0] is in degrees for revolute joints — convert to radians
            msg.position[i] = joints[i].jointPosition[0] * Mathf.Deg2Rad;
            msg.velocity[i] = joints[i].jointVelocity[0] * Mathf.Deg2Rad;
            msg.effort[i]   = joints[i].jointAcceleration[0]; // proxy for effort
        }

        ros.Publish("/unity/joint_states", msg);
    }
}
```

---

## Hands-On: Code Example

This Python ROS 2 node commands the robot to follow a sinusoidal trajectory on its shoulder joint and prints the joint states echoed back from Unity — demonstrating the full round-trip:

```python
#!/usr/bin/env python3
"""
unity_sinusoidal_controller.py

Sends a sinusoidal joint trajectory to a Unity robot simulation via
the ROS-TCP bridge and logs the echoed joint states.

Prerequisites:
  1. Gazebo (Unity) is running with RobotJointController listening
     on /unity/joint_command.
  2. ros_tcp_endpoint is running:
       ros2 run ros_tcp_endpoint default_server_endpoint \
            --ros-args -p ROS_IP:=127.0.0.1 -p ROS_PORT:=10000
  3. This script is run in a sourced ROS 2 Humble environment.

Install message packages if needed:
  sudo apt install ros-humble-sensor-msgs
"""

import math
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState


class UnitySinusoidalController(Node):
    """
    Publishes sinusoidal position targets to a Unity robot arm
    and subscribes to the joint states published back by Unity.
    """

    # Trajectory parameters
    AMPLITUDE_RAD  = 0.8    # Peak angle in radians (~46°)
    FREQUENCY_HZ   = 0.25   # Full cycle every 4 seconds
    PUBLISH_RATE   = 50     # Hz — matches Unity publisher

    # URDF joint names must match the Unity JointStatePublisher.jointNames array
    JOINT_NAMES = ["shoulder", "elbow"]

    def __init__(self):
        super().__init__("unity_sinusoidal_controller")

        # ── Publishers ────────────────────────────────────────────
        self.cmd_pub = self.create_publisher(
            JointState,
            "/unity/joint_command",
            10,
        )

        # ── Subscribers ───────────────────────────────────────────
        self.state_sub = self.create_subscription(
            JointState,
            "/unity/joint_states",
            self.joint_state_callback,
            10,
        )

        # ── Timer for control loop ────────────────────────────────
        period = 1.0 / self.PUBLISH_RATE
        self.timer = self.create_timer(period, self.control_loop)

        self.start_time = time.time()
        self.get_logger().info("Unity sinusoidal controller started.")

    def control_loop(self) -> None:
        """Called at PUBLISH_RATE Hz. Computes and publishes target joint angles."""
        t = time.time() - self.start_time
        omega = 2.0 * math.pi * self.FREQUENCY_HZ

        # Shoulder: sinusoidal swing
        shoulder_target = self.AMPLITUDE_RAD * math.sin(omega * t)

        # Elbow: half-amplitude, opposite phase — creates a reach/retract motion
        elbow_target = (self.AMPLITUDE_RAD / 2.0) * math.sin(omega * t + math.pi)

        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name     = self.JOINT_NAMES
        msg.position = [shoulder_target, elbow_target]  # radians
        msg.velocity = []   # empty — let Unity's PD drive handle velocity
        msg.effort   = []

        self.cmd_pub.publish(msg)
        self.get_logger().debug(
            f"t={t:.2f}s  shoulder={math.degrees(shoulder_target):.1f}°  "
            f"elbow={math.degrees(elbow_target):.1f}°"
        )

    def joint_state_callback(self, msg: JointState) -> None:
        """
        Receives joint states echoed back from Unity.
        Computes and logs the position error for monitoring.
        """
        if len(msg.position) < len(self.JOINT_NAMES):
            return

        t = time.time() - self.start_time
        omega = 2.0 * math.pi * self.FREQUENCY_HZ

        # Recompute current targets to calculate error
        target_shoulder = self.AMPLITUDE_RAD * math.sin(omega * t)
        target_elbow    = (self.AMPLITUDE_RAD / 2.0) * math.sin(omega * t + math.pi)

        # Assume position order matches JOINT_NAMES
        actual_shoulder = msg.position[0]
        actual_elbow    = msg.position[1] if len(msg.position) > 1 else 0.0

        err_shoulder = abs(math.degrees(target_shoulder - actual_shoulder))
        err_elbow    = abs(math.degrees(target_elbow    - actual_elbow))

        self.get_logger().info(
            f"Joint errors → shoulder: {err_shoulder:.2f}°  elbow: {err_elbow:.2f}°"
        )


def main(args=None):
    rclpy.init(args=args)
    node = UnitySinusoidalController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
```

Run the full stack:

```bash
# Terminal 1 — ROS-TCP endpoint (bridge)
source ~/ros2_unity_ws/install/setup.bash
ros2 run ros_tcp_endpoint default_server_endpoint \
     --ros-args -p ROS_IP:=127.0.0.1 -p ROS_PORT:=10000

# Terminal 2 — Press Play in Unity first, then run the controller
source /opt/ros/humble/setup.bash
ros2 run your_package unity_sinusoidal_controller

# Terminal 3 — Monitor joint errors in real time
ros2 topic echo /unity/joint_states --field position
```

---

## Common Mistakes

1. **Pressing Play in Unity before the ROS-TCP Endpoint is running.** The C# `ROSConnection` attempts to connect at `Start()`. If the endpoint is not listening, the connection silently fails and no messages flow. Always start the Python endpoint node first, verify it prints "Listening on port 10000", then press Play.

2. **Joint angle units mismatch (degrees vs. radians).** Unity's `ArticulationBody.xDrive.target` uses **degrees** internally, while ROS `JointState.position` values are always **radians**. The C# controller code must multiply by `Mathf.Rad2Deg` when writing targets and divide by the same factor when reading back. This is the single most common source of "robot is spinning wildly" bugs.

3. **URDF mesh paths incompatible with Unity's project structure.** The URDF Importer expects mesh files to already exist under `Assets/`. If your URDF uses `package://` URIs, you must copy meshes into the project and either edit the URDF to use relative paths or configure the importer's mesh directory setting before importing.

4. **Physics timestep mismatch.** Unity's default fixed timestep is 0.02 s (50 Hz). If your ROS 2 controller publishes at 200 Hz, most commands are simply dropped. Align Unity's **Edit → Project Settings → Time → Fixed Timestep** with your ROS publish rate, or rate-limit your ROS node to match Unity.

5. **Articulation Body island sleeping.** Unity's physics engine puts ArticulationBody chains to sleep when velocities are low, which causes them to stop responding to small drive updates mid-trajectory. Disable sleep on the root ArticulationBody component (`sleepThreshold = 0`) during development to avoid this confusing behavior.

---

## Summary

- The Unity Robotics Hub connects ROS 2 and Unity via a TCP bridge: the Python `ros_tcp_endpoint` node on one side, and the C# `ROSConnection` component on the other.
- URDF robots are imported into Unity with the URDF Importer package, which creates a GameObject hierarchy with `ArticulationBody` components on each movable joint.
- `ArticulationBody` uses Featherstone's articulated-body algorithm for physically accurate joint simulation; it is configured with a PD-style `xDrive` (stiffness, damping, target position).
- Joint commands flow from Python → ROS 2 → TCP endpoint → Unity C# → ArticulationBody drive; joint states flow in the opposite direction.
- Always reconcile units (radians vs. degrees), timesteps, and connection startup order to avoid the most common integration failures.

---

## Review Questions

1. Explain the role of the `ros_tcp_endpoint` Python node. What would happen if you tried to have the Unity C# code publish directly on ROS 2 DDS without this intermediary?
2. Your robot arm's elbow joint spins to ±360° continuously instead of tracking the commanded 45° target. Without looking at the Unity console, identify the two most likely causes based on what you learned in this chapter.
3. You want to simulate a humanoid robot grasping a cup from a table. List the Unity components and ROS 2 message types you would need, and describe the data flow for a single grasp action.
4. Compare and contrast Unity's `ArticulationBody` with Gazebo's ODE physics for the purpose of simulating a 7-DOF robot arm. When would you choose one over the other?
5. Write the C# code snippet (not Python) that subscribes to a ROS 2 `geometry_msgs/Twist` message in Unity and applies the linear x velocity to move a differential-drive robot base using `ArticulationBody` drives on the left and right wheel joints.
```

---

All three chapters are complete. Here is a summary of what was produced:

**Chapter 5 — URDF & Robot Description**
- Covers the full URDF tree (links, joints, visual/collision/inertial elements) with real XML for a two-link pendulum and a xacro-parameterized wheeled robot
- Python examples: `xacro_process.py` for programmatic URDF expansion and `inspect_urdf.py` for kinematic-tree debugging using `urdf_parser_py`
- Shell commands for RViz2 visualization included

**Chapter 6 — Gazebo Simulation Setup**
- Covers Classic vs. Harmonic distinction, full installation commands, SDF world file authoring, robot spawning, and sensor plugin XML for lidar/camera/IMU
- YAML-based `ros_gz_bridge` configuration for clean topic routing
- Python ROS 2 node (`obstacle_stopper.py`) demonstrating a complete lidar-reactive control loop

**Chapter 7 — Unity for Robotics**
- Covers Unity Robotics Hub architecture, ROS-TCP Connector installation, URDF import workflow, `ArticulationBody` PD drive setup, and HRI scene design
- C# code for `RobotJointController` (command subscriber) and `JointStatePublisher` (state publisher back to ROS 2)
- Python ROS 2 node (`unity_sinusoidal_controller.py`) for a full round-trip sinusoidal trajectory test with error logging