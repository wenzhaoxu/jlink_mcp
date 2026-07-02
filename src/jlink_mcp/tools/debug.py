"""Debug Control Tool Functions / 调试控制工具函数."""

from typing import Dict, Any, List, Optional

from ..jlink_manager import jlink_manager
from ..exceptions import JLinkMCPError, JLinkErrorCode
from ..models.operations import DebugBreakpoint, CPUState
from ..utils import logger

_breakpoint_handles: Dict[int, int] = {}  # address -> handle


def _strip_reg_comment(name: str) -> str:
    """Strip parenthetical suffix like ' (PC)' from register names for API lookup."""
    idx = name.find(' (')
    return name[:idx] if idx > 0 else name


def reset_target(reset_type: str = "normal") -> Dict[str, Any]:
    """复位目标芯片.

    Args:
        reset_type: 复位类型
            - normal: 普通复位
            - halt: 复位后暂停
            - core: 内核复位

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - reset_type: 复位类型
        - message: 状态信息
    """
    try:
        jlink = jlink_manager.get_jlink()

        if reset_type == "halt":
            logger.info("执行复位并暂停")
            jlink.reset(halt=True)
        elif reset_type == "core":
            logger.info("执行内核复位")
            jlink.reset(halt=True)
        else:  # normal
            logger.info("执行普通复位")
            jlink.reset(halt=False)

        return {
            "success": True,
            "reset_type": reset_type,
            "message": f"目标已复位（{reset_type}）"
        }
    except JLinkMCPError as e:
        logger.error(f"复位失败: {e}")
        return {
            "success": False,
            "reset_type": reset_type,
            "error": e.to_dict()
        }
    except Exception as e:
        logger.error(f"复位失败: {e}")
        return {
            "success": False,
            "reset_type": reset_type,
            "error": {
                "code": JLinkErrorCode.RESET_FAILED.value[0],
                "description": str(e),
                "suggestion": "请检查目标芯片连接和供电状态"
            }
        }


def halt_cpu() -> Dict[str, Any]:
    """暂停 CPU.

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - pc: 程序计数器值
        - message: 状态信息
    """
    try:
        jlink = jlink_manager.get_jlink()
        jlink.halt()

        pc = jlink.register_read("R15 (PC)")
        logger.info(f"CPU 已暂停，PC = {pc:#x}")

        return {
            "success": True,
            "pc": pc,
            "message": f"CPU 已暂停，PC = {pc:#x}"
        }
    except JLinkMCPError as e:
        logger.error(f"暂停 CPU 失败: {e}")
        return {
            "success": False,
            "pc": None,
            "error": e.to_dict()
        }
    except Exception as e:
        logger.error(f"暂停 CPU 失败: {e}")
        return {
            "success": False,
            "pc": None,
            "error": {
                "code": JLinkErrorCode.UNKNOWN_ERROR.value[0],
                "description": str(e),
                "suggestion": "请检查目标是否正在运行"
            }
        }


def run_cpu() -> Dict[str, Any]:
    """运行 CPU.

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - message: 状态信息
    """
    try:
        jlink = jlink_manager.get_jlink()

        try:
            if hasattr(jlink, "halted") and not jlink.halted():
                logger.info("CPU 已在运行，无需恢复")
                return {
                    "success": True,
                    "message": "CPU 已在运行"
                }
        except Exception:
            logger.debug("无法预先判断 CPU 是否已暂停，继续尝试恢复运行")

        if hasattr(jlink, "restart"):
            restarted = jlink.restart(skip_breakpoints=True)
            if restarted:
                logger.info("CPU 已恢复运行")
                return {
                    "success": True,
                    "message": "CPU 已恢复运行"
                }

            if hasattr(jlink, "halted") and not jlink.halted():
                logger.info("CPU 已恢复运行")
                return {
                    "success": True,
                    "message": "CPU 已恢复运行"
                }

        raise RuntimeError(
            "当前 pylink 版本不支持在不复位的情况下继续运行目标，请升级 pylink-square 或改用 reset_target"
        )
    except JLinkMCPError as e:
        logger.error(f"运行 CPU 失败: {e}")
        return {
            "success": False,
            "error": e.to_dict()
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"运行 CPU 失败: {error_msg}")
        return {
            "success": False,
            "error": {
                "code": JLinkErrorCode.UNKNOWN_ERROR.value[0],
                "description": error_msg,
                "suggestion": "请检查目标芯片状态；如需重新启动程序请使用 reset_target，而非 run_cpu"
            }
        }


def step_instruction() -> Dict[str, Any]:
    """单步执行一条指令.

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - pc: 程序计数器值
        - message: 状态信息
    """
    try:
        jlink = jlink_manager.get_jlink()
        jlink.step()

        pc = jlink.register_read("R15 (PC)")
        logger.info(f"单步执行，PC = {pc:#x}")

        return {
            "success": True,
            "pc": pc,
            "message": f"单步执行完成，PC = {pc:#x}"
        }
    except JLinkMCPError as e:
        logger.error(f"单步执行失败: {e}")
        return {
            "success": False,
            "pc": None,
            "error": e.to_dict()
        }
    except Exception as e:
        logger.error(f"单步执行失败: {e}")
        return {
            "success": False,
            "pc": None,
            "error": {
                "code": JLinkErrorCode.UNKNOWN_ERROR.value[0],
                "description": str(e),
                "suggestion": "请确保目标已暂停"
            }
        }


def get_cpu_state() -> Dict[str, Any]:
    """获取 CPU 状态.

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - running: 是否正在运行
        - halted: 是否已暂停
        - pc: 程序计数器
        - lr: 链接寄存器
        - sp: 堆栈指针
    """
    try:
        jlink = jlink_manager.get_jlink()

        # 检查运行状态
        halted = jlink.halted()
        running = not halted

        pc = lr = sp = None
        if halted:
            try:
                pc = jlink.register_read("R15 (PC)")
                lr = jlink.register_read("R14")  # LR 寄存器名称是 R14，不是 R14 (LR)
                sp = jlink.register_read("R13 (SP)")
            except Exception as e:
                logger.warning(f"读取寄存器失败: {e}")

        # Detect CPU in reset: PC=0 typically means CPU is held in reset or debug connection lost
        if halted and (pc is None or pc == 0):
            logger.warning("CPU 已暂停但 PC=0，可能处于复位状态或调试连接异常")
            return {
                "success": True,
                "running": False,
                "halted": True,
                "pc": pc,
                "lr": lr,
                "sp": sp,
                "message": "CPU 状态: 已暂停 (PC=0，可能处于复位状态，请执行 run_cpu 或检查硬件连接)"
            }

        logger.info(f"CPU 状态: {'运行' if running else '暂停'}")
        return {
            "success": True,
            "running": running,
            "halted": halted,
            "pc": pc,
            "lr": lr,
            "sp": sp,
            "message": f"CPU 状态: {'运行中' if running else '已暂停'}"
        }
    except JLinkMCPError as e:
        logger.error(f"获取 CPU 状态失败: {e}")
        return {
            "success": False,
            "running": False,
            "halted": False,
            "pc": None,
            "lr": None,
            "sp": None,
            "error": e.to_dict()
        }
    except Exception as e:
        logger.error(f"获取 CPU 状态失败: {e}")
        return {
            "success": False,
            "running": False,
            "halted": False,
            "pc": None,
            "lr": None,
            "sp": None,
            "error": {
                "code": JLinkErrorCode.UNKNOWN_ERROR.value[0],
                "description": str(e),
                "suggestion": "请检查设备连接状态"
            }
        }


def set_breakpoint(address: int) -> Dict[str, Any]:
    """设置断点.

    Args:
        address: 断点地址

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - address: 断点地址
        - message: 状态信息
    """
    try:
        jlink = jlink_manager.get_jlink()

        # 确保目标已暂停
        if not jlink.halted():
            raise JLinkMCPError(
                JLinkErrorCode.TARGET_RUNNING,
                "目标正在运行，无法设置断点",
                "请先调用 halt_cpu 暂停目标"
            )

        # 设置断点
        handle = jlink.breakpoint_set(address)
        _breakpoint_handles[address] = handle

        # Verify FPB is enabled (Cortex-M: check FP_CTRL @ 0xE0002000)
        fpb_enabled = False
        try:
            fpb_ctrl_addr = 0xE0002000
            fpb_ctrl = jlink.memory_read32(fpb_ctrl_addr, 1)[0]
            fpb_enabled = bool(fpb_ctrl & 0x1)
            if not fpb_enabled:
                logger.warning(f"FPB 未使能 (FP_CTRL=0x{fpb_ctrl:08X})，断点可能不生效")
                # Try to enable FPB
                try:
                    jlink.memory_write32(fpb_ctrl_addr, [0x3])  # ENABLE(bit0) + KEY(bit1)
                    fpb_ctrl2 = jlink.memory_read32(fpb_ctrl_addr, 1)[0]
                    fpb_enabled = bool(fpb_ctrl2 & 0x1)
                    if fpb_enabled:
                        logger.info("已手动使能 FPB 单元")
                except Exception:
                    pass
        except Exception:
            logger.debug("无法验证 FPB 状态（可能目标不支持）")

        logger.info(f"断点已设置: {address:#x} (FPB使能={fpb_enabled})")
        return {
            "success": True,
            "address": address,
            "fpb_enabled": fpb_enabled,
            "message": f"断点已设置: {address:#x}" + ("" if fpb_enabled else " (警告: FPB未使能，断点可能不生效)")
        }
    except JLinkMCPError as e:
        logger.error(f"设置断点失败: {e}")
        return {
            "success": False,
            "address": address,
            "error": e.to_dict()
        }
    except Exception as e:
        logger.error(f"设置断点失败: {e}")
        return {
            "success": False,
            "address": address,
            "error": {
                "code": JLinkErrorCode.UNKNOWN_ERROR.value[0],
                "description": str(e),
                "suggestion": "请检查地址是否有效，是否已达到断点数量限制"
            }
        }


def clear_breakpoint(address: int) -> Dict[str, Any]:
    """清除断点.

    Args:
        address: 断点地址

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - address: 断点地址
        - message: 状态信息
    """
    try:
        jlink = jlink_manager.get_jlink()

        # 清除断点
        handle = _breakpoint_handles.pop(address, None)
        if handle is None:
            handle = jlink.breakpoint_find(address)
        if handle:
            jlink.breakpoint_clear(handle)

        logger.info(f"断点已清除: {address:#x}")
        return {
            "success": True,
            "address": address,
            "message": f"断点已清除: {address:#x}"
        }
    except JLinkMCPError as e:
        logger.error(f"清除断点失败: {e}")
        return {
            "success": False,
            "address": address,
            "error": e.to_dict()
        }
    except Exception as e:
        logger.error(f"清除断点失败: {e}")
        return {
            "success": False,
            "address": address,
            "error": {
                "code": JLinkErrorCode.UNKNOWN_ERROR.value[0],
                "description": str(e),
                "suggestion": "请检查地址是否正确"
            }
        }

def clear_all_breakpoints() -> Dict[str, Any]:
    """Clear all hardware breakpoints / 清除所有硬件断点.

    Iterates through all known breakpoints and clears them one by one.
    遍历所有已知断点并逐一清除。

    Returns:
        Clear result, with list of cleared addresses / 清除结果，包含已清除的地址列表
    """
    global _breakpoint_handles

    try:
        jlink = jlink_manager.get_jlink()
        cleared = []
        errors = []

        # Clear by handle (our tracked breakpoints)
        addresses = list(_breakpoint_handles.keys())
        for addr in addresses:
            try:
                jlink.breakpoint_clear(_breakpoint_handles[addr])
                cleared.append(addr)
            except Exception as e:
                errors.append({"address": addr, "error": str(e)})

        # Also try to find and clear any FPB breakpoints not in our list
        try:
            if hasattr(jlink, 'fpb_num_breakpoints'):
                for i in range(jlink.fpb_num_breakpoints()):
                    bp = jlink.fpb_breakpoint(i)
                    if bp is not None and bp.address not in addresses:
                        try:
                            jlink.fpb_breakpoint_clear(i)
                            cleared.append(bp.address)
                        except Exception:
                            pass
        except Exception:
            pass

        _breakpoint_handles.clear()

        logger.info(f"清除了 {len(cleared)} 个断点")
        return {
            "success": True,
            "cleared_count": len(cleared),
            "addresses": cleared,
            "errors": errors if errors else None,
            "message": f"成功清除 {len(cleared)} 个断点" + (f"，{len(errors)} 个错误" if errors else "")
        }
    except Exception as e:
        logger.error(f"清除所有断点失败: {e}")
        return {
            "success": False,
            "cleared_count": 0,
            "addresses": [],
            "error": {
                "code": JLinkErrorCode.UNKNOWN_ERROR.value[0] if hasattr(JLinkErrorCode, 'UNKNOWN_ERROR') else -1,
                "description": str(e),
                "suggestion": "请检查目标是否已暂停"
            }
        }
