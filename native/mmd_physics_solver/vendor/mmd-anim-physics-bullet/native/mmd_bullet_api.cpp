#include "mmd_bullet_api.h"

#include <btBulletDynamicsCommon.h>
#include <BulletSoftBody/btSoftBodyRigidBodyCollisionConfiguration.h>
#include <BulletSoftBody/btSoftRigidDynamicsWorld.h>

#include <cmath>
#include <memory>
#include <string>
#include <utility>
#include <vector>
#include <windows.h>

#if defined(_MSC_VER) && _MSC_VER < 1900
static std::string g_last_error;
#else
thread_local std::string g_last_error;
#endif

struct RigidBodyEntry {
    std::unique_ptr<btCollisionShape> shape;
    std::unique_ptr<btDefaultMotionState> motion_state;
    std::unique_ptr<btRigidBody> body;
    btTransform initial_transform;

#if defined(_MSC_VER) && _MSC_VER < 1900
    RigidBodyEntry() = default;
    RigidBodyEntry(RigidBodyEntry &&other)
        : shape(std::move(other.shape)),
          motion_state(std::move(other.motion_state)),
          body(std::move(other.body)),
          initial_transform(other.initial_transform) {}
    RigidBodyEntry &operator=(RigidBodyEntry &&other) {
        shape = std::move(other.shape);
        motion_state = std::move(other.motion_state);
        body = std::move(other.body);
        initial_transform = other.initial_transform;
        return *this;
    }
#endif
};

struct mmd_anim_bullet_world {
    std::unique_ptr<btSoftBodyRigidBodyCollisionConfiguration> collision_configuration;
    std::unique_ptr<btCollisionDispatcher> dispatcher;
    std::unique_ptr<btDbvtBroadphase> broadphase;
    std::unique_ptr<btSequentialImpulseConstraintSolver> solver;
    std::unique_ptr<btSoftRigidDynamicsWorld> dynamics_world;
    std::unique_ptr<btCollisionShape> ground_shape;
    std::unique_ptr<btDefaultMotionState> ground_motion_state;
    std::unique_ptr<btRigidBody> ground_body;
    std::vector<RigidBodyEntry> rigidbodies;
    std::vector<std::unique_ptr<btTypedConstraint>> constraints;
};

static mmd_anim_bullet_status fail(mmd_anim_bullet_status status, const char *message) {
    g_last_error = message;
    return status;
}

typedef double(__cdecl *PmxEditorTrigFunction)(double);

static PmxEditorTrigFunction pmx_editor_trig(const char *name) {
    static HMODULE runtime = LoadLibraryW(L"msvcr100.dll");
    return runtime
        ? reinterpret_cast<PmxEditorTrigFunction>(GetProcAddress(runtime, name))
        : nullptr;
}

static btTransform make_transform(const float position[3], const float rotation_xyzw[4]) {
    btTransform transform;
    transform.setIdentity();
    transform.setOrigin(btVector3(position[0], position[1], position[2]));
    transform.setRotation(btQuaternion(
        rotation_xyzw[0],
        rotation_xyzw[1],
        rotation_xyzw[2],
        rotation_xyzw[3]));
    return transform;
}

static void set_vec3_limit(btGeneric6DofSpringConstraint &constraint, const float lower[3], const float upper[3]) {
    constraint.setLinearLowerLimit(btVector3(lower[0], lower[1], lower[2]));
    constraint.setLinearUpperLimit(btVector3(upper[0], upper[1], upper[2]));
}

static void set_angular_limit(btGeneric6DofSpringConstraint &constraint, const float lower[3], const float upper[3]) {
    constraint.setAngularLowerLimit(btVector3(lower[0], lower[1], lower[2]));
    constraint.setAngularUpperLimit(btVector3(upper[0], upper[1], upper[2]));
}

static void configure_linear_spring_axis(
    btGeneric6DofSpringConstraint &constraint,
    int axis,
    int stiffness_axis,
    float stiffness) {
    constraint.enableSpring(axis, false);
    if (stiffness != 0.0f) {
        constraint.enableSpring(axis, true);
        constraint.setStiffness(stiffness_axis, stiffness);
    }
}

static void configure_angular_spring_axis(
    btGeneric6DofSpringConstraint &constraint,
    int axis,
    float stiffness) {
    constraint.enableSpring(axis, true);
    constraint.setStiffness(axis, stiffness);
}

static btCollisionShape *make_shape(const mmd_anim_bullet_rigidbody_desc &desc) {
    switch (desc.shape_type) {
    case MMD_ANIM_BULLET_SHAPE_SPHERE:
        return new btSphereShape(desc.shape_size[0]);
    case MMD_ANIM_BULLET_SHAPE_BOX:
        return new btBoxShape(btVector3(
            desc.shape_size[0],
            desc.shape_size[1],
            desc.shape_size[2]));
    case MMD_ANIM_BULLET_SHAPE_CAPSULE:
        return new btCapsuleShape(desc.shape_size[0], desc.shape_size[1]);
    default:
        return nullptr;
    }
}

static void calculate_local_inertia(
    const mmd_anim_bullet_rigidbody_desc &desc,
    btCollisionShape &shape,
    btScalar mass,
    btVector3 &inertia) {
    if (desc.shape_type != MMD_ANIM_BULLET_SHAPE_BOX) {
        shape.calculateLocalInertia(mass, inertia);
        return;
    }

    const auto &box = static_cast<const btBoxShape &>(shape);
    const btVector3 half_extents = box.getHalfExtentsWithMargin();
    volatile const btScalar dimension_scale = btScalar(2.0f);
    volatile const btScalar mass_scale = btScalar(0.0833333358168602f);
    const btScalar lx = half_extents.x() * dimension_scale;
    const btScalar ly = half_extents.y() * dimension_scale;
    const btScalar lz = half_extents.z() * dimension_scale;
    const btScalar scaled_mass = mass * mass_scale;
    inertia.setValue(
        scaled_mass * (ly * ly + lz * lz),
        scaled_mass * (lx * lx + lz * lz),
        scaled_mass * (lx * lx + ly * ly));
}

static int32_t rigidbody_index_for_collision_object(
    const mmd_anim_bullet_world *world,
    const btCollisionObject *object) {
    if (!world || !object) {
        return -1;
    }
    for (size_t i = 0; i < world->rigidbodies.size(); ++i) {
        if (world->rigidbodies[i].body.get() == object) {
            return static_cast<int32_t>(i);
        }
    }
    return -1;
}

static void copy_vec3(const btVector3 &source, float target[3]) {
    target[0] = source.x();
    target[1] = source.y();
    target[2] = source.z();
}

static void copy_transform(
    const btTransform &source,
    float position[3],
    float rotation_xyzw[4]) {
    copy_vec3(source.getOrigin(), position);
    const btQuaternion rotation = source.getRotation();
    rotation_xyzw[0] = rotation.x();
    rotation_xyzw[1] = rotation.y();
    rotation_xyzw[2] = rotation.z();
    rotation_xyzw[3] = rotation.w();
}

extern "C" {

uint32_t mmd_anim_bullet_get_version(void) {
    return 1;
}

const char *mmd_anim_bullet_get_last_error(void) {
    return g_last_error.c_str();
}

void mmd_anim_bullet_quaternion_rotation_yaw_pitch_roll(
    float yaw,
    float pitch,
    float roll,
    float out_rotation_xyzw[4]) {
    const float half_yaw = yaw * 0.5f;
    const float half_pitch = pitch * 0.5f;
    const float half_roll = roll * 0.5f;
    const PmxEditorTrigFunction sin_function = pmx_editor_trig("sin");
    const PmxEditorTrigFunction cos_function = pmx_editor_trig("cos");
    const float sin_yaw = static_cast<float>(
        sin_function ? sin_function(static_cast<double>(half_yaw))
                     : std::sin(static_cast<double>(half_yaw)));
    const float cos_yaw = static_cast<float>(
        cos_function ? cos_function(static_cast<double>(half_yaw))
                     : std::cos(static_cast<double>(half_yaw)));
    const float sin_pitch = static_cast<float>(
        sin_function ? sin_function(static_cast<double>(half_pitch))
                     : std::sin(static_cast<double>(half_pitch)));
    const float cos_pitch = static_cast<float>(
        cos_function ? cos_function(static_cast<double>(half_pitch))
                     : std::cos(static_cast<double>(half_pitch)));
    const float sin_roll = static_cast<float>(
        sin_function ? sin_function(static_cast<double>(half_roll))
                     : std::sin(static_cast<double>(half_roll)));
    const float cos_roll = static_cast<float>(
        cos_function ? cos_function(static_cast<double>(half_roll))
                     : std::cos(static_cast<double>(half_roll)));

    const double yaw_pitch_sin =
        static_cast<double>(sin_yaw) * static_cast<double>(cos_pitch);
    const double yaw_pitch_cos =
        static_cast<double>(cos_yaw) * static_cast<double>(sin_pitch);
    const double cos_yaw_cos_pitch =
        static_cast<double>(cos_yaw) * static_cast<double>(cos_pitch);
    const double sin_pitch_sin_yaw =
        static_cast<double>(sin_pitch) * static_cast<double>(sin_yaw);
    out_rotation_xyzw[0] = static_cast<float>(
        static_cast<double>(sin_roll) * yaw_pitch_sin +
        static_cast<double>(cos_roll) * yaw_pitch_cos);
    out_rotation_xyzw[1] = static_cast<float>(
        yaw_pitch_sin * static_cast<double>(cos_roll) -
        yaw_pitch_cos * static_cast<double>(sin_roll));
    out_rotation_xyzw[2] = static_cast<float>(
        static_cast<double>(sin_roll) * cos_yaw_cos_pitch -
        static_cast<double>(cos_roll) * sin_pitch_sin_yaw);
    out_rotation_xyzw[3] = static_cast<float>(
        static_cast<double>(sin_roll) * sin_pitch_sin_yaw +
        static_cast<double>(cos_roll) * cos_yaw_cos_pitch);
}

mmd_anim_bullet_status mmd_anim_bullet_world_create(mmd_anim_bullet_world **out_world) {
    if (!out_world) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "out_world is null");
    }

    try {
        auto world = std::make_unique<mmd_anim_bullet_world>();
        world->collision_configuration = std::make_unique<btSoftBodyRigidBodyCollisionConfiguration>();
        world->dispatcher = std::make_unique<btCollisionDispatcher>(world->collision_configuration.get());
        world->broadphase = std::make_unique<btDbvtBroadphase>();
        world->solver = std::make_unique<btSequentialImpulseConstraintSolver>();
        world->dynamics_world = std::make_unique<btSoftRigidDynamicsWorld>(
            world->dispatcher.get(),
            world->broadphase.get(),
            world->solver.get(),
            world->collision_configuration.get());
        world->dynamics_world->setSynchronizeAllMotionStates(true);
        world->dynamics_world->getSolverInfo().m_numIterations = 10;
        world->dynamics_world->getSolverInfo().m_solverMode |= SOLVER_USE_WARMSTARTING;
        world->dynamics_world->setGravity(btVector3(0.0f, 0.0f, -98.0f));

        world->ground_shape = std::make_unique<btStaticPlaneShape>(
            btVector3(0.0f, 1.0f, 0.0f),
            0.0f);
        btTransform ground_transform;
        ground_transform.setIdentity();
        world->ground_motion_state = std::make_unique<btDefaultMotionState>(ground_transform);
        btRigidBody::btRigidBodyConstructionInfo ground_info(
            0.0f,
            world->ground_motion_state.get(),
            world->ground_shape.get(),
            btVector3(0.0f, 0.0f, 0.0f));
        world->ground_body = std::make_unique<btRigidBody>(ground_info);
        world->dynamics_world->addRigidBody(
            world->ground_body.get(),
            static_cast<short>(0x8000),
            static_cast<short>(-1));
        *out_world = world.release();
        g_last_error.clear();
        return MMD_ANIM_BULLET_OK;
    } catch (const std::exception &err) {
        return fail(MMD_ANIM_BULLET_INTERNAL_ERROR, err.what());
    }
}

void mmd_anim_bullet_world_destroy(mmd_anim_bullet_world *world) {
    if (!world) {
        return;
    }
    if (world->dynamics_world) {
        for (auto it = world->constraints.rbegin(); it != world->constraints.rend(); ++it) {
            world->dynamics_world->removeConstraint(it->get());
        }
        for (auto it = world->rigidbodies.rbegin(); it != world->rigidbodies.rend(); ++it) {
            world->dynamics_world->removeRigidBody(it->body.get());
        }
        if (world->ground_body) {
            world->dynamics_world->removeRigidBody(world->ground_body.get());
        }
    }
    delete world;
}

mmd_anim_bullet_status mmd_anim_bullet_world_reset(mmd_anim_bullet_world *world) {
    if (!world) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world is null");
    }

    for (auto &entry : world->rigidbodies) {
        entry.body->setWorldTransform(entry.initial_transform);
        entry.body->setInterpolationWorldTransform(entry.initial_transform);
        entry.body->setLinearVelocity(btVector3(0.0f, 0.0f, 0.0f));
        entry.body->setAngularVelocity(btVector3(0.0f, 0.0f, 0.0f));
        entry.body->setInterpolationLinearVelocity(btVector3(0.0f, 0.0f, 0.0f));
        entry.body->setInterpolationAngularVelocity(btVector3(0.0f, 0.0f, 0.0f));
        entry.body->clearForces();
        entry.body->activate(true);
        if (entry.motion_state) {
            entry.motion_state->setWorldTransform(entry.initial_transform);
        }
    }
    for (auto &constraint : world->constraints) {
#if BT_BULLET_VERSION > 275
        constraint->setEnabled(true);
#endif
    }
    world->dynamics_world->getBroadphase()->getOverlappingPairCache()->cleanProxyFromPairs(nullptr, world->dynamics_world->getDispatcher());
    g_last_error.clear();
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_settle_to_current(mmd_anim_bullet_world *world) {
    if (!world) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world is null");
    }

    world->dynamics_world->clearForces();
    btOverlappingPairCache *pair_cache = world->dynamics_world->getPairCache();
    btDispatcher *dispatcher = world->dynamics_world->getDispatcher();

    for (auto &entry : world->rigidbodies) {
        btRigidBody *body = entry.body.get();
        body->setInterpolationWorldTransform(body->getWorldTransform());
        body->setLinearVelocity(btVector3(0.0f, 0.0f, 0.0f));
        body->setAngularVelocity(btVector3(0.0f, 0.0f, 0.0f));
        body->setInterpolationLinearVelocity(btVector3(0.0f, 0.0f, 0.0f));
        body->setInterpolationAngularVelocity(btVector3(0.0f, 0.0f, 0.0f));
        body->clearForces();
        body->activate(true);

        if (pair_cache && dispatcher && body->getBroadphaseHandle()) {
            pair_cache->cleanProxyFromPairs(body->getBroadphaseHandle(), dispatcher);
        }
    }

    g_last_error.clear();
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_set_solver_iterations(
    mmd_anim_bullet_world *world,
    int32_t iterations) {
    if (!world) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world is null");
    }
    if (iterations < 1 || iterations > 128) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "solver iterations must be in [1, 128]");
    }
    world->dynamics_world->getSolverInfo().m_numIterations = iterations;
#if BT_BULLET_VERSION > 275
    for (auto &constraint : world->constraints) {
        constraint->setOverrideNumSolverIterations(iterations);
    }
#endif
    g_last_error.clear();
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_step(
    mmd_anim_bullet_world *world,
    float delta_time,
    int32_t max_sub_steps,
    float fixed_substep_seconds) {
    if (!world) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world is null");
    }
    if (!std::isfinite(delta_time) || delta_time < 0.0f || max_sub_steps < 0 ||
        !std::isfinite(fixed_substep_seconds) || fixed_substep_seconds <= 0.0f) {
        return fail(
            MMD_ANIM_BULLET_INVALID_ARGUMENT,
            "delta_time and max_sub_steps must be non-negative and fixed_substep_seconds must be positive");
    }

    world->dynamics_world->stepSimulation(delta_time, max_sub_steps, fixed_substep_seconds);
    g_last_error.clear();
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_add_rigidbody(
    mmd_anim_bullet_world *world,
    const mmd_anim_bullet_rigidbody_desc *desc,
    int32_t *out_index) {
    if (!world || !desc || !out_index) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world, desc, or out_index is null");
    }

    try {
        std::unique_ptr<btCollisionShape> shape(make_shape(*desc));
        if (!shape) {
            return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "unknown shape type");
        }

        btTransform initial_transform = make_transform(desc->position, desc->rotation_xyzw);
        btVector3 inertia(0.0f, 0.0f, 0.0f);
        const btScalar mass = desc->mass;
        if (mass > 0.0f) {
            calculate_local_inertia(*desc, *shape, mass, inertia);
        }

        auto motion_state = std::make_unique<btDefaultMotionState>(initial_transform);
        btRigidBody::btRigidBodyConstructionInfo info(mass, motion_state.get(), shape.get(), inertia);
        info.m_linearDamping = desc->linear_damping;
        info.m_angularDamping = desc->angular_damping;
        info.m_friction = desc->friction;
        info.m_restitution = desc->restitution;
        info.m_additionalDamping = false;

        auto body = std::make_unique<btRigidBody>(info);
        if (mass == 0.0f) {
            body->setCollisionFlags(body->getCollisionFlags() | btCollisionObject::CF_KINEMATIC_OBJECT);
        }
        body->setActivationState(DISABLE_DEACTIVATION);

        const int group = 1 << btMin<uint16_t>(desc->collision_group, 15);
        const int mask = static_cast<int>(desc->collision_mask);
        world->dynamics_world->addRigidBody(body.get(), group, mask);

        RigidBodyEntry entry;
        entry.shape = std::move(shape);
        entry.motion_state = std::move(motion_state);
        entry.body = std::move(body);
        entry.initial_transform = initial_transform;
        world->rigidbodies.push_back(std::move(entry));
        *out_index = static_cast<int32_t>(world->rigidbodies.size() - 1);
        g_last_error.clear();
        return MMD_ANIM_BULLET_OK;
    } catch (const std::exception &err) {
        return fail(MMD_ANIM_BULLET_INTERNAL_ERROR, err.what());
    }
}

int32_t mmd_anim_bullet_world_get_rigidbody_count(const mmd_anim_bullet_world *world) {
    if (!world) {
        g_last_error = "world is null";
        return -1;
    }
    g_last_error.clear();
    return static_cast<int32_t>(world->rigidbodies.size());
}

mmd_anim_bullet_status mmd_anim_bullet_world_get_rigidbody_transform(
    const mmd_anim_bullet_world *world,
    int32_t index,
    float out_position[3],
    float out_rotation_xyzw[4]) {
    if (!world || !out_position || !out_rotation_xyzw) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world or output buffer is null");
    }
    if (index < 0 || static_cast<size_t>(index) >= world->rigidbodies.size()) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "rigidbody index out of range");
    }

    const auto &entry = world->rigidbodies[static_cast<size_t>(index)];
    const btTransform &transform = entry.body->getWorldTransform();
    const btVector3 origin = transform.getOrigin();
    const btQuaternion rotation = transform.getRotation();
    out_position[0] = origin.x();
    out_position[1] = origin.y();
    out_position[2] = origin.z();
    out_rotation_xyzw[0] = rotation.x();
    out_rotation_xyzw[1] = rotation.y();
    out_rotation_xyzw[2] = rotation.z();
    out_rotation_xyzw[3] = rotation.w();
    g_last_error.clear();
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_set_rigidbody_transform(
    mmd_anim_bullet_world *world,
    int32_t index,
    const float position[3],
    const float rotation_xyzw[4]) {
    if (!world || !position || !rotation_xyzw) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world or input buffer is null");
    }
    if (index < 0 || static_cast<size_t>(index) >= world->rigidbodies.size()) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "rigidbody index out of range");
    }

    btTransform transform;
    transform.setIdentity();
    transform.setOrigin(btVector3(position[0], position[1], position[2]));
    transform.setRotation(btQuaternion(rotation_xyzw[0], rotation_xyzw[1], rotation_xyzw[2], rotation_xyzw[3]));

    auto &entry = world->rigidbodies[static_cast<size_t>(index)];
    entry.body->setWorldTransform(transform);
    entry.body->setInterpolationWorldTransform(transform);
    entry.body->activate(true);
    if (entry.motion_state) {
        entry.motion_state->setWorldTransform(transform);
    }
    world->dynamics_world->updateSingleAabb(entry.body.get());
    g_last_error.clear();
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_set_rigidbody_position(
    mmd_anim_bullet_world *world,
    int32_t index,
    const float position[3]) {
    if (!world || !position) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world or position buffer is null");
    }
    if (index < 0 || static_cast<size_t>(index) >= world->rigidbodies.size()) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "rigidbody index out of range");
    }
    auto &entry = world->rigidbodies[static_cast<size_t>(index)];
    btTransform transform = entry.body->getWorldTransform();
    transform.setOrigin(btVector3(position[0], position[1], position[2]));
    entry.body->setWorldTransform(transform);
    entry.body->setInterpolationWorldTransform(transform);
    entry.body->activate(true);
    if (entry.motion_state) {
        entry.motion_state->setWorldTransform(transform);
    }
    world->dynamics_world->updateSingleAabb(entry.body.get());
    g_last_error.clear();
    return MMD_ANIM_BULLET_OK;
}

int32_t mmd_anim_bullet_world_get_rigidbody_states(
    const mmd_anim_bullet_world *world,
    mmd_anim_bullet_rigidbody_state *out_states,
    int32_t capacity) {
    if (!world || (capacity > 0 && !out_states)) {
        g_last_error = "world or output buffer is null";
        return -1;
    }
    const int32_t count = static_cast<int32_t>(world->rigidbodies.size());
    if (capacity < count) {
        g_last_error = "rigidbody state buffer is too small";
        return -1;
    }
    for (int32_t index = 0; index < count; ++index) {
        btRigidBody *body = world->rigidbodies[static_cast<size_t>(index)].body.get();
        mmd_anim_bullet_rigidbody_state &state = out_states[index];
        copy_transform(body->getWorldTransform(), state.position, state.rotation_xyzw);
        copy_transform(
            body->getInterpolationWorldTransform(),
            state.interpolation_position,
            state.interpolation_rotation_xyzw);
        copy_vec3(body->getLinearVelocity(), state.linear_velocity);
        copy_vec3(body->getAngularVelocity(), state.angular_velocity);
        copy_vec3(body->getInterpolationLinearVelocity(), state.interpolation_linear_velocity);
        copy_vec3(body->getInterpolationAngularVelocity(), state.interpolation_angular_velocity);
        copy_vec3(body->getTotalForce(), state.total_force);
        copy_vec3(body->getTotalTorque(), state.total_torque);
        state.activation_state = body->getActivationState();
        state.deactivation_time = body->getDeactivationTime();
    }
    g_last_error.clear();
    return count;
}

mmd_anim_bullet_status mmd_anim_bullet_world_set_rigidbody_states(
    mmd_anim_bullet_world *world,
    const mmd_anim_bullet_rigidbody_state *states,
    int32_t count) {
    if (!world || (count > 0 && !states)) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world or state buffer is null");
    }
    if (count < 0 || static_cast<size_t>(count) != world->rigidbodies.size()) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "rigidbody state count does not match world");
    }

    btOverlappingPairCache *pair_cache = world->dynamics_world->getPairCache();
    btDispatcher *dispatcher = world->dynamics_world->getDispatcher();
    for (int32_t index = 0; index < count; ++index) {
        RigidBodyEntry &entry = world->rigidbodies[static_cast<size_t>(index)];
        btRigidBody *body = entry.body.get();
        const mmd_anim_bullet_rigidbody_state &state = states[index];
        const btTransform transform = make_transform(state.position, state.rotation_xyzw);
        const btTransform interpolation_transform = make_transform(
            state.interpolation_position,
            state.interpolation_rotation_xyzw);
        body->setWorldTransform(transform);
        body->setInterpolationWorldTransform(interpolation_transform);
        body->setLinearVelocity(btVector3(
            state.linear_velocity[0], state.linear_velocity[1], state.linear_velocity[2]));
        body->setAngularVelocity(btVector3(
            state.angular_velocity[0], state.angular_velocity[1], state.angular_velocity[2]));
        body->setInterpolationLinearVelocity(btVector3(
            state.interpolation_linear_velocity[0],
            state.interpolation_linear_velocity[1],
            state.interpolation_linear_velocity[2]));
        body->setInterpolationAngularVelocity(btVector3(
            state.interpolation_angular_velocity[0],
            state.interpolation_angular_velocity[1],
            state.interpolation_angular_velocity[2]));
        body->clearForces();
        body->applyCentralForce(btVector3(
            state.total_force[0], state.total_force[1], state.total_force[2]));
        body->applyTorque(btVector3(
            state.total_torque[0], state.total_torque[1], state.total_torque[2]));
        body->forceActivationState(state.activation_state);
        body->setDeactivationTime(state.deactivation_time);
        if (entry.motion_state) {
            entry.motion_state->setWorldTransform(transform);
        }
        if (pair_cache && dispatcher && body->getBroadphaseHandle()) {
            pair_cache->cleanProxyFromPairs(body->getBroadphaseHandle(), dispatcher);
        }
        world->dynamics_world->updateSingleAabb(body);
    }
    if (world->broadphase && dispatcher) {
        world->broadphase->calculateOverlappingPairs(dispatcher);
    }
    g_last_error.clear();
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_apply_world_delta(
    mmd_anim_bullet_world *world,
    int32_t first_index,
    int32_t count,
    const float position[3],
    const float rotation_xyzw[4]) {
    if (!world || !position || !rotation_xyzw) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world or delta transform is null");
    }
    if (first_index < 0 || count < 0 ||
        static_cast<size_t>(first_index) > world->rigidbodies.size() ||
        static_cast<size_t>(count) > world->rigidbodies.size() - static_cast<size_t>(first_index)) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "world delta range is invalid");
    }

    const btTransform delta = make_transform(position, rotation_xyzw);
    const size_t begin = static_cast<size_t>(first_index);
    const size_t end = begin + static_cast<size_t>(count);
    for (size_t index = begin; index < end; ++index) {
        RigidBodyEntry &entry = world->rigidbodies[index];
        const btTransform transform = delta * entry.body->getWorldTransform();
        entry.body->setWorldTransform(transform);
        entry.body->setInterpolationWorldTransform(transform);
        entry.body->activate(true);
        if (entry.motion_state) {
            entry.motion_state->setWorldTransform(transform);
        }
        world->dynamics_world->updateSingleAabb(entry.body.get());
    }
    g_last_error.clear();
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_add_6dof_spring_joint(
    mmd_anim_bullet_world *world,
    const mmd_anim_bullet_6dof_spring_joint_desc *desc,
    int32_t *out_index) {
    if (!world || !desc || !out_index) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world, desc, or out_index is null");
    }
    if (desc->rigidbody_index_a < 0 || desc->rigidbody_index_b < 0 ||
        static_cast<size_t>(desc->rigidbody_index_a) >= world->rigidbodies.size() ||
        static_cast<size_t>(desc->rigidbody_index_b) >= world->rigidbodies.size()) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "joint rigidbody index out of range");
    }

    try {
        auto &body_a = *world->rigidbodies[static_cast<size_t>(desc->rigidbody_index_a)].body;
        auto &body_b = *world->rigidbodies[static_cast<size_t>(desc->rigidbody_index_b)].body;
        btTransform joint_transform = make_transform(desc->position, desc->rotation_xyzw);
        btTransform frame_a = body_a.getWorldTransform().inverse() * joint_transform;
        btTransform frame_b = body_b.getWorldTransform().inverse() * joint_transform;

        auto constraint = std::make_unique<btGeneric6DofSpringConstraint>(body_a, body_b, frame_a, frame_b, true);
        set_vec3_limit(*constraint, desc->translation_lower_limit, desc->translation_upper_limit);
        set_angular_limit(*constraint, desc->rotation_lower_limit, desc->rotation_upper_limit);
        for (int axis = 0; axis < 3; ++axis) {
            // PmxNLib 2.5 writes Z translation stiffness to motor 1 after enabling motor 2.
            const int stiffness_axis = axis == 2 ? 1 : axis;
            configure_linear_spring_axis(
                *constraint,
                axis,
                stiffness_axis,
                desc->spring_translation_factor[axis]);
        }
        for (int axis = 0; axis < 3; ++axis) {
            configure_angular_spring_axis(
                *constraint,
                axis + 3,
                desc->spring_rotation_factor[axis]);
        }
#if BT_BULLET_VERSION > 275
        constraint->setOverrideNumSolverIterations(world->dynamics_world->getSolverInfo().m_numIterations);
#endif
        constraint->setEquilibriumPoint();
        world->dynamics_world->addConstraint(constraint.get(), false);
        world->constraints.push_back(std::move(constraint));
        *out_index = static_cast<int32_t>(world->constraints.size() - 1);
        g_last_error.clear();
        return MMD_ANIM_BULLET_OK;
    } catch (const std::exception &err) {
        return fail(MMD_ANIM_BULLET_INTERNAL_ERROR, err.what());
    }
}

int32_t mmd_anim_bullet_world_get_constraint_count(const mmd_anim_bullet_world *world) {
    if (!world) {
        g_last_error = "world is null";
        return -1;
    }
    g_last_error.clear();
    return static_cast<int32_t>(world->constraints.size());
}

mmd_anim_bullet_status mmd_anim_bullet_world_collect_contacts(
    const mmd_anim_bullet_world *world,
    mmd_anim_bullet_contact_point *out_contacts,
    int32_t capacity,
    int32_t *out_count) {
    if (!world || !out_count) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world or out_count is null");
    }
    if (capacity < 0) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "capacity must be non-negative");
    }
    if (capacity > 0 && !out_contacts) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "out_contacts is null with non-zero capacity");
    }

    int32_t count = 0;
    btDispatcher *dispatcher = world->dynamics_world->getDispatcher();
    const int manifold_count = dispatcher->getNumManifolds();
    for (int manifold_index = 0; manifold_index < manifold_count; ++manifold_index) {
        btPersistentManifold *manifold = dispatcher->getManifoldByIndexInternal(manifold_index);
        if (!manifold) {
            continue;
        }
        const int32_t body_a = rigidbody_index_for_collision_object(
            world,
            static_cast<const btCollisionObject *>(manifold->getBody0()));
        const int32_t body_b = rigidbody_index_for_collision_object(
            world,
            static_cast<const btCollisionObject *>(manifold->getBody1()));
        if (body_a < 0 || body_b < 0) {
            continue;
        }
        const int contact_count = manifold->getNumContacts();
        for (int contact_index = 0; contact_index < contact_count; ++contact_index) {
            const btManifoldPoint &point = manifold->getContactPoint(contact_index);
            if (count < capacity) {
                auto &out = out_contacts[count];
                out.rigidbody_index_a = body_a;
                out.rigidbody_index_b = body_b;
                out.distance = point.getDistance();
                copy_vec3(point.getPositionWorldOnA(), out.position_world_on_a);
                copy_vec3(point.getPositionWorldOnB(), out.position_world_on_b);
                copy_vec3(point.m_normalWorldOnB, out.normal_world_on_b);
            }
            ++count;
        }
    }

    *out_count = count;
    g_last_error.clear();
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_get_gravity(
    const mmd_anim_bullet_world *world,
    float out_gravity_xyz[3]) {
    if (!world || !out_gravity_xyz) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world or out_gravity_xyz is null");
    }
    btVector3 gravity = world->dynamics_world->getGravity();
    out_gravity_xyz[0] = gravity.x();
    out_gravity_xyz[1] = gravity.y();
    out_gravity_xyz[2] = gravity.z();
    g_last_error.clear();
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_set_gravity(
    mmd_anim_bullet_world *world,
    const float gravity_xyz[3]) {
    if (!world || !gravity_xyz) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world or gravity_xyz is null");
    }
    if (!std::isfinite(gravity_xyz[0]) || !std::isfinite(gravity_xyz[1]) || !std::isfinite(gravity_xyz[2])) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "gravity_xyz must be finite");
    }
    world->dynamics_world->setGravity(btVector3(gravity_xyz[0], gravity_xyz[1], gravity_xyz[2]));
    g_last_error.clear();
    return MMD_ANIM_BULLET_OK;
}

}
