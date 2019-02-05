# -*- coding: utf-8 -*-

from ast_helper import *
import idaapi
import ida_name
import ida_xref
import idc

find_global_write = """Patterns.ObjBind("written")
"""

def xref_global(node, ctx):
    var = ctx.get_obj("written")
    print("%x at %x" % (var.addr, node.ea))
    # Terrible check to see if we're in a function
    if idc.get_func_flags(var.addr) == -1:
        ida_xref.add_dref(node.ea, var.addr, ida_xref.XREF_USER)
    return False

PATTERNS = []
EXPR_PATTERNS = [(find_global_write, xref_global, False)]

strlen_global = """Patterns.ChainPattern([
    Patterns.ExprInst(Patterns.AsgnExpr(Patterns.VarBind("t1"), Patterns.ObjBind("strlenarg"))),
    Patterns.DoInst(Patterns.LnotExpr(Patterns.VarBind("t2")),Patterns.BlockInst([
        Patterns.ExprInst(Patterns.AsgnExpr(Patterns.VarBind("t3"), Patterns.PtrExpr(Patterns.AnyPattern()))),
        Patterns.ExprInst(Patterns.AsgAddExpr(Patterns.VarBind("t1"),Patterns.NumberExpr(Patterns.NumberConcrete(4)))),
        Patterns.ExprInst(Patterns.AsgnExpr(Patterns.VarBind("t2"),
                Patterns.BAndExpr(
                    Patterns.BAndExpr(
                        Patterns.BnotExpr(Patterns.VarBind("t3")),
                        Patterns.SubExpr(Patterns.VarBind("t3"), Patterns.NumberExpr(Patterns.NumberConcrete(0x1010101)))
                    ),
                    Patterns.NumberExpr(Patterns.NumberConcrete(0x80808080))
                )
            )
        ),
        ], False)
    ),
    Patterns.ExprInst(Patterns.AsgnExpr(Patterns.AnyPattern(), Patterns.AnyPattern())),
    Patterns.IfInst(Patterns.AnyPattern(), Patterns.AnyPattern()),
    Patterns.IfInst(Patterns.AnyPattern(), Patterns.AnyPattern()),
    Patterns.ExprInst(Patterns.AsgnExpr(Patterns.VarBind("res"), Patterns.AnyPattern()))
])"""

def replacer_strlen_global(idx, ctx):
    var = ctx.get_var("res")
    varname = ctx.get_var_name(var.idx)
    obj = ctx.get_obj("strlenarg")

    varexp = make_var_expr(var.idx, var.typ, var.mba)
    arg1 = make_obj_expr(obj.addr, obj.type, arg=True)
    arglist = ida_hexrays.carglist_t()
    arglist.push_back(arg1)
    val = ida_hexrays.call_helper(ida_hexrays.dummy_ptrtype(4, False), arglist, "strlen_inlined")
    insn = make_cexpr_insn(idx.ea, make_asgn_expr(varexp, val))

    idx.cleanup()
    idaapi.qswap(idx, insn)
    # del original inst because we swapped them on previous line
    del insn
    return True

# Third arg - is chain
# PATTERNS = [(strlen_global, replacer_strlen_global, True)]

#=======================================
# This pattern is works with following case
#  dword_XXXX = (anytype)GetProcAddr(<anyArg>, 'funcName1')
#  dword_XXXY = (anytype)GetProcAddr(<anyArg>, 'funcName2')
#  ....
# After running this code if we decompile function where such pattern exist we will
#  automatically get:
#  funcName1 = (anytype)GetProcAddr(<anyArg>, 'funcName1')
#  funcName2 = (anytype)GetProcAddr(<anyArg>, 'funcName2')
#
#=======================================
get_proc_addr = """Patterns.ExprInst(
    Patterns.AsgnExpr(
        Patterns.ObjBind("fcnPtr"),
        Patterns.CastExpr(
            Patterns.CallExpr(
                Patterns.ObjConcrete(0x{:x}),
                [Patterns.AnyPattern(), Patterns.ObjBind("fcnName")]
            )
        )
    )
)
""".format(0x3)  # 0x3 - replace by addr of getProcAddr

def getProc_addr(idx, ctx):
    import ida_bytes
    obj = ctx.get_obj("fcnPtr")
    print "%x" % obj.addr
    name = ctx.get_obj("fcnName")
    name_str = ida_bytes.get_strlit_contents(name.addr, -1, -1)
    ida_name.set_name(obj.addr, name_str)
    return False

#PATTERNS = [(get_proc_addr, getProc_addr, False)]


#========================================
# This pattern will replace code like that
#   struct_XXX.field_X = (anytype)sub_XXXX
#   struct_XXX.field_Y = (anytype)sub_YYYY
# by
#   struct_XXX.sub_XXXX = (anytype)sub_XXXX
#   struct_XXX.sub_YYYY = (anytype)sub_YYYY
# 
# So, it's just renames structure fields
#========================================

global_struct_fields_sub = """
Patterns.ExprInst(
    Patterns.AsgnExpr(
        Patterns.MemRefGlobalBind('stroff'),
        Patterns.CastExpr(
            Patterns.ObjBind('fcn'),
        )
    )
)"""

def rename_struct_field_as_func_name(idx, ctx):
    import idc
    import ida_bytes
    obj = ctx.get_memref('stroff')
    print "%x" % obj.ea
    ti = idaapi.opinfo_t()
    f = idc.GetFlags(obj.ea)
    if idaapi.get_opinfo(obj.ea, 0, f, ti):
        print("tid=%08x - %s" % (ti.tid, idaapi.get_struc_name(ti.tid)))
    print "Offset: {}".format(obj.offset)
    import ida_struct
    obj2 = ctx.get_obj('fcn')
    print "%x" % obj2.addr
    name_str = ida_name.get_name(obj2.addr)
    print "Name {}".format(name_str)
    ida_struct.set_member_name(ida_struct.get_struc(ti.tid), obj.offset, name_str)
    return False

# PATTERNS = [(global_struct_fields_sub, rename_struct_field_as_func_name, False)]


#==============================
# Test case for BindExpr
# So it just saves all condition expressions from
# all if without else
#==============================


test_bind_expr = """Patterns.IfInst(Patterns.BindExpr('if_cond', Patterns.AnyPattern()), Patterns.AnyPattern())"""

def test_bind(idx, ctx):
    exprs = ctx.get_expr('if_cond')
    for i in exprs:
        print i
    return False
#PATTERNS = [(test_bind_expr, test_bind, False)]

#==============================================================
# Dummy example for switching vptr union based on variable type
# Here we have union like that
# union a{
#    vptr1_1 *class1;
#    struc_5 *class2;   
# }
#==============================================================

test_deep = """
Patterns.ExprInst(
    Patterns.CallExpr(
        Patterns.CastExpr(
            Patterns.MemptrExpr(
                Patterns.BindExpr(
                    'union_type',
                    Patterns.MemrefExpr(
                        Patterns.DeepExprPattern(
                            Patterns.MemptrExpr(Patterns.VarBind('v1'), 0, 8)
                        )
                    )
                )
            )
        ),
        [Patterns.AnyPattern() for i in range(12)]
    )
)
"""

test_deep_without_cast = """Patterns.ExprInst(
    Patterns.CallExpr(
        Patterns.MemptrExpr(
            Patterns.BindExpr(
                'union_type',
                Patterns.MemrefExpr(
                    Patterns.DeepExprPattern(
                        Patterns.MemptrExpr(Patterns.VarBind('v1'), 0, 8)
                    )
                )
            )
        ),
        [Patterns.AnyPattern() for i in range(12)]
    )
)
"""

def test_xx(idx, ctx):
    import ida_typeinf
    uni = ctx.get_expr('union_type')
    var = ctx.get_var('v1')
    tname =  var.typ.dstr().split(' ')[0]
    tinfo = idaapi.tinfo_t()
    if tname == 'class1':
        idaapi.parse_decl2(idaapi.cvar.idati, 'vptr1_1 *;', tinfo, idaapi.PT_TYP)
        uni[0].type = tinfo
        uni[0].m = 0
    elif tname == "class2":
        idaapi.parse_decl2(idaapi.cvar.idati, 'struc_5 *;', tinfo, idaapi.PT_TYP)
        uni[0].type = tinfo
        uni[0].m = 1
    else:
        return False
    return True

#PATTERNS = [(test_deep, test_xx, False), (test_deep_without_cast, test_xx, False)]


str_asgn = """Patterns.ExprInst(
    Patterns.AsgnExpr(Patterns.VarBind('r'),
                     Patterns.BindExpr('n',Patterns.NumberExpr())
                     )
)"""
GLOBAL = {}
MAX = 0
LAST_FCN_EA = None

def xx(inst, ctx):
    global MAX
    global GLOBAL
    global LAST_FCN_EA
    if LAST_FCN_EA is None:
        LAST_FCN_EA = ctx.fcn.entry_ea
    if LAST_FCN_EA != ctx.fcn.entry_ea:
        GLOBAL = {}
        MAX = 0
        LAST_FCN_EA = ctx.fcn.entry_ea
    print "{:x}".format(inst.ea)
    v = ctx.get_var('r')
    n = ctx.get_expr('n')[0]
    val = n.n._value
    v_o = get_var_offset(ctx.fcn, v.idx)
    print "Var offset from stack:", v_o
    print val
    if v_o > MAX:
        MAX = v_o
    if val < 256:
        if val == 0:
            GLOBAL[v_o] = "\\x00"
        else:
            GLOBAL[v_o] = chr(val)
    ret = ''
    for i in range(MAX+1):
        if i not in GLOBAL:
            ret += '_'
        else:

            ret += GLOBAL[i]
    print ret
#PATTERNS = [(str_asgn, xx, False)]
