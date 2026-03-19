---
sidebar_position: 5
---

# Chapter 5: URDF & Robot Description

## Learning Objectives
- Understand the purpose and structure of the Unified Robot Description Format (URDF)
- Define links and joints (revolute, prismatic, fixed) and explain how they form a kinematic chain
- Add visual, collision, and inertial elements to a URDF model
- Write a minimal two-link robot URDF from scratch and visualize it in RViz2
- Use xacro macros to eliminate repetition and parameterize robot descriptions

## Introduction

Before a robot can move, plan, or perceive the world, the software stack must know what the robot *looks like* — its geometry, mass distribution, and how its parts connect. The Unified Robot Description Format (URDF) is the standard XML-based answer to that need in the ROS ecosystem. A URDF file encodes every rigid body (called a **link**) and every mechanical connection between bodies (called a **joint**) in a tree structure that ROS tools can parse, visualize, and feed into physics simulators.

URDF grew out of the Willow Garage era alongside ROS 1 and has remained the lingua franca of robot description ever since. Every major ROS-compatible robot — from the PR2 research platform to the Boston Dynamics Spot — ships a URDF or its parameterized cousin, xacro. Understanding URDF deeply unlocks the ability to import custom hardware into simulation, generate correct collision geometry for motion planning, and feed accurate inertia tensors into a physics engine such as Gazebo.

This chapter walks you through the format from first principles. You will build a simple two-link pendulum robot by hand, then refactor it with xacro macros to demonstrate how real robot packages manage complexity. All examples are compatible with ROS 2 Humble / Iron and RViz2.

---

## Core Concepts

### 5.1 The URDF Tree Structure

A URDF file has one root `<robot>` element containing any number of `<link>` and `<joint>` elements. Joints reference exactly two links — a **parent** and a **child** — forming a directed tree with exactly one root link (typically `base_link`). Loops are not allowed in URDF; if your mechanism has a closed kinematic chain (e.g., a parallel gripper) you must approximate it with constraints handled at the controller level.

```xml
<robot name="my_robot">
  <!-- links and joints go here -->
</robot>
```

### 5.2 Links

A `<link>` represents a single rigid body. It contains up to three child elements:

| Element | Purpose |
|---|---|
| `<visual>` | Geometry rendered in RViz2 and simulation GUIs |
| `<collision>` | Simplified geometry used by the physics/collision engine |
| `<inertial>` | Mass and inertia tensor used by the physics engine |

Separating visual and collision geometry is a best practice: visual meshes can be highly detailed STL/DAE files, while collision geometry should be convex primitives (boxes, cylinders, spheres) for fast contact detection.

```xml
<link name="base_link">
  <visual>
    <geometry>
      <box size="0.3 0.2 0.1"/>   <!-- width, depth, height in metres -->
    </geometry>
    <material name="blue">
      <color rgba="0.0 0.0 0.8 1.0"/>
    </material>
  </visual>

  <collision>
    <geometry>
      <box size="0.3 0.2 0.1"/>   <!-- same shape, kept simple -->
    </geometry>
  </collision>

  <inertial>
    <mass value="1.0"/>           <!-- kilograms -->
    <origin xyz="0 0 0" rpy="0 0 0"/>
    <!-- Inertia tensor for a solid box: Ixx=(m/12)*(y^2+z^2) etc. -->
    <inertia ixx="0.00417" ixy="0" ixz="0"
             iyy="0.00833" iyz="0"
             izz="0.01083"/>
  </inertial>
</link>
```

### 5.3 Joints

A `<joint>` connects a parent link to a child link and specifies the type of motion permitted.

| Joint Type | Degrees of Freedom | Typical Use |
|---|---|---|
| `fixed` | 0 | Rigid attachment (sensors, static brackets) |
| `revolute` | 1 rotation, limited range | Elbow, wrist, knee |
| `continuous` | 1 rotation, unlimited | Wheel |
| `prismatic` | 1 translation, limited range | Linear actuator |
| `floating` | 6 | Free-floating base (rarely used) |
| `planar` | 3 (XY + yaw) | Mobile bases |

Every joint needs an `<axis>` (the unit vector of motion), an `<origin>` (transform from parent to joint frame), and for revolute/prismatic joints, `<limit>` bounds.

```xml
<joint name="shoulder_joint" type="revolute">
  <!-- Place this joint 0.1 m above the base_link origin -->
  <origin xyz="0 0 0.1" rpy="0 0 0"/>
  <parent link="base_link"/>
  <child link="upper_arm"/>
  <!-- Rotation around the Y axis -->
  <axis xyz="0 1 0"/>
  <limit lower="-1.57" upper="1.57"   <!-- ±90° in radians -->
         effort="10.0"                 <!-- max torque in N·m -->
         velocity="1.0"/>              <!-- max speed in rad/s -->
  <dynamics damping="0.1" friction="0.0"/>
</joint>
```

### 5.4 A Complete Minimal Robot

Combining the concepts above, here is a full two-link pendulum robot:

```xml
<?xml version="1.0"?>
<robot name="pendulum">

  <!-- ── Root link (world-fixed base) ─────────────────────────── -->
  <link name="base_link">
    <visual>
      <geometry><box size="0.1 0.1 0.05"/></geometry>
      <material name="grey"><color rgba="0.5 0.5 0.5 1"/></material>
    </visual>
    <collision>
      <geometry><box size="0.1 0.1 0.05"/></geometry>
    </collision>
    <inertial>
      <mass value="0.5"/>
      <inertia ixx="0.0004" ixy="0" ixz="0"
               iyy="0.0004" iyz="0" izz="0.0008"/>
    </inertial>
  </link>

  <!-- ── Upper arm ─────────────────────────────────────────────── -->
  <link name="upper_arm">
    <visual>
      <!-- Cylinder: length 0.3 m, radius 0.02 m -->
      <origin xyz="0 0 0.15" rpy="0 0 0"/>
      <geometry><cylinder length="0.3" radius="0.02"/></geometry>
      <material name="red"><color rgba="0.8 0.0 0.0 1"/></material>
    </visual>
    <collision>
      <origin xyz="0 0 0.15" rpy="0 0 0"/>
      <geometry><cylinder length="0.3" radius="0.02"/></geometry>
    </collision>
    <inertial>
      <origin xyz="0 0 0.15"/>
      <mass value="0.3"/>
      <!-- Thin rod about end: I = (1/3)*m*l^2 for axis perpendicular to rod -->
      <inertia ixx="0.009" ixy="0" ixz="0"
               iyy="0.009" iyz="0"
               izz="0.00006"/>
    </inertial>
  </link>

  <!-- ── Shoulder joint (revolute, Y axis) ─────────────────────── -->
  <joint name="shoulder" type="revolute">
    <origin xyz="0 0 0.025"/>   <!-- top of base box -->
    <parent link="base_link"/>
    <child  link="upper_arm"/>
    <axis xyz="0 1 0"/>
    <limit lower="-3.14" upper="3.14" effort="5" velocity="2"/>
  </joint>

</robot>
```

Save this as `pendulum.urdf` and visualize it instantly with:

```bash
# Install the joint_state_publisher_gui if not already present
sudo apt install ros-humble-joint-state-publisher-gui

# Launch RViz2 with the URDF
ros2 run robot_state_publisher robot_state_publisher \
     --ros-args -p robot_description:="$(xacro pendulum.urdf)" &

ros2 run joint_state_publisher_gui joint_state_publisher_gui &

rviz2 &
# In RViz2: Add > RobotModel, set Fixed Frame to "base_link"
```

### 5.5 Xacro Macros

Real robots have dozens of identical links (fingers, wheel assemblies). Xacro (XML macro) is a pre-processor that adds variables, math expressions, conditionals, and reusable macros to URDF.

```xml
<?xml version="1.0"?>
<robot name="wheeled_bot" xmlns:xacro="http://www.ros.org/wiki/xacro">

  <!-- ── Parameters ────────────────────────────────────────────── -->
  <xacro:property name="wheel_radius"   value="0.05"/>
  <xacro:property name="wheel_width"    value="0.03"/>
  <xacro:property name="wheel_mass"     value="0.2"/>
  <xacro:property name="chassis_length" value="0.4"/>

  <!-- ── Reusable wheel macro ──────────────────────────────────── -->
  <!-- Calling: <xacro:wheel name="left_wheel" y_offset="0.15"/> -->
  <xacro:macro name="wheel" params="name y_offset">

    <link name="${name}">
      <visual>
        <!-- Cylinder defaults to Z axis; rotate 90° so it rolls on X -->
        <origin rpy="${pi/2} 0 0"/>
        <geometry>
          <cylinder radius="${wheel_radius}" length="${wheel_width}"/>
        </geometry>
        <material name="black"><color rgba="0.1 0.1 0.1 1"/></material>
      </visual>
      <collision>
        <origin rpy="${pi/2} 0 0"/>
        <geometry>
          <cylinder radius="${wheel_radius}" length="${wheel_width}"/>
        </geometry>
      </collision>
      <inertial>
        <mass value="${wheel_mass}"/>
        <!-- Solid cylinder: Ixx=Iyy=(m/12)*(3r²+h²), Izz=(m/2)*r² -->
        <inertia
          ixx="${wheel_mass/12*(3*wheel_radius**2 + wheel_width**2)}"
          ixy="0" ixz="0"
          iyy="${wheel_mass/12*(3*wheel_radius**2 + wheel_width**2)}"
          iyz="0"
          izz="${wheel_mass/2*wheel_radius**2}"/>
      </inertial>
    </link>

    <joint name="${name}_joint" type="continuous">
      <origin xyz="0 ${y_offset} 0"/>
      <parent link="base_link"/>
      <child  link="${name}"/>
      <axis xyz="0 1 0"/>
    </joint>

  </xacro:macro>

  <!-- ── Chassis ───────────────────────────────────────────────── -->
  <link name="base_link">
    <visual>
      <geometry><box size="${chassis_length} 0.3 0.05"/></geometry>
      <material name="green"><color rgba="0 0.6 0 1"/></material>
    </visual>
    <collision>
      <geometry><box size="${chassis_length} 0.3 0.05"/></geometry>
    </collision>
    <inertial>
      <mass value="2.0"/>
      <inertia ixx="0.015" ixy="0" ixz="0"
               iyy="0.027" iyz="0" izz="0.040"/>
    </inertial>
  </link>

  <!-- ── Instantiate both wheels ───────────────────────────────── -->
  <xacro:wheel name="left_wheel"  y_offset=" 0.175"/>
  <xacro:wheel name="right_wheel" y_offset="-0.175"/>

</robot>
```

Process with Python's xacro library before loading:

```python
#!/usr/bin/env python3
"""
xacro_process.py
Converts a .xacro file into a plain URDF string and writes it to disk.
Requires: pip install xacro
"""

import xacro
import pathlib

def process_xacro(input_path: str, output_path: str) -> str:
    """
    Parse a xacro file, apply all macros, and return the resulting URDF XML.

    Args:
        input_path:  Path to the .urdf.xacro source file.
        output_path: Destination path for the expanded .urdf file.

    Returns:
        The expanded URDF as a string.
    """
    # Load and process the xacro document
    doc = xacro.process_file(input_path)

    # Serialize to a UTF-8 string
    urdf_string = doc.toprettyxml(indent="  ")

    # Optionally write to disk so Gazebo / robot_state_publisher can read it
    pathlib.Path(output_path).write_text(urdf_string, encoding="utf-8")

    print(f"[xacro_process] Written {len(urdf_string)} chars → {output_path}")
    return urdf_string


if __name__ == "__main__":
    urdf = process_xacro(
        input_path="wheeled_bot.urdf.xacro",
        output_path="/tmp/wheeled_bot.urdf",
    )
    # Quick sanity check — count how many <link> tags were generated
    link_count = urdf.count("<link ")
    print(f"[xacro_process] Robot has {link_count} link(s) after macro expansion.")
```

---

## Hands-On: Code Example

The following Python script uses the `urdf_parser_py` library to programmatically inspect a URDF file and report the kinematic chain — a useful debugging technique when your robot description does not visualize as expected.

```python
#!/usr/bin/env python3
"""
inspect_urdf.py
Parses a URDF file and prints every link and joint in the kinematic tree,
showing parent → joint_type → child relationships.

Install:  pip install urdf-parser-py
Usage:    python inspect_urdf.py pendulum.urdf
"""

import sys
from urdf_parser_py.urdf import URDF

JOINT_TYPE_EMOJI = {        # purely for readable terminal output
    "fixed":      "[FXD]",
    "revolute":   "[REV]",
    "prismatic":  "[PRS]",
    "continuous": "[CNT]",
    "floating":   "[FLT]",
    "planar":     "[PLN]",
}


def print_kinematic_tree(robot: URDF, link_name: str, depth: int = 0) -> None:
    """
    Recursively walk the kinematic tree starting from link_name.
    Prints each link, then each child joint/link indented by depth.
    """
    indent = "  " * depth
    print(f"{indent}LINK  '{link_name}'")

    # Find all joints whose parent is this link
    child_joints = [j for j in robot.joints if j.parent == link_name]

    for joint in child_joints:
        tag = JOINT_TYPE_EMOJI.get(joint.joint_type, "[???]")
        print(f"{indent}  └─ {tag} joint '{joint.name}' → ", end="")
        # Recurse into the child link
        print_kinematic_tree(robot, joint.child, depth + 2)


def main():
    if len(sys.argv) < 2:
        print("Usage: python inspect_urdf.py <path_to_robot.urdf>")
        sys.exit(1)

    urdf_path = sys.argv[1]

    # Parse the URDF from file
    robot = URDF.from_xml_file(urdf_path)

    print(f"\n=== Robot: '{robot.name}' ===")
    print(f"    Links:  {len(robot.links)}")
    print(f"    Joints: {len(robot.joints)}\n")

    # Find the root link (the one that is never a child)
    child_links = {j.child for j in robot.joints}
    root_links  = [l.name for l in robot.links if l.name not in child_links]

    if not root_links:
        print("[ERROR] No root link found — URDF may contain a loop!")
        sys.exit(1)

    root = root_links[0]
    print(f"Root link: '{root}'\n")
    print_kinematic_tree(robot, root)

    # Report any links that lack inertial data (Gazebo will warn about these)
    print("\n--- Inertial coverage ---")
    for link in robot.links:
        has_inertial = link.inertial is not None
        status = "OK " if has_inertial else "MISSING"
        print(f"  [{status}] {link.name}")


if __name__ == "__main__":
    main()
```

Run it against the pendulum URDF:

```bash
python inspect_urdf.py pendulum.urdf

# Expected output:
# === Robot: 'pendulum' ===
#     Links:  2
#     Joints: 1
#
# Root link: 'base_link'
#
# LINK  'base_link'
#   └─ [REV] joint 'shoulder' →     LINK  'upper_arm'
#
# --- Inertial coverage ---
#   [OK ] base_link
#   [OK ] upper_arm
```

---

## Common Mistakes

1. **Missing inertial elements on non-fixed links.** Gazebo requires `<inertial>` for every link that is not attached with a `fixed` joint. Omitting it causes the link to be treated as infinitely light, resulting in violent simulation instability. Always compute realistic inertia tensors using the solid-body formulas or a CAD tool.

2. **Wrong axis for cylinders.** URDF cylinders are oriented along the Z axis by default. Wheels that should roll along the ground need a 90-degree rotation (`rpy="${pi/2} 0 0"`) on their `<origin>`, or the wheel will spin in the wrong plane.

3. **Using mesh files with absolute paths.** URDF mesh paths should use the `package://` URI scheme (`package://my_robot_description/meshes/arm.stl`) rather than absolute filesystem paths. Absolute paths break on other machines and inside Docker containers.

4. **Forgetting the `<limit>` on revolute/prismatic joints.** Without effort and velocity limits, some ROS controllers refuse to activate. Always specify realistic values even if the limits are wide.

5. **Xacro math without parentheses.** Xacro evaluates Python expressions inside `${}`, but operator precedence can surprise you. Write `${(a + b) * c}` rather than `${a + b * c}` when in doubt, and test the expansion with `xacro --check-order`.

---

## Summary

- A URDF file is an XML tree of **links** (rigid bodies) and **joints** (connections), rooted at `base_link`.
- Joint types (`revolute`, `prismatic`, `fixed`, `continuous`) define the motion available at each connection.
- Each link should have `<visual>`, `<collision>`, and `<inertial>` sub-elements; missing inertial data breaks physics simulation.
- Visualize any URDF instantly with `robot_state_publisher` + `joint_state_publisher_gui` + RViz2.
- **Xacro** extends URDF with properties, math, and macros — use it for any robot with repeated structures or configurable parameters.

---

## Review Questions

1. What is the difference between a `revolute` and a `continuous` joint? Give a real-world mechanical example of each.
2. A robot arm link is modeled as a solid cylinder with mass 0.5 kg, radius 0.03 m, and length 0.25 m. Write the `<inertial>` block with correct inertia tensor values (show your formula).
3. Why should collision geometry typically be simpler than visual geometry? What performance consequences arise from using high-polygon meshes for collision?
4. Your xacro file uses `${wheel_radius * 2}` to compute the wheel diameter. After expanding the macro, the URDF says `diameter="0.0"`. What likely went wrong and how do you debug it?
5. Explain why URDF cannot represent closed kinematic chains, and describe one strategy for handling a parallel gripper mechanism in a ROS-based system.
```

---

## Chapter 6

```markdown