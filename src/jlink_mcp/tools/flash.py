"""Flash Operations Tool Functions / Flash 操作工具函数."""

from typing import Dict, Any, Optional

from ..jlink_manager import jlink_manager
from ..exceptions import JLinkMCPError, JLinkErrorCode
from ..models.operations import FlashEraseRequest, FlashProgramRequest
from ..utils import logger, human_readable_size


def erase_flash(
    start_address: Optional[int] = None,
    end_address: Optional[int] = None,
    chip_erase: bool = False
) -> Dict[str, Any]:
    """擦除 Flash.

    Args:
        start_address: 起始地址（可选）
        end_address: 结束地址（可选）
        chip_erase: 是否整片擦除（默认 False）

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - erase_type: 擦除类型（chip/sector）
        - bytes_erased: 擦除的字节数
        - message: 状态信息
    """
    try:
        jlink = jlink_manager.get_jlink()

        if chip_erase:
            # 整片擦除
            logger.info("执行整片擦除")
            jlink.erase()
            erase_type = "chip"
            bytes_erased = 0  # 整片擦除无法知道具体字节数
        elif start_address is not None and end_address is not None:
            # 指定范围擦除
            if start_address >= end_address:
                raise JLinkMCPError(
                    JLinkErrorCode.INVALID_PARAMETER,
                    f"起始地址 {start_address:#x} 必须小于结束地址 {end_address:#x}"
                )

            size = end_address - start_address
            logger.info(f"擦除 Flash {start_address:#x} - {end_address:#x} ({human_readable_size(size)})")

            # 分扇区擦除
            jlink.exec_command(f"EraseSector {start_address:#x} {(end_address - 1):#x}")
            erase_type = "sector"
            bytes_erased = size
        else:
            raise JLinkMCPError(
                JLinkErrorCode.INVALID_PARAMETER,
                "必须指定 chip_erase=True 或提供 start_address 和 end_address"
            )

        logger.info("Flash 擦除成功")
        return {
            "success": True,
            "erase_type": erase_type,
            "bytes_erased": bytes_erased,
            "message": f"Flash 擦除成功（{erase_type}）"
        }
    except JLinkMCPError as e:
        logger.error(f"擦除 Flash 失败: {e}")
        return {
            "success": False,
            "erase_type": None,
            "bytes_erased": 0,
            "error": e.to_dict()
        }
    except Exception as e:
        logger.error(f"擦除 Flash 失败: {e}")
        return {
            "success": False,
            "erase_type": None,
            "bytes_erased": 0,
            "error": {
                "code": JLinkErrorCode.ERASE_FAILED.value[0],
                "description": str(e),
                "suggestion": "请检查 Flash 是否被保护，尝试先解除保护"
            }
        }


def program_flash(address: int, data: bytes, verify: bool = True) -> Dict[str, Any]:
    """烧录固件到 Flash.

    Args:
        address: 起始地址
        data: 要烧录的数据
        verify: 烧录后是否校验（默认 True）

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - bytes_programmed: 烧录的字节数
        - verify_result: 校验结果（如果 verify=True）
        - message: 状态信息
    """
    try:
        if not data:
            raise JLinkMCPError(JLinkErrorCode.INVALID_PARAMETER, "数据不能为空")

        jlink = jlink_manager.get_jlink()

        logger.info(f"烧录 Flash {address:#x} 大小 {human_readable_size(len(data))}")
        jlink.flash(data, address)

        verify_result = None
        if verify:
            # 校验
            logger.info("校验 Flash")
            read_back = jlink.memory_read(address, len(data), nbits=8)

            if read_back == list(data):
                verify_result = {"matched": True, "mismatches": []}
                logger.info("Flash 校验成功")
            else:
                # 找出不匹配的位置
                mismatches = []
                for i, (a, b) in enumerate(zip(data, read_back)):
                    if a != b:
                        mismatches.append({"address": address + i, "expected": a, "actual": b})

                verify_result = {"matched": False, "mismatches": mismatches}
                logger.warning(f"Flash 校验失败，{len(mismatches)} 处不匹配")

        logger.info("Flash 烧录成功")
        return {
            "success": True,
            "bytes_programmed": len(data),
            "verify_result": verify_result,
            "message": f"成功烧录 {human_readable_size(len(data))} 到 Flash"
        }
    except JLinkMCPError as e:
        logger.error(f"烧录 Flash 失败: {e}")
        return {
            "success": False,
            "bytes_programmed": 0,
            "verify_result": None,
            "error": e.to_dict()
        }
    except Exception as e:
        logger.error(f"烧录 Flash 失败: {e}")
        return {
            "success": False,
            "bytes_programmed": 0,
            "verify_result": None,
            "error": {
                "code": JLinkErrorCode.VERIFY_FAILED.value[0],
                "description": str(e),
                "suggestion": "请检查 Flash 是否已擦除，地址是否有效"
            }
        }


def _parse_intel_hex(data: bytes) -> tuple[int, list[int]]:
    """Parse Intel HEX format and return (start_address, byte_list)."""
    min_addr = 0xFFFFFFFF
    max_addr = 0
    segments = {}
    extended_addr = 0
    lines = data.decode('ascii', errors='ignore').splitlines()

    for line in lines:
        line = line.strip()
        if not line.startswith(':'):
            continue
        try:
            byte_count = int(line[1:3], 16)
            addr = int(line[3:7], 16)
            rectype = int(line[7:9], 16)
            if rectype == 0x04:  # Extended Linear Address
                extended_addr = int(line[9:9 + byte_count * 2], 16) << 16
            elif rectype == 0x00:  # Data record
                abs_addr = extended_addr + addr
                record_data = bytes.fromhex(line[9:9 + byte_count * 2])
                segments[abs_addr] = record_data
                min_addr = min(min_addr, abs_addr)
                max_addr = max(max_addr, abs_addr + byte_count)
            elif rectype == 0x01:  # EOF
                break
        except (ValueError, IndexError):
            continue

    if min_addr == 0xFFFFFFFF:
        raise ValueError("No valid HEX data records found")

    size = max_addr - min_addr
    result = bytearray(size)
    for addr, seg_data in segments.items():
        result[addr - min_addr:addr - min_addr + len(seg_data)] = seg_data

    return min_addr, list(result)


def program_file(path: str, address: int = 0x08000000) -> Dict[str, Any]:
    """烧录固件文件到 Flash（支持 .hex 和 .bin 格式）.

    自动检测文件格式：
    - .hex 文件：解析 Intel HEX 记录，提取地址和数据
    - .bin 文件：直接读取为二进制数据

    Args:
        path: 固件文件路径（.hex 或 .bin）
        address: Flash 起始地址（仅 .bin 文件使用，.hex 文件使用内部地址）

    Returns:
        烧录结果，包含 bytes_programmed、verify_result 等字段
    """
    try:
        with open(path, 'rb') as f:
            raw_data = f.read()

        if not raw_data:
            raise JLinkMCPError(JLinkErrorCode.INVALID_PARAMETER, f"文件为空: {path}")

        # Auto-detect format
        if path.lower().endswith('.hex') or raw_data[:1] == b':':
            # Intel HEX format
            actual_addr, byte_list = _parse_intel_hex(raw_data)
            logger.info(f"解析 HEX 文件 {path}: {len(byte_list)} 字节, 起始地址 {actual_addr:#x}")
            return program_flash(actual_addr, byte_list, verify=True)
        else:
            # Raw binary
            byte_list = list(raw_data)
            logger.info(f"读取 BIN 文件 {path}: {len(byte_list)} 字节")
            return program_flash(address, byte_list, verify=True)

    except FileNotFoundError:
        logger.error(f"文件未找到: {path}")
        return {
            "success": False,
            "bytes_programmed": 0,
            "error": {
                "code": JLinkErrorCode.INVALID_PARAMETER.value[0],
                "description": f"文件未找到: {path}",
                "suggestion": "请检查文件路径是否正确"
            }
        }
    except Exception as e:
        logger.error(f"烧录文件失败: {e}")
        return {
            "success": False,
            "bytes_programmed": 0,
            "error": {
                "code": JLinkErrorCode.FLASH_PROGRAM_FAILED.value[0],
                "description": str(e),
                "suggestion": "请检查文件格式和 Flash 地址是否正确"
            }
        }


def verify_flash(address: int, data: bytes) -> Dict[str, Any]:
    """校验 Flash 内容.

    Args:
        address: 起始地址
        data: 期望的数据

    Returns:
        包含以下字段的字典:
        - success: 是否成功
        - matched: 数据是否匹配
        - mismatches: 不匹配地址列表
        - message: 状态信息
    """
    try:
        if not data:
            raise JLinkMCPError(JLinkErrorCode.INVALID_PARAMETER, "数据不能为空")

        jlink = jlink_manager.get_jlink()
        read_back = jlink.memory_read(address, len(data), nbits=8)

        if read_back == list(data):
            logger.info(f"Flash 校验成功（{len(data)} 字节）")
            return {
                "success": True,
                "matched": True,
                "mismatches": [],
                "message": f"Flash 校验成功（{len(data)} 字节）"
            }
        else:
            # 找出不匹配的位置
            mismatches = []
            for i, (a, b) in enumerate(zip(data, read_back)):
                if a != b:
                    mismatches.append({
                        "address": address + i,
                        "expected": a,
                        "actual": b
                    })

            logger.warning(f"Flash 校验失败，{len(mismatches)} 处不匹配")
            return {
                "success": True,
                "matched": False,
                "mismatches": mismatches,
                "message": f"Flash 校验失败，{len(mismatches)} 处不匹配"
            }
    except JLinkMCPError as e:
        logger.error(f"校验 Flash 失败: {e}")
        return {
            "success": False,
            "matched": False,
            "mismatches": [],
            "error": e.to_dict()
        }
    except Exception as e:
        logger.error(f"校验 Flash 失败: {e}")
        return {
            "success": False,
            "matched": False,
            "mismatches": [],
            "error": {
                "code": JLinkErrorCode.VERIFY_FAILED.value[0],
                "description": str(e),
                "suggestion": "请检查地址是否有效"
            }
        }


def verify_file(path: str, address: int) -> Dict[str, Any]:
    """Verify Flash content against a local file / 校验 Flash 内容与本地文件是否一致.

    Reads a binary file from the local filesystem and compares it with Flash contents.

    Args:
        path: Path to the binary file on the local filesystem / 本地文件系统路径
        address: Start address in Flash to verify / 要校验的 Flash 起始地址

    Returns:
        Verification result, same format as verify_flash / 校验结果，与 verify_flash 格式相同
    """
    try:
        with open(path, 'rb') as f:
            data = f.read()
        if not data:
            raise JLinkMCPError(JLinkErrorCode.INVALID_PARAMETER, f"文件为空: {path}")
        logger.info(f"读取文件 {path} 成功，大小 {len(data)} 字节")
        return verify_flash(address, list(data))
    except FileNotFoundError:
        logger.error(f"文件未找到: {path}")
        return {
            "success": False,
            "matched": False,
            "mismatches": [],
            "error": {
                "code": JLinkErrorCode.INVALID_PARAMETER.value[0],
                "description": f"文件未找到: {path}",
                "suggestion": "请检查文件路径是否正确"
            }
        }
    except Exception as e:
        logger.error(f"校验文件失败: {e}")
        return {
            "success": False,
            "matched": False,
            "mismatches": [],
            "error": {
                "code": JLinkErrorCode.VERIFY_FAILED.value[0],
                "description": str(e),
                "suggestion": "请检查文件路径和 Flash 地址是否正确"
            }
        }