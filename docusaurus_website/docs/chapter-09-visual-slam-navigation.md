---
sidebar_position: 9
---

# Chapter 9: Visual SLAM & Navigation

## Learning Objectives
- Understand the core principles of Visual SLAM and how feature-based and direct methods differ
- Compare ORB-SLAM3 and RTAB-Map for different robot platforms and sensor configurations
- Configure the Nav2 stack, including costmaps, path planners, and the behavior tree executor
- Describe the unique navigation challenges posed by bipedal and humanoid robots
- Write a Nav2 action client in Python to send navigation goals programmatically

## Introduction

Simultaneous Localization and Mapping (SLAM) is the process by which a robot builds a map of an unknown environment while simultaneously tracking its own position within that map. Visual SLAM (vSLAM) accomplishes this using cameras rather than — or in addition to — laser rangefinders. This matters for humanoid robots because cameras are lightweight, power-efficient, and information-rich, whereas lidar units are heavy and expensive. Understanding vSLAM is therefore foundational to building robots that can navigate in unstructured, real-world environments.

The Robot Operating System 2 (ROS 2) navigation stack, known as **Nav2**, is the standard framework for autonomous mobile robot navigation. Nav2 provides a modular pipeline: it ingests sensor data, builds occupancy costmaps, runs path planners, executes motion controllers, and handles recovery behaviors — all coordinated through a behavior tree. While Nav2 was originally designed for wheeled robots, the community has extended it to support legged and humanoid platforms, though with notable additional complexity around stability constraints.

This chapter covers the theoretical foundations of vSLAM, the practical configuration of Nav2, and the specific adaptations needed for bipedal navigation. By the end you will be able to launch a complete mapping and navigation stack from a ROS 2 launch file and send goals to it from a Python action client.

## Core Concepts

### Visual SLAM Fundamentals

All vSLAM systems maintain three data structures:
- **Map**: a set of 3D landmarks (points or voxels) in the world frame
- **Keyframes**: a sparse set of camera poses from which landmarks were observed
- **Graph**: edges connecting keyframes via relative pose constraints, used for loop closure

**Feature-based methods** (e.g., ORB-SLAM3) extract and match sparse keypoints across frames. ORB-SLAM3 uses ORB (Oriented FAST and Rotated BRIEF) descriptors, which are fast to compute and rotation-invariant. It supports monocular, stereo, and RGB-D camera configurations, as well as optional IMU fusion for metric scale recovery in monocular setups. Loop closures are detected by comparing a current frame's bag-of-words descriptor against a database of past keyframes.

**Dense/semi-dense methods** (e.g., RTAB-Map) build richer maps by storing RGB-D point clouds or occupancy grids rather than sparse feature points. **RTAB-Map** (Real-Time Appearance-Based Mapping) is a graph-SLAM library with built-in loop-closure detection and supports a wide array of sensor combinations: RGB-D cameras (RealSense, Kinect), stereo cameras, and lidar-camera fusion. It exports maps as both 2D occupancy grids (suitable for Nav2) and 3D point clouds.

### The Nav2 Stack Architecture

Nav2 is organized into several servers that communicate via ROS 2 action interfaces:

| Server | Responsibility |
|---|---|
| `map_server` | Publishes a static or SLAM-generated occupancy grid |
| `amcl` | Particle filter localization against the static map |
| `costmap_2d` (global) | Inflates obstacles for global path planning |
| `costmap_2d` (local) | Real-time obstacle inflation for controller |
| `planner_server` | Computes global path (NavFn, Smac Planner) |
| `controller_server` | Executes path via local controller (DWB, RPP) |
| `behavior_server` | Executes recovery behaviors (spin, backup, wait) |
| `bt_navigator` | Orchestrates the above via a behavior tree |

### Costmaps: Local and Global

A **costmap** is a 2D grid where each cell holds a cost value from 0 (free) to 254 (lethal obstacle), with an inflation radius that creates a gradient around obstacles. This gradient allows planners to find paths that stay a safe distance from walls.

- **Global costmap**: built from the full static map. Updated infrequently. Used by the path planner to compute a coarse route from start to goal.
- **Local costmap**: a small rolling window (e.g., 5 m × 5 m) centered on the robot. Updated from live sensor data at high frequency. Used by the controller to avoid dynamic obstacles.

### Path Planners: NavFn and Smac

- **NavFn**: a Dijkstra/A* planner on the global costmap. Simple, reliable, but does not account for robot orientation or non-holonomic constraints. Good for wheeled robots on flat floors.
- **Smac Planner** (State-space Machine A*): supports non-holonomic (Smac 2D), Dubin's/Reeds-Shepp (Smac Hybrid-A*), and lattice-based planning. Smac Hybrid-A* generates kinematically feasible paths and is the preferred planner for differential-drive robots and humanoids because it respects turning radius constraints.

### Behavior Trees in Nav2

Nav2 uses **BehaviorTree.CPP** to define the high-level navigation logic. A behavior tree (BT) is a tree of nodes: control nodes (Sequence, Fallback, Parallel) and leaf nodes (actions and conditions). The `bt_navigator` ticks the tree at a fixed rate. A typical navigate-to-pose tree looks like:

```
Sequence
├── ComputePathToPose     (calls planner_server)
├── FollowPath            (calls controller_server)
└── Fallback
    ├── GoalReached?
    └── RecoverySequence
        ├── ClearCostmaps
        └── Spin
```

Custom BT nodes can be written in C++ or loaded as plugins, letting you add domain-specific behaviors such as "wait at elevator door" or "slow down on stairs."

### Bipedal Navigation Challenges

Wheeled robot navigation assumes a planar footprint and constant ground contact. Bipedal robots introduce three additional challenges:

1. **Footstep-aware planning**: The footprint changes with gait phase. A stepping-stone planner must verify that each individual footstep lands on stable ground.
2. **Dynamic stability constraints**: The robot's navigation speed is coupled to its balance controller. Aggressive accelerations that are fine for wheels can topple a biped.
3. **Height variation**: Bipeds can step over small obstacles, crouch under overhead beams, and traverse stairs — but the costmap must be informed of these capabilities via 3D voxel maps rather than flat 2D grids.

## Hands-On: Code Example

### Python Nav2 Action Client

```python
# chapter9_nav2_client.py
# Sends a navigation goal to the Nav2 bt_navigator action server.
# Run after: ros2 launch nav2_bringup navigation_launch.py use_sim_time:=true
#
# Install: pip install transforms3d (for quaternion conversion)

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped
import math


def euler_to_quaternion(yaw: float):
    """Convert a yaw angle (radians) to a geometry_msgs Quaternion."""
    # Only yaw is needed for 2D navigation goals
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    # Roll = 0, Pitch = 0
    return {"x": 0.0, "y": 0.0, "z": sy, "w": cy}


class Nav2GoalSender(Node):
    def __init__(self):
        super().__init__("nav2_goal_sender")
        # Connect to the NavigateToPose action server provided by bt_navigator
        self._client = ActionClient(self, NavigateToPose, "navigate_to_pose")

    def send_goal(self, x: float, y: float, yaw: float):
        """
        Send a 2D navigation goal specified in the map frame.

        Args:
            x:   Target x-position in meters
            y:   Target y-position in meters
            yaw: Target heading in radians (0 = facing +x axis)
        """
        # Wait until the action server is ready (timeout 10 s)
        self.get_logger().info("Waiting for Nav2 action server...")
        if not self._client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error("Nav2 action server not available!")
            return

        # Build the goal pose
        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = PoseStamped()
        goal_msg.pose.header.frame_id = "map"
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.pose.position.x = x
        goal_msg.pose.pose.position.y = y
        goal_msg.pose.pose.position.z = 0.0

        q = euler_to_quaternion(yaw)
        goal_msg.pose.pose.orientation.x = q["x"]
        goal_msg.pose.pose.orientation.y = q["y"]
        goal_msg.pose.pose.orientation.z = q["z"]
        goal_msg.pose.pose.orientation.w = q["w"]

        self.get_logger().info(
            f"Sending goal: x={x:.2f}, y={y:.2f}, yaw={math.degrees(yaw):.1f}°"
        )

        # Send the goal asynchronously and attach callbacks
        send_goal_future = self._client.send_goal_async(
            goal_msg,
            feedback_callback=self._feedback_callback
        )
        send_goal_future.add_done_callback(self._goal_response_callback)

    def _goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error("Goal was REJECTED by Nav2.")
            return
        self.get_logger().info("Goal ACCEPTED. Robot is navigating...")
        # Wait for the final result asynchronously
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._result_callback)

    def _feedback_callback(self, feedback_msg):
        # Feedback contains estimated time of arrival and current pose
        eta = feedback_msg.feedback.estimated_time_remaining
        self.get_logger().info(f"ETA: {eta.sec}s remaining")

    def _result_callback(self, future):
        result = future.result().result
        status = future.result().status
        if status == 4:  # SUCCEEDED
            self.get_logger().info("Navigation SUCCEEDED!")
        else:
            self.get_logger().warn(f"Navigation ended with status: {status}")
        rclpy.shutdown()


def main():
    rclpy.init()
    node = Nav2GoalSender()
    # Navigate to (3.0, 1.5) facing east (yaw=0)
    node.send_goal(x=3.0, y=1.5, yaw=0.0)
    rclpy.spin(node)


if __name__ == "__main__":
    main()
```

### Nav2 Launch File Snippet

```python
# chapter9_nav2_launch.py  (save as nav2_custom.launch.py in your package)
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    nav2_dir = get_package_share_directory("nav2_bringup")

    # ── RTAB-Map for live SLAM ────────────────────────────────────────────────
    rtabmap_node = Node(
        package="rtabmap_ros",
        executable="rtabmap",
        name="rtabmap",
        parameters=[{
            "subscribe_depth": True,
            "frame_id": "base_link",
            "Mem/IncrementalMemory": "true",  # SLAM mode (vs localization)
            "Reg/Strategy": "1",              # ICP registration
            "RGBD/AngularUpdate": "0.1",      # keyframe on 0.1 rad rotation
            "RGBD/LinearUpdate": "0.1",       # keyframe on 0.1 m translation
        }],
        remappings=[
            ("rgb/image", "/camera/color/image_raw"),
            ("depth/image", "/camera/depth/image_rect_raw"),
            ("rgb/camera_info", "/camera/color/camera_info"),
        ],
        output="screen",
    )

    # ── Nav2 bringup (uses params from nav2_params.yaml) ─────────────────────
    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_dir, "launch", "navigation_launch.py")
        ),
        launch_arguments={
            "use_sim_time": "false",
            "params_file": "/path/to/your/nav2_params.yaml",
        }.items(),
    )

    return LaunchDescription([rtabmap_node, nav2_launch])
```

## Common Mistakes

1. **Using NavFn for non-holonomic robots.** NavFn ignores robot heading and kinematic constraints. For differential-drive or legged robots, use Smac Hybrid-A* to get kinematically feasible paths that the controller can actually follow.

2. **Setting the costmap inflation radius too small.** A robot navigating with no inflation radius will plan paths that graze walls. The inflation radius should be at least the robot's inscribed radius plus a safety margin (typically 0.3–0.5 m for a humanoid).

3. **Mismatched `frame_id` in the goal PoseStamped.** The goal must be in the `map` frame. Sending a goal in `odom` or `base_link` will either fail silently or cause erratic behavior because Nav2 internally transforms everything to the map frame.

4. **Not handling loop closure latency in RTAB-Map.** Loop closure detection runs on a background thread and can briefly stall the map topic. Downstream nodes that assume a constant map update rate may miss corrections. Always subscribe to the corrected `/map` topic, not the incremental odometry.

5. **Ignoring the behavior tree timeout.** The default Nav2 BT has a navigation timeout. For slow-moving humanoids or long paths, increase `NavigateToPose.Goal.behavior_tree` timeout parameters in `nav2_params.yaml`, or the robot will abort mid-route and trigger recovery behaviors unnecessarily.

## Summary

- Visual SLAM builds a map and localizes the robot simultaneously; feature-based methods like ORB-SLAM3 use sparse keypoints, while dense methods like RTAB-Map build richer 3D maps suitable for complex environments.
- Nav2 is a modular ROS 2 navigation stack composed of map, localization, costmap, planning, control, and behavior servers orchestrated by a behavior tree.
- Global and local costmaps serve different roles: the global costmap guides macro-level path planning, while the local costmap enables real-time obstacle avoidance.
- Smac Hybrid-A* is the preferred global planner for non-holonomic and legged robots because it generates kinematically feasible paths.
- Bipedal navigation requires footstep-aware planning, stability-constrained velocity profiles, and 3D voxel costmaps rather than purely 2D occupancy grids.

## Review Questions

1. What is the fundamental difference between feature-based vSLAM (ORB-SLAM3) and dense vSLAM (RTAB-Map)? In what scenarios would you prefer each?
2. Explain the role of loop closure in a SLAM system. What happens to the map and pose estimates when a loop closure is detected?
3. A robot navigating with NavFn keeps overshooting corners and colliding with walls. What planner would you switch to, and why?
4. In the Nav2 Python action client code above, what does the feedback callback receive, and how could you use it to display a progress bar in a GUI?
5. Name two specific challenges that arise when adapting a wheeled-robot Nav2 configuration for a bipedal humanoid, and describe a technical approach to address each one.
