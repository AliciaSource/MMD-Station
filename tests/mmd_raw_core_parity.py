import json,os,struct,sys,tempfile
from pathlib import Path
import bpy
repo=Path(r'D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator');ext=Path(r'C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org')
sys.path[:0]=[str(ext),str(repo)]
import mmd_tools;mmd_tools.register()
import mmd_skirt_proxy_creator;mmd_skirt_proxy_creator.register()
from mmd_skirt_proxy_creator.physics_preview import runtime

def records(path):
 d=Path(path).read_bytes();o=0;out=[]
 while o<len(d):
  h=struct.unpack_from('<8I',d,o);o+=32
  assert h[0]==0x5442524d and h[1]==2
  bodies=[]
  for _ in range(h[4]):
   vals=struct.unpack_from('<48f2i',d,o);o+=200;bodies.append(vals)
  out.append({'call':h[2],'phase':h[3],'count':h[4],'dt':struct.unpack('<f',struct.pack('<I',h[5]))[0],'max':h[6],'fixed':struct.unpack('<f',struct.pack('<I',h[7]))[0],'bodies':bodies})
 return out

def raw_basis(solver):
 out=[]
 for t in solver.basis_transforms():out.append(tuple(float(t.basis_row_major[j]) for j in range(9))+(float(t.position.x),float(t.position.y),float(t.position.z)))
 return out

def bits(v):return struct.pack('<12f',*v)
def find_vtable_rva(path,class_name):
 d=Path(path).read_bytes();pe=struct.unpack_from('<I',d,0x3c)[0];coff=pe+4
 section_count=struct.unpack_from('<H',d,coff+2)[0];optional_size=struct.unpack_from('<H',d,coff+16)[0];optional=coff+20
 image_base=struct.unpack_from('<Q',d,optional+24)[0];sections=[];section_table=optional+optional_size
 for index in range(section_count):
  offset=section_table+index*40;virtual_size,virtual_address,raw_size,raw_offset=struct.unpack_from('<4I',d,offset+8)
  sections.append((raw_offset,raw_offset+raw_size,virtual_address,max(virtual_size,raw_size)))
 def file_to_rva(offset):
  for raw_start,raw_end,virtual_address,_ in sections:
   if raw_start<=offset<raw_end:return virtual_address+offset-raw_start
  raise ValueError(f'file offset {offset:#x} is outside PE sections')
 type_name=(f'.?AV{class_name}@@\0').encode('ascii');name_offset=d.index(type_name);type_descriptor_rva=file_to_rva(name_offset-16)
 needle=struct.pack('<I',type_descriptor_rva);search=0
 while True:
  reference=d.find(needle,search)
  if reference<0:break
  search=reference+1;col_offset=reference-12
  if col_offset<0:continue
  try:col_rva=file_to_rva(col_offset)
  except ValueError:continue
  signature,self_rva=struct.unpack_from('<I16xI',d,col_offset)
  if signature!=1 or self_rva!=col_rva:continue
  locator_pointer=struct.pack('<Q',image_base+col_rva);vtable_locator=d.find(locator_pointer)
  if vtable_locator>=0:return file_to_rva(vtable_locator+8)
 raise ValueError(f'RTTI vtable not found for {class_name}')
evidence=repo/'_archive'/'headless-validation-runs'/'mmd-raw-core-parity-20260818'
oracle_trace=os.environ.get('SPX_MMD_ORACLE_TRACE',str(evidence/'rossi_mmd_raw_trace_constraints.bin'))
trace=records(oracle_trace)
pairs={}
for r in trace:pairs.setdefault(r['call'],{})[r['phase']]=r
import ctypes
from mmd_skirt_proxy_creator.physics_preview.ffi import default_library
plugin_trace=str(Path(tempfile.gettempdir())/'spx_mmd_raw_core_parity.bin')
try: Path(plugin_trace).unlink()
except FileNotFoundError: pass
os.environ['MMD_RAW_TRACE']=plugin_trace
library=default_library('MMD')
hook_path=os.environ.get('SPX_MMD_RAW_HOOK',str(repo/'tests'/'tools'/'bin'/'mmd_raw_trace_hook_generic.dll'))
hook=ctypes.WinDLL(hook_path)
hook.install_for_module.argtypes=(ctypes.c_wchar_p,ctypes.c_ulonglong)
hook.install_for_module.restype=ctypes.c_int
dll_path=repo/'mmd_skirt_proxy_creator'/'physics_preview'/'bin'/'win_amd64'/'mmd_physics_solver_mmd.dll'
vtable_rva=find_vtable_rva(dll_path,'btDiscreteDynamicsWorld')
print('MMD_RAW_CORE_VTABLE',hex(vtable_rva))
assert hook.install_for_module('mmd_physics_solver_mmd.dll',vtable_rva)==1
bpy.ops.mmd_tools.import_model(filepath=r'D:\MMD\MEGA\_Alicia模型\Endfield-Rossi\Endfield-RossiVer1.0_by_Alicia\Rossi Ver1.0.pmx',types={'ARMATURE','PHYSICS'},scale=.08,clean_model=False,remove_doubles=False,fix_bone_order=False,rename_bones=False)
root=next(o for o in bpy.context.scene.objects if getattr(o,'mmd_type','')=='ROOT');root['import_folder']=str(Path(r'D:\MMD\MEGA\_Alicia模型\Endfield-Rossi\Endfield-RossiVer1.0_by_Alicia').resolve())
s=bpy.context.scene.surface_proxy_creator;s.preview_solver_target='MMD';s.preview_scope='MODEL';s.preview_gravity=(0,0,-9.8);s.preview_substeps=10;s.preview_frequency=60
for x in bpy.context.scene.objects:
 if getattr(x,'mmd_type','')=='ROOT':x.spx_physics_preview_selected=x==root
p=runtime.start_preview(bpy.context)[0];solver=p.world.solver
summary=[]
for call in sorted(pairs):
 pre=pairs[call].get(0);post=pairs[call].get(1)
 if not pre or not post or pre['count']!=340 or pre['dt']<=0:continue
 actual_pre=raw_basis(solver);expected_pre=[b[0:12] for b in pre['bodies'][1:]]
 pre_exact=sum(bits(a)==bits(e) for a,e in zip(actual_pre,expected_pre))
 for i,desc in enumerate(p.body_descs):
  if int(desc.mode)!=0:continue
  motion=pre['bodies'][i+1][24:36]
  solver.set_body_target_basis(i,motion[9:12],motion[0:9])
 solver.step(pre['dt'],pre['max'])
 actual=raw_basis(solver);expected=[b[0:12] for b in post['bodies'][1:]]
 exact=sum(bits(a)==bits(e) for a,e in zip(actual,expected));exact_f=0;first=None;maxerr=0
 for i,(a,e) in enumerate(zip(actual,expected)):
  for j,(x,y) in enumerate(zip(a,e)):
   xb=struct.pack('<f',x);yb=struct.pack('<f',y);exact_f+=xb==yb;maxerr=max(maxerr,abs(x-y))
   if first is None and xb!=yb:first={'body':i,'name':p.rigids[i].name,'component':j,'actual':x,'expected':y,'actual_bits':xb.hex(),'expected_bits':yb.hex(),'mode':int(p.body_descs[i].mode)}
 row={'call':call,'dt':pre['dt'],'pre_exact':pre_exact,'exact':exact,'exact_floats':exact_f,'total_floats':339*12,'first':first,'maxerr':maxerr};summary.append(row);print('MMD_RAW_DIFF',json.dumps(row,ensure_ascii=False))
 break
result_path=Path(tempfile.gettempdir())/'spx_mmd_raw_core_parity.json'
result_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
assert summary, 'No positive MMD physics steps were compared'
assert len(summary)==1, 'Raw core certification must compare exactly one clean positive step'
failed=[row for row in summary if row['pre_exact'] != 339 or row['exact'] != 339 or row['exact_floats'] != row['total_floats']]
print('MMD_RAW_CORE_PARITY_RESULT',json.dumps({'steps':len(summary),'failed_steps':len(failed),'result':str(result_path)},ensure_ascii=False))
assert not failed, f'MMD raw core parity failed in {len(failed)}/{len(summary)} steps; see {result_path}'
print('MMD_RAW_CORE_PARITY_OK')


