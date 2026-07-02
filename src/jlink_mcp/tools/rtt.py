"""RTT (Real Time Transfer) Tool Functions / RTT (Real Time Transfer) 工具函数."""

from typing import Dict, Any, Optional

from ..jlink_manager import jlink_manager
from ..exceptions import JLinkMCPError, JLinkErrorCode, RTTError
from ..utils import logger


# 全局 RTT 状态
_rtt_started = False
_rtt_config = {
    "buffer_index": 0,
    "read_mode": "continuous",
    "timeout_ms": 1000
}


def rtt_start(
    buffer_index: int = 0,
    read_mode: str = "continuous",
    timeout_ms: int = 1000
) -> Dict[str, Any]:
    """启动 RTT.

    Args:
        buffer_index: RTT 缓冲区索引（默认 0）
        read_mode: 读取模式（continuous/once，默认 continuous）
        timeout_ms: 超时时间（毫秒，默认 1000）

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - buffer_index: 缓冲区索引
        - message: 状态信息
    """
    global _rtt_started, _rtt_config

    try:
        if _rtt_started:
            # Already started - update config and return success instead of error
            _rtt_config = {
                "buffer_index": buffer_index,
                "read_mode": read_mode,
                "timeout_ms": timeout_ms
            }
            logger.info(f"RTT 已在运行（缓冲区 {buffer_index}），复用现有连接")
            return {
                "success": True,
                "buffer_index": buffer_index,
                "message": f"RTT 已在运行（缓冲区 {buffer_index}）"
            }

        jlink = jlink_manager.get_jlink()

        # 配置 RTT
        logger.info(f"启动 RTT，缓冲区索引: {buffer_index}")
        jlink.rtt_start(buffer_index)

        _rtt_started = True
        _rtt_config = {
            "buffer_index": buffer_index,
            "read_mode": read_mode,
            "timeout_ms": timeout_ms
        }

        return {
            "success": True,
            "buffer_index": buffer_index,
            "message": f"RTT 已启动（缓冲区 {buffer_index}）"
        }
    except RTTError as e:
        logger.error(f"启动 RTT 失败: {e}")
        return {
            "success": False,
            "buffer_index": buffer_index,
            "error": e.to_dict()
        }
    except Exception as e:
        logger.error(f"启动 RTT 失败: {e}")
        return {
            "success": False,
            "buffer_index": buffer_index,
            "error": {
                "code": JLinkErrorCode.RTT_NOT_STARTED.value[0],
                "description": str(e),
                "suggestion": "请确保目标固件已启用 RTT 并正确配置"
            }
        }


def rtt_stop() -> Dict[str, Any]:
    """停止 RTT.

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - message: 状态信息
    """
    global _rtt_started

    try:
        if not _rtt_started:
            raise RTTError(
                JLinkErrorCode.RTT_NOT_STARTED,
                "RTT 未启动",
                "无需停止"
            )

        jlink = jlink_manager.get_jlink()
        jlink.rtt_stop()

        _rtt_started = False
        logger.info("RTT 已停止")

        return {
            "success": True,
            "message": "RTT 已停止"
        }
    except RTTError as e:
        logger.error(f"停止 RTT 失败: {e}")
        return {
            "success": False,
            "error": e.to_dict()
        }
    except Exception as e:
        logger.error(f"停止 RTT 失败: {e}")
        return {
            "success": False,
            "error": {
                "code": JLinkErrorCode.UNKNOWN_ERROR.value[0],
                "description": str(e),
                "suggestion": "请检查 RTT 状态"
            }
        }


def rtt_read(
    buffer_index: int = 0,
    size: int = 1024,
    timeout_ms: Optional[int] = None
) -> Dict[str, Any]:
    """读取 RTT 日志.

    Args:
        buffer_index: RTT 缓冲区索引（默认 0）
        size: 读取大小（字节，默认 1024）
        timeout_ms: 超时时间（毫秒，None 则使用配置的值）

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - data: 读取的数据（字符串）
        - bytes_read: 读取的字节数
        - message: 状态信息
    """
    global _rtt_started, _rtt_config

    try:
        if not _rtt_started:
            raise RTTError(
                JLinkErrorCode.RTT_NOT_STARTED,
                "RTT 未启动",
                "请先调用 rtt_start 启动 RTT"
            )

        jlink = jlink_manager.get_jlink()

        # 使用配置的超时时间
        if timeout_ms is None:
            timeout_ms = _rtt_config.get("timeout_ms", 1000)

        # 读取 RTT 数据
        data = jlink.rtt_read(buffer_index, size)

        if data:
            # 兼容 JLink SDK 返回 list 或 bytes
            if isinstance(data, list):
                data = bytes(data)
            # 尝试解码为字符串
            try:
                text_data = data.decode('utf-8', errors='ignore')
            except Exception:
                text_data = data.decode('latin1')

            logger.info(f"RTT 读取 {len(data)} 字节")
            return {
                "success": True,
                "data": text_data,
                "bytes_read": len(data),
                "message": f"成功读取 {len(data)} 字节"
            }
        else:
            return {
                "success": True,
                "data": "",
                "bytes_read": 0,
                "message": "RTT 缓冲区为空"
            }

    except RTTError as e:
        logger.error(f"读取 RTT 失败: {e}")
        return {
            "success": False,
            "data": "",
            "bytes_read": 0,
            "error": e.to_dict()
        }
    except Exception as e:
        logger.error(f"读取 RTT 失败: {e}")
        return {
            "success": False,
            "data": "",
            "bytes_read": 0,
            "error": {
                "code": JLinkErrorCode.RTT_NOT_STARTED.value[0],
                "description": str(e),
                "suggestion": "请检查 RTT 是否已启动，缓冲区索引是否正确"
            }
        }


def rtt_read_raw(cb_address: int, buffer_index: int = 0) -> Dict[str, Any]:
    """直接读取 RTT 控制块并提取文本数据（无需先调用 rtt_start）。

    通过读取目标内存中的 SEGGER RTT 控制块，解析 up-buffer 结构，
    直接获取 RTT 终端输出。适用于 pylink RTT API 不可用时的备选方案。

    控制块结构（SEGGER RTT）:
        Offset 0x00: acID[16] = "SEGGER RTT"
        Offset 0x10: MaxNumUpBuffers (4B)
        Offset 0x14: MaxNumDownBuffers (4B)
        Offset 0x18: aUp[0].sName (4B ptr)
        Offset 0x1C: aUp[0].pBuffer (4B ptr) ← 数据缓冲区地址
        Offset 0x20: aUp[0].SizeOfBuffer (4B)
        Offset 0x24: aUp[0].WrOff (4B)       ← 写入偏移
        Offset 0x28: aUp[0].RdOff (4B)       ← 读取偏移
        Offset 0x30: aUp[1]... (每个 24 字节)

    Args:
        cb_address: RTT 控制块地址（从 map 文件获取 _SEGGER_RTT 符号）
        buffer_index: up-buffer 索引（默认 0 = 终端输出）

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - data: 解码后的文本数据
        - bytes_read: 读取的字节数
        - buffer_addr: 数据缓冲区地址
        - wr_off: 写入偏移
        - message: 状态信息
    """
    try:
        jlink = jlink_manager.get_jlink()

        # Read CB header (16 bytes acID + 8 bytes config)
        cb_data = jlink.memory_read(cb_address, 48, nbits=8)

        # Verify magic "SEGGER RTT"
        magic = bytes(cb_data[:16]).decode('ascii', errors='ignore')
        if not magic.startswith("SEGGER RTT"):
            return {
                "success": False,
                "data": "",
                "bytes_read": 0,
                "error": {
                    "code": -1,
                    "description": f"RTT 控制块无效 (magic={magic[:20]})",
                    "suggestion": "请确认 cb_address 是否正确，固件是否已初始化 RTT"
                }
            }

        # Parse up-buffer descriptor (offset 24 + buf_index * 24)
        desc_offset = 24 + buffer_index * 24
        if desc_offset + 24 > len(cb_data):
            # Need to read more
            more = jlink.memory_read(cb_address + desc_offset, 24, nbits=8)
        else:
            more = cb_data[desc_offset:desc_offset + 24]

        # pBuffer at descriptor offset 4
        pbuf = more[4] | (more[5] << 8) | (more[6] << 16) | (more[7] << 24)
        size = more[8] | (more[9] << 8) | (more[10] << 16) | (more[11] << 24)
        wr_off = more[12] | (more[13] << 8) | (more[14] << 16) | (more[15] << 24)

        if pbuf == 0 or size == 0:
            return {
                "success": False,
                "data": "",
                "bytes_read": 0,
                "error": {
                    "code": -1,
                    "description": f"RTT up-buffer {buffer_index} 未配置 (pbuf=0x{pbuf:08X}, size={size})",
                    "suggestion": "固件中需要调用 SEGGER_RTT_ConfigUpBuffer 或使用 RTT_LOG 宏"
                }
            }

        # Read buffer data
        if wr_off > size:
            wr_off = size
        if wr_off > 0:
            buf_data = jlink.memory_read(pbuf, wr_off, nbits=8)
            text = bytes(buf_data).decode('utf-8', errors='ignore')
        else:
            text = ""

        logger.info(f"RTT raw read: pbuf=0x{pbuf:08X}, wr={wr_off}, size={size}")
        return {
            "success": True,
            "data": text,
            "bytes_read": wr_off,
            "buffer_addr": pbuf,
            "wr_off": wr_off,
            "size": size,
            "message": f"成功读取 {wr_off} 字节 (缓冲区 {buffer_index})"
        }

    except Exception as e:
        logger.error(f"RTT raw read 失败: {e}")
        return {
            "success": False,
            "data": "",
            "bytes_read": 0,
            "error": {
                "code": -1,
                "description": str(e),
                "suggestion": "请检查 cb_address 和 buffer_index 是否正确"
            }
        }


def rtt_write(data: str, buffer_index: int = 0) -> Dict[str, Any]:
    """向 RTT 写入数据.

    Args:
        data: 要写入的数据（字符串）
        buffer_index: RTT 缓冲区索引（默认 0）

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - bytes_written: 写入的字节数
        - message: 状态信息
    """
    global _rtt_started

    try:
        if not _rtt_started:
            raise RTTError(
                JLinkErrorCode.RTT_NOT_STARTED,
                "RTT 未启动",
                "请先调用 rtt_start 启动 RTT"
            )

        jlink = jlink_manager.get_jlink()

        # 编码数据
        data_bytes = data.encode('utf-8')

        # 写入 RTT
        bytes_written = jlink.rtt_write(buffer_index, data_bytes)

        logger.info(f"RTT 写入 {bytes_written} 字节")
        return {
            "success": True,
            "bytes_written": bytes_written,
            "message": f"成功写入 {bytes_written} 字节"
        }
    except RTTError as e:
        logger.error(f"RTT 写入失败: {e}")
        return {
            "success": False,
            "bytes_written": 0,
            "error": e.to_dict()
        }
    except Exception as e:
        logger.error(f"RTT 写入失败: {e}")
        return {
            "success": False,
            "bytes_written": 0,
            "error": {
                "code": JLinkErrorCode.RTT_NOT_STARTED.value[0],
                "description": str(e),
                "suggestion": "请检查 RTT 是否已启动"
            }
        }


def rtt_reset_state() -> None:
    """重置 RTT 状态（由 disconnect_device 调用）."""
    global _rtt_started
    _rtt_started = False
    logger.info("RTT 状态已重置（设备断开）")


def rtt_get_status() -> Dict[str, Any]:
    """获取 RTT 状态.

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - started: 是否已启动
        - buffer_index: 当前缓冲区索引
        - config: 当前配置
    """
    global _rtt_started, _rtt_config

    return {
        "success": True,
        "started": _rtt_started,
        "buffer_index": _rtt_config.get("buffer_index", 0) if _rtt_started else None,
        "config": _rtt_config if _rtt_started else None,
        "message": "RTT 已启动" if _rtt_started else "RTT 未启动"
    }