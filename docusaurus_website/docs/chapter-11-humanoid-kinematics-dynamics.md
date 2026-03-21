---
sidebar_position: 11
---

# Chapter 11: Humanoid Kinematics & Dynamics

## Learning Objectives
- Compute forward kinematics for a serial kinematic chain using Denavit-Hartenberg (DH) parameters
- Distinguish between analytical and numerical inverse kinematics solutions and know when to use each
- Explain the Zero Moment Point (ZMP) criterion and its role in bipedal balance control
- Use MoveIt2 to plan and execute IK-based trajectories in a ROS 2 workspace
- Implement a numerical IK solver using scipy for a simplified robot arm

## Introduction

Kinematics is the study of motion without regard to forces; dynamics adds forces and inertia to the picture. For humanoid robots, both are essential: kinematics tells the robot where its limbs are and how to move them to a desired pose, while dynamics governs whether the robot remains upright during motion and how to generate the motor torques that produce a planned trajectory. A deep understanding of these topics is what separates a robot that can execute pre-programmed motions from one that can adapt its whole-body behavior in real time.

Humanoid robots are kinematically complex: a typical full-body humanoid has 30 to 60 degrees of freedom (DOF) distributed across legs, arms, a torso, and a head. This complexity makes closed-form solutions to the inverse kinematics problem rare. Instead, practitioners rely on numerical methods and specialized libraries. On the dynamics side, the key challenge unique to bipedal robots is balance: unlike wheeled or quadrupedal robots, a biped's support polygon is small and changes with every step, making whole-body balance control a continuous and critical concern.

This chapter builds your understanding from the mathematical foundations (DH parameters, transformation matrices) through practical balance theory (ZMP, center of mass control) to working code that solves IK for a robot arm using numerical optimization. You will also see how MoveIt2 integrates these concepts into a production-ready motion planning framework for ROS 2.

## Core Concepts

### Denavit-Hartenberg Parameters

The **Denavit-Hartenberg (DH) convention** is a systematic method for assigning coordinate frames to the links of a serial kinematic chain. Each joint is described by exactly four parameters:

| Parameter | Symbol | Description |
|---|---|---|
| Link length | `a` | Distance along x\_i from z\_\{i-1\} to z\_i |
| Link twist | `α` | Angle about x\_i from z\_\{i-1\} to z\_i |
| Link offset | `d` | Distance along z\_\{i-1\} from x\_\{i-1\} to x\_i |
| Joint angle | `θ` | Angle about z\_\{i-1\} from x\_\{i-1\} to x\_i (variable for revolute joints) |

The 4×4 homogeneous transformation from frame `i-1` to frame `i` is:

```
T_{i-1}^{i} = Rot_z(θ) · Trans_z(d) · Trans_x(a) · Rot_x(α)
```

**Forward kinematics (FK)** is computed by chaining these transformations from the base frame to the end-effector:

```
T_base^{ee} = T_0^1 · T_1^2 · ... · T_{n-1}^n
```

FK is always a straightforward matrix multiplication — it has a unique solution given joint angles.

### Inverse Kinematics: Analytical vs Numerical

**Inverse kinematics (IK)** asks the opposite question: given a desired end-effector pose, what joint angles produce it? This is a much harder problem.

**Analytical IK** derives closed-form equations by exploiting the specific geometry of a manipulator. It requires a specific structure (e.g., three consecutive revolute joint axes that intersect at a point — a "spherical wrist"), but when applicable it is fast (microseconds) and returns all solutions simultaneously. Most 6-DOF industrial arms (e.g., UR5, Franka Panda with proper wrist geometry) have analytical solutions.

**Numerical IK** uses iterative optimization to find joint angles that minimize the error between the current end-effector pose and the target. The most common approach uses the **Jacobian**, a matrix `J` that maps joint velocities to end-effector velocities:

```
ẋ = J(q) · q̇
```

The **Jacobian pseudoinverse** gives the joint velocity update:

```
Δq = J⁺ · Δx
```

where `Δx` is the Cartesian error between current and target pose. This is iterated until convergence. Numerical IK can handle arbitrary robot geometries and redundant DOF (more joints than the 6 needed for a general pose), but it can converge to local minima and is slower than analytical solutions.

### The Jacobian and Singularities

A **kinematic singularity** occurs when the Jacobian loses rank — some columns become linearly dependent, meaning certain end-effector motions require theoretically infinite joint velocities. Common singularities include:

- **Shoulder singularity**: two joint axes become aligned
- **Elbow singularity**: the arm is fully extended or fully folded
- **Wrist singularity**: two wrist axes become coplanar

Near singularities, numerical IK solutions become numerically unstable. In practice, **damped least squares** (also called the Levenberg-Marquardt method) adds a damping term to the pseudoinverse to prevent joint velocity blow-up:

```
Δq = (Jᵀ·J + λ²·I)⁻¹ · Jᵀ · Δx
```

The damping factor `λ` is increased near singularities and reduced far from them.

### Bipedal Balance: Zero Moment Point (ZMP)

Wheeled robots maintain balance passively (their base never tips). A biped must actively ensure its body does not fall. The key concept is the **Zero Moment Point (ZMP)**, defined as the point on the ground plane where the net moment of all inertial and gravitational forces acting on the robot has zero horizontal component.

The stability criterion is: **the ZMP must lie within the support polygon** (the convex hull of all ground contact points). If it exits the polygon, the robot will rotate about the edge of the polygon — i.e., it will fall.

For a robot in a double-support phase (both feet on the ground), the support polygon is large. During single-support (one foot), it shrinks to approximately the area of the stance foot. During a step, controlling the ZMP trajectory to stay within the shrinking and shifting support polygon is the central task of the walking controller.

### Center of Mass Control and Whole-Body Control

For slow, quasi-static motions, ZMP-based control is sufficient. For dynamic locomotion, engineers use **whole-body control (WBC)** frameworks that formulate the robot's full-body motion as a quadratic program (QP) at each timestep. The QP simultaneously:

- Tracks desired joint trajectories or task-space targets
- Satisfies contact constraints (non-slip, non-penetration)
- Ensures the contact wrench is within friction cones
- Minimizes actuation effort or joint accelerations

This is computationally demanding but allows humanoids to walk dynamically, recover from pushes, and manipulate objects while maintaining balance.

### MoveIt2 for IK and Motion Planning

**MoveIt2** is the standard ROS 2 motion planning framework. It provides:

- **IK plugins**: KDL (numerical Jacobian), TRAC-IK (improved numerical), BioIK (genetic-algorithm-based), and IKFast (analytical, auto-generated from OpenRAVE)
- **Motion planners**: OMPL (sampling-based: RRT, RRT*, PRM), CHOMP (gradient-based trajectory optimization)
- **Collision checking**: against the robot's own links and the planning scene
- **MoveGroupInterface**: a Python/C++ API that hides the complexity of the planning pipeline

MoveIt2 reads the robot's kinematic structure from a URDF file and a semantic description file (SRDF) that defines planning groups (e.g., "right_arm"), end-effectors, and self-collision exemptions.

## Hands-On: Code Example

### DH-Based Forward Kinematics and Numerical IK with scipy

```python
# chapter11_kinematics.py
# Forward kinematics using DH parameters and numerical IK using scipy.
# No special robotics library required — only numpy and scipy.
# pip install numpy scipy

import numpy as np
from scipy.optimize import minimize
from typing import List, Tuple


# ── DH Transformation Matrix ──────────────────────────────────────────────────

def dh_transform(theta: float, d: float, a: float, alpha: float) -> np.ndarray:
    """
    Compute the 4x4 homogeneous transformation matrix for one DH frame.

    Args:
        theta: Joint angle (radians) — variable for revolute joints
        d:     Link offset along z-axis (meters)
        a:     Link length along x-axis (meters)
        alpha: Link twist about x-axis (radians)

    Returns:
        4x4 numpy array representing T_{i-1}^{i}
    """
    ct, st = np.cos(theta), np.sin(theta)
    ca, sa = np.cos(alpha), np.sin(alpha)
    return np.array([
        [ct,   -st*ca,   st*sa,  a*ct],
        [st,    ct*ca,  -ct*sa,  a*st],
        [0.0,      sa,      ca,     d],
        [0.0,    0.0,     0.0,   1.0],
    ])


# ── Forward Kinematics ────────────────────────────────────────────────────────

# DH parameters for a simplified 6-DOF arm (similar to a UR3 geometry).
# Each row: [d, a, alpha] — theta is the variable joint angle.
# Units: meters and radians.
DH_PARAMS = [
    #  d      a       alpha
    [0.152,  0.000,  np.pi/2],   # Joint 1 (shoulder rotation)
    [0.000,  0.244,  0.000  ],   # Joint 2 (shoulder flex)
    [0.000,  0.213,  0.000  ],   # Joint 3 (elbow)
    [0.131,  0.000,  np.pi/2],   # Joint 4 (wrist 1)
    [0.102,  0.000, -np.pi/2],   # Joint 5 (wrist 2)
    [0.092,  0.000,  0.000  ],   # Joint 6 (wrist 3)
]


def forward_kinematics(joint_angles: np.ndarray) -> np.ndarray:
    """
    Compute end-effector pose via forward kinematics.

    Args:
        joint_angles: Array of 6 joint angles in radians.

    Returns:
        4x4 homogeneous transformation matrix (base → end-effector).
    """
    T = np.eye(4)
    for i, (d, a, alpha) in enumerate(DH_PARAMS):
        theta = joint_angles[i]
        T = T @ dh_transform(theta, d, a, alpha)
    return T


def pose_from_transform(T: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Extract (position, rotation_matrix) from a 4x4 transform."""
    return T[:3, 3], T[:3, :3]


# ── Numerical Inverse Kinematics ──────────────────────────────────────────────

def ik_cost(
    q: np.ndarray,
    target_pos: np.ndarray,
    target_rot: np.ndarray,
    pos_weight: float = 1.0,
    rot_weight: float = 0.5,
) -> float:
    """
    Cost function for IK optimization.
    Returns weighted sum of position error and rotation error.

    Args:
        q:           Current joint angle guess (6,)
        target_pos:  Desired end-effector position (3,)
        target_rot:  Desired end-effector rotation matrix (3x3)
        pos_weight:  Weight on position error
        rot_weight:  Weight on rotation error

    Returns:
        Scalar cost value
    """
    T = forward_kinematics(q)
    current_pos, current_rot = pose_from_transform(T)

    # Position error: squared Euclidean distance
    pos_error = np.sum((current_pos - target_pos) ** 2)

    # Rotation error: Frobenius norm of (R_current - R_target)
    # This is a simple proxy; geodesic distance is more correct but costlier
    rot_error = np.sum((current_rot - target_rot) ** 2)

    return pos_weight * pos_error + rot_weight * rot_error


def numerical_ik(
    target_pos: np.ndarray,
    target_rot: np.ndarray,
    initial_guess: np.ndarray = None,
    joint_limits: List[Tuple[float, float]] = None,
    tol: float = 1e-6,
) -> Tuple[np.ndarray, bool]:
    """
    Solve IK numerically using L-BFGS-B (gradient-based optimizer from scipy).

    Args:
        target_pos:    Desired end-effector position (3,)
        target_rot:    Desired end-effector rotation matrix (3x3)
        initial_guess: Starting joint angles. Defaults to zeros.
        joint_limits:  List of (lower, upper) bounds per joint in radians.
        tol:           Convergence tolerance on cost.

    Returns:
        (joint_angles, success) — best solution found and whether it converged.
    """
    n_joints = len(DH_PARAMS)

    if initial_guess is None:
        initial_guess = np.zeros(n_joints)

    if joint_limits is None:
        # Conservative default limits (±170° for most joints)
        joint_limits = [(-np.radians(170), np.radians(170))] * n_joints

    result = minimize(
        fun=ik_cost,
        x0=initial_guess,
        args=(target_pos, target_rot),
        method="L-BFGS-B",         # Good for bounded, smooth problems
        bounds=joint_limits,
        options={"ftol": tol, "gtol": 1e-7, "maxiter": 1000},
    )

    success = result.success and result.fun < 1e-4  # Threshold on cost
    return result.x, success


# ── Demo ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 1. Forward kinematics: compute EE pose for a known configuration
    q_test = np.array([0.3, -0.5, 0.8, 0.1, -0.3, 0.2])
    T_fk = forward_kinematics(q_test)
    ee_pos, ee_rot = pose_from_transform(T_fk)
    print("FK result:")
    print(f"  End-effector position: {ee_pos}")
    print(f"  End-effector rotation:\n{ee_rot}")

    # 2. Inverse kinematics: recover q_test from the EE pose
    q_ik, converged = numerical_ik(
        target_pos=ee_pos,
        target_rot=ee_rot,
        initial_guess=np.zeros(6),   # Start from home position
    )
    print(f"\nIK converged: {converged}")
    print(f"  IK solution:  {np.round(q_ik, 4)}")
    print(f"  Ground truth: {np.round(q_test, 4)}")

    # Verify by running FK on the IK solution
    T_verify = forward_kinematics(q_ik)
    pos_verify, _ = pose_from_transform(T_verify)
    pos_error = np.linalg.norm(pos_verify - ee_pos)
    print(f"  Position error after IK: {pos_error:.6f} m")
```

### MoveIt2 Python API — Sending an IK Goal

```python
# chapter11_moveit2_client.py
# Uses MoveIt2's MoveGroupInterface to plan and execute to a Cartesian target.
# Requires: ros-humble-moveit, moveit_configs_utils
# Run: ros2 run your_pkg chapter11_moveit2_client.py

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose
from moveit.planning import MoveItPy


def main():
    rclpy.init()

    # MoveItPy automatically reads the robot description from /robot_description
    moveit = MoveItPy(node_name="moveit2_ik_client")
    arm = moveit.get_planning_component("right_arm")  # SRDF group name

    # Define target pose in the robot base frame
    target_pose = Pose()
    target_pose.position.x = 0.45
    target_pose.position.y = -0.20
    target_pose.position.z = 0.30
    # Quaternion: pointing downward (gripper facing floor)
    target_pose.orientation.x = 0.0
    target_pose.orientation.y = 0.707
    target_pose.orientation.z = 0.0
    target_pose.orientation.w = 0.707

    # Set the goal as a Pose (MoveIt internally calls the IK solver)
    arm.set_goal_state(pose_stamped_msg=target_pose, pose_link="right_hand")

    # Plan using OMPL RRTConnect
    plan_result = arm.plan()
    if plan_result:
        print("Plan found! Executing...")
        moveit.execute(plan_result.trajectory, controllers=[])
    else:
        print("Planning failed — target may be unreachable or in collision.")

    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

## Common Mistakes

1. **Using the wrong DH convention.** There are two common DH variants: the "classic" (Denavit-Hartenberg 1955) and the "modified" (Craig 1986). They assign frames and parameter meanings differently. Mixing up the convention for a given robot's parameter table produces entirely wrong FK results. Always check which convention your robot's datasheet uses.

2. **Ignoring joint limits in numerical IK.** An unconstrained optimizer will happily find solutions with joint angles outside physical limits. Always pass joint limit bounds to the optimizer, or add a penalty term for limit violations.

3. **Expecting a unique IK solution.** Most 6-DOF robots have up to 16 analytical IK solutions for a given pose (due to elbow-up/elbow-down and wrist-flip configurations). Numerical IK finds one solution depending on the initial guess. For motion planning, you often want the solution closest to the current configuration — pass the current joint angles as the initial guess.

4. **Confusing ZMP with center of mass (CoM) projection.** The CoM projection onto the ground plane is only equal to the ZMP when the robot is in a static pose. During dynamic motion, inertial effects shift the ZMP away from the CoM projection. Using CoM projection as a stability criterion during fast walking leads to falls.

5. **Neglecting link inertia in dynamics calculations.** For slow manipulation tasks, kinematic planning is sufficient. For fast arm motions or whole-body dynamic locomotion, ignoring link inertia causes significant torque prediction errors. Use a rigid-body dynamics library (Pinocchio, RBDyn) for any high-speed or force-controlled task.

## Summary

- DH parameters provide a systematic 4-parameter description of each joint in a serial kinematic chain; forward kinematics chains their transformation matrices from base to end-effector.
- Analytical IK is fast and returns all solutions but requires specific robot geometry; numerical IK (Jacobian-based or optimization-based) works for any robot but is slower and may converge to local minima.
- The Jacobian maps joint velocities to end-effector velocities; near singularities it becomes rank-deficient and damped least squares must be used to prevent joint velocity blow-up.
- The Zero Moment Point (ZMP) must remain within the support polygon for a biped to remain stable; during dynamic walking this constraint drives the entire gait controller design.
- MoveIt2 provides a production-ready IK and motion planning framework for ROS 2, integrating multiple IK solvers, OMPL planners, and collision checking through a simple Python API.

## Review Questions

1. Write out the 4×4 DH transformation matrix for a joint with parameters θ=90°, d=0.1 m, a=0.3 m, α=0°. What is the end-effector position for a two-link arm with these parameters on each joint if both joint angles are 0°?
2. Why does a 6-DOF robot arm have multiple IK solutions for most end-effector poses? How would you select the "best" solution in a real application?
3. What is a kinematic singularity? Describe one physical configuration that causes a singularity in a humanoid arm and explain what goes wrong when a Jacobian pseudoinverse IK solver approaches it.
4. Explain why the ZMP and the center-of-mass ground projection are only equivalent in static conditions. What additional forces cause the ZMP to differ from the CoM projection during dynamic walking?
5. You are implementing a whole-body controller for a humanoid that must simultaneously track a hand target pose and maintain balance. Why is a QP-based whole-body controller preferred over solving arm IK and balance separately, and what constraints does the QP typically enforce?
