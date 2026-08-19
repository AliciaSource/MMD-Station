use mmd_anim_physics_bullet::{
    BulletWorld, RigidBodyDesc as BulletBodyDesc, RigidBodyHandle, RigidBodyShape,
    SixDofSpringJointDesc, quaternion_rotation_yaw_pitch_roll,
};
use std::ffi::c_void;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::ptr;
use std::slice;

const ABI_VERSION: u32 = 4;
#[cfg(test)]
const DEFAULT_WORLD_SCALE: f32 = 1.0;
const MMD_GRAVITY_SCALE: f32 = 10.0;

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct Vec3 {
    pub x: f32,
    pub y: f32,
    pub z: f32,
}

impl Vec3 {
    fn from_array(value: [f32; 3]) -> Self {
        Self { x: value[0], y: value[1], z: value[2] }
    }

    fn array(self) -> [f32; 3] {
        [self.x, self.y, self.z]
    }

    fn scaled_array(self, scale: f32) -> [f32; 3] {
        [self.x * scale, self.y * scale, self.z * scale]
    }

    fn add(self, other: Self) -> Self {
        Self {
            x: self.x + other.x,
            y: self.y + other.y,
            z: self.z + other.z,
        }
    }

    fn neg(self) -> Self {
        Self {
            x: -self.x,
            y: -self.y,
            z: -self.z,
        }
    }

    fn mmd_basis(self) -> Self {
        Self {
            x: self.x,
            y: self.z,
            z: self.y,
        }
    }

    fn mmd_angular_basis(self) -> Self {
        Self {
            x: -self.x,
            y: -self.z,
            z: -self.y,
        }
    }
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct Quat {
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub w: f32,
}

impl Default for Quat {
    fn default() -> Self {
        Self {
            x: 0.0,
            y: 0.0,
            z: 0.0,
            w: 1.0,
        }
    }
}

impl Quat {
    fn from_array(value: [f32; 4]) -> Self {
        Self { x: value[0], y: value[1], z: value[2], w: value[3] }
    }

    fn array(self) -> [f32; 4] {
        [self.x, self.y, self.z, self.w]
    }

    fn mmd_basis(self) -> Self {
        Self {
            x: -self.x,
            y: -self.z,
            z: -self.y,
            w: self.w,
        }
    }

    fn normalized(self) -> Self {
        let length = (self.x * self.x + self.y * self.y + self.z * self.z + self.w * self.w).sqrt();
        if length <= 1.0e-8 {
            return Self::default();
        }
        Self {
            x: self.x / length,
            y: self.y / length,
            z: self.z / length,
            w: self.w / length,
        }
    }

    fn inverse(self) -> Self {
        let q = self.normalized();
        Self {
            x: -q.x,
            y: -q.y,
            z: -q.z,
            w: q.w,
        }
    }

    fn mul(self, other: Self) -> Self {
        Self {
            x: self.w * other.x + self.x * other.w + self.y * other.z - self.z * other.y,
            y: self.w * other.y - self.x * other.z + self.y * other.w + self.z * other.x,
            z: self.w * other.z + self.x * other.y - self.y * other.x + self.z * other.w,
            w: self.w * other.w - self.x * other.x - self.y * other.y - self.z * other.z,
        }
        .normalized()
    }

    fn rotate(self, value: Vec3) -> Vec3 {
        let q = self.normalized();
        let u = Vec3 {
            x: q.x,
            y: q.y,
            z: q.z,
        };
        let dot_uv = u.x * value.x + u.y * value.y + u.z * value.z;
        let dot_uu = u.x * u.x + u.y * u.y + u.z * u.z;
        let cross = Vec3 {
            x: u.y * value.z - u.z * value.y,
            y: u.z * value.x - u.x * value.z,
            z: u.x * value.y - u.y * value.x,
        };
        Vec3 {
            x: 2.0 * dot_uv * u.x + (q.w * q.w - dot_uu) * value.x + 2.0 * q.w * cross.x,
            y: 2.0 * dot_uv * u.y + (q.w * q.w - dot_uu) * value.y + 2.0 * q.w * cross.y,
            z: 2.0 * dot_uv * u.z + (q.w * q.w - dot_uu) * value.z + 2.0 * q.w * cross.z,
        }
    }
}

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct Transform {
    pub position: Vec3,
    pub rotation: Quat,
}

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct BasisTransform {
    pub position: Vec3,
    pub basis_row_major: [f32; 9],
}

impl Transform {
    fn compose(self, other: Self) -> Self {
        Self {
            position: self.position.add(self.rotation.rotate(other.position)),
            rotation: self.rotation.mul(other.rotation),
        }
    }

    fn inverse(self) -> Self {
        let rotation = self.rotation.inverse();
        Self {
            position: rotation.rotate(self.position.neg()),
            rotation,
        }
    }

    fn mmd_basis(self) -> Self {
        Self {
            position: self.position.mmd_basis(),
            rotation: self.rotation.mmd_basis(),
        }
    }
}

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct BodyDesc {
    pub mode: u32,
    pub shape: u32,
    pub transform: Transform,
    pub bone_transform: Transform,
    pub has_bone: u32,
    pub size: Vec3,
    pub mass: f32,
    pub linear_damping: f32,
    pub angular_damping: f32,
    pub restitution: f32,
    pub friction: f32,
    pub collision_group: u32,
    pub collision_mask: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct JointDesc {
    pub body_a: u32,
    pub body_b: u32,
    pub transform: Transform,
    pub linear_lower: Vec3,
    pub linear_upper: Vec3,
    pub angular_lower: Vec3,
    pub angular_upper: Vec3,
    pub linear_spring: Vec3,
    pub angular_spring: Vec3,
}

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct JointState {
    pub frame_a: Transform,
    pub frame_b: Transform,
}

#[derive(Clone, Copy)]
struct BodyBinding {
    mode: u32,
    has_bone: bool,
    body_from_bone: Transform,
    initial_body: Transform,
    initial_animation_bone: Transform,
    animation_bone: Transform,
    last_body_target: Transform,
    source_euler: Option<Vec3>,
}

#[derive(Clone, Copy)]
struct JointBinding {
    body_a: usize,
    body_b: usize,
    frame_a: Transform,
    frame_b: Transform,
}

struct Solver {
    world: BulletWorld,
    world_scale: f32,
    bodies: Vec<RigidBodyHandle>,
    bindings: Vec<BodyBinding>,
    joints: Vec<JointBinding>,
}

fn rigid_body_shape(desc: &BodyDesc, world_scale: f32) -> Result<RigidBodyShape, String> {
    match desc.shape {
        0 => Ok(RigidBodyShape::Sphere {
            radius: desc.size.x * world_scale,
        }),
        1 => Ok(RigidBodyShape::Box {
            half_extents: desc.size.mmd_basis().scaled_array(world_scale),
        }),
        2 => Ok(RigidBodyShape::Capsule {
            radius: desc.size.x * world_scale,
            height: desc.size.y * world_scale,
        }),
        _ => Err(format!("unsupported rigid body shape {}", desc.shape)),
    }
}

impl Solver {
    #[cfg(test)]
    fn new(body_descs: &[BodyDesc], joint_descs: &[JointDesc]) -> Result<Self, String> {
        Self::new_with_world_scale(body_descs, joint_descs, DEFAULT_WORLD_SCALE)
    }

    fn new_with_world_scale(
        body_descs: &[BodyDesc],
        joint_descs: &[JointDesc],
        requested_world_scale: f32,
    ) -> Result<Self, String> {
        Self::new_with_world_scale_and_source_eulers(
            body_descs,
            joint_descs,
            requested_world_scale,
            None,
        )
    }

    fn new_with_world_scale_and_source_eulers(
        body_descs: &[BodyDesc],
        joint_descs: &[JointDesc],
        requested_world_scale: f32,
        source_eulers: Option<(&[Vec3], &[Vec3])>,
    ) -> Result<Self, String> {
        if !requested_world_scale.is_finite() || requested_world_scale <= 0.0 {
            return Err("world scale must be positive and finite".to_owned());
        }
        let world_scale = 1.0_f32;
        let mut world = BulletWorld::new().map_err(|error| error.to_string())?;
        let mut bodies = Vec::with_capacity(body_descs.len());
        let mut bindings = Vec::with_capacity(body_descs.len());
        for (body_index, desc) in body_descs.iter().enumerate() {
            let transform = desc.transform.mmd_basis();
            let bone_transform = desc.bone_transform.mmd_basis();
            let shape = rigid_body_shape(desc, world_scale)?;
            let handle = world
                .add_rigidbody(BulletBodyDesc {
                    shape,
                    position: transform.position.scaled_array(world_scale),
                    rotation_xyzw: transform.rotation.array(),
                    mass: if desc.mode == 0 { 0.0 } else { desc.mass },
                    linear_damping: desc.linear_damping,
                    angular_damping: desc.angular_damping,
                    friction: desc.friction,
                    restitution: desc.restitution,
                    collision_group: desc.collision_group.min(15) as u16,
                    collision_mask: desc.collision_mask as u16,
                })
                .map_err(|error| error.to_string())?;
            bodies.push(handle);
            bindings.push(BodyBinding {
                mode: desc.mode,
                has_bone: desc.has_bone != 0,
                body_from_bone: bone_transform.inverse().compose(transform),
                initial_body: transform,
                initial_animation_bone: bone_transform,
                animation_bone: bone_transform,
                last_body_target: transform,
                source_euler: source_eulers.map(|(body_eulers, _)| body_eulers[body_index]),
            });
        }
        let mut joints = Vec::with_capacity(joint_descs.len());
        for (joint_index, desc) in joint_descs.iter().enumerate() {
            let transform = desc.transform.mmd_basis();
            let body_a = *bodies
                .get(desc.body_a as usize)
                .ok_or_else(|| format!("joint body A {} is out of range", desc.body_a))?;
            let body_b = *bodies
                .get(desc.body_b as usize)
                .ok_or_else(|| format!("joint body B {} is out of range", desc.body_b))?;
            let joint = SixDofSpringJointDesc {
                    rigidbody_a: body_a,
                    rigidbody_b: body_b,
                    position: transform.position.scaled_array(world_scale),
                    rotation_xyzw: transform.rotation.array(),
                    translation_lower_limit: desc
                        .linear_lower
                        .mmd_basis()
                        .scaled_array(world_scale),
                    translation_upper_limit: desc
                        .linear_upper
                        .mmd_basis()
                        .scaled_array(world_scale),
                    rotation_lower_limit: desc.angular_upper.mmd_angular_basis().array(),
                    rotation_upper_limit: desc.angular_lower.mmd_angular_basis().array(),
                    spring_translation_factor: desc.linear_spring.mmd_basis().array(),
                    spring_rotation_factor: desc.angular_spring.mmd_basis().array(),
                };
            let (frame_a, frame_b) = if let Some((body_eulers, joint_eulers)) = source_eulers {
                let (_, frame_a, frame_b) = world
                    .add_mmd_6dof_spring_joint(
                        joint,
                        body_eulers[desc.body_a as usize].array(),
                        body_eulers[desc.body_b as usize].array(),
                        joint_eulers[joint_index].array(),
                    )
                    .map_err(|error| error.to_string())?;
                (
                    Transform {
                        position: Vec3::from_array(frame_a.position),
                        rotation: Quat::from_array(frame_a.rotation_xyzw),
                    },
                    Transform {
                        position: Vec3::from_array(frame_b.position),
                        rotation: Quat::from_array(frame_b.rotation_xyzw),
                    },
                )
            } else {
                world
                    .add_6dof_spring_joint(joint)
                    .map_err(|error| error.to_string())?;
                let body_a_transform = body_descs[desc.body_a as usize].transform.mmd_basis();
                let body_b_transform = body_descs[desc.body_b as usize].transform.mmd_basis();
                (
                    body_a_transform.inverse().compose(transform),
                    body_b_transform.inverse().compose(transform),
                )
            };
            joints.push(JointBinding {
                body_a: desc.body_a as usize,
                body_b: desc.body_b as usize,
                frame_a,
                frame_b,
            });
        }
        world
            .set_solver_iterations(10)
            .map_err(|error| error.to_string())?;
        Ok(Self {
            world,
            world_scale,
            bodies,
            bindings,
            joints,
        })
    }

    fn set_gravity(&mut self, gravity: Vec3) -> Result<(), String> {
        self.world
            .set_gravity(gravity.mmd_basis().scaled_array(MMD_GRAVITY_SCALE))
            .map_err(|error| error.to_string())
    }

    fn set_iterations(&mut self, iterations: u32) -> Result<(), String> {
        self.world
            .set_solver_iterations(iterations.clamp(1, 128) as i32)
            .map_err(|error| error.to_string())
    }

    fn set_bone_target(&mut self, index: usize, target: Transform) -> Result<(), String> {
        let binding = self
            .bindings
            .get_mut(index)
            .ok_or_else(|| format!("rigid body {} is out of range", index))?;
        if !binding.has_bone {
            return Ok(());
        }
        let target = target.mmd_basis();
        binding.animation_bone = target;
        if binding.mode != 0 {
            return Ok(());
        }
        let handle = *self
            .bodies
            .get(index)
            .ok_or_else(|| format!("rigid body {} is out of range", index))?;
        let translation_only = target.rotation.array()
            == binding.initial_animation_bone.rotation.array();
        let body_target = if translation_only {
            Transform {
                position: binding.initial_body.position.add(
                    target.position.add(binding.initial_animation_bone.position.neg()),
                ),
                rotation: binding.initial_body.rotation,
            }
        } else {
            target.compose(binding.body_from_bone)
        };
        binding.last_body_target = body_target;
        if translation_only {
            self.world
                .set_rigidbody_position(
                    handle,
                    body_target.position.scaled_array(self.world_scale),
                )
                .map_err(|error| error.to_string())?;
            if let Some(source_euler) = binding.source_euler {
                self.world
                    .set_rigidbody_motion_state_mmd_euler(handle, source_euler.array())
                    .map_err(|error| error.to_string())
            } else {
                let composed = target.compose(binding.body_from_bone);
                self.world
                    .set_rigidbody_motion_state_rotation(handle, composed.rotation.array())
                    .map_err(|error| error.to_string())
            }
        } else {
            self.world
                .set_rigidbody_position(
                    handle,
                    body_target.position.scaled_array(self.world_scale),
                )
                .map_err(|error| error.to_string())?;
            self.world
                .set_rigidbody_motion_state_rotation(handle, body_target.rotation.array())
                .map_err(|error| error.to_string())
        }
    }

    fn set_body_target_basis(&mut self, index: usize, target: BasisTransform) -> Result<(), String> {
        let binding = self
            .bindings
            .get(index)
            .ok_or_else(|| format!("rigid body {} is out of range", index))?;
        if binding.mode != 0 {
            return Ok(());
        }
        let handle = *self
            .bodies
            .get(index)
            .ok_or_else(|| format!("rigid body {} is out of range", index))?;
        self.world
            .set_rigidbody_motion_state_matrix(
                handle,
                mmd_anim_physics_bullet::MatrixTransform {
                    position: target.position.scaled_array(self.world_scale),
                    basis_row_major: target.basis_row_major,
                },
            )
            .map_err(|error| error.to_string())
    }

    fn set_body_target_transform(&mut self, index: usize, target: Transform) -> Result<(), String> {
        let binding = self
            .bindings
            .get(index)
            .ok_or_else(|| format!("rigid body {} is out of range", index))?;
        if binding.mode != 0 {
            return Ok(());
        }
        let handle = *self
            .bodies
            .get(index)
            .ok_or_else(|| format!("rigid body {} is out of range", index))?;
        self.world
            .set_rigidbody_position(handle, target.position.scaled_array(self.world_scale))
            .map_err(|error| error.to_string())?;
        self.world
            .set_rigidbody_motion_state_rotation(handle, target.rotation.array())
            .map_err(|error| error.to_string())
    }

    fn set_body_target_position(&mut self, index: usize, position: Vec3) -> Result<(), String> {
        let binding = self
            .bindings
            .get(index)
            .ok_or_else(|| format!("rigid body {} is out of range", index))?;
        if binding.mode != 0 {
            return Ok(());
        }
        let handle = *self
            .bodies
            .get(index)
            .ok_or_else(|| format!("rigid body {} is out of range", index))?;
        self.world
            .set_rigidbody_position(handle, position.scaled_array(self.world_scale))
            .map_err(|error| error.to_string())
    }

    fn set_body_target_position_if_near(
        &mut self,
        index: usize,
        position: Vec3,
        max_ulps: u32,
    ) -> Result<bool, String> {
        let binding = self
            .bindings
            .get(index)
            .ok_or_else(|| format!("rigid body {} is out of range", index))?;
        if binding.mode != 0 {
            return Ok(false);
        }
        fn ordered_bits(value: f32) -> i32 {
            let bits = value.to_bits() as i32;
            if bits < 0 { i32::MIN - bits } else { bits }
        }
        fn near(a: f32, b: f32, max_ulps: u32) -> bool {
            ordered_bits(a).abs_diff(ordered_bits(b)) <= max_ulps
        }
        let current = binding.last_body_target.position;
        if !near(current.x, position.x, max_ulps)
            || !near(current.y, position.y, max_ulps)
            || !near(current.z, position.z, max_ulps)
        {
            return Ok(false);
        }
        self.set_body_target_position(index, position)?;
        Ok(true)
    }

    fn step(&mut self, dt: f32, substeps: u32) -> Result<(), String> {
        if !dt.is_finite() || dt <= 0.0 {
            return Err("delta time must be positive and finite".to_owned());
        }
        let max_substeps = substeps.clamp(1, 32);
        self.world
            .step_with_fixed_substep(dt, max_substeps as i32, 1.0 / 60.0)
            .map_err(|error| error.to_string())
    }

    fn transforms(&self, output: &mut [Transform]) -> Result<(), String> {
        if output.len() < self.bodies.len() {
            return Err("output transform buffer is too small".to_owned());
        }
        for (target, handle) in output.iter_mut().zip(&self.bodies) {
            let value = self
                .world
                .rigidbody_transform(*handle)
                .map_err(|error| error.to_string())?;
            *target = Transform {
                position: Vec3 {
                    x: value.position[0] / self.world_scale,
                    y: value.position[1] / self.world_scale,
                    z: value.position[2] / self.world_scale,
                },
                rotation: Quat {
                    x: value.rotation_xyzw[0],
                    y: value.rotation_xyzw[1],
                    z: value.rotation_xyzw[2],
                    w: value.rotation_xyzw[3],
                },
            }
            .mmd_basis();
        }
        Ok(())
    }

    fn basis_transforms(&self, output: &mut [BasisTransform]) -> Result<(), String> {
        if output.len() < self.bodies.len() {
            return Err("output basis transform buffer is too small".to_owned());
        }
        for (target, handle) in output.iter_mut().zip(&self.bodies) {
            let value = self
                .world
                .rigidbody_matrix(*handle)
                .map_err(|error| error.to_string())?;
            let basis = value.basis_row_major;
            *target = BasisTransform {
                position: Vec3 {
                    x: value.position[0] / self.world_scale,
                    y: value.position[1] / self.world_scale,
                    z: value.position[2] / self.world_scale,
                },
                basis_row_major: basis,
            };
        }
        Ok(())
    }

    fn bone_transforms(&self, output: &mut [Transform]) -> Result<(), String> {
        if output.len() < self.bodies.len() {
            return Err("output bone transform buffer is too small".to_owned());
        }
        let mut body_transforms = vec![Transform::default(); self.bodies.len()];
        self.transforms(&mut body_transforms)?;
        for (index, target) in output.iter_mut().take(self.bodies.len()).enumerate() {
            let binding = self.bindings[index];
            if !binding.has_bone || binding.mode == 0 {
                *target = binding.animation_bone.mmd_basis();
                continue;
            }
            let body_transform = body_transforms[index].mmd_basis();
            let physics_bone = body_transform.compose(binding.body_from_bone.inverse());
            let result = if binding.mode == 2 {
                Transform {
                    position: binding.animation_bone.position,
                    rotation: physics_bone.rotation,
                }
            } else {
                physics_bone
            };
            *target = result.mmd_basis();
        }
        Ok(())
    }

    fn joint_states(&self, output: &mut [JointState]) -> Result<(), String> {
        if output.len() < self.joints.len() {
            return Err("output joint state buffer is too small".to_owned());
        }
        let mut body_transforms = vec![Transform::default(); self.bodies.len()];
        self.transforms(&mut body_transforms)?;
        for transform in &mut body_transforms {
            *transform = transform.mmd_basis();
        }
        for (target, binding) in output.iter_mut().zip(&self.joints) {
            *target = JointState {
                frame_a: body_transforms[binding.body_a]
                    .compose(binding.frame_a)
                    .mmd_basis(),
                frame_b: body_transforms[binding.body_b]
                    .compose(binding.frame_b)
                    .mmd_basis(),
            };
        }
        Ok(())
    }
}

fn ffi_guard<T: Copy>(fallback: T, callback: impl FnOnce() -> T) -> T {
    catch_unwind(AssertUnwindSafe(callback)).unwrap_or(fallback)
}

#[unsafe(no_mangle)]
pub extern "C" fn mmd_solver_abi_version() -> u32 {
    ABI_VERSION
}

#[unsafe(no_mangle)]
pub extern "C" fn mmd_solver_pmx_euler_to_blender_quaternion(
    euler: Vec3,
    output: *mut Quat,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    let value = quaternion_rotation_yaw_pitch_roll(euler.y, euler.x, euler.z);
    unsafe {
        *output = Quat {
            x: value[0],
            y: value[1],
            z: value[2],
            w: value[3],
        }
        .mmd_basis();
    }
    0
}

#[unsafe(no_mangle)]
/// # Safety
///
/// `bodies` must reference `body_count` readable descriptors. When `joint_count` is nonzero,
/// `joints` must reference `joint_count` readable descriptors.
pub unsafe extern "C" fn mmd_solver_create(
    bodies: *const BodyDesc,
    body_count: u32,
    joints: *const JointDesc,
    joint_count: u32,
    world_scale: f32,
) -> *mut c_void {
    ffi_guard(ptr::null_mut(), || {
        if bodies.is_null() || (joint_count > 0 && joints.is_null()) {
            return ptr::null_mut();
        }
        let body_slice = unsafe { slice::from_raw_parts(bodies, body_count as usize) };
        let joint_slice = if joint_count == 0 {
            &[]
        } else {
            unsafe { slice::from_raw_parts(joints, joint_count as usize) }
        };
        Solver::new_with_world_scale(body_slice, joint_slice, world_scale)
            .map(|solver| Box::into_raw(Box::new(solver)) as *mut c_void)
            .unwrap_or(ptr::null_mut())
    })
}

#[unsafe(no_mangle)]
/// # Safety
///
/// All descriptor and Euler pointers must reference the corresponding readable element count.
pub unsafe extern "C" fn mmd_solver_create_mmd(
    bodies: *const BodyDesc,
    body_count: u32,
    joints: *const JointDesc,
    joint_count: u32,
    body_source_eulers: *const Vec3,
    joint_source_eulers: *const Vec3,
    world_scale: f32,
) -> *mut c_void {
    ffi_guard(ptr::null_mut(), || {
        if bodies.is_null()
            || body_source_eulers.is_null()
            || (joint_count > 0 && (joints.is_null() || joint_source_eulers.is_null()))
        {
            return ptr::null_mut();
        }
        let body_slice = unsafe { slice::from_raw_parts(bodies, body_count as usize) };
        let body_euler_slice = unsafe {
            slice::from_raw_parts(body_source_eulers, body_count as usize)
        };
        let joint_slice = if joint_count == 0 {
            &[]
        } else {
            unsafe { slice::from_raw_parts(joints, joint_count as usize) }
        };
        let joint_euler_slice = if joint_count == 0 {
            &[]
        } else {
            unsafe { slice::from_raw_parts(joint_source_eulers, joint_count as usize) }
        };
        Solver::new_with_world_scale_and_source_eulers(
            body_slice,
            joint_slice,
            world_scale,
            Some((body_euler_slice, joint_euler_slice)),
        )
        .map(|solver| Box::into_raw(Box::new(solver)) as *mut c_void)
        .unwrap_or(ptr::null_mut())
    })
}

#[unsafe(no_mangle)]
/// # Safety
///
/// `handle` must be null or a live handle returned by `mmd_solver_create` that has not been
/// destroyed previously.
pub unsafe extern "C" fn mmd_solver_destroy(handle: *mut c_void) {
    if !handle.is_null() {
        unsafe {
            drop(Box::from_raw(handle as *mut Solver));
        }
    }
}

#[unsafe(no_mangle)]
/// # Safety
///
/// `handle` must be a live handle returned by `mmd_solver_create`.
pub unsafe extern "C" fn mmd_solver_set_gravity(handle: *mut c_void, gravity: Vec3) -> i32 {
    ffi_guard(0, || {
        let Some(solver) = (unsafe { (handle as *mut Solver).as_mut() }) else {
            return 0;
        };
        solver.set_gravity(gravity).is_ok() as i32
    })
}

#[unsafe(no_mangle)]
/// # Safety
///
/// `handle` must be null or a live handle returned by `mmd_solver_create`.
pub unsafe extern "C" fn mmd_solver_set_iterations(handle: *mut c_void, iterations: u32) -> i32 {
    ffi_guard(0, || {
        let Some(solver) = (unsafe { (handle as *mut Solver).as_mut() }) else {
            return 0;
        };
        solver.set_iterations(iterations).is_ok() as i32
    })
}

#[unsafe(no_mangle)]
/// # Safety
///
/// `handle` must be a live handle returned by `mmd_solver_create`.
pub unsafe extern "C" fn mmd_solver_set_bone_target(
    handle: *mut c_void,
    index: u32,
    target: Transform,
) -> i32 {
    ffi_guard(0, || {
        let Some(solver) = (unsafe { (handle as *mut Solver).as_mut() }) else {
            return 0;
        };
        solver.set_bone_target(index as usize, target).is_ok() as i32
    })
}

#[unsafe(no_mangle)]
/// # Safety
///
/// `handle` must be a live handle returned by `mmd_solver_create`.
pub unsafe extern "C" fn mmd_solver_step(handle: *mut c_void, dt: f32, substeps: u32) -> i32 {
    ffi_guard(0, || {
        let Some(solver) = (unsafe { (handle as *mut Solver).as_mut() }) else {
            return 0;
        };
        solver.step(dt, substeps).is_ok() as i32
    })
}

#[unsafe(no_mangle)]
/// # Safety
///
/// `handle` must be a live handle returned by `mmd_solver_create`, and `output` must reference
/// writable storage for at least `capacity` transforms.
pub unsafe extern "C" fn mmd_solver_get_transforms(
    handle: *mut c_void,
    output: *mut Transform,
    capacity: u32,
) -> u32 {
    ffi_guard(0, || {
        let Some(solver) = (unsafe { (handle as *mut Solver).as_ref() }) else {
            return 0;
        };
        if output.is_null() || capacity < solver.bodies.len() as u32 {
            return 0;
        }
        let result = unsafe { slice::from_raw_parts_mut(output, solver.bodies.len()) };
        if solver.transforms(result).is_err() {
            return 0;
        }
        solver.bodies.len() as u32
    })
}

#[unsafe(no_mangle)]
/// # Safety
///
/// `handle` must be live and `output` must reference writable storage for `capacity` transforms.
pub unsafe extern "C" fn mmd_solver_get_basis_transforms(
    handle: *mut c_void,
    output: *mut BasisTransform,
    capacity: u32,
) -> u32 {
    ffi_guard(0, || {
        let Some(solver) = (unsafe { (handle as *mut Solver).as_ref() }) else {
            return 0;
        };
        if output.is_null() || capacity < solver.bodies.len() as u32 {
            return 0;
        }
        let result = unsafe { slice::from_raw_parts_mut(output, solver.bodies.len()) };
        if solver.basis_transforms(result).is_err() {
            return 0;
        }
        solver.bodies.len() as u32
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mmd_solver_set_body_target_basis(
    handle: *mut c_void,
    index: u32,
    target: BasisTransform,
) -> i32 {
    ffi_guard(0, || {
        let Some(solver) = (unsafe { (handle as *mut Solver).as_mut() }) else {
            return 0;
        };
        solver.set_body_target_basis(index as usize, target).is_ok() as i32
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mmd_solver_set_body_target_transform(
    handle: *mut c_void,
    index: u32,
    target: Transform,
) -> i32 {
    ffi_guard(0, || {
        let Some(solver) = (unsafe { (handle as *mut Solver).as_mut() }) else {
            return 0;
        };
        solver.set_body_target_transform(index as usize, target).is_ok() as i32
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mmd_solver_set_body_target_position(
    handle: *mut c_void,
    index: u32,
    position: Vec3,
) -> i32 {
    ffi_guard(0, || {
        let Some(solver) = (unsafe { (handle as *mut Solver).as_mut() }) else {
            return 0;
        };
        solver.set_body_target_position(index as usize, position).is_ok() as i32
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mmd_solver_set_body_target_position_if_near(
    handle: *mut c_void,
    index: u32,
    position: Vec3,
    max_ulps: u32,
) -> i32 {
    ffi_guard(0, || {
        let Some(solver) = (unsafe { (handle as *mut Solver).as_mut() }) else {
            return 0;
        };
        match solver.set_body_target_position_if_near(index as usize, position, max_ulps) {
            Ok(true) => 1,
            Ok(false) => 2,
            Err(_) => 0,
        }
    })
}

#[unsafe(no_mangle)]
/// # Safety
///
/// `handle` must be live and `output` must reference writable storage for `capacity` transforms.
pub unsafe extern "C" fn mmd_solver_get_bone_transforms(
    handle: *mut c_void,
    output: *mut Transform,
    capacity: u32,
) -> u32 {
    ffi_guard(0, || {
        let Some(solver) = (unsafe { (handle as *mut Solver).as_ref() }) else {
            return 0;
        };
        if output.is_null() || capacity < solver.bodies.len() as u32 {
            return 0;
        }
        let result = unsafe { slice::from_raw_parts_mut(output, solver.bodies.len()) };
        if solver.bone_transforms(result).is_err() {
            return 0;
        }
        solver.bodies.len() as u32
    })
}

#[unsafe(no_mangle)]
/// # Safety
///
/// `handle` must be live and `output` must reference writable storage for `capacity` states.
pub unsafe extern "C" fn mmd_solver_get_joint_states(
    handle: *mut c_void,
    output: *mut JointState,
    capacity: u32,
) -> u32 {
    ffi_guard(0, || {
        let Some(solver) = (unsafe { (handle as *mut Solver).as_ref() }) else {
            return 0;
        };
        if output.is_null() || capacity < solver.joints.len() as u32 {
            return 0;
        }
        let result = unsafe { slice::from_raw_parts_mut(output, solver.joints.len()) };
        if solver.joint_states(result).is_err() {
            return 0;
        }
        solver.joints.len() as u32
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bullet_dynamic_body_falls() {
        let body = BodyDesc {
            mode: 1,
            shape: 0,
            size: Vec3 {
                x: 0.2,
                y: 0.2,
                z: 0.2,
            },
            mass: 1.0,
            ..BodyDesc::default()
        };
        let mut solver = Solver::new(&[body], &[]).unwrap();
        solver
            .set_gravity(Vec3 {
                x: 0.0,
                y: 0.0,
                z: -9.80665,
            })
            .unwrap();
        solver.step(1.0 / 60.0, 2).unwrap();
        let mut output = [Transform::default()];
        solver.transforms(&mut output).unwrap();
        assert!(output[0].position.z < 0.0);
    }

    #[test]
    fn mmd_ground_plane_supports_dynamic_bodies() {
        let body = BodyDesc {
            mode: 1,
            shape: 0,
            transform: Transform {
                position: Vec3 {
                    x: 0.0,
                    y: 0.0,
                    z: 2.0,
                },
                rotation: Quat::default(),
            },
            size: Vec3 {
                x: 0.2,
                y: 0.2,
                z: 0.2,
            },
            mass: 1.0,
            collision_mask: u16::MAX as u32,
            ..BodyDesc::default()
        };
        let mut solver = Solver::new_with_world_scale(&[body], &[], 1.0).unwrap();
        solver
            .set_gravity(Vec3 {
                x: 0.0,
                y: 0.0,
                z: -9.8,
            })
            .unwrap();
        for _ in 0..300 {
            solver.step(1.0 / 60.0, 10).unwrap();
        }
        let mut output = [Transform::default()];
        solver.transforms(&mut output).unwrap();
        assert!(
            (output[0].position.z - 0.2).abs() < 1.0e-3,
            "unexpected resting height {}",
            output[0].position.z
        );
    }

    #[test]
    fn max_substeps_does_not_change_a_60_hz_step_when_capacity_is_sufficient() {
        let body = BodyDesc {
            mode: 1,
            shape: 0,
            size: Vec3 {
                x: 0.2,
                y: 0.2,
                z: 0.2,
            },
            mass: 1.0,
            ..BodyDesc::default()
        };
        let mut solver_two = Solver::new(&[body], &[]).unwrap();
        let mut solver_ten = Solver::new(&[body], &[]).unwrap();
        for solver in [&mut solver_two, &mut solver_ten] {
            solver
                .set_gravity(Vec3 {
                    x: 0.0,
                    y: 0.0,
                    z: -9.80665,
                })
                .unwrap();
        }
        solver_two.step(1.0 / 60.0, 2).unwrap();
        solver_ten.step(1.0 / 60.0, 10).unwrap();
        let mut output_two = [Transform::default()];
        let mut output_ten = [Transform::default()];
        solver_two.transforms(&mut output_two).unwrap();
        solver_ten.transforms(&mut output_ten).unwrap();
        assert!((output_two[0].position.z - output_ten[0].position.z).abs() < 1.0e-6);
    }

    #[test]
    fn mmd_quaternion_matches_runtime_d3dx_float_bits() {
        let value = quaternion_rotation_yaw_pitch_roll(-0.2, 0.1, 0.3);
        assert_eq!(value[0].to_bits(), 0x3d0c5f8a);
        assert_eq!(value[1].to_bits(), 0xbdd92148);
        assert_eq!(value[2].to_bits(), 0x3e1d1f31);
        assert_eq!(value[3].to_bits(), 0x3f7b5aed);
    }

    #[test]
    fn translated_static_body_survives_the_next_step() {
        let body = BodyDesc {
            mode: 0,
            shape: 0,
            has_bone: 1,
            size: Vec3 {
                x: 0.2,
                y: 0.2,
                z: 0.2,
            },
            ..BodyDesc::default()
        };
        let mut solver = Solver::new_with_world_scale(&[body], &[], 1.0).unwrap();
        let target = Transform {
            position: Vec3 {
                x: 0.5,
                y: 0.25,
                z: -0.125,
            },
            rotation: Quat::default(),
        };
        solver.set_bone_target(0, target).unwrap();
        solver.step(1.0 / 60.0, 10).unwrap();
        let mut output = [Transform::default()];
        solver.transforms(&mut output).unwrap();
        assert_eq!(output[0].position.array(), target.position.array());
    }

    #[test]
    fn solver_steps_do_not_replay_authored_body_transforms() {
        let body = BodyDesc {
            mode: 0,
            shape: 0,
            has_bone: 1,
            size: Vec3 {
                x: 0.2,
                y: 0.2,
                z: 0.2,
            },
            ..BodyDesc::default()
        };
        let body_eulers = [Vec3::default()];
        let joint_eulers = [];
        let mut solver = Solver::new_with_world_scale_and_source_eulers(
            &[body],
            &[],
            1.0,
            Some((&body_eulers, &joint_eulers)),
        )
        .unwrap();
        let target = Transform {
            position: Vec3 {
                x: 0.5,
                y: 0.25,
                z: -0.125,
            },
            rotation: Quat::default(),
        };
        for _ in 0..5 {
            solver.set_bone_target(0, target).unwrap();
            solver.step(1.0 / 60.0, 10).unwrap();
            let mut output = [Transform::default()];
            solver.transforms(&mut output).unwrap();
            assert_eq!(output[0].position.array(), target.position.array());
        }
    }

    #[test]
    fn mmd_native_units_ignore_host_import_scale() {
        let body = BodyDesc {
            mode: 1,
            shape: 0,
            transform: Transform {
                position: Vec3 {
                    x: 0.0,
                    y: 0.0,
                    z: 1.0,
                },
                rotation: Quat::default(),
            },
            size: Vec3 {
                x: 0.2,
                y: 0.2,
                z: 0.2,
            },
            mass: 1.0,
            ..BodyDesc::default()
        };

        let mut solver_008 = Solver::new_with_world_scale(&[body], &[], 12.5).unwrap();
        let mut solver_010 = Solver::new_with_world_scale(&[body], &[], 10.0).unwrap();
        for solver in [&mut solver_008, &mut solver_010] {
            solver
                .set_gravity(Vec3 {
                    x: 0.0,
                    y: 0.0,
                    z: -9.8,
                })
                .unwrap();
        }
        for _ in 0..60 {
            solver_008.step(1.0 / 60.0, 2).unwrap();
            solver_010.step(1.0 / 60.0, 10).unwrap();
        }
        let mut output_008 = [Transform::default()];
        let mut output_010 = [Transform::default()];
        solver_008.transforms(&mut output_008).unwrap();
        solver_010.transforms(&mut output_010).unwrap();
        assert_eq!(output_008[0].position.array(), output_010[0].position.array());
    }

    #[test]
    fn bullet_joint_is_created_in_input_order() {
        let anchor = BodyDesc {
            mode: 0,
            shape: 0,
            size: Vec3 {
                x: 0.2,
                y: 0.2,
                z: 0.2,
            },
            ..BodyDesc::default()
        };
        let dynamic = BodyDesc {
            mode: 1,
            shape: 0,
            size: Vec3 {
                x: 0.2,
                y: 0.2,
                z: 0.2,
            },
            mass: 1.0,
            transform: Transform {
                position: Vec3 {
                    x: 0.0,
                    y: 0.0,
                    z: -1.0,
                },
                rotation: Quat::default(),
            },
            ..BodyDesc::default()
        };
        let joint = JointDesc {
            body_a: 0,
            body_b: 1,
            transform: Transform {
                position: Vec3 {
                    x: 0.0,
                    y: 0.0,
                    z: -0.5,
                },
                rotation: Quat::default(),
            },
            ..JointDesc::default()
        };
        let solver = Solver::new(&[anchor, dynamic], &[joint]).unwrap();
        assert_eq!(solver.world.constraint_count().unwrap(), 1);
    }

    #[test]
    fn dynamic_bone_target_preserves_animation_position_without_teleporting_body() {
        let body = BodyDesc {
            mode: 2,
            shape: 0,
            transform: Transform {
                position: Vec3 {
                    x: 0.0,
                    y: 0.0,
                    z: 1.0,
                },
                rotation: Quat::default(),
            },
            bone_transform: Transform::default(),
            has_bone: 1,
            size: Vec3 {
                x: 0.2,
                y: 0.2,
                z: 0.2,
            },
            mass: 1.0,
            ..BodyDesc::default()
        };
        let mut solver = Solver::new(&[body], &[]).unwrap();
        solver
            .set_bone_target(
                0,
                Transform {
                    position: Vec3 {
                        x: 5.0,
                        y: 0.0,
                        z: 0.0,
                    },
                    rotation: Quat::default(),
                },
            )
            .unwrap();

        let mut bodies = [Transform::default()];
        solver.transforms(&mut bodies).unwrap();
        assert!(bodies[0].position.x.abs() < 1.0e-6);

        let mut bones = [Transform::default()];
        solver.bone_transforms(&mut bones).unwrap();
        assert!((bones[0].position.x - 5.0).abs() < 1.0e-6);
    }

    #[test]
    fn joint_frames_share_the_authored_world_position_at_bind() {
        let bodies = [
            BodyDesc {
                mode: 0,
                shape: 0,
                transform: Transform {
                    position: Vec3 {
                        x: -1.0,
                        y: 0.0,
                        z: 0.0,
                    },
                    rotation: Quat::default(),
                },
                size: Vec3 {
                    x: 0.2,
                    y: 0.2,
                    z: 0.2,
                },
                ..BodyDesc::default()
            },
            BodyDesc {
                mode: 1,
                shape: 0,
                transform: Transform {
                    position: Vec3 {
                        x: 1.0,
                        y: 0.0,
                        z: 0.0,
                    },
                    rotation: Quat::default(),
                },
                size: Vec3 {
                    x: 0.2,
                    y: 0.2,
                    z: 0.2,
                },
                mass: 1.0,
                ..BodyDesc::default()
            },
        ];
        let joint = JointDesc {
            body_a: 0,
            body_b: 1,
            transform: Transform::default(),
            ..JointDesc::default()
        };
        let solver = Solver::new(&bodies, &[joint]).unwrap();
        let mut states = [JointState::default()];
        solver.joint_states(&mut states).unwrap();
        let difference = states[0].frame_a.position.x - states[0].frame_b.position.x;
        assert!(difference.abs() < 1.0e-6);
    }

    #[test]
    fn blender_basis_round_trips_through_mmd_space() {
        let transform = Transform {
            position: Vec3 {
                x: 1.0,
                y: 2.0,
                z: 3.0,
            },
            rotation: Quat {
                x: 0.1,
                y: 0.2,
                z: 0.3,
                w: 0.9,
            },
        };
        let round_trip = transform.mmd_basis().mmd_basis();
        assert_eq!(round_trip.position.array(), transform.position.array());
        assert_eq!(round_trip.rotation.array(), transform.rotation.array());

        let blender_lower = Vec3 {
            x: -0.5,
            y: -0.25,
            z: -1.0,
        };
        let blender_upper = Vec3 {
            x: 0.75,
            y: 0.5,
            z: 1.25,
        };
        assert_eq!(
            blender_upper.mmd_angular_basis().array(),
            [-0.75, -1.25, -0.5]
        );
        assert_eq!(
            blender_lower.mmd_angular_basis().array(),
            [0.5, 1.0, 0.25]
        );
    }

    #[test]
    fn blender_box_half_extents_are_reordered_for_mmd_y_up_space() {
        let body = BodyDesc {
            shape: 1,
            size: Vec3 {
                x: 2.0,
                y: 3.0,
                z: 5.0,
            },
            ..BodyDesc::default()
        };
        let shape = rigid_body_shape(&body, 10.0).unwrap();
        assert_eq!(
            shape,
            RigidBodyShape::Box {
                half_extents: [20.0, 50.0, 30.0],
            }
        );
    }
}
