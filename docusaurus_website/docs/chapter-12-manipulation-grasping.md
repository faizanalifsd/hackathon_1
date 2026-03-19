---
sidebar_position: 12
---

# Chapter 12: Manipulation & Grasping

## Learning Objectives
- Distinguish between gripper types (parallel-jaw, suction, dexterous) and select the right one for a given task
- Understand grasp planning pipelines using GraspNet and GPD
- Interpret force/torque sensor data to implement compliant grasping behaviors
- Plan collision-free arm trajectories using MoveIt2 in ROS 2
- Estimate grasp poses from depth images using point cloud processing

## Introduction

Manipulation is one of the most fundamental capabilities that separates a useful humanoid robot from a mobile platform with a camera. The ability to reach into the world, pick up an object, and reposition it unlocks a vast range of tasks — from warehouse logistics to assisted living. Yet grasping is deceptively difficult: the robot must reason about object geometry, surface friction, payload weight, and the kinematics of its own arm simultaneously, all in real time and under sensor noise.

Modern manipulation pipelines combine classical robotics (kinematics, trajectory planning, force control) with learned components (grasp pose estimation, object segmentation). Understanding where each technique fits, and how they interact, is the foundation for building reliable manipulation systems. A failure anywhere in the chain — a miscalibrated depth camera, an overloaded force controller, a poorly tuned MoveIt2 planner — will cause the robot to drop the object or collide with the environment.

This chapter walks through the full manipulation stack. We start at the hardware level with gripper selection, move through perception (grasp pose estimation from depth), planning (MoveIt2), and execution (force/torque feedback). By the end, you will have a working Python script that commands a robot arm to pick up an object from a table using MoveIt2's Python API.

## Core Concepts

### Gripper Types

**Parallel-jaw grippers** are the workhorse of industrial robotics. Two flat fingers close symmetrically around an object. They are robust, fast, and easy to control — a single motor drives both jaws. The limitation is that they can only grasp objects with two nearly parallel surfaces available. The Robotiq 2F-85 is a canonical example. For a humanoid operating in a home, this gripper style handles bottles, boxes, and tools well but struggles with irregular shapes.

**Suction grippers** use a vacuum cup to adhere to flat or gently curved surfaces. They are extremely fast (no finger repositioning required) and work well in e-commerce fulfillment. Their weakness is sensitivity to surface texture and porosity — they fail on mesh bags or highly curved surfaces. Many warehouse robots (Amazon Sparrow) use suction as their primary end-effector.

**Dexterous hands** replicate the human hand with three to five fingers and multiple degrees of freedom per finger. The SHADOW Dexterous Hand and the Inspire-Robots RH56 fall into this category. They can perform in-hand manipulation — repositioning an object within the grasp without setting it down — which is critical for tasks like turning a door handle or unscrewing a cap. The trade-off is mechanical complexity, higher failure rates, and significantly harder control problems.

For most humanoid deployments today, a two-finger or three-finger underactuated gripper (fingers that passively conform to object shape via springs) offers the best capability/reliability trade-off.

### Grasp Planning: GPD and GraspNet

**Grasp Pose Detection (GPD)** is a classical learning-based approach that takes a 3D point cloud of a scene, samples grasp candidates (each defined by a 6-DoF pose for the gripper), and scores them using a convolutional neural network trained on simulated and real grasp data. GPD outputs a ranked list of grasps; the planner selects the highest-scoring reachable one.

**GraspNet-1Billion** is a large-scale dataset and associated model (from CUHK) trained on over one billion grasp annotations across hundreds of objects. The model takes an organized depth image and returns dense per-pixel grasp quality scores along with grasp orientations. GraspNet generalizes better to novel objects and cluttered scenes than GPD because of its training scale.

Both approaches output a **grasp pose**: a 4x4 homogeneous transformation matrix describing where the gripper should be and how it should be oriented in the world frame when it closes. This pose is then passed to the motion planner.

### Force/Torque Sensing

A 6-axis force/torque (F/T) sensor mounted at the wrist measures the forces and torques acting on the end-effector. This data is essential for:

- **Contact detection**: knowing when the gripper has touched the object without relying on position alone
- **Compliant insertion**: inserting a peg into a hole by moving in the direction of measured force error (force-guided insertion)
- **Grasp quality monitoring**: detecting slip by watching for sudden changes in tangential force
- **Safety**: stopping the arm if contact forces exceed a threshold, protecting both the robot and environment

The ATI Mini45 and Rokubi are popular wrist-mounted F/T sensors. In ROS 2, they publish `geometry_msgs/WrenchStamped` messages.

### MoveIt2 Motion Planning

MoveIt2 is the standard ROS 2 library for robot arm motion planning. It wraps multiple planning backends (OMPL, CHOMP, PILZ) behind a unified API. The key concepts are:

- **Planning Scene**: a representation of the robot, its collision geometry, and all known obstacles in the workspace
- **MoveGroup**: the planning interface for a named group of joints (e.g., `"right_arm"`)
- **Pose Goal vs. Joint Goal**: you can command the arm to reach a Cartesian end-effector pose (MoveIt solves IK internally) or a specific set of joint angles
- **Cartesian Path**: a sequence of waypoints the end-effector must pass through exactly, computed via interpolation rather than sampling-based planning

MoveIt2's Python API (`moveit_py`) was rewritten for ROS 2 and is the recommended interface for Python-based manipulation code.

### Whole-Body Manipulation

For humanoid robots, manipulation is not just an arm problem. When reaching far objects, the robot must coordinate its base, torso, and arm simultaneously — a problem called **whole-body manipulation**. Frameworks like OCS2 and Pink (a Python inverse kinematics library) support whole-body IK, treating all joints including the floating base as decision variables. This is an active research area; most production deployments still use a decoupled strategy (navigate close, then use the arm).

## Hands-On: Code Example

The following Python script uses MoveIt2's Python API (`moveit_py`) to move a robot arm to a pre-grasp pose above an object, open the gripper, descend to the grasp pose, close the gripper, and retreat. This assumes a robot with a MoveIt2-configured planning group named `"right_arm"` and a gripper action server.

```python
#!/usr/bin/env python3
"""
chapter12_grasp.py
Demonstrates a full pick sequence using MoveIt2's Python API (moveit_py).
Prerequisites:
    - ROS 2 Humble or later
    - moveit_py installed (ros-humble-moveit-py)
    - A running robot driver or simulation (e.g., Gazebo with a UR5e)
    - MoveIt2 move_group node running for "right_arm"
Run:
    ros2 run your_package chapter12_grasp.py
"""

import rclpy
from rclpy.node import Node
import numpy as np
from geometry_msgs.msg import PoseStamped
from moveit.planning import MoveItPy                      # moveit_py high-level interface
from moveit.core.robot_state import RobotState
from control_msgs.action import GripperCommand
from rclpy.action import ActionClient
import time


class GraspExecutor(Node):
    def __init__(self):
        super().__init__('grasp_executor')

        # --- MoveIt2 initialization ---
        # MoveItPy connects to the move_group node automatically via ROS 2 topics.
        self.moveit = MoveItPy(node_name='grasp_executor_moveit')
        self.arm = self.moveit.get_planning_component('right_arm')

        # Gripper action client — sends open/close commands to the hardware interface.
        self._gripper_client = ActionClient(
            self, GripperCommand, '/right_gripper/gripper_action'
        )

        self.get_logger().info('GraspExecutor ready.')

    # ------------------------------------------------------------------
    # Helper: send a Cartesian pose goal to the arm and execute it
    # ------------------------------------------------------------------
    def move_to_pose(self, pose: PoseStamped, velocity_scale: float = 0.3) -> bool:
        """
        Plan and execute motion to a target end-effector pose.
        velocity_scale: fraction of max joint velocity (0.0-1.0)
        Returns True on success, False on planning or execution failure.
        """
        self.arm.set_start_state_to_current_state()
        self.arm.set_goal_state(pose_stamped_msg=pose, pose_link='right_hand')

        # Plan — returns a PlanningResult with trajectory and status
        plan_result = self.arm.plan()
        if not plan_result:
            self.get_logger().error('Planning failed!')
            return False

        # Execute the planned trajectory on the real (or simulated) hardware
        robot_trajectory = plan_result.trajectory
        success = self.moveit.execute(robot_trajectory, controllers=[])
        if not success:
            self.get_logger().error('Execution failed!')
        return success

    # ------------------------------------------------------------------
    # Helper: open or close the gripper
    # ------------------------------------------------------------------
    def set_gripper(self, position: float, max_effort: float = 50.0):
        """
        position: 0.0 = fully closed, 0.085 = fully open (meters for Robotiq 2F-85)
        max_effort: Newtons — limits squeeze force to protect fragile objects
        """
        goal = GripperCommand.Goal()
        goal.command.position = position
        goal.command.max_effort = max_effort
        self._gripper_client.wait_for_server()
        future = self._gripper_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future)
        time.sleep(0.5)   # brief pause for gripper to settle mechanically

    # ------------------------------------------------------------------
    # Main pick sequence
    # ------------------------------------------------------------------
    def pick(self, grasp_pose: PoseStamped):
        """
        Full pick sequence:
            1. Move to pre-grasp (10 cm above grasp pose)
            2. Open gripper
            3. Descend to grasp pose (straight-line Cartesian move)
            4. Close gripper
            5. Retreat upward
        """
        # --- Step 1: Pre-grasp pose (offset 10 cm above the grasp along world Z) ---
        pre_grasp = PoseStamped()
        pre_grasp.header = grasp_pose.header
        pre_grasp.pose = grasp_pose.pose
        pre_grasp.pose.position.z += 0.10   # 10 cm vertical clearance
        self.get_logger().info('Moving to pre-grasp...')
        if not self.move_to_pose(pre_grasp, velocity_scale=0.4):
            return False

        # --- Step 2: Open gripper fully before descending ---
        self.get_logger().info('Opening gripper...')
        self.set_gripper(position=0.085, max_effort=20.0)

        # --- Step 3: Straight-line descent to the grasp pose ---
        self.get_logger().info('Descending to grasp pose...')
        if not self.move_to_pose(grasp_pose, velocity_scale=0.15):   # slow for safety
            return False

        # --- Step 4: Close gripper — apply moderate force to secure the object ---
        self.get_logger().info('Closing gripper...')
        self.set_gripper(position=0.0, max_effort=40.0)

        # --- Step 5: Retreat — lift object 15 cm off the surface ---
        retreat = PoseStamped()
        retreat.header = grasp_pose.header
        retreat.pose = grasp_pose.pose
        retreat.pose.position.z += 0.15
        self.get_logger().info('Retreating with object...')
        return self.move_to_pose(retreat, velocity_scale=0.2)


def main():
    rclpy.init()
    node = GraspExecutor()

    # Example grasp pose — in practice this comes from GraspNet or GPD
    # based on a depth image of the scene.
    target = PoseStamped()
    target.header.frame_id = 'world'
    target.pose.position.x = 0.45
    target.pose.position.y = -0.10
    target.pose.position.z = 0.80
    # Quaternion: gripper pointing straight down (top-down grasp)
    target.pose.orientation.x = 1.0
    target.pose.orientation.y = 0.0
    target.pose.orientation.z = 0.0
    target.pose.orientation.w = 0.0

    success = node.pick(target)
    node.get_logger().info(f'Pick {"succeeded" if success else "FAILED"}')

    rclpy.shutdown()


if __name__ == '__main__':
    main()
```

The `velocity_scale=0.15` on the descent step is intentional — slow approach gives the force/torque sensor time to detect unexpected contact before the arm stalls against an obstacle.

## Common Mistakes

1. **Skipping collision object registration.** If you do not add the table, the object itself, or any obstacles to the MoveIt2 planning scene before planning, the planner will happily generate trajectories that collide with them. Always publish `CollisionObject` messages to `/collision_object` before calling `plan()`.

2. **Gripper frame confusion.** Grasp poses from GraspNet are typically expressed relative to the camera frame. Forgetting to transform them into the robot's `world` or `base_link` frame before passing them to MoveIt2 is the single most common source of grasping failures in new setups. Always check `tf2_ros.Buffer.transform()` output visually in RViz before running on hardware.

3. **Commanding zero max_effort.** Sending a gripper goal with `max_effort=0` usually results in no motor current and a gripper that never closes. Always set a positive, object-appropriate effort limit.

4. **Ignoring IK failure modes.** MoveIt2's IK solver can fail for poses that are kinematically reachable but unreachable given joint limits. Wrapping `plan()` results without checking the status flag leads to silent failures where the arm stays still while the code proceeds to close the gripper on air.

5. **Treating grasp planning as offline.** Objects move. If you compute the grasp pose from an image captured 3 seconds before execution, the object may have shifted (especially on a vibrating table or conveyor). Timestamp and re-verify grasp poses immediately before descent.

## Summary

- Gripper selection (parallel-jaw, suction, dexterous) is driven by object geometry, surface properties, and whether in-hand manipulation is required.
- GraspNet and GPD turn depth images or point clouds into ranked 6-DoF grasp pose candidates.
- Force/torque sensing at the wrist enables compliant behavior, contact detection, and slip monitoring during grasp execution.
- MoveIt2 provides a unified Python API for planning and executing collision-free arm trajectories to Cartesian or joint-space goals.
- A complete pick sequence consists of pre-grasp approach, gripper opening, slow descent, gripper closing, and vertical retreat — each step requiring careful error checking.

## Review Questions

1. A robot needs to pick mesh laundry bags from a pile. Which gripper type is most appropriate, and why would the other two types fail?
2. What is the role of the planning scene in MoveIt2, and what happens if it does not include the robot's table surface?
3. Explain the difference between a joint-space goal and a Cartesian pose goal in MoveIt2. When would you prefer each?
4. A grasp executor reliably picks objects in simulation but fails on the real robot — the gripper always closes on air 2 cm to the left of the object. List three possible causes and describe how you would isolate each one.
5. How does a force/torque sensor improve the reliability of a peg-in-hole insertion task compared to a pure position-controlled approach?
