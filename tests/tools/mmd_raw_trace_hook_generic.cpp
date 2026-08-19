#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define BT_NO_PROFILE
#include <windows.h>
#include <btBulletDynamicsCommon.h>

#pragma pack(push, 1)
struct TraceHeader { unsigned int magic, version, call_index, phase, body_count, time_step_bits; int max_substeps; unsigned int fixed_step_bits; };
struct BodyState { float values[48]; int activation_state; int collision_flags; };
#pragma pack(pop)
typedef int (__fastcall *StepFn)(btDiscreteDynamicsWorld*, float, int, float);
static StepFn g_original = 0;
static WCHAR g_output[MAX_PATH * 4] = {0};
static volatile LONG g_call_index = -1;
static BodyState* g_initial_model_states = 0;
static int g_initial_model_count = 0;
static bool g_controlled = false;
static bool g_restored = false;
static bool g_metadata_written = false;
static bool g_no_constraints = false;
static bool g_payload_written = false;
static bool g_constraints_written = false;
static unsigned int float_bits(float value) { union { float f; unsigned int u; } bits; bits.f = value; return bits.u; }
static void write_all(HANDLE file, const void* data, DWORD size) { const BYTE* cursor=static_cast<const BYTE*>(data); while(size){ DWORD written=0; if(!WriteFile(file,cursor,size,&written,0)||!written)return; cursor+=written; size-=written; } }
static void store_transform(float* target, const btTransform& transform) {
    const btMatrix3x3& basis=transform.getBasis(); const btVector3& origin=transform.getOrigin();
    target[0]=basis[0][0];target[1]=basis[0][1];target[2]=basis[0][2];
    target[3]=basis[1][0];target[4]=basis[1][1];target[5]=basis[1][2];
    target[6]=basis[2][0];target[7]=basis[2][1];target[8]=basis[2][2];
    target[9]=origin[0];target[10]=origin[1];target[11]=origin[2];
}
static void store_vec(float* target,const btVector3& value){target[0]=value[0];target[1]=value[1];target[2]=value[2];}
static btTransform load_transform(const float* source) {
    return btTransform(
        btMatrix3x3(
            source[0], source[1], source[2],
            source[3], source[4], source[5],
            source[6], source[7], source[8]),
        btVector3(source[9], source[10], source[11]));
}
static void read_state(btCollisionObject* object, BodyState& state) {
    ZeroMemory(&state,sizeof(state));
    store_transform(state.values+0,object->getWorldTransform());
    store_transform(state.values+12,object->getInterpolationWorldTransform());
    btTransform motion=object->getWorldTransform();
    if(object->getInternalType()==btCollisionObject::CO_RIGID_BODY){
        btRigidBody* body=static_cast<btRigidBody*>(object);
        if(body->getMotionState())body->getMotionState()->getWorldTransform(motion);
        store_vec(state.values+36,body->getLinearVelocity());
        store_vec(state.values+39,body->getAngularVelocity());
    }
    store_transform(state.values+24,motion);
    store_vec(state.values+42,object->getInterpolationLinearVelocity());
    store_vec(state.values+45,object->getInterpolationAngularVelocity());
    state.activation_state=object->getActivationState();
    state.collision_flags=object->getCollisionFlags();
}
static void apply_state(btCollisionObject* object, const BodyState& state) {
    object->setWorldTransform(load_transform(state.values+0));
    object->setInterpolationWorldTransform(load_transform(state.values+12));
    object->setInterpolationLinearVelocity(btVector3(state.values[42],state.values[43],state.values[44]));
    object->setInterpolationAngularVelocity(btVector3(state.values[45],state.values[46],state.values[47]));
    object->setCollisionFlags(state.collision_flags);
    if(object->getInternalType()==btCollisionObject::CO_RIGID_BODY){
        btRigidBody* body=static_cast<btRigidBody*>(object);
        body->setLinearVelocity(btVector3(state.values[36],state.values[37],state.values[38]));
        body->setAngularVelocity(btVector3(state.values[39],state.values[40],state.values[41]));
        body->clearForces();
        if(body->getMotionState())body->getMotionState()->setWorldTransform(load_transform(state.values+24));
    }
}
static void save_initial_model_state(btDiscreteDynamicsWorld* world) {
    if(g_initial_model_states)return;
    btCollisionObjectArray& objects=world->getCollisionObjectArray();
    if(objects.size()<=1)return;
    g_initial_model_count=objects.size()-1;
    g_initial_model_states=static_cast<BodyState*>(HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,sizeof(BodyState)*g_initial_model_count));
    if(!g_initial_model_states){g_initial_model_count=0;return;}
    for(int index=0;index<g_initial_model_count;++index)read_state(objects[index+1],g_initial_model_states[index]);
}
static void write_metadata(btDiscreteDynamicsWorld* world) {
    if(g_metadata_written||!g_output[0])return;
    g_metadata_written=true;
    struct Metadata {
        unsigned int magic, version;
        unsigned __int64 world_vtable, broadphase_vtable, pair_cache_vtable, dispatcher_vtable, solver_vtable;
        float gravity[3];
        int iterations, solver_mode, split_impulse;
        float erp, erp2, global_cfm, warmstarting_factor;
    } metadata;
    ZeroMemory(&metadata,sizeof(metadata));
    metadata.magic=0x4154454d;metadata.version=1;
    BYTE* base=reinterpret_cast<BYTE*>(GetModuleHandleW(0));
    metadata.world_vtable=*reinterpret_cast<unsigned __int64*>(world)-reinterpret_cast<unsigned __int64>(base);
    metadata.broadphase_vtable=*reinterpret_cast<unsigned __int64*>(world->getBroadphase())-reinterpret_cast<unsigned __int64>(base);
    metadata.pair_cache_vtable=*reinterpret_cast<unsigned __int64*>(world->getPairCache())-reinterpret_cast<unsigned __int64>(base);
    metadata.dispatcher_vtable=*reinterpret_cast<unsigned __int64*>(world->getDispatcher())-reinterpret_cast<unsigned __int64>(base);
    metadata.solver_vtable=*reinterpret_cast<unsigned __int64*>(world->getConstraintSolver())-reinterpret_cast<unsigned __int64>(base);
    btVector3 gravity=world->getGravity();metadata.gravity[0]=gravity[0];metadata.gravity[1]=gravity[1];metadata.gravity[2]=gravity[2];
    const btContactSolverInfo& info=world->getSolverInfo();metadata.iterations=info.m_numIterations;metadata.solver_mode=info.m_solverMode;metadata.split_impulse=info.m_splitImpulse;metadata.erp=info.m_erp;metadata.erp2=info.m_erp2;metadata.global_cfm=info.m_globalCfm;metadata.warmstarting_factor=info.m_warmstartingFactor;
    WCHAR path[MAX_PATH*4];lstrcpyW(path,g_output);lstrcatW(path,L".meta");HANDLE file=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,0,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,0);if(file!=INVALID_HANDLE_VALUE){write_all(file,&metadata,sizeof(metadata));CloseHandle(file);}
}
static void write_payload(btDiscreteDynamicsWorld* world) {
    if(g_payload_written||!g_output[0])return;
    btCollisionObjectArray& objects=world->getCollisionObjectArray();if(objects.size()<=1)return;g_payload_written=true;
    struct Payload { float values[24]; int shape_type, group, mask, collision_flags; };
    WCHAR path[MAX_PATH*4];lstrcpyW(path,g_output);lstrcatW(path,L".payload");HANDLE file=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,0,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,0);if(file==INVALID_HANDLE_VALUE)return;
    unsigned int header[3]={0x4c594150,1,static_cast<unsigned int>(objects.size())};write_all(file,header,sizeof(header));
    for(int index=0;index<objects.size();++index){Payload payload;ZeroMemory(&payload,sizeof(payload));btCollisionObject* object=objects[index];btRigidBody* body=btRigidBody::upcast(object);if(body){payload.values[0]=body->getInvMass();store_vec(payload.values+1,body->getInvInertiaDiagLocal());payload.values[4]=body->getLinearDamping();payload.values[5]=body->getAngularDamping();store_vec(payload.values+18,body->getLinearFactor());store_vec(payload.values+21,body->getAngularFactor());}payload.values[6]=object->getFriction();payload.values[7]=object->getRestitution();btCollisionShape* shape=object->getCollisionShape();payload.values[8]=shape->getMargin();store_vec(payload.values+9,shape->getLocalScaling());btVector3 aabb_min,aabb_max;shape->getAabb(object->getWorldTransform(),aabb_min,aabb_max);store_vec(payload.values+12,aabb_min);store_vec(payload.values+15,aabb_max);payload.shape_type=shape->getShapeType();btBroadphaseProxy* proxy=object->getBroadphaseHandle();if(proxy){payload.group=proxy->m_collisionFilterGroup;payload.mask=proxy->m_collisionFilterMask;}payload.collision_flags=object->getCollisionFlags();write_all(file,&payload,sizeof(payload));}
    CloseHandle(file);
}
static int object_index(btDiscreteDynamicsWorld* world,const btCollisionObject* target){btCollisionObjectArray& objects=world->getCollisionObjectArray();for(int index=0;index<objects.size();++index)if(objects[index]==target)return index;return -1;}
static void write_constraints(btDiscreteDynamicsWorld* world) {
    if(g_constraints_written||!g_output[0]||world->getNumConstraints()<=0)return;g_constraints_written=true;
    struct ConstraintPayload { float values[36]; int body_a,body_b,use_offset,constraint_type; };
    WCHAR path[MAX_PATH*4];lstrcpyW(path,g_output);lstrcatW(path,L".constraints");HANDLE file=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,0,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,0);if(file==INVALID_HANDLE_VALUE)return;unsigned int header[3]={0x54534e43,1,static_cast<unsigned int>(world->getNumConstraints())};write_all(file,header,sizeof(header));
    for(int index=0;index<world->getNumConstraints();++index){ConstraintPayload payload;ZeroMemory(&payload,sizeof(payload));btTypedConstraint* typed=world->getConstraint(index);btGeneric6DofConstraint* constraint=static_cast<btGeneric6DofConstraint*>(typed);store_transform(payload.values+0,constraint->getFrameOffsetA());store_transform(payload.values+12,constraint->getFrameOffsetB());btTranslationalLimitMotor* linear=constraint->getTranslationalLimitMotor();store_vec(payload.values+24,linear->m_lowerLimit);store_vec(payload.values+27,linear->m_upperLimit);for(int axis=0;axis<3;++axis){btRotationalLimitMotor* angular=constraint->getRotationalLimitMotor(axis);payload.values[30+axis]=angular->m_loLimit;payload.values[33+axis]=angular->m_hiLimit;}payload.body_a=object_index(world,&typed->getRigidBodyA());payload.body_b=object_index(world,&typed->getRigidBodyB());payload.use_offset=0;payload.constraint_type=typed->getConstraintType();write_all(file,&payload,sizeof(payload));}
    CloseHandle(file);
}
static void prepare_controlled_world(btDiscreteDynamicsWorld* world) {
    if(!g_controlled||g_restored||!g_initial_model_states)return;
    btCollisionObjectArray& objects=world->getCollisionObjectArray();
    if(objects.size()!=g_initial_model_count+1)return;
    btRigidBody** bodies=static_cast<btRigidBody**>(HeapAlloc(GetProcessHeap(),0,sizeof(btRigidBody*)*g_initial_model_count));
    short* groups=static_cast<short*>(HeapAlloc(GetProcessHeap(),0,sizeof(short)*g_initial_model_count));
    short* masks=static_cast<short*>(HeapAlloc(GetProcessHeap(),0,sizeof(short)*g_initial_model_count));
    if(!bodies||!groups||!masks)return;
    for(int index=0;index<g_initial_model_count;++index){bodies[index]=static_cast<btRigidBody*>(objects[index+1]);btBroadphaseProxy* proxy=bodies[index]->getBroadphaseHandle();groups[index]=proxy->m_collisionFilterGroup;masks[index]=proxy->m_collisionFilterMask;}
    for(int index=g_initial_model_count-1;index>=0;--index)world->removeRigidBody(bodies[index]);
    for(int index=0;index<g_initial_model_count;++index){apply_state(bodies[index],g_initial_model_states[index]);world->addRigidBody(bodies[index],groups[index],masks[index]);}
    HeapFree(GetProcessHeap(),0,masks);HeapFree(GetProcessHeap(),0,groups);HeapFree(GetProcessHeap(),0,bodies);
    if(g_no_constraints){for(int index=world->getNumConstraints()-1;index>=0;--index)world->removeConstraint(world->getConstraint(index));}
    world->clearForces();
    world->updateAabbs();
    g_restored=true;
}
static void capture(btDiscreteDynamicsWorld* world,unsigned int call_index,unsigned int phase,float time_step,int max_substeps,float fixed_step){
    if(!g_output[0]||!world)return; btCollisionObjectArray& objects=world->getCollisionObjectArray(); const int count=objects.size(); if(count<=0||count>20000)return;
    HANDLE file=CreateFileW(g_output,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,0,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,0); if(file==INVALID_HANDLE_VALUE)return;
    TraceHeader header={0x5442524d,2,call_index,phase,static_cast<unsigned int>(count),float_bits(time_step),max_substeps,float_bits(fixed_step)}; write_all(file,&header,sizeof(header));
    for(int index=0;index<count;++index){
        BodyState state; read_state(objects[index],state); write_all(file,&state,sizeof(state));
    } CloseHandle(file);
}
static int __fastcall hook_step(btDiscreteDynamicsWorld* world,float time_step,int max_substeps,float fixed_step){
    unsigned int call_index=static_cast<unsigned int>(InterlockedIncrement(&g_call_index));
    write_metadata(world);
    if(time_step>0.0f&&!g_initial_model_states)save_initial_model_state(world);
    if(time_step>0.0f)g_controlled=true;
    if(g_controlled&&time_step>0.0f)prepare_controlled_world(world);
    if(time_step>0.0f)write_payload(world);
    if(time_step>0.0f)write_constraints(world);
    capture(world,call_index,0,time_step,max_substeps,fixed_step);
    int result=g_original(world,time_step,max_substeps,fixed_step);
    capture(world,call_index,1,time_step,max_substeps,fixed_step);
    return result;
}
extern "C" __declspec(dllexport) int install_for_module(const wchar_t* module_name,unsigned __int64 vtable_rva){HMODULE module=GetModuleHandleW(module_name);if(!module)return 0;BYTE* base=reinterpret_cast<BYTE*>(module);void** slot=reinterpret_cast<void**>(base+vtable_rva+7*sizeof(void*));DWORD old_protect=0;if(!VirtualProtect(slot,sizeof(void*),PAGE_EXECUTE_READWRITE,&old_protect))return 0;g_original=reinterpret_cast<StepFn>(*slot);*slot=reinterpret_cast<void*>(&hook_step);FlushInstructionCache(GetCurrentProcess(),slot,sizeof(void*));DWORD ignored=0;VirtualProtect(slot,sizeof(void*),old_protect,&ignored);return 1;}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID){if(reason==DLL_PROCESS_ATTACH){DisableThreadLibraryCalls(instance);GetEnvironmentVariableW(L"MMD_RAW_TRACE",g_output,sizeof(g_output)/sizeof(g_output[0]));}return TRUE;}

