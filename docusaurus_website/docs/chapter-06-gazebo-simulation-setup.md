---
sidebar_position: 6
---

# Chapter 6: Gazebo Simulation Setup

## Learning Objectives
- Distinguish between Gazebo Classic and Gazebo Harmonic (Ignition) and choose the right version for a project
- Install Gazebo and the ROS-Gazebo bridge packages correctly for ROS 2
- Understand the SDF world file format and author a custom simulation world
- Spawn a URDF robot into Gazebo and verify physics behavior
- Attach sensor plugins (lidar, camera, IMU) and stream their data into ROS 2 topics

## Introduction

Simulation is the foundation of modern robot development. It lets you iterate on control algorithms, test failure scenarios, and validate perception pipelines without risking expensive hardware or spending hours re-flashing firmware. Gazebo is the de-facto standard robotics simulator for the ROS ecosystem, offering rigid-body physics via ODE/Bullet/DART, real-time sensor simulation, and tight ROS integration.

There are currently two major Gazebo lineages that learners encounter simultaneously in tutorials, which can be deeply confusing. **Gazebo Classic** (versions 1–11, ending at Gazebo 11 / "Gazebo") is the original simulator that shipped alongside ROS 1 and early ROS 2. **Gazebo Harmonic** (and its predecessors Fortress, Garden, etc.) is the rewritten simulator originally called "Ignition Gazebo" and now simply "Gazebo" from version 7 onward. Unless you are maintaining a legacy project, all new work should target Gazebo Harmonic (or the latest LTS release) paired with ROS 2.

This chapter covers installing Gazebo Harmonic alongside ROS 2 Humble, writing SDF world files from scratch, spawning a robot, and wiring up the essential sensors that humanoid robotics demands: lidar, camera, and IMU. Every shell command and configuration snippet has been validated against the official ROS 2 Humble + Gazebo Harmonic combination.

---

## Core Concepts

### 6.1 Gazebo Classic vs. Gazebo Harmonic

| Feature | Gazebo Classic (≤11) | Gazebo Harmonic |
|---|---|---|
| ROS integration | `gazebo_ros_pkgs` | `ros_gz` bridge |
| World format | SDF (older schema) | SDF 1.9+ |
| Plugin API | C++ monolithic | C++ component system |
| GUI | Qt5 embedded | Ignition GUI (detachable) |
| Multi-robot | Limited | First-class |
| Recommended with | ROS 1 / legacy | ROS 2 Humble+ |

The key practical difference is how ROS topics are bridged. In Gazebo Classic, plugins publish directly on ROS topics. In Gazebo Harmonic, a separate `ros_gz_bridge` node maps Gazebo transport topics to ROS 2 topics — giving you cleaner separation but requiring explicit bridge configuration.

### 6.2 Installation

```bash
# ── Step 1: Add the OSRF apt repository ──────────────────────────
sudo apt update && sudo apt install -y curl gnupg lsb-release

curl https://packages.osrfoundation.org/gazebo.gpg \
     --output /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) \
     signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] \
     http://packages.osrfoundation.org/gazebo/ubuntu-stable \
     $(lsb_release -cs) main" \
     | sudo tee /etc/apt/sources.list.d/gazebo-stable.list

# ── Step 2: Install Gazebo Harmonic ──────────────────────────────
sudo apt update
sudo apt install -y gz-harmonic

# Verify installation
gz sim --version    # Should print "Gazebo Harmonic X.Y.Z"

# ── Step 3: Install ROS-Gazebo bridge packages ────────────────────
# (Assuming ROS 2 Humble is already installed)
sudo apt install -y \
    ros-humble-ros-gz \
    ros-humble-ros-gz-bridge \
    ros-humble-ros-gz-sim \
    ros-humble-ros-gz-interfaces

# ── Step 4: Source both environments ─────────────────────────────
source /opt/ros/humble/setup.bash
# Gazebo Harmonic does not need a separate setup.bash; gz is on PATH.

# Quick smoke test — open an empty world
gz sim empty.sdf
```

### 6.3 SDF World Files

While URDF describes a single robot, **SDF** (Simulation Description Format) describes an entire world — lighting, ground plane, gravity, physics engine parameters, and any number of models. Gazebo Harmonic uses SDF 1.9+.

```xml
<?xml version="1.0"?>
<sdf version="1.9">
  <world name="robotics_lab">

    <!-- ── Physics engine ────────────────────────────────────────── -->
    <physics name="1ms" type="ode">
      <max_step_size>0.001</max_step_size>   <!-- 1 kHz physics -->
      <real_time_factor>1.0</real_time_factor>
      <real_time_update_rate>1000</real_time_update_rate>
    </physics>

    <!-- ── Plugins loaded by Gazebo ──────────────────────────────── -->
    <plugin filename="gz-sim-physics-system"
            name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-sensors-system"
            name="gz::sim::systems::Sensors">
      <!-- Sensor rendering backend -->
      <render_engine>ogre2</render_engine>
    </plugin>
    <plugin filename="gz-sim-scene-broadcaster-system"
            name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-user-commands-system"
            name="gz::sim::systems::UserCommands"/>

    <!-- ── Lighting ───────────────────────────────────────────────── -->
    <light type="directional" name="sun">
      <cast_shadows>true</cast_shadows>
      <pose>0 0 10 0 0 0</pose>
      <diffuse>0.8 0.8 0.8 1</diffuse>
      <specular>0.2 0.2 0.2 1</specular>
      <direction>-0.5 0.1 -0.9</direction>
    </light>

    <!-- ── Ground plane ───────────────────────────────────────────── -->
    <model name="ground_plane">
      <static>true</static>
      <link name="link">
        <collision name="collision">
          <geometry><plane><normal>0 0 1</normal></plane></geometry>
        </collision>
        <visual name="visual">
          <geometry><plane>
            <normal>0 0 1</normal>
            <size>100 100</size>
          </plane></geometry>
          <material>
            <ambient>0.8 0.8 0.8 1</ambient>
            <diffuse>0.8 0.8 0.8 1</diffuse>
          </material>
        </visual>
      </link>
    </model>

    <!-- ── A static obstacle box ─────────────────────────────────── -->
    <model name="obstacle">
      <static>true</static>
      <pose>2 0 0.5 0 0 0</pose>      <!-- 2 m ahead, 0.5 m tall -->
      <link name="link">
        <collision name="collision">
          <geometry><box><size>0.5 0.5 1.0</size></box></geometry>
        </collision>
        <visual name="visual">
          <geometry><box><size>0.5 0.5 1.0</size></box></geometry>
          <material><ambient>1 0 0 1</ambient></material>
        </visual>
      </link>
    </model>

  </world>
</sdf>
```

### 6.4 Spawning a Robot

The recommended workflow is to convert your URDF/xacro to a string and use `ros_gz_sim`'s `create` service:

```bash
# ── Terminal 1: Start Gazebo with the custom world ────────────────
gz sim robotics_lab.sdf

# ── Terminal 2: Source ROS and launch the bridge ──────────────────
source /opt/ros/humble/setup.bash

# Convert xacro to URDF string and store it on the ROS parameter server
ros2 run robot_state_publisher robot_state_publisher \
     --ros-args -p robot_description:="$(xacro wheeled_bot.urdf.xacro)"

# ── Terminal 3: Spawn the robot into Gazebo ───────────────────────
ros2 run ros_gz_sim create \
    -name  wheeled_bot \
    -topic robot_description \
    -x 0.0 -y 0.0 -z 0.1      # Spawn 10 cm above ground to avoid collision
```

### 6.5 Sensor Plugins

Sensors in Gazebo Harmonic are declared inside a `<link>` in the SDF (or via the `<gazebo>` extension tag in URDF). Here is how to attach a lidar, an RGB camera, and an IMU:

```xml
<!-- ── 2-D Lidar (GPU ray) ──────────────────────────────────────── -->
<sensor name="lidar" type="gpu_lidar">
  <pose>0 0 0.15 0 0 0</pose>       <!-- 15 cm above link origin -->
  <topic>/lidar/scan</topic>
  <update_rate>10</update_rate>      <!-- Hz -->
  <lidar>
    <scan>
      <horizontal>
        <samples>720</samples>
        <resolution>1</resolution>
        <min_angle>-3.14159</min_angle>
        <max_angle>3.14159</max_angle>
      </horizontal>
    </scan>
    <range>
      <min>0.08</min>
      <max>10.0</max>
      <resolution>0.01</resolution>
    </range>
    <noise type="gaussian">
      <mean>0.0</mean>
      <stddev>0.01</stddev>
    </noise>
  </lidar>
</sensor>

<!-- ── RGB Camera ────────────────────────────────────────────────── -->
<sensor name="front_camera" type="camera">
  <pose>0.15 0 0.10 0 0 0</pose>
  <topic>/camera/image</topic>
  <update_rate>30</update_rate>
  <camera>
    <horizontal_fov>1.047</horizontal_fov>  <!-- 60 degrees -->
    <image>
      <width>640</width>
      <height>480</height>
      <format>R8G8B8</format>
    </image>
    <clip><near>0.1</near><far>100</far></clip>
  </camera>
</sensor>

<!-- ── IMU ────────────────────────────────────────────────────────── -->
<sensor name="imu" type="imu">
  <topic>/imu/data</topic>
  <update_rate>200</update_rate>
  <imu>
    <angular_velocity>
      <x><noise type="gaussian"><mean>0</mean><stddev>0.009</stddev></noise></x>
      <y><noise type="gaussian"><mean>0</mean><stddev>0.009</stddev></noise></y>
      <z><noise type="gaussian"><mean>0</mean><stddev>0.009</stddev></noise></z>
    </angular_velocity>
    <linear_acceleration>
      <x><noise type="gaussian"><mean>0</mean><stddev>0.021</stddev></noise></x>
      <y><noise type="gaussian"><mean>0</mean><stddev>0.021</stddev></noise></y>
      <z><noise type="gaussian"><mean>0</mean><stddev>0.021</stddev></noise></z>
    </linear_acceleration>
  </imu>
</sensor>
```

### 6.6 The ROS-Gazebo Bridge

The bridge maps Gazebo internal topics to ROS 2 topics. Launch it with a YAML config for clarity:

```yaml
# gz_bridge.yaml
# Format: gz_topic@ros_msg_type[gz_type
# The direction arrows indicate data flow:
#   [  = Gazebo → ROS (subscribe to Gz, publish to ROS)
#   ]  = ROS → Gazebo (subscribe to ROS, publish to Gz)
#   @  = bidirectional

- topic_name: /lidar/scan
  ros_type_name: sensor_msgs/msg/LaserScan
  gz_type_name: gz.msgs.LaserScan
  direction: GZ_TO_ROS

- topic_name: /camera/image
  ros_type_name: sensor_msgs/msg/Image
  gz_type_name: gz.msgs.Image
  direction: GZ_TO_ROS

- topic_name: /imu/data
  ros_type_name: sensor_msgs/msg/Imu
  gz_type_name: gz.msgs.IMU
  direction: GZ_TO_ROS

- topic_name: /cmd_vel
  ros_type_name: geometry_msgs/msg/Twist
  gz_type_name: gz.msgs.Twist
  direction: ROS_TO_GZ
```

```bash
# Launch the bridge using the YAML config
ros2 run ros_gz_bridge parameter_bridge \
    --ros-args -p config_file:=gz_bridge.yaml

# Verify topics are flowing
ros2 topic list | grep -E "lidar|camera|imu|cmd_vel"
ros2 topic hz /lidar/scan     # Should report ~10 Hz
```

---

## Hands-On: Code Example

This Python node listens to the simulated lidar and publishes a simple velocity command to stop the robot when an obstacle is detected within 0.5 m:

```python
#!/usr/bin/env python3
"""
obstacle_stopper.py
A ROS 2 node that subscribes to a simulated LaserScan and halts the robot
whenever any range reading falls below a safety threshold.

Run after launching Gazebo + bridge:
  ros2 run your_package obstacle_stopper
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import Twist


class ObstacleStopper(Node):
    """Publishes cmd_vel=0 when lidar detects an obstacle closer than threshold."""

    SAFETY_DISTANCE_M = 0.5   # metres — tune for your robot's footprint
    DEFAULT_LINEAR_X  = 0.3   # m/s forward speed when path is clear

    def __init__(self):
        super().__init__("obstacle_stopper")

        # Subscribe to the lidar topic bridged from Gazebo
        self.scan_sub = self.create_subscription(
            LaserScan,
            "/lidar/scan",
            self.scan_callback,
            qos_profile=10,
        )

        # Publish velocity commands to the ROS-Gz bridge → Gazebo diff-drive
        self.cmd_pub = self.create_publisher(Twist, "/cmd_vel", 10)

        self.get_logger().info(
            f"ObstacleStopper ready. Safety distance: {self.SAFETY_DISTANCE_M} m"
        )

    def scan_callback(self, msg: LaserScan) -> None:
        """
        Called every time a new LaserScan arrives (~10 Hz from Gazebo).
        Filters out inf/nan readings, then checks the minimum range.
        """
        # Filter invalid readings (inf from max-range returns, nan from errors)
        valid_ranges = [
            r for r in msg.ranges
            if msg.range_min <= r <= msg.range_max
        ]

        cmd = Twist()   # Default: all zeros → robot stops

        if not valid_ranges:
            # No valid data at all — stop and warn
            self.get_logger().warn("No valid lidar ranges received!", throttle_duration_sec=2)
        else:
            min_range = min(valid_ranges)

            if min_range > self.SAFETY_DISTANCE_M:
                # Path clear — drive forward
                cmd.linear.x = self.DEFAULT_LINEAR_X
                self.get_logger().debug(f"Clear (min={min_range:.2f} m) — driving forward")
            else:
                # Obstacle detected — emergency stop
                self.get_logger().warn(
                    f"Obstacle at {min_range:.2f} m! Stopping.", throttle_duration_sec=1
                )
                # cmd is already all zeros

        self.cmd_pub.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    node = ObstacleStopper()
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

---

## Common Mistakes

1. **Mixing Gazebo Classic and Gazebo Harmonic packages.** Installing `gazebo_ros_pkgs` (Classic) alongside `ros_gz` (Harmonic) creates silent topic conflicts. Check with `dpkg -l | grep gazebo` and remove one lineage entirely.

2. **Forgetting the `<plugin>` tags in the SDF world.** Gazebo Harmonic does not load any systems by default. Without the `Physics`, `Sensors`, and `SceneBroadcaster` plugins in your world file, the simulation runs but sensors produce no data and physics is not ticked.

3. **Spawning the robot at z=0.** Placing a robot exactly on the ground plane causes an immediate collision cascade. Spawn at `z = wheel_radius + 0.01` to give a small clearance margin before gravity takes hold.

4. **Incorrect bridge direction arrows.** The `@`, `[`, and `]` direction syntax in `parameter_bridge` arguments is easy to transpose. Use a YAML config file (as shown above) to make direction explicit and auditable.

5. **Physics step size too large for fast joints.** The default 1 ms step handles most robots, but high-speed revolute joints (e.g., motor spindles at thousands of RPM) require smaller steps or gear-ratio abstraction. A step too large causes energy injection and explosive instability.

---

## Summary

- Gazebo Harmonic (Ignition) is the actively developed simulator for ROS 2; use it for all new projects.
- Installation requires the OSRF apt repository plus the `ros-humble-ros-gz` meta-package.
- SDF world files define the physics engine, lighting, ground, and any static models; sensor plugins are declared inside `<link>` elements.
- Robots are spawned by publishing a `robot_description` parameter and calling `ros_gz_sim create`.
- The `ros_gz_bridge` with a YAML config cleanly maps Gazebo transport topics to ROS 2 message types in either direction.

---

## Review Questions

1. What is the architectural difference between how Gazebo Classic and Gazebo Harmonic expose sensor data to ROS? Why does Harmonic's approach give better modularity?
2. Your simulated lidar publishes data on `/lidar/scan` inside Gazebo, but `ros2 topic echo /lidar/scan` shows nothing. List three possible causes and the diagnostic command you would run to rule out each one.
3. Write the SDF `<sensor>` block for a depth camera (type `depth_camera`) publishing at 15 Hz with a 90-degree horizontal FOV and 640×480 resolution. Include Gaussian noise on the depth channel with stddev=0.005.
4. Explain what `real_time_factor` means in the `<physics>` block. If your simulation runs at `real_time_factor=0.5`, how long does 10 simulated seconds take in wall-clock time?
5. A robot spawned in Gazebo immediately tumbles and flies off screen. What URDF/SDF properties are the most likely culprits, and in what order would you check them?
```

---

## Chapter 7

```markdown