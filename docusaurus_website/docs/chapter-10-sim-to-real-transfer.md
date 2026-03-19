---
sidebar_position: 10
---

# Chapter 10: Sim-to-Real Transfer

## Learning Objectives
- Identify the main causes of the sim-to-real gap and categorize them as visual, physical, or dynamic
- Apply domain randomization to randomize physics, visual, and sensor parameters during training
- Use system identification to calibrate simulator parameters against real hardware measurements
- Implement noise injection in simulation to match real sensor characteristics
- Deploy a policy trained in Isaac Lab or MuJoCo to a physical robot using a ROS 2 interface

## Introduction

Training robot policies entirely in simulation offers enormous advantages: you can run thousands of parallel environments, reset instantly after failures, and collect data at a speed that would be physically impossible on real hardware. The catch is the **sim-to-real gap** — the mismatch between the simulated world where the policy was trained and the physical world where it must operate. A policy that achieves 99% success in simulation may fail completely on a real robot because the simulator modeled friction incorrectly, lighting conditions differ, or sensor noise was not represented.

Bridging the sim-to-real gap is one of the central unsolved problems in robot learning. The field has converged on several complementary strategies: **domain randomization** (intentionally widening the distribution of simulated conditions so the real world falls within it), **system identification** (carefully measuring real-world parameters and updating the simulator to match), **adaptive policies** (learning to adapt online using a small amount of real-world data), and **noise injection** (augmenting simulated observations with realistic noise models). In practice, successful sim-to-real transfers use several of these techniques together.

This chapter explains each approach in detail, shows how to implement domain randomization in Python for a physics simulation, and walks through the workflow for deploying a trained policy to physical robot hardware. The concepts apply to any simulator (Isaac Lab, MuJoCo, PyBullet, Gazebo), with Isaac Sim-specific examples highlighted where relevant.

## Core Concepts

### Causes of the Sim-to-Real Gap

The gap has three major categories:

**1. Physics modeling errors**
Rigid-body simulators approximate the real world. Key sources of error include:
- **Contact and friction**: Coulomb friction models are simplified; real contacts involve deformation, stick-slip transitions, and surface texture.
- **Actuator dynamics**: Simulators often model motors as ideal torque sources. Real actuators have backlash, compliance, inertia, and velocity-dependent damping.
- **Rigid-body approximation**: Real robot links flex slightly under load; most simulators treat them as perfectly rigid.

**2. Sensor noise and latency**
Real cameras produce motion blur, rolling-shutter artifacts, lens distortion, and spatially-varying noise. Real IMUs drift and have quantization noise. Real joint encoders have resolution limits and communication latency. Simulators typically render perfect images and return exact joint angles.

**3. Visual domain gap**
Even photorealistic renderers do not perfectly replicate real lighting, material BRDFs, dust on lenses, or the appearance of deformable objects. Policies that take image observations are particularly susceptible.

### Domain Randomization (DR)

Domain randomization addresses the gap by training across a wide distribution of simulated conditions. Instead of training with a single friction coefficient of 0.8, you sample it uniformly from [0.3, 1.2] at the start of each episode. If the real-world value falls within this range, the policy has seen it (or something like it) during training.

Parameters commonly randomized include:
- **Physics**: mass, inertia, link lengths, joint damping, friction coefficients, contact restitution
- **Actuation**: motor gain, latency, maximum torque
- **Observations**: sensor noise magnitude, observation dropout, communication delay
- **Visual** (for image-based policies): lighting color and intensity, texture randomization, camera pose perturbation, background replacement

The key insight is that a policy trained on a wide distribution generalizes better than one trained on a single point estimate — at the cost of lower peak performance in any single condition. Finding the right randomization range is an empirical process: too narrow and the real world is out-of-distribution; too wide and the problem becomes too hard to learn.

### System Identification

System identification (SysID) is the process of fitting simulator parameters to match measurements from the real robot. Rather than guessing that joint damping is 0.1 N·m·s/rad, you command known trajectories on the real robot, measure the resulting motions, and optimize simulator parameters to minimize the prediction error.

A typical SysID workflow:
1. Define a parameterized simulator model (masses, frictions, motor gains).
2. Design informative trajectories that excite the dynamics you want to identify.
3. Execute the trajectories on the real robot and log state data.
4. Run an optimization (gradient-based or Bayesian) to find simulator parameters that best reproduce the logged data.
5. Update the simulator and re-train or fine-tune the policy.

### Adaptive Policies and Domain Adaptation

**Adaptive policies** use a small context vector — computed from recent real-world observations — to infer the current dynamics and condition the policy on them. This is often called **Rapid Motor Adaptation (RMA)** in the legged locomotion literature. During simulation training, the policy learns to use a latent "privileged" vector that encodes the current domain parameters. At deployment, a second encoder (trained in simulation via supervised learning) estimates that latent vector from a short history of proprioceptive observations, without requiring any online gradient updates.

### Noise Injection

Noise injection means adding synthetic noise to simulated sensor readings to mimic real hardware:

- **Gaussian noise**: additive white noise on joint positions/velocities
- **Latency simulation**: delaying observations by a random number of timesteps sampled from a realistic distribution
- **Observation dropout**: randomly zeroing out sensor channels to simulate temporary packet loss
- **Action noise**: perturbing commanded torques to model actuator variability

## Hands-On: Code Example

The following example demonstrates a domain randomization wrapper for a MuJoCo (or any gym-compatible) environment. It randomizes physics parameters at the start of every episode — the same pattern used in Isaac Lab via `InteractiveScene` APIs.

```python
# chapter10_domain_randomization.py
# Domain randomization wrapper for any gym-compatible robot environment.
# Requires: gymnasium, mujoco (pip install gymnasium[mujoco])

import numpy as np
import gymnasium as gym
from gymnasium import Wrapper
from typing import Dict, Tuple, Any


class DomainRandomizationWrapper(Wrapper):
    """
    Wraps a MuJoCo-based Gym environment and randomizes physics parameters
    at the start of each episode.

    Randomized parameters:
    - Body masses (±20% of nominal)
    - Joint damping coefficients (±40% of nominal)
    - Floor friction (uniform sample from realistic range)
    - Observation noise (Gaussian, configurable std)
    - Action latency (0–2 timesteps delay)
    """

    def __init__(
        self,
        env: gym.Env,
        mass_scale: float = 0.2,
        damping_scale: float = 0.4,
        friction_range: Tuple[float, float] = (0.4, 1.4),
        obs_noise_std: float = 0.01,
        max_latency_steps: int = 2,
        seed: int = 42,
    ):
        super().__init__(env)
        self.mass_scale = mass_scale
        self.damping_scale = damping_scale
        self.friction_range = friction_range
        self.obs_noise_std = obs_noise_std
        self.max_latency_steps = max_latency_steps
        self.rng = np.random.default_rng(seed)

        # Cache nominal (default) physics parameters from the model
        # These are read once and used as the center of randomization
        model = self.unwrapped.model
        self._nominal_masses = model.body_mass.copy()       # shape: (nbody,)
        self._nominal_damping = model.dof_damping.copy()    # shape: (ndof,)
        self._nominal_friction = model.geom_friction.copy() # shape: (ngeom, 3)

        # Action buffer for latency simulation
        self._action_buffer = []
        self._current_latency = 0

    def reset(self, **kwargs):
        """Reset the environment and randomize physics for the new episode."""
        obs, info = self.env.reset(**kwargs)

        # ── Randomize body masses ─────────────────────────────────────────────
        model = self.unwrapped.model
        mass_multipliers = self.rng.uniform(
            1.0 - self.mass_scale,
            1.0 + self.mass_scale,
            size=self._nominal_masses.shape,
        )
        model.body_mass[:] = self._nominal_masses * mass_multipliers

        # ── Randomize joint damping ───────────────────────────────────────────
        damping_multipliers = self.rng.uniform(
            1.0 - self.damping_scale,
            1.0 + self.damping_scale,
            size=self._nominal_damping.shape,
        )
        model.dof_damping[:] = self._nominal_damping * damping_multipliers

        # ── Randomize floor friction (tangential component only) ──────────────
        new_friction = self.rng.uniform(*self.friction_range)
        # geom_friction[:, 0] is the sliding friction coefficient
        model.geom_friction[:, 0] = (
            self._nominal_friction[:, 0] * new_friction
            / self._nominal_friction[:, 0].mean()  # normalize to new mean
        )

        # ── Randomize action latency ──────────────────────────────────────────
        self._current_latency = self.rng.integers(0, self.max_latency_steps + 1)
        self._action_buffer = []

        # Add observation noise to the initial observation
        obs = self._add_obs_noise(obs)

        info["domain_params"] = {
            "mass_multipliers": mass_multipliers.tolist(),
            "damping_multipliers": damping_multipliers.tolist(),
            "floor_friction": float(new_friction),
            "latency_steps": int(self._current_latency),
        }
        return obs, info

    def step(self, action: np.ndarray):
        """
        Execute one step with latency simulation and observation noise.
        """
        # ── Action latency: buffer the action and execute a past one ──────────
        self._action_buffer.append(action.copy())
        if len(self._action_buffer) > self._current_latency + 1:
            self._action_buffer.pop(0)

        # Use the delayed action (or current one if buffer not full yet)
        delayed_action = self._action_buffer[0]

        obs, reward, terminated, truncated, info = self.env.step(delayed_action)

        # ── Add Gaussian noise to observation ────────────────────────────────
        obs = self._add_obs_noise(obs)

        return obs, reward, terminated, truncated, info

    def _add_obs_noise(self, obs: np.ndarray) -> np.ndarray:
        """Add zero-mean Gaussian noise scaled by obs_noise_std."""
        noise = self.rng.normal(0.0, self.obs_noise_std, size=obs.shape)
        return obs + noise.astype(obs.dtype)


# ── Usage example ─────────────────────────────────────────────────────────────

def train_with_dr():
    """
    Demonstrates wrapping HalfCheetah (a locomotion task) with DR.
    Replace with your humanoid environment for real use.
    """
    base_env = gym.make("HalfCheetah-v4")
    env = DomainRandomizationWrapper(
        base_env,
        mass_scale=0.2,          # ±20% mass
        damping_scale=0.4,       # ±40% damping
        friction_range=(0.3, 1.3),
        obs_noise_std=0.005,
        max_latency_steps=2,
    )

    total_reward = 0.0
    obs, info = env.reset()
    print("Domain params for episode 1:", info["domain_params"])

    for step in range(200):
        action = env.action_space.sample()   # Replace with your policy
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        if terminated or truncated:
            obs, info = env.reset()
            print(f"Episode reset at step {step}. "
                  f"New domain params: {info['domain_params']}")

    print(f"Total reward over 200 steps: {total_reward:.2f}")
    env.close()


if __name__ == "__main__":
    train_with_dr()
```

### Deploying a Trained Policy to Real Hardware via ROS 2

```python
# chapter10_policy_deploy.py
# Loads a trained PyTorch policy and publishes joint torque commands via ROS 2.
# Subscribes to /joint_states, publishes to /effort_controller/commands

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray
import torch
import numpy as np


class PolicyDeployNode(Node):
    def __init__(self, policy_path: str):
        super().__init__("policy_deploy_node")

        # Load the trained policy (TorchScript or state dict)
        self.policy = torch.jit.load(policy_path)
        self.policy.eval()
        self.get_logger().info(f"Loaded policy from {policy_path}")

        # Subscribe to joint states (position + velocity from encoders)
        self.sub = self.create_subscription(
            JointState, "/joint_states", self._joint_state_cb, 10
        )
        # Publish joint effort commands
        self.pub = self.create_publisher(
            Float64MultiArray, "/effort_controller/commands", 10
        )
        self._latest_obs = None

    def _joint_state_cb(self, msg: JointState):
        # Build observation vector: concatenate positions and velocities
        pos = np.array(msg.position, dtype=np.float32)
        vel = np.array(msg.velocity, dtype=np.float32)
        obs = np.concatenate([pos, vel])

        # Convert to tensor and run inference (no gradient needed)
        obs_tensor = torch.from_numpy(obs).unsqueeze(0)  # (1, obs_dim)
        with torch.no_grad():
            action = self.policy(obs_tensor).squeeze(0).numpy()

        # Publish torque commands
        cmd_msg = Float64MultiArray()
        cmd_msg.data = action.tolist()
        self.pub.publish(cmd_msg)


def main():
    rclpy.init()
    node = PolicyDeployNode("/path/to/trained_policy.pt")
    rclpy.spin(node)
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

## Common Mistakes

1. **Randomizing too aggressively without curriculum.** Setting very wide randomization ranges from the start often makes the task impossible to learn. Use curriculum domain randomization: start with narrow ranges and gradually widen them as the policy improves.

2. **Forgetting actuator dynamics in simulation.** Training with ideal torque actuators and then deploying to motors with significant backlash and latency is one of the most common failure modes. Model actuator dynamics explicitly — at minimum, add PD gains and latency.

3. **Not measuring real noise empirically.** Guessing observation noise levels instead of measuring them from actual hardware logs leads to either under- or over-regularization. Always record a few minutes of hardware data and fit noise distributions from it.

4. **Skipping system identification for contact-rich tasks.** For manipulation and bipedal locomotion, contact physics dominates the behavior. Without SysID, even well-randomized policies often fail at contact events because the nominal simulator friction is far from reality.

5. **Deploying at simulation control frequency on real hardware.** Policies trained at 1 kHz simulation timesteps may require more computation than is available on the robot's onboard computer. Profile your policy inference time on the target hardware and match the control loop frequency before deployment.

## Summary

- The sim-to-real gap arises from physics modeling errors, sensor noise/latency mismatches, and visual domain differences between simulation and the real world.
- Domain randomization trains a policy across a wide distribution of simulated conditions so the real world falls within the training distribution, improving out-of-the-box transfer.
- System identification calibrates simulator parameters (masses, frictions, damping) against real hardware measurements, reducing the nominal gap before training begins.
- Noise injection — including Gaussian observation noise, action latency simulation, and observation dropout — teaches policies to be robust to the imperfect sensing of real hardware.
- Adaptive policies (e.g., RMA) estimate a latent dynamics context from real-world proprioceptive history, enabling online adaptation without gradient updates at deployment time.

## Review Questions

1. List three categories of sim-to-real gap and give one concrete example of a physical phenomenon in each category that a typical rigid-body simulator fails to capture accurately.
2. In the domain randomization code example, why is the nominal mass array cached before training begins rather than re-read from the model each episode?
3. What is the difference between domain randomization and system identification as strategies for bridging the sim-to-real gap? Under what circumstances would you rely more heavily on each?
4. A bipedal robot policy trained in simulation falls over immediately when deployed on hardware. List three diagnostic steps you would take to identify whether the failure is due to physics gap, sensor noise, or control frequency mismatch.
5. Explain the Rapid Motor Adaptation (RMA) approach. What is trained in simulation, what is the role of the adaptation module, and why does this approach not require real-world gradient updates?
