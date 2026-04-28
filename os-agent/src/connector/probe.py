"""环境探测模块 - 支持多发行版检测"""
import platform
import os
import subprocess
from typing import List
from src.agent.models import Environment
from src.utils.logger import log


class EnvironmentProbe:
    """环境探测器 - 支持Windows、Linux各发行版"""

    def detect(self) -> Environment:
        """探测当前服务器环境"""
        env = Environment()

        # 获取系统信息
        env.os_name = platform.system()
        env.os_version = platform.version()
        env.hostname = platform.node()
        env.kernel = platform.release()

        # 获取当前用户
        env.current_user = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

        # 获取工作目录
        env.working_dir = os.getcwd()

        # 检测Linux发行版
        if env.os_name == "Linux":
            self._detect_linux_distro(env)

        log.info(f"环境探测完成: os={env.os_name}, distro={env.distro_name}, pkg_mgr={env.package_manager}")
        return env

    def _detect_linux_distro(self, env: Environment):
        """检测Linux发行版 - 支持主流国产和国际发行版"""
        # 方法1: 读取 /etc/os-release (最标准的方法，systemd系统都支持)
        if os.path.exists("/etc/os-release"):
            try:
                with open("/etc/os-release", "r") as f:
                    content = f.read()
                    for line in content.split("\n"):
                        if line.startswith("ID="):
                            distro_id = line.split("=")[1].strip().strip('"')
                            env.distro_name = self._normalize_distro_name(distro_id)
                        elif line.startswith("VERSION_ID="):
                            env.distro_version = line.split("=")[1].strip().strip('"')
                        elif line.startswith("NAME="):
                            if not env.distro_name:
                                name = line.split("=")[1].strip().strip('"')
                                env.distro_name = name
            except Exception as e:
                log.warning(f"读取 /etc/os-release 失败: {e}")

        # 方法2: 检查发行版特定文件 (兼容旧系统)
        if not env.distro_name:
            distro_files = [
                ("/etc/openEuler-release", "openEuler"),
                ("/etc/kylin-release", "Kylin"),
                ("/etc/UOS-release", "UOS"),
                ("/etc/centos-release", "CentOS"),
                ("/etc/redhat-release", "RHEL"),
                ("/etc/fedora-release", "Fedora"),
                ("/etc/lsb-release", "Ubuntu"),
                ("/etc/debian_version", "Debian"),
                ("/etc/alinux-release", "Alibaba Cloud Linux"),
                ("/etc/tencentos-release", "TencentOS"),
            ]
            for file_path, distro in distro_files:
                if os.path.exists(file_path):
                    env.distro_name = distro
                    # 尝试读取版本号
                    try:
                        with open(file_path, "r") as f:
                            content = f.read()
                            import re
                            version_match = re.search(r'(\d+\.\d+(\.\d+)?)', content)
                            if version_match:
                                env.distro_version = version_match.group(1)
                    except:
                        pass
                    break

        # 方法3: 使用lsb_release命令 (部分系统支持)
        if not env.distro_name:
            try:
                result = subprocess.run(["lsb_release", "-a"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.split("\n"):
                        if line.startswith("Distributor ID:"):
                            env.distro_name = line.split(":")[1].strip()
                        elif line.startswith("Release:"):
                            env.distro_version = line.split(":")[1].strip()
            except:
                pass

        # 检测包管理器
        env.package_manager = self._detect_package_manager(env.distro_name)

        log.debug(f"Linux发行版检测结果: {env.distro_name} {env.distro_version}, 包管理器: {env.package_manager}")

    def _normalize_distro_name(self, distro_id: str) -> str:
        """标准化发行版名称 - 支持主流国产和国际发行版"""
        distro_map = {
            # 国际主流
            "centos": "CentOS",
            "rhel": "RHEL",
            "ubuntu": "Ubuntu",
            "debian": "Debian",
            "fedora": "Fedora",
            "opensuse": "openSUSE",
            "sles": "SUSE",
            "arch": "Arch Linux",
            "alpine": "Alpine",
            "amzn": "Amazon Linux",
            # 国产发行版
            "openeuler": "openEuler",
            "kylin": "Kylin",
            "uos": "UOS",
            "neokylin": "NeoKylin",
            "deepin": "Deepin",
            "aliyun": "Alibaba Cloud Linux",
            "alinux": "Alibaba Cloud Linux",
            "tencentos": "TencentOS",
            "anolis": "Anolis OS",
            "bclinux": "BigCloud Linux",
        }
        return distro_map.get(distro_id.lower(), distro_id)

    def _detect_package_manager(self, distro_name: str) -> str:
        """检测包管理器 - 基于发行版和实际命令可用性"""
        # 发行版到包管理器的映射 (优先级从高到低)
        distro_pkg_map = {
            # RHEL系 - 优先dnf (Fedora 22+, CentOS 8+, openEuler)
            "CentOS": ["dnf", "yum"],
            "RHEL": ["dnf", "yum"],
            "Fedora": ["dnf", "yum"],
            "openEuler": ["dnf", "yum"],
            "Alibaba Cloud Linux": ["dnf", "yum"],
            "TencentOS": ["dnf", "yum"],
            "Anolis OS": ["dnf", "yum"],
            "BigCloud Linux": ["dnf", "yum"],
            # Debian系
            "Ubuntu": ["apt", "apt-get"],
            "Debian": ["apt", "apt-get"],
            "Deepin": ["apt", "apt-get"],
            "UOS": ["apt", "apt-get"],
            "Kylin": ["apt", "apt-get"],
            "NeoKylin": ["apt", "yum"],
            # 其他
            "openSUSE": ["zypper"],
            "SUSE": ["zypper"],
            "Arch Linux": ["pacman"],
            "Alpine": ["apk"],
            "Amazon Linux": ["yum", "dnf"],
        }

        # 如果发行版已识别，使用对应的包管理器
        if distro_name in distro_pkg_map:
            for pkg_mgr in distro_pkg_map[distro_name]:
                if self._command_exists(pkg_mgr):
                    return pkg_mgr

        # 通用检测：检查哪些命令存在
        all_pkg_mgrs = ["apt", "apt-get", "dnf", "yum", "pacman", "zypper", "apk"]
        for pkg_mgr in all_pkg_mgrs:
            if self._command_exists(pkg_mgr):
                return pkg_mgr

        log.warning(f"未检测到包管理器，发行版: {distro_name}")
        return "unknown"

    def _command_exists(self, command: str) -> bool:
        """检查命令是否存在 - 跨平台兼容"""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["where", command],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            else:
                result = subprocess.run(
                    ["which", command],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            return result.returncode == 0
        except Exception as e:
            log.debug(f"检查命令 {command} 是否存在时出错: {e}")
            return False

    def get_distro_info(self) -> dict:
        """获取完整的发行版信息"""
        env = self.detect()
        return {
            "os_name": env.os_name,
            "os_version": env.os_version,
            "distro_name": env.distro_name,
            "distro_version": env.distro_version,
            "kernel": env.kernel,
            "hostname": env.hostname,
            "current_user": env.current_user,
            "package_manager": env.package_manager,
        }

    def check_health(self, executor=None) -> List[str]:
        """检查系统健康状态，返回警告列表

        检查项:
        - 磁盘使用率 > 90%
        - 内存使用率 > 90%

        Args:
            executor: 命令执行器（可选，默认使用subprocess）

        Returns:
            警告消息列表，空列表表示一切正常
        """
        warnings = []

        try:
            if executor:
                # 使用传入的执行器（支持远程服务器）
                disk_result = executor.execute("df -h / | tail -1 | awk '{print $5}'")
                if disk_result.success:
                    usage_str = disk_result.output.strip().rstrip('%')
                    try:
                        disk_usage = int(usage_str)
                        if disk_usage >= 95:
                            warnings.append(f"**磁盘空间严重不足:** 根分区使用率 {disk_usage}%，建议立即清理")
                        elif disk_usage >= 90:
                            warnings.append(f"**磁盘空间紧张:** 根分区使用率 {disk_usage}%，建议清理不必要的文件")
                    except ValueError:
                        pass

                mem_result = executor.execute("free | awk '/Mem:/ {printf \"%.0f\", $3/$2*100}'")
                if mem_result.success:
                    try:
                        mem_usage = int(mem_result.output.strip())
                        if mem_usage >= 95:
                            warnings.append(f"**内存严重不足:** 使用率 {mem_usage}%，系统可能变得不稳定")
                        elif mem_usage >= 90:
                            warnings.append(f"**内存紧张:** 使用率 {mem_usage}%，建议关闭不必要的进程")
                    except ValueError:
                        pass
            else:
                # 使用subprocess直接检查
                # 磁盘检查
                result = subprocess.run(
                    ["df", "-h", "/"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) >= 2:
                        parts = lines[1].split()
                        if len(parts) >= 5:
                            usage_str = parts[4].rstrip('%')
                            try:
                                disk_usage = int(usage_str)
                                if disk_usage >= 95:
                                    warnings.append(f"**磁盘空间严重不足:** 根分区使用率 {disk_usage}%，建议立即清理")
                                elif disk_usage >= 90:
                                    warnings.append(f"**磁盘空间紧张:** 根分区使用率 {disk_usage}%，建议清理不必要的文件")
                            except ValueError:
                                pass

                # 内存检查
                result = subprocess.run(
                    ["free"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if line.startswith('Mem:'):
                            parts = line.split()
                            if len(parts) >= 3:
                                total = int(parts[1])
                                used = int(parts[2])
                                if total > 0:
                                    mem_usage = int(used / total * 100)
                                    if mem_usage >= 95:
                                        warnings.append(f"**内存严重不足:** 使用率 {mem_usage}%，系统可能变得不稳定")
                                    elif mem_usage >= 90:
                                        warnings.append(f"**内存紧张:** 使用率 {mem_usage}%，建议关闭不必要的进程")
                            break

        except Exception as e:
            log.warning(f"系统健康检查失败: {e}")

        return warnings
