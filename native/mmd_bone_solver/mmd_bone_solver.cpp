#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <map>
#include <xmmintrin.h>
#include <stdexcept>
#include <string>
#include <vector>

#define SPX_API extern "C" __declspec(dllexport)

struct Vec3 { float x, y, z; };
struct Vec4 { float x, y, z, w; };
struct Quat { float x, y, z, w; };
struct Mat4 { float m[16]; };

static std::string g_error;
typedef Quat* (WINAPI *D3DXQuatNormalizeFn)(Quat*,const Quat*);
typedef Quat* (WINAPI *D3DXQuatInverseFn)(Quat*,const Quat*);
typedef Quat* (WINAPI *D3DXQuatMultiplyFn)(Quat*,const Quat*,const Quat*);
typedef Quat* (WINAPI *D3DXQuatRotationAxisFn)(Quat*,const Vec3*,float);
typedef void (WINAPI *D3DXQuatToAxisAngleFn)(const Quat*,Vec3*,float*);
typedef Quat* (WINAPI *D3DXQuatRotationMatrixFn)(Quat*,const Mat4*);
typedef Quat* (WINAPI *D3DXQuatSlerpFn)(Quat*,const Quat*,const Quat*,float);
typedef Mat4* (WINAPI *D3DXMatrixRotationQuatFn)(Mat4*,const Quat*);
typedef Mat4* (WINAPI *D3DXMatrixRotationAxisFn)(Mat4*,float);
typedef Mat4* (WINAPI *D3DXMatrixMultiplyFn)(Mat4*,const Mat4*,const Mat4*);
typedef Mat4* (WINAPI *D3DXMatrixInverseFn)(Mat4*,float*,const Mat4*);
typedef Vec4* (WINAPI *D3DXVec3TransformFn)(Vec4*,const Vec3*,const Mat4*);
typedef Vec3* (WINAPI *D3DXVec3NormalizeFn)(Vec3*,const Vec3*);
static D3DXQuatNormalizeFn g_d3dx_qnorm=0;
static D3DXQuatInverseFn g_d3dx_qinverse=0;
static D3DXQuatMultiplyFn g_d3dx_qmultiply=0;
static D3DXQuatRotationAxisFn g_d3dx_qaxis=0;
static D3DXQuatToAxisAngleFn g_d3dx_to_axis_angle=0;
static D3DXQuatRotationMatrixFn g_d3dx_qfrom_matrix=0;
static D3DXQuatSlerpFn g_d3dx_qslerp=0;
static D3DXMatrixRotationQuatFn g_d3dx_mrotq=0;
static D3DXMatrixRotationAxisFn g_d3dx_mrotx=0,g_d3dx_mroty=0,g_d3dx_mrotz=0;
static D3DXMatrixMultiplyFn g_d3dx_mmul=0;
static D3DXMatrixInverseFn g_d3dx_minverse=0;
static D3DXVec3TransformFn g_d3dx_transform=0;
static D3DXVec3NormalizeFn g_d3dx_vnormalize=0;
static void load_d3dx(){
    if(g_d3dx_mmul)return;
    HMODULE m=LoadLibraryW(L"d3dx9_43.dll");
    if(!m)throw std::runtime_error("d3dx9_43.dll is unavailable");
    g_d3dx_qnorm=(D3DXQuatNormalizeFn)GetProcAddress(m,"D3DXQuaternionNormalize");
    g_d3dx_qinverse=(D3DXQuatInverseFn)GetProcAddress(m,"D3DXQuaternionInverse");
    g_d3dx_qmultiply=(D3DXQuatMultiplyFn)GetProcAddress(m,"D3DXQuaternionMultiply");
    g_d3dx_qaxis=(D3DXQuatRotationAxisFn)GetProcAddress(m,"D3DXQuaternionRotationAxis");
    g_d3dx_to_axis_angle=(D3DXQuatToAxisAngleFn)GetProcAddress(m,"D3DXQuaternionToAxisAngle");
    g_d3dx_qfrom_matrix=(D3DXQuatRotationMatrixFn)GetProcAddress(m,"D3DXQuaternionRotationMatrix");
    g_d3dx_qslerp=(D3DXQuatSlerpFn)GetProcAddress(m,"D3DXQuaternionSlerp");
    g_d3dx_mrotq=(D3DXMatrixRotationQuatFn)GetProcAddress(m,"D3DXMatrixRotationQuaternion");
    g_d3dx_mrotx=(D3DXMatrixRotationAxisFn)GetProcAddress(m,"D3DXMatrixRotationX");
    g_d3dx_mroty=(D3DXMatrixRotationAxisFn)GetProcAddress(m,"D3DXMatrixRotationY");
    g_d3dx_mrotz=(D3DXMatrixRotationAxisFn)GetProcAddress(m,"D3DXMatrixRotationZ");
    g_d3dx_mmul=(D3DXMatrixMultiplyFn)GetProcAddress(m,"D3DXMatrixMultiply");
    g_d3dx_minverse=(D3DXMatrixInverseFn)GetProcAddress(m,"D3DXMatrixInverse");
    g_d3dx_transform=(D3DXVec3TransformFn)GetProcAddress(m,"D3DXVec3Transform");
    g_d3dx_vnormalize=(D3DXVec3NormalizeFn)GetProcAddress(m,"D3DXVec3Normalize");
    if(!g_d3dx_qnorm||!g_d3dx_qinverse||!g_d3dx_qmultiply||!g_d3dx_qaxis||!g_d3dx_to_axis_angle||!g_d3dx_qfrom_matrix||!g_d3dx_qslerp||!g_d3dx_mrotq||!g_d3dx_mrotx||!g_d3dx_mroty||!g_d3dx_mrotz||!g_d3dx_mmul||!g_d3dx_minverse||!g_d3dx_transform||!g_d3dx_vnormalize)throw std::runtime_error("D3DX math exports are unavailable");
}

static Vec3 v3(float x, float y, float z) { Vec3 v = {x, y, z}; return v; }
static Quat q4(float x, float y, float z, float w) { Quat q = {x, y, z, w}; return q; }
static Vec3 add(Vec3 a, Vec3 b) { return v3(a.x+b.x, a.y+b.y, a.z+b.z); }
static Vec3 sub(Vec3 a, Vec3 b) { return v3(a.x-b.x, a.y-b.y, a.z-b.z); }
static Vec3 mul(Vec3 a, float s) { return v3(a.x*s, a.y*s, a.z*s); }
static float dot(Vec3 a, Vec3 b) { return a.x*b.x+a.y*b.y+a.z*b.z; }
static Vec3 cross(Vec3 a, Vec3 b) { return v3(a.y*b.z-a.z*b.y, a.z*b.x-a.x*b.z, a.x*b.y-a.y*b.x); }
static float length(Vec3 a) { return sqrtf(dot(a,a)); }
static float ordered_sum3(float a,float b,float c){volatile float ab=a+b;return ab+c;}
static __declspec(noinline) float ordered_div(float a,float b){return _mm_cvtss_f32(_mm_div_ss(_mm_set_ss(a),_mm_set_ss(b)));}
static Vec3 normalize(Vec3 a) { load_d3dx();Vec3 r;g_d3dx_vnormalize(&r,&a);return r; }
static Quat qmul(Quat a, Quat b) {
    return q4(a.w*b.x+a.x*b.w+a.y*b.z-a.z*b.y,
              a.w*b.y-a.x*b.z+a.y*b.w+a.z*b.x,
              a.w*b.z+a.x*b.y-a.y*b.x+a.z*b.w,
              a.w*b.w-a.x*b.x-a.y*b.y-a.z*b.z);
}
static Quat qnorm(Quat q) { load_d3dx(); Quat r; g_d3dx_qnorm(&r,&q); return r; }
static Quat qinverse(Quat q){load_d3dx();Quat r;g_d3dx_qinverse(&r,&q);return r;}
static Quat qmultiply_d3dx(Quat first,Quat second){load_d3dx();Quat r;g_d3dx_qmultiply(&r,&first,&second);return r;}
static Quat qaxis(Vec3 a,float t) { float h=t*0.5f,s=sinf(h); return q4(a.x*s,a.y*s,a.z*s,cosf(h)); }
static Quat qslerp(Quat a, Quat b, float t) {
    volatile float c=a.y*b.y;
    c=c+a.x*b.x;
    c=c+a.z*b.z;
    c=c+a.w*b.w;
    volatile float distance=1.0f-c*c;
    if(distance==0.0f)return a;
    const float edge=0.99999898672103881836f;
    if(c>edge)c=edge;
    else if(c<-edge)c=-edge;
    float angle=acosf(c);
    if(c<0.0f&&angle>1.57079601287841796875f){
        c=-c;
        angle=acosf(c);
        float denominator=sinf(angle);
        float first=sinf((1.0f-t)*angle)/denominator;
        float second=sinf(t*angle)/denominator;
        return q4(a.x*first-b.x*second,a.y*first-b.y*second,a.z*first-b.z*second,a.w*first-b.w*second);
    }
    float denominator=sinf(angle);
    float first=sinf((1.0f-t)*angle)/denominator;
    float second=sinf(t*angle)/denominator;
    return q4(a.x*first+b.x*second,a.y*first+b.y*second,a.z*first+b.z*second,a.w*first+b.w*second);
}
static Quat qslerp_d3dx(Quat a,Quat b,float t){load_d3dx();Quat r;g_d3dx_qslerp(&r,&a,&b,t);return r;}
static Mat4 identity(){Mat4 r={{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1}};return r;}
static Mat4 translation(Vec3 v){Mat4 r=identity();r.m[12]=v.x;r.m[13]=v.y;r.m[14]=v.z;return r;}
static Mat4 local_matrix(Quat q, Vec3 t) {
    load_d3dx(); q=qnorm(q); Mat4 r; g_d3dx_mrotq(&r,&q);r.m[12]=t.x;r.m[13]=t.y;r.m[14]=t.z;return r;
}
static Mat4 mmul(const Mat4&a,const Mat4&b){load_d3dx();Mat4 r;g_d3dx_mmul(&r,&a,&b);return r;}
static Mat4 minverse(const Mat4&m){load_d3dx();Mat4 r;g_d3dx_minverse(&r,0,&m);return r;}
static Mat4 rigid_rest_matrix(Vec3 position,Vec3 rotation){load_d3dx();Mat4 rx,ry,rz,zx,result;g_d3dx_mrotx(&rx,rotation.x);g_d3dx_mroty(&ry,rotation.y);g_d3dx_mrotz(&rz,rotation.z);g_d3dx_mmul(&zx,&rz,&rx);g_d3dx_mmul(&result,&zx,&ry);result.m[12]=position.x;result.m[13]=position.y;result.m[14]=position.z;return result;}
static Mat4 rigid_rest_inverse(Vec3 position,Vec3 rotation){
    load_d3dx();Mat4 rx,ry,rz,negative=translation(v3(-position.x,-position.y,-position.z)),step_y,step_x,result;
    g_d3dx_mroty(&ry,-rotation.y);g_d3dx_mrotx(&rx,-rotation.x);g_d3dx_mrotz(&rz,-rotation.z);
    g_d3dx_mmul(&step_y,&negative,&ry);g_d3dx_mmul(&step_x,&step_y,&rx);g_d3dx_mmul(&result,&step_x,&rz);return result;
}
static Quat bullet_quat_from_matrix(const Mat4&m){float trace=m.m[0]+m.m[5]+m.m[10],t[4];if(trace>0.0f){float s=sqrtf(trace+1.0f);t[3]=s*0.5f;s=0.5f/s;t[0]=(m.m[6]-m.m[9])*s;t[1]=(m.m[8]-m.m[2])*s;t[2]=(m.m[1]-m.m[4])*s;}else{float d[3]={m.m[0],m.m[5],m.m[10]};int i=d[0]<d[1]?(d[1]<d[2]?2:1):(d[0]<d[2]?2:0),j=(i+1)%3,k=(i+2)%3;float r[3][3]={{m.m[0],m.m[4],m.m[8]},{m.m[1],m.m[5],m.m[9]},{m.m[2],m.m[6],m.m[10]}};float s=sqrtf(r[i][i]-r[j][j]-r[k][k]+1.0f);t[i]=s*0.5f;s=0.5f/s;t[3]=(r[k][j]-r[j][k])*s;t[j]=(r[j][i]+r[i][j])*s;t[k]=(r[k][i]+r[i][k])*s;}return q4(t[0],t[1],t[2],t[3]);}
static __declspec(noinline) float ordered_transform_component(float x,float mx,float y,float my,float z,float mz,float t){volatile float r=x*mx;r=r+y*my;r=r+z*mz;r=r+t;return r;}
static Vec3 transform_point(Vec3 v,const Mat4&m){return v3(ordered_transform_component(v.x,m.m[0],v.y,m.m[4],v.z,m.m[8],m.m[12]),ordered_transform_component(v.x,m.m[1],v.y,m.m[5],v.z,m.m[9],m.m[13]),ordered_transform_component(v.x,m.m[2],v.y,m.m[6],v.z,m.m[10],m.m[14]));}
static Vec3 qrotate(Quat q,Vec3 v){Quat p=q4(v.x,v.y,v.z,0),qi=q4(-q.x,-q.y,-q.z,q.w),r=qmul(qmul(q,p),qi);return v3(r.x,r.y,r.z);}
static Vec3 q_to_yxz(Quat q){float xx=q.x*q.x,yy=q.y*q.y,zz=q.z*q.z;float sy=2.0f*(q.x*q.z-q.w*q.y);sy=std::max(-1.0f,std::min(1.0f,-sy));float x=atan2f(2.0f*(q.y*q.z+q.w*q.x),1.0f-2.0f*(xx+yy));float y=asinf(sy);float z=atan2f(2.0f*(q.x*q.y+q.w*q.z),1.0f-2.0f*(yy+zz));return v3(x,y,z);}
static Quat q_from_yxz(Vec3 e){Quat qy=qaxis(v3(0,1,0),e.y),qx=qaxis(v3(1,0,0),e.x),qz=qaxis(v3(0,0,1),e.z);return qnorm(qmul(qmul(qy,qx),qz));}
static Vec3 q_to_xyz(Quat q){load_d3dx();Mat4 m;g_d3dx_mrotq(&m,&q);float y=asinf(std::max(-1.0f,std::min(1.0f,-m.m[2])));float cy=cosf(y);if(fabsf(y)>1.5358890295028687f){y=y<0?-1.5358890295028687f:1.5358890295028687f;cy=cosf(y);}return v3(atan2f(ordered_div(m.m[6],cy),ordered_div(m.m[10],cy)),y,atan2f(ordered_div(m.m[1],cy),ordered_div(m.m[0],cy)));}
static Quat q_from_xyz(Vec3 e,Mat4*out=0){load_d3dx();Mat4 x,y,z,xy,xyz;g_d3dx_mrotx(&x,e.x);g_d3dx_mroty(&y,e.y);g_d3dx_mrotz(&z,e.z);g_d3dx_mmul(&xy,&x,&y);g_d3dx_mmul(&xyz,&xy,&z);if(out)*out=xyz;Quat q;g_d3dx_qfrom_matrix(&q,&xyz);return q;}
static Vec3 q_to_zxy(Quat q){load_d3dx();Mat4 m;g_d3dx_mrotq(&m,&q);float x=asinf(std::max(-1.0f,std::min(1.0f,-m.m[9])));float cx=cosf(x);if(fabsf(x)>1.5358890295028687f){x=x<0?-1.5358890295028687f:1.5358890295028687f;cx=cosf(x);}float ya=ordered_div(m.m[8],cx),yb=ordered_div(m.m[10],cx),za=ordered_div(m.m[1],cx),zb=ordered_div(m.m[5],cx);return v3(x,atan2f(ya,yb),atan2f(za,zb));}
static Quat q_from_zxy(Vec3 e,Mat4*out=0){load_d3dx();Mat4 x,y,z,zx,zxy;g_d3dx_mrotx(&x,e.x);g_d3dx_mroty(&y,e.y);g_d3dx_mrotz(&z,e.z);g_d3dx_mmul(&zx,&z,&x);g_d3dx_mmul(&zxy,&zx,&y);if(out)*out=zxy;Quat q;g_d3dx_qfrom_matrix(&q,&zxy);return q;}
static float normalized_angle(float a){const float pi=3.14159265358979323846f,two_pi=6.28318530717958647692f;while(a>pi)a-=two_pi;while(a<-pi)a+=two_pi;return a;}
static float angle_difference(float a,float b){return normalized_angle(normalized_angle(a)-normalized_angle(b));}
static float constrain_ik_angle(float value,float lo,float hi,bool clamp_only){if(value<lo){float reflected=lo*2.0f-value;return clamp_only||reflected>hi?lo:reflected;}if(value>hi){float reflected=hi*2.0f-value;return clamp_only||reflected<lo?hi:reflected;}return value;}
static Vec3 q_to_yxz_candidate(Quat q,Vec3 before){
    Vec3 basic=q_to_yxz(q),best=basic;float best_error=fabsf(angle_difference(basic.x,before.x))+fabsf(angle_difference(basic.y,before.y))+fabsf(angle_difference(basic.z,before.z));
    const float pi=3.14159265358979323846f;const float signs[2]={pi,-pi};
    for(int ix=0;ix<2;ix++)for(int iy=0;iy<2;iy++)for(int iz=0;iz<2;iz++){Vec3 candidate=v3(basic.x+signs[ix],pi-basic.y+signs[iy],basic.z+signs[iz]);float error=fabsf(angle_difference(candidate.x,before.x))+fabsf(angle_difference(candidate.y,before.y))+fabsf(angle_difference(candidate.z,before.z));if(error<best_error){best_error=error;best=candidate;}}
    return best;
}
static Quat quat_from_matrix(const Mat4&m){
    float tr=m.m[0]+m.m[5]+m.m[10]; Quat q;
    if(tr>0){float s=sqrtf(tr+1)*2;q.w=.25f*s;q.x=(m.m[6]-m.m[9])/s;q.y=(m.m[8]-m.m[2])/s;q.z=(m.m[1]-m.m[4])/s;}
    else if(m.m[0]>m.m[5]&&m.m[0]>m.m[10]){float s=sqrtf(1+m.m[0]-m.m[5]-m.m[10])*2;q.w=(m.m[6]-m.m[9])/s;q.x=.25f*s;q.y=(m.m[4]+m.m[1])/s;q.z=(m.m[8]+m.m[2])/s;}
    else if(m.m[5]>m.m[10]){float s=sqrtf(1+m.m[5]-m.m[0]-m.m[10])*2;q.w=(m.m[8]-m.m[2])/s;q.x=(m.m[4]+m.m[1])/s;q.y=.25f*s;q.z=(m.m[9]+m.m[6])/s;}
    else{float s=sqrtf(1+m.m[10]-m.m[0]-m.m[5])*2;q.w=(m.m[1]-m.m[4])/s;q.x=(m.m[8]+m.m[2])/s;q.y=(m.m[9]+m.m[6])/s;q.z=.25f*s;}return qnorm(q);
}

class Reader {
public:
    const unsigned char *p,*e;
    Reader(const void*d,size_t n):p((const unsigned char*)d),e(p+n){}
    void need(size_t n){if((size_t)(e-p)<n)throw std::runtime_error("truncated input");}
    template<class T>T get(){need(sizeof(T));T v;memcpy(&v,p,sizeof(T));p+=sizeof(T);return v;}
    void skip(size_t n){need(n);p+=n;}
    std::wstring text(bool utf8){int n=get<int>();if(n<0)throw std::runtime_error("negative string length");need(n);if(!n)return L"";if(!utf8){if(n&1)throw std::runtime_error("odd UTF-16 string length");std::wstring w((const wchar_t*)p,(size_t)n/2);p+=n;return w;}int chars=MultiByteToWideChar(CP_UTF8,0,(LPCSTR)p,n,0,0);if(chars<=0)throw std::runtime_error("invalid UTF-8 string");std::vector<wchar_t>b(chars);MultiByteToWideChar(CP_UTF8,0,(LPCSTR)p,n,&b[0],chars);p+=n;return std::wstring(b.begin(),b.end());}
    std::wstring sjis(size_t n){need(n);size_t z=0;while(z<n&&p[z])z++;int chars=MultiByteToWideChar(932,0,(LPCSTR)p,(int)z,0,0);std::vector<wchar_t>b(chars);if(chars)MultiByteToWideChar(932,0,(LPCSTR)p,(int)z,&b[0],chars);p+=n;return std::wstring(b.begin(),b.end());}
};
static int index(Reader&r,int s){if(s==1)return (int)r.get<signed char>();if(s==2)return (int)r.get<short>();return r.get<int>();}
static unsigned int uindex(Reader&r,int s){if(s==1)return r.get<unsigned char>();if(s==2)return r.get<unsigned short>();return r.get<unsigned int>();}
static Vec3 read_v3(Reader&r){Vec3 v={r.get<float>(),r.get<float>(),r.get<float>()};return v;}
static Quat read_q(Reader&r){Quat q={r.get<float>(),r.get<float>(),r.get<float>(),r.get<float>()};return q;}

struct Link {int bone; bool limited; Vec3 lo,hi;};
struct Bone {
    std::wstring name; Vec3 position; int parent,level; unsigned short flags; int append_source; float append_ratio; Vec3 fixed_axis; int ik_target,ik_loops; float ik_limit; std::vector<Link> links;
    Bone():parent(-1),level(0),flags(0),append_source(-1),append_ratio(0),fixed_axis(v3(0,0,0)),ik_target(-1),ik_loops(0),ik_limit(0){}
};
struct BoneMorph {int bone;Vec3 position;Quat rotation;};
struct Morph {std::wstring name; unsigned char type; std::vector<std::pair<int,float> > group; std::vector<BoneMorph> bones;};
struct Rigid {int bone;Vec3 position,rotation;unsigned char mode;Rigid():bone(-1),position(v3(0,0,0)),rotation(v3(0,0,0)),mode(0){}};
struct BoneKey {unsigned int frame;Vec3 position;Quat rotation;unsigned char interp[64];};
struct MorphKey {unsigned int frame;float weight;};
struct PropertyKey {unsigned int frame;std::map<std::wstring,bool> ik;};
struct BoneLevelLess { const std::vector<Bone>* bones; BoneLevelLess(const std::vector<Bone>*v):bones(v){} bool operator()(int a,int b)const{return (*bones)[a].level<(*bones)[b].level;} };
struct BoneKeyLess { bool operator()(const BoneKey&a,const BoneKey&b)const{return a.frame<b.frame;} };
struct MorphKeyLess { bool operator()(const MorphKey&a,const MorphKey&b)const{return a.frame<b.frame;} };

struct Solver {
    Solver():has_evaluated(false),last_frame(0.0f),live_mode(false){}
    bool has_evaluated;float last_frame;bool live_mode;
    std::vector<Bone>bones; std::vector<Morph>morphs; std::vector<Rigid>rigids; std::map<std::wstring,std::vector<BoneKey> >bone_tracks; std::map<std::wstring,std::vector<MorphKey> >morph_tracks; std::vector<PropertyKey>property_keys;
    std::vector<Vec3>pos,physical_pos;std::vector<Quat>rot,ikrot,appendrot,selfrot,delayedrot,fixedrot,physical_rot;std::vector<unsigned char>ik_applied,fixedrot_valid,external_active,external_rigid_active,physical_active,physical_mode,live_active,live_ik_enabled;std::vector<Vec3>appendpos,selfpos,delayedpos;std::vector<Mat4>local,world,external_world,external_rigid_world,live_world;std::vector<float>live_morph_weights;std::vector<int>order;std::map<std::wstring,int>bone_map,morph_map;
};

static __declspec(noinline) float reconstruct_rigid_component(float bone,float rigid){volatile float relative=rigid-bone;return bone+relative;}
static Vec3 mmd_rigid_position(const Solver&s,const Rigid&r){if(r.bone<0||r.bone>=(int)s.bones.size())return r.position;const Vec3&b=s.bones[r.bone].position;return v3(reconstruct_rigid_component(b.x,r.position.x),reconstruct_rigid_component(b.y,r.position.y),reconstruct_rigid_component(b.z,r.position.z));}

static void skip_vertices(Reader&r,int count,int add_uv,int bone_size){
    for(int i=0;i<count;i++){r.skip(12+12+8+add_uv*16);unsigned char d=r.get<unsigned char>();if(d==0)r.skip(bone_size);else if(d==1)r.skip(2*bone_size+4);else if(d==2||d==4)r.skip(4*bone_size+16);else if(d==3)r.skip(2*bone_size+4+36);else throw std::runtime_error("unknown vertex deform");r.skip(4);}
}
static void parse_pmx(Solver&s,const void*data,size_t size){
    Reader r(data,size);r.need(4);if(memcmp(r.p,"PMX ",4))throw std::runtime_error("not PMX");r.skip(4);r.get<float>();int hs=r.get<unsigned char>();r.need(hs);unsigned char enc=r.p[0],add_uv=r.p[1],vis=r.p[2],tis=r.p[3],mis=r.p[4],bis=r.p[5],mos=r.p[6],ris=r.p[7];r.skip(hs);bool utf8=enc!=0;
    r.text(utf8);r.text(utf8);r.text(utf8);r.text(utf8);
    int vc=r.get<int>();skip_vertices(r,vc,add_uv,bis);int ic=r.get<int>();r.skip((size_t)ic*vis);
    int tc=r.get<int>();for(int i=0;i<tc;i++)r.text(utf8);
    int mc=r.get<int>();for(int i=0;i<mc;i++){r.text(utf8);r.text(utf8);r.skip(16+12+4+12+1+16+4);r.skip(tis+tis+1);unsigned char shared=r.get<unsigned char>();r.skip(shared?1:tis);r.text(utf8);r.skip(4);}
    int bc=r.get<int>();s.bones.resize(bc);
    for(int i=0;i<bc;i++){
        Bone&b=s.bones[i];b.name=r.text(utf8);r.text(utf8);b.position=read_v3(r);b.parent=index(r,bis);b.level=r.get<int>();b.flags=r.get<unsigned short>();
        if(b.flags&0x0001)index(r,bis);else r.skip(12);
        if(b.flags&(0x0100|0x0200)){b.append_source=index(r,bis);b.append_ratio=r.get<float>();}
        if(b.flags&0x0400)b.fixed_axis=read_v3(r);
        if(b.flags&0x0800)r.skip(24);
        if(b.flags&0x2000)r.skip(4);
        if(b.flags&0x0020){b.ik_target=index(r,bis);b.ik_loops=r.get<int>();b.ik_limit=r.get<float>();if(b.ik_limit>0.0f){int minimum=(int)(3.14f/(b.ik_limit*0.25f));if(b.ik_loops<minimum)b.ik_loops=minimum;}int lc=r.get<int>();for(int j=0;j<lc;j++){Link l;l.bone=index(r,bis);l.limited=r.get<unsigned char>()!=0;l.lo=l.hi=v3(0,0,0);if(l.limited){l.lo=read_v3(r);l.hi=read_v3(r);}b.links.push_back(l);}}
        s.bone_map[b.name]=i;
    }
    int moc=r.get<int>();s.morphs.resize(moc);
    for(int i=0;i<moc;i++){
        Morph&m=s.morphs[i];m.name=r.text(utf8);r.text(utf8);r.get<unsigned char>();m.type=r.get<unsigned char>();int n=r.get<int>();
        for(int j=0;j<n;j++){
            if(m.type==0||m.type==9){int mi=index(r,mos);float w=r.get<float>();m.group.push_back(std::make_pair(mi,w));}
            else if(m.type==1){r.skip(vis+12);}
            else if(m.type==2){BoneMorph x;x.bone=index(r,bis);x.position=read_v3(r);x.rotation=read_q(r);m.bones.push_back(x);}
            else if(m.type>=3&&m.type<=7){r.skip(vis+16);}
            else if(m.type==8){r.skip(mis+1+112);}
            else if(m.type==10){r.skip(ris+1+24);}
            else throw std::runtime_error("unknown morph type");
        }s.morph_map[m.name]=i;
    }
    int display_count=r.get<int>();
    for(int i=0;i<display_count;i++){
        r.text(utf8);r.text(utf8);r.get<unsigned char>();int element_count=r.get<int>();
        for(int j=0;j<element_count;j++){unsigned char kind=r.get<unsigned char>();index(r,kind?mos:bis);}
    }
    int rigid_count=r.get<int>();s.rigids.resize(rigid_count);
    for(int i=0;i<rigid_count;i++){
        Rigid&rigid=s.rigids[i];r.text(utf8);r.text(utf8);rigid.bone=index(r,bis);r.skip(1+2+1+12);
        rigid.position=read_v3(r);rigid.rotation=read_v3(r);r.skip(20);rigid.mode=r.get<unsigned char>();
    }
    s.order.resize(bc);for(int i=0;i<bc;i++)s.order[i]=i;std::stable_sort(s.order.begin(),s.order.end(),BoneLevelLess(&s.bones));
    s.pos.resize(bc);s.physical_pos.resize(bc,v3(0,0,0));s.rot.resize(bc);s.physical_rot.resize(bc,q4(0,0,0,1));s.ikrot.resize(bc);s.appendrot.resize(bc);s.selfrot.resize(bc,q4(0,0,0,1));s.delayedrot.resize(bc,q4(0,0,0,1));s.fixedrot.resize(bc,q4(0,0,0,1));s.ik_applied.resize(bc);s.fixedrot_valid.resize(bc,0);s.external_active.resize(bc,0);s.external_rigid_active.resize(rigid_count,0);s.physical_active.resize(bc,0);s.physical_mode.resize(bc,0);s.live_active.resize(bc,0);s.live_ik_enabled.resize(bc,1);s.appendpos.resize(bc);s.selfpos.resize(bc,v3(0,0,0));s.delayedpos.resize(bc,v3(0,0,0));s.local.resize(bc);s.world.resize(bc);s.external_world.resize(bc);s.external_rigid_world.resize(rigid_count);s.live_world.resize(bc);s.live_morph_weights.resize(moc,0.0f);
}

static Quat project_fixed_rotation(Quat q,Vec3 fixed_axis){Vec3 a=normalize(fixed_axis);float w=std::max(-1.0f,std::min(1.0f,q.w));float sign=dot(v3(q.x,q.y,q.z),a)<0.0f?-1.0f:1.0f;float sn=sqrtf(std::max(0.0f,1.0f-w*w))*sign;Quat result=q4(a.x*sn,a.y*sn,a.z*sn,w);if(result.x==0.0f)result.x=0.0f;if(result.y==0.0f)result.y=0.0f;if(result.z==0.0f)result.z=0.0f;return result;}
static void parse_vmd(Solver&s,const void*data,size_t size){
    Reader r(data,size);r.skip(30);r.skip(20);unsigned int n=r.get<unsigned int>();
    for(unsigned int i=0;i<n;i++){std::wstring name=r.sjis(15);BoneKey k;k.frame=r.get<unsigned int>();k.position=read_v3(r);k.rotation=read_q(r);std::map<std::wstring,int>::iterator bi=s.bone_map.find(name);if(bi!=s.bone_map.end()&&(s.bones[bi->second].flags&0x0400))k.rotation=project_fixed_rotation(k.rotation,s.bones[bi->second].fixed_axis);r.need(64);memcpy(k.interp,r.p,64);r.skip(64);s.bone_tracks[name].push_back(k);}
    unsigned int mn=r.get<unsigned int>();for(unsigned int i=0;i<mn;i++){std::wstring name=r.sjis(15);MorphKey k={r.get<unsigned int>(),r.get<float>()};s.morph_tracks[name].push_back(k);}
    if(r.p==r.e)return;unsigned int cn=r.get<unsigned int>();r.skip((size_t)cn*61);if(r.p==r.e)return;unsigned int ln=r.get<unsigned int>();r.skip((size_t)ln*28);if(r.p==r.e)return;unsigned int sn=r.get<unsigned int>();r.skip((size_t)sn*9);if(r.p==r.e)return;
    unsigned int pn=r.get<unsigned int>();for(unsigned int i=0;i<pn;i++){PropertyKey p;p.frame=r.get<unsigned int>();r.get<unsigned char>();unsigned int c=r.get<unsigned int>();for(unsigned int j=0;j<c;j++){std::wstring name=r.sjis(20);p.ik[name]=r.get<unsigned char>()!=0;}s.property_keys.push_back(p);}
    for(std::map<std::wstring,std::vector<BoneKey> >::iterator it=s.bone_tracks.begin();it!=s.bone_tracks.end();++it)std::stable_sort(it->second.begin(),it->second.end(),BoneKeyLess());
    for(std::map<std::wstring,std::vector<MorphKey> >::iterator it=s.morph_tracks.begin();it!=s.morph_tracks.end();++it)std::stable_sort(it->second.begin(),it->second.end(),MorphKeyLess());
}

static float bezier(float x,unsigned char x1,unsigned char y1,unsigned char x2,unsigned char y2){
    if(x1==y1&&x2==y2)return x;
    const float scale=0.02362200058996677399f;
    float step=0.5f,t=0.5f;
    for(int i=0;i<12;i++){
        float u=1.0f-t;
        volatile float first=u*u;first=first*t;first=first*(float)x1;first=first*scale;
        volatile float second=u*t;second=second*t;second=second*(float)x2;second=second*scale;
        volatile float third=t*t;third=third*t;
        volatile float curve=first+second;curve=curve+third;
        if(x==curve)break;
        step*=0.5f;
        if(x>curve)t+=step;else t-=step;
    }
    float u=1.0f-t;
    volatile float first=u*u;first=first*t;first=first*(float)y1;first=first*scale;
    volatile float second=u*t;second=second*t;second=second*(float)y2;second=second*scale;
    volatile float third=t*t;third=third*t;
    volatile float result=first+second;result=result+third;return result;
}
static void sample_bone(const std::vector<BoneKey>&ks,float frame,Vec3&pos,Quat&rot){
    if(ks.empty())return;if(frame<=ks.front().frame){pos=ks.front().position;rot=ks.front().rotation;return;}if(frame>=ks.back().frame){pos=ks.back().position;rot=ks.back().rotation;return;}
    size_t hi=1;while(hi<ks.size()&&ks[hi].frame<frame)hi++;if(ks[hi].frame==frame){pos=ks[hi].position;rot=ks[hi].rotation;return;}const BoneKey&a=ks[hi-1],&b=ks[hi];float x=(frame-a.frame)/(b.frame-a.frame);
    float tx=bezier(x,b.interp[0],b.interp[4],b.interp[8],b.interp[12]),ty=bezier(x,b.interp[16],b.interp[20],b.interp[24],b.interp[28]),tz=bezier(x,b.interp[32],b.interp[36],b.interp[40],b.interp[44]),tr=bezier(x,b.interp[48],b.interp[52],b.interp[56],b.interp[60]);
    pos=v3(a.position.x+(b.position.x-a.position.x)*tx,a.position.y+(b.position.y-a.position.y)*ty,a.position.z+(b.position.z-a.position.z)*tz);rot=qslerp(a.rotation,b.rotation,tr);
}
static float sample_morph(const std::vector<MorphKey>&ks,float frame){if(ks.empty())return 0;if(frame<=ks.front().frame)return ks.front().weight;if(frame>=ks.back().frame)return ks.back().weight;size_t hi=1;while(hi<ks.size()&&ks[hi].frame<frame)hi++;if(ks[hi].frame==frame)return ks[hi].weight;const MorphKey&a=ks[hi-1],&b=ks[hi];float t=(frame-a.frame)/(b.frame-a.frame);return a.weight+(b.weight-a.weight)*t;}

static Quat scale_self_morph_rotation(Quat q,float ratio){
    float w=std::max(-1.0f,std::min(1.0f,q.w));float angle=acosf(w);if(w<0.0f)angle-=3.1400001049041748047f;float n=sqrtf(q.x*q.x+q.y*q.y+q.z*q.z);if(angle==0.0f||n<1.0e-7f)return q4(0,0,0,1);angle*=ratio;float scale=sinf(angle)/n;return q4(q.x*scale,q.y*scale,q.z*scale,cosf(angle));
}
static void apply_morph(Solver&s,int mi,float weight,std::vector<float>&stack){
    if(mi<0||mi>=(int)s.morphs.size()||weight==0||stack[mi]!=0)return;stack[mi]=weight;Morph&m=s.morphs[mi];
    for(size_t i=0;i<m.group.size();i++)apply_morph(s,m.group[i].first,weight*m.group[i].second,stack);
    for(size_t i=0;i<m.bones.size();i++){BoneMorph&x=m.bones[i];if(x.bone<0||x.bone>=(int)s.bones.size())continue;s.pos[x.bone]=add(s.pos[x.bone],mul(x.position,weight));if(s.bones[x.bone].append_source==x.bone)s.rot[x.bone]=qmultiply_d3dx(s.rot[x.bone],scale_self_morph_rotation(x.rotation,weight));else s.rot[x.bone]=qnorm(qmul(s.rot[x.bone],qslerp_d3dx(q4(0,0,0,1),x.rotation,weight)));}stack[mi]=0;
}
static Quat scale_append_rotation(Quat q,float ratio){
    float w=std::max(-1.0f,std::min(1.0f,q.w));float angle=acosf(w);if(w<0.0f)angle-=3.1400001049041748047f;float n=sqrtf(q.x*q.x+q.y*q.y+q.z*q.z);if(angle==0.0f||n<1.0e-7f)return q4(0,0,0,1);angle*=ratio;float scale=sinf(angle)/n;return q4(q.x*scale,q.y*scale,q.z*scale,cosf(angle));
}
static Quat append_rotation(Quat q,float ratio){
    load_d3dx();Mat4 m;g_d3dx_mrotq(&m,&q);g_d3dx_qfrom_matrix(&q,&m);return scale_append_rotation(q,ratio);
}
static Quat bone_rotation(const Solver&s,int i){return s.ik_applied[i]?s.ikrot[i]:s.rot[i];}
static Quat effective_rotation(Solver&s,int i);
static void compute_append(Solver&s,int i,std::vector<unsigned char>&state){
    if(i<0||i>=(int)s.bones.size()||state[i]==2)return;if(state[i]==1)return;state[i]=1;Bone&b=s.bones[i];s.appendrot[i]=q4(0,0,0,1);s.appendpos[i]=v3(0,0,0);
    if(b.append_source>=0&&b.append_source<(int)s.bones.size()){
        if(b.append_source==i){
            if(b.flags&0x0100)s.appendrot[i]=b.append_ratio==1.0f?s.selfrot[i]:scale_append_rotation(s.selfrot[i],b.append_ratio);
            if(b.flags&0x0200)s.appendpos[i]=mul(s.selfpos[i],b.append_ratio);
            state[i]=2;return;
        }
        Bone&source=s.bones[b.append_source];bool use_source_append=!(b.flags&0x0080)&&source.append_source>=0;
        compute_append(s,b.append_source,state);
        Quat sr=effective_rotation(s,b.append_source);Vec3 sp=use_source_append?s.appendpos[b.append_source]:s.pos[b.append_source];
        if(b.flags&0x0100){if(s.ik_applied[b.append_source]){load_d3dx();g_d3dx_qfrom_matrix(&sr,&s.local[b.append_source]);s.appendrot[i]=scale_append_rotation(sr,b.append_ratio);}else s.appendrot[i]=append_rotation(sr,b.append_ratio);}if(b.flags&0x0200)s.appendpos[i]=mul(sp,b.append_ratio);
    }state[i]=2;
}
static Quat effective_rotation(Solver&s,int i){
    Bone&b=s.bones[i];Quat q=bone_rotation(s,i);Quat arot=s.appendrot[i];if(b.flags&0x0400)q=project_fixed_rotation(q,b.fixed_axis);if(arot.x!=0.0f||arot.y!=0.0f||arot.z!=0.0f||arot.w!=1.0f)q=qmultiply_d3dx(q,arot);return q;
}
static Mat4 compose_local(Solver&s,int i,const Mat4&r){
    Bone&b=s.bones[i];Mat4 a=translation(mul(b.position,-1.0f)),t=translation(add(s.pos[i],s.appendpos[i])),rest=translation(b.position);Mat4 local=mmul(a,r);local=mmul(local,t);return mmul(local,rest);
}
static void update_world_from_local(Solver&s,int i){
    Bone&b=s.bones[i];s.world[i]=b.parent>=0?mmul(s.local[i],s.world[b.parent]):s.local[i];
}
static void update_one_world(Solver&s,int i){
    Quat q=effective_rotation(s,i);Mat4 r;load_d3dx();g_d3dx_mrotq(&r,&q);s.local[i]=compose_local(s,i,r);update_world_from_local(s,i);
}
static void update_world(Solver&s){
    std::vector<unsigned char>state(s.bones.size(),0);for(size_t i=0;i<s.bones.size();i++)compute_append(s,(int)i,state);for(size_t oi=0;oi<s.order.size();oi++)update_one_world(s,s.order[oi]);
}
static bool has_external_pose(const Solver&s){for(size_t i=0;i<s.external_active.size();i++)if(s.external_active[i])return true;for(size_t i=0;i<s.external_rigid_active.size();i++)if(s.external_rigid_active[i])return true;return false;}
static void derive_external_parameters(Solver&s){
    std::vector<unsigned char>rigid_bone_active(s.bones.size(),0);
    for(size_t ri=0;ri<s.rigids.size();ri++)if(s.external_rigid_active[ri]){Rigid&r=s.rigids[ri];if(r.mode!=0&&r.bone>=0&&r.bone<(int)s.bones.size()){s.world[r.bone]=s.external_rigid_world[ri];rigid_bone_active[r.bone]=1;}}
    for(size_t i=0;i<s.bones.size();i++)if(s.external_active[i]&&!rigid_bone_active[i])s.world[i]=s.external_world[i];
    for(size_t ri=0;ri<s.rigids.size();ri++)if(s.external_rigid_active[ri]){Rigid&r=s.rigids[ri];int i=r.bone;if(r.mode==0||i<0||i>=(int)s.bones.size())continue;Bone&b=s.bones[i];Mat4 raw_local;if(b.parent>=0){Mat4 parent_inverse;load_d3dx();if(!g_d3dx_minverse(&parent_inverse,0,&s.world[b.parent])){s.external_world[i]=s.world[i];s.external_active[i]=1;s.physical_mode[i]=r.mode;continue;}raw_local=mmul(s.world[i],parent_inverse);}else raw_local=s.world[i];Quat q;load_d3dx();g_d3dx_qfrom_matrix(&q,&raw_local);Mat4 rest_times_local=mmul(translation(b.position),raw_local);Mat4 pivoted=mmul(rest_times_local,translation(v3(-b.position.x,-b.position.y,-b.position.z)));s.rot[i]=q;s.pos[i]=v3(pivoted.m[12],pivoted.m[13],pivoted.m[14]);s.appendrot[i]=q4(0,0,0,1);s.appendpos[i]=v3(0,0,0);s.ikrot[i]=q4(0,0,0,1);s.ik_applied[i]=0;s.local[i]=raw_local;if(r.mode==2){s.pos[i]=v3(0,0,0);rest_times_local.m[12]=rest_times_local.m[13]=rest_times_local.m[14]=0.0f;s.local[i]=mmul(translation(v3(-b.position.x,-b.position.y,-b.position.z)),rest_times_local);s.local[i]=mmul(s.local[i],translation(b.position));update_world_from_local(s,i);}s.external_world[i]=s.world[i];s.external_active[i]=1;s.physical_mode[i]=r.mode;}
    for(size_t oi=0;oi<s.order.size();oi++){int i=s.order[oi];if(!s.external_active[i]||rigid_bone_active[i])continue;Bone&b=s.bones[i];Mat4 local=b.parent>=0?mmul(s.world[i],minverse(s.world[b.parent])):s.world[i];Quat q;load_d3dx();g_d3dx_qfrom_matrix(&q,&local);Mat4 pivoted=mmul(translation(b.position),local);pivoted=mmul(pivoted,translation(v3(-b.position.x,-b.position.y,-b.position.z)));s.rot[i]=q;s.pos[i]=v3(pivoted.m[12],pivoted.m[13],pivoted.m[14]);s.appendrot[i]=q4(0,0,0,1);s.appendpos[i]=v3(0,0,0);s.ikrot[i]=q4(0,0,0,1);s.ik_applied[i]=0;s.local[i]=local;s.external_world[i]=s.world[i];}
}
static void update_world_with_external(Solver&s){
    std::vector<unsigned char>state(s.bones.size(),0);for(size_t i=0;i<s.bones.size();i++)compute_append(s,(int)i,state);for(size_t oi=0;oi<s.order.size();oi++){int i=s.order[oi];if(s.external_active[i]){Bone&b=s.bones[i];s.local[i]=b.parent>=0?mmul(s.external_world[i],minverse(s.world[b.parent])):s.external_world[i];s.world[i]=s.external_world[i];}else update_one_world(s,i);}
}
static Mat4 compose_base_local(Solver&s,int i){Bone&b=s.bones[i];Quat q=bone_rotation(s,i);if(b.flags&0x0400)q=project_fixed_rotation(q,b.fixed_axis);Mat4 r;load_d3dx();g_d3dx_mrotq(&r,&q);Mat4 a=translation(mul(b.position,-1.0f)),t=translation(s.pos[i]),rest=translation(b.position);Mat4 local=mmul(a,r);local=mmul(local,t);return mmul(local,rest);}
static void update_ik_chain(Solver&s,const Bone&ik,size_t link_index){
    update_world_from_local(s,ik.links[link_index].bone);for(int i=(int)link_index-1;i>=0;i--)if(ik.links[(size_t)i].bone>=0)update_world_from_local(s,ik.links[(size_t)i].bone);Mat4 target_local=compose_base_local(s,ik.ik_target);int parent=s.bones[ik.ik_target].parent;s.world[ik.ik_target]=parent>=0?mmul(target_local,s.world[parent]):target_local;
}
static bool ik_enabled(const Solver&s,int bone_index,float frame){if(s.live_mode)return s.live_ik_enabled[bone_index]!=0;const Bone&b=s.bones[bone_index];bool enabled=true;for(size_t i=0;i<s.property_keys.size()&&s.property_keys[i].frame<=frame;i++){std::map<std::wstring,bool>::const_iterator it=s.property_keys[i].ik.find(b.name);if(it!=s.property_keys[i].ik.end())enabled=it->second;}return enabled;}
static void refresh_append_world(Solver&s){std::vector<unsigned char>state(s.bones.size(),0);for(size_t i=0;i<s.bones.size();i++)compute_append(s,(int)i,state);for(size_t oi=0;oi<s.order.size();oi++){int i=s.order[oi];if(s.external_active[i]){Bone&b=s.bones[i];s.local[i]=b.parent>=0?mmul(s.external_world[i],minverse(s.world[b.parent])):s.external_world[i];s.world[i]=s.external_world[i];}else if(s.ik_applied[i])update_world_from_local(s,i);else update_one_world(s,i);}}
static void refresh_world_only(Solver&s){for(size_t oi=0;oi<s.order.size();oi++){int i=s.order[oi];if(s.external_active[i]){Bone&b=s.bones[i];s.local[i]=b.parent>=0?mmul(s.external_world[i],minverse(s.world[b.parent])):s.external_world[i];s.world[i]=s.external_world[i];}else if(s.ik_applied[i])update_world_from_local(s,i);else update_one_world(s,i);}}
static bool append_source_affected_by_ik(const Solver&s,int source,const Bone&ik){
    for(size_t depth=0;depth<s.bones.size()&&source>=0&&source<(int)s.bones.size();depth++){
        if(source==ik.ik_target)return true;for(size_t li=0;li<ik.links.size();li++)if(source==ik.links[li].bone)return true;
        int next=s.bones[source].append_source;if(next<0||next==source)break;source=next;
    }
    return false;
}
static void solve_ik(Solver&s,float frame){
    std::vector<unsigned char>frozen(s.bones.size(),0);std::vector<Quat>frozen_rot(s.bones.size());std::vector<Vec3>frozen_pos(s.bones.size());
    int current_level=-2147483647;for(size_t oi=0;oi<s.order.size();oi++){int ii=s.order[oi];Bone&ik=s.bones[ii];if(!(ik.flags&0x20)||!ik_enabled(s,ii,frame)||ik.ik_target<0)continue;if(current_level==-2147483647||ik.level!=current_level){if(current_level!=-2147483647)refresh_append_world(s);current_level=ik.level;}for(size_t before=0;before<oi;before++){int bi=s.order[before];Bone&prior=s.bones[bi];if(!frozen[bi]&&prior.level==current_level&&prior.append_source>=0&&prior.append_source!=bi&&append_source_affected_by_ik(s,prior.append_source,ik)){frozen[bi]=1;frozen_rot[bi]=s.delayedrot[bi];frozen_pos[bi]=s.delayedpos[bi];}}
        std::vector<float>plane(ik.links.size(),0.0f);std::vector<Vec3>previous(ik.links.size(),v3(0,0,0));for(size_t li=0;li<ik.links.size();li++)if(ik.links[li].bone>=0)previous[li]=q_to_yxz(s.rot[ik.links[li].bone]);
        bool converged=false;for(int loop=0;loop<ik.ik_loops&&!converged;loop++)for(size_t li=0;li<ik.links.size();li++){Link&link=ik.links[li];if(link.bone<0||link.bone==ik.ik_target)continue;Vec3 lp=transform_point(s.bones[link.bone].position,s.world[link.bone]);Vec3 target_point=transform_point(s.bones[ik.ik_target].position,s.world[ik.ik_target]);Vec3 goal_point=transform_point(ik.position,s.world[ii]);Vec3 ep=sub(target_point,lp);Vec3 gp=sub(goal_point,lp);if(dot(ep,ep)<1e-12f||dot(gp,gp)<1e-12f)continue;Vec3 a=normalize(ep),b=normalize(gp);Vec3 vector_delta=sub(a,b);if(dot(vector_delta,vector_delta)<1e-7f){converged=true;break;}float c=std::max(-1.0f,std::min(1.0f,dot(a,b)));float angle=acosf(c);if(angle<1e-7f)continue;angle=std::min(angle,(float)(li+1)*ik.ik_limit);if(angle<1e-7f)continue;
            bool only_x=link.limited&&(link.lo.x!=0||link.hi.x!=0)&&link.lo.y==0&&link.hi.y==0&&link.lo.z==0&&link.hi.z==0;
            Vec3 axis=cross(a,b);if(s.bones[link.bone].parent>=0){const Mat4&p=s.world[s.bones[link.bone].parent];if(link.limited&&loop<ik.ik_loops/2&&only_x){float x=ordered_sum3(axis.y*p.m[1],axis.x*p.m[0],axis.z*p.m[2]);axis=v3(x<0.0f?-1.0f:1.0f,0,0);}else{axis=v3(ordered_sum3(axis.y*p.m[1],axis.x*p.m[0],axis.z*p.m[2]),ordered_sum3(axis.y*p.m[5],axis.x*p.m[4],axis.z*p.m[6]),ordered_sum3(axis.y*p.m[9],axis.x*p.m[8],axis.z*p.m[10]));axis=normalize(axis);}}else axis=normalize(axis);if(length(axis)<1e-7f)continue;Quat dq=qaxis(axis,angle);Quat combined=qmultiply_d3dx(s.ikrot[link.bone],dq);if(loop==0){Quat base=s.bones[link.bone].append_source==link.bone?effective_rotation(s,link.bone):s.rot[link.bone];combined=qmultiply_d3dx(base,combined);}Mat4 rotation_matrix;if(link.limited){bool broad_x=link.lo.x<=-1.5707963267948966f||link.hi.x>=1.5707963267948966f;Vec3 e=broad_x?q_to_xyz(combined):q_to_zxy(combined);bool clamp_only=loop>=ik.ik_loops/2;e.x=constrain_ik_angle(e.x,link.lo.x,link.hi.x,clamp_only);e.y=constrain_ik_angle(e.y,link.lo.y,link.hi.y,clamp_only);e.z=constrain_ik_angle(e.z,link.lo.z,link.hi.z,clamp_only);previous[li]=e;combined=broad_x?q_from_xyz(e,&rotation_matrix):q_from_zxy(e,&rotation_matrix);}else{load_d3dx();g_d3dx_mrotq(&rotation_matrix,&combined);}s.ikrot[link.bone]=combined;s.ik_applied[link.bone]=1;s.local[link.bone]=compose_local(s,link.bone,rotation_matrix);update_ik_chain(s,ik,li);}
    }
    refresh_append_world(s);for(size_t i=0;i<s.bones.size();i++)if(frozen[i]){s.delayedrot[i]=s.appendrot[i];s.delayedpos[i]=s.appendpos[i];s.appendrot[i]=frozen_rot[i];s.appendpos[i]=frozen_pos[i];}refresh_world_only(s);
}
static void write_output(Solver&s,float*out){
    for(size_t i=0;i<s.bones.size();i++){Mat4 exported=s.world[i];Vec3 p=transform_point(s.bones[i].position,s.world[i]);exported.m[12]=p.x;exported.m[13]=p.y;exported.m[14]=p.z;memcpy(out+i*16,exported.m,64);}
}
static void evaluate(Solver&s,float frame,float*out,int forced_passes);
static void evaluate_after_physics(Solver&s,float*out){
    bool had_physical=false;for(size_t i=0;i<s.physical_active.size();i++)if(s.physical_active[i]){had_physical=true;break;}
    derive_external_parameters(s);
    for(size_t i=0;i<s.bones.size();i++)if(s.external_active[i]){s.physical_pos[i]=s.pos[i];s.physical_rot[i]=s.rot[i];s.physical_active[i]=1;}
    std::fill(s.external_active.begin(),s.external_active.end(),0);std::fill(s.external_rigid_active.begin(),s.external_rigid_active.end(),0);
    if(had_physical)write_output(s,out);else evaluate(s,s.last_frame,out,4);
}
static void apply_live_inputs(Solver&s){
    for(size_t oi=0;oi<s.order.size();oi++){
        int i=s.order[oi];if(!s.live_active[i])continue;Bone&b=s.bones[i];Mat4 local=s.live_world[i];
        if(b.parent>=0&&s.live_active[b.parent])local=mmul(local,minverse(s.live_world[b.parent]));
        Quat q;load_d3dx();g_d3dx_qfrom_matrix(&q,&local);Mat4 pivoted=mmul(translation(b.position),local);pivoted=mmul(pivoted,translation(v3(-b.position.x,-b.position.y,-b.position.z)));s.rot[i]=q;s.pos[i]=v3(pivoted.m[12],pivoted.m[13],pivoted.m[14]);
    }
}
static void evaluate(Solver&s,float frame,float*out,int forced_passes=0){
    bool continuing=s.has_evaluated&&frame==s.last_frame+1.0f;std::vector<Quat>prior=s.ikrot;
    size_t n=s.bones.size();for(size_t i=0;i<n;i++){s.pos[i]=v3(0,0,0);s.rot[i]=q4(0,0,0,1);s.ikrot[i]=continuing&&s.bones[i].level>0?prior[i]:q4(0,0,0,1);s.ik_applied[i]=0;}
    for(std::map<std::wstring,std::vector<BoneKey> >::iterator it=s.bone_tracks.begin();it!=s.bone_tracks.end();++it){std::map<std::wstring,int>::iterator bi=s.bone_map.find(it->first);if(bi!=s.bone_map.end())sample_bone(it->second,frame,s.pos[bi->second],s.rot[bi->second]);}
    if(s.live_mode)apply_live_inputs(s);
    std::vector<float>stack(s.morphs.size(),0);if(s.live_mode){for(size_t i=0;i<s.live_morph_weights.size();i++)apply_morph(s,(int)i,s.live_morph_weights[i],stack);}else for(std::map<std::wstring,std::vector<MorphKey> >::iterator it=s.morph_tracks.begin();it!=s.morph_tracks.end();++it){std::map<std::wstring,int>::iterator mi=s.morph_map.find(it->first);if(mi!=s.morph_map.end())apply_morph(s,mi->second,sample_morph(it->second,frame),stack);}
    for(size_t i=0;i<n;i++)if(s.physical_active[i]){if(s.physical_mode[i]==1)s.pos[i]=s.physical_pos[i];s.rot[i]=s.physical_rot[i];}
    bool external=has_external_pose(s);int passes=forced_passes?forced_passes:(continuing?1:4);for(int pass=0;pass<passes;pass++){if(pass>0){std::vector<Quat>seed=s.ikrot;for(size_t j=0;j<n;j++){s.ikrot[j]=s.bones[j].level>0?seed[j]:q4(0,0,0,1);s.ik_applied[j]=0;}}update_world(s);if(external){derive_external_parameters(s);update_world_with_external(s);}solve_ik(s,frame);}for(size_t i=0;i<n;i++)if(s.bones[i].append_source==(int)i){Quat result=s.ik_applied[i]?s.ikrot[i]:effective_rotation(s,(int)i);s.selfrot[i]=result;s.selfpos[i]=add(s.pos[i],s.appendpos[i]);}if(external){for(size_t i=0;i<n;i++)if(s.external_active[i]){s.physical_pos[i]=s.pos[i];s.physical_rot[i]=s.rot[i];s.physical_active[i]=1;}std::fill(s.external_active.begin(),s.external_active.end(),0);}s.has_evaluated=true;s.last_frame=frame;write_output(s,out);
}

SPX_API unsigned int spx_mmd_bone_abi_version(){return 2;}
SPX_API void* spx_mmd_bone_create(const void*pmx,size_t pmx_size,const void*vmd,size_t vmd_size){try{Solver*s=new Solver();parse_pmx(*s,pmx,pmx_size);if(vmd&&vmd_size)parse_vmd(*s,vmd,vmd_size);g_error.clear();return s;}catch(const std::exception&e){g_error=e.what();return 0;}catch(...){g_error="unknown error";return 0;}}
SPX_API void spx_mmd_bone_destroy(void*p){delete (Solver*)p;}
SPX_API unsigned int spx_mmd_bone_count(void*p){return p?(unsigned int)((Solver*)p)->bones.size():0;}
SPX_API unsigned int spx_mmd_bone_rigid_count(void*p){return p?(unsigned int)((Solver*)p)->rigids.size():0;}
SPX_API int spx_mmd_bone_rigid_position(void*p,unsigned int i,float*out,size_t count){if(!p||!out||count<3||i>=((Solver*)p)->rigids.size())return 0;const Vec3&v=((Solver*)p)->rigids[i].position;out[0]=v.x;out[1]=v.y;out[2]=v.z;return 1;}
SPX_API int spx_mmd_bone_rest_position(void*p,unsigned int i,float*out,size_t count){if(!p||!out||count<3||i>=((Solver*)p)->bones.size())return 0;const Vec3&v=((Solver*)p)->bones[i].position;out[0]=v.x;out[1]=v.y;out[2]=v.z;return 1;}
static void write_bone_transform(Solver&s,unsigned int i,float*out){const Mat4&world=s.world[i];Vec3 head=transform_point(s.bones[i].position,world);Quat rotation;load_d3dx();g_d3dx_qfrom_matrix(&rotation,&world);out[0]=head.x;out[1]=head.y;out[2]=head.z;out[3]=rotation.x;out[4]=rotation.y;out[5]=rotation.z;out[6]=rotation.w;}
SPX_API int spx_mmd_bone_transform(void*p,unsigned int i,float*out,size_t count){if(!p||!out||count<7||i>=((Solver*)p)->bones.size())return 0;write_bone_transform(*(Solver*)p,i,out);return 1;}
SPX_API int spx_mmd_bone_transforms(void*p,const unsigned int*indices,float*out,size_t count){if(!p)return 0;if(!count)return 1;if(!indices||!out)return 0;Solver&s=*(Solver*)p;for(size_t item=0;item<count;item++)if(indices[item]>=s.bones.size())return 0;try{std::vector<float>values(count*7);for(size_t item=0;item<count;item++)write_bone_transform(s,indices[item],&values[item*7]);memcpy(out,&values[0],values.size()*sizeof(float));g_error.clear();return 1;}catch(const std::exception&e){g_error=e.what();return 0;}catch(...){g_error="unknown error";return 0;}}
static void write_rigid_target(Solver&s,unsigned int rigid_index,float*out){Rigid&rigid=s.rigids[rigid_index];Mat4 body=rigid_rest_matrix(rigid.position,rigid.rotation);if(rigid.bone>=0&&rigid.bone<(int)s.bones.size())body=mmul(body,s.world[rigid.bone]);Quat rotation;load_d3dx();g_d3dx_qfrom_matrix(&rotation,&body);out[0]=body.m[12];out[1]=body.m[13];out[2]=body.m[14];out[3]=rotation.x;out[4]=rotation.y;out[5]=rotation.z;out[6]=rotation.w;}
SPX_API int spx_mmd_bone_rigid_target(void*p,unsigned int rigid_index,float*out,size_t count){if(!p||!out||count<7||rigid_index>=((Solver*)p)->rigids.size())return 0;write_rigid_target(*(Solver*)p,rigid_index,out);return 1;}
SPX_API int spx_mmd_bone_rigid_targets(void*p,const unsigned int*indices,float*out,size_t count){if(!p)return 0;if(!count)return 1;if(!indices||!out)return 0;Solver&s=*(Solver*)p;for(size_t item=0;item<count;item++)if(indices[item]>=s.rigids.size())return 0;try{std::vector<float>values(count*7);for(size_t item=0;item<count;item++)write_rigid_target(s,indices[item],&values[item*7]);memcpy(out,&values[0],values.size()*sizeof(float));g_error.clear();return 1;}catch(const std::exception&e){g_error=e.what();return 0;}catch(...){g_error="unknown error";return 0;}}
SPX_API int spx_mmd_bone_rigid_matrix(void*p,unsigned int rigid_index,float*out,size_t count){if(!p||!out||count<12||rigid_index>=((Solver*)p)->rigids.size())return 0;Solver&s=*(Solver*)p;Rigid&rigid=s.rigids[rigid_index];Mat4 body=rigid_rest_matrix(rigid.position,rigid.rotation);if(rigid.bone>=0&&rigid.bone<(int)s.bones.size())body=mmul(body,s.world[rigid.bone]);out[0]=body.m[12];out[1]=body.m[13];out[2]=body.m[14];out[3]=body.m[0];out[4]=body.m[4];out[5]=body.m[8];out[6]=body.m[1];out[7]=body.m[5];out[8]=body.m[9];out[9]=body.m[2];out[10]=body.m[6];out[11]=body.m[10];return 1;}
SPX_API void spx_mmd_bone_begin_live_input(void*p){if(!p)return;Solver&s=*(Solver*)p;s.live_mode=true;std::fill(s.live_active.begin(),s.live_active.end(),0);std::fill(s.live_morph_weights.begin(),s.live_morph_weights.end(),0.0f);}
SPX_API void spx_mmd_bone_end_live_input(void*p){if(!p)return;Solver&s=*(Solver*)p;s.live_mode=false;std::fill(s.live_active.begin(),s.live_active.end(),0);}
static void set_live_matrix(Solver&s,unsigned int i,const float*position,const float*basis){Mat4 world=identity();world.m[0]=basis[0];world.m[1]=basis[1];world.m[2]=basis[2];world.m[4]=basis[3];world.m[5]=basis[4];world.m[6]=basis[5];world.m[8]=basis[6];world.m[9]=basis[7];world.m[10]=basis[8];Vec3 head=v3(position[0],position[1],position[2]);Vec3 rotated=transform_point(s.bones[i].position,world);world.m[12]=head.x-rotated.x;world.m[13]=head.y-rotated.y;world.m[14]=head.z-rotated.z;s.live_world[i]=world;s.live_active[i]=1;}
SPX_API int spx_mmd_bone_set_live_matrix(void*p,unsigned int i,const float*position,const float*basis,size_t count){if(!p||!position||!basis||count<9||i>=((Solver*)p)->bones.size())return 0;set_live_matrix(*(Solver*)p,i,position,basis);return 1;}
SPX_API int spx_mmd_bone_set_live_matrices(void*p,const unsigned int*indices,const float*positions,const float*bases,size_t count){if(!p)return 0;if(!count)return 1;if(!indices||!positions||!bases)return 0;Solver&s=*(Solver*)p;for(size_t item=0;item<count;item++)if(indices[item]>=s.bones.size())return 0;for(size_t item=0;item<count;item++)set_live_matrix(s,indices[item],positions+item*3,bases+item*9);return 1;}
SPX_API int spx_mmd_bone_set_live_ik_enabled(void*p,unsigned int i,int enabled){if(!p||i>=((Solver*)p)->bones.size())return 0;Solver&s=*(Solver*)p;s.live_mode=true;s.live_ik_enabled[i]=enabled?1:0;return 1;}
SPX_API unsigned int spx_mmd_bone_morph_count(void*p){return p?(unsigned int)((Solver*)p)->morphs.size():0;}
SPX_API int spx_mmd_bone_morph_name_utf8(void*p,unsigned int i,char*out,size_t cap){if(!p||i>=((Solver*)p)->morphs.size())return 0;const std::wstring&w=((Solver*)p)->morphs[i].name;int n=WideCharToMultiByte(CP_UTF8,0,w.c_str(),(int)w.size(),0,0,0,0);if(out&&cap>(size_t)n){WideCharToMultiByte(CP_UTF8,0,w.c_str(),(int)w.size(),out,n,0,0);out[n]=0;}return n;}
SPX_API int spx_mmd_bone_set_live_morph_weight(void*p,unsigned int i,float weight){if(!p||i>=((Solver*)p)->morphs.size())return 0;Solver&s=*(Solver*)p;s.live_mode=true;s.live_morph_weights[i]=weight;return 1;}
SPX_API int spx_mmd_bone_set_external_transform(void*p,unsigned int i,const float*position,const float*rotation,size_t count){if(!p||!position||!rotation||count<4||i>=((Solver*)p)->bones.size())return 0;Solver&s=*(Solver*)p;Quat q=q4(rotation[0],rotation[1],rotation[2],rotation[3]);Mat4 world;load_d3dx();g_d3dx_mrotq(&world,&q);Vec3 head=v3(position[0],position[1],position[2]);Vec3 rotated=transform_point(s.bones[i].position,world);world.m[12]=head.x-rotated.x;world.m[13]=head.y-rotated.y;world.m[14]=head.z-rotated.z;s.external_world[i]=world;s.external_active[i]=1;return 1;}
SPX_API int spx_mmd_bone_set_external_physical_transform(void*p,unsigned int i,unsigned int mode,const float*position,const float*rotation,size_t count){int result=spx_mmd_bone_set_external_transform(p,i,position,rotation,count);if(result)((Solver*)p)->physical_mode[i]=(unsigned char)mode;return result;}
SPX_API int spx_mmd_bone_set_external_physical_pose(void*p,unsigned int i,unsigned int mode,const float*initial,const float*current,size_t count){if(!p||!initial||!current||count<7)return 0;Quat initial_rotation=q4(initial[3],initial[4],initial[5],initial[6]);Quat current_rotation=q4(current[3],current[4],current[5],current[6]);Quat relative=qmultiply_d3dx(qinverse(initial_rotation),current_rotation);float rotation[4]={relative.x,relative.y,relative.z,relative.w};return spx_mmd_bone_set_external_physical_transform(p,i,mode,current,rotation,4);}
SPX_API int spx_mmd_bone_set_external_physical_matrix(void*p,unsigned int i,unsigned int mode,const float*initial,const float*current,size_t count){if(!p||!initial||!current||count<7||i>=((Solver*)p)->bones.size())return 0;Solver&s=*(Solver*)p;load_d3dx();Quat iq=q4(initial[3],initial[4],initial[5],initial[6]),cq=q4(current[3],current[4],current[5],current[6]);Mat4 im,cm;g_d3dx_mrotq(&im,&iq);g_d3dx_mrotq(&cm,&cq);im.m[12]=initial[0];im.m[13]=initial[1];im.m[14]=initial[2];cm.m[12]=current[0];cm.m[13]=current[1];cm.m[14]=current[2];Mat4 deform=mmul(minverse(im),cm);if(mode==2){Vec3 head=transform_point(s.bones[i].position,s.world[i]),rotated=transform_point(s.bones[i].position,deform);deform.m[12]+=head.x-rotated.x;deform.m[13]+=head.y-rotated.y;deform.m[14]+=head.z-rotated.z;}s.external_world[i]=deform;s.external_active[i]=1;s.physical_mode[i]=(unsigned char)mode;return 1;}
SPX_API int spx_mmd_bone_set_external_rigid_transform(void*p,unsigned int rigid_index,const float*position,const float*rotation,size_t count){
    if(!p||!position||!rotation||count<4||rigid_index>=((Solver*)p)->rigids.size())return 0;
    Solver&s=*(Solver*)p;Rigid&rigid=s.rigids[rigid_index];if(rigid.mode==0||rigid.bone<0||rigid.bone>=(int)s.bones.size())return 1;
    Mat4 body_rest=rigid_rest_matrix(rigid.position,rigid.rotation);
    load_d3dx();Quat q=q4(rotation[0],rotation[1],rotation[2],rotation[3]),rest_q;g_d3dx_qfrom_matrix(&rest_q,&body_rest);
    Quat relative=qmultiply_d3dx(qinverse(rest_q),q);Mat4 bone_deform;g_d3dx_mrotq(&bone_deform,&relative);Vec3 body_position=v3(position[0],position[1],position[2]);Vec3 rotated_rest=transform_point(rigid.position,bone_deform);bone_deform.m[12]=body_position.x-rotated_rest.x;bone_deform.m[13]=body_position.y-rotated_rest.y;bone_deform.m[14]=body_position.z-rotated_rest.z;
    s.external_rigid_world[rigid_index]=bone_deform;s.external_rigid_active[rigid_index]=1;return 1;
}
static bool build_external_rigid_matrix(Solver&s,unsigned int rigid_index,const float*position,const float*basis,bool mmd_semantics,Mat4&bone_deform){
    Rigid&rigid=s.rigids[rigid_index];if(rigid.mode==0||rigid.bone<0||rigid.bone>=(int)s.bones.size())return false;
    Vec3 rest_position=mmd_semantics?mmd_rigid_position(s,rigid):rigid.position;Mat4 body_inverse=rigid_rest_inverse(rest_position,rigid.rotation),body_world=identity();
    body_world.m[0]=basis[0];body_world.m[1]=basis[3];body_world.m[2]=basis[6];
    body_world.m[4]=basis[1];body_world.m[5]=basis[4];body_world.m[6]=basis[7];
    body_world.m[8]=basis[2];body_world.m[9]=basis[5];body_world.m[10]=basis[8];
    body_world.m[12]=position[0];body_world.m[13]=position[1];body_world.m[14]=position[2];
    bone_deform=mmul(body_inverse,body_world);return true;
}
static int set_external_rigid_matrix(void*p,unsigned int rigid_index,const float*position,const float*basis,size_t count,bool mmd_semantics){
    if(!p||!position||!basis||count<9||rigid_index>=((Solver*)p)->rigids.size())return 0;
    Solver&s=*(Solver*)p;Mat4 bone_deform;if(!build_external_rigid_matrix(s,rigid_index,position,basis,mmd_semantics,bone_deform))return 1;
    s.external_rigid_world[rigid_index]=bone_deform;s.external_rigid_active[rigid_index]=1;return 1;
}
SPX_API int spx_mmd_bone_set_external_rigid_matrix(void*p,unsigned int rigid_index,const float*position,const float*basis,size_t count){return set_external_rigid_matrix(p,rigid_index,position,basis,count,false);}
SPX_API int spx_mmd_bone_set_external_rigid_matrix_mmd(void*p,unsigned int rigid_index,const float*position,const float*basis,size_t count){return set_external_rigid_matrix(p,rigid_index,position,basis,count,true);}
SPX_API int spx_mmd_bone_set_external_rigid_matrices_mmd(void*p,const unsigned int*indices,const float*positions,const float*bases,size_t count){if(!p)return 0;if(!count)return 1;if(!indices||!positions||!bases)return 0;Solver&s=*(Solver*)p;for(size_t item=0;item<count;item++)if(indices[item]>=s.rigids.size())return 0;try{std::vector<Mat4>matrices(count);std::vector<unsigned char>active(count,0);for(size_t item=0;item<count;item++)if(build_external_rigid_matrix(s,indices[item],positions+item*3,bases+item*9,true,matrices[item]))active[item]=1;for(size_t item=0;item<count;item++)if(active[item]){s.external_rigid_world[indices[item]]=matrices[item];s.external_rigid_active[indices[item]]=1;}g_error.clear();return 1;}catch(const std::exception&e){g_error=e.what();return 0;}catch(...){g_error="unknown error";return 0;}}
SPX_API void spx_mmd_bone_clear_external_transforms(void*p){if(!p)return;Solver&s=*(Solver*)p;std::fill(s.external_active.begin(),s.external_active.end(),0);std::fill(s.external_rigid_active.begin(),s.external_rigid_active.end(),0);std::fill(s.physical_active.begin(),s.physical_active.end(),0);}
SPX_API int spx_mmd_bone_commit_external(void*p){if(!p)return 0;Solver&s=*(Solver*)p;derive_external_parameters(s);for(size_t i=0;i<s.bones.size();i++)if(s.external_active[i]){s.physical_pos[i]=s.pos[i];s.physical_rot[i]=s.rot[i];s.physical_active[i]=1;}std::fill(s.external_active.begin(),s.external_active.end(),0);std::fill(s.external_rigid_active.begin(),s.external_rigid_active.end(),0);return 1;}
SPX_API int spx_mmd_bone_evaluate_after_physics(void*p,float*out,size_t floats){try{if(!p||!out||floats<((Solver*)p)->bones.size()*16)throw std::runtime_error("invalid output buffer");evaluate_after_physics(*(Solver*)p,out);g_error.clear();return 1;}catch(const std::exception&e){g_error=e.what();return 0;}}
SPX_API int spx_mmd_bone_evaluate_before_physics(void*p,float frame,float*out,size_t floats){try{if(!p||!out||floats<((Solver*)p)->bones.size()*16)throw std::runtime_error("invalid output buffer");evaluate(*(Solver*)p,frame,out,2);g_error.clear();return 1;}catch(const std::exception&e){g_error=e.what();return 0;}}
SPX_API int spx_mmd_bone_evaluate(void*p,float frame,float*out,size_t floats){try{if(!p||!out||floats<((Solver*)p)->bones.size()*16)throw std::runtime_error("invalid output buffer");evaluate(*(Solver*)p,frame,out);g_error.clear();return 1;}catch(const std::exception&e){g_error=e.what();return 0;}}
SPX_API int spx_mmd_bone_name_utf8(void*p,unsigned int i,char*out,size_t cap){if(!p||i>=((Solver*)p)->bones.size())return 0;const std::wstring&w=((Solver*)p)->bones[i].name;int n=WideCharToMultiByte(CP_UTF8,0,w.c_str(),(int)w.size(),0,0,0,0);if(out&&cap>(size_t)n){WideCharToMultiByte(CP_UTF8,0,w.c_str(),(int)w.size(),out,n,0,0);out[n]=0;}return n;}
SPX_API const char* spx_mmd_bone_last_error(){return g_error.c_str();}
