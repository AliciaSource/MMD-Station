#include "mmd_bullet_api.h"

#include <btBulletDynamicsCommon.h>

#include <cmath>
#include <cstdlib>
#include <cstring>
#include <windows.h>

static char g_last_error[1024] = {0};

struct RigidBodyEntry {
    btCollisionShape *shape;
    btDefaultMotionState *motion_state;
    btRigidBody *body;
    btTransform initial_transform;

    RigidBodyEntry() : shape(NULL), motion_state(NULL), body(NULL) {}
};

struct mmd_anim_bullet_world {
    btDefaultCollisionConfiguration *collision_configuration;
    btCollisionDispatcher *dispatcher;
    btDbvtBroadphase *broadphase;
    btSequentialImpulseConstraintSolver *solver;
    btDiscreteDynamicsWorld *dynamics_world;
    btCollisionShape *ground_shape;
    btDefaultMotionState *ground_motion_state;
    btRigidBody *ground_body;
    RigidBodyEntry *rigidbodies;
    size_t rigidbody_count;
    size_t rigidbody_capacity;
    btTypedConstraint **constraints;
    size_t constraint_count;
    size_t constraint_capacity;

    mmd_anim_bullet_world()
        : collision_configuration(NULL), dispatcher(NULL), broadphase(NULL), solver(NULL),
          dynamics_world(NULL), ground_shape(NULL), ground_motion_state(NULL), ground_body(NULL),
          rigidbodies(NULL), rigidbody_count(0), rigidbody_capacity(0), constraints(NULL),
          constraint_count(0), constraint_capacity(0) {}
};

static void set_last_error(const char *message) {
    if (!message) {
        g_last_error[0] = '\0';
        return;
    }
    const size_t length = strlen(message);
    const size_t copy_length = length < sizeof(g_last_error) - 1 ? length : sizeof(g_last_error) - 1;
    memcpy(g_last_error, message, copy_length);
    g_last_error[copy_length] = '\0';
}

static mmd_anim_bullet_status fail(mmd_anim_bullet_status status, const char *message) {
    set_last_error(message);
    return status;
}

static bool append_rigidbody(mmd_anim_bullet_world *world, const RigidBodyEntry &entry) {
    if (world->rigidbody_count == world->rigidbody_capacity) {
        const size_t capacity = world->rigidbody_capacity == 0 ? 16 : world->rigidbody_capacity * 2;
        void *memory = realloc(world->rigidbodies, capacity * sizeof(RigidBodyEntry));
        if (!memory) {
            return false;
        }
        world->rigidbodies = static_cast<RigidBodyEntry *>(memory);
        world->rigidbody_capacity = capacity;
    }
    world->rigidbodies[world->rigidbody_count++] = entry;
    return true;
}

static bool append_constraint(mmd_anim_bullet_world *world, btTypedConstraint *constraint) {
    if (world->constraint_count == world->constraint_capacity) {
        const size_t capacity = world->constraint_capacity == 0 ? 16 : world->constraint_capacity * 2;
        void *memory = realloc(world->constraints, capacity * sizeof(btTypedConstraint *));
        if (!memory) {
            return false;
        }
        world->constraints = static_cast<btTypedConstraint **>(memory);
        world->constraint_capacity = capacity;
    }
    world->constraints[world->constraint_count++] = constraint;
    return true;
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
        return NULL;
    }
}

static void calculate_local_inertia(
    const mmd_anim_bullet_rigidbody_desc &,
    btCollisionShape &shape,
    btScalar mass,
    btVector3 &inertia) {
    shape.calculateLocalInertia(mass, inertia);
}

static int32_t rigidbody_index_for_collision_object(
    const mmd_anim_bullet_world *world,
    const btCollisionObject *object) {
    if (!world || !object) {
        return -1;
    }
    for (size_t i = 0; i < world->rigidbody_count; ++i) {
        if (world->rigidbodies[i].body == object) {
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

extern "C" {

uint32_t mmd_anim_bullet_get_version(void) {
    return 1;
}

const char *mmd_anim_bullet_get_last_error(void) {
    return g_last_error;
}

void mmd_anim_bullet_quaternion_rotation_yaw_pitch_roll(
    float yaw,
    float pitch,
    float roll,
    float out_rotation_xyzw[4]) {
    const float half_yaw = yaw * 0.5f;
    const float half_pitch = pitch * 0.5f;
    const float half_roll = roll * 0.5f;
    const float sin_yaw = static_cast<float>(std::sin(static_cast<double>(half_yaw)));
    const float cos_yaw = static_cast<float>(std::cos(static_cast<double>(half_yaw)));
    const float sin_pitch = static_cast<float>(std::sin(static_cast<double>(half_pitch)));
    const float cos_pitch = static_cast<float>(std::cos(static_cast<double>(half_pitch)));
    const float sin_roll = static_cast<float>(std::sin(static_cast<double>(half_roll)));
    const float cos_roll = static_cast<float>(std::cos(static_cast<double>(half_roll)));

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

    mmd_anim_bullet_world *world = new mmd_anim_bullet_world();
    world->collision_configuration = new btDefaultCollisionConfiguration();
    world->dispatcher = new btCollisionDispatcher(world->collision_configuration);
    world->broadphase = new btDbvtBroadphase();
    world->solver = new btSequentialImpulseConstraintSolver();
    world->dynamics_world = new btDiscreteDynamicsWorld(
        world->dispatcher,
        world->broadphase,
        world->solver,
        world->collision_configuration);
    world->dynamics_world->setSynchronizeAllMotionStates(true);
    world->dynamics_world->getSolverInfo().m_numIterations = 10;
    world->dynamics_world->getSolverInfo().m_solverMode |= SOLVER_USE_WARMSTARTING;
    world->dynamics_world->setGravity(btVector3(0.0f, 0.0f, -98.0f));

    world->ground_shape = new btStaticPlaneShape(
        btVector3(0.0f, 1.0f, 0.0f),
        0.0f);
    btTransform ground_transform;
    ground_transform.setIdentity();
    world->ground_motion_state = new btDefaultMotionState(ground_transform);
    btRigidBody::btRigidBodyConstructionInfo ground_info(
        0.0f,
        world->ground_motion_state,
        world->ground_shape,
        btVector3(0.0f, 0.0f, 0.0f));
    world->ground_body = new btRigidBody(ground_info);
    world->dynamics_world->addRigidBody(
        world->ground_body,
        static_cast<short>(0x8000),
        static_cast<short>(-1));
    *out_world = world;
    g_last_error[0] = '\0';
    return MMD_ANIM_BULLET_OK;
}

void mmd_anim_bullet_world_destroy(mmd_anim_bullet_world *world) {
    if (!world) {
        return;
    }
    if (world->dynamics_world) {
        for (size_t i = world->constraint_count; i > 0; --i) {
            world->dynamics_world->removeConstraint(world->constraints[i - 1]);
        }
        for (size_t i = world->rigidbody_count; i > 0; --i) {
            world->dynamics_world->removeRigidBody(world->rigidbodies[i - 1].body);
        }
        if (world->ground_body) {
            world->dynamics_world->removeRigidBody(world->ground_body);
        }
    }
    for (size_t i = 0; i < world->constraint_count; ++i) {
        delete world->constraints[i];
    }
    for (size_t i = 0; i < world->rigidbody_count; ++i) {
        delete world->rigidbodies[i].body;
        delete world->rigidbodies[i].motion_state;
        delete world->rigidbodies[i].shape;
    }
    free(world->constraints);
    free(world->rigidbodies);
    delete world->ground_body;
    delete world->ground_motion_state;
    delete world->ground_shape;
    delete world->dynamics_world;
    delete world->solver;
    delete world->broadphase;
    delete world->dispatcher;
    delete world->collision_configuration;
    delete world;
}

mmd_anim_bullet_status mmd_anim_bullet_world_reset(mmd_anim_bullet_world *world) {
    if (!world) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world is null");
    }

    for (size_t i = 0; i < world->rigidbody_count; ++i) {
        RigidBodyEntry &entry = world->rigidbodies[i];
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
    for (size_t i = 0; i < world->constraint_count; ++i) {
        btTypedConstraint *constraint = world->constraints[i];
#if BT_BULLET_VERSION > 275
        constraint->setEnabled(true);
#endif
    }
    world->dynamics_world->getBroadphase()->getOverlappingPairCache()->cleanProxyFromPairs(NULL, world->dynamics_world->getDispatcher());
    g_last_error[0] = '\0';
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_settle_to_current(mmd_anim_bullet_world *world) {
    if (!world) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world is null");
    }

    world->dynamics_world->clearForces();
    btOverlappingPairCache *pair_cache = world->dynamics_world->getPairCache();
    btDispatcher *dispatcher = world->dynamics_world->getDispatcher();

    for (size_t i = 0; i < world->rigidbody_count; ++i) {
        RigidBodyEntry &entry = world->rigidbodies[i];
        btRigidBody *body = entry.body;
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

    g_last_error[0] = '\0';
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
    for (size_t i = 0; i < world->constraint_count; ++i) {
        btTypedConstraint *constraint = world->constraints[i];
        constraint->setOverrideNumSolverIterations(iterations);
    }
#endif
    g_last_error[0] = '\0';
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
    if (!_finite(delta_time) || delta_time < 0.0f || max_sub_steps < 0 ||
        !_finite(fixed_substep_seconds) || fixed_substep_seconds <= 0.0f) {
        return fail(
            MMD_ANIM_BULLET_INVALID_ARGUMENT,
            "delta_time and max_sub_steps must be non-negative and fixed_substep_seconds must be positive");
    }

    world->dynamics_world->stepSimulation(delta_time, max_sub_steps, fixed_substep_seconds);
    g_last_error[0] = '\0';
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_add_rigidbody(
    mmd_anim_bullet_world *world,
    const mmd_anim_bullet_rigidbody_desc *desc,
    int32_t *out_index) {
    if (!world || !desc || !out_index) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world, desc, or out_index is null");
    }

    btCollisionShape *shape = make_shape(*desc);
        if (!shape) {
            return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "unknown shape type");
        }

        btTransform initial_transform = make_transform(desc->position, desc->rotation_xyzw);
        btVector3 inertia(0.0f, 0.0f, 0.0f);
        const btScalar mass = desc->mass;
        if (mass > 0.0f) {
            calculate_local_inertia(*desc, *shape, mass, inertia);
        }

        btDefaultMotionState *motion_state = new btDefaultMotionState(initial_transform);
        btRigidBody::btRigidBodyConstructionInfo info(mass, motion_state, shape, inertia);
        info.m_linearDamping = desc->linear_damping;
        info.m_angularDamping = desc->angular_damping;
        info.m_friction = desc->friction;
        info.m_restitution = desc->restitution;
        info.m_additionalDamping = false;

        btRigidBody *body = new btRigidBody(info);
        if (mass == 0.0f) {
            body->setCollisionFlags(body->getCollisionFlags() | btCollisionObject::CF_KINEMATIC_OBJECT);
        }
        body->setActivationState(DISABLE_DEACTIVATION);

        const int group = 1 << btMin<uint16_t>(desc->collision_group, 15);
        const int mask = static_cast<int>(desc->collision_mask);
        world->dynamics_world->addRigidBody(body, group, mask);

        RigidBodyEntry entry;
        entry.shape = shape;
        entry.motion_state = motion_state;
        entry.body = body;
        entry.initial_transform = initial_transform;
        if (!append_rigidbody(world, entry)) {
            world->dynamics_world->removeRigidBody(body);
            delete body;
            delete motion_state;
            delete shape;
            return fail(MMD_ANIM_BULLET_INTERNAL_ERROR, "failed to grow rigid body storage");
        }
        *out_index = static_cast<int32_t>(world->rigidbody_count - 1);
        g_last_error[0] = '\0';
    return MMD_ANIM_BULLET_OK;
}

int32_t mmd_anim_bullet_world_get_rigidbody_count(const mmd_anim_bullet_world *world) {
    if (!world) {
        set_last_error("world is null");
        return -1;
    }
    g_last_error[0] = '\0';
    return static_cast<int32_t>(world->rigidbody_count);
}

mmd_anim_bullet_status mmd_anim_bullet_world_get_rigidbody_transform(
    const mmd_anim_bullet_world *world,
    int32_t index,
    float out_position[3],
    float out_rotation_xyzw[4]) {
    if (!world || !out_position || !out_rotation_xyzw) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world or output buffer is null");
    }
    if (index < 0 || static_cast<size_t>(index) >= world->rigidbody_count) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "rigidbody index out of range");
    }

    const RigidBodyEntry &entry = world->rigidbodies[static_cast<size_t>(index)];
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
    g_last_error[0] = '\0';
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
    if (index < 0 || static_cast<size_t>(index) >= world->rigidbody_count) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "rigidbody index out of range");
    }

    btTransform transform;
    transform.setIdentity();
    transform.setOrigin(btVector3(position[0], position[1], position[2]));
    transform.setRotation(btQuaternion(rotation_xyzw[0], rotation_xyzw[1], rotation_xyzw[2], rotation_xyzw[3]));

    RigidBodyEntry &entry = world->rigidbodies[static_cast<size_t>(index)];
    entry.body->setWorldTransform(transform);
    g_last_error[0] = '\0';
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_set_rigidbody_position(
    mmd_anim_bullet_world *world,
    int32_t index,
    const float position[3]) {
    if (!world || !position) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world or position buffer is null");
    }
    if (index < 0 || static_cast<size_t>(index) >= world->rigidbody_count) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "rigidbody index out of range");
    }
    RigidBodyEntry &entry = world->rigidbodies[static_cast<size_t>(index)];
    btTransform transform = entry.body->getWorldTransform();
    transform.setOrigin(btVector3(position[0], position[1], position[2]));
    entry.body->setWorldTransform(transform);
    if (entry.motion_state) {
        entry.motion_state->setWorldTransform(transform);
    }
    g_last_error[0] = '\0';
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
        static_cast<size_t>(desc->rigidbody_index_a) >= world->rigidbody_count ||
        static_cast<size_t>(desc->rigidbody_index_b) >= world->rigidbody_count) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "joint rigidbody index out of range");
    }

    btRigidBody &body_a = *world->rigidbodies[static_cast<size_t>(desc->rigidbody_index_a)].body;
        btRigidBody &body_b = *world->rigidbodies[static_cast<size_t>(desc->rigidbody_index_b)].body;
        btTransform joint_transform = make_transform(desc->position, desc->rotation_xyzw);
        btTransform frame_a = body_a.getWorldTransform().inverse() * joint_transform;
        btTransform frame_b = body_b.getWorldTransform().inverse() * joint_transform;

        btGeneric6DofSpringConstraint *constraint = new btGeneric6DofSpringConstraint(body_a, body_b, frame_a, frame_b, true);
        set_vec3_limit(*constraint, desc->translation_lower_limit, desc->translation_upper_limit);
        set_angular_limit(*constraint, desc->rotation_lower_limit, desc->rotation_upper_limit);
        for (int axis = 0; axis < 3; ++axis) {
            configure_linear_spring_axis(
                *constraint,
                axis,
                axis,
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
        world->dynamics_world->addConstraint(constraint, false);
        if (!append_constraint(world, constraint)) {
            world->dynamics_world->removeConstraint(constraint);
            delete constraint;
            return fail(MMD_ANIM_BULLET_INTERNAL_ERROR, "failed to grow constraint storage");
        }
        *out_index = static_cast<int32_t>(world->constraint_count - 1);
        g_last_error[0] = '\0';
    return MMD_ANIM_BULLET_OK;
}

int32_t mmd_anim_bullet_world_get_constraint_count(const mmd_anim_bullet_world *world) {
    if (!world) {
        set_last_error("world is null");
        return -1;
    }
    g_last_error[0] = '\0';
    return static_cast<int32_t>(world->constraint_count);
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
                mmd_anim_bullet_contact_point &out = out_contacts[count];
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
    g_last_error[0] = '\0';
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
    g_last_error[0] = '\0';
    return MMD_ANIM_BULLET_OK;
}

mmd_anim_bullet_status mmd_anim_bullet_world_set_gravity(
    mmd_anim_bullet_world *world,
    const float gravity_xyz[3]) {
    if (!world || !gravity_xyz) {
        return fail(MMD_ANIM_BULLET_NULL_POINTER, "world or gravity_xyz is null");
    }
    if (!_finite(gravity_xyz[0]) || !_finite(gravity_xyz[1]) || !_finite(gravity_xyz[2])) {
        return fail(MMD_ANIM_BULLET_INVALID_ARGUMENT, "gravity_xyz must be finite");
    }
    world->dynamics_world->setGravity(btVector3(gravity_xyz[0], gravity_xyz[1], gravity_xyz[2]));
    g_last_error[0] = '\0';
    return MMD_ANIM_BULLET_OK;
}

}
